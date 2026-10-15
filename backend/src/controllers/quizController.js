import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { newId } from "../utils/ids.js";
import { recordUserEvent } from "../services/analytics.js";
import {
  revealedQuestion,
  sanitizeResponses,
  scoreAttempt,
  studentQuestion,
} from "../services/quizScoring.js";
import {
  ACTIVITY_TYPES,
  LATE_GRACE_MS,
  getQuiz,
  getQuizItems,
  parseJson,
  publicQuiz,
  quizIsOpen,
  requireUuid,
  revealAllowed,
  studentCanSee,
} from "../services/quizData.js";

const listQuery = z.object({
  topic: z.string().max(120).optional(),
  difficulty: z.enum(["easy", "medium", "hard", "mixed"]).optional(),
  mode: z.enum(["practice", "assessment"]).optional(),
  activity_type: z.enum(ACTIVITY_TYPES).optional(),
});

export async function listQuizzes(req, res, next) {
  try {
    const q = listQuery.parse(req.query);
    const where = ["z.status = 'published'", "(z.owner_user_id IS NULL OR z.owner_user_id = ?)"];
    const params = [req.user.id];
    if (q.topic) {
      where.push("z.topic LIKE ?");
      params.push(`%${q.topic}%`);
    }
    if (q.difficulty) {
      where.push("z.difficulty = ?");
      params.push(q.difficulty);
    }
    if (q.mode) {
      where.push("z.mode = ?");
      params.push(q.mode);
    }
    if (q.activity_type) {
      where.push("z.activity_type = ?");
      params.push(q.activity_type);
    }
    const [rows] = await pool.query(
      `SELECT z.*,
        (SELECT COUNT(*) FROM quiz_items i WHERE i.quiz_id = z.id) AS question_count,
        (SELECT COUNT(*) FROM quiz_attempts a WHERE a.quiz_id = z.id AND a.user_id = ?) AS attempts_used,
        (SELECT MAX(a.percent) FROM quiz_attempts a WHERE a.quiz_id = z.id AND a.user_id = ? AND a.status = 'submitted') AS best_percent,
        (SELECT a.id FROM quiz_attempts a WHERE a.quiz_id = z.id AND a.user_id = ? AND a.status = 'in_progress' LIMIT 1) AS open_attempt_id
       FROM quizzes z WHERE ${where.join(" AND ")}
       ORDER BY z.owner_user_id IS NULL DESC, z.published_at DESC, z.created_at DESC LIMIT 200`,
      [req.user.id, req.user.id, req.user.id, ...params]
    );
    const now = new Date();
    res.json({
      quizzes: rows.map((row) => ({
        ...publicQuiz(row),
        question_count: Number(row.question_count),
        attempts_used: Number(row.attempts_used),
        best_percent: row.best_percent == null ? null : Number(row.best_percent),
        open_attempt_id: row.open_attempt_id || null,
        open: quizIsOpen(row, now),
      })),
    });
  } catch (err) {
    next(err);
  }
}

function deadlinePassed(attempt, now = new Date()) {
  return Boolean(attempt.deadline_at && now.getTime() > new Date(attempt.deadline_at).getTime() + LATE_GRACE_MS);
}

// Scores an attempt inside an open transaction (the attempt row is already locked).
async function finalizeAttempt(conn, attempt, quiz, responses, { late }) {
  const items = await getQuizItems(quiz.id, conn);
  const order = parseJson(attempt.question_order_json, []);
  const byId = new Map(items.map((item) => [item.id, item]));
  const ordered = order.map((id) => byId.get(id)).filter(Boolean);
  const clean = sanitizeResponses(responses, ordered.map((q) => q.id));
  const result = scoreAttempt(
    ordered.map((q) => ({ question: q, points: q.points })),
    clean
  );
  for (const a of result.answers) {
    await conn.query(
      `INSERT INTO quiz_answers (id, attempt_id, question_id, response_json, is_correct, points, max_points)
       VALUES (?,?,?,?,?,?,?)`,
      [newId(), attempt.id, a.questionId, a.response == null ? null : JSON.stringify(a.response), a.correct ? 1 : 0, a.points, a.maxPoints]
    );
  }
  const now = new Date();
  const submittedAt = late && attempt.deadline_at ? new Date(attempt.deadline_at) : now;
  const duration = Math.max(0, Math.round((submittedAt - new Date(attempt.started_at)) / 1000));
  await conn.query(
    `UPDATE quiz_attempts SET status = 'submitted', submitted_at = ?, score_points = ?, max_points = ?, percent = ?,
       duration_sec = ? WHERE id = ?`,
    [submittedAt, result.score, result.max, result.percent, duration, attempt.id]
  );
  return result;
}

async function buildResult(attemptId, userId) {
  const [rows] = await pool.query("SELECT * FROM quiz_attempts WHERE id = ? AND user_id = ?", [attemptId, userId]);
  const attempt = rows[0];
  const quiz = await getQuiz(attempt.quiz_id);
  const reveal = revealAllowed(quiz);
  const [answers] = await pool.query(
    `SELECT a.*, q.qtype, q.prompt, q.options_json, q.answer_json, q.explanation, q.topic, q.difficulty,
            q.textbook_page, q.source_document
     FROM quiz_answers a JOIN quiz_questions q ON q.id = a.question_id WHERE a.attempt_id = ?`,
    [attemptId]
  );
  const order = parseJson(attempt.question_order_json, []);
  answers.sort((x, y) => order.indexOf(x.question_id) - order.indexOf(y.question_id));
  const revise = new Map();
  for (const a of answers) {
    if (Number(a.points) < Number(a.max_points)) {
      const entry = revise.get(a.topic) || { topic: a.topic, pages: new Set(), missed: 0 };
      entry.missed += 1;
      if (a.textbook_page) entry.pages.add(a.textbook_page);
      revise.set(a.topic, entry);
    }
  }
  return {
    attempt: {
      id: attempt.id,
      quiz_id: attempt.quiz_id,
      attempt_no: attempt.attempt_no,
      status: attempt.status,
      started_at: attempt.started_at,
      submitted_at: attempt.submitted_at,
      duration_sec: attempt.duration_sec,
      score: Number(attempt.score_points),
      max_score: Number(attempt.max_points),
      percent: Number(attempt.percent),
    },
    quiz: publicQuiz(quiz),
    reveal,
    reveal_note: reveal
      ? null
      : quiz.reveal_answers === "after_close"
        ? "Answers will be shown after your teacher closes this assessment."
        : "Answers are not shown for this assessment.",
    questions: answers.map((a) => {
      const base = { id: a.question_id, qtype: a.qtype, prompt: a.prompt, topic: a.topic };
      if (!reveal) return base;
      return {
        ...revealedQuestion({ ...a, id: a.question_id }),
        response: parseJson(a.response_json),
        correct: Boolean(a.is_correct),
        points: Number(a.points),
        max_points: Number(a.max_points),
      };
    }),
    topics_to_revise: [...revise.values()].map((r) => ({
      topic: r.topic,
      missed: r.missed,
      textbook_pages: [...r.pages].sort((a, b) => a - b),
    })),
  };
}

async function inProgressPayload(attempt, quiz) {
  const items = await getQuizItems(quiz.id);
  const byId = new Map(items.map((item) => [item.id, item]));
  const order = parseJson(attempt.question_order_json, []);
  return {
    attempt: {
      id: attempt.id,
      quiz_id: quiz.id,
      attempt_no: attempt.attempt_no,
      status: attempt.status,
      started_at: attempt.started_at,
      deadline_at: attempt.deadline_at,
    },
    server_now: new Date().toISOString(),
    quiz: publicQuiz(quiz),
    questions: order.map((id) => byId.get(id)).filter(Boolean).map(studentQuestion),
    autosave: parseJson(attempt.autosave_json, {}) || {},
  };
}

// Finalizes an expired in-progress attempt from its last server autosave.
async function expireIfNeeded(attemptId) {
  const conn = await pool.getConnection();
  try {
    await conn.beginTransaction();
    const [rows] = await conn.query("SELECT * FROM quiz_attempts WHERE id = ? FOR UPDATE", [attemptId]);
    const attempt = rows[0];
    if (attempt && attempt.status === "in_progress" && deadlinePassed(attempt)) {
      const quiz = await getQuiz(attempt.quiz_id, conn);
      await finalizeAttempt(conn, attempt, quiz, parseJson(attempt.autosave_json, {}), { late: true });
    }
    await conn.commit();
  } catch (err) {
    await conn.rollback();
    throw err;
  } finally {
    conn.release();
  }
}

export async function startAttempt(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const quiz = await getQuiz(req.params.quizId, conn);
    if (!studentCanSee(quiz, req.user)) throw new AppError(404, "NOT_FOUND", "Quiz not found.");
    if (!quizIsOpen(quiz)) throw new AppError(409, "QUIZ_CLOSED", "This quiz is not open right now.");
    await conn.beginTransaction();
    // Serialize attempt creation per student, so double clicks cannot exceed the attempt limit.
    await conn.query("SELECT id FROM users WHERE id = ? FOR UPDATE", [req.user.id]);
    const [open] = await conn.query(
      "SELECT * FROM quiz_attempts WHERE quiz_id = ? AND user_id = ? AND status = 'in_progress' FOR UPDATE",
      [quiz.id, req.user.id]
    );
    if (open.length && !deadlinePassed(open[0])) {
      await conn.commit();
      res.json({ resumed: true, ...(await inProgressPayload(open[0], quiz)) });
      return;
    }
    if (open.length) {
      await finalizeAttempt(conn, open[0], quiz, parseJson(open[0].autosave_json, {}), { late: true });
    }
    const [[{ n }]] = await conn.query(
      "SELECT COUNT(*) AS n FROM quiz_attempts WHERE quiz_id = ? AND user_id = ?",
      [quiz.id, req.user.id]
    );
    if (quiz.max_attempts && Number(n) >= quiz.max_attempts) {
      await conn.commit();
      throw new AppError(409, "ATTEMPT_LIMIT", "You have used all attempts for this quiz.");
    }
    const items = await getQuizItems(quiz.id, conn);
    if (!items.length) throw new AppError(409, "QUIZ_EMPTY", "This quiz has no questions yet.");
    const id = newId();
    const now = new Date();
    const deadline = quiz.time_limit_sec ? new Date(now.getTime() + quiz.time_limit_sec * 1000) : null;
    await conn.query(
      `INSERT INTO quiz_attempts (id, quiz_id, user_id, attempt_no, status, started_at, deadline_at, question_order_json, autosave_json)
       VALUES (?,?,?,?, 'in_progress', ?, ?, ?, ?)`,
      [id, quiz.id, req.user.id, Number(n) + 1, now, deadline, JSON.stringify(items.map((q) => q.id)), JSON.stringify({})]
    );
    await conn.commit();
    await recordUserEvent(req.user.id, "QUIZ_STARTED", { quiz_id: quiz.id, attempt_id: id, activity_type: quiz.activity_type });
    const [rows] = await pool.query("SELECT * FROM quiz_attempts WHERE id = ?", [id]);
    res.status(201).json({ resumed: false, ...(await inProgressPayload(rows[0], quiz)) });
  } catch (err) {
    try {
      await conn.rollback();
    } catch {
      /* already committed */
    }
    next(err);
  } finally {
    conn.release();
  }
}

async function ownedAttempt(attemptId, user) {
  requireUuid(attemptId, "attempt id");
  const [rows] = await pool.query("SELECT * FROM quiz_attempts WHERE id = ?", [attemptId]);
  // Another student's attempt looks exactly like a missing one (no IDOR signal).
  if (!rows.length || rows[0].user_id !== user.id) throw new AppError(404, "NOT_FOUND", "Attempt not found.");
  return rows[0];
}

export async function getAttempt(req, res, next) {
  try {
    let attempt = await ownedAttempt(req.params.attemptId, req.user);
    if (attempt.status === "in_progress" && deadlinePassed(attempt)) {
      await expireIfNeeded(attempt.id);
      attempt = await ownedAttempt(attempt.id, req.user);
    }
    if (attempt.status === "in_progress") {
      const quiz = await getQuiz(attempt.quiz_id);
      res.json(await inProgressPayload(attempt, quiz));
      return;
    }
    res.json(await buildResult(attempt.id, req.user.id));
  } catch (err) {
    next(err);
  }
}

const responsesBody = z.object({ responses: z.record(z.string(), z.any()).default({}) });

export async function autosaveAttempt(req, res, next) {
  try {
    const body = responsesBody.parse(req.body || {});
    const attempt = await ownedAttempt(req.params.attemptId, req.user);
    if (attempt.status !== "in_progress") throw new AppError(409, "ALREADY_SUBMITTED", "This attempt was already submitted.");
    if (deadlinePassed(attempt)) throw new AppError(409, "TIME_UP", "Time is up for this attempt.");
    const ids = parseJson(attempt.question_order_json, []);
    const clean = sanitizeResponses(body.responses, ids);
    await pool.query("UPDATE quiz_attempts SET autosave_json = ? WHERE id = ? AND status = 'in_progress'", [
      JSON.stringify(clean),
      attempt.id,
    ]);
    res.json({ saved: true, saved_at: new Date().toISOString() });
  } catch (err) {
    next(err);
  }
}

export async function submitAttempt(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const body = responsesBody.parse(req.body || {});
    requireUuid(req.params.attemptId, "attempt id");
    await conn.beginTransaction();
    const [rows] = await conn.query("SELECT * FROM quiz_attempts WHERE id = ? FOR UPDATE", [req.params.attemptId]);
    const attempt = rows[0];
    if (!attempt || attempt.user_id !== req.user.id) throw new AppError(404, "NOT_FOUND", "Attempt not found.");
    if (attempt.status !== "in_progress") {
      throw new AppError(409, "ALREADY_SUBMITTED", "This attempt was already submitted.");
    }
    const quiz = await getQuiz(attempt.quiz_id, conn);
    const late = deadlinePassed(attempt);
    // After the deadline (plus a short grace) only the last server autosave counts.
    const responses = late ? parseJson(attempt.autosave_json, {}) : body.responses;
    const result = await finalizeAttempt(conn, attempt, quiz, responses, { late });
    await conn.commit();
    await recordUserEvent(req.user.id, "QUIZ_SUBMITTED", {
      quiz_id: quiz.id,
      attempt_id: attempt.id,
      activity_type: quiz.activity_type,
      percent: result.percent,
      late,
    });
    res.json({ late, ...(await buildResult(attempt.id, req.user.id)) });
  } catch (err) {
    try {
      await conn.rollback();
    } catch {
      /* ignore */
    }
    next(err);
  } finally {
    conn.release();
  }
}

// Topic-wise performance for the signed-in student, with revision suggestions.
export async function studentTopicStats(userId) {
  const [rows] = await pool.query(
    `SELECT q.topic, COUNT(*) AS answered, SUM(a.points) AS points, SUM(a.max_points) AS max_points,
            GROUP_CONCAT(DISTINCT q.textbook_page ORDER BY q.textbook_page) AS pages
     FROM quiz_answers a
     JOIN quiz_attempts t ON t.id = a.attempt_id
     JOIN quiz_questions q ON q.id = a.question_id
     WHERE t.user_id = ? AND t.status = 'submitted'
     GROUP BY q.topic ORDER BY q.topic`,
    [userId]
  );
  return rows.map((r) => {
    const accuracy = Number(r.max_points) > 0 ? Math.round((Number(r.points) / Number(r.max_points)) * 1000) / 10 : 0;
    return {
      topic: r.topic,
      answered: Number(r.answered),
      accuracy,
      textbook_pages: String(r.pages || "").split(",").filter(Boolean).map(Number),
    };
  });
}

export async function myQuizHistory(req, res, next) {
  try {
    const [attempts] = await pool.query(
      `SELECT t.id, t.quiz_id, t.attempt_no, t.status, t.started_at, t.submitted_at, t.percent, t.duration_sec,
              z.title, z.topic, z.activity_type, z.mode
       FROM quiz_attempts t JOIN quizzes z ON z.id = t.quiz_id
       WHERE t.user_id = ? ORDER BY t.started_at DESC LIMIT 200`,
      [req.user.id]
    );
    const topics = await studentTopicStats(req.user.id);
    const suggestions = topics
      .filter((t) => t.accuracy < 70)
      .sort((a, b) => a.accuracy - b.accuracy)
      .map((t) => ({
        topic: t.topic,
        accuracy: t.accuracy,
        suggestion: `Revise "${t.topic}"${t.textbook_pages.length ? ` (textbook page ${t.textbook_pages.join(", ")})` : ""}, then try a Revision Challenge.`,
      }));
    res.json({
      attempts: attempts.map((a) => ({ ...a, percent: a.percent == null ? null : Number(a.percent) })),
      topics,
      suggestions,
    });
  } catch (err) {
    next(err);
  }
}

async function createPersonalQuiz(user, { title, description, topic, activityType, questionIds, timeLimit = null }) {
  const conn = await pool.getConnection();
  try {
    await conn.beginTransaction();
    const id = newId();
    await conn.query(
      `INSERT INTO quizzes (id, title, description, topic, difficulty, mode, activity_type, time_limit_sec, max_attempts,
         reveal_answers, status, owner_user_id, created_by, published_at)
       VALUES (?,?,?,?, 'mixed', 'practice', ?, ?, NULL, 'after_submit', 'published', ?, NULL, UTC_TIMESTAMP(3))`,
      [id, title, description, topic.slice(0, 120), activityType, timeLimit, user.id]
    );
    let position = 1;
    for (const qid of questionIds) {
      await conn.query("INSERT INTO quiz_items (quiz_id, question_id, position) VALUES (?,?,?)", [id, qid, position]);
      position += 1;
    }
    await conn.commit();
    await recordUserEvent(user.id, "ACTIVITY_CREATED", { quiz_id: id, activity_type: activityType, questions: questionIds.length });
    return id;
  } catch (err) {
    await conn.rollback();
    throw err;
  } finally {
    conn.release();
  }
}

// Revision Challenge: published questions from the student's own weakest topics,
// preferring the exact questions they missed.
export async function createRevisionChallenge(req, res, next) {
  try {
    const topics = (await studentTopicStats(req.user.id)).filter((t) => t.accuracy < 100);
    if (!topics.length) {
      throw new AppError(409, "NO_DATA", "Finish a quiz first. The Revision Challenge uses the topics you missed.");
    }
    topics.sort((a, b) => a.accuracy - b.accuracy);
    const weak = topics.slice(0, 3).map((t) => t.topic);
    const [missed] = await pool.query(
      `SELECT DISTINCT q.id FROM quiz_answers a JOIN quiz_attempts t ON t.id = a.attempt_id
       JOIN quiz_questions q ON q.id = a.question_id
       WHERE t.user_id = ? AND a.points < a.max_points AND q.status = 'published' AND q.topic IN (?)`,
      [req.user.id, weak]
    );
    const [others] = await pool.query(
      "SELECT id FROM quiz_questions WHERE status = 'published' AND topic IN (?) ORDER BY RAND() LIMIT 12",
      [weak]
    );
    const ids = [...new Set([...missed.map((r) => r.id), ...others.map((r) => r.id)])].slice(0, 8);
    if (!ids.length) throw new AppError(409, "NO_DATA", "There are no published questions for your missed topics yet.");
    const id = await createPersonalQuiz(req.user, {
      title: "Revision Challenge",
      description: `Questions from topics you missed: ${weak.join(", ")}.`,
      topic: weak.join(", "),
      activityType: "revision",
      questionIds: ids,
    });
    res.status(201).json({ quiz_id: id, topics: weak, question_count: ids.length });
  } catch (err) {
    next(err);
  }
}

const checkpointBody = z.object({ topic: z.string().trim().min(2).max(160) });

// Module checkpoint: up to 6 published questions about the module's topic.
export async function createCheckpoint(req, res, next) {
  try {
    const { topic } = checkpointBody.parse(req.body || {});
    const words = topic
      .toLowerCase()
      .replace(/[^a-z\s]/g, " ")
      .split(/\s+/)
      .filter((w) => w.length >= 4 && !["what", "were", "about", "explain", "system", "their", "with", "from", "under"].includes(w))
      .slice(0, 5);
    if (!words.length) throw new AppError(404, "NO_QUESTIONS", "No checkpoint questions for this topic yet.");
    const clauses = words.map(() => "(LOWER(topic) LIKE ? OR LOWER(prompt) LIKE ?)").join(" OR ");
    const params = words.flatMap((w) => [`%${w}%`, `%${w}%`]);
    const [rows] = await pool.query(
      `SELECT id FROM quiz_questions WHERE status = 'published' AND (${clauses}) ORDER BY RAND() LIMIT 6`,
      params
    );
    if (rows.length < 3) throw new AppError(404, "NO_QUESTIONS", "No checkpoint questions for this topic yet.");
    const id = await createPersonalQuiz(req.user, {
      title: `Checkpoint: ${topic.slice(0, 80)}`,
      description: "A short check after your learning module.",
      topic,
      activityType: "checkpoint",
      questionIds: rows.map((r) => r.id),
    });
    res.status(201).json({ quiz_id: id, question_count: rows.length });
  } catch (err) {
    next(err);
  }
}

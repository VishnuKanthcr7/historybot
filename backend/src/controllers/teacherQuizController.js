import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { newId } from "../utils/ids.js";
import { mean, median } from "../services/quizScoring.js";
import { ACTIVITY_TYPES, getQuiz, getQuizItems, parseJson, publicQuiz, requireUuid } from "../services/quizData.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../");
const DOC = "KTBS Class 9 Social Science Part 2 (English) 2026-27, Chapter 17";
let passageCache = null;

function passages() {
  if (!passageCache) {
    passageCache = JSON.parse(fs.readFileSync(path.join(ROOT, "data/quiz/textbook_passages.json"), "utf8"));
  }
  return passageCache;
}

// Checks that a question is structurally gradable. Returns "" when valid.
export function questionProblem(q) {
  const opts = q.options;
  const ans = q.answer;
  switch (q.qtype) {
    case "mcq": {
      if (!Array.isArray(opts) || opts.length < 2 || opts.length > 6) return "MCQ needs 2 to 6 options.";
      const ids = opts.map((o) => o?.id);
      if (new Set(ids).size !== ids.length || opts.some((o) => !o?.id || !String(o.text || "").trim())) {
        return "Each option needs a unique id and text.";
      }
      if (!ids.includes(ans)) return "The answer must be one of the option ids.";
      return "";
    }
    case "true_false":
      return typeof ans === "boolean" ? "" : "The answer must be true or false.";
    case "fill_blank":
      if (!/_{3,}/.test(q.prompt || "")) return "Put ______ where the blank goes.";
      return Array.isArray(ans) && ans.length && ans.every((a) => String(a).trim()) ? "" : "Give at least one accepted answer.";
    case "order":
      if (!Array.isArray(opts) || opts.length < 2) return "Order questions need at least 2 items.";
      if (!Array.isArray(ans) || ans.length !== opts.length) return "The answer must list every item once.";
      if (new Set(ans).size !== ans.length || !ans.every((id) => opts.some((o) => o.id === id))) return "Answer ids must match the items.";
      return "";
    case "match": {
      const left = opts?.left;
      const right = opts?.right;
      if (!Array.isArray(left) || !Array.isArray(right) || left.length < 2 || left.length !== right.length) {
        return "Match questions need equal left and right lists (2 or more).";
      }
      if (!ans || typeof ans !== "object") return "Give the correct pairs.";
      const rights = Object.values(ans);
      if (Object.keys(ans).length !== left.length || new Set(rights).size !== rights.length) return "Each item must be paired once.";
      if (!left.every((l) => right.some((r) => r.id === ans[l.id]))) return "Pairs must use the listed ids.";
      return "";
    }
    default:
      return "Unsupported question type.";
  }
}

const questionBody = z.object({
  qtype: z.enum(["mcq", "true_false", "match", "order", "fill_blank"]),
  prompt: z.string().trim().min(5).max(1000),
  options: z.any().optional(),
  answer: z.any(),
  explanation: z.string().max(2000).optional().default(""),
  topic: z.string().trim().min(2).max(120),
  difficulty: z.enum(["easy", "medium", "hard"]).default("medium"),
  textbook_page: z.number().int().min(1).max(500).nullable().optional(),
  source_chunk_id: z.string().max(128).nullable().optional(),
  source_excerpt: z.string().max(1000).nullable().optional(),
});

function questionOut(row) {
  return {
    id: row.id,
    qtype: row.qtype,
    prompt: row.prompt,
    options: parseJson(row.options_json),
    answer: parseJson(row.answer_json),
    explanation: row.explanation,
    topic: row.topic,
    difficulty: row.difficulty,
    source_document: row.source_document,
    textbook_page: row.textbook_page,
    source_chunk_id: row.source_chunk_id,
    source_excerpt: row.source_excerpt,
    status: row.status,
    origin: row.origin,
    reviewed_at: row.reviewed_at,
    review_note: row.review_note,
    created_at: row.created_at,
    updated_at: row.updated_at,
    mine: undefined,
  };
}

const listQ = z.object({
  status: z.enum(["draft", "needs_review", "published", "archived"]).optional(),
  topic: z.string().max(120).optional(),
  q: z.string().max(100).optional(),
  page: z.coerce.number().int().min(1).default(1),
  size: z.coerce.number().int().min(1).max(100).default(25),
});

export async function listQuestions(req, res, next) {
  try {
    const f = listQ.parse(req.query);
    const where = ["1=1"];
    const params = [];
    if (f.status) {
      where.push("status = ?");
      params.push(f.status);
    }
    if (f.topic) {
      where.push("topic = ?");
      params.push(f.topic);
    }
    if (f.q) {
      where.push("(prompt LIKE ? OR topic LIKE ?)");
      params.push(`%${f.q}%`, `%${f.q}%`);
    }
    const [[{ n }]] = await pool.query(`SELECT COUNT(*) AS n FROM quiz_questions WHERE ${where.join(" AND ")}`, params);
    const [rows] = await pool.query(
      `SELECT * FROM quiz_questions WHERE ${where.join(" AND ")} ORDER BY topic, created_at LIMIT ? OFFSET ?`,
      [...params, f.size, (f.page - 1) * f.size]
    );
    const [topics] = await pool.query("SELECT DISTINCT topic FROM quiz_questions ORDER BY topic");
    res.json({ total: Number(n), page: f.page, size: f.size, questions: rows.map(questionOut), topics: topics.map((t) => t.topic) });
  } catch (err) {
    next(err);
  }
}

async function getQuestion(id) {
  requireUuid(id, "question id");
  const [rows] = await pool.query("SELECT * FROM quiz_questions WHERE id = ?", [id]);
  if (!rows.length) throw new AppError(404, "NOT_FOUND", "Question not found.");
  return rows[0];
}

export async function createQuestion(req, res, next) {
  try {
    const b = questionBody.parse(req.body || {});
    const problem = questionProblem(b);
    if (problem) throw new AppError(400, "VALIDATION_ERROR", problem);
    const id = newId();
    await pool.query(
      `INSERT INTO quiz_questions (id, qtype, prompt, options_json, answer_json, explanation, topic, difficulty,
         source_document, textbook_page, source_chunk_id, source_excerpt, status, origin, created_by)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'draft', 'teacher', ?)`,
      [
        id, b.qtype, b.prompt, b.options == null ? null : JSON.stringify(b.options), JSON.stringify(b.answer), b.explanation,
        b.topic, b.difficulty, b.source_chunk_id ? DOC : null, b.textbook_page ?? null, b.source_chunk_id ?? null,
        b.source_excerpt ?? null, req.user.id,
      ]
    );
    res.status(201).json({ question: questionOut(await getQuestion(id)) });
  } catch (err) {
    next(err);
  }
}

export async function updateQuestion(req, res, next) {
  try {
    const current = await getQuestion(req.params.questionId);
    if (current.status !== "draft" && current.status !== "needs_review") {
      throw new AppError(409, "NOT_DRAFT", "Only draft questions can be edited. Archive it and create a new one.");
    }
    const b = questionBody.parse(req.body || {});
    const problem = questionProblem(b);
    if (problem) throw new AppError(400, "VALIDATION_ERROR", problem);
    await pool.query(
      `UPDATE quiz_questions SET qtype=?, prompt=?, options_json=?, answer_json=?, explanation=?, topic=?, difficulty=?,
         textbook_page=?, source_excerpt=COALESCE(?, source_excerpt), updated_at=UTC_TIMESTAMP(3)
       WHERE id=? AND status IN ('draft', 'needs_review')`,
      [
        b.qtype, b.prompt, b.options == null ? null : JSON.stringify(b.options), JSON.stringify(b.answer), b.explanation, b.topic,
        b.difficulty, b.textbook_page ?? current.textbook_page, b.source_excerpt ?? null, current.id,
      ]
    );
    res.json({ question: questionOut(await getQuestion(current.id)) });
  } catch (err) {
    next(err);
  }
}

const statusBody = z.object({
  status: z.enum(["draft", "needs_review", "published", "archived"]),
  review_note: z.string().max(500).optional(),
});

export async function setQuestionStatus(req, res, next) {
  try {
    const q = await getQuestion(req.params.questionId);
    const { status, review_note } = statusBody.parse(req.body || {});
    if (status === "published") {
      const problem = questionProblem({
        qtype: q.qtype,
        prompt: q.prompt,
        options: parseJson(q.options_json),
        answer: parseJson(q.answer_json),
      });
      if (problem) throw new AppError(400, "VALIDATION_ERROR", problem);
    }
    if ((status === "draft" || status === "needs_review") && q.status === "published") {
      const [[{ n }]] = await pool.query("SELECT COUNT(*) AS n FROM quiz_answers WHERE question_id = ?", [q.id]);
      if (Number(n) > 0) throw new AppError(409, "IN_USE", "This question already has student answers. Archive it instead.");
    }
    await pool.query(
      `UPDATE quiz_questions SET status=?, reviewed_by=?, reviewed_at=UTC_TIMESTAMP(3), review_note=COALESCE(?, review_note),
         updated_at=UTC_TIMESTAMP(3) WHERE id=?`,
      [status, req.user.id, review_note ?? null, q.id]
    );
    res.json({ question: questionOut(await getQuestion(q.id)) });
  } catch (err) {
    next(err);
  }
}

const passageQ = z.object({ q: z.string().max(100).optional(), page: z.coerce.number().int().min(1).max(500).optional() });

export async function searchPassages(req, res, next) {
  try {
    const f = passageQ.parse(req.query);
    const needle = (f.q || "").toLowerCase().trim();
    const rows = passages()
      .filter((p) => (!f.page || p.page === f.page) && (!needle || p.text.toLowerCase().includes(needle)))
      .slice(0, 20)
      .map((p) => ({ chunk_id: p.chunk_id, page: p.page, text: p.text, sentences: splitSentences(p.text) }));
    res.json({ source_document: DOC, passages: rows });
  } catch (err) {
    next(err);
  }
}

export function splitSentences(text) {
  const seen = new Set();
  return String(text || "")
    .split(/(?<=[.!?])\s+(?=[A-Z‘“"])/)
    .map((s) => s.trim())
    .filter((s) => s.length >= 25 && s.length <= 300 && /[.!?]$/.test(s))
    .filter((s) => (seen.has(s) ? false : (seen.add(s), true)));
}

// Deterministic draft from one textbook sentence. The teacher must review it before publishing.
export function draftFromSentence(sentence, qtype) {
  const s = String(sentence || "").trim();
  if (qtype === "true_false") {
    return { qtype, prompt: s, answer: true, explanation: `Textbook: "${s}"` };
  }
  const year = s.match(/\b(1[0-9]{3})\b/);
  let term = year ? year[1] : null;
  if (!term) {
    const names = [...s.matchAll(/(?<!^)\b([A-Z][a-z’'-]+(?:[ -](?:[A-Z][a-z’'-]+|e|i|ul))*)/g)]
      .map((m) => m[1])
      .filter((w) => w.length >= 4 && !["The", "This", "There", "These", "They", "When", "After", "Since"].includes(w));
    term = names.length ? names[names.length - 1] : null;
  }
  if (!term) return null;
  const prompt = s.replace(term, "______");
  if (prompt === s) return null;
  return { qtype: "fill_blank", prompt, answer: [term], explanation: `Textbook: "${s}"` };
}

const draftBody = z.object({
  chunk_id: z.string().max(128),
  sentence: z.string().trim().min(10).max(400),
  qtype: z.enum(["fill_blank", "true_false"]),
  topic: z.string().trim().min(2).max(120),
});

export async function draftFromPassage(req, res, next) {
  try {
    const b = draftBody.parse(req.body || {});
    const passage = passages().find((p) => p.chunk_id === b.chunk_id);
    if (!passage) throw new AppError(404, "NOT_FOUND", "Passage not found.");
    const norm = (t) => t.replace(/\s+/g, " ").trim();
    if (!norm(passage.text).includes(norm(b.sentence))) {
      throw new AppError(400, "VALIDATION_ERROR", "The sentence must come from the selected passage.");
    }
    const draft = draftFromSentence(b.sentence, b.qtype);
    if (!draft) throw new AppError(422, "NO_DRAFT", "No clear key term in this sentence. Write the question by hand.");
    const id = newId();
    await pool.query(
      `INSERT INTO quiz_questions (id, qtype, prompt, options_json, answer_json, explanation, topic, difficulty,
         source_document, textbook_page, source_chunk_id, source_excerpt, status, origin, created_by, review_note)
       VALUES (?,?,?,NULL,?,?,?, 'medium', ?,?,?,?, 'draft', 'extracted', ?, 'Drafted from a textbook sentence; check before publishing.')`,
      [id, draft.qtype, draft.prompt, JSON.stringify(draft.answer), draft.explanation, b.topic, DOC, passage.page, passage.chunk_id, b.sentence, req.user.id]
    );
    res.status(201).json({ question: questionOut(await getQuestion(id)) });
  } catch (err) {
    next(err);
  }
}

// ---------- Quizzes ----------
const quizBody = z.object({
  title: z.string().trim().min(3).max(160),
  description: z.string().max(500).optional().default(""),
  topic: z.string().trim().min(2).max(120),
  difficulty: z.enum(["easy", "medium", "hard", "mixed"]).default("mixed"),
  mode: z.enum(["practice", "assessment"]).default("practice"),
  activity_type: z.enum(ACTIVITY_TYPES.filter((t) => t !== "revision" && t !== "checkpoint")).default("quiz"),
  assessment_phase: z.enum(["none", "pre", "post"]).default("none"),
  time_limit_sec: z.number().int().min(30).max(7200).nullable().optional(),
  max_attempts: z.number().int().min(1).max(50).nullable().optional(),
  reveal_answers: z.enum(["after_submit", "after_close", "never"]).default("after_submit"),
  available_from: z.string().datetime({ offset: true }).nullable().optional(),
  available_until: z.string().datetime({ offset: true }).nullable().optional(),
  question_ids: z.array(z.string().uuid()).max(60).default([]),
  // A post-test is compared only with the pre-test the teacher links here (matched students).
  pre_quiz_id: z.string().uuid().nullable().optional(),
}).refine((b) => !(b.available_from && b.available_until) || new Date(b.available_until) > new Date(b.available_from), {
  message: "The closing time must be after the opening time.",
});

async function checkPreQuiz(b, selfId = null) {
  if (b.assessment_phase !== "post" || !b.pre_quiz_id) return null;
  if (b.pre_quiz_id === selfId) throw new AppError(400, "VALIDATION_ERROR", "A quiz cannot be its own pre-test.");
  let pre;
  try {
    pre = await getQuiz(b.pre_quiz_id);
  } catch {
    throw new AppError(400, "VALIDATION_ERROR", "The linked pre-test does not exist.");
  }
  if (pre.owner_user_id || pre.assessment_phase !== "pre") {
    throw new AppError(400, "VALIDATION_ERROR", "The linked quiz must be a teacher quiz marked as a pre-test.");
  }
  // One post-test per pre-test, so every matched comparison is unambiguous.
  const [dupe] = await pool.query("SELECT id FROM quizzes WHERE pre_quiz_id = ? AND id <> ? LIMIT 1", [pre.id, selfId || ""]);
  if (dupe.length) throw new AppError(409, "PRE_TEST_ALREADY_LINKED", "That pre-test is already linked to another post-test.");
  return pre.id;
}

async function teacherQuizSummary(where = "z.owner_user_id IS NULL", params = []) {
  const [rows] = await pool.query(
    `SELECT z.*, u.display_name AS created_by_name,
       (SELECT COUNT(*) FROM quiz_items i WHERE i.quiz_id = z.id) AS question_count,
       (SELECT COUNT(*) FROM quiz_attempts a WHERE a.quiz_id = z.id AND a.status = 'submitted') AS submitted_attempts,
       (SELECT COUNT(DISTINCT a.user_id) FROM quiz_attempts a WHERE a.quiz_id = z.id AND a.status = 'submitted') AS students,
       (SELECT AVG(a.percent) FROM quiz_attempts a WHERE a.quiz_id = z.id AND a.status = 'submitted') AS mean_percent
     FROM quizzes z LEFT JOIN users u ON u.id = z.created_by WHERE ${where} ORDER BY z.created_at DESC`,
    params
  );
  return rows.map((r) => ({
    ...publicQuiz(r),
    created_by_name: r.created_by_name,
    mine: undefined,
    created_by: r.created_by,
    question_count: Number(r.question_count),
    submitted_attempts: Number(r.submitted_attempts),
    students: Number(r.students),
    mean_percent: r.mean_percent == null ? null : Math.round(Number(r.mean_percent) * 10) / 10,
  }));
}

export async function listTeacherQuizzes(req, res, next) {
  try {
    const quizzes = (await teacherQuizSummary()).map((q) => ({ ...q, mine: q.created_by === req.user.id }));
    res.json({ quizzes });
  } catch (err) {
    next(err);
  }
}

async function setItems(conn, quizId, questionIds) {
  if (questionIds.length) {
    const [found] = await conn.query("SELECT id, status FROM quiz_questions WHERE id IN (?)", [questionIds]);
    if (found.length !== new Set(questionIds).size) throw new AppError(400, "VALIDATION_ERROR", "Unknown question id.");
    if (found.some((q) => q.status === "archived")) throw new AppError(400, "VALIDATION_ERROR", "Archived questions cannot be added.");
  }
  await conn.query("DELETE FROM quiz_items WHERE quiz_id = ?", [quizId]);
  let position = 1;
  for (const qid of [...new Set(questionIds)]) {
    await conn.query("INSERT INTO quiz_items (quiz_id, question_id, position) VALUES (?,?,?)", [quizId, qid, position]);
    position += 1;
  }
}

function dt(value) {
  return value ? new Date(value) : null;
}

export async function createTeacherQuiz(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const b = quizBody.parse(req.body || {});
    const preId = await checkPreQuiz(b);
    await conn.beginTransaction();
    const id = newId();
    await conn.query(
      `INSERT INTO quizzes (id, title, description, topic, difficulty, mode, activity_type, assessment_phase, time_limit_sec,
         max_attempts, reveal_answers, available_from, available_until, status, created_by, pre_quiz_id)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'draft', ?, ?)`,
      [
        id, b.title, b.description, b.topic, b.difficulty, b.mode, b.activity_type, b.assessment_phase, b.time_limit_sec ?? null,
        b.max_attempts ?? null, b.reveal_answers, dt(b.available_from), dt(b.available_until), req.user.id, preId,
      ]
    );
    await setItems(conn, id, b.question_ids);
    await conn.commit();
    res.status(201).json({ quiz: publicQuiz(await getQuiz(id)) });
  } catch (err) {
    await conn.rollback();
    next(err);
  } finally {
    conn.release();
  }
}

async function ownTeacherQuiz(id, user) {
  const quiz = await getQuiz(id);
  if (quiz.owner_user_id) throw new AppError(404, "NOT_FOUND", "Quiz not found.");
  if (quiz.created_by && quiz.created_by !== user.id) {
    throw new AppError(403, "FORBIDDEN", "Only the teacher who created this quiz can change it.");
  }
  return quiz;
}

export async function updateTeacherQuiz(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const quiz = await ownTeacherQuiz(req.params.quizId, req.user);
    const b = quizBody.parse(req.body || {});
    const preId = await checkPreQuiz(b, quiz.id);
    const [[{ n }]] = await conn.query("SELECT COUNT(*) AS n FROM quiz_attempts WHERE quiz_id = ?", [quiz.id]);
    const items = await getQuizItems(quiz.id, conn);
    const sameItems = items.map((i) => i.id).join(",") === [...new Set(b.question_ids)].join(",");
    if (Number(n) > 0 && !sameItems) {
      throw new AppError(409, "HAS_ATTEMPTS", "Students have already taken this quiz, so its questions cannot change.");
    }
    await conn.beginTransaction();
    await conn.query(
      `UPDATE quizzes SET title=?, description=?, topic=?, difficulty=?, mode=?, activity_type=?, assessment_phase=?,
         time_limit_sec=?, max_attempts=?, reveal_answers=?, available_from=?, available_until=?, pre_quiz_id=?, updated_at=UTC_TIMESTAMP(3)
       WHERE id=?`,
      [
        b.title, b.description, b.topic, b.difficulty, b.mode, b.activity_type, b.assessment_phase, b.time_limit_sec ?? null,
        b.max_attempts ?? null, b.reveal_answers, dt(b.available_from), dt(b.available_until), preId, quiz.id,
      ]
    );
    if (!sameItems) await setItems(conn, quiz.id, b.question_ids);
    await conn.commit();
    res.json({ quiz: publicQuiz(await getQuiz(quiz.id)) });
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

const quizStatusBody = z.object({ status: z.enum(["draft", "published", "archived"]) });

export async function setQuizStatus(req, res, next) {
  try {
    const quiz = await ownTeacherQuiz(req.params.quizId, req.user);
    const { status } = quizStatusBody.parse(req.body || {});
    if (status === "published") {
      const items = await getQuizItems(quiz.id);
      if (!items.length) throw new AppError(400, "VALIDATION_ERROR", "Add at least one question before publishing.");
      if (items.some((q) => q.status !== "published")) {
        throw new AppError(400, "VALIDATION_ERROR", "Publish (review) every question in the quiz first.");
      }
      if (quiz.assessment_phase === "post" && !quiz.pre_quiz_id) {
        throw new AppError(400, "VALIDATION_ERROR", "Link this post-test to its pre-test before publishing.");
      }
      if (quiz.assessment_phase === "post") {
        const pre = await getQuiz(quiz.pre_quiz_id);
        if (pre.status === "draft") throw new AppError(400, "VALIDATION_ERROR", "Publish the linked pre-test before publishing this post-test.");
      }
    }
    await pool.query(
      `UPDATE quizzes SET status=?, published_at=IF(? = 'published', COALESCE(published_at, UTC_TIMESTAMP(3)), published_at),
         updated_at=UTC_TIMESTAMP(3) WHERE id=?`,
      [status, status, quiz.id]
    );
    res.json({ quiz: publicQuiz(await getQuiz(quiz.id)) });
  } catch (err) {
    next(err);
  }
}

export async function previewTeacherQuiz(req, res, next) {
  try {
    const quiz = await getQuiz(req.params.quizId);
    if (quiz.owner_user_id) throw new AppError(404, "NOT_FOUND", "Quiz not found.");
    const items = await getQuizItems(quiz.id);
    res.json({
      quiz: { ...publicQuiz(quiz), created_by: quiz.created_by, mine: quiz.created_by === req.user.id },
      questions: items.map(questionOut),
    });
  } catch (err) {
    next(err);
  }
}

export async function quizResults(req, res, next) {
  try {
    const quiz = await getQuiz(req.params.quizId);
    if (quiz.owner_user_id) throw new AppError(404, "NOT_FOUND", "Quiz not found.");
    const [attempts] = await pool.query(
      `SELECT a.id, a.user_id, u.display_name, a.attempt_no, a.percent, a.score_points, a.max_points, a.duration_sec, a.submitted_at
       FROM quiz_attempts a JOIN users u ON u.id = a.user_id
       WHERE a.quiz_id = ? AND a.status = 'submitted' ORDER BY a.submitted_at DESC`,
      [quiz.id]
    );
    const percents = attempts.map((a) => Number(a.percent));
    const bins = [0, 0, 0, 0, 0];
    for (const p of percents) bins[Math.min(4, Math.floor(p / 20))] += 1;
    const [perQuestion] = await pool.query(
      `SELECT q.id, q.prompt, q.topic, COUNT(*) AS answered, SUM(qa.is_correct) AS correct, SUM(qa.points) AS points,
              SUM(qa.max_points) AS max_points
       FROM quiz_answers qa JOIN quiz_attempts a ON a.id = qa.attempt_id JOIN quiz_questions q ON q.id = qa.question_id
       WHERE a.quiz_id = ? AND a.status = 'submitted' GROUP BY q.id, q.prompt, q.topic`,
      [quiz.id]
    );
    res.json({
      quiz: publicQuiz(quiz),
      aggregate: {
        attempts: attempts.length,
        students: new Set(attempts.map((a) => a.user_id)).size,
        mean_percent: percents.length ? Math.round(mean(percents) * 10) / 10 : null,
        median_percent: percents.length ? Math.round(median(percents) * 10) / 10 : null,
        distribution: ["0-19", "20-39", "40-59", "60-79", "80-100"].map((label, i) => ({ label, count: bins[i] })),
      },
      questions: perQuestion.map((q) => ({
        id: q.id,
        prompt: q.prompt,
        topic: q.topic,
        answered: Number(q.answered),
        percent_correct: Number(q.max_points) > 0 ? Math.round((Number(q.points) / Number(q.max_points)) * 1000) / 10 : null,
      })),
      individual: attempts.map((a) => ({
        attempt_id: a.id,
        student_id: a.user_id,
        student: a.display_name,
        attempt_no: a.attempt_no,
        percent: Number(a.percent),
        score: Number(a.score_points),
        max_score: Number(a.max_points),
        duration_sec: a.duration_sec,
        submitted_at: a.submitted_at,
      })),
    });
  } catch (err) {
    next(err);
  }
}

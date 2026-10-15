import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { mean, median } from "../services/quizScoring.js";
import { toCsv } from "../services/csv.js";
import { requireUuid } from "../services/quizData.js";
import { studentTopicStats } from "./quizController.js";

// Dates are school days in India (IST, UTC+05:30); the database stores UTC.
const IST = "+05:30";
const DAY_MS = 24 * 60 * 60 * 1000;

const rangeQ = z.object({
  from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
});

function istDate(d) {
  return new Date(d.getTime() + 330 * 60 * 1000).toISOString().slice(0, 10);
}

export function parseRange(query) {
  const r = rangeQ.parse({ from: query.from, to: query.to });
  const today = istDate(new Date());
  const to = r.to || today;
  const from = r.from || istDate(new Date(new Date(`${to}T00:00:00${IST}`).getTime() - 29 * DAY_MS));
  const start = new Date(`${from}T00:00:00${IST}`);
  const end = new Date(new Date(`${to}T00:00:00${IST}`).getTime() + DAY_MS);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start >= end) {
    throw new AppError(400, "VALIDATION_ERROR", "Invalid date range.");
  }
  if (end - start > 400 * DAY_MS) throw new AppError(400, "VALIDATION_ERROR", "Date range is too long (max 400 days).");
  return { from, to, start, end };
}

async function quizTrackingBegan() {
  try {
    const [rows] = await pool.query("SELECT applied_at FROM schema_migrations WHERE id = '005_quizzes_analytics'");
    return rows[0]?.applied_at || null;
  } catch {
    return null;
  }
}

const round1 = (x) => (x == null || Number.isNaN(x) ? null : Math.round(x * 10) / 10);

export const DEFINITIONS = {
  students_total: "Student accounts that exist (role student), regardless of activity.",
  active_students: "Students with at least one chat question or one submitted quiz/activity in the date range. Not attendance.",
  chat_questions: "Questions students typed in chat in the date range (count only; chat text is never shown here).",
  modules_generated: "Learning modules (e-content) students generated in the date range.",
  quiz_attempts: "Quiz and activity attempts submitted in the date range.",
  mean_percent: "Average score of submitted attempts in the date range (all attempts, equal weight).",
  sign_ins: "Not available: past sign-ins are not stored. Sign-ins would not measure attendance anyway.",
};

export async function overview(req, res, next) {
  try {
    const range = parseRange(req.query);
    const began = await quizTrackingBegan();
    const [[students]] = await pool.query("SELECT COUNT(*) AS n FROM users WHERE role = 'student'");
    const [[chat]] = await pool.query(
      `SELECT COUNT(*) AS n, COUNT(DISTINCT s.user_id) AS users FROM messages m
       JOIN conversations c ON c.id = m.conversation_id JOIN anonymous_sessions s ON s.id = c.session_id
       JOIN users u ON u.id = s.user_id AND u.role = 'student'
       WHERE m.role = 'user' AND m.created_at >= ? AND m.created_at < ?`,
      [range.start, range.end]
    );
    const [[modules]] = await pool.query(
      `SELECT COUNT(*) AS n FROM analytics_events e JOIN anonymous_sessions s ON s.id = e.session_id
       JOIN users u ON u.id = s.user_id AND u.role = 'student'
       WHERE e.event_type = 'E_CONTENT_GENERATED' AND e.created_at >= ? AND e.created_at < ?`,
      [range.start, range.end]
    );
    const [[quiz]] = await pool.query(
      `SELECT COUNT(*) AS n, AVG(a.percent) AS mean_percent, COUNT(DISTINCT a.user_id) AS users
       FROM quiz_attempts a JOIN users u ON u.id = a.user_id AND u.role = 'student'
       WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ?`,
      [range.start, range.end]
    );
    const [[active]] = await pool.query(
      `SELECT COUNT(*) AS n FROM users u WHERE u.role = 'student' AND (
         EXISTS (SELECT 1 FROM quiz_attempts a WHERE a.user_id = u.id AND a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ?)
         OR EXISTS (SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id
                    JOIN anonymous_sessions s ON s.id = c.session_id
                    WHERE s.user_id = u.id AND m.role = 'user' AND m.created_at >= ? AND m.created_at < ?))`,
      [range.start, range.end, range.start, range.end]
    );
    const quizNote =
      began && range.start < new Date(began)
        ? `Quiz tracking began ${istDate(new Date(began))}; earlier days have no quiz data.`
        : null;
    res.json({
      range: { from: range.from, to: range.to, timezone: "IST (UTC+05:30)" },
      tracking: { quiz_tracking_began: began, chat_tracking: "Chat counts come from stored messages since the app started." },
      cards: {
        students_total: Number(students.n),
        active_students: Number(active.n),
        chat_questions: Number(chat.n),
        modules_generated: Number(modules.n),
        quiz_attempts: Number(quiz.n),
        mean_percent: quiz.mean_percent == null ? null : round1(Number(quiz.mean_percent)),
        sign_ins: null,
      },
      notes: { quiz: quizNote, sign_ins: DEFINITIONS.sign_ins },
      definitions: DEFINITIONS,
      not_implemented: [
        "Digital-attitude scale: not implemented (needs a validated instrument from the researcher).",
        "Social-engagement scale: not implemented (needs a validated instrument from the researcher).",
        "Collaboration features: assessed only, not built.",
      ],
    });
  } catch (err) {
    next(err);
  }
}

const SORTS = {
  name: "display_name",
  joined: "joined",
  chat_questions: "chat_questions",
  quiz_attempts: "quiz_attempts",
  mean_percent: "mean_percent",
  last_active: "last_active",
};

const studentsQ = z.object({
  search: z.string().max(80).optional(),
  sort: z.enum(Object.keys(SORTS)).default("name"),
  dir: z.enum(["asc", "desc"]).default("asc"),
  page: z.coerce.number().int().min(1).default(1),
  size: z.coerce.number().int().min(1).max(100).default(20),
  activity: z.enum(["all", "active", "inactive"]).default("all"),
});

async function studentRows(range, f, { paginate = true } = {}) {
  const where = ["u.role = 'student'"];
  const params = [];
  if (f.search) {
    where.push("u.display_name LIKE ?");
    params.push(`%${f.search}%`);
  }
  const base = `
    SELECT u.id, u.display_name, u.created_at AS joined,
      (SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id
         JOIN anonymous_sessions s ON s.id = c.session_id
         WHERE s.user_id = u.id AND m.role = 'user' AND m.created_at >= ? AND m.created_at < ?) AS chat_questions,
      (SELECT COUNT(*) FROM quiz_attempts a WHERE a.user_id = u.id AND a.status = 'submitted'
         AND a.submitted_at >= ? AND a.submitted_at < ?) AS quiz_attempts,
      (SELECT AVG(a.percent) FROM quiz_attempts a WHERE a.user_id = u.id AND a.status = 'submitted'
         AND a.submitted_at >= ? AND a.submitted_at < ?) AS mean_percent,
      GREATEST(
        COALESCE((SELECT MAX(m.created_at) FROM messages m JOIN conversations c ON c.id = m.conversation_id
           JOIN anonymous_sessions s ON s.id = c.session_id WHERE s.user_id = u.id AND m.role = 'user'), '1970-01-01'),
        COALESCE((SELECT MAX(a.submitted_at) FROM quiz_attempts a WHERE a.user_id = u.id), '1970-01-01')) AS last_active
    FROM users u WHERE ${where.join(" AND ")}`;
  const rangeParams = [range.start, range.end, range.start, range.end, range.start, range.end];
  const activityFilter =
    f.activity === "active" ? "WHERE (chat_questions + quiz_attempts) > 0" : f.activity === "inactive" ? "WHERE (chat_questions + quiz_attempts) = 0" : "";
  const [[{ n }]] = await pool.query(`SELECT COUNT(*) AS n FROM (${base}) t ${activityFilter}`, [...rangeParams, ...params]);
  const order = `${SORTS[f.sort]} ${f.dir === "desc" ? "DESC" : "ASC"}, id`;
  const limit = paginate ? `LIMIT ${Number(f.size)} OFFSET ${(Number(f.page) - 1) * Number(f.size)}` : "LIMIT 5000";
  const [rows] = await pool.query(`SELECT * FROM (${base}) t ${activityFilter} ORDER BY ${order} ${limit}`, [
    ...rangeParams,
    ...params,
  ]);
  return {
    total: Number(n),
    rows: rows.map((r) => ({
      id: r.id,
      display_name: r.display_name,
      joined: r.joined,
      chat_questions: Number(r.chat_questions),
      quiz_attempts: Number(r.quiz_attempts),
      mean_percent: r.mean_percent == null ? null : round1(Number(r.mean_percent)),
      last_active: new Date(r.last_active).getUTCFullYear() <= 1970 ? null : r.last_active,
    })),
  };
}

export async function students(req, res, next) {
  try {
    const range = parseRange(req.query);
    const f = studentsQ.parse(req.query);
    const { total, rows } = await studentRows(range, f);
    res.json({ range: { from: range.from, to: range.to }, total, page: f.page, size: f.size, students: rows });
  } catch (err) {
    next(err);
  }
}

export async function studentProfile(req, res, next) {
  try {
    requireUuid(req.params.userId, "student id");
    const [users] = await pool.query("SELECT id, display_name, created_at, role FROM users WHERE id = ?", [req.params.userId]);
    if (!users.length || users[0].role !== "student") throw new AppError(404, "NOT_FOUND", "Student not found.");
    const u = users[0];
    const [attempts] = await pool.query(
      `SELECT a.id, a.attempt_no, a.percent, a.submitted_at, a.duration_sec, z.title, z.topic, z.activity_type, z.mode
       FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id
       WHERE a.user_id = ? AND a.status = 'submitted' ORDER BY a.submitted_at`,
      [u.id]
    );
    const [[chat]] = await pool.query(
      `SELECT COUNT(*) AS n FROM messages m JOIN conversations c ON c.id = m.conversation_id
       JOIN anonymous_sessions s ON s.id = c.session_id WHERE s.user_id = ? AND m.role = 'user'`,
      [u.id]
    );
    const topics = await studentTopicStats(u.id);
    res.json({
      student: { id: u.id, display_name: u.display_name, joined: u.created_at },
      totals: { chat_questions: Number(chat.n), quiz_attempts: attempts.length },
      attempts: attempts.map((a) => ({ ...a, percent: Number(a.percent) })),
      observed_topics: topics,
      suggested_topics: topics
        .filter((t) => t.accuracy < 70)
        .sort((a, b) => a.accuracy - b.accuracy)
        .map((t) => ({ topic: t.topic, accuracy: t.accuracy, textbook_pages: t.textbook_pages })),
      note: "Observed = topics the student answered quiz questions on (accuracy). Suggested = topics below 70% accuracy. Chat text is not shown.",
    });
  } catch (err) {
    next(err);
  }
}

async function topicRows(range) {
  const [rows] = await pool.query(
    `SELECT q.topic, COUNT(*) AS answered, SUM(qa.points) AS points, SUM(qa.max_points) AS max_points,
            COUNT(DISTINCT a.user_id) AS students, COUNT(DISTINCT a.id) AS attempts
     FROM quiz_answers qa JOIN quiz_attempts a ON a.id = qa.attempt_id JOIN quiz_questions q ON q.id = qa.question_id
     JOIN users u ON u.id = a.user_id AND u.role = 'student'
     WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ?
     GROUP BY q.topic ORDER BY q.topic`,
    [range.start, range.end]
  );
  return rows.map((r) => ({
    topic: r.topic,
    answered: Number(r.answered),
    students: Number(r.students),
    attempts: Number(r.attempts),
    accuracy: Number(r.max_points) > 0 ? round1((Number(r.points) / Number(r.max_points)) * 100) : null,
  }));
}

export async function topics(req, res, next) {
  try {
    const range = parseRange(req.query);
    res.json({ range: { from: range.from, to: range.to }, topics: await topicRows(range) });
  } catch (err) {
    next(err);
  }
}

export async function timeseries(req, res, next) {
  try {
    const range = parseRange(req.query);
    const bucket = req.query.bucket === "week" ? "week" : "day";
    const key =
      bucket === "week"
        ? "DATE_FORMAT(DATE_SUB(DATE(CONVERT_TZ(%s, '+00:00', '+05:30')), INTERVAL WEEKDAY(CONVERT_TZ(%s, '+00:00', '+05:30')) DAY), '%%Y-%%m-%%d')"
        : "DATE_FORMAT(DATE(CONVERT_TZ(%s, '+00:00', '+05:30')), '%%Y-%%m-%%d')";
    const k = (col) => key.replaceAll("%s", col).replaceAll("%%", "%");
    const [quiz] = await pool.query(
      `SELECT ${k("a.submitted_at")} AS bucket, COUNT(*) AS n, AVG(a.percent) AS mean_percent, COUNT(DISTINCT a.user_id) AS students
       FROM quiz_attempts a JOIN users u ON u.id = a.user_id AND u.role = 'student'
       WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ? GROUP BY bucket ORDER BY bucket`,
      [range.start, range.end]
    );
    const [chat] = await pool.query(
      `SELECT ${k("m.created_at")} AS bucket, COUNT(*) AS n, COUNT(DISTINCT s.user_id) AS students
       FROM messages m JOIN conversations c ON c.id = m.conversation_id JOIN anonymous_sessions s ON s.id = c.session_id
       JOIN users u ON u.id = s.user_id AND u.role = 'student'
       WHERE m.role = 'user' AND m.created_at >= ? AND m.created_at < ? GROUP BY bucket ORDER BY bucket`,
      [range.start, range.end]
    );
    const map = new Map();
    for (const r of quiz) map.set(r.bucket, { bucket: r.bucket, quiz_attempts: Number(r.n), quiz_students: Number(r.students), mean_percent: round1(Number(r.mean_percent)), chat_questions: 0, chat_students: 0 });
    for (const r of chat) {
      const e = map.get(r.bucket) || { bucket: r.bucket, quiz_attempts: 0, quiz_students: 0, mean_percent: null, chat_questions: 0, chat_students: 0 };
      e.chat_questions = Number(r.n);
      e.chat_students = Number(r.students);
      map.set(r.bucket, e);
    }
    res.json({
      range: { from: range.from, to: range.to },
      bucket,
      note: "n = number of submitted attempts in the period. Means from small n are not reliable.",
      series: [...map.values()].sort((a, b) => (a.bucket < b.bucket ? -1 : 1)),
    });
  } catch (err) {
    next(err);
  }
}

function stats(values) {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return { n: 0, mean: null, median: null, sd: null, min: null, max: null, distribution: [] };
  const m = mean(v);
  const sd = v.length > 1 ? Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / (v.length - 1)) : null;
  const bins = [0, 0, 0, 0, 0];
  for (const x of v) bins[Math.min(4, Math.floor(x / 20))] += 1;
  return {
    n: v.length,
    mean: round1(m),
    median: round1(median(v)),
    sd: round1(sd),
    min: Math.min(...v),
    max: Math.max(...v),
    distribution: ["0-19", "20-39", "40-59", "60-79", "80-100"].map((label, i) => ({ label, count: bins[i] })),
  };
}

export async function achievement(req, res, next) {
  try {
    const range = parseRange(req.query);
    const quizId = req.query.quiz_id ? requireUuid(String(req.query.quiz_id), "quiz id") : null;
    // First submitted attempt per student per quiz, so repeated practice does not inflate the numbers.
    const [rows] = await pool.query(
      `SELECT a.user_id, a.quiz_id, a.percent, z.assessment_phase, z.topic, z.title
       FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN users u ON u.id = a.user_id AND u.role = 'student'
       WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ? AND z.owner_user_id IS NULL
         ${quizId ? "AND a.quiz_id = ?" : ""}
         AND a.attempt_no = (SELECT MIN(b.attempt_no) FROM quiz_attempts b WHERE b.quiz_id = a.quiz_id AND b.user_id = a.user_id AND b.status = 'submitted')`,
      quizId ? [range.start, range.end, quizId] : [range.start, range.end]
    );
    const overall = stats(rows.map((r) => Number(r.percent)));
    const pre = rows.filter((r) => r.assessment_phase === "pre");
    const post = rows.filter((r) => r.assessment_phase === "post");
    let prePost = { available: false, note: "Pre/post comparison appears only when the teacher marks one quiz as a pre-test and another as a post-test." };
    if (pre.length && post.length) {
      const preBy = new Map();
      for (const r of pre) preBy.set(r.user_id, Number(r.percent));
      const pairs = post.filter((r) => preBy.has(r.user_id)).map((r) => ({ pre: preBy.get(r.user_id), post: Number(r.percent) }));
      prePost = {
        available: true,
        pre: stats(pre.map((r) => Number(r.percent))),
        post: stats(post.map((r) => Number(r.percent))),
        paired_n: pairs.length,
        mean_change: pairs.length ? round1(mean(pairs.map((p) => p.post - p.pre))) : null,
        note: "Descriptive only. A change between pre- and post-test does not show what caused it.",
      };
    }
    res.json({
      range: { from: range.from, to: range.to },
      basis: "First submitted attempt per student per quiz (teacher quizzes only).",
      overall,
      pre_post: prePost,
    });
  } catch (err) {
    next(err);
  }
}

// ---------- CSV reports ----------
function studentRef(id) {
  return `S-${String(id).replace(/-/g, "").slice(0, 8)}`;
}

export async function reportCsv(req, res, next) {
  try {
    const range = parseRange(req.query);
    const kind = req.params.kind;
    const withNames = req.query.include_names === "1";
    let header;
    let rows;
    if (kind === "attempts") {
      const [data] = await pool.query(
        `SELECT a.user_id, u.display_name, z.title, z.topic, z.activity_type, z.mode, z.assessment_phase, a.attempt_no,
                a.score_points, a.max_points, a.percent, a.duration_sec, a.submitted_at
         FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN users u ON u.id = a.user_id AND u.role = 'student'
         WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ? ORDER BY a.submitted_at`,
        [range.start, range.end]
      );
      header = ["student_ref", ...(withNames ? ["student_name"] : []), "quiz", "topic", "activity_type", "mode", "phase", "attempt_no", "score", "max_score", "percent", "duration_sec", "submitted_at_utc"];
      rows = data.map((r) => [
        studentRef(r.user_id), ...(withNames ? [r.display_name] : []), r.title, r.topic, r.activity_type, r.mode, r.assessment_phase,
        r.attempt_no, Number(r.score_points), Number(r.max_points), Number(r.percent), r.duration_sec, r.submitted_at,
      ]);
    } else if (kind === "students") {
      const { rows: data } = await studentRows(range, { sort: "name", dir: "asc", page: 1, size: 100, activity: "all" }, { paginate: false });
      header = ["student_ref", ...(withNames ? ["student_name"] : []), "joined_utc", "chat_questions", "quiz_attempts", "mean_percent", "last_active_utc"];
      rows = data.map((r) => [studentRef(r.id), ...(withNames ? [r.display_name] : []), r.joined, r.chat_questions, r.quiz_attempts, r.mean_percent, r.last_active]);
    } else if (kind === "topics") {
      const data = await topicRows(range);
      header = ["topic", "answers", "students", "attempts", "accuracy_percent"];
      rows = data.map((r) => [r.topic, r.answered, r.students, r.attempts, r.accuracy]);
    } else {
      throw new AppError(404, "NOT_FOUND", "Unknown report.");
    }
    const csv = toCsv(header, rows);
    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader("Content-Disposition", `attachment; filename="historybot-${kind}-${range.from}-to-${range.to}.csv"`);
    res.setHeader("Cache-Control", "no-store");
    res.send(`\ufeff${csv}`);
  } catch (err) {
    next(err);
  }
}

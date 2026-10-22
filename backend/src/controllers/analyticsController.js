import { z } from "zod";
import { buildSeries } from "../services/timeseries.js";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { mean, median } from "../services/quizScoring.js";
import { toCsv } from "../services/csv.js";
import { requireUuid } from "../services/quizData.js";
import { studentTopicStats } from "./quizController.js";
import { pairedT } from "../services/stats.js";
import { questionnaireCsv } from "./researchController.js";
import { EXTRA_REPORTS, REPORT_TITLES, renderPdf, requireStudent, researchSummaryRows, studentTimeline } from "../services/reports.js";

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

async function migrationApplied(id) {
  try {
    const [rows] = await pool.query("SELECT applied_at FROM schema_migrations WHERE id = ?", [id]);
    return rows[0]?.applied_at || null;
  } catch {
    return null;
  }
}

const quizTrackingBegan = () => migrationApplied("005_quizzes_analytics");
const progressTrackingBegan = () => migrationApplied("006_progress_research");

function trackingNote(began, range, what) {
  if (!began) return `${what}: data not available (tracking has not started).`;
  return range.start < new Date(began) ? `${what}: tracking began ${istDate(new Date(began))}; earlier days have no data.` : null;
}

// Abandoned = an untimed attempt still in progress more than 24 hours after it started (never submitted).
const ABANDON_HOURS = 24;

const round1 = (x) => (x == null || Number.isNaN(x) ? null : Math.round(x * 10) / 10);

export { DEFINITIONS } from "../services/metricDefinitions.js";
import { DEFINITIONS } from "../services/metricDefinitions.js";

const round2 = (x) => (x == null || Number.isNaN(x) ? null : Math.round(x * 100) / 100);

async function one(sql, params) {
  const [[row]] = await pool.query(sql, params);
  return row;
}

export async function overviewData(range) {
  const quizBegan = await quizTrackingBegan();
  const progressBegan = await progressTrackingBegan();
  const P = [range.start, range.end];
  const students = await one("SELECT COUNT(*) AS n, SUM(created_at >= ? AND created_at < ?) AS new_n FROM users WHERE role = 'student'", P);
  const chat = await one(
    `SELECT COUNT(*) AS n FROM messages m
     JOIN conversations c ON c.id = m.conversation_id JOIN anonymous_sessions s ON s.id = c.session_id
     JOIN users u ON u.id = s.user_id AND u.role = 'student'
     WHERE m.role = 'user' AND m.created_at >= ? AND m.created_at < ?`,
    P
  );
  const generated = await one(
    `SELECT COUNT(*) AS n FROM econtent_documents d JOIN anonymous_sessions s ON s.id = d.session_id
     JOIN users u ON u.id = s.user_id AND u.role = 'student' WHERE d.created_at >= ? AND d.created_at < ?`,
    P
  );
  const progress = await one(
    `SELECT SUM(p.first_opened_at >= ? AND p.first_opened_at < ?) AS opened, SUM(p.completed_at >= ? AND p.completed_at < ?) AS completed
     FROM module_progress p JOIN users u ON u.id = p.user_id AND u.role = 'student'`,
    [...P, ...P]
  );
  const events = await one(
    `SELECT SUM(e.event_type = 'USER_SIGNED_IN') AS sign_ins, SUM(e.event_type = 'PDF_DOWNLOADED') AS pdf
     FROM analytics_events e
     LEFT JOIN anonymous_sessions s ON s.id = e.session_id
     JOIN users u ON u.id = COALESCE(e.user_id, s.user_id) AND u.role = 'student'
     WHERE e.event_type IN ('USER_SIGNED_IN', 'PDF_DOWNLOADED') AND e.created_at >= ? AND e.created_at < ?`,
    P
  );
  const quiz = await one(
    `SELECT COUNT(*) AS n, SUM(a.end_reason = 'timed_out') AS timed_out,
            SUM(z.mode = 'assessment' AND z.owner_user_id IS NULL) AS assessments,
            AVG(IF(z.mode = 'practice' OR z.owner_user_id IS NOT NULL, a.percent, NULL)) AS practice_mean,
            SUM(z.mode = 'practice' OR z.owner_user_id IS NOT NULL) AS practice_n
     FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN users u ON u.id = a.user_id AND u.role = 'student'
     WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ?`,
    P
  );
  const achievementRow = await one(
    `SELECT AVG(a.percent) AS mean, COUNT(*) AS n, SUM(a.end_reason = 'timed_out') AS timed_out FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id
     JOIN users u ON u.id = a.user_id AND u.role = 'student'
     WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ? AND z.mode = 'assessment' AND z.owner_user_id IS NULL
       AND a.attempt_no = (SELECT MIN(b.attempt_no) FROM quiz_attempts b WHERE b.quiz_id = a.quiz_id AND b.user_id = a.user_id AND b.status = 'submitted')`,
    P
  );
  const abandoned = await one(
    `SELECT COUNT(*) AS n FROM quiz_attempts a JOIN users u ON u.id = a.user_id AND u.role = 'student'
     WHERE a.status = 'in_progress' AND a.deadline_at IS NULL AND a.started_at >= ? AND a.started_at < ?
       AND a.started_at < UTC_TIMESTAMP(3) - INTERVAL ${ABANDON_HOURS} HOUR`,
    P
  );
  const active = await one(
    `SELECT COUNT(*) AS n FROM users u WHERE u.role = 'student' AND (
       EXISTS (SELECT 1 FROM quiz_attempts a WHERE a.user_id = u.id AND a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ?)
       OR EXISTS (SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id
                  JOIN anonymous_sessions s ON s.id = c.session_id
                  WHERE s.user_id = u.id AND m.role = 'user' AND m.created_at >= ? AND m.created_at < ?)
       OR EXISTS (SELECT 1 FROM module_progress p WHERE p.user_id = u.id AND p.last_opened_at >= ? AND p.last_opened_at < ?)
       OR EXISTS (SELECT 1 FROM research_responses r WHERE r.user_id = u.id AND r.status = 'submitted' AND r.submitted_at >= ? AND r.submitted_at < ?))`,
    [...P, ...P, ...P, ...P]
  );
  const num = (x) => Number(x || 0);
  return {
    range: { from: range.from, to: range.to, timezone: "IST (UTC+05:30)", inclusive: true },
    data_as_of: new Date().toISOString(),
    tracking: {
      quiz_tracking_began: quizBegan,
      progress_tracking_began: progressBegan,
      chat_tracking: "Chat counts come from stored messages since the app started.",
    },
    cards: {
      students_total: num(students.n),
      registered_in_range: num(students.new_n),
      active_students: num(active.n),
      sign_ins: progressBegan ? num(events.sign_ins) : null,
      chat_questions: num(chat.n),
      modules_generated: num(generated.n),
      modules_opened: progressBegan ? num(progress.opened) : null,
      modules_completed: progressBegan ? num(progress.completed) : null,
      pdf_downloads: num(events.pdf),
      quiz_attempts: num(quiz.n),
      timed_out: num(quiz.timed_out),
      abandoned: num(abandoned.n),
      assessments_submitted: num(quiz.assessments),
      mean_percent: achievementRow.mean == null ? null : round1(Number(achievementRow.mean)),
      mean_percent_n: num(achievementRow.n),
      mean_percent_timed_out: num(achievementRow.timed_out),
      practice_mean_percent_n: num(quiz.practice_n),
      practice_mean_percent: quiz.practice_mean == null ? null : round1(Number(quiz.practice_mean)),
    },
    notes: {
      quiz: trackingNote(quizBegan, range, "Quizzes"),
      progress: trackingNote(progressBegan, range, "Sign-ins and module opened/completed"),
      pdf: "PDF downloads before progress tracking began were recorded per session and are included when the session belongs to a student.",
    },
    definitions: DEFINITIONS,
    not_implemented: [
      "Digital-attitude and social-engagement: questionnaire shells exist in Research; results appear only after the researcher's approved items are published.",
      "Collaboration features: not built (no research requirement found).",
    ],
  };
}

export async function overview(req, res, next) {
  try {
    res.json(await overviewData(parseRange(req.query)));
  } catch (err) {
    next(err);
  }
}

const SORTS = {
  name: "display_name",
  roll: "roll_number",
  joined: "joined",
  chat_questions: "chat_questions",
  quiz_attempts: "quiz_attempts",
  mean_percent: "mean_percent",
  modules_completed: "modules_completed",
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
    where.push("(u.display_name LIKE ? OR u.roll_number = ?)");
    params.push(`%${f.search}%`, f.search.trim());
  }
  const base = `
    SELECT u.id, u.display_name, u.roll_number, u.cohort_code, u.created_at AS joined,
      (SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id
         JOIN anonymous_sessions s ON s.id = c.session_id
         WHERE s.user_id = u.id AND m.role = 'user' AND m.created_at >= ? AND m.created_at < ?) AS chat_questions,
      (SELECT COUNT(*) FROM quiz_attempts a WHERE a.user_id = u.id AND a.status = 'submitted'
         AND a.submitted_at >= ? AND a.submitted_at < ?) AS quiz_attempts,
      (SELECT AVG(a.percent) FROM quiz_attempts a WHERE a.user_id = u.id AND a.status = 'submitted'
         AND a.submitted_at >= ? AND a.submitted_at < ?) AS mean_percent,
      (SELECT COUNT(*) FROM module_progress p WHERE p.user_id = u.id AND p.completed_at >= ? AND p.completed_at < ?) AS modules_completed,
      -- CAST: GREATEST over mixed DATETIME/string arguments returns a string, which the driver would not read as UTC.
      CAST(GREATEST(
        COALESCE((SELECT MAX(m.created_at) FROM messages m JOIN conversations c ON c.id = m.conversation_id
           JOIN anonymous_sessions s ON s.id = c.session_id WHERE s.user_id = u.id AND m.role = 'user'), '1970-01-01'),
        COALESCE((SELECT MAX(a.submitted_at) FROM quiz_attempts a WHERE a.user_id = u.id), '1970-01-01'),
        COALESCE((SELECT MAX(p.last_opened_at) FROM module_progress p WHERE p.user_id = u.id), '1970-01-01')) AS DATETIME) AS last_active
    FROM users u WHERE ${where.join(" AND ")}`;
  const rangeParams = [range.start, range.end, range.start, range.end, range.start, range.end, range.start, range.end];
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
      roll_number: r.roll_number || null,
      cohort_code: r.cohort_code || null,
      joined: r.joined,
      chat_questions: Number(r.chat_questions),
      quiz_attempts: Number(r.quiz_attempts),
      mean_percent: r.mean_percent == null ? null : round1(Number(r.mean_percent)),
      modules_completed: Number(r.modules_completed),
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
    const [users] = await pool.query("SELECT id, display_name, roll_number, cohort_code, created_at, role FROM users WHERE id = ?", [req.params.userId]);
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
      student: { id: u.id, display_name: u.display_name, roll_number: u.roll_number, cohort_code: u.cohort_code, joined: u.created_at },
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
    const [events] = await pool.query(
      `SELECT ${k("e.created_at")} AS bucket, e.event_type, COUNT(*) AS n
       FROM analytics_events e
       LEFT JOIN anonymous_sessions s ON s.id = e.session_id
       JOIN users u ON u.id = COALESCE(e.user_id, s.user_id) AND u.role = 'student'
       WHERE e.event_type IN ('MODULE_OPENED', 'MODULE_COMPLETED', 'PDF_DOWNLOADED', 'USER_SIGNED_IN')
         AND e.created_at >= ? AND e.created_at < ? GROUP BY bucket, e.event_type`,
      [range.start, range.end]
    );
    const built = buildSeries({ quiz, chat, events }, range.from, range.to, bucket);
    res.json({
      range: { from: range.from, to: range.to, timezone: "IST (UTC+05:30)", inclusive: true },
      bucket,
      note: "Every IST day (or week) in the range is listed, including days with no activity. n = number of finished attempts; means from small n are not reliable.",
      ...built,
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
    const prePost = await prePostData(range);
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

// ---------- Pre/post (teacher-designated pairs only) ----------
// A post-test counts only when the teacher linked it to a pre-test (quizzes.pre_quiz_id).
// Basis: each student's FIRST finished attempt on each quiz. Post-test attempts are filtered by the date range;
// pre-test attempts may be from any earlier date. Only students with both are compared (matched pairs).
export async function prePostData(range) {
  const [pairs] = await pool.query(
    `SELECT post.id AS post_id, post.title AS post_title, post.status AS post_status, pre.id AS pre_id, pre.title AS pre_title, pre.status AS pre_status
     FROM quizzes post JOIN quizzes pre ON pre.id = post.pre_quiz_id
     WHERE post.owner_user_id IS NULL AND post.status <> 'draft' ORDER BY post.created_at`
  );
  const firstAttempts = async (quizId, filterRange) => {
    const [rows] = await pool.query(
      `SELECT a.user_id, a.percent, a.submitted_at FROM quiz_attempts a JOIN users u ON u.id = a.user_id AND u.role = 'student'
       WHERE a.quiz_id = ? AND a.status = 'submitted'
         AND a.attempt_no = (SELECT MIN(b.attempt_no) FROM quiz_attempts b WHERE b.quiz_id = a.quiz_id AND b.user_id = a.user_id AND b.status = 'submitted')
         ${filterRange ? "AND a.submitted_at >= ? AND a.submitted_at < ?" : ""}`,
      filterRange ? [quizId, range.start, range.end] : [quizId]
    );
    return new Map(rows.map((r) => [r.user_id, Number(r.percent)]));
  };
  const out = [];
  for (const pair of pairs) {
    const post = await firstAttempts(pair.post_id, true);
    const pre = await firstAttempts(pair.pre_id, false);
    const matched = [...post.keys()].filter((id) => pre.has(id));
    const preVals = matched.map((id) => pre.get(id));
    const postVals = matched.map((id) => post.get(id));
    const gains = matched.map((id) => post.get(id) - pre.get(id));
    const avg = (v) => (v.length ? round2(v.reduce((x, y) => x + y, 0) / v.length) : null);
    out.push({
      pre_quiz: { id: pair.pre_id, title: pair.pre_title, status: pair.pre_status, n: pre.size },
      post_quiz: { id: pair.post_id, title: pair.post_title, status: pair.post_status, n: post.size },
      paired_n: matched.length,
      mean_pre: avg(preVals),
      mean_post: avg(postVals),
      mean_gain: avg(gains),
      paired_t: pairedT(gains),
      unmatched: {
        pre_only: [...pre.keys()].filter((id) => !post.has(id)).map(studentRef).sort(),
        post_only: [...post.keys()].filter((id) => !pre.has(id)).map(studentRef).sort(),
      },
      matched_students: matched.map((id) => ({ student_ref: studentRef(id), pre: pre.get(id), post: post.get(id), gain: round2(post.get(id) - pre.get(id)) })),
    });
  }
  return {
    available: out.length > 0,
    pairs: out,
    method:
      "Matched students only (first finished attempt on each quiz). Paired t-test reported as a descriptive statistic; it does not show what caused any change.",
    note: out.length ? null : "No pre/post pair yet. Create a quiz with phase 'post' and link it to its pre-test.",
  };
}

// ---------- CSV reports ----------
// "2026-10-15 14:05:09 IST": exports show the school's time zone.
export function istStamp(d) {
  if (!d) return "";
  const t = new Date(d);
  if (Number.isNaN(t.getTime())) return "";
  return `${new Date(t.getTime() + 330 * 60 * 1000).toISOString().slice(0, 19).replace("T", " ")} IST`;
}

function studentRef(id) {
  return `S-${String(id).replace(/-/g, "").slice(0, 8)}`;
}

export async function buildReport(req) {
  {
    const range = parseRange(req.query);
    const kind = req.params.kind;
    const withNames = req.query.include_names === "1";
    let header;
    let rows;
    let title = REPORT_TITLES[kind] || kind;
    if (kind === "attempts") {
      const [data] = await pool.query(
        `SELECT a.user_id, u.display_name, z.title, z.topic, z.activity_type, z.mode, z.assessment_phase, a.attempt_no, a.end_reason,
                a.score_points, a.max_points, a.percent, a.duration_sec, a.submitted_at
         FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN users u ON u.id = a.user_id AND u.role = 'student'
         WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ? ORDER BY a.submitted_at`,
        [range.start, range.end]
      );
      header = ["student_ref", ...(withNames ? ["student_name"] : []), "quiz", "topic", "activity_type", "mode", "phase", "attempt_no", "end_reason", "score", "max_score", "percent", "duration_sec", "submitted_at_ist"];
      rows = data.map((r) => [
        studentRef(r.user_id), ...(withNames ? [r.display_name] : []), r.title, r.topic, r.activity_type, r.mode, r.assessment_phase,
        r.attempt_no, r.end_reason || "submitted", Number(r.score_points), Number(r.max_points), Number(r.percent), r.duration_sec, istStamp(r.submitted_at),
      ]);
    } else if (kind === "students") {
      const { rows: data } = await studentRows(range, { sort: "name", dir: "asc", page: 1, size: 100, activity: "all" }, { paginate: false });
      header = ["student_ref", ...(withNames ? ["student_name"] : []), "roll_number", "joined_ist", "chat_questions", "quiz_attempts", "mean_percent", "modules_completed", "last_active_ist"];
      rows = data.map((r) => [studentRef(r.id), ...(withNames ? [r.display_name] : []), r.roll_number || "", istStamp(r.joined), r.chat_questions, r.quiz_attempts, r.mean_percent, r.modules_completed, istStamp(r.last_active)]);
    } else if (kind === "topics") {
      const data = await topicRows(range);
      header = ["topic", "answers", "students", "attempts", "accuracy_percent"];
      rows = data.map((r) => [r.topic, r.answered, r.students, r.attempts, r.accuracy]);
    } else if (kind === "prepost") {
      const data = await prePostData(range);
      header = ["pre_quiz", "post_quiz", "student_ref", "status", "pre_percent", "post_percent", "gain"];
      rows = [];
      for (const pair of data.pairs) {
        for (const m of pair.matched_students) rows.push([pair.pre_quiz.title, pair.post_quiz.title, m.student_ref, "matched", m.pre, m.post, m.gain]);
        for (const ref of pair.unmatched.pre_only) rows.push([pair.pre_quiz.title, pair.post_quiz.title, ref, "pre_only", "", "", ""]);
        for (const ref of pair.unmatched.post_only) rows.push([pair.pre_quiz.title, pair.post_quiz.title, ref, "post_only", "", "", ""]);
      }
    } else if (kind === "questionnaires") {
      ({ header, rows } = await questionnaireCsv(range, req.query.instrument_id));
    } else if (kind === "research_summary") {
      header = ["measure", "value"];
      rows = researchSummaryRows(await overviewData(range));
    } else if (EXTRA_REPORTS[kind]) {
      const extra = await EXTRA_REPORTS[kind](range, req.query, withNames);
      ({ header, rows } = extra);
      title = extra.title;
    } else {
      throw new AppError(404, "NOT_FOUND", "Unknown report.");
    }
    return { kind, range, header, rows, title };
  }
}

function reportFilename(kind, range, ext) {
  return `historybot-${kind}-${range.from}-to-${range.to}.${ext}`;
}

export async function reportCsv(req, res, next) {
  try {
    const { kind, range, header, rows } = await buildReport(req);
    const csv = toCsv(header, rows);
    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader("Content-Disposition", `attachment; filename="${reportFilename(kind, range, "csv")}"`);
    res.setHeader("Cache-Control", "no-store");
    res.send(`\ufeff${csv}`);
  } catch (err) {
    next(err);
  }
}

export async function reportPdf(req, res, next) {
  try {
    const { kind, range, header, rows, title } = await buildReport(req);
    const pdf = await renderPdf({
      title,
      header,
      rows,
      range,
      notes: ["Student names are hidden unless 'include names' was chosen. Only stored records are shown; nothing is estimated."],
    });
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="${reportFilename(kind, range, "pdf")}"`);
    res.setHeader("Cache-Control", "no-store");
    res.send(pdf);
  } catch (err) {
    next(err);
  }
}

export async function studentTimelineApi(req, res, next) {
  try {
    const u = await requireStudent(req.params.userId);
    const range = req.query.from || req.query.to ? parseRange(req.query) : null;
    const items = await studentTimeline(u.id, range, 1000);
    res.json({
      student: { id: u.id, display_name: u.display_name, roll_number: u.roll_number, cohort_code: u.cohort_code },
      range: range ? { from: range.from, to: range.to } : null,
      items,
      note: "Times are stored in UTC and shown in IST. Chat question text is not shown here. Activity before tracking began is not available.",
    });
  } catch (err) {
    next(err);
  }
}
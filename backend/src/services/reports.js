// Extra teacher reports (student activity timeline, class activity by day,
// learning progress, research summary) and a plain PDF renderer for any report.
// Only stored records are reported; nothing is estimated or back-filled.
import PDFDocument from "pdfkit";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { requireUuid } from "./quizData.js";

const IST_MS = 330 * 60 * 1000;
export function istStampLocal(d) {
  if (!d) return "";
  const t = new Date(d);
  if (Number.isNaN(t.getTime())) return "";
  return `${new Date(t.getTime() + IST_MS).toISOString().slice(0, 19).replace("T", " ")} IST`;
}
const ref = (id) => `S-${String(id).replace(/-/g, "").slice(0, 8)}`;

const EVENT_LABELS = {
  SESSION_STARTED: "Opened HistoryBot",
  USER_REGISTERED: "Registered",
  USER_SIGNED_IN: "Logged in",
  QUESTION_ASKED: "Asked a chat question",
  ANSWER_GENERATED: "Received an answer",
  NEW_CHAT: "Started a new chat",
  LANGUAGE_CHANGED: "Changed language",
  E_CONTENT_GENERATED: "Generated a learning module",
  MODULE_OPENED: "Opened a learning module",
  MODULE_COMPLETED: "Completed a learning module",
  PDF_DOWNLOADED: "Downloaded a PDF",
  QUIZ_STARTED: "Started a quiz",
  QUIZ_SUBMITTED: "Submitted a quiz",
  QUIZ_TIMED_OUT: "Quiz timed out",
  ACTIVITY_CREATED: "Created a practice activity",
  QUESTIONNAIRE_SUBMITTED: "Submitted a questionnaire",
};

export async function requireStudent(userId) {
  requireUuid(String(userId || ""), "student id");
  const [rows] = await pool.query("SELECT id, display_name, roll_number, cohort_code, role, created_at FROM users WHERE id = ?", [userId]);
  if (!rows.length || rows[0].role !== "student") throw new AppError(404, "NOT_FOUND", "Student not found.");
  return rows[0];
}

// Chronological activity for one student. Chat text is never included.
export async function studentTimeline(userId, range = null, limit = 1000) {
  const params = [userId, userId];
  let when = "";
  if (range) {
    when = "AND e.created_at >= ? AND e.created_at < ?";
    params.push(range.start, range.end);
  }
  const [events] = await pool.query(
    `SELECT e.event_type, e.topic_text, e.language, e.created_at FROM analytics_events e
     LEFT JOIN anonymous_sessions s ON s.id = e.session_id
     WHERE (e.user_id = ? OR (e.user_id IS NULL AND s.user_id = ?)) ${when}
     ORDER BY e.created_at, e.id LIMIT ${Number(limit)}`,
    params
  );
  const aParams = [userId];
  let aWhen = "";
  if (range) {
    aWhen = "AND a.submitted_at >= ? AND a.submitted_at < ?";
    aParams.push(range.start, range.end);
  }
  const [attempts] = await pool.query(
    `SELECT a.submitted_at, a.percent, a.score_points, a.max_points, a.end_reason, z.title FROM quiz_attempts a
     JOIN quizzes z ON z.id = a.quiz_id WHERE a.user_id = ? AND a.status = 'submitted' ${aWhen}`,
    aParams
  );
  const items = events
    .filter((e) => e.event_type !== "QUIZ_SUBMITTED" && e.event_type !== "QUIZ_TIMED_OUT")
    .map((e) => ({
      at: e.created_at,
      type: e.event_type,
      label: EVENT_LABELS[e.event_type] || e.event_type,
      detail: e.event_type === "QUESTION_ASKED" ? "" : e.topic_text || "",
    }));
  for (const a of attempts) {
    items.push({
      at: a.submitted_at,
      type: a.end_reason === "timed_out" ? "QUIZ_TIMED_OUT" : "QUIZ_SUBMITTED",
      label: a.end_reason === "timed_out" ? "Quiz timed out (auto-submitted)" : "Submitted a quiz",
      detail: `${a.title}: ${Number(a.score_points)}/${Number(a.max_points)} (${Number(a.percent)}%)`,
    });
  }
  items.sort((x, y) => new Date(x.at) - new Date(y.at));
  return items;
}

async function timelineReport(range, query, withNames) {
  const u = await requireStudent(query.user_id);
  const items = await studentTimeline(u.id, range, 5000);
  return {
    title: `Student activity: ${withNames ? u.display_name : ref(u.id)}${u.roll_number ? ` (roll ${u.roll_number})` : ""}`,
    header: ["student_ref", ...(withNames ? ["student_name"] : []), "roll_number", "time_ist", "activity", "detail"],
    rows: items.map((i) => [ref(u.id), ...(withNames ? [u.display_name] : []), u.roll_number || "", istStampLocal(i.at), i.label, i.detail]),
  };
}

async function classActivityReport(range) {
  const [rows] = await pool.query(
    `SELECT DATE(CONVERT_TZ(e.created_at, '+00:00', '+05:30')) AS day, e.event_type, COUNT(*) AS n,
            COUNT(DISTINCT COALESCE(e.user_id, s.user_id)) AS students
     FROM analytics_events e LEFT JOIN anonymous_sessions s ON s.id = e.session_id
     JOIN users u ON u.id = COALESCE(e.user_id, s.user_id) AND u.role = 'student'
     WHERE e.created_at >= ? AND e.created_at < ?
     GROUP BY day, e.event_type ORDER BY day, e.event_type`,
    [range.start, range.end]
  );
  return {
    title: "Class activity by day (IST)",
    header: ["date_ist", "activity", "count", "students"],
    rows: rows.map((r) => [
      typeof r.day === "string" ? r.day : new Date(r.day.getTime() - r.day.getTimezoneOffset() * 60000).toISOString().slice(0, 10),
      EVENT_LABELS[r.event_type] || r.event_type,
      Number(r.n),
      Number(r.students),
    ]),
  };
}

async function progressReport(range, _query, withNames) {
  const [rows] = await pool.query(
    `SELECT u.id, u.display_name, u.roll_number, d.topic, p.first_opened_at, p.last_opened_at, p.open_count, p.pdf_downloads, p.completed_at, p.completion_method
     FROM module_progress p JOIN users u ON u.id = p.user_id AND u.role = 'student'
     LEFT JOIN econtent_documents d ON d.id = p.econtent_id
     WHERE p.last_opened_at >= ? AND p.last_opened_at < ? ORDER BY u.display_name, p.first_opened_at`,
    [range.start, range.end]
  );
  return {
    title: "Learning progress (learning modules)",
    header: ["student_ref", ...(withNames ? ["student_name"] : []), "roll_number", "module_topic", "first_opened_ist", "last_opened_ist", "times_opened", "pdf_downloads", "completed_ist", "completion_method"],
    rows: rows.map((r) => [
      ref(r.id), ...(withNames ? [r.display_name] : []), r.roll_number || "", r.topic || "", istStampLocal(r.first_opened_at), istStampLocal(r.last_opened_at),
      Number(r.open_count || 0), Number(r.pdf_downloads || 0), istStampLocal(r.completed_at), r.completion_method || "",
    ]),
  };
}

export function researchSummaryRows(ov) {
  const c = ov.cards;
  const val = (x) => (x == null ? "not tracked in this range" : x);
  return [
    ["Date range (IST)", `${ov.range.from} to ${ov.range.to}`],
    ["Students registered (total)", c.students_total],
    ["Students registered in range", c.registered_in_range],
    ["Active students in range", c.active_students],
    ["Log-ins", val(c.sign_ins)],
    ["Chat questions", c.chat_questions],
    ["Learning modules generated", c.modules_generated],
    ["Learning modules opened", val(c.modules_opened)],
    ["Learning modules completed", val(c.modules_completed)],
    ["PDF downloads", c.pdf_downloads],
    ["Quiz attempts finished", c.quiz_attempts],
    ["Quiz attempts timed out", c.timed_out],
    ["Assessments submitted", c.assessments_submitted],
    ["Assessment mean % (first attempts)", c.mean_percent == null ? "no data" : `${c.mean_percent} (n=${c.mean_percent_n})`],
    ["Practice mean %", c.practice_mean_percent == null ? "no data" : `${c.practice_mean_percent} (n=${c.practice_mean_percent_n})`],
    ["Quiz tracking began", ov.tracking.quiz_tracking_began ? istStampLocal(ov.tracking.quiz_tracking_began) : "not started"],
    ["Log-in/module tracking began", ov.tracking.progress_tracking_began ? istStampLocal(ov.tracking.progress_tracking_began) : "not started"],
    ["Not tracked", "Time spent reading, page views, and anything before the tracking dates above."],
    ...ov.not_implemented.map((t) => ["Not available", t]),
  ];
}

export const EXTRA_REPORTS = {
  timeline: timelineReport,
  class_activity: classActivityReport,
  progress: progressReport,
};

export const REPORT_TITLES = {
  attempts: "Assessment report (quiz attempts)",
  students: "Student list with activity",
  topics: "Topic accuracy",
  prepost: "Pre/post comparison (matched students)",
  questionnaires: "Questionnaire responses",
  research_summary: "Research summary",
};

// Simple A4 landscape table. Long cells wrap; rows break across pages.
export function renderPdf({ title, header, rows, range, notes = [] }) {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ size: "A4", layout: "landscape", margin: 36, info: { Title: title, Author: "HistoryBot" } });
    const chunks = [];
    doc.on("data", (c) => chunks.push(c));
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);
    const left = doc.page.margins.left;
    const width = doc.page.width - left - doc.page.margins.right;
    doc.font("Helvetica-Bold").fontSize(15).text(title);
    doc.font("Helvetica").fontSize(9).fillColor("#444")
      .text(`HistoryBot teacher report · ${range ? `${range.from} to ${range.to} (IST)` : ""} · generated ${istStampLocal(new Date())}`);
    for (const n of notes) doc.text(n);
    doc.moveDown(0.6).fillColor("#000");
    const cols = header.length;
    const colW = width / cols;
    const drawRow = (cells, bold) => {
      doc.font(bold ? "Helvetica-Bold" : "Helvetica").fontSize(8);
      const texts = cells.map((c) => (c == null ? "" : String(c)));
      const h = Math.max(...texts.map((t) => doc.heightOfString(t, { width: colW - 4 }))) + 4;
      if (doc.y + h > doc.page.height - doc.page.margins.bottom) {
        doc.addPage();
      }
      const y = doc.y;
      texts.forEach((t, i) => doc.text(t, left + i * colW + 2, y + 2, { width: colW - 4 }));
      doc.moveTo(left, y + h).lineTo(left + width, y + h).strokeColor("#ccc").lineWidth(0.5).stroke();
      doc.x = left;
      doc.y = y + h;
    };
    drawRow(header, true);
    if (!rows.length) drawRow(["No records in this range.", ...Array(cols - 1).fill("")], false);
    for (const r of rows) drawRow(r, false);
    doc.end();
  });
}

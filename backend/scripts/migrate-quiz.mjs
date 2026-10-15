import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import crypto from "node:crypto";

const require = createRequire(import.meta.url);
const mysql = require("mysql2/promise");
const dotenv = require("dotenv");

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

function mysqlConfig() {
  return {
    host: process.env.MYSQL_HOST || "localhost",
    port: Number(process.env.MYSQL_PORT || 3306),
    user: process.env.MYSQL_USER,
    password: process.env.MYSQL_PASSWORD || "",
    database: process.env.MYSQL_DATABASE || "historybot",
  };
}

function findDump() {
  const candidates = [
    "C:\\Program Files\\MySQL\\MySQL Server 8.0\\bin\\mysqldump.exe",
    "C:\\Program Files\\MySQL\\MySQL Server 8.4\\bin\\mysqldump.exe",
    "mysqldump",
  ];
  for (const candidate of candidates) {
    if (candidate === "mysqldump" || fs.existsSync(candidate)) return candidate;
  }
  return "mysqldump";
}

function backupDatabase() {
  const cfg = mysqlConfig();
  const dir = path.join(root, "tmp", "backups");
  fs.mkdirSync(dir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const outfile = path.join(dir, `historybot-pre-quiz-${stamp}.sql`);
  const fd = fs.openSync(outfile, "w");
  const args = [
    "-h",
    cfg.host,
    "-P",
    String(cfg.port),
    "-u",
    cfg.user,
    "--single-transaction",
    "--databases",
    cfg.database,
  ];
  // Pass the password through the child's environment, not the command line,
  // so it does not appear in the process list.
  const env = { ...process.env };
  if (cfg.password) env.MYSQL_PWD = cfg.password;
  const result = spawnSync(findDump(), args, { stdio: ["ignore", fd, "pipe"], env });
  fs.closeSync(fd);
  if (result.status !== 0) {
    fs.rmSync(outfile, { force: true });
    const raw = Buffer.concat([result.stderr || Buffer.alloc(0), result.stdout || Buffer.alloc(0)]).toString("utf8");
    const safe = cfg.password ? raw.replaceAll(cfg.password, "[redacted]") : raw;
    throw new Error(`Database backup failed. Schema was not changed. ${safe.slice(0, 500)}`);
  }
  const size = fs.statSync(outfile).size;
  if (size < 100) {
    throw new Error("Database backup looked empty. Schema was not changed.");
  }
  console.log(`BACKUP ${outfile} (${size} bytes)`);
}

async function columnExists(conn, table, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`,
    [table, name]
  );
  return Number(rows[0].n) > 0;
}

async function indexExists(conn, table, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND INDEX_NAME = ?`,
    [table, name]
  );
  return Number(rows[0].n) > 0;
}

async function constraintExists(conn, table, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.TABLE_CONSTRAINTS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND CONSTRAINT_NAME = ?`,
    [table, name]
  );
  return Number(rows[0].n) > 0;
}

// Applies scripts/sql/005_quizzes_analytics.sql (additive) after a mysqldump backup, then
// seeds the textbook question bank and quizzes (idempotent; keyed by seed_key).
// Usage: node backend/scripts/migrate-quiz.mjs [--seed-only]
async function applySchema(conn) {
  const sql = fs
    .readFileSync(path.join(root, "scripts/sql/005_quizzes_analytics.sql"), "utf8")
    .split("\n")
    .filter((line) => !line.trim().startsWith("--"))
    .join("\n");
  for (const statement of sql.split(";").map((part) => part.trim()).filter(Boolean)) {
    await conn.query(statement);
  }
  console.log("ENSURED schema_migrations, quiz_questions, quizzes, quiz_items, quiz_attempts, quiz_answers");
  if (!(await columnExists(conn, "analytics_events", "user_id"))) {
    await conn.query("ALTER TABLE analytics_events ADD COLUMN user_id CHAR(36) NULL");
    console.log("ADDED analytics_events.user_id");
  }
  if (!(await indexExists(conn, "analytics_events", "idx_analytics_user"))) {
    await conn.query("ALTER TABLE analytics_events ADD INDEX idx_analytics_user (user_id, created_at)");
    console.log("ADDED idx_analytics_user");
  }
  if (!(await indexExists(conn, "analytics_events", "idx_analytics_type"))) {
    await conn.query("ALTER TABLE analytics_events ADD INDEX idx_analytics_type (event_type, created_at)");
    console.log("ADDED idx_analytics_type");
  }
  if (!(await constraintExists(conn, "analytics_events", "fk_analytics_user"))) {
    await conn.query(
      "ALTER TABLE analytics_events ADD CONSTRAINT fk_analytics_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE"
    );
    console.log("ADDED fk_analytics_user");
  }
  // Widen the event-type CHECK so quiz/activity events are allowed (existing values unchanged).
  const [checks] = await conn.query(
    `SELECT CHECK_CLAUSE AS clause FROM information_schema.CHECK_CONSTRAINTS
     WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_analytics_event_type'`
  );
  if (checks.length && !String(checks[0].clause).includes("QUIZ_SUBMITTED")) {
    await conn.query(
      `ALTER TABLE analytics_events DROP CHECK chk_analytics_event_type,
       ADD CONSTRAINT chk_analytics_event_type CHECK (event_type IN (
         'SESSION_STARTED', 'QUESTION_ASKED', 'ANSWER_GENERATED', 'LANGUAGE_CHANGED', 'E_CONTENT_GENERATED',
         'PDF_DOWNLOADED', 'NEW_CHAT', 'QUIZ_STARTED', 'QUIZ_SUBMITTED', 'ACTIVITY_CREATED'))`
    );
    console.log("WIDENED chk_analytics_event_type (+QUIZ_STARTED, QUIZ_SUBMITTED, ACTIVITY_CREATED)");
  }
  await conn.query("INSERT IGNORE INTO schema_migrations (id) VALUES ('005_quizzes_analytics')");
}

function norm(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

async function seed(conn) {
  const questions = JSON.parse(fs.readFileSync(path.join(root, "data/quiz/seed_questions.json"), "utf8"));
  const quizzes = JSON.parse(fs.readFileSync(path.join(root, "data/quiz/seed_quizzes.json"), "utf8"));
  const passages = JSON.parse(fs.readFileSync(path.join(root, "data/quiz/textbook_passages.json"), "utf8"));
  const passageText = new Map(passages.map((p) => [p.chunk_id, norm(p.text)]));
  const [admins] = await conn.query("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1");
  const teacherId = admins[0]?.id || null;
  const ids = new Map();
  let published = 0;
  let drafts = 0;
  for (const q of questions) {
    // An answer key is published only when every cited excerpt is found verbatim in the textbook passage.
    const sources = q.extra_sources || [{ chunk_id: q.source_chunk_id, excerpt: q.source_excerpt }];
    const verified = sources.every((s) => (passageText.get(s.chunk_id) || "").includes(norm(s.excerpt)));
    const status = q.status === "published" && verified ? "published" : "draft";
    if (status === "published") published += 1;
    else drafts += 1;
    const [found] = await conn.query("SELECT id FROM quiz_questions WHERE seed_key = ?", [q.key]);
    if (found.length) {
      ids.set(q.key, found[0].id);
      continue; // never overwrite a question a teacher may have reviewed or edited
    }
    const id = crypto.randomUUID();
    ids.set(q.key, id);
    await conn.query(
      `INSERT INTO quiz_questions
        (id, seed_key, qtype, prompt, options_json, answer_json, explanation, topic, difficulty, source_document,
         textbook_page, source_chunk_id, source_excerpt, status, origin, created_by, reviewed_by, reviewed_at, review_note)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'fixture',?,?,?,?)`,
      [
        id, q.key, q.qtype, q.prompt, q.options ? JSON.stringify(q.options) : null, JSON.stringify(q.answer),
        q.explanation || null, q.topic, q.difficulty, q.source_document || null, q.textbook_page ?? null,
        q.source_chunk_id || null, String(q.source_excerpt || "").slice(0, 1000), status, teacherId,
        status === "published" ? teacherId : null, status === "published" ? new Date() : null,
        status === "published" ? "Seed: answer key checked against the cited textbook excerpt." : "Seed draft: needs teacher review.",
      ]
    );
  }
  let quizCount = 0;
  for (const z of quizzes) {
    const [found] = await conn.query("SELECT id FROM quizzes WHERE seed_key = ?", [z.key]);
    if (found.length) continue;
    const id = crypto.randomUUID();
    const qids = z.questions.map((key) => ids.get(key)).filter(Boolean);
    // A quiz is published only when all of its questions are published.
    const [statusRows] = qids.length
      ? await conn.query("SELECT COUNT(*) AS n FROM quiz_questions WHERE id IN (?) AND status = 'published'", [qids])
      : [[{ n: 0 }]];
    const status = z.status === "published" && Number(statusRows[0].n) === qids.length ? "published" : "draft";
    await conn.query(
      `INSERT INTO quizzes (id, seed_key, title, description, topic, difficulty, mode, activity_type, assessment_phase,
         time_limit_sec, max_attempts, reveal_answers, status, created_by, published_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [
        id, z.key, z.title, z.description, z.topic, z.difficulty, z.mode, z.activity_type, z.assessment_phase || "none",
        z.time_limit_sec, z.max_attempts, z.reveal_answers, status, teacherId, status === "published" ? new Date() : null,
      ]
    );
    let position = 1;
    for (const qid of qids) {
      await conn.query("INSERT INTO quiz_items (quiz_id, question_id, position) VALUES (?,?,?)", [id, qid, position]);
      position += 1;
    }
    quizCount += 1;
  }
  console.log(`SEEDED questions published=${published} draft=${drafts}; new quizzes=${quizCount}; teacher=${teacherId ? "found" : "none"}`);
}

async function main() {
  if (!process.env.MYSQL_USER) throw new Error("MYSQL_USER is required");
  const seedOnly = process.argv.includes("--seed-only");
  if (!seedOnly) backupDatabase();
  const conn = await mysql.createConnection(mysqlConfig());
  try {
    if (!seedOnly) await applySchema(conn);
    await seed(conn);
    const [m] = await conn.query("SELECT applied_at FROM schema_migrations WHERE id = '005_quizzes_analytics'");
    console.log(`MIGRATION 005 applied_at=${m[0]?.applied_at?.toISOString?.() || "missing"}`);
  } finally {
    await conn.end();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});

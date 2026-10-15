// Applies scripts/sql/006_progress_research.sql (additive) after a mysqldump backup, widens CHECKs,
// adds columns idempotently, and seeds the two research-instrument SHELLS (draft, placeholder items).
// Usage: node backend/scripts/migrate-006.mjs
import crypto from "node:crypto";
import {
  backupDatabase,
  checkClause,
  columnExists,
  constraintExists,
  indexExists,
  mysql,
  mysqlConfig,
  sqlStatements,
} from "./lib/migrate-utils.mjs";

const EVENT_TYPES = [
  "SESSION_STARTED", "QUESTION_ASKED", "ANSWER_GENERATED", "LANGUAGE_CHANGED", "E_CONTENT_GENERATED",
  "PDF_DOWNLOADED", "NEW_CHAT", "QUIZ_STARTED", "QUIZ_SUBMITTED", "ACTIVITY_CREATED",
  "USER_REGISTERED", "USER_SIGNED_IN", "MODULE_OPENED", "MODULE_COMPLETED", "QUIZ_TIMED_OUT", "QUESTIONNAIRE_SUBMITTED",
];

async function addColumn(conn, table, name, ddl) {
  if (await columnExists(conn, table, name)) return;
  await conn.query(`ALTER TABLE ${table} ADD COLUMN ${name} ${ddl}`);
  console.log(`ADDED ${table}.${name}`);
}

async function widenCheck(conn, table, name, mustInclude, clause) {
  const current = await checkClause(conn, name);
  if (current && current.includes(mustInclude)) return;
  try {
    await conn.query(`ALTER TABLE ${table} ${current ? `DROP CHECK ${name},` : ""} ADD CONSTRAINT ${name} CHECK (${clause})`);
  } catch (err) {
    // MariaDB (used only for local test databases) spells it DROP CONSTRAINT.
    if (!current || err.code !== "ER_PARSE_ERROR") throw err;
    await conn.query(`ALTER TABLE ${table} DROP CONSTRAINT ${name}, ADD CONSTRAINT ${name} CHECK (${clause})`);
  }
  console.log(`WIDENED ${name}`);
}

async function applySchema(conn) {
  for (const statement of sqlStatements("scripts/sql/006_progress_research.sql")) await conn.query(statement);
  console.log("ENSURED module_progress, research_instruments, research_items, research_responses, research_response_items");

  await addColumn(conn, "analytics_events", "idempotency_key", "VARCHAR(120) NULL");
  if (!(await indexExists(conn, "analytics_events", "uq_analytics_idem"))) {
    await conn.query("ALTER TABLE analytics_events ADD UNIQUE KEY uq_analytics_idem (idempotency_key)");
    console.log("ADDED uq_analytics_idem");
  }
  await widenCheck(
    conn, "analytics_events", "chk_analytics_event_type", "QUESTIONNAIRE_SUBMITTED",
    `event_type IN (${EVENT_TYPES.map((t) => `'${t}'`).join(", ")})`
  );

  await addColumn(conn, "quiz_attempts", "end_reason", "VARCHAR(12) NULL");
  await widenCheck(conn, "quiz_attempts", "chk_attempt_end_reason", "timed_out", "end_reason IS NULL OR end_reason IN ('submitted', 'timed_out')");
  // Backfill: an attempt finalised exactly at its deadline was closed by the timer.
  const [bf] = await conn.query(
    `UPDATE quiz_attempts SET end_reason = IF(deadline_at IS NOT NULL AND submitted_at = deadline_at, 'timed_out', 'submitted')
     WHERE status = 'submitted' AND end_reason IS NULL`
  );
  console.log(`BACKFILLED quiz_attempts.end_reason rows=${bf.affectedRows}`);

  await addColumn(conn, "quizzes", "pre_quiz_id", "CHAR(36) NULL");
  if (!(await constraintExists(conn, "quizzes", "fk_quiz_pre"))) {
    await conn.query("ALTER TABLE quizzes ADD CONSTRAINT fk_quiz_pre FOREIGN KEY (pre_quiz_id) REFERENCES quizzes (id) ON DELETE SET NULL");
    console.log("ADDED fk_quiz_pre");
  }
  await addColumn(conn, "quizzes", "source_econtent_id", "CHAR(36) NULL");
  if (!(await constraintExists(conn, "quizzes", "fk_quiz_econtent"))) {
    await conn.query(
      "ALTER TABLE quizzes ADD CONSTRAINT fk_quiz_econtent FOREIGN KEY (source_econtent_id) REFERENCES econtent_documents (id) ON DELETE SET NULL"
    );
    console.log("ADDED fk_quiz_econtent");
  }

  await widenCheck(conn, "quiz_questions", "chk_qq_status", "needs_review", "status IN ('draft', 'needs_review', 'published', 'archived')");
  await conn.query("INSERT IGNORE INTO schema_migrations (id) VALUES ('006_progress_research')");
}

const PLACEHOLDER = "[REQUIRES RESEARCHER APPROVAL]";
const SHELLS = [
  {
    key: "shell_digital_attitude",
    title: "Digital Attitude questionnaire (shell)",
    construct: "Digital attitude",
    description:
      "SHELL ONLY. No validated scale has been supplied. Replace every placeholder item with the items the researcher has approved (with their source), set subscales and reverse-scored items, then publish. No cutoffs or interpretation bands are defined.",
  },
  {
    key: "shell_social_engagement",
    title: "Social Engagement questionnaire (shell)",
    construct: "Social engagement",
    description:
      "SHELL ONLY. No validated scale has been supplied. Replace every placeholder item with the items the researcher has approved (with their source), set subscales and reverse-scored items, then publish. No cutoffs or interpretation bands are defined.",
  },
];

async function seedShells(conn) {
  const [admins] = await conn.query("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1");
  const teacherId = admins[0]?.id || null;
  let created = 0;
  for (const s of SHELLS) {
    const [found] = await conn.query("SELECT id FROM research_instruments WHERE seed_key = ?", [s.key]);
    if (found.length) continue;
    const id = crypto.randomUUID();
    await conn.query(
      `INSERT INTO research_instruments (id, seed_key, title, construct, description, scale_min, scale_max, scale_labels_json, status, created_by)
       VALUES (?,?,?,?,?,1,5,?,'draft',?)`,
      [id, s.key, s.title, s.construct, s.description,
        JSON.stringify(["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"]), teacherId]
    );
    for (let i = 1; i <= 4; i += 1) {
      await conn.query(
        `INSERT INTO research_items (id, instrument_id, position, text, subscale, reverse_scored, requires_approval)
         VALUES (?,?,?,?,?,0,1)`,
        [crypto.randomUUID(), id, i, `${PLACEHOLDER} Placeholder item ${i}: replace with an approved item.`, "Subscale to be defined"]
      );
    }
    created += 1;
  }
  console.log(`SEEDED research shells new=${created}`);
}

async function main() {
  if (!process.env.MYSQL_USER) throw new Error("MYSQL_USER is required");
  const backup = backupDatabase("006");
  const conn = await mysql.createConnection(mysqlConfig());
  try {
    await applySchema(conn);
    await seedShells(conn);
    const [m] = await conn.query("SELECT applied_at FROM schema_migrations WHERE id = '006_progress_research'");
    console.log(`MIGRATION 006 applied_at=${m[0]?.applied_at?.toISOString?.() || "missing"} backup=${backup}`);
  } finally {
    await conn.end();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});

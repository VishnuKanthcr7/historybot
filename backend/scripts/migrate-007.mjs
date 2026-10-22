// Applies migration 007 (email-free student accounts) additively after a mysqldump backup.
// Usage: node backend/scripts/migrate-007.mjs   (MYSQL_DATABASE env selects the target DB)
import { backupDatabase, checkClause, columnExists, indexExists, mysql, mysqlConfig } from "./lib/migrate-utils.mjs";

async function main() {
  if (!process.env.MYSQL_USER) throw new Error("MYSQL_USER is required");
  const backup = backupDatabase("007");
  const conn = await mysql.createConnection(mysqlConfig());
  try {
    const [col] = await conn.query(
      "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='email'"
    );
    if (col[0]?.IS_NULLABLE === "NO") {
      await conn.query("ALTER TABLE users MODIFY email VARCHAR(255) NULL");
      console.log("users.email now NULLable (data unchanged)");
    }
    if (!(await columnExists(conn, "users", "roll_number"))) {
      await conn.query("ALTER TABLE users ADD COLUMN roll_number VARCHAR(2) NULL AFTER display_name");
      console.log("ADDED users.roll_number");
    }
    if (!(await columnExists(conn, "users", "cohort_code"))) {
      await conn.query("ALTER TABLE users ADD COLUMN cohort_code VARCHAR(40) NULL AFTER roll_number");
      console.log("ADDED users.cohort_code");
    }
    if (!(await indexExists(conn, "users", "uq_users_cohort_roll"))) {
      await conn.query("ALTER TABLE users ADD UNIQUE KEY uq_users_cohort_roll (cohort_code, roll_number)");
      console.log("ADDED uq_users_cohort_roll");
    }
    if (!(await checkClause(conn, "chk_users_roll"))) {
      await conn.query(
        "ALTER TABLE users ADD CONSTRAINT chk_users_roll CHECK (roll_number IS NULL OR (roll_number REGEXP '^[0-9]{2}$' AND roll_number <> '00'))"
      );
      console.log("ADDED chk_users_roll");
    }
    await conn.query("INSERT IGNORE INTO schema_migrations (id) VALUES ('007_student_roll')");
    const [n] = await conn.query("SELECT role, COUNT(*) n FROM users GROUP BY role");
    console.log("MIGRATION 007 done; users by role:", JSON.stringify(n), "backup=", backup);
  } finally {
    await conn.end();
  }
}
main().catch((err) => { console.error(err.message || err); process.exit(1); });

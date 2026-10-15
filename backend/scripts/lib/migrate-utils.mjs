// Shared helpers for tracked, additive migrations (mysqldump backup first; password only via MYSQL_PWD env).
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
export const mysql = require("mysql2/promise");
const dotenv = require("dotenv");

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
dotenv.config({ path: path.join(root, ".env") });

export function mysqlConfig() {
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

export function backupDatabase(label) {
  const cfg = mysqlConfig();
  const dir = path.join(root, "tmp", "backups");
  fs.mkdirSync(dir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const outfile = path.join(dir, `historybot-pre-${label}-${stamp}.sql`);
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
  return outfile;
}

export async function columnExists(conn, table, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`,
    [table, name]
  );
  return Number(rows[0].n) > 0;
}

export async function indexExists(conn, table, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND INDEX_NAME = ?`,
    [table, name]
  );
  return Number(rows[0].n) > 0;
}

export async function constraintExists(conn, table, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.TABLE_CONSTRAINTS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND CONSTRAINT_NAME = ?`,
    [table, name]
  );
  return Number(rows[0].n) > 0;
}


export async function checkClause(conn, name) {
  const [rows] = await conn.query(
    `SELECT CHECK_CLAUSE AS clause FROM information_schema.CHECK_CONSTRAINTS
     WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = ?`,
    [name]
  );
  return rows.length ? String(rows[0].clause) : null;
}

export function sqlStatements(file) {
  return fs
    .readFileSync(path.join(root, file), "utf8")
    .split("\n")
    .filter((line) => !line.trim().startsWith("--"))
    .join("\n")
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
}

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import crypto from "node:crypto";

const require = createRequire(import.meta.url);
const mysql = require("mysql2/promise");
const dotenv = require("dotenv");

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const manifestPath = path.join(root, "data/extracted/chapter5_image_manifest.json");

async function columnExists(conn, name) {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS n FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'verified_images' AND COLUMN_NAME = ?`,
    [name]
  );
  return Number(rows[0].n) > 0;
}

async function main() {
  const data = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const conn = await mysql.createConnection({
    host: process.env.MYSQL_HOST || "localhost",
    port: Number(process.env.MYSQL_PORT || 3306),
    user: process.env.MYSQL_USER,
    password: process.env.MYSQL_PASSWORD || "",
    database: process.env.MYSQL_DATABASE || "historybot",
  });
  try {
    if (!(await columnExists(conn, "textbook_page_number"))) {
      await conn.query("ALTER TABLE verified_images ADD COLUMN textbook_page_number INT NULL");
      console.log("ADDED textbook_page_number");
    }
    if (!(await columnExists(conn, "alt_text"))) {
      await conn.query("ALTER TABLE verified_images ADD COLUMN alt_text VARCHAR(512) NULL");
      console.log("ADDED alt_text");
    }
    for (const item of data) {
      if (item.verification_status !== "verified") continue;
      const [found] = await conn.query("SELECT id FROM verified_images WHERE file_path = ? LIMIT 1", [
        item.file_path,
      ]);
      if (found.length) {
        await conn.query(
          `UPDATE verified_images SET topic=?, person_name=?, caption=?, source=?, license=?,
            verification_status='verified', verified_by=?, textbook_page_number=?, alt_text=?
           WHERE id=?`,
          [
            item.topic,
            item.person_name || null,
            item.caption || null,
            item.source || null,
            item.license || null,
            item.verified_by || null,
            item.textbook_page || null,
            item.alt_text || null,
            found[0].id,
          ]
        );
      } else {
        await conn.query(
          `INSERT INTO verified_images
            (id, topic, person_name, file_path, caption, source, license, verification_status, verified_by, textbook_page_number, alt_text)
           VALUES (?,?,?,?,?,?,?,'verified',?,?,?)`,
          [
            crypto.randomUUID(),
            item.topic,
            item.person_name || null,
            item.file_path,
            item.caption || null,
            item.source || null,
            item.license || null,
            item.verified_by || null,
            item.textbook_page || null,
            item.alt_text || null,
          ]
        );
      }
    }
    console.log("SEEDED verified_images from manifest");
  } finally {
    await conn.end();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});

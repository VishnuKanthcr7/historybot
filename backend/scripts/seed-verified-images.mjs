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

// Usage: node backend/scripts/seed-verified-images.mjs [--manifest <path>] [--dry-run]
// Default manifest: data/extracted/chapter5_image_manifest.json. A manifest is a JSON array of
// { topic, person_name, file_path: "data/images/<file>", caption, alt_text, source, license,
//   verified_by, textbook_page, media_kind: "image" | "gif", verification_status: "verified" }.
// Only "verified" items are stored. Items are matched by file_path, so re-running is safe.
const args = process.argv.slice(2);
const manifestArg = args.includes("--manifest") ? args[args.indexOf("--manifest") + 1] : "";
const dryRun = args.includes("--dry-run");
const manifestPath = manifestArg
  ? path.resolve(manifestArg)
  : path.join(root, "data/extracted/chapter5_image_manifest.json");
const IMAGE_EXT = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif"]);

// Returns a problem string, or "" when the item can be stored.
export function manifestItemProblem(item) {
  const rel = String(item.file_path || "").replace(/\\/g, "/");
  if (!rel.startsWith("data/images/") || rel.includes("..")) return "file_path must be under data/images/";
  const ext = path.extname(rel).toLowerCase();
  if (!IMAGE_EXT.has(ext)) return `unsupported file type ${ext || "(none)"}`;
  if (!fs.existsSync(path.join(root, rel))) return "file not found";
  if (!item.topic) return "topic is required";
  if (item.external) {
    // Openly licensed image from outside the textbook (e.g. Wikimedia Commons): no textbook
    // page, but the licence and the attribution/source must be recorded.
    if (item.textbook_page != null) return "external images must not carry a textbook_page";
    if (!item.license || !item.source) return "external images need license and source (attribution)";
  } else if (!Number.isFinite(Number(item.textbook_page))) {
    return "textbook_page is required (images are shown only next to answers citing that page)";
  }
  if (item.media_kind && !["image", "gif"].includes(item.media_kind)) return "media_kind must be image or gif";
  return "";
}

function mediaKind(item) {
  if (item.media_kind === "gif" || item.media_kind === "image") return item.media_kind;
  return path.extname(String(item.file_path || "")).toLowerCase() === ".gif" ? "gif" : "image";
}

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
    if (!dryRun && !(await columnExists(conn, "textbook_page_number"))) {
      await conn.query("ALTER TABLE verified_images ADD COLUMN textbook_page_number INT NULL");
      console.log("ADDED textbook_page_number");
    }
    if (!dryRun && !(await columnExists(conn, "alt_text"))) {
      await conn.query("ALTER TABLE verified_images ADD COLUMN alt_text VARCHAR(512) NULL");
      console.log("ADDED alt_text");
    }
    const hasMediaKind = await columnExists(conn, "media_kind");
    let stored = 0;
    let skipped = 0;
    for (const item of data) {
      if (item.verification_status !== "verified") continue;
      const problem = manifestItemProblem(item);
      if (problem) {
        skipped += 1;
        console.log(`SKIP ${item.file_path || "(no file_path)"}: ${problem}`);
        continue;
      }
      stored += 1;
      if (dryRun) {
        console.log(`OK ${item.file_path} (${mediaKind(item)}, page ${item.external ? "none (external)" : item.textbook_page})`);
        continue;
      }
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
      if (hasMediaKind) {
        await conn.query("UPDATE verified_images SET media_kind = ? WHERE file_path = ?", [mediaKind(item), item.file_path]);
      }
    }
    console.log(`${dryRun ? "DRY RUN" : "SEEDED"} verified_images from ${path.relative(root, manifestPath)}: ok=${stored} skipped=${skipped}`);
  } finally {
    await conn.end();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});

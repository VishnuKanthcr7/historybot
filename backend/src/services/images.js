import path from "node:path";
import { fileURLToPath } from "node:url";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../");

export function publicImage(row) {
  return {
    id: row.id,
    topic: row.topic,
    title: row.caption || row.topic,
    alt: row.alt_text || row.caption || row.topic,
    textbook_page_number: row.textbook_page_number,
  };
}

export async function findVerifiedImages(text) {
  const blob = String(text || "").toLowerCase();
  const [rows] = await pool.query(
    `SELECT id, topic, person_name, caption, alt_text, textbook_page_number, file_path
     FROM verified_images WHERE verification_status = 'verified'`
  );
  const matched = [];
  for (const row of rows) {
    if (matchesTopic(blob, row)) {
      matched.push(row);
    }
  }
  return matched;
}

function matchesTopic(blob, row) {
  const topic = String(row.topic || "").toLowerCase();
  const person = String(row.person_name || "").toLowerCase();
  if (topic.includes("panch") || topic.includes("mahal")) {
    return blob.includes("panch") || blob.includes("fatehpur");
  }
  if (topic.includes("kingdom") && person === "akbar") {
    return blob.includes("akbar") && (blob.includes("kingdom") || blob.includes("empire") || blob.includes("map"));
  }
  if (topic.includes("akbar") || person === "akbar") {
    return /\bakbar\b/.test(blob) && !blob.includes("world war");
  }
  if (person === "shivaji" || topic.includes("maratha")) {
    return blob.includes("shivaji") || blob.includes("maratha") || blob.includes("guerilla") || blob.includes("guerrilla");
  }
  return topic && blob.includes(topic);
}

export async function getVerifiedImageRow(id) {
  const [rows] = await pool.query(
    `SELECT id, topic, person_name, caption, alt_text, textbook_page_number, file_path, verification_status
     FROM verified_images WHERE id = ? LIMIT 1`,
    [id]
  );
  if (!rows.length || rows[0].verification_status !== "verified") {
    throw new AppError(404, "NOT_FOUND", "Image not found.");
  }
  return rows[0];
}

export function resolveImagePath(filePath) {
  const relative = String(filePath || "").replace(/\\/g, "/");
  if (!relative.startsWith("data/images/") || relative.includes("..")) {
    throw new AppError(404, "NOT_FOUND", "Image not found.");
  }
  return path.join(ROOT, relative);
}

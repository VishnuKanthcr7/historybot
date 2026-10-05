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

export async function findVerifiedImages(question, answer) {
  const q = String(question || "").toLowerCase();
  const a = String(answer || "").toLowerCase();
  const blob = `${q} ${a}`;
  const [rows] = await pool.query(
    `SELECT id, topic, person_name, caption, alt_text, textbook_page_number, file_path
     FROM verified_images WHERE verification_status = 'verified'`
  );
  const matched = [];
  for (const row of rows) {
    if (matchesTopic(q, a, blob, row)) {
      matched.push(row);
    }
  }
  return matched;
}

function namedPerson(text) {
  if (/\bbaji\s*rao\b|\bbajirao\b/.test(text)) return "bajirao";
  if (/\bshivaji\b/.test(text)) return "shivaji";
  if (/\bbabur\b|\bbabar\b/.test(text)) return "babur";
  if (/\bakbar\b/.test(text)) return "akbar";
  if (/\bshah jahan\b|\bshahjahan\b/.test(text)) return "shahjahan";
  if (/\baurangzeb\b/.test(text)) return "aurangzeb";
  return "";
}

function matchesTopic(question, answer, blob, row) {
  const topic = String(row.topic || "").toLowerCase();
  const person = String(row.person_name || "").toLowerCase();
  const asked = namedPerson(question);
  if (topic.includes("panch") || topic.includes("mahal") || topic.includes("taj")) {
    return /\btaj\b/.test(answer) || /\btaj\b/.test(question);
  }
  if (topic.includes("kingdom") && person === "akbar") {
    return asked === "akbar" && (blob.includes("kingdom") || blob.includes("empire") || blob.includes("map"));
  }
  if (person === "akbar" || topic.includes("akbar")) {
    if (asked && asked !== "akbar") return false;
    return /\bakbar\b/.test(asked ? question : answer) || (/\bmughals?\b/.test(question) && /\bakbar\b/.test(answer));
  }
  if (person === "bajirao" || topic.includes("baji")) {
    if (asked && asked !== "bajirao") return false;
    return /\bbaji\s*rao\b|\bbajirao\b/.test(asked ? question : blob);
  }
  if (person === "shivaji" || topic.includes("maratha")) {
    if (asked && asked !== "shivaji") return false;
    return blob.includes("shivaji") || (/\bmaratha/.test(question) && answer.includes("shivaji"));
  }
  if (person === "babur" || topic.includes("babur") || topic.includes("babar")) {
    if (asked && asked !== "babur") return false;
    return /\bbabur\b|\bbabar\b/.test(asked ? question : blob);
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

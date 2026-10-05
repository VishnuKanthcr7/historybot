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

function sourcePageSet(sourcePages) {
  const pages = new Set();
  for (const item of sourcePages || []) {
    if (item == null) continue;
    if (typeof item === "number" && Number.isFinite(item)) {
      pages.add(item);
      continue;
    }
    if (typeof item === "object") {
      const value = item.printed_page_number ?? item.textbook_page_number ?? item.page;
      const num = Number(value);
      if (Number.isFinite(num)) pages.add(num);
      continue;
    }
    const num = Number(item);
    if (Number.isFinite(num)) pages.add(num);
  }
  return pages;
}

function pageCompatible(imagePage, citedPages) {
  if (!citedPages || citedPages.size === 0) return false;
  const page = Number(imagePage);
  if (!Number.isFinite(page)) return false;
  for (const cited of citedPages) {
    if (Math.abs(cited - page) <= 1) return true;
  }
  return false;
}

export async function findVerifiedImages(question, answer, sourcePages = []) {
  const q = String(question || "").toLowerCase();
  const a = String(answer || "").toLowerCase();
  const blob = `${q} ${a}`;
  const cited = sourcePageSet(sourcePages);
  const [rows] = await pool.query(
    `SELECT id, topic, person_name, caption, alt_text, textbook_page_number, file_path
     FROM verified_images WHERE verification_status = 'verified'`
  );
  const matched = [];
  for (const row of rows) {
    if (!matchesTopic(q, a, blob, row)) continue;
    if (!pageCompatible(row.textbook_page_number, cited)) continue;
    matched.push(row);
  }
  return matched;
}

function namedPerson(text) {
  const value = String(text || "").toLowerCase();
  if (/\bbaji\s*rao\b|\bbajirao\b/.test(value)) return "bajirao";
  if (/\bshivaji\b/.test(value)) return "shivaji";
  if (/\bbabur\b|\bbabar\b/.test(value)) return "babur";
  if (/\bakbar\b/.test(value)) return "akbar";
  if (/\bshah jahan\b|\bshahjahan\b/.test(value)) return "shahjahan";
  if (/\baurangzeb\b/.test(value)) return "aurangzeb";
  return "";
}

function imagePerson(row) {
  const person = String(row.person_name || "").toLowerCase();
  const topic = String(row.topic || "").toLowerCase();
  if (person) return namedPerson(person) || person.replace(/\s+/g, "");
  if (topic.includes("baji")) return "bajirao";
  if (topic.includes("shivaji") || topic.includes("maratha")) return "shivaji";
  if (topic.includes("akbar")) return "akbar";
  if (topic.includes("babur") || topic.includes("babar")) return "babur";
  if (topic.includes("shah")) return "shahjahan";
  if (topic.includes("aurangzeb")) return "aurangzeb";
  return "";
}

function matchesTopic(question, answer, blob, row) {
  const topic = String(row.topic || "").toLowerCase();
  const asked = namedPerson(question) || namedPerson(answer);
  const imgPerson = imagePerson(row);

  if (topic.includes("panch") || topic.includes("mahal") || topic.includes("taj")) {
    return /\btaj\b/.test(answer) || /\btaj\b/.test(question);
  }

  // Strict entity match: if the student asked about a person, image must be that person.
  if (asked) {
    if (!imgPerson || imgPerson !== asked) return false;
    // Require the asked name to appear in the question (preferred) or answer body.
    if (asked === "bajirao") return /\bbaji\s*rao\b|\bbajirao\b/.test(question || blob);
    if (asked === "shivaji") return /\bshivaji\b/.test(question || answer);
    if (asked === "akbar") return /\bakbar\b/.test(question || answer);
    if (asked === "babur") return /\bbabur\b|\bbabar\b/.test(question || answer);
    if (asked === "shahjahan") return /\bshah jahan\b|\bshahjahan\b/.test(question || answer);
    if (asked === "aurangzeb") return /\baurangzeb\b/.test(question || answer);
    return blob.includes(asked);
  }

  // No clear asked person: only attach when image person is explicitly present in answer.
  if (imgPerson === "akbar") return /\bakbar\b/.test(answer);
  if (imgPerson === "bajirao") return /\bbaji\s*rao\b|\bbajirao\b/.test(answer);
  if (imgPerson === "shivaji") return /\bshivaji\b/.test(answer) && !/\bmaratha kingdom map\b/.test(topic);
  if (imgPerson === "babur") return /\bbabur\b|\bbabar\b/.test(answer);
  return Boolean(topic) && blob.includes(topic);
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

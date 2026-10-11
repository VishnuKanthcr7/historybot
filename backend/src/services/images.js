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
    media_kind: row.media_kind === "gif" ? "gif" : "image",
    source: row.source || null,
    license: row.license || null,
    from_textbook: row.textbook_page_number != null,
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

// At most this many images per answer: textbook figures on a cited page first, then
// openly licensed images (no textbook page) that match the topic.
const MAX_IMAGES = 2;

export async function findVerifiedImages(question, answer, sourcePages = [], options = {}) {
  const limit = Number.isFinite(options.limit) ? options.limit : MAX_IMAGES;
  const q = String(question || "").toLowerCase();
  const a = String(answer || "").toLowerCase();
  const blob = `${q} ${a}`;
  const cited = sourcePageSet(sourcePages);
  const [rows] = await pool.query(
    `SELECT id, topic, person_name, caption, alt_text, textbook_page_number, file_path, source, license, media_kind
     FROM verified_images WHERE verification_status = 'verified'
     ORDER BY (textbook_page_number IS NULL), created_at`
  );
  const textbook = [];
  const external = [];
  for (const row of rows) {
    if (!matchesTopic(q, a, blob, row)) continue;
    if (row.textbook_page_number == null) {
      // Openly licensed image with no textbook page: the topic match is enough, so it can
      // accompany a supplementary answer that cites no page.
      external.push(row);
      continue;
    }
    if (!pageCompatible(row.textbook_page_number, cited)) continue;
    textbook.push(row);
  }
  return [...textbook, ...external].slice(0, Math.max(0, limit));
}

const ENTITY_TESTS = [
  ["shershah", /\bsher\s*shah(?:\s*suri)?\b|\bshershah\b/i],
  ["shahjahan", /\bshah\s*jahan\b|\bshahjahan\b/i],
  ["tajmahal", /\btaj\s*mahal\b/i],
  ["humayun", /\bhumayun\b/i],
  ["bajirao", /\bbaji\s*rao\b|\bbajirao\b/i],
  ["shivaji", /\bshivaji\b/i],
  ["babur", /\bbabur\b|\bbabar\b/i],
  ["akbar", /\bakbar\b/i],
  ["aurangzeb", /\baurangzeb\b/i],
];

function mentionedEntities(text) {
  const value = String(text || "");
  return ENTITY_TESTS.filter(([, pattern]) => pattern.test(value)).map(([key]) => key);
}

function imagePerson(row) {
  const fromName = mentionedEntities(row.person_name || "");
  if (fromName.length) return fromName[0];
  const topic = String(row.topic || "").toLowerCase();
  if (topic.includes("panch")) return "";
  if (topic.includes("taj")) return "tajmahal";
  if (topic.includes("humayun")) return "humayun";
  if (topic.includes("sher")) return "shershah";
  if (topic.includes("baji")) return "bajirao";
  if (topic.includes("shivaji") || topic.includes("maratha")) return "shivaji";
  if (topic.includes("akbar")) return "akbar";
  if (topic.includes("babur") || topic.includes("babar")) return "babur";
  if (topic.includes("aurangzeb")) return "aurangzeb";
  if (topic.includes("shah jahan") || topic.includes("shahjahan")) return "shahjahan";
  return "";
}

// A pattern for a person named on an image row that is not in ENTITY_TESTS
// (for example a future asset). Words may be separated by spaces or joined.
function personNamePattern(name) {
  const words = String(name || "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length || words.join("").length < 4) return null;
  const escaped = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`\\b${escaped.join("\\s*")}\\b`, "i");
}

export function imageMatchesTopic(question, answer, row) {
  const topic = String(row.topic || "").toLowerCase();
  const questionEntities = mentionedEntities(question);
  const answerEntities = mentionedEntities(answer);
  const asked = questionEntities.length ? questionEntities : answerEntities;
  const imgPerson = imagePerson(row);
  const haystack = `${question || ""} ${answer || ""}`;

  if (topic.includes("panch")) {
    return /\bpanch\b|\bfatehpur\b/i.test(haystack);
  }
  const otherPerson = !imgPerson && row.person_name ? personNamePattern(row.person_name) : null;
  if (otherPerson) {
    // A person outside the built-in list: show only when the question names them,
    // or, when the question names nobody known, when the answer does.
    if (otherPerson.test(question || "")) return true;
    if (questionEntities.length) return false;
    return otherPerson.test(answer || "");
  }
  if (asked.length) {
    return Boolean(imgPerson) && asked.includes(imgPerson);
  }
  if (imgPerson) return answerEntities.includes(imgPerson);
  return Boolean(topic) && topic.length > 3 && haystack.toLowerCase().includes(topic);
}

function matchesTopic(question, answer, _blob, row) {
  return imageMatchesTopic(question, answer, row);
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

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

// At most this many images per answer.
const MAX_IMAGES = 2;

const MAP_Q = /\bmaps?\b|\bkingdom\b|\bempire\b|\bterritor|\bexpan|\bborders?\b|\bextent\b|\bconquest|\bregions?\b/i;
const PLACE_Q = /\bforts?\b|\bpalace|\btomb|\bmahal\b|\bdarwaza\b|\bgateway|\bmonument|\bmosque|\bbattle\s*(?:field|site)?\b|\bfatehpur\b|\bsikri\b|\braigad\b|\bcapital city\b|\bbuilding/i;
const PERSON_Q = /^\s*(?:who\s+(?:was|were|is)|tell\s+me\s+about|about|describe|introduce|life\s+of|biography\s+of)\b/i;

// What the question is mainly about: "person", "map", "place" or "general".
export function classifyImageQuestion(question) {
  const q = String(question || "");
  if (/^\s*who\s+(?:was|were|is)\b/i.test(q)) return "person";
  if (MAP_Q.test(q)) return "map";
  if (PLACE_Q.test(q)) return "place";
  if (PERSON_Q.test(q) && mentionedEntities(q).length) return "person";
  return "general";
}

// What an image shows: "portrait" (a painting/figure of a person), "map" or "place".
export function imageKind(row) {
  const text = `${row.caption || ""} ${row.topic || ""} ${row.file_path || ""}`.toLowerCase();
  if (/\bmap\b|-map\b/.test(text)) return "map";
  if (/portrait|painting|miniature|depiction/.test(text)) return "portrait";
  return "place";
}

// The question itself names what a textbook figure shows, so the figure may be used even
// when the answer cites a different page (e.g. "Who was Akbar?" answered from pp. 7-10
// can still show the Akbar figure from p. 3).
function questionNamesFigure(question, row, kind, qKind) {
  const q = String(question || "");
  const person = imagePerson(row);
  const asked = mentionedEntities(q);
  if (kind === "portrait") return qKind === "person" && Boolean(person) && asked.includes(person);
  if (kind === "map") return Boolean(person) && asked.includes(person) && MAP_Q.test(q);
  if (String(row.topic || "").toLowerCase().includes("panch")) return /\bpanch\b/i.test(q);
  return false;
}

const KIND_ORDER = {
  person: ["portrait", "map", "place"],
  map: ["map", "place", "portrait"],
  place: ["place", "map", "portrait"],
};

export function selectImages(question, answer, rows, sourcePages = [], limit = MAX_IMAGES) {
  const cited = sourcePageSet(sourcePages);
  const qKind = classifyImageQuestion(question);
  const candidates = [];
  for (const row of rows) {
    if (!imageMatchesTopic(question, answer, row)) continue;
    const kind = imageKind(row);
    const textbook = row.textbook_page_number != null;
    // Textbook figures: on (or next to) a cited page, or named by the question itself.
    if (textbook && !pageCompatible(row.textbook_page_number, cited) && !questionNamesFigure(question, row, kind, qKind)) {
      continue;
    }
    candidates.push({ row, kind, textbook });
  }
  const order = KIND_ORDER[qKind];
  const rank = (c) => (order ? order.indexOf(c.kind) * 2 : 0) + (c.textbook ? 0 : 1);
  candidates.sort((x, y) => rank(x) - rank(y));
  const picked = [];
  let portraits = 0;
  for (const c of candidates) {
    if (picked.length >= Math.max(0, limit)) break;
    if (c.kind === "portrait") {
      // A portrait only for a person question about that exact person, and only one.
      if (qKind === "person" && portraits === 0) {
        const asked = mentionedEntities(question);
        if (!asked.length || asked.includes(imagePerson(c.row))) {
          picked.push(c.row);
          portraits += 1;
        }
      } else if (qKind === "general" && portraits === 0) {
        picked.push(c.row);
        portraits += 1;
      }
      continue;
    }
    picked.push(c.row);
  }
  return picked;
}

export async function findVerifiedImages(question, answer, sourcePages = [], options = {}) {
  const limit = Number.isFinite(options.limit) ? options.limit : MAX_IMAGES;
  const [rows] = await pool.query(
    `SELECT id, topic, person_name, caption, alt_text, textbook_page_number, file_path, source, license, media_kind
     FROM verified_images WHERE verification_status = 'verified'
     ORDER BY (textbook_page_number IS NULL), created_at`
  );
  return selectImages(question, answer, rows, sourcePages, limit);
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

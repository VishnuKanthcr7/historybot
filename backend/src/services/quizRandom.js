// Per-attempt randomisation, decided on the server and stored on the attempt (question_order_json), so a
// reload or resume shows the same layout and scoring never depends on display order.
//  - Every attempt uses all questions of the same published quiz (the pool), each exactly once.
//  - Options are shuffled by their stable ids; answer keys reference ids, so the mapping is untouched.
//  - Pre/post tests are NOT randomised: both keep the teacher's fixed order so the two forms stay equivalent.
// Seeds are stored, and the PRNG is deterministic, so tests can reproduce any layout.
import crypto from "node:crypto";

function hashSeed(seed) {
  const h = crypto.createHash("sha256").update(String(seed)).digest();
  return h.readUInt32LE(0);
}

// mulberry32
export function rng(seed) {
  let a = hashSeed(seed);
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffle(list, rand) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function shouldRandomize(quiz) {
  return !(quiz.assessment_phase === "pre" || quiz.assessment_phase === "post");
}

const parse = (v) => {
  if (v == null) return null;
  if (typeof v === "object") return v;
  try {
    return JSON.parse(v);
  } catch {
    return null;
  }
};

// items: quiz items (with id, qtype, options_json). Returns the JSON stored on the attempt.
export function buildLayout(items, quiz, seed = crypto.randomUUID()) {
  const ids = items.map((q) => q.id);
  if (!shouldRandomize(quiz)) return { v: 2, seed: null, order: ids, options: {} };
  const rand = rng(seed);
  const options = {};
  for (const q of items) {
    const o = parse(q.options_json);
    if (q.qtype === "mcq" && Array.isArray(o)) options[q.id] = shuffle(o.map((x) => x.id), rand);
    else if (q.qtype === "order" && Array.isArray(o)) options[q.id] = shuffle(o.map((x) => x.id), rand);
    else if (q.qtype === "match" && o?.right) options[q.id] = shuffle(o.right.map((x) => x.id), rand);
  }
  return { v: 2, seed, order: shuffle(ids, rand), options };
}

// Legacy attempts stored a plain array of question ids.
export function layoutOf(attempt) {
  const v = parse(attempt.question_order_json);
  if (Array.isArray(v)) return { order: v, options: {} };
  return { order: Array.isArray(v?.order) ? v.order : [], options: v?.options || {} };
}

export const orderIds = (attempt) => layoutOf(attempt).order;

// Reorders a public question's options by the stored option-id order (unknown ids keep their place at the end).
export function applyOptionOrder(question, optionIds) {
  if (!optionIds?.length || !question.options) return question;
  const rank = new Map(optionIds.map((id, i) => [id, i]));
  const sort = (arr) => [...arr].sort((x, y) => (rank.get(x.id) ?? 999) - (rank.get(y.id) ?? 999));
  if (Array.isArray(question.options)) return { ...question, options: sort(question.options) };
  if (question.options.right) return { ...question, options: { ...question.options, right: sort(question.options.right) } };
  return question;
}

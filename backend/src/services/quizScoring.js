// Server-side grading. Pure functions: no database, no network. The client never sends scores.

export const QUESTION_TYPES = ["mcq", "true_false", "match", "order", "fill_blank"];

function parseJson(value, fallback = null) {
  if (value == null) return fallback;
  if (typeof value !== "string") return value;
  // mysql2 already decodes JSON columns, so a plain string here is usually a decoded JSON string ("b").
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

export function normalizeText(value) {
  return String(value ?? "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

// Returns { correct, fraction } for one question. Invalid or empty responses score 0.
export function gradeQuestion(question, response) {
  const answer = parseJson(question.answer_json ?? question.answer);
  const options = parseJson(question.options_json ?? question.options);
  switch (question.qtype) {
    case "mcq": {
      const valid = Array.isArray(options) && options.some((o) => o.id === response);
      const correct = valid && response === answer;
      return { correct, fraction: correct ? 1 : 0 };
    }
    case "true_false": {
      if (typeof response !== "boolean") return { correct: false, fraction: 0 };
      const correct = response === Boolean(answer);
      return { correct, fraction: correct ? 1 : 0 };
    }
    case "fill_blank": {
      const accepted = (Array.isArray(answer) ? answer : [answer]).map(normalizeText).filter(Boolean);
      const given = normalizeText(typeof response === "string" ? response.slice(0, 200) : "");
      const correct = Boolean(given) && accepted.includes(given);
      return { correct, fraction: correct ? 1 : 0 };
    }
    case "order": {
      const key = Array.isArray(answer) ? answer : [];
      if (!Array.isArray(response) || response.length !== key.length) return { correct: false, fraction: 0 };
      const correct = key.every((id, i) => response[i] === id);
      return { correct, fraction: correct ? 1 : 0 };
    }
    case "match": {
      const key = answer && typeof answer === "object" ? answer : {};
      const lefts = Object.keys(key);
      if (!lefts.length || !response || typeof response !== "object" || Array.isArray(response)) {
        return { correct: false, fraction: 0 };
      }
      // Each right-hand item may be used once; reusing one does not earn extra credit.
      const used = new Set();
      let right = 0;
      for (const left of lefts) {
        const pick = response[left];
        if (typeof pick !== "string" || used.has(pick)) continue;
        used.add(pick);
        if (pick === key[left]) right += 1;
      }
      const fraction = right / lefts.length;
      return { correct: right === lefts.length, fraction };
    }
    default:
      return { correct: false, fraction: 0 };
  }
}

// items: [{ question, points }], responses: { [questionId]: response }
export function scoreAttempt(items, responses) {
  const safe = responses && typeof responses === "object" && !Array.isArray(responses) ? responses : {};
  let score = 0;
  let max = 0;
  const answers = [];
  for (const { question, points } of items) {
    const weight = Number(points) || 1;
    const has = Object.prototype.hasOwnProperty.call(safe, question.id);
    const response = has ? safe[question.id] : null;
    const { correct, fraction } = has ? gradeQuestion(question, response) : { correct: false, fraction: 0 };
    const earned = Math.round(weight * fraction * 100) / 100;
    score += earned;
    max += weight;
    answers.push({ questionId: question.id, response, correct, points: earned, maxPoints: weight });
  }
  const percent = max > 0 ? Math.round((score / max) * 10000) / 100 : 0;
  return { score: Math.round(score * 100) / 100, max, percent, answers };
}

// What a student may see before submitting: no answer key, no explanation.
export function studentQuestion(question) {
  const options = parseJson(question.options_json);
  return {
    id: question.id,
    qtype: question.qtype,
    prompt: question.prompt,
    options: question.qtype === "true_false" ? null : options,
    topic: question.topic,
    difficulty: question.difficulty,
  };
}

// Feedback after submission (only when the reveal setting allows it).
export function revealedQuestion(question) {
  return {
    ...studentQuestion(question),
    answer: parseJson(question.answer_json),
    explanation: question.explanation || "",
    textbook_page: question.textbook_page,
    source_document: question.source_document,
  };
}

// Only keep responses for questions in the attempt; trim strings; drop anything else.
export function sanitizeResponses(raw, allowedIds) {
  const out = {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  const allowed = new Set(allowedIds);
  for (const [key, value] of Object.entries(raw)) {
    if (!allowed.has(key)) continue;
    if (typeof value === "string") out[key] = value.slice(0, 200);
    else if (typeof value === "boolean") out[key] = value;
    else if (Array.isArray(value)) out[key] = value.slice(0, 20).map((v) => String(v).slice(0, 40));
    else if (value && typeof value === "object") {
      const obj = {};
      for (const [k, v] of Object.entries(value).slice(0, 20)) obj[String(k).slice(0, 40)] = String(v).slice(0, 40);
      out[key] = obj;
    }
  }
  return out;
}

export function median(values) {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const mid = Math.floor(v.length / 2);
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

export function mean(values) {
  const v = values.filter((x) => Number.isFinite(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

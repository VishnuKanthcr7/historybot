import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { isUuid } from "../utils/ids.js";

export const LATE_GRACE_MS = 30 * 1000;
export const ACTIVITY_TYPES = [
  "quiz",
  "history_challenge",
  "beat_the_clock",
  "timeline",
  "match_figure",
  "find_correct",
  "revision",
  "checkpoint",
];

export function requireUuid(value, what = "id") {
  if (!isUuid(value)) throw new AppError(400, "VALIDATION_ERROR", `Invalid ${what}.`);
  return value;
}

export async function getQuiz(id, conn = pool) {
  requireUuid(id, "quiz id");
  const [rows] = await conn.query("SELECT * FROM quizzes WHERE id = ?", [id]);
  if (!rows.length) throw new AppError(404, "NOT_FOUND", "Quiz not found.");
  return rows[0];
}

export async function getQuizItems(quizId, conn = pool) {
  const [rows] = await conn.query(
    `SELECT q.*, i.position, i.points FROM quiz_items i JOIN quiz_questions q ON q.id = i.question_id
     WHERE i.quiz_id = ? ORDER BY i.position`,
    [quizId]
  );
  return rows;
}

export function quizIsOpen(quiz, now = new Date()) {
  if (quiz.status !== "published") return false;
  if (quiz.available_from && new Date(quiz.available_from) > now) return false;
  if (quiz.available_until && new Date(quiz.available_until) < now) return false;
  return true;
}

export function quizIsClosed(quiz, now = new Date()) {
  return quiz.status === "archived" || Boolean(quiz.available_until && new Date(quiz.available_until) < now);
}

// May this student see the quiz at all? Personal quizzes belong to one student only.
export function studentCanSee(quiz, user) {
  if (!user) return false;
  if (quiz.owner_user_id && quiz.owner_user_id !== user.id) return false;
  return quiz.status === "published";
}

// Answer keys, explanations and per-question correctness after submission.
export function revealAllowed(quiz, now = new Date()) {
  if (quiz.mode === "practice") return quiz.reveal_answers !== "never";
  if (quiz.reveal_answers === "after_submit") return true;
  if (quiz.reveal_answers === "after_close") return quizIsClosed(quiz, now);
  return false;
}

export function publicQuiz(quiz) {
  return {
    id: quiz.id,
    title: quiz.title,
    description: quiz.description,
    topic: quiz.topic,
    difficulty: quiz.difficulty,
    mode: quiz.mode,
    activity_type: quiz.activity_type,
    assessment_phase: quiz.assessment_phase,
    time_limit_sec: quiz.time_limit_sec,
    max_attempts: quiz.max_attempts,
    reveal_answers: quiz.reveal_answers,
    available_from: quiz.available_from,
    available_until: quiz.available_until,
    status: quiz.status,
    personal: Boolean(quiz.owner_user_id),
  };
}

export function parseJson(value, fallback = null) {
  if (value == null) return fallback;
  if (typeof value !== "string") return value;
  // mysql2 already decodes JSON columns, so a plain string here is usually a decoded JSON string ("b").
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

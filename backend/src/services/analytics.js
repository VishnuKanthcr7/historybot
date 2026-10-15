import { newId } from "../utils/ids.js";
import { pool } from "../db/pool.js";

// Session-level learning events (chat, modules, PDFs). userId attributes the event to the signed-in account.
// idempotencyKey (optional) makes a retried or refreshed request record the event once only.
export async function recordEvent({ sessionId, conversationId, userId, eventType, topicText, language, metadata, idempotencyKey }) {
  await pool.query(
    `INSERT INTO analytics_events
      (id, session_id, conversation_id, user_id, event_type, topic_text, language, metadata_json, idempotency_key)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE id = id`,
    [
      newId(),
      sessionId || null,
      conversationId || null,
      userId || null,
      eventType,
      topicText ? String(topicText).slice(0, 255) : null,
      language || null,
      metadata ? JSON.stringify(metadata) : null,
      idempotencyKey ? String(idempotencyKey).slice(0, 120) : null,
    ]
  );
}

// Learner events (accounts, quizzes, activities, modules, questionnaires): user id, ids and scores only (never chat text).
// A failure to record an event never breaks the student's request. A repeated idempotencyKey is ignored.
export async function recordUserEvent(userId, eventType, metadata, idempotencyKey = null) {
  try {
    await pool.query(
      `INSERT INTO analytics_events (id, user_id, event_type, metadata_json, idempotency_key) VALUES (?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE id = id`,
      [newId(), userId, eventType, metadata ? JSON.stringify(metadata) : null, idempotencyKey ? String(idempotencyKey).slice(0, 120) : null]
    );
  } catch (err) {
    console.warn("analytics_event_failed", err?.code || "error");
  }
}

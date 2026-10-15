import { newId } from "../utils/ids.js";
import { pool } from "../db/pool.js";

export async function recordEvent({ sessionId, conversationId, eventType, topicText, language, metadata }) {
  await pool.query(
    `INSERT INTO analytics_events
      (id, session_id, conversation_id, event_type, topic_text, language, metadata_json)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      newId(),
      sessionId || null,
      conversationId || null,
      eventType,
      topicText ? String(topicText).slice(0, 255) : null,
      language || null,
      metadata ? JSON.stringify(metadata) : null,
    ]
  );
}

// Learner events for quizzes and activities: user id, ids and scores only (never chat text).
// A failure to record an event never breaks the student's request.
export async function recordUserEvent(userId, eventType, metadata) {
  try {
    await pool.query(
      `INSERT INTO analytics_events (id, user_id, event_type, metadata_json) VALUES (?, ?, ?, ?)`,
      [newId(), userId, eventType, metadata ? JSON.stringify(metadata) : null]
    );
  } catch (err) {
    console.warn("analytics_event_failed", err?.code || "error");
  }
}

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

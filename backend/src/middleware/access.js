import { AppError } from "../utils/errors.js";
import { isUuid } from "../utils/ids.js";
import { pool } from "../db/pool.js";

export async function requireSession(sessionId, actor = null) {
  if (!actor) {
    throw new AppError(401, "UNAUTHENTICATED", "Please log in again.");
  }
  if (!isUuid(sessionId)) {
    throw new AppError(400, "VALIDATION_ERROR", "Invalid session_id.");
  }
  const [rows] = await pool.query(
    "SELECT id, created_at, language, user_id FROM anonymous_sessions WHERE id = ?",
    [sessionId]
  );
  if (!rows.length) {
    throw new AppError(404, "SESSION_NOT_FOUND", "Session not found.");
  }
  if (!rows[0].user_id || rows[0].user_id !== actor.id) {
    throw new AppError(403, "FORBIDDEN", "Session does not belong to this account.");
  }
  return rows[0];
}

export async function requireOwnedConversation(conversationId, sessionId, actor = null) {
  if (!isUuid(conversationId)) {
    throw new AppError(400, "VALIDATION_ERROR", "Invalid conversation_id.");
  }
  const session = await requireSession(sessionId, actor);
  const [rows] = await pool.query(
    "SELECT id, session_id, title, created_at, updated_at FROM conversations WHERE id = ?",
    [conversationId]
  );
  if (!rows.length) {
    throw new AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.");
  }
  if (rows[0].session_id !== session.id) {
    throw new AppError(403, "FORBIDDEN", "Conversation does not belong to this session.");
  }
  return { session, conversation: rows[0] };
}

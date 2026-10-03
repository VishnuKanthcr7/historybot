import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { newId, utcNow } from "../utils/ids.js";
import { requireOwnedConversation, requireSession } from "../middleware/access.js";
import { recordEvent } from "../services/analytics.js";
import { queryRag } from "../services/ragClient.js";
import { config } from "../config/env.js";

const createSchema = z.object({
  session_id: z.string().uuid(),
  title: z.string().max(255).optional(),
});

const messageSchema = z.object({
  session_id: z.string().uuid(),
  message: z.string().trim().min(1).max(config.maxMessageChars),
  language: z.enum(["en", "kn"]).optional(),
});

export async function createConversation(req, res, next) {
  try {
    const body = createSchema.parse(req.body);
    await requireSession(body.session_id);
    const id = newId();
    const title = body.title?.trim() || "New chat";
    await pool.query(
      "INSERT INTO conversations (id, session_id, title) VALUES (?, ?, ?)",
      [id, body.session_id, title]
    );
    await recordEvent({
      sessionId: body.session_id,
      conversationId: id,
      eventType: "NEW_CHAT",
    });
    res.status(201).json({
      conversation_id: id,
      title,
      created_at: utcNow(),
    });
  } catch (err) {
    next(err);
  }
}

export async function getConversation(req, res, next) {
  try {
    const sessionId = req.query.session_id || req.get("x-session-id");
    if (!sessionId) {
      throw new AppError(400, "VALIDATION_ERROR", "session_id is required.");
    }
    const { conversation } = await requireOwnedConversation(req.params.conversationId, sessionId);
    const [messages] = await pool.query(
      `SELECT id, role, content, language, source_pages, retrieval_ok, created_at
       FROM messages WHERE conversation_id = ? ORDER BY created_at ASC`,
      [conversation.id]
    );
    res.json({
      conversation_id: conversation.id,
      title: conversation.title,
      created_at: conversation.created_at,
      messages: messages.map((row) => ({
        id: row.id,
        role: row.role,
        content: row.content,
        language: row.language,
        grounded: row.retrieval_ok === null ? null : Boolean(row.retrieval_ok),
        sources: parseSources(row.source_pages),
        created_at: row.created_at,
      })),
    });
  } catch (err) {
    next(err);
  }
}

export async function postMessage(req, res, next) {
  try {
    const body = messageSchema.parse(req.body);
    const { conversation } = await requireOwnedConversation(req.params.conversationId, body.session_id);
    const language = body.language || "en";
    const userId = newId();
    await pool.query(
      `UPDATE anonymous_sessions SET last_seen_at = UTC_TIMESTAMP(3), language = ? WHERE id = ?`,
      [language, body.session_id]
    );
    await pool.query(
      `INSERT INTO messages (id, conversation_id, role, content, language) VALUES (?, ?, 'user', ?, ?)`,
      [userId, conversation.id, body.message, language]
    );
    await pool.query(
      `UPDATE conversations SET updated_at = UTC_TIMESTAMP(3) WHERE id = ?`,
      [conversation.id]
    );
    await recordEvent({
      sessionId: body.session_id,
      conversationId: conversation.id,
      eventType: "QUESTION_ASKED",
      topicText: body.message,
      language,
    });

    const history = await loadHistory(conversation.id, userId);
    const rag = await queryRag({
      question: body.message,
      language,
      conversationHistory: history,
    });

    const assistantId = newId();
    const publicSources = (rag.sources || [])
      .filter((item) => item && item.textbook_page_number != null)
      .map((item) => ({ textbook_page_number: item.textbook_page_number }));
    const chunkIds = (rag.sources || []).map((item) => item.chunk_id).filter(Boolean);

    await pool.query(
      `INSERT INTO messages
        (id, conversation_id, role, content, language, source_pages, chunk_ids, retrieval_ok)
       VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)`,
      [
        assistantId,
        conversation.id,
        rag.answer,
        rag.language,
        JSON.stringify(publicSources),
        JSON.stringify(chunkIds),
        rag.grounded ? 1 : 0,
      ]
    );
    await recordEvent({
      sessionId: body.session_id,
      conversationId: conversation.id,
      eventType: "ANSWER_GENERATED",
      topicText: body.message,
      language: rag.language,
      metadata: { grounded: rag.grounded },
    });

    res.status(201).json({
      message: {
        id: assistantId,
        role: "assistant",
        content: rag.answer,
        language: rag.language,
        grounded: rag.grounded,
        sources: publicSources,
        created_at: utcNow(),
      },
    });
  } catch (err) {
    next(err);
  }
}

async function loadHistory(conversationId, excludeUserId) {
  const [rows] = await pool.query(
    `SELECT id, role, content FROM messages
     WHERE conversation_id = ? AND id <> ?
     ORDER BY created_at DESC
     LIMIT 16`,
    [conversationId, excludeUserId]
  );
  const chronological = rows.reverse();
  const users = chronological.filter((row) => row.role === "user").slice(-4);
  const assistants = chronological.filter((row) => row.role === "assistant").slice(-4);
  const allowed = new Set([...users, ...assistants].map((row) => row.id));
  return chronological
    .filter((row) => allowed.has(row.id))
    .map((row) => ({
      role: row.role,
      content: String(row.content || "").slice(0, 2000),
    }));
}

function parseSources(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value;
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { newId, utcNow } from "../utils/ids.js";
import { requireOwnedConversation, requireSession } from "../middleware/access.js";
import { recordEvent } from "../services/analytics.js";
import { queryRag } from "../services/ragClient.js";
import { findVerifiedImages, publicImage } from "../services/images.js";
import { publicSources } from "../utils/sources.js";
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

export async function listConversations(req, res, next) {
  try {
    const sessionId = req.query.session_id;
    if (!sessionId) {
      throw new AppError(400, "VALIDATION_ERROR", "session_id is required.");
    }
    await requireSession(sessionId);
    const [rows] = await pool.query(
      `SELECT id, title, created_at, updated_at
       FROM conversations
       WHERE session_id = ?
       ORDER BY updated_at DESC`,
      [sessionId]
    );
    res.json({
      conversations: rows.map((row) => ({
        conversation_id: row.id,
        title: row.title,
        created_at: row.created_at,
        updated_at: row.updated_at,
      })),
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
    const mapped = [];
    for (const row of messages) {
      const sources = parseSources(row.source_pages);
      let images = [];
      if (row.role === "assistant" && row.retrieval_ok) {
        images = (await findVerifiedImages(row.content)).map(publicImage);
      }
      mapped.push({
        id: row.id,
        role: row.role,
        content: row.content,
        language: row.language,
        grounded: row.retrieval_ok === null ? null : Boolean(row.retrieval_ok),
        sources,
        images,
        created_at: row.created_at,
      });
    }
    res.json({
      conversation_id: conversation.id,
      title: conversation.title,
      created_at: conversation.created_at,
      messages: mapped,
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

    const { history, taskState } = await loadHistory(conversation.id, userId);
    if (!conversation.title || /^new chat$/i.test(conversation.title) || conversation.title === "ಹೊಸ ಚಾಟ್") {
      await pool.query("UPDATE conversations SET title = ?, updated_at = UTC_TIMESTAMP(3) WHERE id = ?", [
        body.message.slice(0, 80),
        conversation.id,
      ]);
    }
    const rag = await queryRag({
      question: body.message,
      language,
      conversationHistory: history,
      taskState,
    });

    const assistantId = newId();
    const publicSourceList = publicSources(rag.sources);
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
        JSON.stringify(publicSourceList),
        encodeChunkIds(chunkIds, rag.task),
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

    const imageRows = rag.grounded
      ? await findVerifiedImages(body.message, rag.answer || "")
      : [];

    res.status(201).json({
      message: {
        id: assistantId,
        role: "assistant",
        content: rag.answer,
        language: rag.language,
        grounded: rag.grounded,
        sources: publicSourceList,
        images: imageRows.map(publicImage),
        created_at: utcNow(),
      },
    });
  } catch (err) {
    next(err);
  }
}

async function loadHistory(conversationId, excludeUserId) {
  const [rows] = await pool.query(
    `SELECT id, role, content, chunk_ids FROM messages
     WHERE conversation_id = ? AND id <> ?
     ORDER BY created_at DESC
     LIMIT 16`,
    [conversationId, excludeUserId]
  );
  const chronological = rows.reverse();
  const users = chronological.filter((row) => row.role === "user").slice(-4);
  const assistants = chronological.filter((row) => row.role === "assistant").slice(-4);
  const allowed = new Set([...users, ...assistants].map((row) => row.id));
  const kept = chronological.filter((row) => allowed.has(row.id));
  const taskState = collectTaskState(kept);
  const history = kept.map((row) => {
    const task = decodeTask(row.chunk_ids);
    const raw = String(row.content || "");
    return {
      role: row.role,
      content: task?.type === "MCQ" ? raw : raw.slice(0, 2000),
      ...(task ? { task_state: task } : {}),
    };
  });
  return { history, taskState };
}

function encodeChunkIds(ids, task) {
  if (!task || typeof task !== "object") {
    return JSON.stringify(ids || []);
  }
  return JSON.stringify({
    historybot_task: true,
    ids: ids || [],
    type: task.type || null,
    topic: task.topic || null,
    entity: task.entity || null,
    count: task.count ?? null,
    fingerprints: Array.isArray(task.fingerprints) ? task.fingerprints.slice(0, 80) : [],
    generation_index: task.generation_index ?? null,
  });
}

function decodeTask(value) {
  if (!value) {
    return null;
  }
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!parsed || Array.isArray(parsed) || !parsed.historybot_task) {
    return null;
  }
  return {
    type: parsed.type || null,
    topic: parsed.topic || null,
    entity: parsed.entity || null,
    count: parsed.count ?? null,
    fingerprints: Array.isArray(parsed.fingerprints) ? parsed.fingerprints : [],
    generation_index: parsed.generation_index ?? null,
  };
}

function collectTaskState(rows) {
  const fingerprints = [];
  let last = null;
  for (const row of rows) {
    const task = decodeTask(row.chunk_ids);
    if (!task) {
      continue;
    }
    last = task;
    fingerprints.push(...(task.fingerprints || []));
  }
  if (!last) {
    return null;
  }
  const unique = [];
  const seen = new Set();
  for (const item of fingerprints) {
    if (item && !seen.has(item)) {
      seen.add(item);
      unique.push(item);
    }
  }
  return { ...last, fingerprints: unique };
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

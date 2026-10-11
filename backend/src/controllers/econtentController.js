import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { isUuid, newId, utcNow } from "../utils/ids.js";
import { requireOwnedConversation, requireSession } from "../middleware/access.js";
import { recordEvent } from "../services/analytics.js";
import { generateEcontent, renderEcontentPdf } from "../services/ragClient.js";
import { findVerifiedImages, publicImage } from "../services/images.js";
import { publicSources } from "../utils/sources.js";

const createSchema = z.object({
  session_id: z.string().uuid(),
  conversation_id: z.string().uuid().optional(),
  topic: z.string().trim().min(1).max(255),
  language: z.enum(["en", "kn"]).optional(),
});

const pdfSchema = z.object({
  session_id: z.string().uuid(),
});

export async function createEcontent(req, res, next) {
  try {
    const body = createSchema.parse(req.body);
    await requireSession(body.session_id, req.user);
    if (body.conversation_id) {
      await requireOwnedConversation(body.conversation_id, body.session_id, req.user);
    }
    const language = body.language || "en";
    const rag = await generateEcontent({ topic: body.topic, language });
    if (!rag.grounded || !rag.content) {
      return res.status(200).json({
        id: null,
        grounded: false,
        message: rag.message || "This topic is not available in the textbook.",
        title: null,
        language,
        content: null,
        sources: [],
        images: [],
      });
    }
    const id = newId();
    const publicSourceList = publicSources(rag.sources);
    const imageRows = await findVerifiedImages(body.topic, rag.title || "", publicSourceList, { limit: 3 });
    await pool.query(
      `INSERT INTO econtent_documents
        (id, session_id, conversation_id, topic, language, body_json, source_pages)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        id,
        body.session_id,
        body.conversation_id || null,
        body.topic,
        language,
        JSON.stringify({
          title: rag.title,
          content: rag.content,
          images: imageRows.map(publicImage),
        }),
        JSON.stringify(publicSourceList),
      ]
    );
    await recordEvent({
      sessionId: body.session_id,
      conversationId: body.conversation_id || null,
      eventType: "E_CONTENT_GENERATED",
      topicText: body.topic,
      language,
    });
    res.status(201).json({
      id,
      grounded: true,
      title: rag.title,
      language,
      content: rag.content,
      sources: publicSourceList,
      images: imageRows.map(publicImage),
      created_at: utcNow(),
    });
  } catch (err) {
    next(err);
  }
}

export async function getEcontent(req, res, next) {
  try {
    const sessionId = req.query.session_id;
    const doc = await requireOwnedEcontent(req.params.econtentId, sessionId, req.user);
    const body = parseJson(doc.body_json);
    res.json({
      id: doc.id,
      title: body.title || doc.topic,
      language: doc.language,
      content: body.content || null,
      sources: parseJson(doc.source_pages) || [],
      images: body.images || [],
      created_at: doc.created_at,
    });
  } catch (err) {
    next(err);
  }
}

export async function downloadEcontentPdf(req, res, next) {
  try {
    const body = pdfSchema.parse(req.body);
    const doc = await requireOwnedEcontent(req.params.econtentId, body.session_id, req.user);
    const stored = parseJson(doc.body_json);
    const imageRows = await findVerifiedImages(
      doc.topic,
      stored.title || "",
      parseJson(doc.source_pages) || [],
      { limit: 3 }
    );
    const pdf = await renderEcontentPdf(
      {
        title: stored.title || doc.topic,
        language: doc.language,
        content: stored.content || {},
        sources: parseJson(doc.source_pages) || [],
      },
      imageRows
    );
    await recordEvent({
      sessionId: body.session_id,
      conversationId: doc.conversation_id,
      eventType: "PDF_DOWNLOADED",
      topicText: doc.topic,
      language: doc.language,
    });
    const safeName = String(stored.title || doc.topic || "historybot")
      .replace(/[^\w\u0C80-\u0CFF-]+/g, "-")
      .slice(0, 40);
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="${safeName || "historybot"}.pdf"`);
    res.send(pdf);
  } catch (err) {
    next(err);
  }
}

async function requireOwnedEcontent(econtentId, sessionId, actor = null) {
  const session = await requireSession(sessionId, actor);
  if (!isUuid(econtentId)) {
    throw new AppError(400, "VALIDATION_ERROR", "Invalid e-content id.");
  }
  const [rows] = await pool.query(
    `SELECT id, session_id, conversation_id, topic, language, body_json, source_pages, created_at
     FROM econtent_documents WHERE id = ?`,
    [econtentId]
  );
  if (!rows.length) {
    throw new AppError(404, "NOT_FOUND", "E-content not found.");
  }
  if (rows[0].session_id !== session.id) {
    throw new AppError(403, "FORBIDDEN", "E-content does not belong to this session.");
  }
  return rows[0];
}

function parseJson(value) {
  if (!value) return null;
  if (typeof value === "object") return value;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

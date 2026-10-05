import { AppError } from "../utils/errors.js";
import { config } from "../config/env.js";

async function ragFetch(path, body, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${config.rag.url}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": config.rag.secret,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (path.endsWith("/pdf")) {
      if (!response.ok) {
        throw new AppError(502, "RAG_UNAVAILABLE", "PDF service is unavailable.");
      }
      return Buffer.from(await response.arrayBuffer());
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new AppError(502, "RAG_UNAVAILABLE", "Answer service is unavailable.");
    }
    return payload;
  } catch (err) {
    if (err instanceof AppError) {
      throw err;
    }
    if (err?.name === "AbortError") {
      throw new AppError(504, "RAG_TIMEOUT", "Answer service timed out.");
    }
    throw new AppError(502, "RAG_UNAVAILABLE", "Answer service is unavailable.");
  } finally {
    clearTimeout(timer);
  }
}

export async function queryRag({ question, language, conversationHistory, taskState }) {
  const payload = await ragFetch(
    "/internal/query",
    {
      question,
      language,
      conversation_history: conversationHistory,
      task_state: taskState || null,
    },
    config.rag.timeoutMs
  );
  return {
    answer: payload.answer,
    language: payload.language === "kn" ? "kn" : "en",
    grounded: Boolean(payload.grounded),
    sources: Array.isArray(payload.sources) ? payload.sources : [],
    intent: payload.intent || null,
    task: payload.task || null,
  };
}

export async function generateEcontent({ topic, language }) {
  const payload = await ragFetch(
    "/internal/econtent",
    { topic, language },
    config.rag.econtentTimeoutMs
  );
  return {
    title: payload.title || topic,
    language: payload.language === "kn" ? "kn" : "en",
    grounded: Boolean(payload.grounded),
    content: payload.content || null,
    sources: Array.isArray(payload.sources) ? payload.sources : [],
    message: payload.message || null,
  };
}

export async function renderEcontentPdf(document, images) {
  return ragFetch(
    "/internal/econtent/pdf",
    {
      title: document.title,
      language: document.language,
      content: document.content,
      sources: document.sources,
      images: (images || []).map((item) => ({
        file_path: item.file_path,
        caption: item.caption,
        alt_text: item.alt_text,
        topic: item.topic,
      })),
    },
    config.rag.timeoutMs
  );
}

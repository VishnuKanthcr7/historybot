import { AppError } from "../utils/errors.js";
import { config } from "../config/env.js";

export async function queryRag({ question, language, conversationHistory }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.rag.timeoutMs);
  try {
    const response = await fetch(`${config.rag.url}/internal/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": config.rag.secret,
      },
      body: JSON.stringify({
        question,
        language,
        conversation_history: conversationHistory,
      }),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) {
        throw new AppError(502, "RAG_UNAVAILABLE", "Answer service is unavailable.");
      }
      throw new AppError(502, "RAG_UNAVAILABLE", "Answer service is unavailable.");
    }
    return {
      answer: payload.answer,
      language: payload.language === "kn" ? "kn" : "en",
      grounded: Boolean(payload.grounded),
      sources: Array.isArray(payload.sources) ? payload.sources : [],
    };
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

const BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api/v1").replace(
  /\/$/,
  ""
);

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function friendlyMessage(code, fallback) {
  switch (code) {
    case "RAG_UNAVAILABLE":
      return "HistoryBot is temporarily unavailable. Please try again in a moment.";
    case "RAG_TIMEOUT":
      return "HistoryBot is taking longer than expected. Please try again in a moment.";
    case "VALIDATION_ERROR":
      return "Please enter a valid question.";
    case "SESSION_NOT_FOUND":
    case "CONVERSATION_NOT_FOUND":
    case "FORBIDDEN":
      return "This chat could not be opened. Start a new chat to continue.";
    case "RATE_LIMITED":
      return "Too many questions in a short time. Please wait a moment.";
    case "NETWORK":
      return "We couldn't connect to HistoryBot. Please check your connection and try again.";
    default:
      return fallback || "Something went wrong. Please try again.";
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new ApiError("NETWORK", friendlyMessage("NETWORK"), 0);
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = data?.error?.code || "INTERNAL_ERROR";
    throw new ApiError(code, friendlyMessage(code, data?.error?.message), response.status);
  }
  return data;
}

export function createSession() {
  return request("/sessions", { method: "POST", body: JSON.stringify({}) });
}

export function createConversation(sessionId, title) {
  return request("/conversations", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      ...(title ? { title } : {}),
    }),
  });
}

export function listConversations(sessionId) {
  const query = new URLSearchParams({ session_id: sessionId });
  return request(`/conversations?${query.toString()}`);
}

export function getConversation(conversationId, sessionId) {
  const query = new URLSearchParams({ session_id: sessionId });
  return request(`/conversations/${conversationId}?${query.toString()}`);
}

export function sendMessage(conversationId, sessionId, message, language) {
  return request(`/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      message,
      language,
    }),
  });
}

export function createEcontent(sessionId, conversationId, topic, language) {
  return request("/econtent", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      ...(conversationId ? { conversation_id: conversationId } : {}),
      topic,
      language,
    }),
  });
}

export function getEcontent(econtentId, sessionId) {
  const query = new URLSearchParams({ session_id: sessionId });
  return request(`/econtent/${econtentId}?${query.toString()}`);
}

export async function downloadEcontentPdf(econtentId, sessionId) {
  let response;
  try {
    response = await fetch(`${BASE}/econtent/${econtentId}/pdf`, {
      method: "POST",
      headers: {
        Accept: "application/pdf",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    throw new ApiError("NETWORK", friendlyMessage("NETWORK"), 0);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const code = data?.error?.code || "INTERNAL_ERROR";
    throw new ApiError(code, friendlyMessage(code, data?.error?.message), response.status);
  }
  return response.blob();
}

export function imageUrl(id) {
  return `${BASE}/images/${id}`;
}

export function checkHealth() {
  return request("/health");
}

export { BASE as API_BASE };

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:3000").replace(
  /\/$/,
  ""
);
const BASE = API_BASE_URL.endsWith("/api/v1") ? API_BASE_URL : `${API_BASE_URL}/api/v1`;

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
    case "INTERNAL_ERROR":
    case "DATABASE_ERROR":
      return "Something went wrong. Please try again in a moment.";
    case "INVALID_JSON":
      return "Please enter a valid question.";
    case "VALIDATION_ERROR":
      return "Please enter a valid question.";
    case "SESSION_NOT_FOUND":
    case "CONVERSATION_NOT_FOUND":
    case "FORBIDDEN":
      return "This chat could not be opened. Start a new chat to continue.";
    case "RATE_LIMITED":
      return fallback || "Too many attempts. Please wait a moment.";
    case "INVALID_CREDENTIALS":
      return "Email or password is incorrect.";
    case "EMAIL_IN_USE":
      return "An account with this email already exists.";
    case "UNAUTHENTICATED":
      return "Please log in again.";
    case "NETWORK":
      return "We couldn't connect to HistoryBot. Please check your connection and try again.";
    default:
      return fallback || "Something went wrong. Please try again.";
  }
}

const TOKEN_KEY = "historybot_auth_token";

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setAuthToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let unauthorizedHandler = null;

// AppContext registers this so a rejected login token also clears the signed-in state.
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = typeof handler === "function" ? handler : null;
}

function handleUnauthorized(status, sentToken) {
  if (status !== 401 || !sentToken) return;
  setAuthToken("");
  if (unauthorizedHandler) unauthorizedHandler();
}

async function request(path, options = {}) {
  const { auth = true, ...fetchOptions } = options;
  const tokenHeaders = auth ? authHeaders() : {};
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...fetchOptions,
      headers: {
        Accept: "application/json",
        ...tokenHeaders,
        ...(fetchOptions.body ? { "Content-Type": "application/json" } : {}),
        ...(fetchOptions.headers || {}),
      },
    });
  } catch {
    throw new ApiError("NETWORK", friendlyMessage("NETWORK"), 0);
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    handleUnauthorized(response.status, Boolean(tokenHeaders.Authorization));
    const code = data?.error?.code || "INTERNAL_ERROR";
    throw new ApiError(code, friendlyMessage(code, data?.error?.message), response.status);
  }
  return data;
}

export function registerAccount(displayName, email, password) {
  return request("/auth/register", {
    method: "POST",
    auth: false,
    body: JSON.stringify({
      display_name: displayName,
      email,
      password,
    }),
  });
}

export function loginAccount(email, password) {
  return request("/auth/login", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ email, password }),
  });
}

export function logoutAccount() {
  return request("/auth/logout", { method: "POST", body: JSON.stringify({}) });
}

export function currentAccount() {
  return request("/auth/me");
}

export function adminSummary() {
  return request("/admin/summary");
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
  const tokenHeaders = authHeaders();
  let response;
  try {
    response = await fetch(`${BASE}/econtent/${econtentId}/pdf`, {
      method: "POST",
      headers: {
        Accept: "application/pdf",
        "Content-Type": "application/json",
        ...tokenHeaders,
      },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    throw new ApiError("NETWORK", friendlyMessage("NETWORK"), 0);
  }
  if (!response.ok) {
    handleUnauthorized(response.status, Boolean(tokenHeaders.Authorization));
    const data = await response.json().catch(() => ({}));
    const code = data?.error?.code || "INTERNAL_ERROR";
    throw new ApiError(code, friendlyMessage(code, data?.error?.message), response.status);
  }
  return response.blob();
}

export async function fetchProtectedImage(id) {
  const tokenHeaders = authHeaders();
  let response;
  try {
    response = await fetch(`${BASE}/images/${id}`, {
      headers: {
        Accept: "image/png,image/gif,image/webp,image/jpeg,*/*",
        ...tokenHeaders,
      },
    });
  } catch {
    throw new ApiError("NETWORK", friendlyMessage("NETWORK"), 0);
  }
  if (!response.ok) {
    handleUnauthorized(response.status, Boolean(tokenHeaders.Authorization));
    const data = await response.json().catch(() => ({}));
    const code = data?.error?.code || "UNAUTHENTICATED";
    throw new ApiError(code, friendlyMessage(code, data?.error?.message), response.status);
  }
  return response.blob();
}

export function checkHealth() {
  return request("/health");
}

export { API_BASE_URL, BASE as API_BASE };

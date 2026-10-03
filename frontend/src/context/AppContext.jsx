import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as api from "../services/api.js";

const SESSION_KEY = "historybot_session_id";
const LANG_KEY = "historybot_language";
const CURRENT_KEY = "historybot_current_conversation_id";

function convKey(sessionId) {
  return `historybot_conversations_${sessionId}`;
}

function isUntitled(title) {
  const value = String(title || "").trim();
  return !value || value === "New Chat" || value === "New chat" || value === "ಹೊಸ ಚಾಟ್";
}

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || "");
  const [language, setLanguageState] = useState(() =>
    localStorage.getItem(LANG_KEY) === "kn" ? "kn" : "en"
  );
  const [conversations, setConversations] = useState([]);
  const [currentId, setCurrentId] = useState(() => localStorage.getItem(CURRENT_KEY) || "");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let sid = localStorage.getItem(SESSION_KEY);
        if (!sid) {
          const created = await api.createSession();
          sid = created.session_id;
          localStorage.setItem(SESSION_KEY, sid);
        }
        if (cancelled) return;
        setSessionId(sid);
        setConversations(readJson(convKey(sid), []));
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not start a session.");
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const persistConversations = useCallback((sid, list) => {
    setConversations(list);
    localStorage.setItem(convKey(sid), JSON.stringify(list));
  }, []);

  const setLanguage = useCallback((next) => {
    const value = next === "kn" ? "kn" : "en";
    setLanguageState(value);
    localStorage.setItem(LANG_KEY, value);
  }, []);

  const openConversation = useCallback(
    async (conversationId, sid = sessionId) => {
      if (!sid || !conversationId) return;
      setError("");
      const data = await api.getConversation(conversationId, sid);
      setCurrentId(conversationId);
      localStorage.setItem(CURRENT_KEY, conversationId);
      setMessages(data.messages || []);
    },
    [sessionId]
  );

  const newChat = useCallback(
    async (title) => {
      if (!sessionId) throw new Error("No session");
      const created = await api.createConversation(sessionId, title);
      const entry = {
        id: created.conversation_id,
        title: created.title || title || "New chat",
      };
      persistConversations(sessionId, [entry, ...conversations.filter((c) => c.id !== entry.id)]);
      setCurrentId(entry.id);
      localStorage.setItem(CURRENT_KEY, entry.id);
      setMessages([]);
      setError("");
      return entry.id;
    },
    [sessionId, conversations, persistConversations]
  );

  const send = useCallback(
    async (text) => {
      const question = String(text || "").trim();
      if (!question || loading) return;
      setError("");
      setLoading(true);
      const userMsg = {
        id: `local-${Date.now()}`,
        role: "user",
        content: question,
        language,
        sources: [],
        grounded: null,
      };
      setMessages((prev) => [...prev, userMsg]);
      try {
        let conversationId = currentId;
        if (!conversationId) {
          conversationId = await newChat(question.slice(0, 80));
        } else {
          persistConversations(
            sessionId,
            conversations.map((c) =>
              c.id === conversationId && isUntitled(c.title)
                ? { ...c, title: question.slice(0, 80) }
                : c
            )
          );
        }
        const result = await api.sendMessage(conversationId, sessionId, question, language);
        setMessages((prev) => [...prev, result.message]);
      } catch (err) {
        setError(err.message || "Request failed.");
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
      } finally {
        setLoading(false);
      }
    },
    [currentId, language, loading, newChat, sessionId, conversations, persistConversations]
  );

  const value = useMemo(
    () => ({
      sessionId,
      language,
      setLanguage,
      conversations,
      currentId,
      messages,
      loading,
      error,
      setError,
      ready,
      openConversation,
      newChat,
      send,
    }),
    [
      sessionId,
      language,
      setLanguage,
      conversations,
      currentId,
      messages,
      loading,
      error,
      ready,
      openConversation,
      newChat,
      send,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

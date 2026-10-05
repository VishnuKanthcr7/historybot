import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as api from "../services/api.js";

const SESSION_KEY = "historybot_session_id";
const LANG_KEY = "historybot_language";
const CURRENT_KEY = "historybot_current_conversation_id";

const AppContext = createContext(null);

function mapList(payload) {
  const rows = payload?.conversations || [];
  return rows.map((row) => ({
    id: row.conversation_id,
    title: row.title,
    created_at: row.created_at,
    updated_at: row.updated_at,
  }));
}

export function AppProvider({ children }) {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || "");
  const [language, setLanguageState] = useState(() =>
    localStorage.getItem(LANG_KEY) === "kn" ? "kn" : "en"
  );
  const [conversations, setConversations] = useState([]);
  const [currentId, setCurrentId] = useState(() => localStorage.getItem(CURRENT_KEY) || "");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [econtentLoading, setEcontentLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [econtent, setEcontent] = useState(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  const refreshList = useCallback(async (sid) => {
    if (!sid) return;
    const payload = await api.listConversations(sid);
    setConversations(mapList(payload));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let sid = localStorage.getItem(SESSION_KEY);
        if (!sid) {
          const created = await api.createSession();
          // Prefer a session another flow wrote while createSession was in flight
          // (e.g. test harness / another tab), so we do not clobber it.
          const existing = localStorage.getItem(SESSION_KEY);
          sid = existing || created.session_id;
          if (!existing) localStorage.setItem(SESSION_KEY, sid);
        }
        if (cancelled) return;
        setSessionId(sid);
        await refreshList(sid);
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not start a session.");
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshList]);

  const setLanguage = useCallback((next) => {
    const value = next === "kn" ? "kn" : "en";
    setLanguageState(value);
    localStorage.setItem(LANG_KEY, value);
  }, []);

  const beginFreshChat = useCallback(() => {
    // Clear active main-chat state only. Sidebar history is untouched.
    setCurrentId("");
    localStorage.removeItem(CURRENT_KEY);
    setMessages([]);
    setEcontent(null);
    setError("");
  }, []);

  const openConversation = useCallback(
    async (conversationId, sid = sessionId) => {
      if (!sid || !conversationId) return;
      setError("");
      setEcontent(null);
      try {
        const data = await api.getConversation(conversationId, sid);
        setCurrentId(conversationId);
        localStorage.setItem(CURRENT_KEY, conversationId);
        setMessages(data.messages || []);
      } catch (err) {
        setError(err.message || "This chat could not be opened.");
        throw err;
      }
    },
    [sessionId]
  );

  const newChat = useCallback(
    async (title) => {
      if (!sessionId) throw new Error("No session");
      const created = await api.createConversation(sessionId, title);
      setCurrentId(created.conversation_id);
      localStorage.setItem(CURRENT_KEY, created.conversation_id);
      setMessages([]);
      setEcontent(null);
      setError("");
      await refreshList(sessionId);
      return created.conversation_id;
    },
    [sessionId, refreshList]
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
        images: [],
        grounded: null,
      };
      setMessages((prev) => [...prev, userMsg]);
      try {
        let conversationId = currentId;
        if (!conversationId) {
          // newChat() resets messages for a blank thread; restore the optimistic
          // user turn so lastUser stays available for "Make a learning module".
          conversationId = await newChat(question.slice(0, 80));
          setMessages([userMsg]);
        }
        const result = await api.sendMessage(conversationId, sessionId, question, language);
        setMessages((prev) => {
          const withoutDup = prev.filter((m) => m.id !== userMsg.id);
          return [...withoutDup, userMsg, result.message];
        });
        await refreshList(sessionId);
      } catch (err) {
        setError(err.message || "Request failed.");
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
      } finally {
        setLoading(false);
      }
    },
    [currentId, language, loading, newChat, sessionId, refreshList]
  );

  const requestEcontent = useCallback(
    async (topic) => {
      if (!sessionId || econtentLoading) return;
      const subject = String(topic || "").trim();
      if (!subject) return;
      setError("");
      setEcontentLoading(true);
      try {
        const result = await api.createEcontent(sessionId, currentId, subject, language);
        setEcontent(result);
        if (!result.grounded) {
          setError(result.message || "This topic is not available in the textbook.");
        }
      } catch (err) {
        setError(err.message || "Request failed.");
      } finally {
        setEcontentLoading(false);
      }
    },
    [sessionId, currentId, language, econtentLoading]
  );

  const downloadPdf = useCallback(async () => {
    if (!econtent?.id || !sessionId || pdfLoading) return;
    setPdfLoading(true);
    try {
      const blob = await api.downloadEcontentPdf(econtent.id, sessionId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${(econtent.title || "historybot").slice(0, 40)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "PDF download failed.");
    } finally {
      setPdfLoading(false);
    }
  }, [econtent, sessionId, pdfLoading]);

  const value = useMemo(
    () => ({
      sessionId,
      language,
      setLanguage,
      conversations,
      currentId,
      messages,
      loading,
      econtentLoading,
      pdfLoading,
      econtent,
      error,
      setError,
      ready,
      beginFreshChat,
      openConversation,
      newChat,
      send,
      requestEcontent,
      downloadPdf,
      setEcontent,
    }),
    [
      sessionId,
      language,
      setLanguage,
      conversations,
      currentId,
      messages,
      loading,
      econtentLoading,
      pdfLoading,
      econtent,
      error,
      ready,
      beginFreshChat,
      openConversation,
      newChat,
      send,
      requestEcontent,
      downloadPdf,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

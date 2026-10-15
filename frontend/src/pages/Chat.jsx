import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { LABELS } from "../i18n/labels.js";
import MessageList from "../components/MessageList.jsx";
import ChatComposer from "../components/ChatComposer.jsx";
import HistorySidebar from "../components/HistorySidebar.jsx";
import EcontentPanel from "../components/EcontentPanel.jsx";
import AccountMenu from "../components/AccountMenu.jsx";
import { clearPendingQuestion } from "../pendingQuestion.js";

export default function Chat() {
  const {
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
    setEcontent,
  } = useApp();
  const t = LABELS[language];
  const [params, setParams] = useSearchParams();
  const [menuOpen, setMenuOpen] = useState(false);
  const pendingQuestion = useRef(false);
  // When true, do not auto-restore last CURRENT_KEY (Start Learning / New Chat).
  const skipAutoRestore = useRef(false);
  // Prevents repeat auto-restore loops for the same conversation id.
  const restoreAttemptedFor = useRef("");
  const freshHandled = useRef(false);

  // Start Learning / Home CTA: force blank main chat and skip restore race.
  useEffect(() => {
    if (freshHandled.current) return;
    if (params.get("fresh") !== "1") return;
    freshHandled.current = true;
    clearPendingQuestion();
    skipAutoRestore.current = true;
    restoreAttemptedFor.current = "";
    beginFreshChat();
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("fresh");
        return next;
      },
      { replace: true }
    );
  }, [params, beginFreshChat, setParams]);

  useEffect(() => {
    if (!ready || pendingQuestion.current) return;
    const q = params.get("q");
    if (q) {
      pendingQuestion.current = true;
      clearPendingQuestion();
      skipAutoRestore.current = true;
      restoreAttemptedFor.current = "";
      setParams({}, { replace: true });
      send(q);
    }
  }, [ready, params, send, setParams]);

  useEffect(() => {
    // Skip while a send is in flight: newChat() briefly clears messages and would
    // race-reload an incomplete conversation, dropping the optimistic user turn.
    // Also skip after Start Learning (?fresh=1) / New Chat so nav cannot lose to restore.
    if (!ready || skipAutoRestore.current || params.get("q") || params.get("fresh") || loading) {
      return;
    }
    if (!currentId || messages.length > 0) return;
    if (restoreAttemptedFor.current === currentId) return;
    restoreAttemptedFor.current = currentId;
    let cancelled = false;
    openConversation(currentId).catch(() => {
      // Allow a later retry (e.g. after session settles) if this attempt failed.
      if (!cancelled && restoreAttemptedFor.current === currentId) {
        restoreAttemptedFor.current = "";
      }
    });
    return () => {
      cancelled = true;
    };
  }, [ready, currentId, messages.length, openConversation, params, loading]);

  async function handleNewChat() {
    skipAutoRestore.current = true;
    restoreAttemptedFor.current = "";
    await newChat(t.newChat);
    // Keep skipAutoRestore true so the empty new thread is not re-fetched as a race.
    setMenuOpen(false);
  }

  async function handleOpen(id) {
    // History click must always restore that conversation's messages.
    skipAutoRestore.current = false;
    restoreAttemptedFor.current = id;
    try {
      await openConversation(id);
    } catch {
      // Error surfaced via AppContext.setError
      restoreAttemptedFor.current = "";
    }
    setMenuOpen(false);
  }

  const lastUser = [...messages].reverse().find((item) => item.role === "user");

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col overflow-x-hidden bg-paper font-sans text-ink">
      <a href="#chat-main" className="skip-link">
        Skip to chat
      </a>
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-rule bg-cream px-3 py-2.5 md:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            className="min-h-11 rounded-full border border-rule px-3 text-sm md:hidden"
            aria-label={menuOpen ? t.closeMenu : t.openMenu}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            {t.history}
          </button>
          <Link to="/" className="truncate font-serif text-xl text-navy">
            HistoryBot
          </Link>
          <span className="hidden text-[10px] uppercase tracking-[0.16em] text-muted lg:inline">
            Class 9 Social Science
          </span>
        </div>
        <div className="chat-actions">
          <button
            type="button"
            onClick={handleNewChat}
            className="min-h-11 rounded-full border border-navy px-3 text-sm text-navy transition hover:bg-navy hover:text-cream"
          >
            {t.newChat}
          </button>
          <button
            type="button"
            disabled={econtentLoading || !lastUser || loading}
            onClick={() => requestEcontent(lastUser?.content)}
            className="chat-module min-h-11 rounded-full border border-rule bg-cream px-3 text-sm text-navy transition hover:border-brass disabled:opacity-50"
            title={!lastUser ? "Ask a question first" : undefined}
          >
            {econtentLoading ? t.econtentWorking : t.makeEcontent}
          </button>
          <label htmlFor="chat-lang" className="sr-only">
            {t.language}
          </label>
          <select
            id="chat-lang"
            className="min-h-11 rounded-full border border-rule bg-cream px-2 text-sm"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="en">{t.english}</option>
            <option value="kn">{t.kannada}</option>
          </select>
          <AccountMenu />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <HistorySidebar
          open={menuOpen}
          conversations={conversations}
          currentId={currentId}
          onOpen={handleOpen}
          onClose={() => setMenuOpen(false)}
          labels={t}
        />
        <section id="chat-main" className="flex min-w-0 flex-1 flex-col bg-paper">
          {error ? (
            <p
              className="mx-3 mt-3 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 md:mx-5"
              role="alert"
            >
              {error}
            </p>
          ) : null}
          {language === "kn" ? (
            <p className="mx-3 mt-3 rounded-2xl border border-brass/40 bg-cream px-3 py-2 text-sm text-navy md:mx-5" role="note" data-testid="kannada-note">
              ಕನ್ನಡ ಉತ್ತರಗಳು ಇನ್ನೂ ಲಭ್ಯವಿಲ್ಲ. Kannada answers and modules are not available yet (the Kannada textbook is not yet in a
              machine-readable form). Menus are in Kannada; please ask your question in English.
            </p>
          ) : null}
          {econtentLoading ? (
            <p
              className="mx-3 mt-3 border border-brass/40 bg-cream px-3 py-2 text-sm text-navy md:mx-5"
              role="status"
              aria-live="polite"
            >
              {t.econtentWait}
            </p>
          ) : null}
          <MessageList
            messages={messages}
            loading={loading}
            language={language}
            onAsk={send}
          />
          <EcontentPanel
            data={econtent}
            labels={t}
            language={language}
            onClose={() => setEcontent(null)}
            onPdf={downloadPdf}
            pdfLoading={pdfLoading}
          />
          <ChatComposer disabled={loading || !ready} onSend={send} labels={t} />
        </section>
      </div>
    </div>
  );
}

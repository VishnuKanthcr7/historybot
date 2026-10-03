import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { LABELS } from "../i18n/labels.js";
import MessageList from "../components/MessageList.jsx";
import ChatComposer from "../components/ChatComposer.jsx";
import HistorySidebar from "../components/HistorySidebar.jsx";
import EcontentPanel from "../components/EcontentPanel.jsx";

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
  const restored = useRef(false);

  useEffect(() => {
    if (!ready || pendingQuestion.current) return;
    const q = params.get("q");
    if (q) {
      pendingQuestion.current = true;
      setParams({}, { replace: true });
      send(q);
    }
  }, [ready, params, send, setParams]);

  useEffect(() => {
    if (!ready || restored.current || params.get("q")) return;
    if (currentId && messages.length === 0) {
      restored.current = true;
      openConversation(currentId).catch(() => {});
    }
  }, [ready, currentId, messages.length, openConversation, params]);

  async function handleNewChat() {
    await newChat(t.newChat);
    setMenuOpen(false);
  }

  async function handleOpen(id) {
    await openConversation(id);
    setMenuOpen(false);
  }

  const lastUser = [...messages].reverse().find((item) => item.role === "user");

  return (
    <div className="flex h-screen min-h-0 flex-col bg-paper text-ink">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-rule bg-cream px-3 py-2.5 md:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            className="min-h-10 border border-rule px-3 text-sm md:hidden"
            aria-label={menuOpen ? t.closeMenu : t.openMenu}
            onClick={() => setMenuOpen((v) => !v)}
          >
            {t.history}
          </button>
          <Link to="/" className="truncate font-serif text-xl text-navy">
            HistoryBot
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleNewChat}
            className="min-h-10 border border-navy px-3 text-sm text-navy hover:bg-navy hover:text-cream"
          >
            {t.newChat}
          </button>
          <button
            type="button"
            disabled={econtentLoading || !lastUser || loading}
            onClick={() => requestEcontent(lastUser?.content)}
            className="min-h-10 border border-brass px-3 text-sm text-navy disabled:opacity-50"
          >
            {econtentLoading ? t.econtentWorking : t.makeEcontent}
          </button>
          <label htmlFor="chat-lang" className="sr-only">
            {t.language}
          </label>
          <select
            id="chat-lang"
            className="min-h-10 border border-rule bg-cream px-2 text-sm"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="en">{t.english}</option>
            <option value="kn">{t.kannada}</option>
          </select>
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
        <section className="flex min-w-0 flex-1 flex-col">
          {error ? (
            <p className="mx-4 mt-3 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
              {error}
            </p>
          ) : null}
          <MessageList messages={messages} loading={loading} language={language} />
          <EcontentPanel
            data={econtent}
            labels={t}
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

import { useEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble.jsx";
import { LABELS } from "../i18n/labels.js";

const EXAMPLES = [
  "Who was Akbar?",
  "Why did Sher Shah defeat Humayun?",
  "Explain the Mansabdari system.",
  "Compare Akbar and Aurangzeb.",
];

export default function MessageList({ messages, loading, language, onAsk }) {
  const endRef = useRef(null);
  const t = LABELS[language] || LABELS.en;

  const [announcement, setAnnouncement] = useState("");
  const wasLoading = useRef(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Tell screen-reader users when an answer arrives (the "thinking" line disappears silently).
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (wasLoading.current && !loading && last?.role === "assistant") {
      setAnnouncement(t.answerReady || "Answer ready");
    } else if (loading) {
      setAnnouncement("");
    }
    wasLoading.current = loading;
  }, [loading, messages, t.answerReady]);

  return (
    <div className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-4 sm:px-5 md:px-8">
      {messages.length === 0 && !loading ? (
        <div className="mx-auto max-w-2xl pt-8 sm:pt-14">
          <p className="font-serif text-3xl text-navy">HistoryBot</p>
          <p className="mt-2 text-base text-muted">{t.emptyChat}</p>
          <ul className="mt-6 grid gap-2 sm:grid-cols-2">
            {EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  onClick={() => onAsk?.(example)}
                  className="min-h-11 w-full rounded-2xl border border-rule bg-cream px-4 py-3 text-left text-sm text-ink transition hover:border-brass"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <ol className="mx-auto max-w-2xl space-y-4">
        {messages.map((msg) => (
          <li key={msg.id}>
            <MessageBubble message={msg} language={language} />
          </li>
        ))}
        {loading ? (
          <li className="px-1 text-sm text-muted" aria-live="polite">
            <span className="inline-flex items-center gap-2">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brass" aria-hidden />
              {t.thinking}
            </span>
          </li>
        ) : null}
      </ol>
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
      <div ref={endRef} />
    </div>
  );
}

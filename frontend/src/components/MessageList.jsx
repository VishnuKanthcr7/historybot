import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";
import { LABELS } from "../i18n/labels.js";

export default function MessageList({ messages, loading, language }) {
  const endRef = useRef(null);
  const t = LABELS[language] || LABELS.en;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4 sm:px-5 md:px-8">
      {messages.length === 0 && !loading ? (
        <div className="mx-auto max-w-2xl border border-rule bg-cream p-6">
          <p className="font-serif text-xl text-navy">{t.emptyChat}</p>
          <p className="mt-2 text-sm leading-relaxed text-stone-600">{t.how2}</p>
          <ul className="mt-4 space-y-1.5 text-sm text-stone-600">
            <li>· Who was Akbar?</li>
            <li>· Explain Shivaji in detail</li>
            <li>· Give me 10 MCQs on the Marathas</li>
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
          <li
            className="border border-dashed border-brass/40 bg-cream/80 px-4 py-3 text-sm text-brass"
            aria-live="polite"
          >
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-brass" aria-hidden />
              {t.thinking}
            </span>
          </li>
        ) : null}
      </ol>
      <div ref={endRef} />
    </div>
  );
}

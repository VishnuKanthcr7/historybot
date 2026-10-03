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
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-8">
      {messages.length === 0 && !loading ? (
        <div className="mx-auto max-w-2xl border border-rule bg-cream p-5">
          <p className="font-serif text-lg text-navy">{t.emptyChat}</p>
          <p className="mt-2 text-sm text-stone-600">{t.how2}</p>
        </div>
      ) : null}
      <ol className="mx-auto max-w-2xl space-y-4">
        {messages.map((msg) => (
          <li key={msg.id}>
            <MessageBubble message={msg} language={language} />
          </li>
        ))}
        {loading ? (
          <li className="text-sm italic text-brass" aria-live="polite">
            {t.thinking}
          </li>
        ) : null}
      </ol>
      <div ref={endRef} />
    </div>
  );
}

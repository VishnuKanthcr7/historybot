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
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-10">
      {messages.length === 0 && !loading ? (
        <p className="mx-auto max-w-2xl text-stone-600">{t.emptyChat}</p>
      ) : null}
      <ol className="mx-auto max-w-2xl space-y-5">
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

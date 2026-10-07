import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import SourceCite from "./SourceCite.jsx";
import { imageUrl } from "../services/api.js";
import { LABELS } from "../i18n/labels.js";

function displayContent(content) {
  return String(content || "")
    .replace(/\n*Source:\s*[^\n]*/gi, "")
    .trim();
}

function splitContext(content) {
  const cleaned = displayContent(content);
  const parts = cleaned.split(/\n+Additional historical context:\s*/i);
  return {
    main: (parts[0] || "").trim(),
    extra: (parts[1] || "").trim(),
  };
}

const markdownComponents = {
  a: ({ children }) => <span>{children}</span>,
  h1: ({ children }) => (
    <h3 className="mb-2 mt-4 font-serif text-lg text-navy first:mt-0">{children}</h3>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 mt-4 font-serif text-lg text-navy first:mt-0">{children}</h3>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-3 font-serif text-base text-navy first:mt-0">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-navydeep">{children}</strong>,
  code: ({ children }) => <span>{children}</span>,
};

export default function MessageBubble({ message, language }) {
  const isUser = message.role === "user";
  const { main, extra } = splitContext(message.content);
  return (
    <article className={isUser ? "flex justify-end" : "flex gap-3"}>
      {isUser ? null : (
        <span
          className="mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy font-serif text-sm text-cream sm:inline-flex"
          aria-hidden
        >
          H
        </span>
      )}
      <div
        className={`min-w-0 max-w-full rounded-2xl px-4 py-3.5 ${
          isUser
            ? "max-w-[85%] bg-navy text-cream"
            : "flex-1 border border-rule bg-cream"
        }`}
      >
        <p className={`mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] ${isUser ? "text-cream/70" : "text-brass"}`}>
          {isUser ? (language === "kn" ? "ವಿದ್ಯಾರ್ಥಿ" : "You") : "HistoryBot"}
        </p>
        {isUser ? (
          <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed">{message.content}</p>
        ) : (
          <div className="prose-history break-words text-[15px] leading-relaxed text-ink">
            {main ? (
              <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
                {main}
              </Markdown>
            ) : null}
            <SourceCite sources={message.sources} language={language} />
            {extra ? (
              <aside className="mt-3 rounded-xl border border-rule bg-paper px-3 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-brass">
                  Additional historical context
                </p>
                <div className="mt-2">
                  <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
                    {extra}
                  </Markdown>
                </div>
              </aside>
            ) : null}
            {(message.images || []).map((img) => (
              <figure key={img.id} className="mt-3 overflow-hidden rounded-xl border border-rule bg-paper p-2">
                <img
                  src={imageUrl(img.id)}
                  alt={img.alt}
                  className="max-h-52 w-full object-contain"
                  loading="lazy"
                />
                <figcaption className="mt-1 text-xs text-muted">
                  {img.title}
                  {img.textbook_page_number
                    ? ` · ${LABELS[language]?.textbookPage || "Textbook page"} ${img.textbook_page_number}`
                    : ""}
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

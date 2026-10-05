import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import SourceCite from "./SourceCite.jsx";
import { imageUrl } from "../services/api.js";
import { LABELS } from "../i18n/labels.js";

function displayContent(content) {
  return String(content || "")
    .replace(/\n*Source:\s*Textbook pages?[^\n]*/gi, "")
    .trim();
}

export default function MessageBubble({ message, language }) {
  const isUser = message.role === "user";
  return (
    <article
      className={`rounded-sm px-4 py-3.5 ${
        isUser
          ? "ml-4 bg-navy text-cream sm:ml-10"
          : "mr-2 border border-rule bg-cream shadow-[0_1px_0_rgba(30,58,95,0.04)] sm:mr-6"
      }`}
    >
      <p
        className={`mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] ${
          isUser ? "text-cream/70" : "text-brass"
        }`}
      >
        {isUser ? (language === "kn" ? "ವಿದ್ಯಾರ್ಥಿ" : "You") : "HistoryBot"}
      </p>
      {isUser ? (
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
      ) : (
        <div className="prose-history text-[15px] leading-relaxed text-ink">
          <Markdown
            rehypePlugins={[rehypeSanitize]}
            components={{
              a: ({ children }) => <span>{children}</span>,
              h1: ({ children }) => (
                <h3 className="mb-2 mt-4 border-b border-rule/70 pb-1 font-serif text-lg text-navy first:mt-0">
                  {children}
                </h3>
              ),
              h2: ({ children }) => (
                <h3 className="mb-2 mt-4 border-b border-rule/70 pb-1 font-serif text-lg text-navy first:mt-0">
                  {children}
                </h3>
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
            }}
          >
            {displayContent(message.content)}
          </Markdown>
          <SourceCite sources={message.sources} language={language} />
          {(message.images || []).map((img) => (
            <figure key={img.id} className="mt-3 border border-rule bg-paper p-2">
              <img
                src={imageUrl(img.id)}
                alt={img.alt}
                className="max-h-52 w-full object-contain"
                loading="lazy"
              />
              <figcaption className="mt-1 text-xs text-stone-600">
                {img.title}
                {img.textbook_page_number
                  ? ` · ${LABELS[language]?.textbookPage || "Textbook page"} ${img.textbook_page_number}`
                  : ""}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </article>
  );
}

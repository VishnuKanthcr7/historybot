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
      className={`px-4 py-3 ${
        isUser ? "ml-6 bg-navy text-cream" : "mr-2 border border-rule bg-cream"
      }`}
    >
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide opacity-80">
        {isUser ? (language === "kn" ? "ವಿದ್ಯಾರ್ಥಿ" : "You") : "HistoryBot"}
      </p>
      {isUser ? (
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
      ) : (
        <div className="prose-history leading-relaxed">
          <Markdown
            rehypePlugins={[rehypeSanitize]}
            components={{
              a: ({ children }) => <span>{children}</span>,
              h1: ({ children }) => <h3 className="mb-2 mt-3 font-serif text-lg">{children}</h3>,
              h2: ({ children }) => <h3 className="mb-2 mt-3 font-serif text-lg">{children}</h3>,
              h3: ({ children }) => <h3 className="mb-2 mt-3 font-serif text-base">{children}</h3>,
              p: ({ children }) => <p className="mb-2">{children}</p>,
              ul: ({ children }) => <ul className="mb-2 list-disc pl-5">{children}</ul>,
              ol: ({ children }) => <ol className="mb-2 list-decimal pl-5">{children}</ol>,
              li: ({ children }) => <li className="mb-1">{children}</li>,
              code: ({ children }) => <span>{children}</span>,
            }}
          >
            {displayContent(message.content)}
          </Markdown>
          <SourceCite sources={message.sources} language={language} />
          {(message.images || []).map((img) => (
            <figure key={img.id} className="mt-3 border border-rule bg-paper p-2">
              <img src={imageUrl(img.id)} alt={img.alt} className="max-h-48 w-full object-contain" />
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

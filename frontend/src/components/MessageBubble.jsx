import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import SourceCite from "./SourceCite.jsx";

function displayContent(content) {
  return String(content || "")
    .replace(/\n*Source:\s*Textbook pages?[^\n]*/gi, "")
    .trim();
}

export default function MessageBubble({ message, language }) {
  const isUser = message.role === "user";
  return (
    <article
      className={`rounded-sm px-4 py-3 ${
        isUser ? "ml-8 bg-navy text-cream" : "mr-4 border border-rule bg-cream"
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
        </div>
      )}
    </article>
  );
}

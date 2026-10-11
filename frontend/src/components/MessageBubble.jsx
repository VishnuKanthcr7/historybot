import { useState } from "react";
import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import SourceCite from "./SourceCite.jsx";
import ProtectedImage, { ImageFigure } from "./ProtectedImage.jsx";
import { LABELS } from "../i18n/labels.js";

function displayContent(content) {
  return String(content || "")
    .replace(/\n*Source:\s*[^\n]*/gi, "")
    .trim();
}

// Answers come in labelled parts: "From your textbook" (cited), "Additional historical
// explanation" (general history, never cited) and an optional "Quick revision".
const SECTION_RE =
  /^[ \t]*(?:#{1,4}[ \t]*)?\*\*[ \t]*(From your textbook|Additional historical (?:explanation|context)|Quick revision)[ \t]*:?[ \t]*\*\*[ \t]*$/gim;

function splitContext(content) {
  const cleaned = displayContent(content);
  const marks = [...cleaned.matchAll(SECTION_RE)];
  if (!marks.length) {
    const parts = cleaned.split(/\n+Additional historical context:\s*/i);
    return { labelled: false, main: (parts[0] || "").trim(), extra: (parts[1] || "").trim(), revision: "" };
  }
  const out = { labelled: true, main: cleaned.slice(0, marks[0].index).trim(), extra: "", revision: "" };
  marks.forEach((mark, index) => {
    const end = index + 1 < marks.length ? marks[index + 1].index : cleaned.length;
    const body = cleaned.slice(mark.index + mark[0].length, end).trim();
    const label = mark[1].toLowerCase();
    if (label.startsWith("from")) out.main = [out.main, body].filter(Boolean).join("\n\n");
    else if (label.startsWith("quick")) out.revision = body;
    else out.extra = [out.extra, body].filter(Boolean).join("\n\n");
  });
  return out;
}

function SectionLabel({ children }) {
  return (
    <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-navy">{children}</p>
  );
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
  const { labelled, main, extra, revision } = splitContext(message.content);
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
        <p className={`mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] ${isUser ? "text-cream/70" : "text-navy"}`}>
          {isUser ? (language === "kn" ? "ವಿದ್ಯಾರ್ಥಿ" : "You") : "HistoryBot"}
        </p>
        {isUser ? (
          <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed">{message.content}</p>
        ) : (
          <div className="prose-history break-words text-[15px] leading-relaxed text-ink">
            {main ? (
              <section>
                {labelled ? <SectionLabel>From your textbook</SectionLabel> : null}
                <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
                  {main}
                </Markdown>
              </section>
            ) : null}
            <SourceCite sources={message.sources} language={language} />
            {extra ? (
              <aside className="mt-3 rounded-xl border border-rule bg-paper px-3 py-3">
                <SectionLabel>Additional historical explanation</SectionLabel>
                <p className="text-xs text-muted">General history to help you understand. Not from your textbook pages.</p>
                <div className="mt-2">
                  <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
                    {extra}
                  </Markdown>
                </div>
              </aside>
            ) : null}
            {revision ? (
              <aside className="mt-3 rounded-xl border border-rule bg-cream px-3 py-3">
                <SectionLabel>Quick revision</SectionLabel>
                <div className="mt-1">
                  <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
                    {revision}
                  </Markdown>
                </div>
              </aside>
            ) : null}
            {(message.images || []).map((img) =>
              img.media_kind === "gif" ? (
                <figure key={img.id} className="mt-3 overflow-hidden rounded-xl border border-rule bg-paper p-2">
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-navy">
                    Educational animation
                  </p>
                  <MotionSafeGif id={img.id} alt={img.alt} language={language} />
                  <figcaption className="mt-1 text-xs text-muted">
                    {img.title}
                    {[img.source, img.license].filter(Boolean).length ? (
                      <span className="mt-1 block">{[img.source, img.license].filter(Boolean).join(" · ")}</span>
                    ) : null}
                  </figcaption>
                </figure>
              ) : (
                <ImageFigure
                  key={img.id}
                  img={img}
                  pageLabel={LABELS[language]?.textbookPage || "Textbook page"}
                />
              )
            )}
          </div>
        )}
      </div>
    </article>
  );
}

// Animations play automatically unless the reader asked the system for reduced motion;
// then the GIF loads only when they choose "Show animation" (WCAG 2.2.2).
function MotionSafeGif({ id, alt, language }) {
  const reduce =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [shown, setShown] = useState(!reduce);
  const t = LABELS[language] || LABELS.en;
  return (
    <div>
      {shown ? <ProtectedImage id={id} alt={alt} className="max-h-52 w-full object-contain" /> : null}
      {reduce ? (
        <button
          type="button"
          className="mt-1 min-h-11 rounded-lg border border-rule px-3 text-xs text-navy"
          aria-pressed={shown}
          onClick={() => setShown((value) => !value)}
        >
          {shown ? t.hideAnimation || LABELS.en.hideAnimation : t.showAnimation || LABELS.en.showAnimation}
        </button>
      ) : null}
    </div>
  );
}

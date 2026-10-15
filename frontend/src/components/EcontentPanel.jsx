import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ImageFigure } from "./ProtectedImage.jsx";
import { quizApi } from "../services/api.js";
import SourceCite from "./SourceCite.jsx";

function CheckpointButton({ topic }) {
  const navigate = useNavigate();
  const [state, setState] = useState("");
  const start = async () => {
    setState("Preparing…");
    try {
      const r = await quizApi.checkpoint(topic);
      const started = await quizApi.start(r.quiz_id);
      navigate(`/attempts/${started.attempt.id}`);
    } catch (err) {
      setState(err.code === "NO_QUESTIONS" ? "No checkpoint questions for this topic yet." : err.message);
    }
  };
  return (
    <>
      <button type="button" className="min-h-11 border border-navy px-3 text-sm text-navy" onClick={start}>
        Checkpoint quiz
      </button>
      {state ? (
        <span className="basis-full text-xs text-muted" role="status">
          {state}
        </span>
      ) : null}
    </>
  );
}

export default function EcontentPanel({ data, labels, language, onClose, onPdf, pdfLoading }) {
  if (!data) return null;
  const content = data.content || {};
  const citations = content.section_citations || {};
  return (
    <aside className="max-h-[52vh] overflow-y-auto border-t border-rule bg-cream px-4 py-4 md:px-10" aria-label={labels.econtent}>
      <div className="mx-auto flex max-w-2xl flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-52">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brass">{labels.econtent}</p>
          <h2 className="mt-1 font-serif text-xl text-navy sm:text-2xl">{data.title}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.id ? (
            <button
              type="button"
              className="min-h-11 border border-navy px-3 text-sm text-navy disabled:opacity-50"
              onClick={onPdf}
              disabled={pdfLoading}
            >
              {pdfLoading ? labels.pdfWorking : labels.downloadPdf}
            </button>
          ) : null}
          {data.grounded && data.title && language !== "kn" ? <CheckpointButton topic={data.title} /> : null}
          <button type="button" className="min-h-11 border border-rule px-3 text-sm" onClick={onClose}>
            {labels.close}
          </button>
        </div>
      </div>
      {!data.grounded ? (
        <p className="mx-auto mt-3 max-w-2xl text-sm">{data.message}</p>
      ) : (
        <div className="mx-auto mt-4 max-w-2xl space-y-5 text-sm leading-relaxed">
          {section(labels.introduction, content.introduction, citations.Introduction)}
          {listSection(labels.objectives, content.learning_objectives)}
          {richSection(labels.detail, content.detailed_explanation, citations["Detailed explanation"])}
          {content.additional_explanation ? (
            <div className="border border-rule bg-paper p-3">
              {richSection("Additional historical explanation", content.additional_explanation)}
              <p className="mt-2 text-xs text-stone-600">General history to help you understand. Not from your textbook pages.</p>
            </div>
          ) : null}
          {namedList(labels.people, content.important_people, "name", "note", labels)}
          {namedList(labels.terms, content.important_terms, "term", "meaning", labels)}
          {namedList(labels.timeline, content.timeline, "when", "event", labels)}
          {listSection(labels.mainEvents, content.main_events)}
          {listSection(labels.keyPoints, content.key_points)}
          {qaList(labels.exam, content.exam_questions, labels)}
          {mcqList(labels.mcq, content.mcqs, labels)}
          {section(labels.revision, content.revision)}
          {citationMap(labels.sectionPages, citations)}
          {(data.images || []).map((img) => (
            <ImageFigure key={img.id} img={img} className="max-h-56 w-full object-contain">
              {img.media_kind === "gif" ? (
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-brass">
                  Educational animation
                </p>
              ) : null}
            </ImageFigure>
          ))}
          <SourceCite sources={data.sources} language={language} />
        </div>
      )}
    </aside>
  );
}

function pageNote(pages, labels) {
  if (!Array.isArray(pages) || !pages.length) return "";
  const unique = [...new Set(pages.map(Number).filter(Number.isFinite))];
  if (!unique.length) return "";
  const prefix = unique.length === 1 ? labels.textbookPage : labels.textbookPages;
  return `${prefix} ${unique.join(", ")}`;
}

function section(title, text, pages) {
  if (!text) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <p className="mt-1 whitespace-pre-wrap">{text}</p>
      {pages ? <p className="mt-1 text-xs text-stone-600">{pageNote(pages, { textbookPage: "Textbook page", textbookPages: "Textbook pages" })}</p> : null}
    </section>
  );
}

function richSection(title, text, pages) {
  if (!text) return null;
  const blocks = String(text).split(/\n(?=## )/);
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <div className="mt-2 space-y-3">
        {blocks.map((block, index) => {
          const trimmed = block.trim();
          if (trimmed.startsWith("## ")) {
            const newline = trimmed.indexOf("\n");
            const heading = newline === -1 ? trimmed.slice(3) : trimmed.slice(3, newline);
            const body = newline === -1 ? "" : trimmed.slice(newline + 1);
            return (
              <div key={`${heading}-${index}`}>
                <h4 className="font-serif text-base text-navy">{heading.trim()}</h4>
                {body ? <p className="mt-1 whitespace-pre-wrap">{body.trim()}</p> : null}
              </div>
            );
          }
          return (
            <p key={index} className="whitespace-pre-wrap">
              {trimmed}
            </p>
          );
        })}
      </div>
      {pages ? (
        <p className="mt-2 text-xs text-stone-600">
          {pageNote(pages, { textbookPage: "Textbook page", textbookPages: "Textbook pages" })}
        </p>
      ) : null}
    </section>
  );
}

function listSection(title, items) {
  if (!Array.isArray(items) || !items.length) return null;
  const readable = items
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") return item.event || item.note || item.meaning || item.question || "";
      return "";
    })
    .filter(Boolean);
  if (!readable.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ul className="mt-1 list-disc pl-5">
        {readable.map((item) => (
          <li key={String(item).slice(0, 80)}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function namedList(title, items, a, b, labels) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ul className="mt-1 list-disc pl-5">
        {items.map((item, index) => (
          <li key={`${item[a] || index}`}>
            <strong>{item[a]}</strong>
            {item[b] ? ` — ${item[b]}` : ""}
            {pageNote(item.pages, labels) ? (
              <span className="ml-1 text-xs text-stone-600">({pageNote(item.pages, labels)})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function qaList(title, items, labels) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ol className="mt-1 list-decimal pl-5">
        {items.map((item, index) => (
          <li key={index} className="mb-3">
            {item.type ? <p className="text-xs uppercase tracking-wide text-brass">{item.type.replace("_", " ")}</p> : null}
            <p className="font-medium">{item.question}</p>
            <p className="mt-1 text-stone-700">
              <span className="font-medium text-navy">{labels.answer}: </span>
              {item.answer}
            </p>
            {pageNote(item.pages, labels) ? <p className="text-xs text-stone-600">{pageNote(item.pages, labels)}</p> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function mcqList(title, items, labels) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ol className="mt-1 list-decimal pl-5">
        {items.map((item, index) => (
          <li key={index} className="mb-3">
            <p className="font-medium">{item.question}</p>
            {Array.isArray(item.options) ? (
              <ul className="mt-1 list-[upper-alpha] pl-5">
                {item.options.map((opt) => (
                  <li key={opt}>{opt}</li>
                ))}
              </ul>
            ) : null}
            <p className="mt-1 text-stone-700">
              <span className="font-medium text-navy">{labels.answer}: </span>
              {item.answer}
            </p>
            {pageNote(item.pages, labels) ? <p className="text-xs text-stone-600">{pageNote(item.pages, labels)}</p> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function citationMap(title, citations) {
  const entries = Object.entries(citations || {}).filter(([, pages]) => Array.isArray(pages) && pages.length);
  if (!entries.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ul className="mt-1 list-disc pl-5 text-sm">
        {entries.map(([name, pages]) => (
          <li key={name}>
            {name}: {pageNote(pages, { textbookPage: "page", textbookPages: "pages" })}
          </li>
        ))}
      </ul>
    </section>
  );
}

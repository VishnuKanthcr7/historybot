import { imageUrl } from "../services/api.js";

export default function EcontentPanel({ data, labels, onClose, onPdf, pdfLoading }) {
  if (!data) return null;
  const content = data.content || {};
  return (
    <aside className="max-h-[42vh] overflow-y-auto border-t border-rule bg-cream px-4 py-4 md:px-10">
      <div className="mx-auto flex max-w-2xl items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brass">{labels.econtent}</p>
          <h2 className="font-serif text-xl text-navy">{data.title}</h2>
        </div>
        <div className="flex gap-2">
          {data.id ? (
            <button
              type="button"
              className="min-h-10 border border-navy px-3 text-sm text-navy disabled:opacity-50"
              onClick={onPdf}
              disabled={pdfLoading}
            >
              {pdfLoading ? labels.pdfWorking : labels.downloadPdf}
            </button>
          ) : null}
          <button type="button" className="min-h-10 border border-rule px-3 text-sm" onClick={onClose}>
            {labels.close}
          </button>
        </div>
      </div>
      {!data.grounded ? (
        <p className="mx-auto mt-3 max-w-2xl text-sm">{data.message}</p>
      ) : (
        <div className="mx-auto mt-4 max-w-2xl space-y-4 text-sm leading-relaxed">
          {section(labels.introduction, content.introduction)}
          {listSection(labels.objectives, content.learning_objectives)}
          {section(labels.easyEnglish, content.easy_english)}
          {section(labels.simpleKannada, content.simple_kannada)}
          {section(labels.context, content.historical_context)}
          {namedList(labels.people, content.important_people, "name", "note")}
          {namedList(labels.terms, content.important_terms, "term", "meaning")}
          {namedList(labels.timeline, content.timeline, "when", "event")}
          {section(labels.detail, content.detailed_explanation)}
          {listSection(labels.keyPoints, content.key_points)}
          {qaList(labels.exam, content.exam_questions)}
          {section(labels.revision, content.revision)}
          {mcqList(labels.mcq, content.mcqs)}
          {(data.images || []).map((img) => (
            <figure key={img.id} className="border border-rule bg-paper p-2">
              <img src={imageUrl(img.id)} alt={img.alt} className="max-h-56 w-full object-contain" />
              <figcaption className="mt-1 text-xs text-stone-600">{img.title}</figcaption>
            </figure>
          ))}
        </div>
      )}
    </aside>
  );
}

function section(title, text) {
  if (!text) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <p className="mt-1 whitespace-pre-wrap">{text}</p>
    </section>
  );
}

function listSection(title, items) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ul className="mt-1 list-disc pl-5">
        {items.map((item) => (
          <li key={String(item)}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
        ))}
      </ul>
    </section>
  );
}

function namedList(title, items, a, b) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ul className="mt-1 list-disc pl-5">
        {items.map((item, index) => (
          <li key={`${item[a] || index}`}>
            <strong>{item[a]}</strong>
            {item[b] ? ` — ${item[b]}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

function qaList(title, items) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ol className="mt-1 list-decimal pl-5">
        {items.map((item, index) => (
          <li key={index} className="mb-2">
            <p>{item.question}</p>
            <p className="text-stone-600">{item.answer}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function mcqList(title, items) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <section>
      <h3 className="font-semibold text-navy">{title}</h3>
      <ol className="mt-1 list-decimal pl-5">
        {items.map((item, index) => (
          <li key={index} className="mb-2">
            <p>{item.question}</p>
            {Array.isArray(item.options) ? (
              <ul className="list-disc pl-5">
                {item.options.map((opt) => (
                  <li key={opt}>{opt}</li>
                ))}
              </ul>
            ) : null}
            <p className="text-stone-600">
              {item.answer}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

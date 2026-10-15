import { useId, useState } from "react";
import { formatSourcePages, LABELS } from "../i18n/labels.js";

// One row per retrieved passage: chapter, printed page and (when the answer engine sent it) a short
// quote, so a student can check where a "From your textbook" statement comes from.
function sourceRows(sources) {
  const seen = new Set();
  const rows = [];
  for (const item of sources || []) {
    const page = Number(item.printed_page_number ?? item.textbook_page_number);
    if (!Number.isFinite(page)) continue;
    const key = `${item.chapter || ""}|${page}|${item.excerpt || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({ key, page, chapter: item.chapter || "", excerpt: item.excerpt || "" });
  }
  return rows.sort((a, b) => a.page - b.page);
}

export default function SourceCite({ sources, language }) {
  const line = formatSourcePages(sources, language);
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (!line) return null;
  const t = LABELS[language] || LABELS.en;
  const rows = sourceRows(sources);
  const withExcerpts = rows.some((r) => r.excerpt);
  return (
    <div className="mt-3 border-t border-rule pt-2" data-testid="sources">
      <button
        type="button"
        className="min-h-10 text-sm font-medium text-navy"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {withExcerpts ? "Sources" : t.source}
        <span className="ml-2 text-xs font-normal text-muted">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div id={panelId} className="pb-1 text-sm leading-relaxed text-muted">
          <p>{line}</p>
          {withExcerpts ? (
            <ul className="mt-2 space-y-2" aria-label="Textbook passages used">
              {rows.map((r) => (
                <li key={r.key} className="rounded-xl border border-rule bg-paper px-3 py-2" data-testid="source-row">
                  <p className="text-xs font-semibold text-navy">
                    {r.chapter ? `${r.chapter}, ` : ""}page {r.page}
                  </p>
                  {r.excerpt ? <blockquote className="mt-1 text-xs italic leading-snug">“{r.excerpt}”</blockquote> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

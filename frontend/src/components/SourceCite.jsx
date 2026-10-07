import { useState } from "react";
import { formatSourcePages, LABELS } from "../i18n/labels.js";

export default function SourceCite({ sources, language }) {
  const line = formatSourcePages(sources, language);
  const [open, setOpen] = useState(false);
  if (!line) return null;
  const t = LABELS[language] || LABELS.en;
  return (
    <div className="mt-3 border-t border-rule pt-2">
      <button
        type="button"
        className="min-h-10 text-sm font-medium text-navy"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {t.source}
        <span className="ml-2 text-xs font-normal text-muted">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? <p className="pb-1 text-sm leading-relaxed text-muted">{line}</p> : null}
    </div>
  );
}

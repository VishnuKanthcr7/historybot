import { formatSourcePages, LABELS } from "../i18n/labels.js";

export default function SourceCite({ sources, language }) {
  const line = formatSourcePages(sources, language);
  if (!line) return null;
  const t = LABELS[language] || LABELS.en;
  return (
    <aside className="mt-3 border-t border-rule pt-3 text-sm text-stone-700">
      <p className="font-medium text-navy">{t.textbookSource}</p>
      <p className="mt-1">{line}</p>
    </aside>
  );
}

import { LABELS } from "../i18n/labels.js";

export default function HistorySidebar({ open, conversations, currentId, onOpen, onClose, labels }) {
  return (
    <>
      {open ? (
        <button
          type="button"
          className="fixed inset-0 z-20 bg-ink/30 md:hidden"
          aria-label={labels.closeMenu}
          onClick={onClose}
        />
      ) : null}
      <aside
        className={`z-30 w-64 shrink-0 border-r border-rule bg-cream p-4 md:static md:block ${
          open ? "fixed inset-y-0 left-0" : "hidden md:block"
        }`}
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-brass">{labels.history}</h2>
        <ul className="mt-3 space-y-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <li className="text-sm text-stone-500">{labels.emptyChat}</li>
          ) : (
            conversations.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onOpen(item.id)}
                  className={`w-full rounded px-2 py-2 text-left text-sm ${
                    item.id === currentId ? "bg-navy text-cream" : "hover:bg-paper"
                  }`}
                >
                  {item.title || LABELS.en.newChat}
                </button>
              </li>
            ))
          )}
        </ul>
      </aside>
    </>
  );
}

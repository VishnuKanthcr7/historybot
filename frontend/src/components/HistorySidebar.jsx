import { LABELS } from "../i18n/labels.js";

export default function HistorySidebar({ open, conversations, currentId, onOpen, onClose, labels }) {
  return (
    <>
      {open ? (
        <button
          type="button"
          className="fixed inset-0 z-20 bg-ink/35 md:hidden"
          aria-label={labels.closeMenu}
          onClick={onClose}
        />
      ) : null}
      <aside
        className={`z-30 flex w-[min(18rem,88vw)] shrink-0 flex-col border-r border-rule bg-cream p-3 md:static md:flex md:w-64 ${
          open ? "fixed inset-y-0 left-0 shadow-lg" : "hidden md:flex"
        }`}
        aria-label={labels.history}
      >
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
          {labels.history}
        </h2>
        <ul className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <li className="px-1 text-sm text-stone-500">{labels.emptyChat}</li>
          ) : (
            conversations.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onOpen(item.id)}
                  className={`min-h-11 w-full rounded-xl px-2.5 py-2 text-left text-sm leading-snug transition ${
                    item.id === currentId
                      ? "bg-navy text-cream"
                      : "text-ink hover:bg-paper"
                  }`}
                  aria-current={item.id === currentId ? "page" : undefined}
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

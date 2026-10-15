export const btn = "inline-flex min-h-11 items-center justify-center rounded-full px-4 text-sm disabled:opacity-40";
export const field = "min-h-11 rounded-2xl border border-rule bg-cream px-3 text-sm";

export function Card({ title, children, className = "", actions }) {
  return (
    <section className={`min-w-0 rounded-3xl border border-rule bg-cream p-4 ${className}`}>
      {title || actions ? (
        <div className="mb-2 flex min-w-0 flex-wrap items-center justify-between gap-2">
          {title ? <h2 className="font-serif text-xl text-navy">{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function ErrorText({ children }) {
  return children ? <p className="text-sm text-red-700" role="alert">{children}</p> : null;
}

export function Bars({ items, max = 100, suffix = "", label = (i) => i.label, value = (i) => i.value, note = () => "" }) {
  return (
    <ul className="space-y-2">
      {items.map((item, idx) => {
        const v = value(item);
        return (
          <li key={idx} className="text-sm">
            <div className="flex justify-between gap-2">
              <span className="truncate">{label(item)}</span>
              <span className="shrink-0 font-semibold tabular-nums">
                {v == null ? "—" : `${v}${suffix}`}
                <span className="ml-1 text-xs font-normal text-muted">{note(item)}</span>
              </span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-rule" aria-hidden="true">
              <div className="h-2 rounded-full bg-navy" style={{ width: `${max ? Math.min(100, ((v || 0) / max) * 100) : 0}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function RangePicker({ range, onChange }) {
  return (
    <div className="flex flex-wrap items-end gap-2 text-sm">
      <label className="flex flex-col text-xs text-muted">
        From
        <input type="date" className={field} value={range.from} max={range.to} onChange={(e) => onChange({ ...range, from: e.target.value })} />
      </label>
      <label className="flex flex-col text-xs text-muted">
        To
        <input type="date" className={field} value={range.to} min={range.from} onChange={(e) => onChange({ ...range, to: e.target.value })} />
      </label>
      <span className="pb-3 text-xs text-muted">Dates in IST</span>
    </div>
  );
}

export function istToday(offsetDays = 0) {
  return new Date(Date.now() + 330 * 60000 + offsetDays * 86400000).toISOString().slice(0, 10);
}

export function fmtDate(value) {
  return value ? new Date(value).toLocaleDateString() : "—";
}

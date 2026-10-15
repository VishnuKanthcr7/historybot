import { useState } from "react";

const optionBase =
  "flex min-h-11 w-full items-center gap-3 rounded-2xl border px-4 py-2 text-left text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brass";

function Choice({ selected, onClick, children, label }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-label={label}
      onClick={onClick}
      className={`${optionBase} ${selected ? "border-navy bg-navy/10 font-semibold text-navy" : "border-rule bg-cream hover:border-brass"}`}
    >
      <span
        aria-hidden="true"
        className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border ${selected ? "border-navy bg-navy" : "border-muted"}`}
      >
        {selected ? <span className="h-2 w-2 rounded-full bg-cream" /> : null}
      </span>
      <span>{children}</span>
    </button>
  );
}

function OrderInput({ question, value, onChange, disabled }) {
  const items = question.options || [];
  const order = Array.isArray(value) && value.length === items.length ? value : items.map((i) => i.id);
  const text = (id) => items.find((i) => i.id === id)?.text || id;
  const move = (index, delta) => {
    const next = [...order];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  return (
    <div>
      <p className="mb-2 text-xs text-muted">Use the arrows to move each item. Top = first.</p>
      <ol className="space-y-2" aria-label="Items in your order">
        {order.map((id, index) => (
          <li key={id} className="flex items-center gap-2 rounded-2xl border border-rule bg-cream px-3 py-2 text-sm">
            <span className="w-6 shrink-0 text-center font-semibold text-brass">{index + 1}</span>
            <span className="flex-1">{text(id)}</span>
            <button
              type="button"
              disabled={disabled || index === 0}
              onClick={() => move(index, -1)}
              aria-label={`Move "${text(id)}" up`}
              className="grid min-h-11 min-w-11 place-items-center rounded-full border border-rule text-navy disabled:opacity-30"
            >
              ↑
            </button>
            <button
              type="button"
              disabled={disabled || index === order.length - 1}
              onClick={() => move(index, 1)}
              aria-label={`Move "${text(id)}" down`}
              className="grid min-h-11 min-w-11 place-items-center rounded-full border border-rule text-navy disabled:opacity-30"
            >
              ↓
            </button>
          </li>
        ))}
      </ol>
      {!Array.isArray(value) ? (
        <button
          type="button"
          onClick={() => onChange(order)}
          className="mt-2 min-h-11 rounded-full border border-navy px-4 text-sm text-navy"
        >
          Keep this order
        </button>
      ) : null}
    </div>
  );
}

function MatchInput({ question, value, onChange, disabled }) {
  const left = question.options?.left || [];
  const right = question.options?.right || [];
  const pairs = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const [active, setActive] = useState(null);
  const usedBy = (rid) => Object.keys(pairs).find((l) => pairs[l] === rid);
  const pick = (rid) => {
    if (!active) return;
    const next = { ...pairs };
    const previous = usedBy(rid);
    if (previous) delete next[previous];
    next[active] = rid;
    onChange(next);
    const nextLeft = left.find((l) => !next[l.id]);
    setActive(nextLeft ? nextLeft.id : null);
  };
  return (
    <div>
      <p className="mb-2 text-xs text-muted">Tap an item on the left, then tap its match on the right.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <ul className="space-y-2" aria-label="Items to match">
          {left.map((l) => {
            const matched = right.find((r) => r.id === pairs[l.id]);
            return (
              <li key={l.id}>
                <button
                  type="button"
                  disabled={disabled}
                  aria-pressed={active === l.id}
                  onClick={() => setActive(l.id)}
                  className={`${optionBase} flex-col items-start ${active === l.id ? "border-navy bg-navy/10" : "border-rule bg-cream"}`}
                >
                  <span className="font-semibold text-navy">{l.text}</span>
                  <span className="text-xs text-muted">{matched ? `→ ${matched.text}` : "Not matched yet"}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <ul className="space-y-2" aria-label="Possible matches">
          {right.map((r) => {
            const owner = usedBy(r.id);
            return (
              <li key={r.id}>
                <button
                  type="button"
                  disabled={disabled || !active}
                  onClick={() => pick(r.id)}
                  className={`${optionBase} ${owner ? "border-brass bg-brass/10" : "border-rule bg-cream"} disabled:cursor-not-allowed`}
                >
                  {r.text}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      {!active ? <p className="mt-2 text-xs text-muted">Choose a left-hand item to change a match.</p> : null}
    </div>
  );
}

export default function QuestionInput({ question, value, onChange, disabled = false }) {
  if (question.qtype === "mcq") {
    return (
      <div role="radiogroup" aria-label="Answer choices" className="space-y-2">
        {(question.options || []).map((o) => (
          <Choice key={o.id} selected={value === o.id} onClick={() => !disabled && onChange(o.id)}>
            {o.text}
          </Choice>
        ))}
      </div>
    );
  }
  if (question.qtype === "true_false") {
    return (
      <div role="radiogroup" aria-label="True or false" className="grid grid-cols-2 gap-2">
        <Choice selected={value === true} onClick={() => !disabled && onChange(true)}>
          True
        </Choice>
        <Choice selected={value === false} onClick={() => !disabled && onChange(false)}>
          False
        </Choice>
      </div>
    );
  }
  if (question.qtype === "fill_blank") {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-xs text-muted">Type the missing word or words</span>
        <input
          type="text"
          value={typeof value === "string" ? value : ""}
          maxLength={100}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="min-h-11 w-full rounded-2xl border border-rule bg-cream px-4 text-base focus:border-navy focus:outline-none"
          autoComplete="off"
        />
      </label>
    );
  }
  if (question.qtype === "order") return <OrderInput question={question} value={value} onChange={onChange} disabled={disabled} />;
  if (question.qtype === "match") return <MatchInput question={question} value={value} onChange={onChange} disabled={disabled} />;
  return <p className="text-sm text-muted">This question type is not supported.</p>;
}

export function answerText(question, answer) {
  if (answer == null || answer === "") return "No answer";
  switch (question.qtype) {
    case "mcq":
      return (question.options || []).find((o) => o.id === answer)?.text || String(answer);
    case "true_false":
      return answer === true ? "True" : answer === false ? "False" : String(answer);
    case "fill_blank":
      return Array.isArray(answer) ? answer[0] : String(answer);
    case "order":
      return Array.isArray(answer)
        ? answer.map((id, i) => `${i + 1}. ${(question.options || []).find((o) => o.id === id)?.text || id}`).join("  ")
        : "No answer";
    case "match": {
      const left = question.options?.left || [];
      const right = question.options?.right || [];
      if (!answer || typeof answer !== "object") return "No answer";
      return left
        .map((l) => `${l.text} → ${right.find((r) => r.id === answer[l.id])?.text || "—"}`)
        .join("; ");
    }
    default:
      return String(answer);
  }
}

export function isAnswered(question, value) {
  if (value == null) return false;
  if (question.qtype === "fill_blank") return typeof value === "string" && value.trim().length > 0;
  if (question.qtype === "match") {
    const left = question.options?.left || [];
    return typeof value === "object" && left.length > 0 && left.every((l) => value[l.id]);
  }
  if (question.qtype === "order") return Array.isArray(value);
  return true;
}

export const ACTIVITY_LABELS = {
  quiz: "Quiz",
  history_challenge: "History Challenge",
  beat_the_clock: "Beat the Clock",
  timeline: "Timeline",
  match_figure: "Match the Figure",
  find_correct: "Find the Correct Answer",
  revision: "Revision Challenge",
  checkpoint: "Module checkpoint",
};

export function formatSeconds(total) {
  const s = Math.max(0, Math.round(total || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function PageShell({ eyebrow, title, children, actions }) {
  return (
    <div className="min-h-dvh bg-paper px-3 py-6 font-sans text-ink sm:px-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            {eyebrow ? <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brass">{eyebrow}</p> : null}
            <h1 className="mt-1 font-serif text-3xl text-navy">{title}</h1>
          </div>
          <div className="flex flex-wrap gap-2">{actions}</div>
        </div>
        {children}
      </div>
    </div>
  );
}

// Clear labels for how a quiz counts: practice vs assessment, pre/post-test, and draft (teacher only).
export function QuizBadges({ quiz, showStatus = false }) {
  const badges = [];
  if (showStatus && quiz.status && quiz.status !== "published") {
    badges.push([quiz.status === "draft" ? "Draft (students cannot see)" : "Archived", "border border-dashed border-muted text-muted"]);
  }
  badges.push(quiz.mode === "assessment" ? ["Assessment", "bg-navy text-cream"] : ["Practice", "bg-brass/15 text-navydeep"]);
  if (quiz.assessment_phase === "pre") badges.push(["Pre-test", "bg-sky-100 text-sky-900"]);
  if (quiz.assessment_phase === "post") badges.push(["Post-test", "bg-violet-100 text-violet-900"]);
  return (
    <>
      {badges.map(([text, cls]) => (
        <span key={text} className={`rounded-full px-2 py-0.5 ${cls}`}>
          {text}
        </span>
      ))}
    </>
  );
}

import { useState } from "react";

export default function ChatComposer({ disabled, onSend, labels }) {
  const [value, setValue] = useState("");

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      className="shrink-0 border-t border-rule bg-cream px-3 py-3 md:px-8"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="composer" className="sr-only">
        {labels.composerLabel}
      </label>
      <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border border-rule bg-paper p-2 focus-within:border-navy">
        <textarea
          id="composer"
          rows={2}
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value.slice(0, 2000))}
          onKeyDown={onKeyDown}
          placeholder={labels.askPlaceholderHome || labels.ask}
          className="max-h-36 min-h-12 min-w-0 flex-1 resize-none bg-transparent px-2 py-2 text-base outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="mb-0.5 min-h-11 min-w-11 rounded-xl bg-navy px-4 text-sm font-medium text-cream disabled:opacity-40"
          aria-label={labels.send}
        >
          {labels.send}
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-2xl text-[11px] text-muted">
        Enter to send · Shift+Enter for a new line
      </p>
    </form>
  );
}

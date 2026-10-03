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
      className="shrink-0 border-t border-rule bg-cream px-4 py-3 md:px-10"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="composer" className="sr-only">
        {labels.composerLabel}
      </label>
      <div className="mx-auto flex max-w-2xl items-end gap-3">
        <textarea
          id="composer"
          rows={2}
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value.slice(0, 2000))}
          onKeyDown={onKeyDown}
          placeholder={labels.ask}
          className="min-h-[3rem] flex-1 resize-none border border-rule bg-paper px-3 py-2"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="min-h-12 min-w-16 bg-navy px-4 text-sm font-semibold text-cream disabled:opacity-50"
        >
          {labels.send}
        </button>
      </div>
    </form>
  );
}

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
      className="shrink-0 border-t border-rule bg-cream/95 px-3 py-3 backdrop-blur md:px-8"
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
          className="min-h-[3rem] flex-1 resize-none border border-rule bg-paper px-3 py-2 text-[15px] outline-none focus:border-navy"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="min-h-12 min-w-[4.5rem] bg-navy px-4 text-sm font-semibold tracking-wide text-cream transition hover:bg-navydeep disabled:opacity-50"
        >
          {labels.send}
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-2xl text-[11px] text-stone-500">
        Answers stay inside the Class 9 textbook. Press Enter to send · Shift+Enter for a new line.
      </p>
    </form>
  );
}

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { LABELS } from "../i18n/labels.js";

export default function Home() {
  const navigate = useNavigate();
  const { language, setLanguage } = useApp();
  const t = LABELS[language];
  const [query, setQuery] = useState("");

  function start(event) {
    event?.preventDefault();
    const q = query.trim();
    navigate(q ? `/chat?q=${encodeURIComponent(q)}` : "/chat");
  }

  return (
    <div className="min-h-screen bg-paper text-ink font-sans">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="border-b border-rule/80 bg-cream/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="group flex items-baseline gap-2">
            <span className="font-serif text-2xl tracking-tight text-navy sm:text-[1.65rem]">
              HistoryBot
            </span>
            <span className="hidden text-[10px] uppercase tracking-[0.2em] text-brass sm:inline">
              Class 9 · Karnataka
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <label htmlFor="home-lang" className="sr-only">
              {t.language}
            </label>
            <select
              id="home-lang"
              className="min-h-10 rounded-sm border border-rule bg-cream px-2 py-1 text-sm text-navy"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="en">{t.english}</option>
              <option value="kn">{t.kannada}</option>
            </select>
            <Link
              to="/chat"
              className="hidden min-h-10 items-center border border-navy px-3 text-sm font-medium text-navy hover:bg-navy hover:text-cream sm:inline-flex"
            >
              {t.start}
            </Link>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="relative overflow-hidden border-b border-rule bg-cream">
          <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-1/3 bg-gradient-to-l from-navy/[0.04] to-transparent md:block" />
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.15fr_0.85fr] md:items-center md:py-16">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-brass">
                Prescribed textbook learning · PhD research demo
              </p>
              <h1 className="mt-3 max-w-xl font-serif text-[2.35rem] leading-tight text-navy sm:text-5xl">
                {t.brand}
              </h1>
              <p className="mt-2 text-lg text-navydeep/90">{t.tagline}</p>
              <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-stone-700">
                Ask questions from the prescribed Class 9 Karnataka State Board History textbook.
                HistoryBot answers from the textbook only and cites printed page numbers — never
                Wikipedia or invents facts.
              </p>
              <ul className="mt-6 flex flex-wrap gap-2 text-xs text-stone-600">
                {["Textbook-grounded", "Page citations", "Learning modules", "Exam practice"].map(
                  (chip) => (
                    <li
                      key={chip}
                      className="rounded-full border border-rule bg-paper px-3 py-1 tracking-wide"
                    >
                      {chip}
                    </li>
                  )
                )}
              </ul>
            </div>
            <form
              onSubmit={start}
              className="academic-panel border border-rule bg-paper p-5 shadow-sm sm:p-6"
            >
              <label htmlFor="home-ask" className="block text-sm font-semibold text-navy">
                {t.ask}
              </label>
              <p className="mt-1 text-xs text-stone-500">
                Example: Who was Baji Rao? · Explain Akbar in detail · 10 MCQs on Shivaji
              </p>
              <input
                id="home-ask"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t.askPlaceholderHome}
                className="mt-3 min-h-12 w-full border border-rule bg-cream px-3 py-2 text-[15px] outline-none focus:border-navy"
                autoComplete="off"
              />
              <button
                type="submit"
                className="mt-4 min-h-11 w-full bg-navy px-4 text-sm font-semibold tracking-wide text-cream transition hover:bg-navydeep"
              >
                {t.start}
              </button>
            </form>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <h2 className="font-serif text-2xl text-navy sm:text-[1.75rem]">{t.howTitle}</h2>
          <ol className="mt-6 grid gap-4 sm:grid-cols-3">
            {[t.how1, t.how2, t.how3].map((item, index) => (
              <li key={item} className="academic-panel border border-rule bg-cream p-5">
                <p className="font-serif text-2xl text-brass/80">{String(index + 1).padStart(2, "0")}</p>
                <p className="mt-3 text-sm leading-relaxed text-stone-700">{item}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-rule bg-cream">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
            <h2 className="font-serif text-2xl text-navy">Research context</h2>
            <div className="mt-8 grid gap-8 md:grid-cols-2">
              <div className="academic-panel border border-rule bg-paper p-5">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brass">
                  Research scholar
                </h3>
                <p className="mt-3 font-serif text-xl text-navy">Pandurang Vajranthi</p>
                <p className="mt-1 text-sm text-stone-600">Reg. No.: PHD23EDR09</p>
                <p className="text-sm text-stone-600">Research Scholar, VSKU Bellary</p>
              </div>
              <div className="academic-panel border border-rule bg-paper p-5">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brass">
                  Guide
                </h3>
                <p className="mt-3 font-serif text-xl text-navy">Dr. Sushma N. Jogan</p>
                <p className="mt-1 text-sm text-stone-600">Assistant Professor</p>
                <p className="text-sm text-stone-600">
                  Department of Studies in Education, VSKU Bellary
                </p>
              </div>
            </div>
            <p className="mt-8 max-w-3xl border-l-2 border-brass/50 pl-4 text-sm leading-relaxed text-stone-700">
              Research topic: “The Impact of Crossover Instructional Modules through Artificial
              Intelligence on Digital Attitude, Social Engagement and Academic Achievement in Social
              Science at Secondary Level.”
            </p>
          </div>
        </section>
      </main>
      <footer className="border-t border-rule px-4 py-5 text-center text-xs text-stone-500 sm:px-6">
        HistoryBot · textbook-grounded classroom assistant · not a general internet chatbot
      </footer>
    </div>
  );
}

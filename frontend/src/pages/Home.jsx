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
    <div className="min-h-screen bg-paper text-ink">
      <header className="border-b border-rule bg-cream">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link to="/" className="font-serif text-2xl tracking-tight text-navy">
            HistoryBot
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <label htmlFor="home-lang" className="sr-only">
              {t.language}
            </label>
            <select
              id="home-lang"
              className="rounded border border-rule bg-cream px-2 py-1"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="en">{t.english}</option>
              <option value="kn">{t.kannada}</option>
            </select>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-16">
        <p className="text-sm uppercase tracking-[0.18em] text-brass">Karnataka State Board · Class 9</p>
        <h1 className="mt-3 font-serif text-4xl text-navy md:text-5xl">{t.brand}</h1>
        <p className="mt-3 max-w-2xl text-lg text-navydeep">{t.tagline}</p>
        <p className="mt-6 max-w-2xl leading-relaxed text-stone-700">
          Ask questions from the prescribed Class 9 Karnataka State Board History textbook. HistoryBot
          answers from the textbook only and shows the printed page number. It is not a general-purpose
          chatbot.
        </p>

        <form onSubmit={start} className="mt-10 max-w-2xl">
          <label htmlFor="home-ask" className="block text-sm font-medium text-navy">
            {t.ask}
          </label>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
            <input
              id="home-ask"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.askPlaceholderHome}
              className="min-h-12 flex-1 rounded border border-rule bg-cream px-4 py-3"
            />
            <button
              type="submit"
              className="min-h-12 rounded bg-navy px-6 text-sm font-semibold text-cream hover:bg-navydeep"
            >
              {t.start}
            </button>
          </div>
        </form>

        <section className="mt-16 border-t border-rule pt-10">
          <h2 className="font-serif text-2xl text-navy">Research context</h2>
          <div className="mt-6 grid gap-10 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-brass">Research scholar</h3>
              <p className="mt-2 font-medium">Pandurang Vajranthi</p>
              <p className="text-sm text-stone-600">Reg. No.: PHD23EDR09</p>
              <p className="text-sm text-stone-600">Research Scholar, VSKU Bellary</p>
            </div>
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-brass">Guide</h3>
              <p className="mt-2 font-medium">Dr. Sushma N. Jogan</p>
              <p className="text-sm text-stone-600">Assistant Professor</p>
              <p className="text-sm text-stone-600">Department of Studies in Education, VSKU Bellary</p>
            </div>
          </div>
          <p className="mt-8 max-w-3xl text-sm leading-relaxed text-stone-700">
            Research topic: “The Impact of Crossover Instructional Modules through Artificial Intelligence
            on Digital Attitude, Social Engagement and Academic Achievement in Social Science at Secondary
            Level.”
          </p>
        </section>
      </main>
    </div>
  );
}

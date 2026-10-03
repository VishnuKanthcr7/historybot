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
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-3">
          <Link to="/" className="font-serif text-2xl tracking-tight text-navy">
            HistoryBot
          </Link>
          <label htmlFor="home-lang" className="sr-only">
            {t.language}
          </label>
          <select
            id="home-lang"
            className="min-h-10 rounded border border-rule bg-cream px-2 py-1 text-sm"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="en">{t.english}</option>
            <option value="kn">{t.kannada}</option>
          </select>
        </div>
      </header>

      <main>
        <section className="border-b border-rule bg-cream">
          <div className="mx-auto grid max-w-5xl gap-8 px-5 py-10 md:grid-cols-[1.2fr_0.8fr] md:items-end">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-brass">
                Karnataka State Board · Class 9
              </p>
              <h1 className="mt-2 font-serif text-4xl text-navy md:text-5xl">{t.brand}</h1>
              <p className="mt-2 text-lg text-navydeep">{t.tagline}</p>
              <p className="mt-4 max-w-xl leading-relaxed text-stone-700">
                Ask questions from the prescribed Class 9 Karnataka State Board History textbook.
                HistoryBot answers from the textbook only and cites printed page numbers.
              </p>
            </div>
            <form onSubmit={start} className="border border-rule bg-paper p-4">
              <label htmlFor="home-ask" className="block text-sm font-medium text-navy">
                {t.ask}
              </label>
              <input
                id="home-ask"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t.askPlaceholderHome}
                className="mt-2 min-h-12 w-full border border-rule bg-cream px-3 py-2"
              />
              <button
                type="submit"
                className="mt-3 min-h-11 w-full bg-navy px-4 text-sm font-semibold text-cream hover:bg-navydeep"
              >
                {t.start}
              </button>
            </form>
          </div>
        </section>

        <section className="mx-auto max-w-5xl px-5 py-10">
          <h2 className="font-serif text-2xl text-navy">{t.howTitle}</h2>
          <ol className="mt-5 grid gap-4 md:grid-cols-3">
            {[t.how1, t.how2, t.how3].map((item, index) => (
              <li key={item} className="border border-rule bg-cream p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-brass">
                  {index + 1}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-stone-700">{item}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-rule bg-cream">
          <div className="mx-auto max-w-5xl px-5 py-10">
            <h2 className="font-serif text-2xl text-navy">Research context</h2>
            <div className="mt-6 grid gap-8 md:grid-cols-2">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-brass">
                  Research scholar
                </h3>
                <p className="mt-2 font-medium">Pandurang Vajranthi</p>
                <p className="text-sm text-stone-600">Reg. No.: PHD23EDR09</p>
                <p className="text-sm text-stone-600">Research Scholar, VSKU Bellary</p>
              </div>
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-brass">Guide</h3>
                <p className="mt-2 font-medium">Dr. Sushma N. Jogan</p>
                <p className="text-sm text-stone-600">Assistant Professor</p>
                <p className="text-sm text-stone-600">
                  Department of Studies in Education, VSKU Bellary
                </p>
              </div>
            </div>
            <p className="mt-6 max-w-3xl text-sm leading-relaxed text-stone-700">
              Research topic: “The Impact of Crossover Instructional Modules through Artificial
              Intelligence on Digital Attitude, Social Engagement and Academic Achievement in Social
              Science at Secondary Level.”
            </p>
          </div>
        </section>
      </main>
      <footer className="border-t border-rule px-5 py-4 text-center text-xs text-stone-500">
        HistoryBot · textbook-grounded classroom assistant · not a general internet chatbot
      </footer>
    </div>
  );
}

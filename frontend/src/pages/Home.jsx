import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { LABELS } from "../i18n/labels.js";

const SUGGESTIONS = [
  "Who was Akbar?",
  "Why did Sher Shah defeat Humayun?",
  "Explain the Mansabdari system.",
  "Compare Akbar and Aurangzeb.",
];

export default function Home() {
  const navigate = useNavigate();
  const { language, setLanguage, beginFreshChat } = useApp();
  const t = LABELS[language];
  const [query, setQuery] = useState("");

  function openChat(text) {
    const q = (text ?? query).trim();
    beginFreshChat();
    navigate(q ? `/chat?q=${encodeURIComponent(q)}` : "/chat?fresh=1");
  }

  function start(event) {
    event?.preventDefault();
    openChat();
  }

  function startLearning(event) {
    event?.preventDefault();
    beginFreshChat();
    navigate("/chat?fresh=1");
  }

  return (
    <div id="top" className="home-page min-h-screen font-sans">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <section className="home-hero">
        <div className="home-hero-media">
          <img
            src="/historybot-panorama.jpg"
            alt="A traditional Indian classroom opening into a modern classroom, with history books and a map across the foreground."
          />
          <div className="home-hero-veil" />
        </div>

        <header className="home-bar">
          <div className="home-bar-row">
            <Link to="/" className="home-brand">
              <img
                className="home-emblem"
                src="/vsku-emblem.png"
                alt="Vijayanagara Sri Krishnadevaraya University emblem"
              />
              <span>
                <span className="home-brand-name">HistoryBot</span>
                <span className="home-brand-sub">Class 9 · Social Science</span>
                <span className="home-brand-board">Karnataka State Board</span>
              </span>
            </Link>
            <nav className="home-nav" aria-label="Page">
              <a href="#top">Home</a>
              <a href="#about">About</a>
              <a href="#how">How to Use</a>
            </nav>
            <div className="home-bar-actions">
              <label htmlFor="home-lang" className="sr-only">
                {t.language}
              </label>
              <select
                id="home-lang"
                className="home-lang"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="en">{t.english}</option>
                <option value="kn">{t.kannada}</option>
              </select>
              <button type="button" className="home-start" onClick={startLearning}>
                Start Learning →
              </button>
            </div>
          </div>
          <p className="home-bar-meta">
            <span>Class 9 · Social Science</span>
            <span>Karnataka State Board</span>
          </p>
          <nav className="home-nav-mobile" aria-label="Page">
            <a href="#top">Home</a>
            <a href="#about">About</a>
            <a href="#how">How to Use</a>
          </nav>
        </header>

        <div className="home-hero-body" id="main">
          <div className="home-hero-copy home-rise">
            <p className="home-kicker">
              <span>Class 9 · Social Science</span>
              <span>Karnataka State Board</span>
            </p>
            <h1>
              Explore History
              <em>with Intelligence.</em>
            </h1>
            <p className="home-lead">AI-powered learning for Class 9 Social Science.</p>
            <p className="home-support">
              Ask questions, explore historical ideas, and learn with clear explanations supported by
              your learning material.
            </p>

            <form onSubmit={start}>
              <label htmlFor="home-ask" className="sr-only">
                {t.ask}
              </label>
              <div className="home-search">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
                  <path d="M16 16.5 20 20.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                </svg>
                <input
                  id="home-ask"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ask anything about History or Social Science..."
                  autoComplete="off"
                />
                <button type="submit" aria-label="Ask HistoryBot">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
                    <path d="M5 12h12M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
            </form>

            <ul className="home-chips">
              {SUGGESTIONS.map((item) => (
                <li key={item}>
                  <button type="button" onClick={() => openChat(item)}>
                    {item}
                  </button>
                </li>
              ))}
            </ul>

            <p className="home-journey" aria-label="From Traditional Roots to an AI-Enabled Future">
              <span className="home-journey-roots">From Traditional Roots</span>
              <span className="home-journey-line" aria-hidden="true" />
              <span className="home-journey-mid">History · Knowledge · Learning</span>
              <span className="home-journey-line" aria-hidden="true" />
              <span className="home-journey-future">to an AI-Enabled Future</span>
            </p>
          </div>

          <aside className="home-badge" aria-label="Academic identity">
            <p>
              <span className="home-badge-kicker">VSKU Ballari</span>
              <strong>Department of Studies in Education</strong>
            </p>
            <p>
              <span className="home-badge-kicker">Research Scholar</span>
              <strong>Pandurang Vajranthi</strong>
            </p>
            <p>
              <span className="home-badge-kicker">Guide</span>
              <strong>Dr. Sushma N. Jogan</strong>
            </p>
            <p className="home-badge-note">
              <strong>HistoryBot</strong>
              {" — "}
              AI-powered learning companion for Class 9 Social Science.
            </p>
          </aside>
        </div>
      </section>

      <section id="how" className="home-how">
        <p className="home-how-kicker text-center">Three steps</p>
        <h2>How HistoryBot Works</h2>
        <ol className="home-steps">
          <li>
            <span className="home-step-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path d="M16 16.5 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </span>
            <span>01</span>
            <h3>Ask</h3>
            <p>Ask a question about your lesson.</p>
          </li>
          <li>
            <span className="home-step-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M6 5.5h9.5A2.5 2.5 0 0 1 18 8v11H8.5A2.5 2.5 0 0 0 6 16.5Z" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path d="M6 5.5A2.5 2.5 0 0 1 8.5 8H18" fill="none" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </span>
            <span>02</span>
            <h3>Explore</h3>
            <p>HistoryBot understands the question and explains it clearly.</p>
          </li>
          <li>
            <span className="home-step-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M9 18h6M10 18a4.5 4.5 0 0 1-1.2-6.2 5 5 0 1 1 6.4 0A4.5 4.5 0 0 1 14 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </span>
            <span>03</span>
            <h3>Learn</h3>
            <p>Use the answer, textbook references and additional historical context when relevant.</p>
          </li>
        </ol>
      </section>

      <section id="about" className="home-study">
        <div className="home-study-panel">
          <img
            className="home-campus"
            src="/vsku-campus.png"
            alt="Vijayanagara Sri Krishnadevaraya University campus in Ballari"
          />
          <div className="home-study-main">
            <img
              className="home-vsku-banner"
              src="/vsku-banner.png"
              alt="Vijayanagara Sri Krishnadevaraya University, Bellary"
            />
            <p className="home-study-kicker">Institution</p>
            <h2>Vijayanagara Sri Krishnadevaraya University, Ballari</h2>
            <p className="home-study-dept">Department of Studies in Education</p>
            <div className="home-study-people">
              <p>
                <span className="home-study-kicker">Research Scholar</span>
                <strong>Pandurang Vajranthi</strong>
              </p>
              <p>
                <span className="home-study-kicker">Guide</span>
                <strong>Dr. Sushma N. Jogan</strong>
              </p>
            </div>
            <p className="home-study-kicker">Research Topic</p>
            <p className="home-topic">
              The Impact of Crossover Instructional Modules through Artificial Intelligence on Digital
              Attitude, Social Engagement and Academic Achievement in Social Science at Secondary Level.
            </p>
          </div>
        </div>
      </section>

      <footer className="home-foot">HistoryBot · VSKU Ballari · Department of Studies in Education</footer>
    </div>
  );
}

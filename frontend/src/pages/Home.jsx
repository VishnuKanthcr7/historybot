import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { LABELS } from "../i18n/labels.js";
import AccountMenu from "../components/AccountMenu.jsx";
import { stashPendingQuestion } from "../pendingQuestion.js";
import { RESEARCH } from "../config/research.js";
import "./Home.css";

const SUGGESTIONS = [
  { text: "Who was Akbar?", icon: "crown" },
  { text: "Why did Sher Shah defeat Humayun?", icon: "swords" },
  { text: "Explain the Mansabdari system.", icon: "book" },
  { text: "Compare Akbar and Aurangzeb.", icon: "people" },
];

const STEPS = [
  { no: "01", icon: "chat", title: "Ask", text: "Ask a question about your lesson." },
  {
    no: "02",
    icon: "book",
    title: "Explore",
    text: "Read an explanation grounded in the textbook, with the printed page numbers.",
  },
  {
    no: "03",
    icon: "pdf",
    title: "Learn",
    text: "Open a learning module and download a PDF when you want to revise.",
  },
];

const FEATURES = [
  {
    icon: "chat",
    title: "Textbook-grounded answers",
    text: "Answers come from the Class 9 Karnataka State Board textbook and show the chapter and printed page.",
  },
  {
    icon: "pdf",
    title: "Learning modules and PDFs",
    text: "Open a short learning module on a topic and download it as a PDF to revise.",
  },
  {
    icon: "book",
    title: "Quizzes",
    text: "Take quizzes set by your teacher and see your score and the correct answers.",
  },
  {
    icon: "people",
    title: "Teacher dashboard",
    text: "Teachers see class activity, quiz results and progress reports for the research study.",
  },
];
export default function Home() {
  const navigate = useNavigate();
  const { language, setLanguage, beginFreshChat, user } = useApp();
  const t = LABELS[language];
  const [menuOpen, setMenuOpen] = useState(false);
  const menuBtnRef = useRef(null);
  const panelRef = useRef(null);
  const wasOpen = useRef(false);

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  // Mobile menu: lock page scroll, move focus into the panel, trap Tab inside
  // it, close on Escape, and hand focus back to the Menu button on close.
  useEffect(() => {
    if (!menuOpen) {
      if (wasOpen.current) {
        wasOpen.current = false;
        menuBtnRef.current?.focus();
      }
      return undefined;
    }
    wasOpen.current = true;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    const panel = panelRef.current;
    panel?.querySelector("[data-autofocus]")?.focus();

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = [...panel.querySelectorAll("a[href], button, select")].filter(
        (el) => !el.disabled && el.offsetParent !== null
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (!panel.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      root.style.overflow = previousOverflow;
    };
  }, [menuOpen]);

  // the menu is only offered below the desktop breakpoint; close it if the
  // window grows past it while open
  useEffect(() => {
    if (!menuOpen || typeof window.matchMedia !== "function") return undefined;
    const wide = window.matchMedia("(min-width: 1200px)");
    const onChange = (event) => {
      if (event.matches) setMenuOpen(false);
    };
    wide.addEventListener?.("change", onChange);
    return () => wide.removeEventListener?.("change", onChange);
  }, [menuOpen]);

  function openChat(text) {
    const q = String(text || "").trim();
    if (!user) {
      stashPendingQuestion(q);
      setMenuOpen(false);
      navigate("/start");
      return;
    }
    beginFreshChat();
    navigate(q ? `/chat?q=${encodeURIComponent(q)}` : "/chat?fresh=1");
  }

  function startLearning(event) {
    event?.preventDefault();
    if (!user) {
      stashPendingQuestion("");
      setMenuOpen(false);
      navigate("/start");
      return;
    }
    beginFreshChat();
    navigate("/chat?fresh=1");
  }

  return (
    <div id="top" className="hb-page">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <header className="hb-bar">
        <div className="hb-bar-row">
          <Link to="/" className="hb-brand" onClick={() => setMenuOpen(false)}>
            <picture>
              <source srcSet="/images/vsku-emblem-small.webp" type="image/webp" />
              <img
                className="hb-emblem-mark"
                src="/images/vsku-emblem-small.png"
                alt="Vijayanagara Sri Krishnadevaraya University emblem"
                width="320"
                height="320"
                decoding="async"
              />
            </picture>
            <span className="hb-brand-rule" aria-hidden="true" />
            <BookMark className="hb-brand-book" />
            <span className="hb-brand-text">
              <span className="hb-brand-name">HistoryBot</span>
              <span className="hb-brand-tag">AI for a Brighter Understanding of History</span>
            </span>
          </Link>

          <nav className="hb-nav" aria-label="Page">
            <a href="#top" aria-current="page">
              Home
            </a>
            <a href="#about">About</a>
            <a href="#features">Features</a>
            <a href="#how">How to Use</a>
          </nav>

          <button
            ref={menuBtnRef}
            type="button"
            className="hb-menu-btn"
            aria-expanded={menuOpen}
            aria-controls="home-menu"
            aria-haspopup="dialog"
            onClick={() => setMenuOpen(true)}
          >
            <span className="hb-menu-icon" aria-hidden="true" />
            Menu
          </button>
          <div className="hb-bar-actions">
            <label htmlFor="home-lang" className="sr-only">
              {t.language}
            </label>
            <select
              id="home-lang"
              className="hb-lang"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="en">{t.english}</option>
              <option value="kn">{t.kannada}</option>
            </select>
            <div className="hb-bar-auth">
              <AccountMenu variant="home" />
            </div>
            <button type="button" className="hb-start" onClick={startLearning}>
              Start Learning
              <Arrow />
            </button>
          </div>
        </div>
        <div id="home-menu" className="hb-drawer" hidden={!menuOpen}>
          <div className="hb-drawer-backdrop" aria-hidden="true" onClick={closeMenu} />
          <div
            ref={panelRef}
            className="hb-drawer-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="home-menu-title"
          >
            <div className="hb-drawer-head">
              <p id="home-menu-title" className="hb-drawer-title">
                Menu
              </p>
              <button
                type="button"
                className="hb-drawer-close"
                aria-label="Close menu"
                data-autofocus
                onClick={closeMenu}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M6 6l12 12M18 6L6 18"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
            <div className="hb-drawer-group" role="group" aria-labelledby="home-menu-accounts">
              <p id="home-menu-accounts" className="hb-drawer-label">
                Accounts
              </p>
              <div className="hb-drawer-auth" onClickCapture={closeMenu}>
                <AccountMenu variant="home" teacherLabel="Teacher / Admin Login" />
              </div>
            </div>
            <div className="hb-drawer-group">
              <p className="hb-drawer-label" aria-hidden="true">
                On this page
              </p>
              <nav aria-label="Page" className="hb-drawer-nav">
                <a href="#top" onClick={closeMenu}>
                  Home
                </a>
                <a href="#about" onClick={closeMenu}>
                  About
                </a>
                <a href="#features" onClick={closeMenu}>
                  Features
                </a>
                <a href="#how" onClick={closeMenu}>
                  How to Use
                </a>
              </nav>
            </div>
            <div className="hb-drawer-lang">
              <label htmlFor="home-lang-menu">{t.language}</label>
              <select
                id="home-lang-menu"
                className="hb-lang"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="en">{t.english}</option>
                <option value="kn">{t.kannada}</option>
              </select>
            </div>
            <button type="button" className="hb-start hb-drawer-start" onClick={startLearning}>
              Start Learning
              <Arrow />
            </button>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="hb-hero" aria-labelledby="home-title">
          <div className="hb-stage">
            <div className="hb-hero-inner">
              <div className="hb-hero-copy">
                <div className="hb-ornament" aria-hidden="true">
                  <BookMark />
                  <span className="hb-ornament-line" />
                </div>
                <h1 id="home-title">
                  <span className="hb-h1-line">Your AI</span>
                  <span className="hb-h1-line">
                    <em>History</em> Companion
                  </span>
                </h1>
                <p className="hb-lead">
                  Ask questions. Explore history. Learn from your Class 9 Karnataka State Board
                  textbook.
                </p>
              </div>

              <figure className="hb-scene">
                <div className="hb-figures">
                  <picture className="hb-fig-shivaji">
                    <source srcSet="/images/shivaji-portrait.webp" type="image/webp" />
                    <img
                      src="/images/shivaji-portrait.jpg"
                      alt="Portrait of Chhatrapati Shivaji Maharaj."
                      width="200"
                      height="244"
                      decoding="async"
                    />
                  </picture>
                  <picture className="hb-fig-bot">
                    <source srcSet="/images/historybot-robot.webp" type="image/webp" />
                    <img
                      src="/images/historybot-robot.png"
                      alt="HistoryBot robot reading the Karnataka State Board Class 9 Social Science History textbook."
                      width="542"
                      height="600"
                      decoding="async"
                      fetchPriority="high"
                    />
                  </picture>
                </div>
              </figure>

              <div className="hb-cta-row">
                <button type="button" className="hb-cta" onClick={startLearning}>
                  Start Learning
                  <span className="hb-cta-arrow" aria-hidden="true">
                    <Arrow />
                  </span>
                </button>
                <a className="hb-cta-quiet" href="#how">
                  <BookMark />
                  Explore History
                </a>
              </div>

              <ul className="hb-examples" aria-label="Suggested questions">
                {SUGGESTIONS.map((item) => (
                  <li key={item.text}>
                    <button type="button" onClick={() => openChat(item.text)}>
                      <Icon name={item.icon} />
                      <span>{item.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section id="about" className="hb-about" aria-labelledby="about-title">
          <div className="hb-about-inner">
            <div className="hb-about-kicker">
              <p className="hb-eyebrow">About the Research Project</p>
              <span className="hb-about-rule" aria-hidden="true" />
            </div>

            <div className="hb-identity">
              <picture>
                <source srcSet="/images/vsku-emblem-small.webp" type="image/webp" />
                <img
                  className="hb-identity-emblem"
                  src="/images/vsku-emblem-small.png"
                  alt="Emblem of Vijayanagara Sri Krishnadevaraya University, Ballari"
                  width="320"
                  height="320"
                  loading="lazy"
                  decoding="async"
                />
              </picture>
              <div className="hb-identity-text">
                <h2 id="about-title">Vijayanagara Sri Krishnadevaraya University, Ballari</h2>
                <p className="hb-dept">Department of Studies in Education</p>
              </div>
            </div>

            <div className="hb-about-grid">
              <figure className="hb-campus">
                <picture>
                  <source
                    type="image/webp"
                    srcSet="/images/campus-640.webp 640w, /images/campus-960.webp 960w, /images/campus-1600.webp 1600w"
                    sizes="(min-width: 1024px) min(780px, 56vw), calc(100vw - 2rem)"
                  />
                  <img
                    src="/images/campus-1280.jpg"
                    alt="University building and the statue of Sri Krishnadevaraya at Vijayanagara Sri Krishnadevaraya University, Ballari."
                    width="1600"
                    height="1066"
                    loading="lazy"
                    decoding="async"
                  />
                </picture>
              </figure>

              <dl className="hb-research">
                <div className="hb-research-item">
                  <dt>
                    <span className="hb-research-no" aria-hidden="true">
                      01 —{" "}
                    </span>
                    {RESEARCH.scholar.role}
                  </dt>
                  <dd className="hb-research-name">{RESEARCH.scholar.name}</dd>
                  <dd className="hb-research-meta">Reg. No. {RESEARCH.scholar.registrationNo}</dd>
                  <dd className="hb-research-meta">Father&apos;s name: {RESEARCH.scholar.fatherName}</dd>
                  <dd className="hb-research-meta">{RESEARCH.scholar.university}</dd>
                </div>
                <div className="hb-research-item">
                  <dt>
                    <span className="hb-research-no" aria-hidden="true">
                      02 —{" "}
                    </span>
                    Research Guide
                  </dt>
                  <dd className="hb-research-name">{RESEARCH.guide.name}</dd>
                  <dd className="hb-research-meta">{RESEARCH.guide.designation}</dd>
                  <dd className="hb-research-meta">{RESEARCH.guide.department}</dd>
                  <dd className="hb-research-meta">{RESEARCH.guide.university}</dd>
                </div>
                <div className="hb-research-item hb-research-topic">
                  <dt>
                    <span className="hb-research-no" aria-hidden="true">
                      03 —{" "}
                    </span>
                    Research Topic
                  </dt>
                  <dd className="hb-topic">{RESEARCH.title}</dd>
                  <dd className="hb-research-meta">{RESEARCH.context}</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
        <section id="features" className="hb-how hb-features" aria-labelledby="features-title">
          <div className="hb-how-inner">
            <div className="hb-how-head">
              <h2 id="features-title">Features</h2>
              <span className="hb-how-rule" aria-hidden="true" />
            </div>
            <ul className="hb-steps hb-feature-list">
              {FEATURES.map((f) => (
                <li key={f.title}>
                  <Icon name={f.icon} className="hb-step-icon" />
                  <div className="hb-step-text">
                    <h3>{f.title}</h3>
                    <p>{f.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
        <section id="how" className="hb-how" aria-labelledby="how-title">
          <div className="hb-how-inner">
            <div className="hb-how-head">
              <h2 id="how-title">How to Use HistoryBot</h2>
              <span className="hb-how-rule" aria-hidden="true" />
            </div>
            <ol className="hb-steps">
              {STEPS.map((step) => (
                <li key={step.no}>
                  <span className="hb-step-no">{step.no}</span>
                  <Icon name={step.icon} className="hb-step-icon" />
                  <div className="hb-step-text">
                    <h3>{step.title}</h3>
                    <p>{step.text}</p>
                  </div>
                  <Chevron />
                </li>
              ))}
            </ol>
          </div>
        </section>

      </main>

      <footer className="hb-foot">
        <div className="hb-foot-inner">
          <picture>
            <source srcSet="/images/vsku-emblem-small.webp" type="image/webp" />
            <img
              src="/images/vsku-emblem-small.png"
              alt=""
              width="320"
              height="320"
              loading="lazy"
              decoding="async"
            />
          </picture>
          <p>
            <span className="hb-foot-brand">HistoryBot</span>{" "}
            <span className="hb-foot-sep" aria-hidden="true">
              ·
            </span>{" "}
            <span>Department of Studies in Education</span>{" "}
            <span className="hb-foot-sep" aria-hidden="true">
              ·
            </span>{" "}
            <span>Vijayanagara Sri Krishnadevaraya University, Ballari</span>
          </p>
        </div>
      </footer>
    </div>
  );
}

function BookMark({ className = "hb-book" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M3.5 5.5c2.9-.6 5.6-.2 8.5 1.6v12.4c-2.9-1.8-5.6-2.2-8.5-1.6V5.5Z"
        fill="currentColor"
        fillOpacity="0.14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path
        d="M20.5 5.5c-2.9-.6-5.6-.2-8.5 1.6v12.4c2.9-1.8 5.6-2.2 8.5-1.6V5.5Z"
        fill="currentColor"
        fillOpacity="0.14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Arrow() {
  return (
    <svg className="hb-arrow" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M5 12h13M13 6.5l5.5 5.5-5.5 5.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Chevron() {
  return (
    <svg className="hb-chev" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Icon({ name, className = "hb-mini" }) {
  const paths = {
    crown: "M4.5 17.5h15M5 15.5l-1-8 4.6 3.6L12 5l3.4 6.1L20 7.5l-1 8H5Z",
    swords:
      "M5 5l9.5 9.5M19 5L9.5 14.5M5 5h2.6l8.2 8.2M19 5h-2.6l-8.2 8.2M13 16l3 3M11 16l-3 3M15.2 13.8l2.5 2.5-1.4 1.4-2.5-2.5M8.8 13.8l-2.5 2.5 1.4 1.4 2.5-2.5",
    book: "M3.5 5.5c2.9-.6 5.6-.2 8.5 1.6v12.4c-2.9-1.8-5.6-2.2-8.5-1.6V5.5ZM20.5 5.5c-2.9-.6-5.6-.2-8.5 1.6v12.4c2.9-1.8 5.6-2.2 8.5-1.6V5.5Z",
    people:
      "M9 11.2a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3.8 19c.5-3.2 2.6-5.2 5.2-5.2s4.7 2 5.2 5.2H3.8ZM16 10.8a2.4 2.4 0 1 0 0-4.8M16.8 13.9c2 .4 3.2 2.2 3.5 5.1h-3",
    chat: "M4.5 6.5c0-1.1.9-2 2-2h11c1.1 0 2 .9 2 2v7.5c0 1.1-.9 2-2 2h-6.3L7 19.5v-3.5h-.5c-1.1 0-2-.9-2-2V6.5ZM8 9.3h8M8 12.3h5.5",
    pdf: "M6.5 3.5h8l4 4v13h-12v-17ZM14.5 3.5v4h4M8.8 12.5h6.4M8.8 15.5h6.4",
  };
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d={paths[name]}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { Achievement, Overview, StudentsTable, TopicsAndTrends } from "../components/teacher/Analytics.jsx";
import QuizManager from "../components/teacher/QuizManager.jsx";
import QuestionBank from "../components/teacher/QuestionBank.jsx";
import Reports from "../components/teacher/Reports.jsx";
import Research from "../components/teacher/Research.jsx";
import { RangePicker, btn, istToday } from "../components/teacher/ui.jsx";

const TABS = [
  ["overview", "Overview"],
  ["students", "Students"],
  ["topics", "Topics & trends"],
  ["achievement", "Achievement"],
  ["quizzes", "Quizzes"],
  ["questions", "Question bank"],
  ["research", "Research"],
  ["reports", "Reports"],
];
const RANGE_TABS = new Set(["overview", "students", "topics", "achievement", "research", "reports"]);

export default function AdminDashboard() {
  const { user, ready, logout } = useApp();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "overview";
  const [range, setRange] = useState({ from: istToday(-29), to: istToday() });

  if (!ready) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (!user) return <Navigate to="/teacher/login" replace />;
  if (user.role !== "admin") return <Navigate to="/" replace />;

  return (
    <div className="min-h-dvh bg-paper px-3 py-6 font-sans text-ink sm:px-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brass">Teacher</p>
            <h1 className="mt-1 font-serif text-3xl text-navy">Dashboard</h1>
            <p className="text-sm text-muted">Signed in as {user.display_name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/chat?fresh=1" className={`${btn} border border-navy text-navy`}>
              Start Learning
            </Link>
            <Link to="/" className={`${btn} border border-rule bg-cream text-navy`}>
              Homepage
            </Link>
            <button type="button" onClick={() => logout()} className={`${btn} border border-rule bg-cream text-navy`}>
              Log out
            </button>
          </div>
        </header>
        {/* Phones: one labelled menu lists every section (nothing hidden off-screen); wider screens: wrapped tabs. */}
        <div className="mb-4 sm:hidden">
          <label htmlFor="dash-section" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
            Dashboard section
          </label>
          <select
            id="dash-section"
            value={tab}
            onChange={(e) => setParams({ tab: e.target.value })}
            className="min-h-11 w-full rounded-full border border-navy bg-cream px-4 text-sm text-navy"
          >
            {TABS.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <nav className="mb-4 hidden sm:block" aria-label="Dashboard sections">
          <div role="tablist" className="flex flex-wrap gap-2">
            {TABS.map(([key, label]) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={tab === key}
                onClick={() => setParams({ tab: key })}
                className={`${btn} ${tab === key ? "bg-navy text-cream" : "border border-rule bg-cream text-navy"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </nav>
        {RANGE_TABS.has(tab) ? (
          <div className="mb-4">
            <RangePicker range={range} onChange={setRange} />
          </div>
        ) : null}
        {tab === "overview" ? <Overview range={range} /> : null}
        {tab === "students" ? <StudentsTable range={range} /> : null}
        {tab === "topics" ? <TopicsAndTrends range={range} /> : null}
        {tab === "achievement" ? <Achievement range={range} /> : null}
        {tab === "quizzes" ? <QuizManager /> : null}
        {tab === "questions" ? <QuestionBank /> : null}
        {tab === "research" ? <Research range={range} /> : null}
        {tab === "reports" ? <Reports range={range} /> : null}
      </div>
    </div>
  );
}

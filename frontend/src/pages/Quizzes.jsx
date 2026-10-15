import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { quizApi } from "../services/api.js";
import { ACTIVITY_LABELS, PageShell, formatSeconds, QuizBadges } from "../components/quiz/QuestionInput.jsx";

const btn = "inline-flex min-h-11 items-center rounded-full px-4 text-sm";

export function QuizCard({ quiz, onStart, busy }) {
  const left = quiz.max_attempts ? quiz.max_attempts - quiz.attempts_used : null;
  const blocked = !quiz.open || (left !== null && left <= 0 && !quiz.open_attempt_id);
  return (
    <article className="flex flex-col rounded-3xl border border-rule bg-cream p-4">
      <div className="flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide">
        <span className="rounded-full bg-navy/10 px-2 py-0.5 text-navy">{ACTIVITY_LABELS[quiz.activity_type] || "Quiz"}</span>
        <QuizBadges quiz={quiz} />
        <span className="rounded-full border border-rule px-2 py-0.5 text-muted">{quiz.difficulty}</span>
      </div>
      <h2 className="mt-2 font-serif text-lg text-navy">{quiz.title}</h2>
      {quiz.description ? <p className="mt-1 text-sm text-muted">{quiz.description}</p> : null}
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted">
        <dt>Questions</dt>
        <dd className="text-ink">{quiz.question_count}</dd>
        <dt>Time limit</dt>
        <dd className="text-ink">{quiz.time_limit_sec ? formatSeconds(quiz.time_limit_sec) : "None"}</dd>
        <dt>Attempts</dt>
        <dd className="text-ink">
          {quiz.attempts_used}
          {quiz.max_attempts ? ` of ${quiz.max_attempts}` : ""}
        </dd>
        <dt>Best score</dt>
        <dd className="text-ink">{quiz.best_percent == null ? "—" : `${quiz.best_percent}%`}</dd>
      </dl>
      <div className="mt-auto pt-4">
        <button
          type="button"
          disabled={blocked || busy}
          onClick={() => onStart(quiz)}
          className={`${btn} bg-navy text-cream disabled:cursor-not-allowed disabled:opacity-40`}
        >
          {quiz.open_attempt_id ? "Continue" : blocked ? (quiz.open ? "No attempts left" : "Not open") : "Start"}
        </button>
      </div>
    </article>
  );
}

export function useStartQuiz() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const start = async (quiz) => {
    setBusy(true);
    setError("");
    try {
      if (quiz.open_attempt_id) {
        navigate(`/attempts/${quiz.open_attempt_id}`);
        return;
      }
      const data = await quizApi.start(quiz.id);
      navigate(`/attempts/${data.attempt.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return { start, busy, error };
}

function History() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    quizApi.history().then(setData).catch((err) => setError(err.message));
  }, []);
  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-muted">Loading your results…</p>;
  const done = data.attempts.filter((a) => a.status === "submitted");
  return (
    <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
      <section className="rounded-3xl border border-rule bg-cream p-4">
        <h2 className="font-serif text-xl text-navy">My attempts</h2>
        {done.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No finished quizzes yet.</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead className="text-xs uppercase text-muted">
                <tr>
                  <th className="py-2 pr-2">Quiz</th>
                  <th className="py-2 pr-2">Date</th>
                  <th className="py-2 pr-2">Score</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {done.map((a) => (
                  <tr key={a.id} className="border-t border-rule">
                    <td className="py-2 pr-2">
                      {a.title}
                      <span className="block text-xs text-muted">Attempt {a.attempt_no}</span>
                    </td>
                    <td className="py-2 pr-2 text-xs">{new Date(a.submitted_at).toLocaleString()}</td>
                    <td className="py-2 pr-2 font-semibold">{a.percent}%</td>
                    <td className="py-2">
                      <Link className="text-navy underline" to={`/attempts/${a.id}`}>
                        Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="rounded-3xl border border-rule bg-cream p-4">
        <h2 className="font-serif text-xl text-navy">By topic</h2>
        {data.topics.length === 0 ? (
          <p className="mt-2 text-sm text-muted">Topic results appear after your first quiz.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {data.topics.map((t) => (
              <li key={t.topic} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span>{t.topic}</span>
                  <span className="font-semibold">{t.accuracy}%</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-rule" aria-hidden="true">
                  <div className="h-2 rounded-full bg-navy" style={{ width: `${t.accuracy}%` }} />
                </div>
                <span className="text-xs text-muted">{t.answered} answers</span>
              </li>
            ))}
          </ul>
        )}
        {data.suggestions.length ? (
          <div className="mt-4 rounded-2xl bg-brass/10 p-3">
            <h3 className="text-sm font-semibold text-navydeep">What to revise</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
              {data.suggestions.map((s) => (
                <li key={s.topic}>{s.suggestion}</li>
              ))}
            </ul>
            <Link to="/activities" className={`${btn} mt-2 bg-navy text-cream`}>
              Try a Revision Challenge
            </Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}

export default function Quizzes() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "history" ? "history" : "list";
  const [filters, setFilters] = useState({ topic: "", difficulty: "", mode: "" });
  const [quizzes, setQuizzes] = useState(null);
  const [error, setError] = useState("");
  const { start, busy, error: startError } = useStartQuiz();

  useEffect(() => {
    if (tab !== "list") return;
    let cancelled = false;
    quizApi
      .list({ difficulty: filters.difficulty, mode: filters.mode })
      .then((d) => !cancelled && setQuizzes(d.quizzes))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [tab, filters.difficulty, filters.mode]);

  const topics = useMemo(() => [...new Set((quizzes || []).map((q) => q.topic))].sort(), [quizzes]);
  const shown = (quizzes || []).filter((q) => !filters.topic || q.topic === filters.topic);
  const select = "min-h-11 rounded-full border border-rule bg-cream px-3 text-sm";

  return (
    <PageShell
      eyebrow="Practice"
      title="Quizzes"
      actions={
        <>
          <Link to="/activities" className={`${btn} border border-navy text-navy`}>
            Activities
          </Link>
          <Link to="/chat" className={`${btn} border border-rule bg-cream text-navy`}>
            Back to learning
          </Link>
        </>
      }
    >
      <div role="tablist" className="mb-4 flex gap-2">
        {[
          ["list", "All quizzes"],
          ["history", "My results"],
        ].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            type="button"
            onClick={() => setParams(key === "history" ? { tab: "history" } : {})}
            className={`${btn} ${tab === key ? "bg-navy text-cream" : "border border-rule bg-cream text-navy"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "history" ? (
        <History />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <label className="sr-only" htmlFor="f-topic">Topic</label>
            <select id="f-topic" className={select} value={filters.topic} onChange={(e) => setFilters({ ...filters, topic: e.target.value })}>
              <option value="">All topics</option>
              {topics.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="f-diff">Difficulty</label>
            <select id="f-diff" className={select} value={filters.difficulty} onChange={(e) => setFilters({ ...filters, difficulty: e.target.value })}>
              <option value="">Any difficulty</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
              <option value="mixed">Mixed</option>
            </select>
            <label className="sr-only" htmlFor="f-mode">Mode</label>
            <select id="f-mode" className={select} value={filters.mode} onChange={(e) => setFilters({ ...filters, mode: e.target.value })}>
              <option value="">Practice and assessment</option>
              <option value="practice">Practice</option>
              <option value="assessment">Assessment</option>
            </select>
          </div>
          {error || startError ? <p className="mb-3 text-sm text-red-700">{error || startError}</p> : null}
          {!quizzes ? (
            <p className="text-sm text-muted">Loading quizzes…</p>
          ) : shown.length === 0 ? (
            <p className="text-sm text-muted">No quizzes match these filters.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((q) => (
                <QuizCard key={q.id} quiz={q} onStart={start} busy={busy} />
              ))}
            </div>
          )}
        </>
      )}
    </PageShell>
  );
}

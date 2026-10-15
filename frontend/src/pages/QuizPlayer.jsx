import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { quizApi } from "../services/api.js";
import QuestionInput, { ACTIVITY_LABELS, PageShell, answerText, formatSeconds, isAnswered } from "../components/quiz/QuestionInput.jsx";

const btn = "inline-flex min-h-11 items-center justify-center rounded-full px-4 text-sm";

function Results({ data, onRetry, retryBusy }) {
  const a = data.attempt;
  const navigate = useNavigate();
  const [revError, setRevError] = useState("");
  const revision = async () => {
    setRevError("");
    try {
      const r = await quizApi.revision();
      const started = await quizApi.start(r.quiz_id);
      navigate(`/attempts/${started.attempt.id}`);
    } catch (err) {
      setRevError(err.message);
    }
  };
  return (
    <PageShell eyebrow={ACTIVITY_LABELS[data.quiz.activity_type] || "Quiz"} title={data.quiz.title}>
      <section className="rounded-3xl border border-rule bg-cream p-5" aria-live="polite">
        <p className="text-sm text-muted">Attempt {a.attempt_no} · submitted {new Date(a.submitted_at).toLocaleString()}</p>
        <p className="mt-2 font-serif text-4xl text-navy">{a.percent}%</p>
        <p className="text-sm">
          {a.score} of {a.max_score} points{a.duration_sec != null ? ` · ${formatSeconds(a.duration_sec)} taken` : ""}
        </p>
        {data.late ? <p className="mt-2 text-sm text-red-700">Time ran out, so your last saved answers were marked.</p> : null}
        {data.reveal_note ? <p className="mt-3 rounded-2xl bg-brass/10 p-3 text-sm">{data.reveal_note}</p> : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/quizzes" className={`${btn} border border-navy text-navy`}>
            All quizzes
          </Link>
          <Link to="/quizzes?tab=history" className={`${btn} border border-rule text-navy`}>
            My results
          </Link>
          {onRetry ? (
            <button type="button" onClick={onRetry} disabled={retryBusy} className={`${btn} bg-navy text-cream`}>
              Try again
            </button>
          ) : null}
        </div>
      </section>
      {data.topics_to_revise?.length ? (
        <section className="mt-4 rounded-3xl border border-rule bg-cream p-5">
          <h2 className="font-serif text-xl text-navy">Topics to revise</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {data.topics_to_revise.map((t) => (
              <li key={t.topic}>
                {t.topic} — {t.missed} missed
                {t.textbook_pages.length ? ` (textbook page ${t.textbook_pages.join(", ")})` : ""}
              </li>
            ))}
          </ul>
          <button type="button" onClick={revision} className={`${btn} mt-3 bg-navy text-cream`}>
            Start a Revision Challenge
          </button>
          {revError ? <p className="mt-2 text-sm text-red-700">{revError}</p> : null}
        </section>
      ) : null}
      {data.reveal ? (
        <ol className="mt-4 space-y-3">
          {data.questions.map((q, i) => (
            <li key={q.id} className={`rounded-3xl border p-4 ${q.correct ? "border-green-700/30 bg-green-50" : "border-red-700/20 bg-red-50/60"}`}>
              <p className="text-xs font-semibold uppercase text-muted">
                Question {i + 1} · {q.correct ? "Correct" : q.points > 0 ? `Partly correct (${q.points}/${q.max_points})` : "Incorrect"}
              </p>
              <p className="mt-1 font-medium">{q.prompt}</p>
              <p className="mt-2 text-sm">
                <span className="text-muted">Your answer: </span>
                {answerText(q, q.response)}
              </p>
              {!q.correct ? (
                <p className="text-sm">
                  <span className="text-muted">Correct answer: </span>
                  <strong>{answerText(q, q.answer)}</strong>
                </p>
              ) : null}
              {q.explanation ? <p className="mt-2 text-sm">{q.explanation}</p> : null}
              {q.textbook_page ? (
                <p className="mt-1 text-xs text-muted">
                  Source: {q.source_document || "Textbook"}, page {q.textbook_page}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </PageShell>
  );
}

export default function QuizPlayer() {
  const { attemptId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [responses, setResponses] = useState({});
  const [index, setIndex] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [remaining, setRemaining] = useState(null);
  const offsetRef = useRef(0);
  const responsesRef = useRef({});
  const submittedRef = useRef(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const d = await quizApi.attempt(attemptId);
      if (d.server_now) offsetRef.current = new Date(d.server_now).getTime() - Date.now();
      setData(d);
      if (d.autosave) {
        setResponses(d.autosave);
        responsesRef.current = d.autosave;
      }
    } catch (err) {
      setError(err.message);
    }
  }, [attemptId]);

  useEffect(() => {
    load();
  }, [load]);

  const inProgress = data?.attempt?.status === "in_progress";

  const save = useCallback(async () => {
    if (!inProgress || submittedRef.current) return;
    setSaveState("Saving…");
    try {
      await quizApi.autosave(attemptId, responsesRef.current);
      setDirty(false);
      setSaveState("Saved");
    } catch (err) {
      setSaveState(err.status === 409 ? "" : "Not saved — check your connection");
    }
  }, [attemptId, inProgress]);

  // Autosave shortly after each change.
  useEffect(() => {
    if (!dirty) return undefined;
    const t = setTimeout(save, 1500);
    return () => clearTimeout(t);
  }, [dirty, responses, save]);

  // Warn before leaving with unsaved answers.
  useEffect(() => {
    if (!inProgress) return undefined;
    const handler = (e) => {
      if (submittedRef.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [inProgress]);

  const submit = useCallback(async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      const result = await quizApi.submit(attemptId, responsesRef.current);
      setConfirming(false);
      setData(result);
    } catch (err) {
      if (err.code === "ALREADY_SUBMITTED") {
        await load();
      } else {
        submittedRef.current = false;
        setError(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }, [attemptId, load]);

  // Timer from the server deadline; submits automatically at zero.
  useEffect(() => {
    if (!inProgress || !data.attempt.deadline_at) {
      setRemaining(null);
      return undefined;
    }
    const deadline = new Date(data.attempt.deadline_at).getTime();
    const tick = () => {
      const left = Math.round((deadline - (Date.now() + offsetRef.current)) / 1000);
      setRemaining(left);
      if (left <= 0) submit();
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [inProgress, data, submit]);

  const setAnswer = (qid, value) => {
    const next = { ...responsesRef.current, [qid]: value };
    responsesRef.current = next;
    setResponses(next);
    setDirty(true);
  };

  const retry = async () => {
    try {
      const d = await quizApi.start(data.quiz.id);
      submittedRef.current = false;
      navigate(`/attempts/${d.attempt.id}`);
    } catch (err) {
      setError(err.message);
    }
  };

  if (error && !data) {
    return (
      <PageShell title="Quiz">
        <p className="text-sm text-red-700">{error}</p>
        <Link to="/quizzes" className="mt-3 inline-block text-navy underline">
          Back to quizzes
        </Link>
      </PageShell>
    );
  }
  if (!data) return <p className="p-8 text-sm text-muted">Loading…</p>;
  if (!inProgress) {
    const canRetry = data.quiz && (!data.quiz.max_attempts || data.attempt.attempt_no < data.quiz.max_attempts) && data.quiz.status === "published";
    return <Results data={data} onRetry={canRetry ? retry : null} />;
  }

  const questions = data.questions;
  const q = questions[index];
  const answered = questions.filter((x) => isAnswered(x, responses[x.id])).length;
  const unanswered = questions.length - answered;
  const lowTime = remaining !== null && remaining <= 30;

  return (
    <PageShell
      eyebrow={`${ACTIVITY_LABELS[data.quiz.activity_type] || "Quiz"} · ${data.quiz.mode === "assessment" ? "Assessment" : "Practice"}`}
      title={data.quiz.title}
    >
      <div className="sticky top-0 z-10 -mx-3 mb-4 border-b border-rule bg-paper/95 px-3 py-2 backdrop-blur sm:mx-0 sm:rounded-2xl sm:border">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>
            Question <strong>{index + 1}</strong> of {questions.length} · {answered} answered
          </span>
          <span className="text-xs text-muted" aria-live="polite">
            {saveState}
          </span>
          {remaining !== null ? (
            <span
              className={`rounded-full px-3 py-1 font-semibold tabular-nums ${lowTime ? "bg-red-700 text-cream" : "bg-navy text-cream"}`}
              role="timer"
              aria-label={`Time left ${formatSeconds(remaining)}`}
            >
              ⏱ {formatSeconds(remaining)}
            </span>
          ) : null}
        </div>
        <div className="mt-2 h-2 rounded-full bg-rule" role="progressbar" aria-valuemin={0} aria-valuemax={questions.length} aria-valuenow={answered} aria-label="Questions answered">
          <div className="h-2 rounded-full bg-brass" style={{ width: `${(answered / questions.length) * 100}%` }} />
        </div>
      </div>

      <section className="rounded-3xl border border-rule bg-cream p-4 sm:p-6" aria-labelledby="q-prompt">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          {q.topic} · {q.difficulty}
        </p>
        <h2 id="q-prompt" className="mt-1 text-lg font-medium leading-snug">
          {q.prompt}
        </h2>
        <div className="mt-4">
          <QuestionInput key={q.id} question={q} value={responses[q.id]} onChange={(v) => setAnswer(q.id, v)} />
        </div>
      </section>

      <nav className="mt-4 flex flex-wrap items-center justify-between gap-2" aria-label="Question navigation">
        <button type="button" disabled={index === 0} onClick={() => setIndex(index - 1)} className={`${btn} border border-navy text-navy disabled:opacity-30`}>
          ← Previous
        </button>
        <ol className="flex flex-wrap gap-1">
          {questions.map((x, i) => (
            <li key={x.id}>
              <button
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Go to question ${i + 1}${isAnswered(x, responses[x.id]) ? " (answered)" : ""}`}
                aria-current={i === index ? "step" : undefined}
                className={`grid h-9 w-9 place-items-center rounded-full text-xs ${i === index ? "bg-navy text-cream" : isAnswered(x, responses[x.id]) ? "bg-brass/30 text-navydeep" : "border border-rule bg-cream"}`}
              >
                {i + 1}
              </button>
            </li>
          ))}
        </ol>
        {index < questions.length - 1 ? (
          <button type="button" onClick={() => setIndex(index + 1)} className={`${btn} bg-navy text-cream`}>
            Next →
          </button>
        ) : (
          <button type="button" onClick={() => setConfirming(true)} className={`${btn} bg-navy text-cream`}>
            Submit
          </button>
        )}
      </nav>
      <div className="mt-3 text-right">
        <button type="button" onClick={() => setConfirming(true)} className="inline-flex min-h-11 items-center px-2 text-sm text-navy underline">
          Finish and submit
        </button>
      </div>
      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}

      {confirming ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <div className="w-full max-w-sm rounded-3xl bg-cream p-5 shadow-xl">
            <h2 id="confirm-title" className="font-serif text-xl text-navy">
              Submit your answers?
            </h2>
            <p className="mt-2 text-sm">
              {unanswered > 0 ? `${unanswered} question${unanswered === 1 ? " is" : "s are"} not answered yet. ` : "All questions are answered. "}
              You cannot change answers after submitting.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" autoFocus onClick={() => setConfirming(false)} className={`${btn} border border-navy text-navy`}>
                Keep working
              </button>
              <button type="button" disabled={submitting} onClick={submit} className={`${btn} bg-navy text-cream disabled:opacity-50`}>
                {submitting ? "Submitting…" : "Submit"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { quizApi } from "../services/api.js";
import { PageShell } from "../components/quiz/QuestionInput.jsx";
import { QuizCard, useStartQuiz } from "./Quizzes.jsx";

const btn = "inline-flex min-h-11 items-center rounded-full px-4 text-sm";

const ACTIVITIES = [
  { type: "history_challenge", title: "History Challenge", text: "Mixed questions across the chapter." },
  { type: "beat_the_clock", title: "Beat the Clock", text: "Answer as many as you can before the timer ends." },
  { type: "timeline", title: "Timeline", text: "Put battles, rulers and events in the right order." },
  { type: "match_figure", title: "Match the Figure", text: "Match historical figures with their titles and works." },
  { type: "find_correct", title: "Find the Correct Answer", text: "Pick the right answer from close choices." },
];

export default function Activities() {
  const navigate = useNavigate();
  const [quizzes, setQuizzes] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [topic, setTopic] = useState("");
  const { start, busy: startBusy, error: startError } = useStartQuiz();

  useEffect(() => {
    quizApi
      .list()
      .then((d) => setQuizzes(d.quizzes))
      .catch((err) => setError(err.message));
  }, []);

  const launch = async (fn) => {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      const started = await quizApi.start(r.quiz_id);
      navigate(`/attempts/${started.attempt.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell
      eyebrow="Learn by doing"
      title="Activities"
      actions={
        <>
          <Link to="/quizzes" className={`${btn} border border-navy text-navy`}>
            Quizzes
          </Link>
          <Link to="/questionnaires" className={`${btn} border border-navy text-navy`}>
            Questionnaires
          </Link>
          <Link to="/chat" className={`${btn} border border-rule bg-cream text-navy`}>
            Back to learning
          </Link>
        </>
      }
    >
      {error || startError ? <p className="mb-3 text-sm text-red-700">{error || startError}</p> : null}
      <div className="grid gap-3 md:grid-cols-2">
        <section className="rounded-3xl border border-rule bg-cream p-4">
          <h2 className="font-serif text-xl text-navy">Revision Challenge</h2>
          <p className="mt-1 text-sm text-muted">Built from the topics you missed in your own quizzes.</p>
          <button type="button" disabled={busy} onClick={() => launch(quizApi.revision)} className={`${btn} mt-3 bg-navy text-cream disabled:opacity-50`}>
            Start Revision Challenge
          </button>
        </section>
        <section className="rounded-3xl border border-rule bg-cream p-4">
          <h2 className="font-serif text-xl text-navy">Module checkpoint</h2>
          <p className="mt-1 text-sm text-muted">A short check on a topic you studied in a learning module.</p>
          <form
            className="mt-3 flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (topic.trim()) launch(() => quizApi.checkpoint(topic.trim()));
            }}
          >
            <label htmlFor="cp-topic" className="sr-only">
              Topic
            </label>
            <input
              id="cp-topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Akbar, Shivaji, Sher Shah"
              maxLength={120}
              className="min-h-11 flex-1 rounded-full border border-rule bg-paper px-4 text-sm"
            />
            <button type="submit" disabled={busy || !topic.trim()} className={`${btn} bg-navy text-cream disabled:opacity-50`}>
              Start checkpoint
            </button>
          </form>
        </section>
      </div>
      {ACTIVITIES.map((a) => {
        const list = (quizzes || []).filter((q) => q.activity_type === a.type);
        return (
          <section key={a.type} className="mt-6">
            <h2 className="font-serif text-2xl text-navy">{a.title}</h2>
            <p className="text-sm text-muted">{a.text}</p>
            {!quizzes ? (
              <p className="mt-2 text-sm text-muted">Loading…</p>
            ) : list.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No {a.title} activity has been published yet.</p>
            ) : (
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {list.map((q) => (
                  <QuizCard key={q.id} quiz={q} onStart={start} busy={startBusy} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </PageShell>
  );
}

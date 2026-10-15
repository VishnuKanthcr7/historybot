import { useEffect, useState } from "react";
import { teacherApi } from "../../services/api.js";
import { ACTIVITY_LABELS, answerText, formatSeconds } from "../quiz/QuestionInput.jsx";
import { Bars, Card, ErrorText, btn, field, fmtDate } from "./ui.jsx";

const EMPTY = {
  title: "",
  description: "",
  topic: "",
  difficulty: "mixed",
  mode: "practice",
  activity_type: "quiz",
  assessment_phase: "none",
  time_min: "",
  max_attempts: "",
  reveal_answers: "after_submit",
  available_from: "",
  available_until: "",
  question_ids: [],
};

const toLocalInput = (v) => (v ? new Date(new Date(v).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");

function QuizForm({ initial, onSaved, onCancel }) {
  const [f, setF] = useState(initial || EMPTY);
  const [bank, setBank] = useState([]);
  const [topicFilter, setTopicFilter] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    teacherApi
      .questions({ size: 100 })
      .then((d) => setBank(d.questions.filter((q) => q.status !== "archived")))
      .catch((e) => setError(e.message));
  }, []);
  const set = (patch) => setF({ ...f, ...patch });
  const toggle = (id) => set({ question_ids: f.question_ids.includes(id) ? f.question_ids.filter((x) => x !== id) : [...f.question_ids, id] });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body = {
      title: f.title,
      description: f.description,
      topic: f.topic,
      difficulty: f.difficulty,
      mode: f.mode,
      activity_type: f.activity_type,
      assessment_phase: f.assessment_phase,
      time_limit_sec: f.time_min ? Math.round(Number(f.time_min) * 60) : null,
      max_attempts: f.max_attempts ? Number(f.max_attempts) : null,
      reveal_answers: f.reveal_answers,
      available_from: f.available_from ? new Date(f.available_from).toISOString() : null,
      available_until: f.available_until ? new Date(f.available_until).toISOString() : null,
      question_ids: f.question_ids,
    };
    try {
      const r = f.id ? await teacherApi.updateQuiz(f.id, body) : await teacherApi.createQuiz(body);
      onSaved(r.quiz);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const topics = [...new Set(bank.map((q) => q.topic))].sort();
  const label = "flex flex-col gap-1 text-sm";
  return (
    <form onSubmit={save} className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className={label}>
          Title
          <input className={field} required minLength={3} value={f.title} onChange={(e) => set({ title: e.target.value })} />
        </label>
        <label className={label}>
          Topic
          <input className={field} required minLength={2} value={f.topic} onChange={(e) => set({ topic: e.target.value })} />
        </label>
      </div>
      <label className={label}>
        Description
        <input className={field} value={f.description} onChange={(e) => set({ description: e.target.value })} />
      </label>
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <label className={label}>
          Activity
          <select className={field} value={f.activity_type} onChange={(e) => set({ activity_type: e.target.value })}>
            {Object.entries(ACTIVITY_LABELS)
              .filter(([k]) => k !== "revision" && k !== "checkpoint")
              .map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
          </select>
        </label>
        <label className={label}>
          Mode
          <select className={field} value={f.mode} onChange={(e) => set({ mode: e.target.value })}>
            <option value="practice">Practice</option>
            <option value="assessment">Assessment</option>
          </select>
        </label>
        <label className={label}>
          Difficulty
          <select className={field} value={f.difficulty} onChange={(e) => set({ difficulty: e.target.value })}>
            {["easy", "medium", "hard", "mixed"].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
        <label className={label}>
          Pre / post test
          <select className={field} value={f.assessment_phase} onChange={(e) => set({ assessment_phase: e.target.value })}>
            <option value="none">Neither</option>
            <option value="pre">Pre-test</option>
            <option value="post">Post-test</option>
          </select>
        </label>
        <label className={label}>
          Time limit (minutes)
          <input className={field} type="number" min="0.5" step="0.5" value={f.time_min} onChange={(e) => set({ time_min: e.target.value })} placeholder="None" />
        </label>
        <label className={label}>
          Attempts allowed
          <input className={field} type="number" min="1" value={f.max_attempts} onChange={(e) => set({ max_attempts: e.target.value })} placeholder="Unlimited" />
        </label>
        <label className={label}>
          Show answers
          <select className={field} value={f.reveal_answers} onChange={(e) => set({ reveal_answers: e.target.value })}>
            <option value="after_submit">After submitting</option>
            <option value="after_close">After the quiz closes</option>
            <option value="never">Never</option>
          </select>
        </label>
        <label className={label}>
          Opens
          <input className={field} type="datetime-local" value={f.available_from} onChange={(e) => set({ available_from: e.target.value })} />
        </label>
        <label className={label}>
          Closes
          <input className={field} type="datetime-local" value={f.available_until} onChange={(e) => set({ available_until: e.target.value })} />
        </label>
      </div>
      <fieldset>
        <legend className="text-sm font-semibold">
          Questions ({f.question_ids.length} selected)
        </legend>
        <select className={`${field} my-2`} aria-label="Filter questions by topic" value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)}>
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <ul className="max-h-72 space-y-1 overflow-y-auto rounded-2xl border border-rule p-2">
          {bank
            .filter((q) => !topicFilter || q.topic === topicFilter)
            .map((q) => (
              <li key={q.id}>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-1 h-5 w-5" checked={f.question_ids.includes(q.id)} onChange={() => toggle(q.id)} />
                  <span>
                    {q.prompt}
                    <span className="block text-xs text-muted">
                      {q.topic} · {q.qtype} · {q.status}
                    </span>
                  </span>
                </label>
              </li>
            ))}
        </ul>
        <p className="mt-1 text-xs text-muted">A quiz can be published only when all its questions are published (reviewed).</p>
      </fieldset>
      <ErrorText>{error}</ErrorText>
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className={`${btn} bg-navy text-cream`}>
          Save
        </button>
        <button type="button" onClick={onCancel} className={`${btn} border border-navy text-navy`}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Preview({ id, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    teacherApi.quiz(id).then(setData).catch((e) => setError(e.message));
  }, [id]);
  return (
    <Card title={data ? `Preview: ${data.quiz.title}` : "Preview"} actions={<button type="button" className={`${btn} border border-navy text-navy`} onClick={onClose}>Close</button>}>
      <ErrorText>{error}</ErrorText>
      <ol className="space-y-2">
        {(data?.questions || []).map((q, i) => (
          <li key={q.id} className="rounded-2xl border border-rule p-3 text-sm">
            <p className="font-medium">
              {i + 1}. {q.prompt}
            </p>
            {q.qtype === "mcq" ? <p className="text-xs text-muted">Options: {q.options.map((o) => o.text).join(" · ")}</p> : null}
            <p className="mt-1 text-xs">
              <span className="text-muted">Answer: </span>
              {answerText(q, q.answer)}
            </p>
            {q.explanation ? <p className="text-xs text-muted">{q.explanation}</p> : null}
            <p className="text-xs text-muted">
              {q.topic} · {q.status}
              {q.textbook_page ? ` · textbook p. ${q.textbook_page}` : ""}
            </p>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Results({ id, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    teacherApi.results(id).then(setData).catch((e) => setError(e.message));
  }, [id]);
  return (
    <Card title={data ? `Results: ${data.quiz.title}` : "Results"} actions={<button type="button" className={`${btn} border border-navy text-navy`} onClick={onClose}>Close</button>}>
      <ErrorText>{error}</ErrorText>
      {!data ? null : data.aggregate.attempts === 0 ? (
        <p className="text-sm text-muted">No submitted attempts yet.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <p className="text-sm">
              {data.aggregate.attempts} attempts by {data.aggregate.students} students · mean {data.aggregate.mean_percent}% · median {data.aggregate.median_percent}%
            </p>
            <h3 className="mt-3 text-sm font-semibold">Distribution</h3>
            <Bars items={data.aggregate.distribution} label={(d) => `${d.label}%`} value={(d) => d.count} max={Math.max(...data.aggregate.distribution.map((d) => d.count), 1)} />
            <h3 className="mt-3 text-sm font-semibold">By question (% correct)</h3>
            <Bars items={data.questions} label={(q) => q.prompt} value={(q) => q.percent_correct} suffix="%" note={(q) => `n=${q.answered}`} />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[360px] text-left text-sm">
              <thead className="text-xs uppercase text-muted">
                <tr>
                  <th className="py-1 pr-2">Student</th>
                  <th className="py-1 pr-2">#</th>
                  <th className="py-1 pr-2">Score</th>
                  <th className="py-1 pr-2">Time</th>
                  <th className="py-1">Date</th>
                </tr>
              </thead>
              <tbody>
                {data.individual.map((r) => (
                  <tr key={r.attempt_id} className="border-t border-rule">
                    <td className="py-1 pr-2">{r.student}</td>
                    <td className="py-1 pr-2">{r.attempt_no}</td>
                    <td className="py-1 pr-2">{r.percent}%</td>
                    <td className="py-1 pr-2">{formatSeconds(r.duration_sec)}</td>
                    <td className="py-1">{fmtDate(r.submitted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function QuizManager({ onChanged }) {
  const [quizzes, setQuizzes] = useState(null);
  const [error, setError] = useState("");
  const [panel, setPanel] = useState(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    teacherApi
      .quizzes()
      .then((d) => {
        setQuizzes(d.quizzes);
        onChanged?.(d.quizzes);
      })
      .catch((e) => setError(e.message));
  }, [reload]); // eslint-disable-line react-hooks/exhaustive-deps
  const status = async (q, s) => {
    setError("");
    try {
      await teacherApi.quizStatus(q.id, s);
      setReload((n) => n + 1);
    } catch (err) {
      setError(err.message);
    }
  };
  const edit = async (q) => {
    setError("");
    try {
      const d = await teacherApi.quiz(q.id);
      setPanel({
        kind: "form",
        initial: {
          ...EMPTY,
          ...d.quiz,
          description: d.quiz.description || "",
          time_min: d.quiz.time_limit_sec ? d.quiz.time_limit_sec / 60 : "",
          max_attempts: d.quiz.max_attempts || "",
          available_from: toLocalInput(d.quiz.available_from),
          available_until: toLocalInput(d.quiz.available_until),
          question_ids: d.questions.map((x) => x.id),
        },
      });
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <div className="space-y-4">
      {panel?.kind === "form" ? (
        <Card title={panel.initial?.id ? "Edit quiz" : "New quiz"}>
          <QuizForm
            initial={panel.initial}
            onCancel={() => setPanel(null)}
            onSaved={() => {
              setPanel(null);
              setReload((n) => n + 1);
            }}
          />
        </Card>
      ) : null}
      {panel?.kind === "preview" ? <Preview id={panel.id} onClose={() => setPanel(null)} /> : null}
      {panel?.kind === "results" ? <Results id={panel.id} onClose={() => setPanel(null)} /> : null}
      <Card
        title="Quizzes and activities"
        actions={
          <button type="button" className={`${btn} bg-navy text-cream`} onClick={() => setPanel({ kind: "form", initial: EMPTY })}>
            New quiz
          </button>
        }
      >
        <ErrorText>{error}</ErrorText>
        {!quizzes ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-xs uppercase text-muted">
                <tr>
                  <th className="py-2 pr-2">Quiz</th>
                  <th className="py-2 pr-2">Status</th>
                  <th className="py-2 pr-2">Questions</th>
                  <th className="py-2 pr-2">Attempts</th>
                  <th className="py-2 pr-2">Mean</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {quizzes.map((q) => (
                  <tr key={q.id} className="border-t border-rule align-top">
                    <td className="py-2 pr-2">
                      <span className="font-medium">{q.title}</span>
                      <span className="block text-xs text-muted">
                        {ACTIVITY_LABELS[q.activity_type]} · {q.mode}
                        {q.assessment_phase !== "none" ? ` · ${q.assessment_phase}-test` : ""}
                        {q.time_limit_sec ? ` · ${formatSeconds(q.time_limit_sec)}` : ""}
                        {q.max_attempts ? ` · ${q.max_attempts} attempt(s)` : ""} · by {q.created_by_name || "—"}
                      </span>
                    </td>
                    <td className="py-2 pr-2">{q.status}</td>
                    <td className="py-2 pr-2">{q.question_count}</td>
                    <td className="py-2 pr-2">
                      {q.submitted_attempts} <span className="text-xs text-muted">({q.students} students)</span>
                    </td>
                    <td className="py-2 pr-2">{q.mean_percent == null ? "—" : `${q.mean_percent}%`}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1">
                        <button type="button" className="rounded-full border border-rule px-3 py-1 text-xs" onClick={() => setPanel({ kind: "preview", id: q.id })}>
                          Preview
                        </button>
                        <button type="button" className="rounded-full border border-rule px-3 py-1 text-xs" onClick={() => setPanel({ kind: "results", id: q.id })}>
                          Results
                        </button>
                        {q.mine ? (
                          <>
                            <button type="button" className="rounded-full border border-navy px-3 py-1 text-xs text-navy" onClick={() => edit(q)}>
                              Edit
                            </button>
                            {q.status !== "published" ? (
                              <button type="button" className="rounded-full bg-navy px-3 py-1 text-xs text-cream" onClick={() => status(q, "published")}>
                                Publish
                              </button>
                            ) : null}
                            {q.status !== "archived" ? (
                              <button type="button" className="rounded-full border border-rule px-3 py-1 text-xs" onClick={() => status(q, "archived")}>
                                Archive
                              </button>
                            ) : null}
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-muted">Archiving an assessment closes it; “after the quiz closes” answers then become visible to students.</p>
      </Card>
    </div>
  );
}

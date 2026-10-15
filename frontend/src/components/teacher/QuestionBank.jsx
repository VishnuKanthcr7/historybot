import { useEffect, useState } from "react";
import { teacherApi } from "../../services/api.js";
import { answerText } from "../quiz/QuestionInput.jsx";
import { Card, ErrorText, btn, field } from "./ui.jsx";

const TYPES = { mcq: "Multiple choice", true_false: "True / false", fill_blank: "Fill in the blank", order: "Order", match: "Match" };

function shuffle(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Editable form state <-> API question shape.
function toForm(q) {
  const f = {
    qtype: q?.qtype || "mcq",
    prompt: q?.prompt || "",
    explanation: q?.explanation || "",
    topic: q?.topic || "",
    difficulty: q?.difficulty || "medium",
    textbook_page: q?.textbook_page ?? "",
    options: ["", "", "", ""],
    correct: 0,
    tf: true,
    accepted: "",
    lines: "",
  };
  if (!q) return f;
  if (q.qtype === "mcq") {
    f.options = q.options.map((o) => o.text);
    f.correct = Math.max(0, q.options.findIndex((o) => o.id === q.answer));
  } else if (q.qtype === "true_false") f.tf = q.answer === true;
  else if (q.qtype === "fill_blank") f.accepted = (q.answer || []).join(", ");
  else if (q.qtype === "order") f.lines = (q.answer || []).map((id) => q.options.find((o) => o.id === id)?.text || "").join("\n");
  else if (q.qtype === "match")
    f.lines = (q.options?.left || []).map((l) => `${l.text} = ${q.options.right.find((r) => r.id === q.answer[l.id])?.text || ""}`).join("\n");
  return f;
}

function fromForm(f) {
  const body = {
    qtype: f.qtype,
    prompt: f.prompt.trim(),
    explanation: f.explanation,
    topic: f.topic.trim(),
    difficulty: f.difficulty,
    textbook_page: f.textbook_page === "" ? null : Number(f.textbook_page),
  };
  const lines = f.lines.split("\n").map((l) => l.trim()).filter(Boolean);
  if (f.qtype === "mcq") {
    const opts = f.options.map((t, i) => ({ id: "abcdef"[i], text: t.trim() })).filter((o) => o.text);
    body.options = opts;
    body.answer = "abcdef"[f.correct];
  } else if (f.qtype === "true_false") body.answer = f.tf;
  else if (f.qtype === "fill_blank") body.answer = f.accepted.split(",").map((s) => s.trim()).filter(Boolean);
  else if (f.qtype === "order") {
    const items = lines.map((text, i) => ({ id: `i${i + 1}`, text }));
    body.options = shuffle(items);
    body.answer = items.map((i) => i.id);
  } else if (f.qtype === "match") {
    const pairs = lines.map((l) => l.split("=").map((s) => s.trim())).filter((p) => p.length === 2 && p[0] && p[1]);
    const left = pairs.map((p, i) => ({ id: `l${i + 1}`, text: p[0] }));
    const right = pairs.map((p, i) => ({ id: `r${i + 1}`, text: p[1] }));
    body.options = { left, right: shuffle(right) };
    body.answer = Object.fromEntries(left.map((l, i) => [l.id, `r${i + 1}`]));
  }
  return body;
}

export function QuestionEditor({ question, onSaved, onCancel }) {
  const [f, setF] = useState(() => toForm(question));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (patch) => setF({ ...f, ...patch });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = fromForm(f);
      const r = question?.id ? await teacherApi.updateQuestion(question.id, body) : await teacherApi.createQuestion(body);
      onSaved(r.question);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save} className="space-y-3 text-sm">
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          Type
          <select className={field} value={f.qtype} disabled={Boolean(question?.id)} onChange={(e) => set({ qtype: e.target.value })}>
            {Object.entries(TYPES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Topic
          <input className={field} required value={f.topic} onChange={(e) => set({ topic: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          Difficulty
          <select className={field} value={f.difficulty} onChange={(e) => set({ difficulty: e.target.value })}>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1">
        Question {f.qtype === "fill_blank" ? "(put ______ where the blank goes)" : ""}
        <textarea className={`${field} min-h-20 py-2`} required value={f.prompt} onChange={(e) => set({ prompt: e.target.value })} />
      </label>
      {f.qtype === "mcq" ? (
        <fieldset className="space-y-2">
          <legend className="mb-1">Options (choose the correct one)</legend>
          {f.options.map((o, i) => (
            <div key={i} className="flex items-center gap-2">
              <input type="radio" name="correct" aria-label={`Option ${i + 1} is correct`} checked={f.correct === i} onChange={() => set({ correct: i })} className="h-5 w-5" />
              <input
                className={`${field} flex-1`}
                aria-label={`Option ${i + 1}`}
                value={o}
                onChange={(e) => set({ options: f.options.map((x, j) => (j === i ? e.target.value : x)) })}
              />
            </div>
          ))}
        </fieldset>
      ) : null}
      {f.qtype === "true_false" ? (
        <fieldset className="flex gap-4">
          <legend className="mb-1">Correct answer</legend>
          <label className="flex items-center gap-2">
            <input type="radio" checked={f.tf} onChange={() => set({ tf: true })} /> True
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={!f.tf} onChange={() => set({ tf: false })} /> False
          </label>
        </fieldset>
      ) : null}
      {f.qtype === "fill_blank" ? (
        <label className="flex flex-col gap-1">
          Accepted answers (comma separated; case and punctuation are ignored)
          <input className={field} value={f.accepted} onChange={(e) => set({ accepted: e.target.value })} />
        </label>
      ) : null}
      {f.qtype === "order" ? (
        <label className="flex flex-col gap-1">
          Items in the correct order, one per line (students see them shuffled)
          <textarea className={`${field} min-h-28 py-2`} value={f.lines} onChange={(e) => set({ lines: e.target.value })} />
        </label>
      ) : null}
      {f.qtype === "match" ? (
        <label className="flex flex-col gap-1">
          Pairs, one per line as “left = right”
          <textarea className={`${field} min-h-28 py-2`} value={f.lines} onChange={(e) => set({ lines: e.target.value })} />
        </label>
      ) : null}
      <div className="grid gap-2 sm:grid-cols-[1fr_8rem]">
        <label className="flex flex-col gap-1">
          Explanation shown after submission
          <input className={field} value={f.explanation} onChange={(e) => set({ explanation: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          Textbook page
          <input className={field} type="number" min="1" value={f.textbook_page} onChange={(e) => set({ textbook_page: e.target.value })} />
        </label>
      </div>
      {question?.source_excerpt ? <p className="rounded-2xl bg-paper p-2 text-xs text-muted">Source excerpt: “{question.source_excerpt}”</p> : null}
      <ErrorText>{error}</ErrorText>
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className={`${btn} bg-navy text-cream`}>
          Save draft
        </button>
        <button type="button" onClick={onCancel} className={`${btn} border border-navy text-navy`}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function PassageDrafter({ onDraft }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [topic, setTopic] = useState("");
  const [qtype, setQtype] = useState("fill_blank");
  const [error, setError] = useState("");
  const search = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setRows((await teacherApi.passages({ q })).passages);
    } catch (err) {
      setError(err.message);
    }
  };
  const draft = async (p, sentence) => {
    setError("");
    if (!topic.trim()) {
      setError("Enter a topic for the new question first.");
      return;
    }
    try {
      const r = await teacherApi.draftFromPassage({ chunk_id: p.chunk_id, sentence, qtype, topic: topic.trim() });
      onDraft(r.question);
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <Card title="Create a draft from a textbook passage">
      <form onSubmit={search} className="flex flex-wrap gap-2">
        <input className={`${field} flex-1`} aria-label="Search the textbook" placeholder="Search the textbook, e.g. Panipat" value={q} onChange={(e) => setQ(e.target.value)} />
        <input className={field} aria-label="Topic for the new question" placeholder="Topic" value={topic} onChange={(e) => setTopic(e.target.value)} />
        <select className={field} aria-label="Question type" value={qtype} onChange={(e) => setQtype(e.target.value)}>
          <option value="fill_blank">Fill in the blank</option>
          <option value="true_false">True / false</option>
        </select>
        <button type="submit" className={`${btn} bg-navy text-cream`}>
          Search
        </button>
      </form>
      <ErrorText>{error}</ErrorText>
      {rows ? (
        <ul className="mt-3 max-h-96 space-y-3 overflow-y-auto">
          {rows.length === 0 ? <li className="text-sm text-muted">No passages found.</li> : null}
          {rows.map((p) => (
            <li key={p.chunk_id} className="rounded-2xl border border-rule p-3">
              <p className="text-xs text-muted">Textbook page {p.page}</p>
              <ul className="mt-1 space-y-1">
                {p.sentences.map((s) => (
                  <li key={s} className="flex items-start justify-between gap-2 text-sm">
                    <span>{s}</span>
                    <button type="button" onClick={() => draft(p, s)} className="shrink-0 rounded-full border border-navy px-3 py-1 text-xs text-navy">
                      Draft
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-muted">Drafts are made from the exact sentence (no AI) and stay drafts until you review and publish them.</p>
      )}
    </Card>
  );
}

export default function QuestionBank() {
  const [filters, setFilters] = useState({ status: "", topic: "", q: "", page: 1, size: 25 });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    teacherApi.questions(filters).then(setData).catch((e) => setError(e.message));
  }, [filters, reload]);
  const setStatus = async (q, status) => {
    setError("");
    try {
      await teacherApi.questionStatus(q.id, status, status === "published" ? "Reviewed and published by teacher." : undefined);
      setReload((n) => n + 1);
    } catch (err) {
      setError(err.message);
    }
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / filters.size)) : 1;
  return (
    <div className="space-y-4">
      {editing ? (
        <Card title={editing.id ? "Edit draft question" : "New question"}>
          <QuestionEditor
            question={editing.id ? editing : null}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              setReload((n) => n + 1);
            }}
          />
        </Card>
      ) : null}
      <PassageDrafter
        onDraft={(q) => {
          setEditing(q);
          setReload((n) => n + 1);
        }}
      />
      <Card
        title="Question bank"
        actions={
          <button type="button" className={`${btn} bg-navy text-cream`} onClick={() => setEditing({})}>
            New question
          </button>
        }
      >
        <div className="mb-3 flex flex-wrap gap-2">
          <select className={field} aria-label="Status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value, page: 1 })}>
            <option value="">Any status</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
          <select className={field} aria-label="Topic" value={filters.topic} onChange={(e) => setFilters({ ...filters, topic: e.target.value, page: 1 })}>
            <option value="">All topics</option>
            {(data?.topics || []).map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <input className={`${field} flex-1`} aria-label="Search questions" placeholder="Search" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value, page: 1 })} />
        </div>
        <ErrorText>{error}</ErrorText>
        <ul className="space-y-2">
          {(data?.questions || []).map((q) => (
            <li key={q.id} className="rounded-2xl border border-rule p-3 text-sm">
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold uppercase">
                <span className={`rounded-full px-2 py-0.5 ${q.status === "published" ? "bg-green-100 text-green-800" : q.status === "draft" ? "bg-brass/20 text-navydeep" : "bg-rule text-muted"}`}>{q.status}</span>
                <span className="rounded-full border border-rule px-2 py-0.5 text-muted">{TYPES[q.qtype]}</span>
                <span className="text-muted">{q.topic}</span>
                {q.textbook_page ? <span className="text-muted">· p. {q.textbook_page}</span> : null}
                <span className="text-muted">· {q.origin}</span>
              </div>
              <p className="mt-1 font-medium">{q.prompt}</p>
              <p className="mt-1 text-xs">
                <span className="text-muted">Answer: </span>
                {answerText(q, q.answer)}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {q.status === "draft" ? (
                  <>
                    <button type="button" className="rounded-full border border-navy px-3 py-1 text-xs text-navy" onClick={() => setEditing(q)}>
                      Edit
                    </button>
                    <button type="button" className="rounded-full bg-navy px-3 py-1 text-xs text-cream" onClick={() => setStatus(q, "published")}>
                      Review &amp; publish
                    </button>
                  </>
                ) : null}
                {q.status !== "archived" ? (
                  <button type="button" className="rounded-full border border-rule px-3 py-1 text-xs" onClick={() => setStatus(q, "archived")}>
                    Archive
                  </button>
                ) : (
                  <button type="button" className="rounded-full border border-rule px-3 py-1 text-xs" onClick={() => setStatus(q, "draft")}>
                    Back to draft
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex items-center justify-end gap-2 text-sm">
          <button type="button" className={`${btn} border border-rule`} disabled={filters.page <= 1} onClick={() => setFilters({ ...filters, page: filters.page - 1 })}>
            Previous
          </button>
          <span>
            {filters.page} / {pages}
          </span>
          <button type="button" className={`${btn} border border-rule`} disabled={filters.page >= pages} onClick={() => setFilters({ ...filters, page: filters.page + 1 })}>
            Next
          </button>
        </div>
      </Card>
    </div>
  );
}

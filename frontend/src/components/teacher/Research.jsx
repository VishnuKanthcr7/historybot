import { useEffect, useState } from "react";
import { teacherApi } from "../../services/api.js";
import { Card, Empty, ErrorText, TableWrap, btn, field, fmtDateTime } from "./ui.jsx";

const PLACEHOLDER = "[REQUIRES RESEARCHER APPROVAL]";
const label = "flex min-w-0 flex-col gap-1 text-xs text-muted";
const small = "min-h-9 rounded-full border px-3 py-1 text-xs";

const toLocalInput = (v) => (v ? new Date(new Date(v).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");

function StatusBadge({ inst }) {
  return (
    <span className="flex flex-wrap gap-1 text-[11px] font-semibold uppercase">
      <span className={`rounded-full px-2 py-0.5 ${inst.status === "published" ? "bg-green-100 text-green-800" : inst.status === "draft" ? "bg-brass/20 text-navydeep" : "bg-rule text-muted"}`}>
        {inst.status}
      </span>
      {inst.is_shell ? <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-800">Shell: requires researcher approval</span> : null}
      {inst.phase !== "none" ? <span className="rounded-full bg-sky-100 px-2 py-0.5 text-sky-900">{inst.phase}-questionnaire</span> : null}
      <span className="rounded-full border border-rule px-2 py-0.5 text-muted">Not a validated scale in this app</span>
    </span>
  );
}

function Editor({ id, onDone }) {
  const [f, setF] = useState(null);
  const [all, setAll] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(false);
  useEffect(() => {
    teacherApi.instruments().then((d) => setAll(d.instruments)).catch(() => setAll([]));
    if (!id) {
      setF({ title: "", construct: "", description: "", scale_min: 1, scale_max: 5, labels: "Strongly disagree, Disagree, Neutral, Agree, Strongly agree", min_answered_ratio: 0.5, phase: "none", pre_instrument_id: "", available_from: "", available_until: "", approval_note: "", items: [] });
      return;
    }
    teacherApi
      .instrument(id)
      .then(({ instrument: i }) => {
        setLocked(i.status === "published" || i.responses > 0);
        setF({
          ...i,
          labels: (i.scale_labels || []).join(", "),
          pre_instrument_id: i.pre_instrument_id || "",
          available_from: toLocalInput(i.available_from),
          available_until: toLocalInput(i.available_until),
          approval_note: i.approval_note || "",
          items: i.items.map((it) => ({ text: it.text, subscale: it.subscale, reverse_scored: it.reverse_scored })),
        });
      })
      .catch((e) => setError(e.message));
  }, [id]);
  if (!f) return <p className="text-sm text-muted">{error || "Loading…"}</p>;
  const set = (patch) => setF({ ...f, ...patch });
  const setItem = (idx, patch) => set({ items: f.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)) });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const labels = f.labels.split(",").map((x) => x.trim()).filter(Boolean);
    const body = {
      title: f.title,
      construct: f.construct,
      description: f.description || "",
      scale_min: Number(f.scale_min),
      scale_max: Number(f.scale_max),
      scale_labels: labels,
      min_answered_ratio: Number(f.min_answered_ratio),
      phase: f.phase,
      pre_instrument_id: f.phase === "post" && f.pre_instrument_id ? f.pre_instrument_id : null,
      available_from: f.available_from ? new Date(f.available_from).toISOString() : null,
      available_until: f.available_until ? new Date(f.available_until).toISOString() : null,
      approval_note: f.approval_note || null,
      ...(locked ? {} : { items: f.items }),
    };
    try {
      if (id) await teacherApi.updateInstrument(id, body);
      else await teacherApi.createInstrument(body);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className={label}>
          Title
          <input className={field} required minLength={3} value={f.title} onChange={(e) => set({ title: e.target.value })} />
        </label>
        <label className={label}>
          Construct (what it is meant to describe)
          <input className={field} required value={f.construct} onChange={(e) => set({ construct: e.target.value })} />
        </label>
        <label className={`${label} sm:col-span-2`}>
          Description shown to students
          <textarea className={`${field} py-2`} rows={2} value={f.description || ""} onChange={(e) => set({ description: e.target.value })} />
        </label>
        <label className={label}>
          Scale from
          <input className={field} type="number" min="0" max="9" disabled={locked} value={f.scale_min} onChange={(e) => set({ scale_min: e.target.value })} />
        </label>
        <label className={label}>
          Scale to
          <input className={field} type="number" min="1" max="10" disabled={locked} value={f.scale_max} onChange={(e) => set({ scale_max: e.target.value })} />
        </label>
        <label className={`${label} sm:col-span-2`}>
          Scale point labels (comma separated, one per point, or empty)
          <input className={field} value={f.labels} onChange={(e) => set({ labels: e.target.value })} />
        </label>
        <label className={label}>
          Minimum share of a subscale's items answered to score it
          <input className={field} type="number" min="0.1" max="1" step="0.05" value={f.min_answered_ratio} onChange={(e) => set({ min_answered_ratio: e.target.value })} />
        </label>
        <label className={label}>
          Pre / post
          <select className={field} value={f.phase} onChange={(e) => set({ phase: e.target.value })}>
            <option value="none">Neither</option>
            <option value="pre">Pre-questionnaire</option>
            <option value="post">Post-questionnaire</option>
          </select>
        </label>
        {f.phase === "post" ? (
          <label className={label}>
            Linked pre-questionnaire
            <select className={field} value={f.pre_instrument_id} onChange={(e) => set({ pre_instrument_id: e.target.value })}>
              <option value="">Choose…</option>
              {all.filter((i) => i.phase === "pre" && i.id !== id).map((i) => (
                <option key={i.id} value={i.id}>{i.title}</option>
              ))}
            </select>
          </label>
        ) : null}
        <label className={label}>
          Opens (IST)
          <input className={field} type="datetime-local" value={f.available_from} onChange={(e) => set({ available_from: e.target.value })} />
        </label>
        <label className={label}>
          Closes (IST)
          <input className={field} type="datetime-local" value={f.available_until} onChange={(e) => set({ available_until: e.target.value })} />
        </label>
        <label className={`${label} sm:col-span-2`}>
          Approval note (required to publish): who approved the items, and their source
          <textarea className={`${field} py-2`} rows={2} value={f.approval_note} onChange={(e) => set({ approval_note: e.target.value })} />
        </label>
      </div>
      <fieldset className="space-y-2" disabled={locked}>
        <legend className="text-sm font-semibold">Items {locked ? "(locked: published or already answered)" : ""}</legend>
        {f.items.length === 0 ? <Empty>No items yet. Paste the researcher-approved items.</Empty> : null}
        {f.items.map((it, idx) => (
          <div key={idx} className={`grid gap-2 rounded-2xl border p-3 sm:grid-cols-[1fr_12rem_auto] ${it.text.includes(PLACEHOLDER) ? "border-red-300 bg-red-50" : "border-rule"}`}>
            <label className={label}>
              Item {idx + 1}
              <textarea className={`${field} py-2`} rows={2} value={it.text} onChange={(e) => setItem(idx, { text: e.target.value })} />
            </label>
            <label className={label}>
              Subscale
              <input className={field} value={it.subscale} onChange={(e) => setItem(idx, { subscale: e.target.value })} />
            </label>
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex min-h-11 items-center gap-2 text-xs">
                <input type="checkbox" className="h-5 w-5" checked={it.reverse_scored} onChange={(e) => setItem(idx, { reverse_scored: e.target.checked })} />
                Reverse-scored
              </label>
              <button type="button" className={`${small} border-rule`} onClick={() => set({ items: f.items.filter((_, i) => i !== idx) })}>
                Remove
              </button>
            </div>
          </div>
        ))}
        <button type="button" className={`${small} border-navy text-navy`} onClick={() => set({ items: [...f.items, { text: "", subscale: "Total", reverse_scored: false }] })}>
          Add item
        </button>
      </fieldset>
      <ErrorText>{error}</ErrorText>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={`${btn} bg-navy text-cream`} disabled={busy}>
          {busy ? "Saving…" : "Save draft"}
        </button>
        <button type="button" className={`${btn} border border-rule`} onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Results({ id, range }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(null);
    teacherApi.instrumentResults(id, range).then(setData).catch((e) => setError(e.message));
  }, [id, range]);
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-3 text-sm">
      <p>
        Submitted: <strong data-testid="q-submitted">{data.submitted}</strong> · Saved but not submitted: {data.in_progress} · {data.range.from} to {data.range.to} (IST)
      </p>
      {data.submitted === 0 ? <Empty>No submitted responses in this date range.</Empty> : null}
      <TableWrap label="Subscale results">
        <table className="w-full min-w-[480px] text-left">
          <thead className="text-xs uppercase text-muted">
            <tr><th className="py-1 pr-2">Subscale</th><th className="pr-2">n scored</th><th className="pr-2">Insufficient</th><th className="pr-2">Mean</th><th className="pr-2">Median</th><th className="pr-2">SD</th><th>Range</th></tr>
          </thead>
          <tbody>
            {data.subscales.map((s) => (
              <tr key={s.subscale} className="border-t border-rule">
                <td className="py-1 pr-2">{s.subscale}</td><td className="pr-2">{s.n}</td><td className="pr-2">{s.insufficient}</td>
                <td className="pr-2">{s.mean ?? "—"}</td><td className="pr-2">{s.median ?? "—"}</td><td className="pr-2">{s.sd ?? "—"}</td>
                <td>{s.min == null ? "—" : `${s.min}–${s.max}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      <TableWrap label="Item results">
        <table className="w-full min-w-[480px] text-left">
          <thead className="text-xs uppercase text-muted">
            <tr><th className="py-1 pr-2">#</th><th className="pr-2">Item</th><th className="pr-2">Answered</th><th className="pr-2">Missing</th><th>Mean (raw)</th></tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={i.id} className="border-t border-rule align-top">
                <td className="py-1 pr-2">{i.position}{i.reverse_scored ? " (R)" : ""}</td><td className="pr-2">{i.text}</td>
                <td className="pr-2">{i.answered}</td><td className="pr-2">{i.missing}</td><td>{i.mean ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      {data.pre_post ? (
        <div className="rounded-2xl border border-rule p-3">
          <p className="font-semibold">Pre/post (matched students) vs {data.pre_post.pre_title}</p>
          <ul className="mt-1 space-y-1">
            {data.pre_post.subscales.map((s) => (
              <li key={s.subscale}>
                {s.subscale}: paired n {s.paired_n}; mean pre {s.mean_pre ?? "—"}, post {s.mean_post ?? "—"}, gain {s.mean_gain ?? "—"};{" "}
                {s.paired_t.t != null ? `t = ${s.paired_t.t}, df = ${s.paired_t.df}, p = ${s.paired_t.p}` : s.paired_t.note}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">
            Unmatched — post only: {data.pre_post.unmatched_post.join(", ") || "none"}; pre only: {data.pre_post.unmatched_pre.join(", ") || "none"}. {data.pre_post.note}
          </p>
        </div>
      ) : null}
      <p className="text-xs text-muted">{data.scoring}</p>
      <p className="text-xs text-muted">{data.validity_note}</p>
    </div>
  );
}

function PrePostSummary({ range }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(null);
    teacherApi.achievement({ from: range.from, to: range.to }).then((d) => setData(d.pre_post)).catch((e) => setError(e.message));
  }, [range.from, range.to]);
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <>
      {!data.pairs.length ? (
        <Empty>{data.note}</Empty>
      ) : (
        <ul className="space-y-2" data-testid="prepost-pairs">
          {data.pairs.map((p) => (
            <li key={p.post_quiz.id} className="min-w-0 rounded-2xl border border-rule p-3 text-sm">
              <p className="font-medium break-words">
                {p.pre_quiz.title} ({p.pre_quiz.status}) → {p.post_quiz.title} ({p.post_quiz.status})
              </p>
              <p className="text-xs text-muted" data-testid="prepost-counts">
                Pre-test takers {p.pre_quiz.n} · post-test takers in range {p.post_quiz.n} · <strong>matched n = {p.paired_n}</strong> · unmatched: {p.unmatched.pre_only.length} pre only, {p.unmatched.post_only.length} post only
              </p>
              <p className="text-xs text-muted">
                {p.paired_n ? `Mean pre ${p.mean_pre}% → post ${p.mean_post}% (gain ${p.mean_gain})` : "No matched students yet, so no comparison is shown."}
                {p.paired_n && p.paired_n < 2 ? " · n too small for a t statistic." : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">
        Limitations: {data.method} No control group; small n is unreliable; first finished attempts only (timed-out attempts count with their autosaved answers). Full detail is in Analytics → Achievement.
      </p>
    </>
  );
}

export default function Research({ range }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  const [panel, setPanel] = useState(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    teacherApi
      .instruments()
      .then((d) => setList(d))
      .catch((e) => setError(e.message));
  }, [reload]);
  const status = async (inst, s) => {
    setError("");
    try {
      await teacherApi.instrumentStatus(inst.id, s);
      setReload((n) => n + 1);
    } catch (e) {
      setError(e.message);
    }
  };
  const done = () => {
    setPanel(null);
    setReload((n) => n + 1);
  };
  return (
    <div className="space-y-4">
      {panel?.kind === "edit" ? (
        <Card title={panel.id ? "Edit questionnaire" : "New questionnaire"}>
          <Editor id={panel.id} onDone={done} />
        </Card>
      ) : null}
      {panel?.kind === "results" ? (
        <Card
          title="Questionnaire results"
          actions={
            <button type="button" className={`${btn} border border-navy text-navy`} onClick={() => setPanel(null)}>
              Close
            </button>
          }
        >
          <Results id={panel.id} range={range} />
        </Card>
      ) : null}
      <Card title="Pre/post comparisons">
        <PrePostSummary range={range} />
      </Card>
      <Card
        title="Research questionnaires"
        actions={
          <button type="button" className={`${btn} bg-navy text-cream`} onClick={() => setPanel({ kind: "edit", id: null })}>
            New questionnaire
          </button>
        }
      >
        <p className="text-sm text-muted">
          Digital Attitude and Social Engagement are empty <strong>shells</strong>. They cannot be published until every placeholder is replaced with the researcher's
          approved items and an approval note is entered. No validated scale or cutoff is built in; results are descriptive.
        </p>
        <ErrorText>{error}</ErrorText>
        {!list ? (
          <p className="mt-3 text-sm text-muted">Loading…</p>
        ) : list.instruments.length === 0 ? (
          <Empty>No questionnaires yet.</Empty>
        ) : (
          <ul className="mt-3 space-y-2">
            {list.instruments.map((i) => (
              <li key={i.id} className="min-w-0 rounded-2xl border border-rule p-3 text-sm" data-testid="instrument">
                <StatusBadge inst={i} />
                {i.is_shell ? <p className="mt-1 text-xs font-semibold text-red-800">Blocked: requires researcher-approved items before publishing.</p> : null}
                <p className="mt-1 font-medium">{i.title}</p>
                <p className="text-xs text-muted">
                  {i.construct} · {i.item_count} items{i.placeholder_count ? ` (${i.placeholder_count} placeholders)` : ""} · {i.submitted} submitted
                  {i.published_at ? ` · published ${fmtDateTime(i.published_at)}` : ""}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className={`${small} border-navy text-navy`} onClick={() => setPanel({ kind: "edit", id: i.id })}>
                    Edit
                  </button>
                  <button type="button" className={`${small} border-rule`} onClick={() => setPanel({ kind: "results", id: i.id })}>
                    Results
                  </button>
                  {i.status === "draft" && !i.is_shell ? (
                    <button type="button" className={`${small} border-navy bg-navy text-cream`} onClick={() => status(i, "published")}>
                      Publish
                    </button>
                  ) : null}
                  {i.status === "published" ? (
                    <button type="button" className={`${small} border-rule`} onClick={() => status(i, "archived")}>
                      Archive
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

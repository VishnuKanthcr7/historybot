import { useEffect, useState } from "react";
import { downloadReportCsv, teacherApi } from "../../services/api.js";
import { Card, ErrorText, btn, field } from "./ui.jsx";

const REPORTS = [
  ["attempts", "Quiz attempts", "One row per submitted attempt: quiz, topic, mode, score, time taken."],
  ["students", "Students", "One row per student: chat questions, quiz attempts, mean score, last active."],
  ["topics", "Topics", "One row per topic: answers, students, accuracy."],
  ["prepost", "Pre/post (matched)", "One row per student per linked pre/post pair: pre %, post %, gain; unmatched students marked."],
];

export default function Reports({ range }) {
  const [names, setNames] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [instruments, setInstruments] = useState([]);
  const [instrumentId, setInstrumentId] = useState("");
  useEffect(() => {
    teacherApi
      .instruments()
      .then((d) => setInstruments(d.instruments.filter((i) => i.status !== "draft")))
      .catch(() => setInstruments([]));
  }, []);
  const download = async (kind) => {
    setError("");
    setBusy(kind);
    try {
      const extra = kind === "questionnaires" ? { instrument_id: instrumentId } : {};
      const blob = await downloadReportCsv(kind, { ...range, ...extra, include_names: names ? "1" : "" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `historybot-${kind}-${range.from}-to-${range.to}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };
  return (
    <Card title="Reports and CSV exports">
      <p className="text-sm text-muted">
        Exports use the date range above. Students appear as pseudonymous codes (S-xxxxxxxx) unless you include names. Emails, passwords and chat text are never exported.
      </p>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-5 w-5" checked={names} onChange={(e) => setNames(e.target.checked)} /> Include student names
      </label>
      <ul className="mt-3 space-y-2">
        {REPORTS.map(([kind, title, text]) => (
          <li key={kind} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-rule p-3">
            <div>
              <p className="font-medium">{title}</p>
              <p className="text-xs text-muted">{text}</p>
            </div>
            <button type="button" disabled={busy === kind} onClick={() => download(kind)} className={`${btn} bg-navy text-cream`}>
              {busy === kind ? "Preparing…" : "Download CSV"}
            </button>
          </li>
        ))}
        <li className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-rule p-3">
          <div className="min-w-0">
            <p className="font-medium">Questionnaire responses</p>
            <p className="text-xs text-muted">One row per submitted response: subscale scores and item values (blank = not answered).</p>
            <label className="mt-2 block text-xs text-muted">
              Questionnaire
              <select className={`${field} mt-1 block w-full max-w-full`} value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)}>
                <option value="">Choose…</option>
                {instruments.map((i) => (
                  <option key={i.id} value={i.id}>{i.title}</option>
                ))}
              </select>
            </label>
            {!instruments.length ? <p className="mt-1 text-xs text-muted">No published questionnaires yet.</p> : null}
          </div>
          <button type="button" disabled={!instrumentId || busy === "questionnaires"} onClick={() => download("questionnaires")} className={`${btn} bg-navy text-cream`}>
            {busy === "questionnaires" ? "Preparing…" : "Download CSV"}
          </button>
        </li>
      </ul>
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}

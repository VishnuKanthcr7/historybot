import { useEffect, useState } from "react";
import { downloadReport, teacherApi } from "../../services/api.js";
import { Card, ErrorText, btn, field } from "./ui.jsx";

const REPORTS = [
  ["research_summary", "Research summary", "Totals for the dates: students, active students, log-ins, chat questions, modules, PDFs, quizzes, mean scores, and when tracking began."],
  ["students", "Student activity (all students)", "One row per student: roll no., chat questions, quiz attempts, mean score, modules done, last active."],
  ["class_activity", "Class activity by day", "One row per IST day and activity type: how many times, and how many students."],
  ["attempts", "Assessment report (quiz attempts)", "One row per submitted attempt: quiz, topic, mode, score, time taken."],
  ["progress", "Learning progress (modules)", "One row per student per learning module: opened, times opened, PDFs, completed."],
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
  const download = async (kind, ext = "csv") => {
    setError("");
    setBusy(`${kind}.${ext}`);
    try {
      const extra = kind === "questionnaires" ? { instrument_id: instrumentId } : {};
      const blob = await downloadReport(kind, { ...range, ...extra, include_names: names ? "1" : "" }, ext);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `historybot-${kind}-${range.from}-to-${range.to}.${ext}`;
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
    <Card title="Reports (CSV and PDF)">
      <p className="text-sm text-muted">
        Exports use the date range above. Students appear as pseudonymous codes (S-xxxxxxxx) unless you include names. Emails, passwords and chat text are never exported. A single student's activity timeline (CSV/PDF) is in Students: open a student. Activity from before tracking began is not available (see the research summary).
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
            <div className="flex gap-2">
              <button type="button" disabled={busy === `${kind}.csv`} onClick={() => download(kind, "csv")} className={`${btn} bg-navy text-cream`}>
                {busy === `${kind}.csv` ? "Preparing..." : "CSV"}
              </button>
              <button type="button" disabled={busy === `${kind}.pdf`} onClick={() => download(kind, "pdf")} className={`${btn} border border-navy text-navy`}>
                {busy === `${kind}.pdf` ? "Preparing..." : "PDF"}
              </button>
            </div>
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
          <button type="button" disabled={!instrumentId || busy === "questionnaires.csv"} onClick={() => download("questionnaires")} className={`${btn} bg-navy text-cream`}>
            {busy === "questionnaires.csv" ? "Preparing…" : "Download CSV"}
          </button>
        </li>
      </ul>
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}

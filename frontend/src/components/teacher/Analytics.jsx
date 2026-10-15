import { useEffect, useState } from "react";
import { teacherApi } from "../../services/api.js";
import { Bars, Card, ErrorText, btn, field, fmtDate } from "./ui.jsx";

const CARD_LABELS = {
  students_total: "Students",
  active_students: "Active students",
  chat_questions: "Chat questions",
  modules_generated: "Learning modules",
  quiz_attempts: "Quiz attempts",
  mean_percent: "Mean quiz score",
  sign_ins: "Sign-ins",
};

export function Overview({ range }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(null);
    teacherApi.overview(range).then(setData).catch((e) => setError(e.message));
  }, [range]);
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Object.entries(CARD_LABELS).map(([key, label]) => {
          const v = data.cards[key];
          return (
            <div key={key} className="rounded-3xl border border-rule bg-cream p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
              <p className="mt-1 font-serif text-3xl text-navy">{v == null ? "—" : key === "mean_percent" ? `${v}%` : v}</p>
              <p className="mt-1 text-xs leading-snug text-muted">{v == null && key !== "mean_percent" ? "Data not available" : data.definitions[key]}</p>
            </div>
          );
        })}
      </div>
      {data.notes.quiz ? <p className="rounded-2xl bg-brass/10 p-3 text-sm">{data.notes.quiz}</p> : null}
      <Card title="About these numbers">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Quiz tracking began {data.tracking.quiz_tracking_began ? fmtDate(data.tracking.quiz_tracking_began) : "—"}. {data.tracking.chat_tracking}</li>
          <li>{data.notes.sign_ins}</li>
          {data.not_implemented.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function StudentProfile({ id, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    teacherApi.student(id).then(setData).catch((e) => setError(e.message));
  }, [id]);
  return (
    <Card
      title={data ? data.student.display_name : "Student"}
      actions={
        <button type="button" onClick={onClose} className={`${btn} border border-navy text-navy`}>
          Close
        </button>
      }
    >
      <ErrorText>{error}</ErrorText>
      {!data ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <p className="text-sm text-muted">
              Joined {fmtDate(data.student.joined)} · {data.totals.chat_questions} chat questions · {data.totals.quiz_attempts} quiz attempts
            </p>
            <h3 className="mt-3 text-sm font-semibold">Attempts over time</h3>
            {data.attempts.length === 0 ? (
              <p className="text-sm text-muted">No quiz attempts yet.</p>
            ) : (
              <Bars
                items={data.attempts}
                label={(a) => `${fmtDate(a.submitted_at)} · ${a.title}`}
                value={(a) => a.percent}
                suffix="%"
              />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold">Observed topics (quiz accuracy)</h3>
            {data.observed_topics.length === 0 ? (
              <p className="text-sm text-muted">No topic data yet.</p>
            ) : (
              <Bars items={data.observed_topics} label={(t) => t.topic} value={(t) => t.accuracy} suffix="%" note={(t) => `n=${t.answered}`} />
            )}
            <h3 className="mt-3 text-sm font-semibold">Suggested revision</h3>
            {data.suggested_topics.length === 0 ? (
              <p className="text-sm text-muted">Nothing below 70% accuracy.</p>
            ) : (
              <ul className="list-disc pl-5 text-sm">
                {data.suggested_topics.map((t) => (
                  <li key={t.topic}>
                    {t.topic} ({t.accuracy}%){t.textbook_pages.length ? ` — textbook p. ${t.textbook_pages.join(", ")}` : ""}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-muted">{data.note}</p>
          </div>
        </div>
      )}
    </Card>
  );
}

const COLS = [
  ["name", "Student"],
  ["joined", "Joined"],
  ["chat_questions", "Chat questions"],
  ["quiz_attempts", "Quiz attempts"],
  ["mean_percent", "Mean score"],
  ["last_active", "Last active"],
];

export function StudentsTable({ range }) {
  const [q, setQ] = useState({ search: "", sort: "name", dir: "asc", page: 1, size: 20, activity: "all" });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  useEffect(() => {
    const t = setTimeout(() => {
      teacherApi
        .students({ ...range, ...q })
        .then(setData)
        .catch((e) => setError(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [range, q]);
  const pages = data ? Math.max(1, Math.ceil(data.total / q.size)) : 1;
  const sortBy = (key) => setQ({ ...q, sort: key, dir: q.sort === key && q.dir === "asc" ? "desc" : "asc", page: 1 });
  return (
    <div className="space-y-4">
      {open ? <StudentProfile id={open} onClose={() => setOpen(null)} /> : null}
      <Card title="Students">
        <div className="mb-3 flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="st-search">
            Search students
          </label>
          <input id="st-search" className={`${field} flex-1`} placeholder="Search by name" value={q.search} onChange={(e) => setQ({ ...q, search: e.target.value, page: 1 })} />
          <label className="sr-only" htmlFor="st-activity">
            Activity filter
          </label>
          <select id="st-activity" className={field} value={q.activity} onChange={(e) => setQ({ ...q, activity: e.target.value, page: 1 })}>
            <option value="all">All students</option>
            <option value="active">Active in range</option>
            <option value="inactive">No activity in range</option>
          </select>
        </div>
        <ErrorText>{error}</ErrorText>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-xs uppercase text-muted">
              <tr>
                {COLS.map(([key, label]) => (
                  <th key={key} className="py-2 pr-2" aria-sort={q.sort === key ? (q.dir === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" className="min-h-9 uppercase" onClick={() => sortBy(key)}>
                      {label} {q.sort === key ? (q.dir === "asc" ? "▲" : "▼") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data?.students || []).map((s) => (
                <tr key={s.id} className="border-t border-rule">
                  <td className="py-2 pr-2">
                    <button type="button" className="text-left text-navy underline" onClick={() => setOpen(s.id)}>
                      {s.display_name}
                    </button>
                  </td>
                  <td className="py-2 pr-2">{fmtDate(s.joined)}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.chat_questions}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.quiz_attempts}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.mean_percent == null ? "—" : `${s.mean_percent}%`}</td>
                  <td className="py-2 pr-2">{fmtDate(s.last_active)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.students.length === 0 ? <p className="py-3 text-sm text-muted">No students match.</p> : null}
        <div className="mt-3 flex items-center justify-between text-sm">
          <span className="text-muted">{data ? `${data.total} students` : ""}</span>
          <div className="flex items-center gap-2">
            <button type="button" className={`${btn} border border-rule`} disabled={q.page <= 1} onClick={() => setQ({ ...q, page: q.page - 1 })}>
              Previous
            </button>
            <span>
              {q.page} / {pages}
            </span>
            <button type="button" className={`${btn} border border-rule`} disabled={q.page >= pages} onClick={() => setQ({ ...q, page: q.page + 1 })}>
              Next
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">Counts for the selected dates. Chat contents and emails are not shown.</p>
      </Card>
    </div>
  );
}

export function TopicsAndTrends({ range }) {
  const [topics, setTopics] = useState(null);
  const [series, setSeries] = useState(null);
  const [bucket, setBucket] = useState("day");
  const [error, setError] = useState("");
  useEffect(() => {
    teacherApi.topics(range).then((d) => setTopics(d.topics)).catch((e) => setError(e.message));
  }, [range]);
  useEffect(() => {
    teacherApi.timeseries({ ...range, bucket }).then(setSeries).catch((e) => setError(e.message));
  }, [range, bucket]);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ErrorText>{error}</ErrorText>
      <Card title="Topic analytics">
        {!topics ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : topics.length === 0 ? (
          <p className="text-sm text-muted">No quiz answers in this date range.</p>
        ) : (
          <Bars items={topics} label={(t) => t.topic} value={(t) => t.accuracy} suffix="%" note={(t) => `${t.answered} answers · ${t.students} students`} />
        )}
      </Card>
      <Card
        title="Performance over time"
        actions={
          <select aria-label="Group by" className={field} value={bucket} onChange={(e) => setBucket(e.target.value)}>
            <option value="day">By day</option>
            <option value="week">By week</option>
          </select>
        }
      >
        {!series ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : series.series.length === 0 ? (
          <p className="text-sm text-muted">No activity in this date range.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-left text-sm">
                <thead className="text-xs uppercase text-muted">
                  <tr>
                    <th className="py-1 pr-2">{bucket === "week" ? "Week of" : "Day"}</th>
                    <th className="py-1 pr-2">Mean score</th>
                    <th className="py-1 pr-2">Attempts (n)</th>
                    <th className="py-1 pr-2">Chat questions</th>
                  </tr>
                </thead>
                <tbody>
                  {series.series.map((p) => (
                    <tr key={p.bucket} className="border-t border-rule">
                      <td className="py-1 pr-2">{p.bucket}</td>
                      <td className="py-1 pr-2">{p.mean_percent == null ? "—" : `${p.mean_percent}%`}</td>
                      <td className="py-1 pr-2">{p.quiz_attempts}</td>
                      <td className="py-1 pr-2">{p.chat_questions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted">{series.note}</p>
          </>
        )}
      </Card>
    </div>
  );
}

function StatBlock({ s }) {
  if (!s || !s.n) return <p className="text-sm text-muted">No attempts.</p>;
  return (
    <div>
      <dl className="grid grid-cols-3 gap-2 text-sm">
        {[
          ["n", s.n],
          ["Mean", `${s.mean}%`],
          ["Median", `${s.median}%`],
          ["SD", s.sd == null ? "—" : s.sd],
          ["Min", `${s.min}%`],
          ["Max", `${s.max}%`],
        ].map(([k, v]) => (
          <div key={k} className="rounded-2xl bg-paper p-2">
            <dt className="text-xs text-muted">{k}</dt>
            <dd className="font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      <h3 className="mt-3 text-sm font-semibold">Score distribution</h3>
      <Bars items={s.distribution} label={(d) => `${d.label}%`} value={(d) => d.count} max={Math.max(...s.distribution.map((d) => d.count), 1)} />
    </div>
  );
}

export function Achievement({ range }) {
  const [quizId, setQuizId] = useState("");
  const [quizzes, setQuizzes] = useState([]);
  useEffect(() => {
    teacherApi
      .quizzes()
      .then((d) => setQuizzes(d.quizzes))
      .catch(() => setQuizzes([]));
  }, []);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    teacherApi.achievement({ ...range, quiz_id: quizId }).then(setData).catch((e) => setError(e.message));
  }, [range, quizId]);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card
        title="Achievement"
        actions={
          <select aria-label="Quiz" className={`${field} w-full max-w-full sm:w-auto`} value={quizId} onChange={(e) => setQuizId(e.target.value)}>
            <option value="">All teacher quizzes</option>
            {(quizzes || []).map((q) => (
              <option key={q.id} value={q.id}>
                {q.title}
              </option>
            ))}
          </select>
        }
      >
        <ErrorText>{error}</ErrorText>
        {data ? (
          <>
            <StatBlock s={data.overall} />
            <p className="mt-2 text-xs text-muted">{data.basis}</p>
          </>
        ) : (
          <p className="text-sm text-muted">Loading…</p>
        )}
      </Card>
      <Card title="Pre-test / post-test">
        {!data ? null : data.pre_post.available ? (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <h3 className="text-sm font-semibold">Pre-test</h3>
                <StatBlock s={data.pre_post.pre} />
              </div>
              <div>
                <h3 className="text-sm font-semibold">Post-test</h3>
                <StatBlock s={data.pre_post.post} />
              </div>
            </div>
            <p className="text-sm">
              Students with both: <strong>{data.pre_post.paired_n}</strong>
              {data.pre_post.mean_change != null ? ` · mean change ${data.pre_post.mean_change} points` : ""}
            </p>
            <p className="text-xs text-muted">{data.pre_post.note}</p>
          </div>
        ) : (
          <p className="text-sm text-muted">{data.pre_post.note}</p>
        )}
      </Card>
    </div>
  );
}

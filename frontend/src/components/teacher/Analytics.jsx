import { useEffect, useState } from "react";
import { teacherApi } from "../../services/api.js";
import { Bars, Card, Empty, ErrorText, TableWrap, btn, field, fmtDate, fmtDateTime } from "./ui.jsx";

// Headline cards first, then the detail cards. Every value comes from the API; null means "not available".
const HEADLINE = [
  ["registered_in_range", "Registered (in range)"],
  ["active_students", "Active students"],
  ["modules_completed", "Modules completed"],
  ["assessments_submitted", "Assessments submitted"],
  ["mean_percent", "Assessment average"],
  ["practice_mean_percent", "Practice average"],
];
const DETAIL = [
  ["students_total", "Student accounts (all time)"],
  ["sign_ins", "Sign-ins"],
  ["chat_questions", "Chat questions"],
  ["modules_generated", "Modules generated"],
  ["modules_opened", "Modules opened"],
  ["pdf_downloads", "PDF downloads"],
  ["quiz_attempts", "Quiz/activity attempts finished"],
  ["timed_out", "Timed out"],
  ["abandoned", "Abandoned"],
];

function StatCard({ label, value, percent, definition, n, nNote, strong }) {
  return (
    <div className={`min-w-0 rounded-3xl border p-4 ${strong ? "border-navy/40 bg-cream" : "border-rule bg-cream"}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-serif text-3xl text-navy" data-testid="stat-value">
        {value == null ? (percent ? <span className="text-xl text-muted">No data</span> : "—") : percent ? `${value}%` : value}
      </p>
      {n != null ? <p className="text-xs text-muted">{n === 0 ? "No qualifying attempts" : `n = ${n} attempt${n === 1 ? "" : "s"}${nNote ? ` (${nNote})` : ""}`}</p> : null}
      {value == null && !percent ? <p className="mt-1 text-xs text-muted">Data not available.</p> : null}
      {definition ? (
        <details className="mt-1 text-xs leading-snug text-muted">
          <summary className="cursor-pointer select-none py-1 text-navy underline-offset-2 hover:underline">What counts?</summary>
          <p className="mt-1">{definition}</p>
        </details>
      ) : null}
    </div>
  );
}

const TREND_SERIES = [
  ["chat_questions", "Chat questions", "bg-brass/70"],
  ["quiz_attempts", "Quiz attempts", "bg-navy"],
  ["modules_opened", "Modules opened", "bg-emerald-700"],
  ["modules_completed", "Modules completed", "bg-sky-800"],
  ["pdf_downloads", "PDF downloads", "bg-stone-500"],
];

// Root cause of the earlier blank chart: each day column was a flex child with height "auto", so the bars'
// percentage heights resolved to 0. Columns now stretch to the fixed chart height (h-40, self-stretch) and
// bar heights are a share of the busiest day. Every IST day in the range is a column (zeros included).
export function Trend({ range }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(null);
    setError("");
    teacherApi.timeseries({ from: range.from, to: range.to, bucket: "day" }).then(setData).catch((e) => setError(e.message));
  }, [range.from, range.to]);
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  if (!data.series?.length || data.empty) return <Empty>No chat questions, quiz attempts or module activity in this date range.</Empty>;
  const total = (d) => TREND_SERIES.reduce((s, [k]) => s + (d[k] || 0), 0);
  const max = Math.max(1, ...data.series.map(total));
  const n = data.series.length;
  const labelEvery = Math.max(1, Math.ceil(n / 8));
  return (
    <>
      <div className="overflow-x-auto">
        <div className="flex h-40 items-stretch gap-px border-b border-rule" style={{ minWidth: `${Math.min(n * 10, 1200)}px` }} role="img" aria-label={`Daily activity from ${data.range.from} to ${data.range.to}`} data-testid="trend-chart">
          {data.series.map((d) => (
            <div
              key={d.bucket}
              data-testid="trend-day"
              data-total={total(d)}
              className="flex min-w-[6px] flex-1 flex-col-reverse self-stretch"
              title={`${d.bucket}: ${TREND_SERIES.map(([k, l]) => `${d[k] || 0} ${l.toLowerCase()}`).join(", ")}`}
            >
              {TREND_SERIES.map(([k, , color]) => (d[k] ? <div key={k} className={color} style={{ height: `${(d[k] / max) * 100}%` }} /> : null))}
            </div>
          ))}
        </div>
        <div className="flex gap-px text-[10px] text-muted" style={{ minWidth: `${Math.min(n * 10, 1200)}px` }} aria-hidden="true">
          {data.series.map((d, i) => (
            <span key={d.bucket} className="min-w-[6px] flex-1 overflow-visible whitespace-nowrap">{i % labelEvery === 0 ? d.bucket.slice(5) : ""}</span>
          ))}
        </div>
      </div>
      <p className="mt-2 flex flex-wrap gap-3 text-xs text-muted">
        {TREND_SERIES.map(([k, label, color]) => (
          <span key={k}>
            <span className={`mr-1 inline-block h-2 w-3 align-middle ${color}`} />
            {label} ({data.totals[k]})
          </span>
        ))}
        <span>IST days {data.range.from} to {data.range.to}, inclusive; tallest day = {max}.</span>
      </p>
    </>
  );
}

export function Overview({ range }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(null);
    setError("");
    teacherApi.overview(range).then(setData).catch((e) => setError(e.message));
  }, [range]);
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  const pct = new Set(["mean_percent", "practice_mean_percent"]);
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted" data-testid="data-as-of">
        Data as of {fmtDateTime(data.data_as_of)} · {data.range.from} to {data.range.to} inclusive (IST)
      </p>
      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-6" data-testid="headline-cards">
        {HEADLINE.map(([key, label]) => (
          <StatCard
            key={key}
            strong
            label={label}
            value={data.cards[key]}
            percent={pct.has(key)}
            definition={data.definitions[key]}
            n={key === "mean_percent" ? data.cards.mean_percent_n : key === "practice_mean_percent" ? data.cards.practice_mean_percent_n : null}
            nNote={key === "mean_percent" && data.cards.mean_percent_timed_out ? `${data.cards.mean_percent_timed_out} timed out` : ""}
          />
        ))}
      </div>
      {[data.notes.quiz, data.notes.progress].filter(Boolean).map((n) => (
        <p key={n} className="rounded-2xl bg-brass/10 p-3 text-sm">{n}</p>
      ))}
      <Card title="Activity over time">
        <Trend range={range} />
      </Card>
      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-5">
        {DETAIL.map(([key, label]) => (
          <StatCard key={key} label={label} value={data.cards[key]} percent={pct.has(key)} definition={data.definitions[key]} />
        ))}
      </div>
      <Card title="About these numbers">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Quiz tracking began {fmtDate(data.tracking.quiz_tracking_began)}; sign-in and module progress tracking began {fmtDate(data.tracking.progress_tracking_began)}. {data.tracking.chat_tracking}</li>
          <li>{data.notes.pdf}</li>
          <li>Logins and sign-ins are not attendance.</li>
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
  ["modules_completed", "Modules done"],
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
          <label className="sr-only" htmlFor="st-sort">
            Sort students
          </label>
          <select
            id="st-sort"
            className={`${field} sm:hidden`}
            value={`${q.sort}:${q.dir}`}
            onChange={(e) => {
              const [sort, dir] = e.target.value.split(":");
              setQ({ ...q, sort, dir, page: 1 });
            }}
          >
            {COLS.flatMap(([key, label]) => [
              <option key={`${key}:asc`} value={`${key}:asc`}>{label} (low to high)</option>,
              <option key={`${key}:desc`} value={`${key}:desc`}>{label} (high to low)</option>,
            ])}
          </select>
        </div>
        <ErrorText>{error}</ErrorText>
        {/* Phones: one card per student. Wider screens: the sortable table. */}
        <ul className="space-y-2 sm:hidden" aria-label="Students">
          {(data?.students || []).map((s) => (
            <li key={s.id} className="rounded-2xl border border-rule p-3 text-sm">
              <button type="button" className="min-h-9 text-left font-medium text-navy underline" onClick={() => setOpen(s.id)}>
                {s.display_name}
              </button>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <dt className="text-muted">Chat questions</dt><dd className="tabular-nums">{s.chat_questions}</dd>
                <dt className="text-muted">Quiz attempts</dt><dd className="tabular-nums">{s.quiz_attempts}</dd>
                <dt className="text-muted">Mean score</dt><dd className="tabular-nums">{s.mean_percent == null ? "—" : `${s.mean_percent}%`}</dd>
                <dt className="text-muted">Modules done</dt><dd className="tabular-nums">{s.modules_completed}</dd>
                <dt className="text-muted">Last active</dt><dd>{fmtDate(s.last_active)}</dd>
              </dl>
            </li>
          ))}
        </ul>
        <div className="hidden overflow-x-auto sm:block">
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
                    <button type="button" className="min-h-9 py-1 text-left text-navy underline" onClick={() => setOpen(s.id)}>
                      {s.display_name}
                    </button>
                  </td>
                  <td className="py-2 pr-2">{fmtDate(s.joined)}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.chat_questions}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.quiz_attempts}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.mean_percent == null ? "—" : `${s.mean_percent}%`}</td>
                  <td className="py-2 pr-2 tabular-nums">{s.modules_completed}</td>
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
        ) : series.empty || !series.series.some((p) => p.quiz_attempts || p.chat_questions) ? (
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
                  {series.series.filter((p) => p.quiz_attempts || p.chat_questions).map((p) => (
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
      <Card title="Pre-test / post-test (matched students)" className="lg:col-span-2">
        {!data ? null : data.pre_post.available ? (
          <div className="space-y-4">
            {data.pre_post.pairs.map((p) => (
              <div key={p.post_quiz.id} className="rounded-2xl border border-rule p-3" data-testid="prepost-pair">
                <p className="text-sm font-semibold">
                  {p.pre_quiz.title} → {p.post_quiz.title}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                  <div><dt className="text-xs text-muted">Paired n</dt><dd data-testid="paired-n" className="font-serif text-2xl text-navy">{p.paired_n}</dd></div>
                  <div><dt className="text-xs text-muted">Mean pre</dt><dd data-testid="mean-pre" className="font-serif text-2xl text-navy">{p.mean_pre ?? "—"}{p.mean_pre != null ? "%" : ""}</dd></div>
                  <div><dt className="text-xs text-muted">Mean post</dt><dd data-testid="mean-post" className="font-serif text-2xl text-navy">{p.mean_post ?? "—"}{p.mean_post != null ? "%" : ""}</dd></div>
                  <div><dt className="text-xs text-muted">Mean gain</dt><dd data-testid="mean-gain" className="font-serif text-2xl text-navy">{p.mean_gain ?? "—"}</dd></div>
                </dl>
                <p className="mt-2 text-xs text-muted">
                  Paired t-test (descriptive):{" "}
                  {p.paired_t.t != null ? `t = ${p.paired_t.t}, df = ${p.paired_t.df}, p = ${p.paired_t.p}` : p.paired_t.note}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Not matched — pre-test only: {p.unmatched.pre_only.length ? p.unmatched.pre_only.join(", ") : "none"}; post-test only:{" "}
                  {p.unmatched.post_only.length ? p.unmatched.post_only.join(", ") : "none"}
                </p>
              </div>
            ))}
            <p className="text-xs text-muted">{data.pre_post.method}</p>
          </div>
        ) : (
          <Empty>{data.pre_post.note}</Empty>
        )}
      </Card>
    </div>
  );
}

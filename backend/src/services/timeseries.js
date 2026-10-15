// Pure helpers for the "Activity over time" chart. Buckets are IST calendar days (or IST weeks starting Monday).
// Every bucket in the inclusive range is returned, with zeros, so the chart has a stable x-axis and an empty
// range is recognisable (all totals 0) rather than an empty array.
const DAY_MS = 24 * 60 * 60 * 1000;
const IST_MS = 330 * 60 * 1000;

export const ACTIVITY_KEYS = ["chat_questions", "quiz_attempts", "modules_opened", "modules_completed", "pdf_downloads", "sign_ins"];

// IST day key for a UTC instant (Date or ISO string).
export function istDayKey(d) {
  return new Date(new Date(d).getTime() + IST_MS).toISOString().slice(0, 10);
}

function weekStart(key) {
  const d = new Date(`${key}T00:00:00Z`);
  const dow = (d.getUTCDay() + 6) % 7; // Monday = 0
  return new Date(d.getTime() - dow * DAY_MS).toISOString().slice(0, 10);
}

export function bucketKey(dayKey, bucket) {
  return bucket === "week" ? weekStart(dayKey) : dayKey;
}

export function enumerateBuckets(from, to, bucket = "day") {
  const out = [];
  for (let t = new Date(`${from}T00:00:00Z`).getTime(); t <= new Date(`${to}T00:00:00Z`).getTime(); t += DAY_MS) {
    const k = bucketKey(new Date(t).toISOString().slice(0, 10), bucket);
    if (out[out.length - 1] !== k) out.push(k);
  }
  return out;
}

const emptyPoint = (bucket) => ({ bucket, ...Object.fromEntries(ACTIVITY_KEYS.map((k) => [k, 0])), quiz_students: 0, chat_students: 0, mean_percent: null });

// rows: { quiz: [{bucket,n,students,mean_percent}], chat: [{bucket,n,students}], events: [{bucket,event_type,n}] }
// Buckets coming from SQL are already IST day keys (YYYY-MM-DD).
export function buildSeries({ quiz = [], chat = [], events = [] }, from, to, bucket = "day") {
  const map = new Map(enumerateBuckets(from, to, bucket).map((b) => [b, emptyPoint(b)]));
  const at = (b) => map.get(bucketKey(String(b).slice(0, 10), bucket));
  for (const r of quiz) {
    const p = at(r.bucket);
    if (!p) continue;
    p.quiz_attempts += Number(r.n);
    p.quiz_students += Number(r.students || 0);
    p.mean_percent = r.mean_percent == null ? null : Math.round(Number(r.mean_percent) * 10) / 10;
  }
  for (const r of chat) {
    const p = at(r.bucket);
    if (!p) continue;
    p.chat_questions += Number(r.n);
    p.chat_students += Number(r.students || 0);
  }
  const typeKey = { MODULE_OPENED: "modules_opened", MODULE_COMPLETED: "modules_completed", PDF_DOWNLOADED: "pdf_downloads", USER_SIGNED_IN: "sign_ins" };
  for (const r of events) {
    const p = at(r.bucket);
    const k = typeKey[r.event_type];
    if (p && k) p[k] += Number(r.n);
  }
  const series = [...map.values()];
  const totals = Object.fromEntries(ACTIVITY_KEYS.map((k) => [k, series.reduce((s, p) => s + p[k], 0)]));
  return { series, totals, empty: Object.values(totals).every((v) => v === 0) };
}

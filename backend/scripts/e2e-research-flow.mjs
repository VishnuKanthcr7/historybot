// End-to-end research flow against ISOLATED test servers (backend :3100 -> RAG :8100, OpenAI blocked). No AI calls.
// Teacher + students A, B, C, D. Known answers produce known numbers; the script checks the database rows, the teacher
// analytics (as deltas against a baseline taken first, so real activity on the shared database cannot break it),
// pre/post matching, date filters, CSV exports, privacy (IDOR, roles, answer keys, sessions) and idempotency.
// Optional: E2E_UI_APP=http://127.0.0.1:4173 also checks the rendered dashboard with Playwright.
// Every record it creates is removed at the end; table counts are compared with the start.
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const { pool } = await import("../src/db/pool.js");
const { hashPassword } = await import("../src/services/passwords.js");
const { newId } = await import("../src/utils/ids.js");

const base = process.env.HISTORYBOT_TEST_API || "http://127.0.0.1:3100/api/v1";
if (!/127\.0\.0\.1:3100|localhost:3100/.test(base) && process.env.E2E_ALLOW_NON_TEST !== "1") {
  console.log("FAIL refusing to run: HISTORYBOT_TEST_API must be the isolated test backend on :3100");
  process.exit(2);
}
let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  if (ok) pass += 1;
  else fail += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail !== "" ? ` — ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : ""}`);
};
const near = (a, b, eps = 0.01) => a != null && b != null && Math.abs(Number(a) - Number(b)) <= eps;

const COUNT_TABLES = [
  "users", "auth_sessions", "anonymous_sessions", "conversations", "messages", "analytics_events", "econtent_documents",
  "quiz_questions", "quizzes", "quiz_items", "quiz_attempts", "quiz_answers", "module_progress",
  "research_instruments", "research_items", "research_responses", "research_response_items", "verified_images", "ai_usage",
];
async function counts() {
  const out = {};
  for (const t of COUNT_TABLES) {
    const [[r]] = await pool.query(`SELECT COUNT(*) AS n FROM ${t}`);
    out[t] = Number(r.n);
  }
  return out;
}

async function api(method, pathname, { token, body, raw } = {}) {
  const res = await fetch(`${base}${pathname}`, {
    method,
    headers: {
      Accept: raw ? "*/*" : "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
  });
  if (raw) return { status: res.status, text: await res.text(), headers: res.headers };
  return { status: res.status, data: await res.json().catch(() => ({})) };
}

const stamp = Date.now();
const tag = `E2E${stamp}`;
const password = `E2e-${stamp}-Pw`;
const created = { users: [], quizzes: [], instruments: [] };
const IST = 330 * 60000;
const istDay = (offset = 0) => new Date(Date.now() + IST + offset * 86400000).toISOString().slice(0, 10);
const today = istDay(0);
const yesterday = istDay(-1);
const twoDaysAgo = istDay(-2);
const dayStart = (d) => new Date(`${d}T00:00:00+05:30`);
const ref = (id) => `S-${String(id).replace(/-/g, "").slice(0, 8)}`;

async function student(label, name = `${tag} ${label}`) {
  const email = `e2e.${label.toLowerCase()}.${stamp}@example.com`;
  const r = await api("POST", "/auth/register", { body: { display_name: name, email, password } });
  if (r.data.user?.id) created.users.push(r.data.user.id);
  return { id: r.data.user?.id, token: r.data.token, session: r.data.session_id, email, status: r.status, label };
}

async function teacher() {
  const id = newId();
  const email = `e2e.teacher.${stamp}@example.com`;
  await pool.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'admin')", [id, email, `${tag} Teacher`, await hashPassword(password)]);
  created.users.push(id);
  const r = await api("POST", "/auth/login", { body: { email, password } });
  return { id, token: r.data.token };
}

// Correct (or deliberately wrong) responses built from the teacher's view of the answer keys.
function respond(q, correct) {
  const a = q.answer;
  switch (q.qtype) {
    case "mcq":
      return correct ? a : q.options.find((o) => o.id !== a).id;
    case "true_false":
      return correct ? a : !a;
    case "fill_blank":
      return correct ? (Array.isArray(a) ? a[0] : a) : "zzzz";
    case "order":
      return correct ? a : [...a].reverse();
    case "match": {
      if (correct) return a;
      const keys = Object.keys(a);
      const vals = keys.map((k) => a[k]);
      return Object.fromEntries(keys.map((k, i) => [k, vals[(i + 1) % vals.length]]));
    }
    default:
      return null;
  }
}

async function overview(T, from, to) {
  return (await api("GET", `/teacher/analytics/overview?from=${from}&to=${to}`, { token: T.token })).data;
}

async function eventCount(type, userId, extra = "") {
  const [[r]] = await pool.query(`SELECT COUNT(*) AS n FROM analytics_events WHERE event_type = ? AND user_id = ? ${extra}`, [type, userId]);
  return Number(r.n);
}

async function main() {
  const T = await teacher();
  // Baselines before any test activity (deltas protect against real activity on the shared database).
  const base0 = await overview(T, today, today);
  const baseWide = await overview(T, istDay(-3), today);
  const baseTopics = (await api("GET", `/teacher/analytics/topics?from=${today}&to=${today}`, { token: T.token })).data.topics;
  const topicAnswered = (list) => list.reduce((s, t) => s + t.answered, 0);

  const A = await student("A");
  const B = await student("B", `=HYPERLINK("http://x.example","B") ${tag}`);
  const C = await student("C");
  const D = await student("D");
  check("four students registered", [A, B, C, D].every((s) => s.status === 201));
  check("registration recorded once per student (USER_REGISTERED)", (await eventCount("USER_REGISTERED", A.id)) === 1);
  const login = await api("POST", "/auth/login", { body: { email: A.email, password } });
  check("student sign-in works and is recorded (not attendance)", login.status === 200 && (await eventCount("USER_SIGNED_IN", A.id)) === 1);
  const A2token = login.data.token;

  // ---------- Bank: published questions with keys (teacher view) ----------
  const bank = (await api("GET", "/teacher/questions?status=published&size=100", { token: T.token })).data.questions;
  const pick = ["mcq", "true_false", "mcq", "true_false"].map((t, i) => bank.filter((q) => q.qtype === t)[i >> 1]);
  check("four published questions available for the assessments", pick.every(Boolean) && new Set(pick.map((q) => q.id)).size === 4);
  const qids = pick.map((q) => q.id);
  const byId = new Map(bank.map((q) => [q.id, q]));

  // ---------- Teacher: pre-test and linked post-test ----------
  const mk = async (body) => {
    const r = await api("POST", "/teacher/quizzes", { token: T.token, body });
    if (r.data.quiz?.id) created.quizzes.push(r.data.quiz.id);
    return r;
  };
  const pre = await mk({ title: `${tag} Pre-test`, topic: "E2E", mode: "assessment", assessment_phase: "pre", reveal_answers: "never", max_attempts: 1, question_ids: qids });
  const postUnlinked = await mk({ title: `${tag} Post (unlinked)`, topic: "E2E", mode: "assessment", assessment_phase: "post", question_ids: qids });
  const pubUnlinked = await api("POST", `/teacher/quizzes/${postUnlinked.data.quiz.id}/status`, { token: T.token, body: { status: "published" } });
  check("a post-test cannot be published without a linked pre-test", pubUnlinked.status === 400, pubUnlinked.status);
  const badLink = await mk({ title: `${tag} Post (bad link)`, topic: "E2E", mode: "assessment", assessment_phase: "post", pre_quiz_id: postUnlinked.data.quiz.id, question_ids: qids });
  check("a post-test can only link to a quiz marked pre-test", badLink.status === 400, badLink.status);
  const post = await mk({ title: `${tag} Post-test`, topic: "E2E", mode: "assessment", assessment_phase: "post", pre_quiz_id: pre.data.quiz.id, reveal_answers: "after_submit", max_attempts: 1, question_ids: qids });
  check("teacher creates pre-test and linked post-test", pre.status === 201 && post.status === 201 && post.data.quiz.pre_quiz_id === pre.data.quiz.id);
  const ghost = await mk({ title: `${tag} Post (missing pre)`, topic: "E2E", mode: "assessment", assessment_phase: "post", pre_quiz_id: "00000000-0000-4000-8000-000000000000", question_ids: qids });
  check("linking to a pre-test that does not exist is 400", ghost.status === 400, ghost.status);
  const dupe = await mk({ title: `${tag} Post (duplicate)`, topic: "E2E", mode: "assessment", assessment_phase: "post", pre_quiz_id: pre.data.quiz.id, question_ids: qids });
  check("a pre-test can be linked to only one post-test (409)", dupe.status === 409, dupe.status);
  const postWhilePreDraft = await api("POST", `/teacher/quizzes/${post.data.quiz.id}/status`, { token: T.token, body: { status: "published" } });
  check("a post-test cannot be published while its pre-test is still a draft", postWhilePreDraft.status === 400, postWhilePreDraft.status);
  for (const z of [pre, post]) await api("POST", `/teacher/quizzes/${z.data.quiz.id}/status`, { token: T.token, body: { status: "published" } });
  const postPub = await api("GET", `/teacher/quizzes/${post.data.quiz.id}`, { token: T.token });
  check("after the pre-test is published, the linked post-test publishes", postPub.data.quiz?.status === "published", postPub.data.quiz?.status);
  const practice = await mk({ title: `${tag} Practice`, topic: "E2E", mode: "practice", question_ids: qids.slice(0, 2) });
  const timed = await mk({ title: `${tag} Timed`, topic: "E2E", mode: "practice", time_limit_sec: 60, question_ids: qids.slice(0, 2) });
  for (const z of [practice, timed]) await api("POST", `/teacher/quizzes/${z.data.quiz.id}/status`, { token: T.token, body: { status: "published" } });

  const take = async (S, quizId, pattern, token = S.token) => {
    const st = await api("POST", `/quizzes/${quizId}/attempts`, { token });
    const attemptId = st.data.attempt?.id;
    const responses = {};
    st.data.questions?.forEach((q, i) => {
      if (pattern[i] !== null) responses[q.id] = respond(byId.get(q.id), pattern[i]);
    });
    const sub = await api("POST", `/attempts/${attemptId}/submit`, { token, body: { responses } });
    return { st, sub, attemptId, responses };
  };

  // Answer keys never reach the student before submission (assessment).
  const preA = await take(A, pre.data.quiz.id, [true, true, false, false]);
  const leaked = JSON.stringify(preA.st.data.questions || []);
  check("assessment start payload has no answer keys or explanations", preA.st.status === 201 && !/"answer"|"explanation"/.test(leaked));
  check("pre-test A scored on the server: 2/4 = 50%", preA.sub.status === 200 && preA.sub.data.attempt.percent === 50, preA.sub.data.attempt?.percent);
  check("reveal 'never': result shows no answers", !JSON.stringify(preA.sub.data.questions).includes('"answer"') && preA.sub.data.reveal === false);
  const dup = await api("POST", `/attempts/${preA.attemptId}/submit`, { token: A.token, body: { responses: preA.responses } });
  check("duplicate submit is rejected (409) and nothing is re-scored", dup.status === 409, dup.status);
  const again = await api("POST", `/quizzes/${pre.data.quiz.id}/attempts`, { token: A.token });
  check("attempt limit enforced (1 attempt)", again.status === 409 && again.data.error?.code === "ATTEMPT_LIMIT", again.status);
  const [[preRow]] = await pool.query("SELECT status, end_reason, score_points, max_points, percent, attempt_no FROM quiz_attempts WHERE id = ?", [preA.attemptId]);
  const [[ansRows]] = await pool.query("SELECT COUNT(*) AS n, SUM(is_correct) AS c FROM quiz_answers WHERE attempt_id = ?", [preA.attemptId]);
  check("DB row: attempt submitted, end_reason submitted, 2/4, attempt_no 1", preRow.status === "submitted" && preRow.end_reason === "submitted" && Number(preRow.score_points) === 2 && Number(preRow.max_points) === 4 && preRow.attempt_no === 1);
  check("DB rows: 4 per-question answers, 2 correct", Number(ansRows.n) === 4 && Number(ansRows.c) === 2);
  check("one QUIZ_STARTED and one QUIZ_SUBMITTED event for the attempt", (await eventCount("QUIZ_STARTED", A.id, `AND JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.attempt_id')) = '${preA.attemptId}'`)) === 1 && (await eventCount("QUIZ_SUBMITTED", A.id, `AND JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.attempt_id')) = '${preA.attemptId}'`)) === 1);

  const postA = await take(A, post.data.quiz.id, [true, true, true, true]);
  const preB = await take(B, pre.data.quiz.id, [true, false, false, false]);
  const postB = await take(B, post.data.quiz.id, [true, true, true, true]);
  const preC = await take(C, pre.data.quiz.id, [true, true, true, true]);
  check("known scores: A post 100, B pre 25, B post 100, C pre 100", postA.sub.data.attempt?.percent === 100 && preB.sub.data.attempt?.percent === 25 && postB.sub.data.attempt?.percent === 100 && preC.sub.data.attempt?.percent === 100);
  check("post-test reveal after submit shows answers and explanations", postA.sub.data.reveal === true && postA.sub.data.questions.every((q) => q.answer !== undefined));

  // ---------- Invalid input ----------
  const badId = await api("GET", "/attempts/not-a-uuid", { token: A.token });
  check("invalid attempt id is 400", badId.status === 400, badId.status);
  const prA = await api("POST", `/quizzes/${practice.data.quiz.id}/attempts`, { token: A.token });
  const badBody = await api("POST", `/attempts/${prA.data.attempt.id}/submit`, { token: A.token, body: { responses: "nope" } });
  check("malformed submit body is 400 and the attempt stays open", badBody.status === 400 && (await pool.query("SELECT status FROM quiz_attempts WHERE id = ?", [prA.data.attempt.id]))[0][0].status === "in_progress");
  const resumed = await api("POST", `/quizzes/${practice.data.quiz.id}/attempts`, { token: A.token });
  check("refresh/restart resumes the same attempt (no second QUIZ_STARTED)", resumed.data.resumed === true && resumed.data.attempt.id === prA.data.attempt.id && (await eventCount("QUIZ_STARTED", A.id, `AND JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.attempt_id')) = '${prA.data.attempt.id}'`)) === 1);
  const unknownQ = await api("POST", `/attempts/${prA.data.attempt.id}/submit`, { token: A.token, body: { responses: { [crypto.randomUUID()]: "a" } } });
  check("responses for unknown question ids are ignored; empty attempt scores 0", unknownQ.status === 200 && unknownQ.data.attempt.percent === 0);

  // ---------- IDOR and roles ----------
  const bRead = await api("GET", `/attempts/${preA.attemptId}`, { token: B.token });
  const bSave = await api("POST", `/attempts/${preA.attemptId}/autosave`, { token: B.token, body: { responses: {} } });
  check("student B cannot read or autosave A's attempt (404)", bRead.status === 404 && bSave.status === 404, `${bRead.status}/${bSave.status}`);
  for (const [m, p] of [["GET", "/teacher/analytics/overview"], ["GET", "/teacher/analytics/achievement"], ["GET", `/teacher/analytics/students/${A.id}`], ["GET", "/teacher/instruments"], ["POST", "/teacher/instruments"], ["GET", "/teacher/reports/prepost.csv"], ["GET", "/teacher/questions"]]) {
    const r = await api(m, p, { token: B.token, body: m === "POST" ? {} : undefined });
    check(`student ${m} ${p} is 403`, r.status === 403, r.status);
  }
  for (const [m, p] of [["GET", "/questionnaires"], ["GET", "/teacher/instruments"], ["POST", `/econtent/${crypto.randomUUID()}/complete`]]) {
    const r = await api(m, p, { body: m === "POST" ? {} : undefined });
    check(`logged-out ${m} ${p} is 401`, r.status === 401, r.status);
  }

  // ---------- Modules: opened != completed; explicit and checkpoint completion ----------
  const [[sample]] = await pool.query("SELECT body_json, source_pages FROM econtent_documents WHERE language = 'en' ORDER BY created_at DESC LIMIT 1");
  const body = sample?.body_json ? (typeof sample.body_json === "string" ? sample.body_json : JSON.stringify(sample.body_json)) : JSON.stringify({ title: "Akbar", content: { introduction: "Akbar." }, images: [] });
  const sources = sample?.source_pages ? (typeof sample.source_pages === "string" ? sample.source_pages : JSON.stringify(sample.source_pages)) : "[]";
  const m1 = newId();
  const m2 = newId();
  for (const id of [m1, m2]) {
    await pool.query("INSERT INTO econtent_documents (id, session_id, topic, language, body_json, source_pages) VALUES (?, ?, ?, 'en', ?, ?)", [id, A.session, "Akbar", body, sources]);
  }
  const open1 = await api("GET", `/econtent/${m1}?session_id=${A.session}`, { token: A.token });
  await api("GET", `/econtent/${m1}?session_id=${A.session}`, { token: A.token });
  const [[mp1]] = await pool.query("SELECT open_count, completed_at FROM module_progress WHERE user_id = ? AND econtent_id = ?", [A.id, m1]);
  check("opening a module twice: open_count 2, one MODULE_OPENED event, NOT completed", open1.status === 200 && mp1.open_count === 2 && mp1.completed_at === null && (await eventCount("MODULE_OPENED", A.id)) === 1 && open1.data.progress?.completed === false);
  const pdf = await api("POST", `/econtent/${m1}/pdf`, { token: A.token, body: { session_id: A.session }, raw: true });
  const disp = pdf.headers.get("content-disposition") || "";
  check("PDF downloads (does not complete the module); safe filename", pdf.status === 200 && /filename="historybot-[A-Za-z0-9-]+\.pdf"/.test(disp) && (await pool.query("SELECT completed_at, pdf_downloads FROM module_progress WHERE user_id = ? AND econtent_id = ?", [A.id, m1]))[0][0].pdf_downloads === 1, `${pdf.status} ${disp}`);
  const bOpen = await api("GET", `/econtent/${m1}?session_id=${B.session}`, { token: B.token });
  const bDone = await api("POST", `/econtent/${m1}/complete`, { token: B.token, body: { session_id: B.session } });
  const bUseA = await api("POST", `/econtent/${m1}/complete`, { token: B.token, body: { session_id: A.session } });
  check("B cannot open or complete A's module (403/404)", [bOpen.status, bDone.status, bUseA.status].every((s) => s === 403 || s === 404), `${bOpen.status}/${bDone.status}/${bUseA.status}`);
  const c1 = await api("POST", `/econtent/${m1}/complete`, { token: A.token, body: { session_id: A.session } });
  const c2 = await api("POST", `/econtent/${m1}/complete`, { token: A.token, body: { session_id: A.session } });
  check("explicit Mark complete is idempotent (one MODULE_COMPLETED)", c1.status === 200 && c2.status === 200 && c1.data.progress.completed && (await eventCount("MODULE_COMPLETED", A.id)) === 1);
  const cpBad = await api("POST", "/activities/checkpoint", { token: B.token, body: { topic: "Akbar", econtent_id: m2, session_id: B.session } });
  check("B cannot link a checkpoint to A's module", cpBad.status === 403 || cpBad.status === 404, cpBad.status);
  const cp = await api("POST", "/activities/checkpoint", { token: A.token, body: { topic: "Akbar", econtent_id: m2, session_id: A.session } });
  const cpStart = await api("POST", `/quizzes/${cp.data.quiz_id}/attempts`, { token: A.token });
  const cpResp = {};
  for (const q of cpStart.data.questions || []) cpResp[q.id] = respond(byId.get(q.id) || { qtype: "x" }, true);
  const cpSub = await api("POST", `/attempts/${cpStart.data.attempt?.id}/submit`, { token: A.token, body: { responses: cpResp } });
  const cpCount = (cpStart.data.questions || []).length;
  const [[mp2]] = await pool.query("SELECT completed_at, completion_method FROM module_progress WHERE user_id = ? AND econtent_id = ?", [A.id, m2]);
  check("submitting the module checkpoint completes the module (method checkpoint)", cp.status === 201 && cpSub.status === 200 && mp2?.completion_method === "checkpoint" && mp2.completed_at !== null, mp2);
  const [[mp2o]] = await pool.query("SELECT first_opened_at FROM module_progress WHERE user_id = ? AND econtent_id = ?", [A.id, m2]);
  const opensM2 = async () => (await pool.query("SELECT COUNT(*) AS n FROM analytics_events WHERE user_id = ? AND event_type = 'MODULE_OPENED' AND JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.econtent_id')) = ?", [A.id, m2]))[0][0].n;
  const opensBefore = Number(await opensM2());
  await api("GET", `/econtent/${m2}?session_id=${A.session}`, { token: A.token });
  const opensAfter = Number(await opensM2());
  check("checkpoint-only completion records the module as opened once; a later open does not double count", mp2o?.first_opened_at && opensBefore === 1 && opensAfter === 1, { opensBefore, opensAfter });
  check("checkpoint scored 100% with known keys", cpSub.data.attempt?.percent === 100, cpSub.data.attempt?.percent);

  // ---------- Timed out and abandoned (D) ----------
  const tStart = await api("POST", `/quizzes/${timed.data.quiz.id}/attempts`, { token: D.token });
  const [tq1] = tStart.data.questions;
  await api("POST", `/attempts/${tStart.data.attempt.id}/autosave`, { token: D.token, body: { responses: { [tq1.id]: respond(byId.get(tq1.id), true) } } });
  await pool.query("UPDATE quiz_attempts SET deadline_at = UTC_TIMESTAMP(3) - INTERVAL 5 MINUTE WHERE id = ?", [tStart.data.attempt.id]);
  const late = await api("POST", `/attempts/${tStart.data.attempt.id}/submit`, { token: D.token, body: { responses: {} } });
  const [[tRow]] = await pool.query("SELECT end_reason, percent FROM quiz_attempts WHERE id = ?", [tStart.data.attempt.id]);
  check("timed-out attempt is scored from the last autosave (1/2 = 50%), end_reason timed_out", late.status === 200 && tRow.end_reason === "timed_out" && Number(tRow.percent) === 50, tRow);
  check("exactly one terminal event (QUIZ_TIMED_OUT, no QUIZ_SUBMITTED)", (await eventCount("QUIZ_TIMED_OUT", D.id)) === 1 && (await eventCount("QUIZ_SUBMITTED", D.id)) === 0);
  const ab = await api("POST", `/quizzes/${practice.data.quiz.id}/attempts`, { token: D.token });
  await pool.query("UPDATE quiz_attempts SET started_at = UTC_TIMESTAMP(3) - INTERVAL 2 DAY WHERE id = ?", [ab.data.attempt.id]);

  // ---------- Date filter fixture: move C's pre-test to yesterday ----------
  await pool.query("UPDATE quiz_attempts SET submitted_at = submitted_at - INTERVAL 1 DAY, started_at = started_at - INTERVAL 1 DAY WHERE id = ?", [preC.attemptId]);

  // ---------- Expired session and failed submit ----------
  const exp = await api("POST", `/quizzes/${practice.data.quiz.id}/attempts`, { token: A2token });
  const expHash = crypto.createHash("sha256").update(A2token).digest("hex");
  await pool.query("UPDATE auth_sessions SET expires_at = UTC_TIMESTAMP(3) - INTERVAL 1 MINUTE WHERE token_hash = ?", [expHash]);
  const expMe = await api("GET", "/auth/me", { token: A2token });
  const expSub = await api("POST", `/attempts/${exp.data.attempt.id}/submit`, { token: A2token, body: { responses: {} } });
  const [[expRow]] = await pool.query("SELECT status FROM quiz_attempts WHERE id = ?", [exp.data.attempt.id]);
  check("expired session is rejected (401) and the failed submit changes nothing", expMe.status === 401 && expSub.status === 401 && expRow.status === "in_progress", `${expMe.status}/${expSub.status}/${expRow.status}`);
  check("an expired token row is removed", (await pool.query("SELECT COUNT(*) AS n FROM auth_sessions WHERE token_hash = ?", [expHash]))[0][0].n === 0);
  // A still has the registration token: the abandoned-by-expiry attempt is resumed and submitted (counts as a finished practice attempt).
  const expDone = await api("POST", `/attempts/${exp.data.attempt.id}/submit`, { token: A.token, body: { responses: {} } });
  check("after signing in again the open attempt can be submitted", expDone.status === 200);

  // ---------- Expected numbers ----------
  // Today (IST): A pre 50, A post 100, B pre 25, B post 100 (assessment, first attempts); C pre moved to yesterday.
  // Practice/personal today: A practice 0 (unknown ids), A checkpoint 100, A practice-after-expiry 0, D timed 50.
  const ov = await overview(T, today, today);
  const d = (k) => (ov.cards[k] ?? 0) - (base0.cards[k] ?? 0);
  check("overview: registered_in_range +4", d("registered_in_range") === 4, d("registered_in_range"));
  check("overview: student sign-ins +1 (registrations are not sign-ins)", d("sign_ins") === 1, d("sign_ins"));
  // m1 was opened; m2 was completed through its checkpoint without being opened, which now also counts as opened (once).
  check("overview: modules completed +2, opened +2, generated +2, PDF downloads +1", d("modules_completed") === 2 && d("modules_opened") === 2 && d("modules_generated") === 2 && d("pdf_downloads") === 1, { c: d("modules_completed"), o: d("modules_opened"), g: d("modules_generated"), p: d("pdf_downloads") });
  check("overview: assessments submitted +4 (C's moved to yesterday)", d("assessments_submitted") === 4, d("assessments_submitted"));
  check("overview: finished attempts +8, timed out +1", d("quiz_attempts") === 8 && d("timed_out") === 1, { a: d("quiz_attempts"), t: d("timed_out") });
  check("overview: active students +3 (A, B, D today; C only yesterday)", d("active_students") === 3, d("active_students"));
  // Average achievement = mean of first assessment attempts; compare with an independent query for the same range.
  const [[ach]] = await pool.query(
    `SELECT AVG(a.percent) AS m, COUNT(*) AS n FROM quiz_attempts a JOIN quizzes z ON z.id = a.quiz_id JOIN users u ON u.id = a.user_id AND u.role = 'student'
     WHERE a.status = 'submitted' AND z.mode = 'assessment' AND z.owner_user_id IS NULL AND a.submitted_at >= ? AND a.submitted_at < ?
       AND a.attempt_no = (SELECT MIN(b.attempt_no) FROM quiz_attempts b WHERE b.quiz_id = a.quiz_id AND b.user_id = a.user_id AND b.status = 'submitted')`,
    [dayStart(today), new Date(dayStart(today).getTime() + 86400000)]
  );
  check("overview: average achievement equals the independent DB query", near(ov.cards.mean_percent, Math.round(Number(ach.m) * 10) / 10, 0.05) && ov.cards.mean_percent_n === Number(ach.n), `${ov.cards.mean_percent} vs ${ach.m} (n ${ach.n})`);
  check("overview has 'data as of' and definitions for every card", Boolean(ov.data_as_of) && Object.keys(ov.cards).filter((k) => !k.endsWith("_n") && !k.endsWith("_timed_out")).every((k) => ov.definitions[k]));
  // Activity-over-time API: every IST day in the range, and today's bucket agrees with the overview cards.
  const ts1 = (await api("GET", `/teacher/analytics/timeseries?from=${today}&to=${today}&bucket=day`, { token: T.token })).data;
  const t0 = ts1.series?.[0] || {};
  check("timeseries one-day range: one bucket (today, IST)", ts1.series?.length === 1 && t0.bucket === today, ts1.series?.map((p) => p.bucket));
  check(
    "timeseries today agrees with overview (chat, finished attempts, modules completed, PDFs, sign-ins)",
    t0.chat_questions === ov.cards.chat_questions && t0.quiz_attempts === ov.cards.quiz_attempts && t0.modules_completed === ov.cards.modules_completed && t0.pdf_downloads === ov.cards.pdf_downloads && t0.sign_ins === ov.cards.sign_ins,
    { ts: t0, cards: ov.cards }
  );
  const ts3 = (await api("GET", `/teacher/analytics/timeseries?from=${twoDaysAgo}&to=${today}&bucket=day`, { token: T.token })).data;
  check("timeseries 3-day range lists all 3 IST days including quiet ones", ts3.series?.length === 3 && ts3.series[0].bucket === twoDaysAgo, ts3.series?.map((p) => p.bucket));
  const ovY = await overview(T, yesterday, yesterday);
  const baseY = baseWide; // only used for shape
  check("date filter: yesterday shows C's assessment, today does not", ovY.cards.assessments_submitted >= 1 && Boolean(baseY));
  const ovWide = await overview(T, istDay(-3), today);
  check("overview: abandoned +1 in a range covering 2 days ago (untimed, >24 h, never submitted)", ovWide.cards.abandoned - baseWide.cards.abandoned === 1, ovWide.cards.abandoned - baseWide.cards.abandoned);

  // Students table (exact: our students only, found by the unique tag).
  const st = await api("GET", `/teacher/analytics/students?from=${today}&to=${today}&search=${tag}&size=50&sort=name`, { token: T.token });
  const row = (S) => st.data.students.find((s) => s.id === S.id);
  check("students table: A has 5 attempts today, mean 50, 2 modules done", row(A)?.quiz_attempts === 5 && near(row(A)?.mean_percent, 50, 0.05) && row(A)?.modules_completed === 2, row(A));
  check("students table: B 2 attempts mean 62.5; C none today; D 1 attempt 50", row(B)?.quiz_attempts === 2 && near(row(B)?.mean_percent, 62.5, 0.05) && row(C)?.quiz_attempts === 0 && row(C)?.mean_percent === null && row(D)?.quiz_attempts === 1 && near(row(D)?.mean_percent, 50, 0.05), { B: row(B), C: row(C), D: row(D) });
  check("students table exposes no email, password or chat text", !/email|password|token_hash|content/i.test(JSON.stringify(st.data.students)));
  const stY = await api("GET", `/teacher/analytics/students?from=${yesterday}&to=${yesterday}&search=${tag}&size=50`, { token: T.token });
  check("date filter: C has 1 attempt (100%) yesterday", stY.data.students.find((s) => s.id === C.id)?.quiz_attempts === 1);

  // Topics: answered count delta for today = 4 assessments x 4 + practice/personal answers (2 + cp + 2) + D 2.
  const topicsNow = (await api("GET", `/teacher/analytics/topics?from=${today}&to=${today}`, { token: T.token })).data.topics;
  const expectTopic = 4 * 4 + 2 + cpCount + 2 + 2;
  check("topics: answers today increased by the expected count", topicAnswered(topicsNow) - topicAnswered(baseTopics) === expectTopic, `${topicAnswered(topicsNow) - topicAnswered(baseTopics)} vs ${expectTopic}`);

  // Pre/post: matched A (50->100) and B (25->100); C pre only.
  const achRes = await api("GET", `/teacher/analytics/achievement?from=${today}&to=${today}`, { token: T.token });
  const pair = achRes.data.pre_post.pairs.find((p) => p.post_quiz.id === post.data.quiz.id);
  check("pre/post: paired n 2, mean pre 37.5, mean post 100, mean gain 62.5", pair?.paired_n === 2 && near(pair.mean_pre, 37.5) && near(pair.mean_post, 100) && near(pair.mean_gain, 62.5), pair && { n: pair.paired_n, pre: pair.mean_pre, post: pair.mean_post, gain: pair.mean_gain });
  check("pre/post: paired t = 5, df 1, p ≈ 0.126 (descriptive)", pair && near(pair.paired_t.t, 5, 0.001) && pair.paired_t.df === 1 && near(pair.paired_t.p, 0.1257, 0.001), pair?.paired_t);
  check("pre/post: C listed as pre-only (unmatched), nobody post-only", pair && pair.unmatched.pre_only.includes(ref(C.id)) && pair.unmatched.post_only.length === 0);
  const achY = await api("GET", `/teacher/analytics/achievement?from=${yesterday}&to=${yesterday}`, { token: T.token });
  check("date filter: no post-tests yesterday, so paired n 0", achY.data.pre_post.pairs.find((p) => p.post_quiz.id === post.data.quiz.id)?.paired_n === 0);
  const empty = await api("GET", "/teacher/analytics/achievement?from=2020-01-01&to=2020-01-02", { token: T.token });
  check("empty range: achievement n 0 with nulls (no fake numbers)", empty.status === 200 && empty.data.overall.n === 0 && empty.data.overall.mean === null);

  // ---------- CSV ----------
  const csvAtt = await api("GET", `/teacher/reports/attempts.csv?from=${today}&to=${today}&include_names=1`, { token: T.token, raw: true });
  const lines = csvAtt.text.replace(/^\ufeff/, "").trim().split(/\r\n/);
  const mine = (S) => lines.filter((l) => l.startsWith(`${ref(S.id)},`));
  check("CSV attempts (today) has A 5, B 2, C 0, D 1 rows", mine(A).length === 5 && mine(B).length === 2 && mine(C).length === 0 && mine(D).length === 1, [mine(A).length, mine(B).length, mine(C).length, mine(D).length]);
  check("CSV formula guard: B's '=HYPERLINK' name is neutralised", mine(B).every((l) => l.includes(`"'=HYPERLINK(`) || l.includes(`'=HYPERLINK(`)) && !mine(B).some((l) => l.includes(`,=HYPERLINK`)));
  check("CSV has IST times and no emails/passwords/tokens", lines[0].includes("submitted_at_ist") && !/@example\.com|password|token/i.test(csvAtt.text));
  const csvY = await api("GET", `/teacher/reports/attempts.csv?from=${yesterday}&to=${yesterday}`, { token: T.token, raw: true });
  check("CSV date filter: C's attempt appears yesterday only", csvY.text.includes(`${ref(C.id)},`) && !csvAtt.text.includes(`${ref(C.id)},`));
  const csvPP = await api("GET", `/teacher/reports/prepost.csv?from=${today}&to=${today}`, { token: T.token, raw: true });
  const ppRows = csvPP.text.split(/\r\n/).filter((l) => l.includes(`${tag} Post-test`));
  check("CSV pre/post: A and B matched with gains 50 and 75; C pre_only", ppRows.some((l) => l.includes(`${ref(A.id)},matched,50,100,50`)) && ppRows.some((l) => l.includes(`${ref(B.id)},matched,25,100,75`)) && ppRows.some((l) => l.includes(`${ref(C.id)},pre_only`)), ppRows);

  // ---------- Questionnaires ----------
  const [shells] = await pool.query("SELECT id FROM research_instruments WHERE seed_key IN ('shell_digital_attitude', 'shell_social_engagement')");
  check("two instrument shells exist", shells.length === 2);
  const shellPub = await api("POST", `/teacher/instruments/${shells[0].id}/status`, { token: T.token, body: { status: "published" } });
  check("a placeholder shell cannot be published", shellPub.status === 400 && /REQUIRES RESEARCHER APPROVAL/.test(shellPub.data.error?.message || ""), shellPub.data.error?.message);
  const studentShell = await api("GET", `/questionnaires/${shells[0].id}`, { token: A.token });
  check("students cannot open a draft questionnaire (404)", studentShell.status === 404);
  const items = [
    { text: `${tag} item one`, subscale: "X", reverse_scored: false },
    { text: `${tag} item two`, subscale: "X", reverse_scored: true },
    { text: `${tag} item three`, subscale: "Y", reverse_scored: false },
    { text: `${tag} item four`, subscale: "Y", reverse_scored: false },
  ];
  const inst = await api("POST", "/teacher/instruments", { token: T.token, body: { title: `${tag} Questionnaire`, construct: "Test construct", items } });
  created.instruments.push(inst.data.instrument?.id);
  const iid = inst.data.instrument.id;
  const noNote = await api("POST", `/teacher/instruments/${iid}/status`, { token: T.token, body: { status: "published" } });
  check("publishing needs an approval note", noNote.status === 400, noNote.status);
  await api("POST", `/teacher/instruments/${iid}`, { token: T.token, body: { title: `${tag} Questionnaire`, construct: "Test construct", approval_note: "E2E test items, not for research use." } });
  const pub = await api("POST", `/teacher/instruments/${iid}/status`, { token: T.token, body: { status: "published" } });
  check("teacher publishes an approved questionnaire", pub.status === 200 && pub.data.instrument.status === "published");
  const qA = await api("GET", `/questionnaires/${iid}`, { token: A.token });
  const ids = qA.data.items.map((i) => i.id);
  check("student view hides subscales and reverse flags", qA.status === 200 && !/subscale|reverse/.test(JSON.stringify(qA.data.items)));
  const bad = await api("POST", `/questionnaires/${iid}/responses`, { token: A.token, body: { answers: { [ids[0]]: 7 } } });
  check("out-of-scale answer is 400", bad.status === 400);
  const sA = await api("POST", `/questionnaires/${iid}/responses`, { token: A.token, body: { answers: { [ids[0]]: 5, [ids[1]]: 1, [ids[2]]: 4, [ids[3]]: null }, submit: true } });
  const sB = await api("POST", `/questionnaires/${iid}/responses`, { token: B.token, body: { answers: { [ids[0]]: 3, [ids[1]]: 3, [ids[2]]: null, [ids[3]]: null }, submit: true } });
  const sDup = await api("POST", `/questionnaires/${iid}/responses`, { token: A.token, body: { answers: { [ids[0]]: 1 }, submit: true } });
  check("responses submitted; duplicate submit is 409", sA.status === 200 && sB.status === 200 && sDup.status === 409, `${sA.status}/${sB.status}/${sDup.status}`);
  const [[nulls]] = await pool.query("SELECT COUNT(*) AS n FROM research_response_items ri JOIN research_responses r ON r.id = ri.response_id WHERE r.instrument_id = ? AND ri.value IS NULL", [iid]);
  check("missing answers stored as NULL (not zero): 3", Number(nulls.n) === 3);
  const lockEdit = await api("POST", `/teacher/instruments/${iid}`, { token: T.token, body: { title: "x x x", construct: "y y", items } });
  check("items cannot change after publishing/responses", lockEdit.status === 409);
  const res = await api("GET", `/teacher/instruments/${iid}/results?from=${today}&to=${today}`, { token: T.token });
  const X = res.data.subscales?.find((s) => s.subscale === "X");
  const Y = res.data.subscales?.find((s) => s.subscale === "Y");
  check("results: 2 submitted; X n 2 mean 4 (reverse-scored); Y n 1 mean 4, 1 insufficient", res.data.submitted === 2 && X?.n === 2 && near(X.mean, 4) && Y?.n === 1 && near(Y.mean, 4) && Y.insufficient === 1, { X, Y });
  check("results: item 4 missing 2 (not counted as zero)", res.data.items.find((i) => i.position === 4)?.missing === 2);
  const qcsv = await api("GET", `/teacher/reports/questionnaires.csv?from=${today}&to=${today}&instrument_id=${iid}`, { token: T.token, raw: true });
  const qlines = qcsv.text.replace(/^\ufeff/, "").trim().split(/\r\n/);
  check("questionnaire CSV: 2 rows, reverse item marked _R, blanks for missing", qlines.length === 3 && qlines[0].includes("item_2_R") && qlines.some((l) => l.startsWith(`${tag} Questionnaire,${ref(B.id)}`) && l.endsWith(",3,3,,")), qlines);
  check("QUESTIONNAIRE_SUBMITTED recorded once for A", (await eventCount("QUESTIONNAIRE_SUBMITTED", A.id)) === 1);

  // ---------- Rendered dashboard (optional) ----------
  if (process.env.E2E_UI_APP) await uiCheck(T, { pair, ov });
}

async function uiCheck(T, expected) {
  const { chromium } = await import(process.env.PLAYWRIGHT_PATH ? pathToFileURL(process.env.PLAYWRIGHT_PATH).href : "playwright");
  const browser = await chromium.launch();
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await ctx.addInitScript((t) => localStorage.setItem("historybot_auth_token", t), T.token);
    const page = await ctx.newPage();
    await page.goto(`${process.env.E2E_UI_APP}/admin?tab=overview`, { waitUntil: "networkidle" });
    await page.getByTestId("headline-cards").waitFor();
    const values = await page.getByTestId("headline-cards").getByTestId("stat-value").allInnerTexts();
    const ov = (await api("GET", `/teacher/analytics/overview`, { token: T.token })).data;
    const fmt = (v, pct) => (v == null ? "—" : pct ? `${v}%` : String(v));
    const want = [
      fmt(ov.cards.registered_in_range), fmt(ov.cards.active_students), fmt(ov.cards.modules_completed),
      fmt(ov.cards.assessments_submitted), fmt(ov.cards.mean_percent, true),
    ];
    check("rendered overview headline cards equal the API values (default 30-day range)", JSON.stringify(values) === JSON.stringify(want), { values, want });
    check("rendered overview shows 'Data as of'", (await page.getByTestId("data-as-of").innerText()).startsWith("Data as of"));
    await page.goto(`${process.env.E2E_UI_APP}/admin?tab=achievement`, { waitUntil: "networkidle" });
    const card = page.getByTestId("prepost-pair").filter({ hasText: `${tag} Post-test` });
    await card.waitFor();
    const n = await card.getByTestId("paired-n").innerText();
    const gain = await card.getByTestId("mean-gain").innerText();
    check("rendered pre/post pair shows paired n 2 and mean gain 62.5", n === "2" && gain === "62.5", { n, gain });
  } finally {
    await browser.close();
  }
}

async function cleanup(before) {
  const users = created.users.filter(Boolean);
  const quizIds = created.quizzes.filter(Boolean);
  if (users.length) {
    // Personal quizzes, attempts, answers, events, module progress and questionnaire responses cascade with users;
    // fixture modules cascade with the students' sessions.
    await pool.query("DELETE FROM quizzes WHERE owner_user_id IN (?)", [users]);
  }
  if (quizIds.length) {
    await pool.query("DELETE FROM quiz_attempts WHERE quiz_id IN (?)", [quizIds]);
    await pool.query("UPDATE quizzes SET pre_quiz_id = NULL WHERE id IN (?)", [quizIds]);
    await pool.query("DELETE FROM quizzes WHERE id IN (?)", [quizIds]);
  }
  const inst = created.instruments.filter(Boolean);
  if (inst.length) await pool.query("DELETE FROM research_instruments WHERE id IN (?)", [inst]);
  if (users.length) {
    await pool.query("DELETE FROM auth_sessions WHERE user_id IN (?)", [users]);
    await pool.query("DELETE FROM anonymous_sessions WHERE user_id IN (?)", [users]);
    await pool.query("DELETE FROM users WHERE id IN (?)", [users]);
  }
  if (before) {
    const after = await counts();
    const diff = COUNT_TABLES.filter((t) => after[t] !== before[t]).map((t) => `${t}:${before[t]}->${after[t]}`);
    check("record counts unchanged after cleanup", diff.length === 0, diff.join(" ") || "all equal");
  }
}

let before = null;
try {
  before = await counts();
  await main();
} catch (err) {
  fail += 1;
  console.log(`FAIL unexpected error — ${err.stack || err}`);
} finally {
  try {
    await cleanup(before);
    console.log("CLEANUP_OK");
  } catch (err) {
    console.log(`FAIL cleanup — ${err.message}`);
    fail += 1;
  }
  await pool.end();
  console.log(`e2e_research_flow ${pass}/${pass + fail} PASS`);
  process.exit(fail ? 1 : 0);
}

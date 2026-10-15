// Integration tests for quizzes, activities, teacher tools, analytics and CSV exports.
// Runs against a test backend (HISTORYBOT_TEST_API, default http://127.0.0.1:3100/api/v1). No AI calls.
// Creates its own students/teachers/quizzes and removes all of them at the end.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const { pool } = await import("../src/db/pool.js");
const { hashPassword } = await import("../src/services/passwords.js");
const { newId } = await import("../src/utils/ids.js");

const base = process.env.HISTORYBOT_TEST_API || "http://127.0.0.1:3100/api/v1";
let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  if (ok) pass += 1;
  else fail += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail !== "" ? ` — ${detail}` : ""}`);
};
const created = { users: [], quizzes: [], questions: [] };
const COUNT_TABLES = ["users", "messages", "conversations", "anonymous_sessions", "analytics_events", "quiz_questions", "quizzes", "quiz_attempts", "verified_images"];

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
      Accept: raw ? "text/csv" : "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (raw) return { status: res.status, text: await res.text(), headers: res.headers };
  return { status: res.status, data: await res.json().catch(() => ({})) };
}

const stamp = Date.now();
const password = `Quiz-${stamp}-Test`;

async function student(name) {
  const r = await api("POST", "/auth/register", { body: { display_name: name, email: `quiz.${name.replace(/\W/g, "")}.${stamp}@example.com`, password } });
  if (r.data.user?.id) created.users.push(r.data.user.id);
  return { id: r.data.user?.id, token: r.data.token, status: r.status };
}

async function teacher(name) {
  const id = newId();
  const email = `quiz.teacher.${name}.${stamp}@example.com`;
  await pool.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'admin')", [id, email, `Test ${name}`, await hashPassword(password)]);
  created.users.push(id);
  const r = await api("POST", "/auth/login", { body: { email, password } });
  return { id, token: r.data.token };
}

const today = new Date(Date.now() + 330 * 60000).toISOString().slice(0, 10);

async function main() {
  const A = await student("Quiz Student A");
  const B = await student("=cmd|' /C calc'!A0");
  const T1 = await teacher("one");
  const T2 = await teacher("two");
  check("students registered", A.status === 201 && B.status === 201);

  // ---- logged-out and role checks ----
  for (const [m, p] of [["GET", "/quizzes"], ["POST", "/activities/revision"], ["GET", "/teacher/quizzes"], ["GET", "/teacher/analytics/overview"], ["GET", "/teacher/reports/attempts.csv"]]) {
    const r = await api(m, p);
    check(`logged-out ${m} ${p} is 401`, r.status === 401, r.status);
  }
  for (const [m, p] of [["GET", "/teacher/questions"], ["GET", "/teacher/quizzes"], ["POST", "/teacher/quizzes"], ["GET", "/teacher/analytics/students"], ["GET", "/teacher/reports/students.csv"]]) {
    const r = await api(m, p, { token: A.token, body: m === "POST" ? {} : undefined });
    check(`student ${m} ${p} is 403`, r.status === 403, r.status);
  }

  // ---- teacher builds a quiz from published bank questions ----
  const bank = await api("GET", "/teacher/questions?status=published&size=100", { token: T1.token });
  check("teacher sees the published question bank with answers", bank.status === 200 && bank.data.questions.length >= 30 && bank.data.questions.every((q) => q.answer !== undefined), bank.data.total);
  const byType = (t) => bank.data.questions.find((q) => q.qtype === t);
  const picks = ["mcq", "true_false", "fill_blank", "order", "match"].map(byType).filter(Boolean);
  check("bank has all five gradable types", picks.length === 5, picks.map((q) => q.qtype).join(","));
  const qids = picks.map((q) => q.id);
  const quizBody = { title: `=HYPERLINK("http://evil.example","x") ${stamp}`, topic: "Test topic", mode: "practice", question_ids: qids, max_attempts: 2 };
  const createdQuiz = await api("POST", "/teacher/quizzes", { token: T1.token, body: quizBody });
  check("teacher creates a draft quiz", createdQuiz.status === 201 && createdQuiz.data.quiz.status === "draft");
  const quizId = createdQuiz.data.quiz?.id;
  created.quizzes.push(quizId);
  const listDraft = await api("GET", "/quizzes", { token: A.token });
  check("draft quiz is not listed for students", !listDraft.data.quizzes.some((q) => q.id === quizId));
  const startDraft = await api("POST", `/quizzes/${quizId}/attempts`, { token: A.token });
  check("student cannot start a draft quiz", startDraft.status === 404, startDraft.status);
  const otherTeacherEdit = await api("POST", `/teacher/quizzes/${quizId}/status`, { token: T2.token, body: { status: "published" } });
  check("another teacher cannot publish my quiz", otherTeacherEdit.status === 403, otherTeacherEdit.status);
  const studentPublish = await api("POST", `/teacher/quizzes/${quizId}/status`, { token: A.token, body: { status: "published" } });
  check("student cannot publish", studentPublish.status === 403);
  const pub = await api("POST", `/teacher/quizzes/${quizId}/status`, { token: T1.token, body: { status: "published" } });
  check("teacher publishes the quiz", pub.status === 200 && pub.data.quiz.status === "published");

  // ---- draft question cannot be published into a quiz unreviewed ----
  const draftQ = await api("POST", "/teacher/questions", { token: T1.token, body: { qtype: "mcq", prompt: "Test draft question?", options: [{ id: "a", text: "x" }, { id: "b", text: "y" }], answer: "a", topic: "Test topic" } });
  check("teacher creates a draft question", draftQ.status === 201 && draftQ.data.question.status === "draft");
  created.questions.push(draftQ.data.question?.id);
  const badQ = await api("POST", "/teacher/questions", { token: T1.token, body: { qtype: "mcq", prompt: "Broken?", options: [{ id: "a", text: "x" }, { id: "b", text: "y" }], answer: "c", topic: "Test topic" } });
  check("invalid answer key is rejected", badQ.status === 400);
  const q2 = await api("POST", "/teacher/quizzes", { token: T1.token, body: { title: `Draft-content quiz ${stamp}`, topic: "Test", question_ids: [draftQ.data.question.id] } });
  created.quizzes.push(q2.data.quiz?.id);
  const pubDraftContent = await api("POST", `/teacher/quizzes/${q2.data.quiz.id}/status`, { token: T1.token, body: { status: "published" } });
  check("quiz with unreviewed draft questions cannot be published", pubDraftContent.status === 400);
  const passages = await api("GET", "/teacher/passages?q=Din-e-Ilahi", { token: T1.token });
  check("teacher searches textbook passages", passages.status === 200 && passages.data.passages.length > 0 && passages.data.passages[0].page > 0);
  const p1582 = passages.data.passages.find((p) => p.sentences.some((s) => /1582/.test(s))) || passages.data.passages[0];
  const sentence = p1582.sentences.find((s) => /1582/.test(s));
  const drafted = await api("POST", "/teacher/questions/draft-from-passage", { token: T1.token, body: { chunk_id: p1582.chunk_id, sentence, qtype: "fill_blank", topic: "Akbar" } });
  check("draft from passage keeps page metadata and stays draft", drafted.status === 201 && drafted.data.question.status === "draft" && drafted.data.question.textbook_page > 0 && drafted.data.question.answer[0] === "1582", JSON.stringify(drafted.data.question?.answer || drafted.data) + " sentence=" + sentence);
  created.questions.push(drafted.data.question?.id);
  const fakeSentence = await api("POST", "/teacher/questions/draft-from-passage", { token: T1.token, body: { chunk_id: passages.data.passages[0].chunk_id, sentence: "Akbar invented the telephone in 1876.", qtype: "true_false", topic: "Akbar" } });
  check("draft from passage rejects text not in the passage", fakeSentence.status === 400);

  // ---- student attempt: answers hidden, scoring server-side ----
  const list = await api("GET", "/quizzes", { token: A.token });
  check("published quiz is listed for students", list.data.quizzes.some((q) => q.id === quizId));
  const start = await api("POST", `/quizzes/${quizId}/attempts`, { token: A.token });
  check("student starts an attempt", start.status === 201 && start.data.questions.length === 5);
  const leak = JSON.stringify(start.data);
  check("no answer key or explanation before submission", !/"answer"|answer_json|explanation/.test(leak));
  const attemptId = start.data.attempt.id;
  const resume = await api("POST", `/quizzes/${quizId}/attempts`, { token: A.token });
  check("starting again resumes the same attempt", resume.data.attempt?.id === attemptId && resume.data.resumed === true);
  const bView = await api("GET", `/attempts/${attemptId}`, { token: B.token });
  check("student B cannot read A's attempt (404)", bView.status === 404);
  const bSubmit = await api("POST", `/attempts/${attemptId}/submit`, { token: B.token, body: { responses: {} } });
  check("student B cannot submit A's attempt", bSubmit.status === 404);
  const tView = await api("GET", `/attempts/${attemptId}`, { token: T1.token });
  check("teacher cannot use the student attempt endpoint for others", tView.status === 404);
  const invalidId = await api("GET", "/attempts/not-a-uuid", { token: A.token });
  check("invalid attempt id is 400", invalidId.status === 400);

  // correct responses built from the bank (teacher view) for all but the fill blank
  const resp = {};
  for (const q of picks) {
    if (q.qtype === "fill_blank") resp[q.id] = "definitely wrong";
    else resp[q.id] = q.answer;
  }
  resp["00000000-0000-4000-8000-000000000000"] = "a";
  const save = await api("POST", `/attempts/${attemptId}/autosave`, { token: A.token, body: { responses: resp } });
  check("autosave works", save.status === 200 && save.data.saved);
  const reopened = await api("GET", `/attempts/${attemptId}`, { token: A.token });
  check("autosaved answers come back after refresh", reopened.data.autosave && Object.keys(reopened.data.autosave).length === 5, JSON.stringify(reopened.data.autosave) + " save=" + JSON.stringify(save.data));
  const forged = { ...resp, score: 100, percent: 100 };
  const submit = await api("POST", `/attempts/${attemptId}/submit`, { token: A.token, body: { responses: forged } });
  check("submit scores on the server (4/5 = 80%)", submit.status === 200 && submit.data.attempt.percent === 80 && submit.data.attempt.score === 4, JSON.stringify(submit.data.questions?.map((q) => [q.qtype, q.response, q.answer, q.points])));
  check("practice feedback shows answers, explanations and pages", submit.data.reveal === true && submit.data.questions.every((q) => "answer" in q && "explanation" in q) && submit.data.questions.some((q) => q.textbook_page));
  check("topics to revise lists the missed topic", submit.data.topics_to_revise.length === 1);
  const dup = await api("POST", `/attempts/${attemptId}/submit`, { token: A.token, body: { responses: resp } });
  check("duplicate submit is rejected (409)", dup.status === 409);
  const [[dbAttempt]] = await pool.query("SELECT percent, score_points, status FROM quiz_attempts WHERE id = ?", [attemptId]);
  const [[dbAnswers]] = await pool.query("SELECT COUNT(*) AS n, SUM(is_correct) AS c FROM quiz_answers WHERE attempt_id = ?", [attemptId]);
  check("attempt persisted in the database", Number(dbAttempt.percent) === 80 && dbAttempt.status === "submitted" && Number(dbAnswers.n) === 5 && Number(dbAnswers.c) === 4);

  // empty submission + attempt limit
  const s2 = await api("POST", `/quizzes/${quizId}/attempts`, { token: A.token });
  const empty = await api("POST", `/attempts/${s2.data.attempt.id}/submit`, { token: A.token, body: { responses: {} } });
  check("empty submission scores 0%", empty.data.attempt?.percent === 0);
  check("first result offered Try again (1 of 2 used)", submit.data.can_retry === true && submit.data.attempts_allowed === 2, JSON.stringify({ c: submit.data.can_retry, a: submit.data.attempts_allowed }));
  check(
    "Try again created a new attempt and kept the old one (attempts 1 and 2 listed)",
    s2.status === 201 && s2.data.attempt.id !== attemptId && s2.data.attempt.attempt_no === 2 && empty.data.previous_attempts?.map((p) => p.attempt_no).join(",") === "1,2" && empty.data.previous_attempts[0].percent === 80,
    JSON.stringify(empty.data.previous_attempts)
  );
  check("after the last allowed attempt Try again is withheld with a reason", empty.data.can_retry === false && /used all attempts/.test(empty.data.retry_blocked_reason || ""), JSON.stringify({ c: empty.data.can_retry, r: empty.data.retry_blocked_reason }));
  const sameOrder = JSON.stringify(start.data.questions.map((q) => q.id)) === JSON.stringify(s2.data.questions.map((q) => q.id));
  const sameIds = [...start.data.questions.map((q) => q.id)].sort().join() === [...s2.data.questions.map((q) => q.id)].sort().join();
  check("practice retry draws the same question pool, each once (order may differ)", sameIds && new Set(s2.data.questions.map((q) => q.id)).size === s2.data.questions.length, `sameOrder=${sameOrder}`);
  const [[layoutRow]] = await pool.query("SELECT question_order_json FROM quiz_attempts WHERE id = ?", [s2.data.attempt.id]);
  const layout = typeof layoutRow.question_order_json === "string" ? JSON.parse(layoutRow.question_order_json) : layoutRow.question_order_json;
  check("practice layout is stored with its seed on the attempt", layout?.v === 2 && typeof layout.seed === "string" && layout.order.length === s2.data.questions.length);
  const s3 = await api("POST", `/quizzes/${quizId}/attempts`, { token: A.token });
  check("attempt limit enforced (max 2)", s3.status === 409 && s3.data.error?.code === "ATTEMPT_LIMIT");
  // Open/close window enforced on the server.
  const past = new Date(Date.now() - 2 * 86400000).toISOString();
  const future = new Date(Date.now() + 2 * 86400000).toISOString();
  for (const [label, win] of [["closed", { available_until: past }], ["not yet open", { available_from: future }]]) {
    const wq = await api("POST", "/teacher/quizzes", { token: T1.token, body: { title: `Window ${label} ${stamp}`, topic: "Test topic", mode: "assessment", max_attempts: 1, question_ids: qids.slice(0, 2), ...win } });
    created.quizzes.push(wq.data.quiz?.id);
    await api("POST", `/teacher/quizzes/${wq.data.quiz?.id}/status`, { token: T1.token, body: { status: "published" } });
    const ws = await api("POST", `/quizzes/${wq.data.quiz?.id}/attempts`, { token: A.token });
    check(`assessment ${label}: start refused (409 QUIZ_CLOSED)`, wq.status === 201 && ws.status === 409 && ws.data.error?.code === "QUIZ_CLOSED", `${wq.status} ${ws.status}`);
  }
  const parallel = await Promise.all([1, 2, 3].map(() => api("POST", `/quizzes/${quizId}/attempts`, { token: B.token })));
  const bAttemptIds = new Set(parallel.filter((r) => r.status < 300).map((r) => r.data.attempt.id));
  check("parallel starts create one attempt", bAttemptIds.size === 1, [...bAttemptIds].length);
  const bId = [...bAttemptIds][0];
  const bWrong = {};
  for (const q of picks) bWrong[q.id] = q.qtype === "true_false" ? !q.answer : q.qtype === "fill_blank" ? "nope" : q.qtype === "mcq" ? q.options.find((o) => o.id !== q.answer).id : null;
  const [r1, r2] = await Promise.all([1, 2].map(() => api("POST", `/attempts/${bId}/submit`, { token: B.token, body: { responses: bWrong } })));
  check("concurrent double submit: one 200, one 409", [r1.status, r2.status].sort().join(",") === "200,409", `${r1.status},${r2.status}`);

  // ---- timed quiz: late submissions use the server autosave ----
  const timed = await api("POST", "/teacher/quizzes", { token: T1.token, body: { title: `Timed ${stamp}`, topic: "Test topic", mode: "practice", activity_type: "beat_the_clock", time_limit_sec: 30, question_ids: qids.slice(0, 2) } });
  created.quizzes.push(timed.data.quiz.id);
  await api("POST", `/teacher/quizzes/${timed.data.quiz.id}/status`, { token: T1.token, body: { status: "published" } });
  const ts = await api("POST", `/quizzes/${timed.data.quiz.id}/attempts`, { token: A.token });
  check("timed attempt has a server deadline", Boolean(ts.data.attempt.deadline_at));
  const tq = ts.data.questions;
  await api("POST", `/attempts/${ts.data.attempt.id}/autosave`, { token: A.token, body: { responses: { [tq[0].id]: resp[tq[0].id] } } });
  await pool.query("UPDATE quiz_attempts SET deadline_at = DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 2 MINUTE), started_at = DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 3 MINUTE) WHERE id = ?", [ts.data.attempt.id]);
  const lateSave = await api("POST", `/attempts/${ts.data.attempt.id}/autosave`, { token: A.token, body: { responses: resp } });
  check("autosave after the deadline is refused", lateSave.status === 409);
  const late = await api("POST", `/attempts/${ts.data.attempt.id}/submit`, { token: A.token, body: { responses: { [tq[0].id]: resp[tq[0].id], [tq[1].id]: resp[tq[1].id] } } });
  check("late submit is scored from the autosave only (50%)", late.data.late === true && late.data.attempt.percent === 50, JSON.stringify(late.data.attempt));

  // ---- assessment mode reveal rules ----
  const assess = await api("POST", "/teacher/quizzes", { token: T1.token, body: { title: `Post-test ${stamp}`, topic: "Test topic", mode: "assessment", assessment_phase: "post", reveal_answers: "after_close", max_attempts: 1, question_ids: qids.slice(0, 3) } });
  created.quizzes.push(assess.data.quiz.id);
  const unlinked = await api("POST", `/teacher/quizzes/${assess.data.quiz.id}/status`, { token: T1.token, body: { status: "published" } });
  check("post-test cannot be published before it is linked to a pre-test", unlinked.status >= 400, `status=${unlinked.status}`);
  const pre = await api("POST", "/teacher/quizzes", { token: T1.token, body: { title: `Pre-test ${stamp}`, topic: "Test topic", mode: "assessment", assessment_phase: "pre", reveal_answers: "after_close", max_attempts: 1, question_ids: qids.slice(0, 3) } });
  created.quizzes.push(pre.data.quiz.id);
  await api("POST", `/teacher/quizzes/${pre.data.quiz.id}/status`, { token: T1.token, body: { status: "published" } });
  const linkBody = { title: `Post-test ${stamp}`, topic: "Test topic", mode: "assessment", assessment_phase: "post", pre_quiz_id: pre.data.quiz.id, reveal_answers: "after_close", max_attempts: 1, question_ids: qids.slice(0, 3) };
  await api("POST", `/teacher/quizzes/${assess.data.quiz.id}`, { token: T1.token, body: linkBody });
  const linked = await api("POST", `/teacher/quizzes/${assess.data.quiz.id}/status`, { token: T1.token, body: { status: "published" } });
  check("linked post-test can be published", linked.status === 200, `status=${linked.status}`);
  const as = await api("POST", `/quizzes/${assess.data.quiz.id}/attempts`, { token: A.token });
  const asSubmit = await api("POST", `/attempts/${as.data.attempt.id}/submit`, { token: A.token, body: { responses: resp } });
  check("assessment hides answers while open", asSubmit.data.reveal === false && asSubmit.data.questions.every((q) => !("answer" in q)) && Boolean(asSubmit.data.reveal_note));
  await api("POST", `/teacher/quizzes/${assess.data.quiz.id}/status`, { token: T1.token, body: { status: "archived" } });
  const asAfter = await api("GET", `/attempts/${as.data.attempt.id}`, { token: A.token });
  check("assessment reveals after the teacher closes it", asAfter.data.reveal === true && asAfter.data.questions.every((q) => "answer" in q));
  const lockedEdit = await api("POST", `/teacher/quizzes/${quizId}`, { token: T1.token, body: { ...quizBody, question_ids: qids.slice(0, 2) } });
  check("questions of a quiz with attempts cannot change", lockedEdit.status === 409);

  // ---- activities ----
  const hist = await api("GET", "/me/quiz-history", { token: A.token });
  check("history has attempts, topic performance and suggestions", hist.status === 200 && hist.data.attempts.length >= 3 && hist.data.topics.length >= 1);
  const rev = await api("POST", "/activities/revision", { token: A.token });
  check("revision challenge built from missed topics", rev.status === 201 && rev.data.question_count >= 1, JSON.stringify(rev.data));
  const revList = await api("GET", "/quizzes?activity_type=revision", { token: A.token });
  check("revision quiz visible to its owner", revList.data.quizzes.some((q) => q.id === rev.data.quiz_id && q.personal));
  const revB = await api("GET", "/quizzes?activity_type=revision", { token: B.token });
  check("revision quiz hidden from other students", !revB.data.quizzes.some((q) => q.id === rev.data.quiz_id));
  const revStartB = await api("POST", `/quizzes/${rev.data.quiz_id}/attempts`, { token: B.token });
  check("other student cannot start someone's revision quiz", revStartB.status === 404);
  const revStart = await api("POST", `/quizzes/${rev.data.quiz_id}/attempts`, { token: A.token });
  const revDone = await api("POST", `/attempts/${revStart.data.attempt.id}/submit`, { token: A.token, body: { responses: {} } });
  check("activity attempt is scored like a quiz", revDone.status === 200 && revDone.data.attempt.percent === 0);
  const noData = await api("POST", "/activities/revision", { token: (await student("Fresh Student")).token });
  check("revision challenge with no data explains why", noData.status === 409 && noData.data.error?.code === "NO_DATA");
  const cp = await api("POST", "/activities/checkpoint", { token: A.token, body: { topic: "Akbar's administration" } });
  check("module checkpoint quiz created", cp.status === 201 && cp.data.question_count >= 3, JSON.stringify(cp.data));
  const cpNone = await api("POST", "/activities/checkpoint", { token: A.token, body: { topic: "Quantum physics" } });
  check("checkpoint for an unknown topic is 404", cpNone.status === 404);

  // ---- teacher results + analytics vs database ----
  const results = await api("GET", `/teacher/quizzes/${quizId}/results`, { token: T2.token });
  const [[dbQuiz]] = await pool.query("SELECT COUNT(*) AS n, AVG(percent) AS m FROM quiz_attempts WHERE quiz_id = ? AND status = 'submitted'", [quizId]);
  check("quiz results aggregate matches the database", results.status === 200 && results.data.aggregate.attempts === Number(dbQuiz.n) && Math.abs(results.data.aggregate.mean_percent - Number(dbQuiz.m)) < 0.1, `${results.data.aggregate?.attempts} vs ${dbQuiz.n}`);
  check("individual results listed", results.data.individual.length === Number(dbQuiz.n));
  const ov = await api("GET", `/teacher/analytics/overview?from=${today}&to=${today}`, { token: T1.token });
  const [[dbToday]] = await pool.query(
    `SELECT COUNT(*) AS n FROM quiz_attempts a JOIN users u ON u.id = a.user_id AND u.role = 'student'
     WHERE a.status = 'submitted' AND a.submitted_at >= ? AND a.submitted_at < ?`,
    [new Date(`${today}T00:00:00+05:30`), new Date(new Date(`${today}T00:00:00+05:30`).getTime() + 86400000)]
  );
  check("overview quiz attempts match the database for today", ov.status === 200 && ov.data.cards.quiz_attempts === Number(dbToday.n), `${ov.data.cards?.quiz_attempts} vs ${dbToday.n}`);
  check("overview has definitions and tracking dates; sign-ins are a real count", Boolean(ov.data.definitions?.active_students) && Boolean(ov.data.tracking?.quiz_tracking_began) && Boolean(ov.data.tracking?.progress_tracking_began) && Number.isInteger(ov.data.cards.sign_ins));
  const [[dbStudents]] = await pool.query("SELECT COUNT(*) AS n FROM users WHERE role = 'student'");
  check("overview student total matches the database", ov.data.cards.students_total === Number(dbStudents.n));
  const emptyRange = await api("GET", "/teacher/analytics/overview?from=2020-01-01&to=2020-01-31", { token: T1.token });
  check("empty date range returns zeros, not errors", emptyRange.status === 200 && emptyRange.data.cards.quiz_attempts === 0 && emptyRange.data.cards.mean_percent === null && Boolean(emptyRange.data.notes.quiz));
  const badRange = await api("GET", "/teacher/analytics/overview?from=2026-02-10&to=2026-01-01", { token: T1.token });
  check("invalid date range is 400", badRange.status === 400);
  const st = await api("GET", `/teacher/analytics/students?search=Quiz%20Student%20A&from=${today}&to=${today}`, { token: T1.token });
  const rowA = st.data.students?.find((s) => s.id === A.id);
  const [[dbA]] = await pool.query(
    "SELECT COUNT(*) AS n FROM quiz_attempts WHERE user_id = ? AND status = 'submitted' AND submitted_at >= ? AND submitted_at < ?",
    [A.id, new Date(`${today}T00:00:00+05:30`), new Date(new Date(`${today}T00:00:00+05:30`).getTime() + 86400000)]
  );
  check("students table counts match the database", rowA && rowA.quiz_attempts === Number(dbA.n), `${rowA?.quiz_attempts} vs ${dbA.n}`);
  check("students table has no email or chat text", st.data.students.every((s) => !("email" in s) && !("content" in s)));
  const sorted = await api("GET", `/teacher/analytics/students?sort=quiz_attempts&dir=desc&size=2&page=1&from=${today}&to=${today}`, { token: T1.token });
  check("students table sorts and paginates", sorted.status === 200 && sorted.data.students.length <= 2 && sorted.data.total >= 2);
  const badSort = await api("GET", "/teacher/analytics/students?sort=password_hash", { token: T1.token });
  check("unknown sort column rejected", badSort.status === 400);
  const prof = await api("GET", `/teacher/analytics/students/${A.id}`, { token: T1.token });
  check("student profile with attempts and topics", prof.status === 200 && prof.data.attempts.length >= 3 && Array.isArray(prof.data.suggested_topics));
  const profTeacher = await api("GET", `/teacher/analytics/students/${T2.id}`, { token: T1.token });
  check("profile endpoint only serves students", profTeacher.status === 404);
  const tp = await api("GET", `/teacher/analytics/topics?from=${today}&to=${today}`, { token: T1.token });
  check("topic analytics returned", tp.status === 200 && tp.data.topics.length >= 1);
  const tsr = await api("GET", `/teacher/analytics/timeseries?from=${today}&to=${today}`, { token: T1.token });
  check("time series with sample sizes", tsr.status === 200 && tsr.data.series.length >= 1 && tsr.data.series.every((p) => "quiz_attempts" in p));
  const ach = await api("GET", `/teacher/analytics/achievement?from=${today}&to=${today}`, { token: T1.token });
  check("achievement stats (n, mean, median, distribution)", ach.status === 200 && ach.data.overall.n >= 1 && ach.data.overall.median !== undefined && ach.data.overall.distribution.length === 5);

  // ---- CSV ----
  const csvAnon = await api("GET", "/teacher/reports/attempts.csv", { raw: true });
  const csvStudent = await api("GET", "/teacher/reports/attempts.csv", { token: A.token, raw: true });
  check("CSV needs a teacher (401/403)", csvAnon.status === 401 && csvStudent.status === 403);
  const csv = await api("GET", `/teacher/reports/attempts.csv?from=${today}&to=${today}&include_names=1`, { token: T1.token, raw: true });
  check("CSV attachment headers", csv.status === 200 && /text\/csv/.test(csv.headers.get("content-type")) && /attachment/.test(csv.headers.get("content-disposition")));
  check("CSV formula injection guarded (title and name)", csv.text.includes("\"'=HYPERLINK") && csv.text.includes("'=cmd") && !/(^|,)=HYPERLINK/m.test(csv.text) && !/(^|,)=cmd/m.test(csv.text));
  const csvNoNames = await api("GET", `/teacher/reports/students.csv?from=${today}&to=${today}`, { token: T1.token, raw: true });
  check("default CSV has pseudonymous refs, no names or emails", csvNoNames.status === 200 && /S-[0-9a-f]{8}/.test(csvNoNames.text) && !csvNoNames.text.includes("Quiz Student A") && !csvNoNames.text.includes("@example.com"));
  const unknownCsv = await api("GET", "/teacher/reports/passwords.csv", { token: T1.token, raw: true });
  check("unknown report is 404", unknownCsv.status === 404);

  // ---- analytics events contain no text ----
  const [ev] = await pool.query("SELECT event_type, topic_text, metadata_json FROM analytics_events WHERE user_id = ?", [A.id]);
  check("quiz events recorded with user id and no text", ev.length >= 3 && ev.every((e) => e.topic_text == null) && ev.some((e) => e.event_type === "QUIZ_SUBMITTED"));

}

async function cleanup(before) {
  const marks = created.users.map(() => "?").join(",");
  // Personal quizzes, attempts, answers and events cascade with the users.
  const quizIds = created.quizzes.filter(Boolean);
  if (quizIds.length) await pool.query("DELETE FROM quizzes WHERE id IN (?)", [quizIds]);
  if (created.users.length) {
    await pool.query(`DELETE FROM quizzes WHERE owner_user_id IN (${marks})`, created.users);
    await pool.query(`DELETE FROM auth_sessions WHERE user_id IN (${marks})`, created.users);
    await pool.query(`DELETE FROM anonymous_sessions WHERE user_id IN (${marks})`, created.users);
    await pool.query(`DELETE FROM users WHERE id IN (${marks})`, created.users);
  }
  const qIds = created.questions.filter(Boolean);
  if (qIds.length) await pool.query("DELETE FROM quiz_questions WHERE id IN (?)", [qIds]);
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
  console.log(`quiz_test ${pass}/${pass + fail} PASS`);
  process.exit(fail ? 1 : 0);
}

/* Real-browser end-to-end run against the TEST instances (backend :3100, Ollama-only RAG :8100, app :4173).
 * Student: register -> sign out -> sign in -> chat question -> learning module -> Mark complete -> PDF ->
 * practice quiz -> Try again (old attempt kept) -> formal assessment -> sign out.
 * Teacher: sign in -> Overview (activity chart) -> Students -> CSV downloads, all compared with the database.
 * Privacy: a second student cannot see or open the first student's chats.
 * Only records created here are deleted at the end; table counts are compared before/after.
 * Credentials are random per run and never printed. */
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const ROOT = path.resolve(__dirname, "..");
require(path.join(ROOT, "backend/node_modules/dotenv")).config({ path: path.join(ROOT, ".env") });
const mysql = require(path.join(ROOT, "backend/node_modules/mysql2/promise"));
const API = process.env.E2E_API || "http://127.0.0.1:3100/api/v1";
const APP = process.env.E2E_APP || "http://127.0.0.1:4173";
const OUT = path.join(ROOT, "tmp", "final-dev", "browser-e2e");
fs.mkdirSync(OUT, { recursive: true });
const COUNT_TABLES = ["users", "auth_sessions", "anonymous_sessions", "conversations", "messages", "econtent_documents", "analytics_events", "quizzes", "quiz_attempts", "quiz_answers", "module_progress"];

let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail !== "" ? ` — ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : ""}`);
};
async function api(method, p, token, body) {
  const r = await fetch(`${API}${p}`, { method, headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}
const istDay = () => new Date(Date.now() + 330 * 60000).toISOString().slice(0, 10);

async function main(db, created) {
  const stamp = Date.now();
  const pw = `Br-${crypto.randomBytes(9).toString("hex")}`;
  const email = `browser.e2e.${stamp}@example.com`;
  const temail = `browser.e2e.teacher.${stamp}@example.com`;
  const { hashPassword } = await import(require("url").pathToFileURL(path.join(ROOT, "backend/src/services/passwords.js")).href);
  const tid = crypto.randomUUID();
  await db.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'admin')", [tid, temail, "Browser E2E Teacher", await hashPassword(pw)]);
  created.users.push(tid);
  const T = (await api("POST", "/auth/login", null, { email: temail, password: pw })).data.token;
  // Fixtures: a practice quiz (unlimited attempts) and a formal assessment (1 attempt), both from published questions.
  const bank = (await api("GET", "/teacher/questions?status=published&size=100", T)).data.questions;
  const tf = bank.filter((q) => q.qtype === "true_false").slice(0, 2).map((q) => q.id);
  const mcq = bank.filter((q) => q.qtype === "mcq").slice(0, 2).map((q) => q.id);
  const mk = async (body) => {
    const r = await api("POST", "/teacher/quizzes", T, body);
    created.quizzes.push(r.data.quiz?.id);
    await api("POST", `/teacher/quizzes/${r.data.quiz?.id}/status`, T, { status: "published" });
    return r.data.quiz;
  };
  const practice = await mk({ title: `Browser E2E Practice ${stamp}`, topic: "E2E", mode: "practice", question_ids: [...tf, ...mcq] });
  const assess = await mk({ title: `Browser E2E Assessment ${stamp}`, topic: "E2E", mode: "assessment", max_attempts: 1, reveal_answers: "after_submit", question_ids: [...mcq, ...tf] });
  check("fixtures: practice quiz and formal assessment published", Boolean(practice?.id && assess?.id));

  const browser = await chromium.launch(process.env.E2E_CHANNEL ? { channel: process.env.E2E_CHANNEL } : {});
  const errors = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text().slice(0, 160)));

    // --- register, sign out, sign in
    await page.goto(`${APP}/signup`, { waitUntil: "networkidle" });
    await page.getByLabel("Name").fill("Browser E2E Student");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(pw);
    await page.getByLabel("Confirm password").fill(pw);
    await page.getByRole("button", { name: "Create student account" }).click();
    await page.waitForURL((u) => !/signup/.test(u.pathname), { timeout: 20000 });
    const [[u]] = await db.query("SELECT id, role FROM users WHERE email = ?", [email]);
    if (u) created.users.push(u.id);
    check("student registers through the form (role student)", u?.role === "student", u?.role);
    await page.goto(`${APP}/chat`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Log out" }).click();
    await page.waitForTimeout(800);
    await page.goto(`${APP}/login`, { waitUntil: "networkidle" });
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(pw);
    await page.getByRole("button", { name: "Log in" }).click();
    await page.waitForURL((x) => !/login/.test(x.pathname), { timeout: 20000 });
    const [[si]] = await db.query("SELECT COUNT(*) AS n FROM analytics_events WHERE user_id = ? AND event_type = 'USER_SIGNED_IN'", [u.id]);
    check("sign out then sign in through the form; one sign-in recorded", Number(si.n) === 1, si.n);

    // --- chat (Ollama test RAG)
    await page.goto(`${APP}/chat`, { waitUntil: "networkidle" });
    await page.getByRole("textbox").first().fill("Who was Akbar?");
    await page.getByRole("textbox").first().press("Enter");
    await page.waitForFunction(() => document.querySelectorAll("article").length >= 2 && !document.body.innerText.includes("Thinking"), null, { timeout: 240000 }).catch(() => {});
    const answer = await page.locator("article").nth(1).innerText().catch(() => "");
    await page.screenshot({ path: path.join(OUT, "chat.png") });
    const [[msg]] = await db.query("SELECT COUNT(*) AS n FROM messages m JOIN conversations c ON c.id = m.conversation_id JOIN anonymous_sessions s ON s.id = c.session_id WHERE s.user_id = ? AND m.role = 'user'", [u.id]);
    check("chat question answered in the browser and stored once", answer.length > 40 && Number(msg.n) === 1, { chars: answer.length, stored: msg.n });

    // --- learning module, Mark complete, PDF
    await page.getByRole("button", { name: "Make a learning module" }).click();
    await page.getByRole("button", { name: /Mark complete/ }).waitFor({ timeout: 300000 });
    await page.screenshot({ path: path.join(OUT, "module.png") });
    await page.getByRole("button", { name: /Mark complete/ }).click();
    await page.getByText("Completed ✓").waitFor({ timeout: 20000 });
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), page.getByRole("button", { name: "Download PDF" }).first().click()]);
    const pdfPath = path.join(OUT, dl.suggestedFilename());
    await dl.saveAs(pdfPath);
    const head = fs.readFileSync(pdfPath).subarray(0, 4).toString();
    const [[mp]] = await db.query("SELECT COUNT(*) AS n, SUM(completed_at IS NOT NULL) AS done, SUM(pdf_downloads) AS pdf FROM module_progress WHERE user_id = ?", [u.id]);
    check("module generated, marked complete and PDF downloaded (DB agrees)", head === "%PDF" && Number(mp.done) === 1 && Number(mp.pdf) === 1, { file: dl.suggestedFilename(), ...mp });

    // --- practice quiz + Try again
    const answerAll = async () => {
      for (let i = 0; i < 8; i++) {
        const radio = page.getByRole("radio").first();
        if (await radio.count()) await radio.click();
        const next = page.getByRole("button", { name: "Next →" });
        if (await next.count() && (await next.isEnabled())) await next.click();
        else break;
      }
      await page.getByRole("button", { name: "Submit", exact: true }).first().click();
      await page.getByRole("dialog").getByRole("button", { name: "Submit" }).click();
      await page.getByTestId("attempt-line").waitFor({ timeout: 20000 });
    };
    await page.goto(`${APP}/quizzes`, { waitUntil: "networkidle" });
    const card = page.locator("li, article, div").filter({ hasText: practice.title }).last();
    await card.getByRole("button", { name: /Start|Continue/ }).first().click();
    await page.getByText(/Question 1 of/).waitFor();
    await answerAll();
    const ui1 = await page.locator("p.font-serif.text-4xl").first().innerText();
    globalThis.__page = page;
    await page.getByRole("button", { name: "Try again" }).dblclick();
    await page.getByText(/Question 1 of/).waitFor();
    await answerAll();
    await page.screenshot({ path: path.join(OUT, "results.png") });
    const prev = await page.getByTestId("previous-attempts").innerText().catch(() => "");
    const [att] = await db.query("SELECT attempt_no, status, percent FROM quiz_attempts WHERE user_id = ? AND quiz_id = ? ORDER BY attempt_no", [u.id, practice.id]);
    check("Try again (double-clicked) created exactly one new attempt; attempt 1 kept and listed", att.length === 2 && att.every((a) => a.status === "submitted") && /Attempt 1/.test(prev) && /Attempt 2/.test(prev), att);
    check("result percentage shown equals the database", ui1.replace("%", "").trim() === String(Number(att[0].percent)), { ui: ui1, db: att[0].percent });

    // --- formal assessment (1 attempt)
    await page.goto(`${APP}/quizzes`, { waitUntil: "networkidle" });
    await page.locator("li, article, div").filter({ hasText: assess.title }).last().getByRole("button", { name: /Start|Continue/ }).first().click();
    await page.getByText(/Question 1 of/).waitFor();
    await answerAll();
    const tryAgain = await page.getByRole("button", { name: "Try again" }).count();
    const blocked = await page.getByText("You have used all attempts for this quiz.").count();
    const again = await api("POST", `/quizzes/${assess.id}/attempts`, (await api("POST", "/auth/login", null, { email, password: pw })).data.token);
    check("assessment: submitted once, no Try again, server refuses a second attempt", tryAgain === 0 && blocked === 1 && again.status === 409, { tryAgain, blocked, second: again.status });

    // --- sign out
    await page.goto(`${APP}/quizzes`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Log out" }).first().click().catch(async () => {
      await page.goto(`${APP}/chat`);
      await page.getByRole("button", { name: "Log out" }).click();
    });
    await page.waitForTimeout(800);
    await page.goto(`${APP}/quizzes`, { waitUntil: "networkidle" });
    check("after sign out, student pages require login", /login|start|\/$/.test(new URL(page.url()).pathname) || (await page.getByRole("button", { name: "Log in" }).count()) > 0, page.url());

    // --- privacy: second student
    const reg2 = await api("POST", "/auth/register", null, { display_name: "Browser E2E Other", email: `browser.e2e.other.${stamp}@example.com`, password: pw });
    created.users.push(reg2.data.user?.id);
    const [[conv]] = await db.query("SELECT c.id, c.session_id FROM conversations c JOIN anonymous_sessions s ON s.id = c.session_id WHERE s.user_id = ? LIMIT 1", [u.id]);
    const peek = await api("GET", `/conversations?session_id=${conv.session_id}`, reg2.data.token);
    const peek2 = await api("GET", `/conversations/${conv.id}?session_id=${conv.session_id}`, reg2.data.token);
    const ctx2 = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await ctx2.addInitScript((t) => localStorage.setItem("historybot_auth_token", t), reg2.data.token);
    const p2 = await ctx2.newPage();
    await p2.goto(`${APP}/chat`, { waitUntil: "networkidle" });
    // "Who was Akbar?" is also a suggestion chip, so look for the first student's stored answer instead.
    const [[firstAnswer]] = await db.query("SELECT m.content FROM messages m WHERE m.conversation_id = ? AND m.role = 'assistant' ORDER BY m.created_at LIMIT 1", [conv.id]);
    const snippet = String(firstAnswer?.content || "").replace(/\s+/g, " ").trim().slice(0, 40);
    const leaks = snippet ? await p2.getByText(snippet, { exact: false }).count() : 1;
    check("another student cannot list or read the first student's chats (API and UI)", [403, 404].includes(peek.status) && [403, 404].includes(peek2.status) && leaks === 0, { list: peek.status, read: peek2.status, uiMatches: leaks });
    await ctx2.close();
    await ctx.close();

    // --- teacher dashboard
    const tctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
    const tp = await tctx.newPage();
    tp.on("pageerror", (e) => errors.push(String(e)));
    await tp.goto(`${APP}/teacher/login`, { waitUntil: "networkidle" });
    await tp.getByLabel("Email").fill(temail);
    await tp.getByLabel("Password").fill(pw);
    await tp.getByRole("button", { name: "Log in" }).click();
    await tp.waitForURL(/admin/, { timeout: 20000 });
    await tp.goto(`${APP}/admin?tab=overview`, { waitUntil: "networkidle" });
    await tp.getByTestId("trend-chart").waitFor({ timeout: 20000 });
    await tp.screenshot({ path: path.join(OUT, "dashboard-overview.png"), fullPage: true });
    const today = istDay();
    const chart = await tp.evaluate((d) => {
      const day = [...document.querySelectorAll("[data-testid=trend-day]")].pop();
      const bars = day ? [...day.children].filter((b) => b.getBoundingClientRect().height > 0.5).length : 0;
      return { total: day ? Number(day.dataset.total) : null, bars, title: day?.title || "" , d };
    }, today);
    const ts = (await api("GET", `/teacher/analytics/timeseries?from=${today}&to=${today}`, T)).data.series[0];
    const tsTotal = ts.chat_questions + ts.quiz_attempts + ts.modules_opened + ts.modules_completed + ts.pdf_downloads;
    check("Activity chart: today's column is drawn and its total equals the API", chart.total === tsTotal && chart.bars > 0, { chart, tsTotal });
    const cards = await tp.getByTestId("stat-value").allInnerTexts();
    const ov = (await api("GET", "/teacher/analytics/overview", T)).data;
    check("Overview headline cards rendered (6) with the API values", cards.length >= 6 && String(ov.cards.registered_in_range) === cards[0].trim(), { cards: cards.slice(0, 6), api: ov.cards.registered_in_range });
    await tp.goto(`${APP}/admin?tab=students`, { waitUntil: "networkidle" });
    const row = await tp.getByText("Browser E2E Student").count();
    check("Students tab lists the test student", row > 0);
    await tp.goto(`${APP}/admin?tab=reports`, { waitUntil: "networkidle" });
    const csvs = {};
    for (const [i, kind] of ["attempts", "students"].entries()) {
      const [d] = await Promise.all([tp.waitForEvent("download"), tp.getByRole("button", { name: "Download CSV" }).nth(i).click()]);
      const f = path.join(OUT, `${kind}.csv`);
      await d.saveAs(f);
      csvs[kind] = fs.readFileSync(f, "utf8");
    }
    const ref = `S-${u.id.replace(/-/g, "").slice(0, 8)}`;
    const attemptRows = csvs.attempts.split(/\r?\n/).filter((l) => l.includes(ref)).length;
    const [[dbAtt]] = await db.query("SELECT COUNT(*) AS n FROM quiz_attempts WHERE user_id = ? AND status = 'submitted'", [u.id]);
    check("attempts CSV (downloaded in the browser) has one row per submitted attempt of the student", attemptRows === Number(dbAtt.n), { csv: attemptRows, db: dbAtt.n });
    const stuLine = csvs.students.split(/\r?\n/).find((l) => l.includes(ref)) || "";
    check("students CSV row present, pseudonymous, no name or email", Boolean(stuLine) && !csvs.students.includes(email) && !csvs.students.includes("Browser E2E Student"), stuLine.slice(0, 120));
    const lastIst = (stuLine.split(",").pop() || "").replace(" IST", "").replace(" ", "T") + "+05:30";
    const skewMin = Math.abs(Date.now() - new Date(lastIst).getTime()) / 60000;
    check("students CSV last_active_ist is the real IST time (within 15 min of now)", skewMin < 15, { last: stuLine.split(",").pop(), skewMin: Math.round(skewMin) });
    await tctx.close();
    check("no script errors in student or teacher pages", errors.length === 0, errors.slice(0, 3));
  } catch (e) {
    if (globalThis.__page) {
      try {
        console.log("URL", globalThis.__page.url());
        await globalThis.__page.screenshot({ path: path.join(OUT, "failure.png"), fullPage: true });
        console.log("TEXT", (await globalThis.__page.locator("body").innerText({ timeout: 3000 })).slice(0, 1200));
      } catch {}
    }
    throw e;
  } finally {
    await browser.close();
  }
}

process.on("unhandledRejection", (e) => console.log(`(ignored late rejection: ${String(e).slice(0, 120)})`));
(async () => {
  const db = await mysql.createConnection({ host: process.env.MYSQL_HOST || "localhost", port: Number(process.env.MYSQL_PORT || 3306), user: process.env.MYSQL_USER, password: process.env.MYSQL_PASSWORD || "", database: process.env.MYSQL_DATABASE || "historybot" });
  const counts = async () => Object.fromEntries(await Promise.all(COUNT_TABLES.map(async (t) => [t, Number((await db.query(`SELECT COUNT(*) AS n FROM ${t}`))[0][0].n)])));
  // remove leftovers of an earlier interrupted run of this script only
  const [old] = await db.query("SELECT id FROM users WHERE email LIKE 'browser.e2e.%@example.com'");
  if (old.length) {
    const ids = old.map((r) => r.id);
    await db.query("DELETE FROM quiz_attempts WHERE user_id IN (?) OR quiz_id IN (SELECT id FROM quizzes WHERE owner_user_id IN (?))", [ids, ids]);
    await db.query("DELETE FROM quizzes WHERE owner_user_id IN (?)", [ids]);
    await db.query("DELETE FROM auth_sessions WHERE user_id IN (?)", [ids]);
    await db.query("DELETE FROM anonymous_sessions WHERE user_id IN (?)", [ids]);
    await db.query("DELETE FROM users WHERE id IN (?)", [ids]);
    console.log(`cleaned ${ids.length} leftover test users from an earlier run`);
  }
  const before = await counts();
  const created = { users: [], quizzes: [] };
  try {
    await main(db, created);
  } catch (err) {
    fail++;
    console.log(`FAIL unexpected — ${String(err.stack || err).slice(0, 900)}`);
    if (globalThis.__page) {
      try {
        console.log("URL", globalThis.__page.url());
        console.log("TEXT", (await globalThis.__page.locator("main").innerText({ timeout: 3000 })).slice(0, 800));
      } catch {}
    }
  } finally {
    const users = created.users.filter(Boolean);
    const quizIds = created.quizzes.filter(Boolean);
    if (users.length) {
      await db.query("DELETE FROM quiz_attempts WHERE user_id IN (?) OR quiz_id IN (SELECT id FROM quizzes WHERE owner_user_id IN (?))", [users, users]);
      await db.query("DELETE FROM quizzes WHERE owner_user_id IN (?)", [users]);
    }
    if (quizIds.length) {
      await db.query("DELETE FROM quiz_attempts WHERE quiz_id IN (?)", [quizIds]);
      await db.query("DELETE FROM quizzes WHERE id IN (?)", [quizIds]);
    }
    if (users.length) {
      await db.query("DELETE FROM auth_sessions WHERE user_id IN (?)", [users]);
      await db.query("DELETE FROM anonymous_sessions WHERE user_id IN (?)", [users]);
      await db.query("DELETE FROM users WHERE id IN (?)", [users]);
    }
    const after = await counts();
    const diff = COUNT_TABLES.filter((t) => after[t] !== before[t]).map((t) => `${t}:${before[t]}->${after[t]}`);
    check("only test records removed: table counts unchanged", diff.length === 0, diff.join(" ") || "all equal");
    await db.end();
    console.log(`browser_e2e ${pass}/${pass + fail} ${fail ? "FAIL" : "PASS"}`);
    process.exit(fail ? 1 : 0);
  }
})();

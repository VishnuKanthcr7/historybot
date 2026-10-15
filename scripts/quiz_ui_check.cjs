/**
 * Playwright check of the quiz player and teacher dashboard at 1366 and 390 px.
 * Needs: a test backend (QUIZ_UI_API, default http://127.0.0.1:3100/api/v1) and a built frontend served at
 * QUIZ_UI_APP (default http://127.0.0.1:4173) that points at that backend. Creates a temporary student and
 * teacher and deletes them (and their attempts) at the end. No AI calls.
 */
const path = require("path");
const fs = require("fs");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const ROOT = path.resolve(__dirname, "..");
require(path.join(ROOT, "backend/node_modules/dotenv")).config({ path: path.join(ROOT, ".env") });
const mysql = require(path.join(ROOT, "backend/node_modules/mysql2/promise"));
const API = process.env.QUIZ_UI_API || "http://127.0.0.1:3100/api/v1";
const APP = process.env.QUIZ_UI_APP || "http://127.0.0.1:4173";
const OUT = process.env.QUIZ_UI_OUT || path.join(ROOT, "tmp", "final-dev", "quiz-ui");
fs.mkdirSync(OUT, { recursive: true });

let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};

async function api(method, p, token, body) {
  const r = await fetch(`${API}${p}`, {
    method,
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.MYSQL_HOST || "localhost",
    port: Number(process.env.MYSQL_PORT || 3306),
    user: process.env.MYSQL_USER,
    password: process.env.MYSQL_PASSWORD || "",
    database: process.env.MYSQL_DATABASE || "historybot",
  });
  const created = [];
  const stamp = Date.now();
  const password = `UiCheck-${stamp}-Pw`;
  const browser = await chromium.launch(process.env.QUIZ_UI_CHANNEL ? { channel: process.env.QUIZ_UI_CHANNEL } : {});
  try {
    const reg = await api("POST", "/auth/register", null, { display_name: "UI Check Student", email: `ui.student.${stamp}@example.com`, password });
    created.push(reg.data.user.id);
    const { hashPassword } = await import(require("url").pathToFileURL(path.join(ROOT, "backend/src/services/passwords.js")).href);
    const tid = require("crypto").randomUUID();
    await db.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'admin')", [tid, `ui.teacher.${stamp}@example.com`, "UI Check Teacher", await hashPassword(password)]);
    created.push(tid);
    const tlogin = await api("POST", "/auth/login", null, { email: `ui.teacher.${stamp}@example.com`, password });

    for (const [w, h] of [[1366, 800], [390, 844]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      await ctx.addInitScript((t) => localStorage.setItem("historybot_auth_token", t), reg.data.token);
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      await page.goto(`${APP}/quizzes`, { waitUntil: "networkidle" });
      await page.getByRole("heading", { name: "Quizzes" }).waitFor();
      const cards = await page.locator("article").count();
      check(`[${w}] quiz list shows published quizzes`, cards >= 5, `${cards} cards`);
      await page.screenshot({ path: path.join(OUT, `quiz-list-${w}.png`), fullPage: true });
      const card = page.locator("article", { hasText: "Match the Figure" }).first();
      await card.getByRole("button", { name: /Start|Continue/ }).click();
      await page.waitForURL(/\/attempts\//);
      await page.getByText(/Question 1 of/).waitFor();
      await page.screenshot({ path: path.join(OUT, `quiz-player-match-${w}.png`), fullPage: true });
      // Tap-to-match: tap left item, then a right item.
      const leftItems = page.getByRole("list", { name: "Items to match" }).getByRole("button");
      await leftItems.first().click();
      await page.getByRole("list", { name: "Possible matches" }).getByRole("button").first().click();
      check(`[${w}] tap-to-match records a pair`, (await leftItems.first().innerText()).includes("→"));
      await page.getByRole("button", { name: "Next →" }).click();
      await page.getByText(/Question 2 of/).waitFor();
      check(`[${w}] next navigation works`, true);
      const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
      check(`[${w}] player has no horizontal overflow`, noOverflow);
      await page.waitForTimeout(1800);
      check(`[${w}] autosave reported`, /Saved/.test(await page.locator("body").innerText()));
      await page.getByRole("button", { name: "Finish and submit" }).click();
      await page.getByRole("dialog").waitFor();
      await page.screenshot({ path: path.join(OUT, `quiz-confirm-${w}.png`) });
      await page.getByRole("dialog").getByRole("button", { name: "Submit" }).click();
      await page.getByText(/points/).first().waitFor();
      const resultText = await page.locator("body").innerText();
      check(`[${w}] results show score and feedback`, /%/.test(resultText) && /Correct answer|Correct/.test(resultText));
      await page.screenshot({ path: path.join(OUT, `quiz-results-${w}.png`), fullPage: true });
      await page.goto(`${APP}/activities`, { waitUntil: "networkidle" });
      await page.getByRole("heading", { name: "Activities" }).waitFor();
      await page.screenshot({ path: path.join(OUT, `activities-${w}.png`), fullPage: true });
      check(`[${w}] activities page lists sections`, (await page.locator("h2").count()) >= 6);
      check(`[${w}] no page errors (student)`, errors.length === 0, errors.join(" | "));
      await ctx.close();

      const tctx = await browser.newContext({ viewport: { width: w, height: h } });
      await tctx.addInitScript((t) => localStorage.setItem("historybot_auth_token", t), tlogin.data.token);
      const tp = await tctx.newPage();
      const terrors = [];
      tp.on("pageerror", (e) => terrors.push(String(e)));
      for (const tab of ["overview", "students", "topics", "achievement", "quizzes", "questions", "reports"]) {
        await tp.goto(`${APP}/admin?tab=${tab}`, { waitUntil: "networkidle" });
        await tp.getByRole("heading", { name: "Dashboard" }).waitFor();
        await tp.waitForTimeout(400);
        const overflow = await tp.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
        check(`[${w}] dashboard ${tab} renders without page overflow`, overflow);
        await tp.screenshot({ path: path.join(OUT, `dashboard-${tab}-${w}.png`), fullPage: true });
      }
      const body = await tp.locator("body").innerText();
      check(`[${w}] reports tab offers CSV`, /Download CSV/.test(body));
      check(`[${w}] no page errors (teacher)`, terrors.length === 0, terrors.join(" | "));
      await tctx.close();
    }
  } finally {
    await browser.close();
    if (created.length) {
      await db.query("DELETE FROM quizzes WHERE owner_user_id IN (?)", [created]);
      await db.query("DELETE FROM auth_sessions WHERE user_id IN (?)", [created]);
      await db.query("DELETE FROM anonymous_sessions WHERE user_id IN (?)", [created]);
      await db.query("DELETE FROM users WHERE id IN (?)", [created]);
      console.log("CLEANUP_OK");
    }
    await db.end();
  }
}

main()
  .catch((e) => {
    fail++;
    console.log(`FAIL unexpected — ${e.stack || e}`);
  })
  .finally(() => {
    console.log(`quiz_ui ${pass}/${pass + fail} PASS`);
    process.exit(fail ? 1 : 0);
  });

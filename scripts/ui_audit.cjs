/**
 * Playwright layout audit: main pages, every dashboard tab, quiz player and questionnaire at
 * 1920x1080, 1366x768, 768x1024, 390x844 and 360x800. Programmatic checks per page:
 *   - horizontal page overflow (document wider than the viewport)
 *   - visible elements sticking out of the viewport (outside any horizontal scroll container)
 *   - clipped text (text overflowing a fixed box without a scroll container or deliberate truncation)
 *   - overlapping interactive controls (buttons/links/inputs whose boxes intersect)
 *   - tap targets under 24x24 px; page errors
 * Needs a test backend (UI_AUDIT_API, default :3100) and the built frontend pointed at it (UI_AUDIT_APP, default :4173).
 * Creates a temporary student, teacher and questionnaire and deletes them. No AI calls.
 */
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const ROOT = path.resolve(__dirname, "..");
require(path.join(ROOT, "backend/node_modules/dotenv")).config({ path: path.join(ROOT, ".env") });
const mysql = require(path.join(ROOT, "backend/node_modules/mysql2/promise"));
const API = process.env.UI_AUDIT_API || "http://127.0.0.1:3100/api/v1";
const APP = process.env.UI_AUDIT_APP || "http://127.0.0.1:4173";
const OUT = process.env.UI_AUDIT_OUT || path.join(ROOT, "tmp", "final-dev", "ui-audit");
fs.mkdirSync(OUT, { recursive: true });
const VIEWPORTS = (process.env.UI_AUDIT_VIEWPORTS || "390x844,768x1024,1024x768,1366x768,1920x1080").split(",").map((v) => v.split("x").map(Number));

let pass = 0;
let fail = 0;
const findings = [];
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  if (!ok) findings.push(`${name}: ${detail}`);
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

// Runs in the page. Returns a list of problems.
function layoutProblems() {
  const vw = window.innerWidth;
  const out = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > vw + 1) out.push(`page overflow ${doc.scrollWidth}px > ${vw}px`);
  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none" || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (/(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth) return true;
      if (/(auto|scroll|hidden|clip)/.test(s.overflowX) && p.getBoundingClientRect().right <= vw + 1) return true;
    }
    return false;
  };
  const isSrOnly = (el) => {
    for (let p = el; p; p = p.parentElement) if (p.classList?.contains("sr-only")) return true;
    return false;
  };
  const describe = (el) => `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}${el.getAttribute("aria-label") ? `[${el.getAttribute("aria-label")}]` : ""} "${(el.innerText || el.value || "").trim().slice(0, 40)}"`;
  const all = [...document.body.querySelectorAll("*")].filter((el) => !isSrOnly(el) && visible(el));
  let sticking = 0;
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if ((r.right > vw + 1 || r.left < -1) && !inScroller(el)) {
      if (sticking++ < 3) out.push(`outside viewport: ${describe(el)} (${Math.round(r.left)}..${Math.round(r.right)})`);
    }
    const s = getComputedStyle(el);
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (hasText && el.scrollWidth > el.clientWidth + 2 && /(hidden|clip)/.test(s.overflowX) && s.textOverflow !== "ellipsis" && !el.title) {
      out.push(`clipped text: ${describe(el)}`);
    }
  }
  // A control scrolled out of an overflow container is not painted there, so it cannot overlap anything.
  const clippedOut = (el) => {
    const r = el.getBoundingClientRect();
    for (let p = el.parentElement; p; p = p.parentElement) {
      if (!/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowY)) continue;
      const pr = p.getBoundingClientRect();
      if (r.bottom <= pr.top + 1 || r.top >= pr.bottom - 1) return true;
    }
    return false;
  };
  const controls = [...document.querySelectorAll("button, a[href], input:not([type=hidden]), select, textarea")].filter((el) => visible(el) && !isSrOnly(el) && !clippedOut(el));
  const boxes = controls.map((el) => ({ el, r: el.getBoundingClientRect() }));
  let overlaps = 0;
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      if (a.el.closest("label") && a.el.closest("label") === b.el.closest("label")) continue;
      const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (w > 2 && h > 2 && overlaps++ < 3) out.push(`overlap: ${describe(a.el)} / ${describe(b.el)}`);
    }
  }
  const small = controls.filter((el) => {
    const r = el.getBoundingClientRect();
    if (el.tagName === "INPUT" && /checkbox|radio/.test(el.type)) return false;
    if (el.tagName === "A" && getComputedStyle(el).display === "inline") return false; // inline text links
    return r.width < 24 || r.height < 24;
  });
  if (small.length) out.push(`small tap targets (${small.length}): ${small.slice(0, 3).map(describe).join(", ")}`);
  return out;
}

async function audit(page, name, w, h) {
  await page.waitForTimeout(400);
  const problems = await page.evaluate(layoutProblems);
  await page.screenshot({ path: path.join(OUT, `${name}-${w}.png`), fullPage: false });
  check(`[${w}x${h}] ${name}`, problems.length === 0, problems.join(" | "));
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.MYSQL_HOST || "localhost",
    port: Number(process.env.MYSQL_PORT || 3306),
    user: process.env.MYSQL_USER,
    password: process.env.MYSQL_PASSWORD || "",
    database: process.env.MYSQL_DATABASE || "historybot",
  });
  const stamp = Date.now();
  const password = `UiAudit-${stamp}-Pw`;
  const users = [];
  let instrumentId = null;
  let attemptId = null;
  const browser = await chromium.launch(process.env.UI_AUDIT_CHANNEL ? { channel: process.env.UI_AUDIT_CHANNEL } : {});
  try {
    const reg = await api("POST", "/auth/register", null, { display_name: "UI Audit Student", email: `ui.audit.${stamp}@example.com`, password });
    users.push(reg.data.user.id);
    const { hashPassword } = await import(require("url").pathToFileURL(path.join(ROOT, "backend/src/services/passwords.js")).href);
    const tid = crypto.randomUUID();
    await db.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'admin')", [tid, `ui.audit.teacher.${stamp}@example.com`, "UI Audit Teacher", await hashPassword(password)]);
    users.push(tid);
    const tlogin = await api("POST", "/auth/login", null, { email: `ui.audit.teacher.${stamp}@example.com`, password });
    const inst = await api("POST", "/teacher/instruments", tlogin.data.token, {
      title: "UI audit questionnaire (temporary)",
      construct: "Layout test",
      approval_note: "Temporary layout-test items; deleted after the audit.",
      items: [1, 2, 3].map((i) => ({ text: `Temporary statement ${i} used only to test the page layout on small screens.`, subscale: "Total" })),
    });
    instrumentId = inst.data.instrument.id;
    await api("POST", `/teacher/instruments/${instrumentId}/status`, tlogin.data.token, { status: "published" });
    const quizzes = await api("GET", "/quizzes", reg.data.token);
    const quiz = quizzes.data.quizzes.find((q) => q.activity_type === "match_figure") || quizzes.data.quizzes[0];

    for (const [w, h] of VIEWPORTS) {
      // Logged out
      const anon = await browser.newContext({ viewport: { width: w, height: h } });
      const ap = await anon.newPage();
      for (const [name, url] of [["home", "/"], ["login", "/login"], ["signup", "/signup"], ["teacher-login", "/teacher/login"]]) {
        await ap.goto(`${APP}${url}`, { waitUntil: "networkidle" });
        await audit(ap, name, w, h);
      }
      await anon.close();

      // Student
      const sctx = await browser.newContext({ viewport: { width: w, height: h } });
      await sctx.addInitScript((t) => localStorage.setItem("historybot_auth_token", t), reg.data.token);
      const sp = await sctx.newPage();
      const errors = [];
      sp.on("pageerror", (e) => errors.push(String(e)));
      sp.on("console", (m) => {
        if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(`console: ${m.text().slice(0, 160)}`);
      });
      for (const [name, url] of [["quizzes", "/quizzes"], ["activities", "/activities"], ["questionnaires", "/questionnaires"], ["questionnaire-player", `/questionnaires/${instrumentId}`], ["chat", "/chat"]]) {
        await sp.goto(`${APP}${url}`, { waitUntil: "networkidle" });
        await audit(sp, name, w, h);
      }
      if (quiz) {
        // One attempt is reused across viewports so quizzes with an attempt limit still work.
        if (!attemptId) {
          const st = await api("POST", `/quizzes/${quiz.id}/attempts`, reg.data.token);
          attemptId = st.data?.attempt?.id;
        }
        if (!attemptId) throw new Error("could not start an audit attempt");
        await sp.goto(`${APP}/attempts/${attemptId}`, { waitUntil: "networkidle" });
        await sp.getByText(/Question 1 of/).waitFor();
        await audit(sp, "quiz-player", w, h);
        // The quiz column must be centred in the viewport (no app sidebar on this page).
        const centre = await sp.evaluate(() => {
          const el = document.querySelector("[data-testid=quiz-column]");
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return { left: Math.round(r.left), right: Math.round(document.documentElement.clientWidth - r.right) };
        });
        check(`[${w}x${h}] quiz-player column is centred`, Boolean(centre) && Math.abs(centre.left - centre.right) <= 2, JSON.stringify(centre));
      }
      // Chat: a long unbroken word must wrap and the composer must not cover the last message.
      await sp.goto(`${APP}/chat`, { waitUntil: "networkidle" });
      const box = sp.getByRole("textbox").first();
      await box.fill(`Who was Akbar ${"Abcdefghij".repeat(14)} and why does this very long question matter for the layout?`);
      await box.press("Enter");
      await sp.waitForFunction(() => document.querySelectorAll("article").length >= 2, null, { timeout: 20000 }).catch(() => {});
      await sp.waitForTimeout(800);
      const chat = await sp.evaluate(() => {
        const arts = [...document.querySelectorAll("article")];
        const wide = arts.filter((a) => [...a.querySelectorAll("*")].some((c) => c.scrollWidth > c.clientWidth + 2 && getComputedStyle(c).overflowX === "visible" && c.clientWidth > 0 && c.getBoundingClientRect().right > a.getBoundingClientRect().right + 2));
        const form = document.querySelector("form");
        const last = arts[arts.length - 1];
        const scroller = last ? last.closest(".overflow-y-auto") : null;
        if (scroller) scroller.scrollTop = scroller.scrollHeight;
        const lr = last ? last.getBoundingClientRect() : null;
        const fr = form ? form.getBoundingClientRect() : null;
        return { n: arts.length, overflowing: wide.length, lastBottom: lr && Math.round(lr.bottom), composerTop: fr && Math.round(fr.top), pageOverflow: document.documentElement.scrollWidth > window.innerWidth + 1 };
      });
      await sp.screenshot({ path: path.join(OUT, `chat-long-${w}.png`) });
      check(`[${w}x${h}] chat: long message wraps, no horizontal scroll`, chat.n >= 1 && chat.overflowing === 0 && !chat.pageOverflow, JSON.stringify(chat));
      check(`[${w}x${h}] chat: composer does not cover the last message`, chat.lastBottom != null && chat.composerTop != null && chat.lastBottom <= chat.composerTop + 1, JSON.stringify(chat));
      check(`[${w}x${h}] student pages have no script errors`, errors.length === 0, errors.join(" | "));
      await sctx.close();

      // Teacher dashboard: every tab
      const tctx = await browser.newContext({ viewport: { width: w, height: h } });
      await tctx.addInitScript((t) => localStorage.setItem("historybot_auth_token", t), tlogin.data.token);
      const tp = await tctx.newPage();
      const terrors = [];
      tp.on("pageerror", (e) => terrors.push(String(e)));
      tp.on("console", (m) => {
        if (m.type() === "error" && !/Failed to load resource/.test(m.text())) terrors.push(`console: ${m.text().slice(0, 160)}`);
      });
      for (const tab of ["overview", "students", "topics", "achievement", "quizzes", "questions", "research", "reports"]) {
        await tp.goto(`${APP}/admin?tab=${tab}`, { waitUntil: "networkidle" });
        await audit(tp, `dashboard-${tab}`, w, h);
        if (tab === "overview") {
          const chart = await tp.evaluate(() => {
            const days = [...document.querySelectorAll("[data-testid=trend-day]")];
            const withData = days.filter((d) => Number(d.dataset.total) > 0);
            const drawn = withData.filter((d) => [...d.children].some((b) => b.getBoundingClientRect().height > 0.5));
            return { days: days.length, withData: withData.length, drawn: drawn.length, empty: Boolean(document.body.innerText.match(/No chat questions, quiz attempts or module activity/)) };
          });
          check(`[${w}x${h}] overview: activity chart draws every day that has data`, (chart.days > 0 && chart.withData === chart.drawn) || chart.empty, JSON.stringify(chart));
        }
      }
      // Forms open inside tabs
      await tp.goto(`${APP}/admin?tab=quizzes`, { waitUntil: "networkidle" });
      await tp.getByRole("button", { name: "New quiz" }).click();
      await audit(tp, "dashboard-quiz-form", w, h);
      await tp.goto(`${APP}/admin?tab=research`, { waitUntil: "networkidle" });
      await tp.getByRole("button", { name: "New questionnaire" }).click();
      await audit(tp, "dashboard-questionnaire-form", w, h);
      check(`[${w}x${h}] dashboard has no script errors`, terrors.length === 0, terrors.join(" | "));
      await tctx.close();
    }
  } finally {
    await browser.close();
    if (instrumentId) await db.query("DELETE FROM research_instruments WHERE id = ?", [instrumentId]);
    if (users.length) {
      await db.query("DELETE FROM quizzes WHERE owner_user_id IN (?)", [users]);
      await db.query("DELETE FROM anonymous_sessions WHERE user_id IN (?)", [users]);
      await db.query("DELETE FROM users WHERE id IN (?)", [users]);
    }
    await db.end();
  }
  fs.writeFileSync(path.join(OUT, "findings.txt"), findings.join("\n") + "\n");
  console.log(`ui_audit ${pass}/${pass + fail} PASS`);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

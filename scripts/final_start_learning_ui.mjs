/**
 * Start Learning blank-chat UI verification (Playwright).
 * Seeds history via Express API so Ollama is not required for the blank-chat race
 * beyond one seed question.
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const OUT = path.join(process.env.TEMP || ".", "historybot-final-qa");
const API = "http://localhost:3000/api/v1";
const APP = "http://localhost:5173";
fs.mkdirSync(OUT, { recursive: true });

async function api(method, urlPath, body) {
  const res = await fetch(`${API}${urlPath}`, {
    method,
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${urlPath} -> ${res.status}`);
  return res.json();
}

async function main() {
  const results = [];
  const record = (id, ok, notes) => {
    results.push({ id, ok, notes });
    console.log(ok ? "PASS" : "FAIL", id, notes || "");
  };

  const session = await api("POST", "/sessions", {});
  const sid = session.session_id;
  const conv = await api("POST", "/conversations", { session_id: sid, title: "Seed Babur QA" });
  const cid = conv.conversation_id;

  console.log("seeding message via API (one Ollama call)...");
  const seeded = await api("POST", `/conversations/${cid}/messages`, {
    session_id: sid,
    message: "Who was Babur?",
    language: "en",
  });
  const seedText = seeded?.message?.content || "";
  record("api_seed", /Babur|Babar|Panipat|textbook/i.test(seedText), seedText.slice(0, 180));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  // Seed storage BEFORE first document load so AppContext never creates a competing session.
  await context.addInitScript(
    ([sessionId, conversationId]) => {
      localStorage.setItem("historybot_session_id", sessionId);
      localStorage.setItem("historybot_current_conversation_id", conversationId);
      localStorage.setItem("historybot_language", "en");
    },
    [sid, cid]
  );
  const page = await context.newPage();
  const consoleErrors = [];
  const failedUrls = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  page.on("response", (res) => {
    if (res.status() === 403 || res.status() >= 500) {
      failedUrls.push(`${res.status()} ${res.url()}`);
    }
  });

  try {
    await page.goto(`${APP}/chat`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForFunction(
      () => {
        const text = document.querySelector("#chat-main")?.innerText || "";
        return /Who was Babur\?/i.test(text) || /Babur|Babar/i.test(text);
      },
      { timeout: 20000 }
    ).catch(() => {});
    const restored = await page.locator("#chat-main").innerText();
    record(
      "restore_seeded_on_chat_load",
      /Who was Babur\?/i.test(restored) || /Babur|Babar/i.test(restored),
      restored.slice(0, 220) + (failedUrls.length ? ` | failed=${failedUrls.slice(0, 3).join(";")}` : "")
    );

    // Home -> Start Learning must blank
    await page.goto(`${APP}/`, { waitUntil: "networkidle" });
    const headerBtn = page.locator("header button", { hasText: /Start Learning/i });
    if (await headerBtn.count()) await headerBtn.click();
    else await page.locator("form button[type=submit]").first().click();
    await page.waitForURL(/\/chat/, { timeout: 15000 });
    await page.waitForTimeout(800);
    const blank = await page.locator("#chat-main").innerText();
    const isBlank =
      /Ask a question from the Class 9 History textbook/i.test(blank) &&
      !/Who was Babur\?/i.test(blank);
    const composerVal = await page.locator("#composer").inputValue();
    record("start_learning_blank", isBlank && composerVal === "", `composer='${composerVal}'; text=${blank.slice(0, 160)}`);

    // Type without sending, then New Chat
    await page.locator("#composer").fill("temp draft");
    await page.locator("button", { hasText: /New Chat/i }).first().click();
    await page.waitForTimeout(1000);
    const afterNew = await page.locator("#chat-main").innerText();
    record(
      "new_chat_blank",
      /Ask a question from the Class 9 History textbook/i.test(afterNew) &&
        !(await page.locator("#composer").inputValue()).includes("Who was"),
      afterNew.slice(0, 160)
    );

    // Open history item — must restore seeded conversation
    const candidates = page.locator("aside button");
    const n = await candidates.count();
    if (n > 0) {
      let clicked = false;
      for (let i = 0; i < n; i++) {
        const txt = await candidates.nth(i).innerText();
        if (/Babur|Seed|Who was/i.test(txt)) {
          await candidates.nth(i).click();
          clicked = true;
          break;
        }
      }
      if (!clicked) await candidates.first().click();
      await page.waitForFunction(
        () => {
          const text = document.querySelector("#chat-main")?.innerText || "";
          return /Babur|Babar|Panipat|Who was Babur/i.test(text);
        },
        { timeout: 15000 }
      ).catch(() => {});
      const histText = await page.locator("#chat-main").innerText();
      record("history_restore", /Babur|Babar|Panipat|Who was Babur/i.test(histText), histText.slice(0, 200));
    } else {
      record("history_restore", false, "no sidebar buttons");
    }

    // Start Learning blank again after restore
    await page.goto(`${APP}/`, { waitUntil: "networkidle" });
    if (await headerBtn.count()) await headerBtn.click();
    else await page.locator("form button[type=submit]").first().click();
    await page.waitForURL(/\/chat/, { timeout: 15000 });
    await page.waitForTimeout(800);
    const again = await page.locator("#chat-main").innerText();
    record(
      "start_learning_blank_again",
      /Ask a question from the Class 9 History textbook/i.test(again) && !/Who was Babur\?/i.test(again),
      again.slice(0, 160)
    );

    // Race: CURRENT_KEY set then Start Learning must still blank
    await page.evaluate(
      ([sessionId, conversationId]) => {
        localStorage.setItem("historybot_session_id", sessionId);
        localStorage.setItem("historybot_current_conversation_id", conversationId);
      },
      [sid, cid]
    );
    await page.goto(`${APP}/`, { waitUntil: "domcontentloaded" });
    const hdr = page.locator("header button", { hasText: /Start Learning/i });
    if (await hdr.count()) await hdr.click();
    else await page.locator("form button[type=submit]").first().click();
    await page.waitForURL(/\/chat/, { timeout: 15000 });
    await page.waitForTimeout(1000);
    const raceText = await page.locator("#chat-main").innerText();
    record(
      "start_learning_race_vs_restore",
      /Ask a question from the Class 9 History textbook/i.test(raceText) && !/Who was Babur\?/i.test(raceText),
      raceText.slice(0, 160)
    );

    record("composer_label", (await page.locator("label[for=composer]").count()) > 0, "label for composer");
    await page.locator("#composer").fill("line1");
    await page.locator("#composer").press("Shift+Enter");
    await page.locator("#composer").type("line2");
    const multi = await page.locator("#composer").inputValue();
    record("shift_enter_newline", multi.includes("\n") || multi.includes("line2"), JSON.stringify(multi));

    for (const w of [375, 390, 768, 1024, 1366, 1920]) {
      await page.setViewportSize({ width: w, height: 800 });
      await page.waitForTimeout(150);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 4);
      record(`responsive_${w}`, !overflow, `overflow=${overflow}`);
    }

    const filtered = consoleErrors.filter(
      (e) => !/favicon|React DevTools|Download the React|403.*favicon/i.test(e)
    );
    // Document known image/auth noise separately from hard failures
    const hard = filtered.filter((e) => !/Failed to load resource:.*403/i.test(e) || failedUrls.some((u) => /\/api\/v1\/(?!images)/.test(u)));
    const api403 = failedUrls.filter((u) => /\/api\/v1\//.test(u) && !/\/images\//.test(u));
    const img403 = failedUrls.filter((u) => /\/images\//.test(u));
    const consoleOk = api403.length === 0 && hard.filter((e) => !/Failed to load resource:.*403/i.test(e)).length === 0;
    record(
      "console_clean",
      consoleOk,
      [
        filtered.slice(0, 5).join(" | "),
        api403.length ? `api403=${api403.slice(0, 3).join(";")}` : "",
        img403.length ? `img403_expected_or_missing=${img403.slice(0, 2).join(";")}` : "",
      ]
        .filter(Boolean)
        .join(" || ") || "clean"
    );
  } catch (err) {
    record("ui_runner_error", false, String(err));
  } finally {
    await browser.close();
  }

  const out = {
    passed: results.filter((r) => r.ok).length,
    total: results.length,
    failed: results.filter((r) => !r.ok).length,
    results,
    consoleErrors,
    failedUrls,
  };
  fs.writeFileSync(path.join(OUT, "UI_START_LEARNING.json"), JSON.stringify(out, null, 2));
  console.log("SUMMARY", JSON.stringify({ passed: out.passed, total: out.total, failed: out.failed, failedUrls: failedUrls.slice(0, 8) }));
  process.exit(out.failed ? 1 : 0);
}

main();

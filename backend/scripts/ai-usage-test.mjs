// Persistent daily AI limit test. Run against a TEST backend started with
//   PORT=3100 AI_DAILY_LIMIT=2 RAG_INTERNAL_URL=http://127.0.0.1:8199 (nothing listening -> no AI call)
// Phases: node ai-usage-test.mjs run | after-restart | cleanup
// Only rows created by this test are deleted.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });
const { pool } = await import("../src/db/pool.js");
const { countAiRequest, usageDay } = await import("../src/services/aiUsage.js");

const base = process.env.HISTORYBOT_TEST_API || "http://127.0.0.1:3100/api/v1";
if (/:3000\b/.test(base)) throw new Error("Refusing to run against the main backend on :3000.");
const stateFile = path.join(root, "tmp", "final-dev", "ai-usage-test-state.json");
const phase = process.argv[2] || "run";
let failures = 0;

function check(name, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` - ${detail}` : ""}`);
}

async function api(method, pathname, body, token) {
  const response = await fetch(`${base}${pathname}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, data: await response.json().catch(() => ({})) };
}

async function usageCount(userId) {
  const [rows] = await pool.query("SELECT request_count FROM ai_usage WHERE user_id = ? AND usage_day = ?", [
    userId,
    usageDay(),
  ]);
  return rows.length ? Number(rows[0].request_count) : 0;
}

async function ask(state) {
  return api(
    "POST",
    `/conversations/${state.conversationId}/messages`,
    { session_id: state.sessionId, message: "Who was Akbar?" },
    state.token
  );
}

async function run() {
  const stamp = Date.now();
  const email = `final.aiusage.${stamp}@example.com`;
  const reg = await api("POST", "/auth/register", { display_name: "AI Usage Test", email, password: `Usage-${stamp}-Test` });
  check("register temp user", reg.status === 201, `status=${reg.status}`);
  const state = { userId: reg.data.user?.id, token: reg.data.token, sessionId: reg.data.session_id };
  fs.writeFileSync(stateFile, JSON.stringify(state));
  const conv = await api("POST", "/conversations", { session_id: state.sessionId }, state.token);
  state.conversationId = conv.data.conversation_id;
  fs.writeFileSync(stateFile, JSON.stringify(state));
  check("create conversation", conv.status === 201, `status=${conv.status}`);

  const first = await ask(state);
  check("1st request reaches the handler (RAG down -> error, not 429)", first.status !== 429, `status=${first.status}`);
  const second = await ask(state);
  check("2nd request reaches the handler", second.status !== 429, `status=${second.status}`);
  check("failed AI calls are still counted", (await usageCount(state.userId)) === 2, `count=${await usageCount(state.userId)}`);
  const third = await ask(state);
  check("3rd request is refused with 429 (limit 2)", third.status === 429, `status=${third.status}`);
  check("429 uses RATE_LIMITED code", third.data?.error?.code === "RATE_LIMITED");

  // Atomic increments under concurrency, straight against the service.
  const before = await usageCount(state.userId);
  const results = await Promise.all(Array.from({ length: 10 }, () => countAiRequest(state.userId)));
  const counts = results.map((r) => r.count).sort((a, b) => a - b);
  const expected = Array.from({ length: 10 }, (_, i) => before + 1 + i);
  check("10 concurrent increments are atomic and distinct", JSON.stringify(counts) === JSON.stringify(expected), `counts=${counts.join(",")}`);
  check("usageDay is YYYY-MM-DD", /^\d{4}-\d{2}-\d{2}$/.test(usageDay()));
}

async function afterRestart() {
  const state = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  const again = await ask(state);
  check("after backend restart the limit still applies (429)", again.status === 429, `status=${again.status}`);
}

async function cleanup() {
  if (!fs.existsSync(stateFile)) {
    console.log("no state file; nothing to clean");
    return;
  }
  const state = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  if (state.userId) {
    const [sess] = await pool.query("SELECT id FROM anonymous_sessions WHERE user_id = ?", [state.userId]);
    const ids = sess.map((row) => row.id);
    const counts = {};
    if (ids.length) {
      const [convs] = await pool.query("SELECT id FROM conversations WHERE session_id IN (?)", [ids]);
      const convIds = convs.map((row) => row.id);
      if (convIds.length) {
        [{ affectedRows: counts.messages }] = await pool.query("DELETE FROM messages WHERE conversation_id IN (?)", [convIds]);
      }
      [{ affectedRows: counts.analytics_events }] = await pool.query("DELETE FROM analytics_events WHERE session_id IN (?)", [ids]);
      [{ affectedRows: counts.conversations }] = await pool.query("DELETE FROM conversations WHERE session_id IN (?)", [ids]);
    }
    [{ affectedRows: counts.ai_usage }] = await pool.query("DELETE FROM ai_usage WHERE user_id = ?", [state.userId]);
    [{ affectedRows: counts.auth_sessions }] = await pool.query("DELETE FROM auth_sessions WHERE user_id = ?", [state.userId]);
    [{ affectedRows: counts.anonymous_sessions }] = await pool.query("DELETE FROM anonymous_sessions WHERE user_id = ?", [state.userId]);
    [{ affectedRows: counts.users }] = await pool.query("DELETE FROM users WHERE id = ?", [state.userId]);
    console.log("cleanup", JSON.stringify(counts));
  }
  fs.rmSync(stateFile, { force: true });
  const [left] = await pool.query("SELECT COUNT(*) AS n FROM users");
  console.log("users remaining", left[0].n);
}

try {
  if (phase === "run") await run();
  else if (phase === "after-restart") await afterRestart();
  else if (phase === "cleanup") await cleanup();
  else throw new Error(`unknown phase ${phase}`);
} finally {
  await pool.end();
}
console.log(`ai-usage-test ${phase} failures=${failures}`);
process.exit(failures ? 1 : 0);

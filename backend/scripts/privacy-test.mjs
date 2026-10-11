// Privacy and auth edge-case checks against a TEST backend (never the live :3000 one).
// Creates its own accounts and rows and deletes only those. No AI calls are made:
// every chat/module request here is rejected before the RAG service is reached.
// Usage: HISTORYBOT_TEST_API=http://127.0.0.1:3100/api/v1 node backend/scripts/privacy-test.mjs
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const base = process.env.HISTORYBOT_TEST_API || "";
if (!base || /:3000\b/.test(base)) {
  console.error("Set HISTORYBOT_TEST_API to a test backend (not :3000).");
  process.exit(2);
}
const { pool } = await import("../src/db/pool.js");
const { newId } = await import("../src/utils/ids.js");

const results = [];
const createdUserIds = [];

function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail && !ok ? ` — ${detail}` : ""}`);
}

async function api(pathname, { token, method = "GET", body, raw } = {}) {
  const response = await fetch(`${base}${pathname}`, {
    method,
    headers: {
      Accept: "application/json",
      ...(body !== undefined || raw !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: raw !== undefined ? raw : body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data = {};
  try {
    data = JSON.parse(text);
  } catch {
    data = { _raw: text.slice(0, 200) };
  }
  return { status: response.status, data, text, headers: response.headers };
}

async function register(label, stamp) {
  const email = `privacy.${label}.${stamp}@example.com`;
  const password = `Privacy-${stamp}-${label}`;
  const res = await api("/auth/register", { method: "POST", body: { display_name: `Privacy ${label}`, email, password } });
  if (res.data.user?.id) createdUserIds.push(res.data.user.id);
  return { email, password, token: res.data.token, session: res.data.session_id, user: res.data.user, status: res.status, text: res.text };
}

async function run() {
  const stamp = Date.now();
  const a = await register("a", stamp);
  const b = await register("b", stamp);
  check("two test students registered", a.status === 201 && b.status === 201);
  check("register response has no password or token hash", !/password_hash|token_hash|scrypt\$/.test(a.text));

  const me = await api("/auth/me", { token: a.token });
  check("/auth/me returns only public fields",
    me.status === 200 && Object.keys(me.data.user || {}).sort().join(",") === "display_name,email,id,role", JSON.stringify(Object.keys(me.data.user || {})));

  const dup = await api("/auth/register", { method: "POST", body: { display_name: "Dup", email: a.email.toUpperCase(), password: a.password } });
  check("duplicate email (different case) is rejected with 409", dup.status === 409, dup.status);
  const caseLogin = await api("/auth/login", { method: "POST", body: { email: a.email.toUpperCase(), password: a.password } });
  check("login is case-insensitive for email", caseLogin.status === 200);
  const extraField = await api("/auth/login", { method: "POST", body: { email: a.email, password: a.password, role: "admin" } });
  check("login rejects unexpected fields", extraField.status === 400);
  const unknownLogin = await api("/auth/login", { method: "POST", body: { email: `nobody.${stamp}@example.com`, password: "whatever-123" } });
  check("unknown email gets the same 401 message as a wrong password",
    unknownLogin.status === 401 && unknownLogin.data.error?.message === "Email or password is incorrect.");

  const garbage = await api("/auth/me", { token: "x".repeat(43) });
  check("garbage bearer token is rejected", garbage.status === 401);

  // A's conversation and an e-content row owned by A (rows created only for this test).
  const conv = await api("/conversations", { method: "POST", token: a.token, body: { session_id: a.session, title: "privacy" } });
  check("A creates a conversation", conv.status === 201);
  const convId = conv.data.conversation_id;
  const econtentId = newId();
  await pool.query(
    `INSERT INTO econtent_documents (id, session_id, conversation_id, topic, language, body_json, source_pages)
     VALUES (?, ?, NULL, 'privacy test', 'en', ?, '[]')`,
    [econtentId, a.session, JSON.stringify({ title: "privacy test", content: {} })]
  );

  const ownRead = await api(`/conversations/${convId}?session_id=${a.session}`, { token: a.token });
  check("A can read A's conversation", ownRead.status === 200);
  const bWithOwnSession = await api(`/conversations/${convId}?session_id=${b.session}`, { token: b.token });
  check("B cannot read A's conversation via B's session", bWithOwnSession.status === 403);
  const bWithASession = await api(`/conversations/${convId}?session_id=${a.session}`, { token: b.token });
  check("B cannot read A's conversation via A's session id", bWithASession.status === 403);
  const bPosts = await api(`/conversations/${convId}/messages`, {
    method: "POST", token: b.token, body: { session_id: a.session, message: "Who was Akbar?", language: "en" },
  });
  check("B cannot post into A's conversation", bPosts.status === 403);
  const bModuleInA = await api("/econtent", {
    method: "POST", token: b.token, body: { session_id: a.session, topic: "Akbar", language: "en" },
  });
  check("B cannot create a module in A's session", bModuleInA.status === 403);
  const bEcontent = await api(`/econtent/${econtentId}?session_id=${b.session}`, { token: b.token });
  check("B cannot read A's learning module", bEcontent.status === 403);
  const bPdf = await api(`/econtent/${econtentId}/pdf`, { method: "POST", token: b.token, body: { session_id: b.session } });
  check("B cannot download A's module PDF", bPdf.status === 403);
  const aEcontent = await api(`/econtent/${econtentId}?session_id=${a.session}`, { token: a.token });
  check("A can read A's learning module", aEcontent.status === 200 && aEcontent.data.id === econtentId);

  const badId = await api(`/econtent/not-a-uuid?session_id=${a.session}`, { token: a.token });
  check("malformed module id gives 400, not 500", badId.status === 400, badId.status);
  const badSession = await api("/conversations?session_id=not-a-uuid", { token: a.token });
  check("malformed session id gives 400", badSession.status === 400);
  const badJson = await api("/auth/login", { method: "POST", raw: "{not json" });
  check("malformed JSON gives 400", badJson.status === 400 && badJson.data.error?.code === "INVALID_JSON");
  const big = await api("/auth/login", { method: "POST", raw: JSON.stringify({ email: "a@b.co", password: "x".repeat(40000) }) });
  check("oversized body gives 413, not 500", big.status === 413, big.status);
  const tooLongMsg = await api(`/conversations/${convId}/messages`, {
    method: "POST", token: a.token, raw: JSON.stringify({ session_id: a.session, message: "x".repeat(5000), language: "en" }),
  });
  check("over-long chat message rejected before any AI call", tooLongMsg.status === 400, tooLongMsg.status);
  const notFound = await api("/does-not-exist");
  check("unknown route gives JSON 404", notFound.status === 404 && notFound.data.error?.code === "NOT_FOUND");
  const health = await api("/health");
  check("health exposes no secrets", health.status === 200 && !/secret|password|key/i.test(health.text));
  check("security headers set (helmet, no x-powered-by)",
    Boolean(health.headers.get("x-content-type-options")) && !health.headers.get("x-powered-by"));

  // Expired token: shorten B's own token row only.
  await pool.query("UPDATE auth_sessions SET expires_at = DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 1 MINUTE) WHERE user_id = ?", [b.user.id]);
  const expired = await api("/auth/me", { token: b.token });
  check("expired token is rejected", expired.status === 401);
  const [left] = await pool.query("SELECT COUNT(*) AS n FROM auth_sessions WHERE user_id = ?", [b.user.id]);
  check("expired token row is removed", Number(left[0].n) === 0);

  const out = await api("/auth/logout", { method: "POST", token: a.token, body: {} });
  const after = await api(`/conversations?session_id=${a.session}`, { token: a.token });
  check("after logout the old token cannot read history", out.status === 200 && after.status === 401);
}

async function cleanup() {
  if (!createdUserIds.length) return;
  const marks = createdUserIds.map(() => "?").join(",");
  // anonymous_sessions cascade to conversations, messages, econtent_documents, analytics_events.
  await pool.query(`DELETE FROM anonymous_sessions WHERE user_id IN (${marks})`, createdUserIds);
  await pool.query(`DELETE FROM users WHERE id IN (${marks})`, createdUserIds);
  const [rest] = await pool.query(`SELECT COUNT(*) AS n FROM users WHERE id IN (${marks})`, createdUserIds);
  console.log(`cleanup test_users_remaining=${rest[0].n}`);
}

try {
  await run();
} catch (err) {
  check("privacy test run completed", false, err.message || String(err));
} finally {
  try {
    await cleanup();
  } catch (err) {
    console.log(`CLEANUP_FAIL ${err.message || err}`);
  }
  await pool.end();
}
const failed = results.filter((r) => !r.ok).length;
console.log(`privacy_test ${results.length - failed}/${results.length} PASS`);
process.exitCode = failed ? 1 : 0;

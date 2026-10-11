// Learning module + PDF flow for a student and a teacher (admin) account, end to end over HTTP.
// Run against a TEST backend whose RAG uses the local test provider (never paid calls):
//   HISTORYBOT_TEST_API=http://127.0.0.1:3100/api/v1 node backend/scripts/module-flow-test.mjs
// Creates throwaway accounts and deletes only the rows it created.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const { hashPassword } = await import("../src/services/passwords.js");
const { pool } = await import("../src/db/pool.js");
const { newId } = await import("../src/utils/ids.js");

const base = process.env.HISTORYBOT_TEST_API || "http://127.0.0.1:3100/api/v1";
const topic = process.env.HISTORYBOT_MODULE_TOPIC || "Akbar";
const outDir = path.join(root, "tmp", "final-dev");
const results = [];
const createdUserIds = [];
const createdSessionIds = [];

function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

async function api(pathname, options = {}) {
  const response = await fetch(`${base}${pathname}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return { status: response.status, data: await response.json(), type };
  return { status: response.status, buffer: Buffer.from(await response.arrayBuffer()), type };
}

async function login(email, password) {
  const res = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  if (res.data?.session_id) createdSessionIds.push(res.data.session_id);
  return res;
}

async function moduleFlow(role, token, sessionId) {
  const auth = { Authorization: `Bearer ${token}` };
  const t0 = Date.now();
  const made = await api("/econtent", {
    method: "POST",
    headers: auth,
    body: JSON.stringify({ session_id: sessionId, topic, language: "en" }),
  });
  const secs = Math.round((Date.now() - t0) / 1000);
  const doc = made.data || {};
  check(`${role}: module generated (${secs}s)`, made.status === 201 && doc.grounded === true && Boolean(doc.id), `status ${made.status}`);
  if (made.status !== 201 || !doc.id) return null;
  const c = doc.content || {};
  const mcqs = Array.isArray(c.mcqs) ? c.mcqs : [];
  check(`${role}: MCQs with answers`, mcqs.length > 0 && mcqs.every((m) => m && (m.answer || m.correct || m.correct_option)), `${mcqs.length} MCQs`);
  const exam = Array.isArray(c.exam_questions) ? c.exam_questions : [];
  check(`${role}: exam questions with answers`, exam.length > 0 && exam.every((q) => q && q.answer), `${exam.length} questions`);
  check(`${role}: revision notes or key points`, Boolean(c.revision) || (Array.isArray(c.key_points) && c.key_points.length > 0));
  const pages = (doc.sources || []).map((s) => s.printed_page_number ?? s.textbook_page_number).filter((p) => p != null);
  check(`${role}: genuine textbook citations`, pages.length > 0, `pages ${pages.join(",")}`);
  check(`${role}: labelled additional explanation (never cited)`, typeof c.additional_explanation === "string" && c.additional_explanation.length > 50 && !/\bpage\s*\d+/i.test(c.additional_explanation), c.additional_explanation ? `${c.additional_explanation.split(/\s+/).length} words` : "missing");
  const images = doc.images || [];
  const raw = JSON.stringify(images);
  check(`${role}: images have caption, alt text and credit`, images.length > 0 && images.every((i) => i.title && i.alt && (i.source || i.license)), `${images.length} images`);
  check(`${role}: no file paths or localhost in image data`, !/data\/images|[A-Z]:\\|localhost|127\.0\.0\.1|file_path/i.test(raw));
  if (images[0]) {
    const img = await fetch(`${base}/images/${images[0].id}`, { headers: auth });
    const anon = await fetch(`${base}/images/${images[0].id}`);
    check(`${role}: image served to the owner, not anonymously`, img.status === 200 && /^image\//.test(img.headers.get("content-type") || "") && anon.status === 401, `${img.status}/${anon.status}`);
  }
  const again = await api(`/econtent/${doc.id}?session_id=${sessionId}`, { headers: auth });
  check(`${role}: module can be reopened`, again.status === 200 && again.data?.id === doc.id);
  const pdf = await api(`/econtent/${doc.id}/pdf`, { method: "POST", headers: auth, body: JSON.stringify({ session_id: sessionId }) });
  const ok = pdf.status === 200 && /application\/pdf/.test(pdf.type) && pdf.buffer?.subarray(0, 4).toString() === "%PDF";
  check(`${role}: PDF downloads`, ok, `${pdf.status} ${pdf.buffer ? pdf.buffer.length : 0} bytes`);
  if (ok) fs.writeFileSync(path.join(outDir, `module-${role}.pdf`), pdf.buffer);
  return { id: doc.id, sessionId };
}

async function run() {
  const anon = await api("/econtent", { method: "POST", body: JSON.stringify({ session_id: newId(), topic }) });
  check("Module needs login", anon.status === 401);
  const stamp = Date.now();
  const password = `Mf-${stamp}-x9!`;
  const studentEmail = `module.student.${stamp}@example.com`;
  const reg = await api("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email: studentEmail, password, display_name: "Module Student" }),
  });
  if (reg.data?.user?.id) createdUserIds.push(reg.data.user.id);
  if (reg.data?.session_id) createdSessionIds.push(reg.data.session_id);
  check("Student registered as a student", reg.status === 201 && reg.data?.user?.role === "student");
  const s = await login(studentEmail, password);
  const teacherId = newId();
  const teacherEmail = `module.teacher.${stamp}@example.com`;
  await pool.query(
    "INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?, ?, ?, ?, 'admin')",
    [teacherId, teacherEmail, "Module Teacher", await hashPassword(password)]
  );
  createdUserIds.push(teacherId);
  const t = await login(teacherEmail, password);
  check("Teacher login", t.status === 200 && t.data?.user?.role === "admin");
  const studentDoc = await moduleFlow("student", s.data.token, s.data.session_id);
  await moduleFlow("teacher", t.data.token, t.data.session_id);
  if (studentDoc) {
    const stolen = await api(`/econtent/${studentDoc.id}?session_id=${t.data.session_id}`, {
      headers: { Authorization: `Bearer ${t.data.token}` },
    });
    check("Another account cannot open the student's module", stolen.status === 403 || stolen.status === 404, `${stolen.status}`);
  }
}

async function cleanup() {
  if (createdSessionIds.length) {
    const marks = createdSessionIds.map(() => "?").join(",");
    await pool.query(`DELETE FROM anonymous_sessions WHERE id IN (${marks})`, createdSessionIds);
  }
  if (!createdUserIds.length) return;
  const marks = createdUserIds.map(() => "?").join(",");
  await pool.query(`DELETE FROM auth_sessions WHERE user_id IN (${marks})`, createdUserIds);
  await pool.query(`DELETE FROM anonymous_sessions WHERE user_id IN (${marks})`, createdUserIds);
  await pool.query(`DELETE FROM ai_usage WHERE user_id IN (${marks})`, createdUserIds).catch(() => {});
  await pool.query(`DELETE FROM users WHERE id IN (${marks})`, createdUserIds);
}

try {
  await run();
} catch (err) {
  check("Test run completed", false, err.message || String(err));
} finally {
  try {
    await cleanup();
    console.log("CLEANUP_OK");
  } catch (err) {
    console.log(`CLEANUP_FAIL ${err.message || err}`);
  }
  await pool.end();
}
const passed = results.filter((r) => r.ok).length;
console.log(`module_flow ${passed}/${results.length} PASS`);
process.exit(passed === results.length ? 0 : 1);

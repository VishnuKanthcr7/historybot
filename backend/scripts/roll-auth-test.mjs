// Email-free student accounts (roll number + password) and the new teacher reports, against the
// ISOLATED test backend on :3100 (whose MYSQL_DATABASE must be a test copy). No AI calls.
// Every record it creates is removed at the end.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
require("dotenv").config({ path: path.join(root, ".env") });
const { pool } = await import("../src/db/pool.js");
const { hashPassword } = await import("../src/services/passwords.js");
const { newId } = await import("../src/utils/ids.js");

const base = process.env.HISTORYBOT_TEST_API || "http://127.0.0.1:3100/api/v1";
if (!/127\.0\.0\.1:3100/.test(base)) { console.log("FAIL refusing: not the :3100 test backend"); process.exit(2); }
if (!/test/i.test(process.env.MYSQL_DATABASE || "")) { console.log("FAIL refusing: MYSQL_DATABASE must be a test copy"); process.exit(2); }
const cohort = process.env.STUDENT_COHORT || "class9-default";
let pass = 0, fail = 0;
const check = (n, ok, d = "") => { ok ? pass++ : fail++; console.log(`${ok ? "PASS" : "FAIL"} ${n}${d ? ` :: ${typeof d === "string" ? d : JSON.stringify(d)}` : ""}`); };
async function api(method, p, { body, token, raw } = {}) {
  const r = await fetch(base + p, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (raw) return { status: r.status, type: r.headers.get("content-type") || "", buf: Buffer.from(await r.arrayBuffer()) };
  return { status: r.status, data: await r.json().catch(() => ({})) };
}
const created = [];
// pick free roll numbers in the test cohort
const [taken] = await pool.query("SELECT roll_number FROM users WHERE cohort_code = ?", [cohort]);
const used = new Set(taken.map((r) => r.roll_number));
const free = []; for (let i = 1; i <= 99 && free.length < 2; i++) { const r = String(i).padStart(2, "0"); if (!used.has(r)) free.push(r); }
const [R1, R2] = free;
const pw = `Roll-${Date.now()}-pw`;
try {
  const before = await pool.query("SELECT COUNT(*) n FROM users").then(([[x]]) => Number(x.n));
  const reg = await api("POST", "/auth/register", { body: { display_name: "  Roll   Test Student ", roll_number: R1, password: pw, confirm_password: pw } });
  check("register with name + roll + password (no email)", reg.status === 201, reg.status);
  if (reg.data.user) created.push(reg.data.user.id);
  check("roll number keeps leading zero", reg.data.user?.roll_number === R1 && R1.startsWith("0"), reg.data.user?.roll_number);
  check("no email stored", reg.data.user?.email === null);
  check("name whitespace normalised", reg.data.user?.display_name === "Roll Test Student", reg.data.user?.display_name);
  const [[row]] = await pool.query("SELECT email, roll_number, cohort_code, password_hash FROM users WHERE id = ?", [reg.data.user?.id]);
  check("DB row: roll text, cohort set, hashed password", row && row.roll_number === R1 && row.cohort_code === cohort && row.password_hash !== pw && row.password_hash.length > 30);
  const dup = await api("POST", "/auth/register", { body: { display_name: "Other", roll_number: R1, password: pw, confirm_password: pw } });
  check("duplicate roll in cohort rejected (409)", dup.status === 409 && dup.data.error?.code === "ROLL_IN_USE", dup.status);
  for (const bad of ["7", "00", "100", "ab", "7a", ""]) {
    const r = await api("POST", "/auth/register", { body: { display_name: "Bad Roll", roll_number: bad, password: pw, confirm_password: pw } });
    check(`roll "${bad}" rejected with simple message`, r.status === 400 && /two digits/i.test(r.data.error?.message || ""), r.data.error?.message);
  }
  const mm = await api("POST", "/auth/register", { body: { display_name: "Mismatch", roll_number: R2, password: pw, confirm_password: pw + "x" } });
  check("password mismatch rejected", mm.status === 400 && /not the same/i.test(mm.data.error?.message || ""), mm.data.error?.message);
  const sh = await api("POST", "/auth/register", { body: { display_name: "Short", roll_number: R2, password: "short", confirm_password: "short" } });
  check("short password rejected", sh.status === 400 && /8 characters/.test(sh.data.error?.message || ""), sh.data.error?.message);
  const nm = await api("POST", "/auth/register", { body: { display_name: " ", roll_number: R2, password: pw, confirm_password: pw } });
  check("missing name rejected", nm.status === 400 && /full name/i.test(nm.data.error?.message || ""));
  const role = await api("POST", "/auth/register", { body: { display_name: "X", roll_number: R2, password: pw, confirm_password: pw, role: "admin" } });
  check("role field rejected", role.status === 400);
  const phone = await api("POST", "/auth/register", { body: { display_name: "Phone", roll_number: R2, password: pw, confirm_password: pw, phone: "123" } });
  check("unknown fields (phone) rejected", phone.status === 400);
  const li = await api("POST", "/auth/login", { body: { roll_number: R1, password: pw } });
  check("login by roll + password", li.status === 200 && li.data.user?.roll_number === R1, li.status);
  const wrong = await api("POST", "/auth/login", { body: { roll_number: R1, password: pw + "x" } });
  check("wrong password -> 401 friendly", wrong.status === 401 && /roll number or password/i.test(wrong.data.error?.message || ""));
  const nobody = await api("POST", "/auth/login", { body: { roll_number: R2, password: pw } });
  check("unregistered roll -> 401 (same message)", nobody.status === 401 && nobody.data.error?.message === wrong.data.error?.message);
  const both = await api("POST", "/auth/login", { body: { roll_number: R1, email: "a@example.com", password: pw } });
  check("login with both roll and email rejected", both.status === 400);
  const me = await api("GET", "/auth/me", { token: li.data.token });
  check("/auth/me returns roll, no email", me.status === 200 && me.data.user?.roll_number === R1 && me.data.user?.email === null);
  // Older email accounts still log in (legacy row inserted directly, like existing students).
  const legacyId = newId(); const legacyEmail = `roll.legacy.${Date.now()}@example.com`;
  await pool.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'student')", [legacyId, legacyEmail, "Legacy Email Student", await hashPassword(pw)]);
  created.push(legacyId);
  const le = await api("POST", "/auth/login", { body: { email: legacyEmail, password: pw } });
  check("existing email student can still log in", le.status === 200 && le.data.user?.email === legacyEmail);
  // Teacher (temporary test admin) and reports
  const tId = newId(); const tEmail = `roll.teacher.${Date.now()}@example.com`;
  await pool.query("INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?,?,?,?, 'admin')", [tId, tEmail, "Roll Test Teacher", await hashPassword(pw)]);
  created.push(tId);
  const T = (await api("POST", "/auth/login", { body: { email: tEmail, password: pw } })).data.token;
  check("teacher email login unchanged", Boolean(T));
  const S = li.data.token;
  const sid = reg.data.user.id;
  await api("POST", "/auth/login", { body: { roll_number: R1, password: pw } }); // a second sign-in event
  const list = await api("GET", `/teacher/analytics/students?search=${R1}`, { token: T });
  check("teacher student search by roll", list.status === 200 && list.data.students.some((s) => s.id === sid && s.roll_number === R1), list.data.total);
  const tl = await api("GET", `/teacher/analytics/students/${sid}/timeline`, { token: T });
  check("timeline lists registration and log-ins in order", tl.status === 200 && tl.data.items[0]?.type === "USER_REGISTERED" && tl.data.items.filter((i) => i.type === "USER_SIGNED_IN").length >= 2, tl.data.items?.map((i) => i.type));
  check("timeline has no chat text field", tl.data.items.every((i) => i.type !== "QUESTION_ASKED" || i.detail === ""));
  check("student cannot read timeline (403)", (await api("GET", `/teacher/analytics/students/${sid}/timeline`, { token: S })).status === 403);
  check("anonymous cannot read timeline (401)", (await api("GET", `/teacher/analytics/students/${sid}/timeline`)).status === 401);
  check("timeline for teacher id -> 404", (await api("GET", `/teacher/analytics/students/${tId}/timeline`, { token: T })).status === 404);
  check("timeline bad id -> 400", (await api("GET", `/teacher/analytics/students/not-a-uuid/timeline`, { token: T })).status === 400);
  const today = new Date(Date.now() + 330 * 60000).toISOString().slice(0, 10);
  for (const kind of ["research_summary", "students", "class_activity", "attempts", "progress", "topics", "prepost"]) {
    const c = await api("GET", `/teacher/reports/${kind}.csv?from=${today}&to=${today}`, { token: T, raw: true });
    check(`${kind}.csv 200 text/csv`, c.status === 200 && c.type.includes("text/csv"), c.status);
    const p = await api("GET", `/teacher/reports/${kind}.pdf?from=${today}&to=${today}`, { token: T, raw: true });
    check(`${kind}.pdf 200 is a PDF`, p.status === 200 && p.buf.slice(0, 5).toString() === "%PDF-", p.status);
    check(`${kind}.pdf forbidden for student`, (await api("GET", `/teacher/reports/${kind}.pdf?from=${today}&to=${today}`, { token: S, raw: true })).status === 403);
  }
  const tcsv = await api("GET", `/teacher/reports/timeline.csv?from=${today}&to=${today}&user_id=${sid}`, { token: T, raw: true });
  const ttext = tcsv.buf.toString("utf8");
  check("timeline.csv pseudonymous by default, has roll + log-ins", tcsv.status === 200 && !ttext.includes("Roll Test Student") && ttext.includes(`,${R1},`) && /Logged in/.test(ttext));
  const named = (await api("GET", `/teacher/reports/timeline.csv?from=${today}&to=${today}&user_id=${sid}&include_names=1`, { token: T, raw: true })).buf.toString("utf8");
  check("timeline.csv includes name only when asked", named.includes("Roll Test Student"));
  const scsv = (await api("GET", `/teacher/reports/students.csv?from=${today}&to=${today}`, { token: T, raw: true })).buf.toString("utf8");
  check("students.csv has roll_number column, no emails", scsv.split("\n")[0].includes("roll_number") && !/@example\.com/.test(scsv));
  const rs = (await api("GET", `/teacher/reports/research_summary.csv?from=${today}&to=${today}`, { token: T, raw: true })).buf.toString("utf8");
  check("research summary states tracking start and what is not tracked", /tracking began/i.test(rs) && /Not tracked/.test(rs));
  check("timeline.csv bad user -> 400/404", [400, 404].includes((await api("GET", `/teacher/reports/timeline.csv?user_id=${tId}`, { token: T, raw: true })).status));
  const after = await pool.query("SELECT COUNT(*) n FROM users").then(([[x]]) => Number(x.n));
  check("only test users were added", after - before === created.length, `${after - before} vs ${created.length}`);
} finally {
  for (const id of created) {
    await pool.query("DELETE FROM analytics_events WHERE user_id = ? OR session_id IN (SELECT id FROM anonymous_sessions WHERE user_id = ?)", [id, id]);
    await pool.query("DELETE FROM anonymous_sessions WHERE user_id = ?", [id]);
    await pool.query("DELETE FROM users WHERE id = ?", [id]);
  }
  await pool.end();
}
console.log(`roll-auth ${pass}/${pass + fail}`);
process.exit(fail ? 1 : 0);

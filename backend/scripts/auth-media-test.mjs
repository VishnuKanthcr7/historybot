import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const { imageMatchesTopic, findVerifiedImages } = await import("../src/services/images.js");
const { hashPassword } = await import("../src/services/passwords.js");
const { pool } = await import("../src/db/pool.js");
const { newId } = await import("../src/utils/ids.js");

const base = process.env.HISTORYBOT_TEST_API || "http://127.0.0.1:3000/api/v1";
const results = [];
const createdUserIds = [];
const createdSessionIds = [];

function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
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
  const data = await response.json().catch(() => ({}));
  return { status: response.status, data };
}

function unitMedia() {
  const akbar = { topic: "Akbar", person_name: "Akbar", media_kind: "image" };
  const gif = { topic: "Akbar", person_name: "Akbar", media_kind: "gif" };
  const unrelatedGif = { topic: "Unrelated dance", person_name: null, media_kind: "gif" };
  const panch = { topic: "Panch Mahal", person_name: null, media_kind: "image" };
  check("Akbar image matches an Akbar question", imageMatchesTopic("Who was Akbar?", "Akbar was emperor.", akbar));
  check(
    "Humayun question does not take the Akbar image",
    !imageMatchesTopic("Who was Humayun?", "Humayun was Akbar's father.", akbar)
  );
  check(
    "Sher Shah question does not take the Akbar image",
    !imageMatchesTopic("Who was Sher Shah Suri?", "Sher Shah defeated Humayun.", akbar)
  );
  check(
    "Taj Mahal does not match the Panch Mahal figure",
    !imageMatchesTopic("What is the Taj Mahal?", "The Taj Mahal is in Agra.", panch)
  );
  check(
    "Panch Mahal matches its own figure",
    imageMatchesTopic("Describe the Panch Mahal", "Panch Mahal is at Fatehpur Sikri.", panch)
  );
  check("A relevant GIF can match Akbar", imageMatchesTopic("Who was Akbar?", "Akbar", gif));
  check(
    "An unrelated GIF does not match",
    !imageMatchesTopic("Explain the Mansabdari system.", "Mansabdari ranked officials.", unrelatedGif)
  );
  // Future assets: a person outside the built-in list is matched by person_name.
  const future = { topic: "Tipu Sultan", person_name: "Tipu Sultan", media_kind: "image" };
  const futureGif = { topic: "Kittur Chennamma", person_name: "Kittur Chennamma", media_kind: "gif" };
  check("Future asset matches a question naming that person", imageMatchesTopic("Who was Tipu Sultan?", "Tipu Sultan ruled Mysore.", future));
  check("Future asset is not shown for an Akbar question", !imageMatchesTopic("Who was Akbar?", "Akbar was emperor.", future));
  check("Future GIF matches its own person", imageMatchesTopic("Tell me about Kittur Chennamma", "", futureGif));
  check("Future GIF is not shown for another person", !imageMatchesTopic("Who was Shivaji?", "Shivaji", futureGif));
}

async function databaseMedia() {
  const akbar = await findVerifiedImages("Who was Akbar?", "Akbar expanded the empire.", [
    { textbook_page_number: 4 },
  ]);
  check(
    "Approved Akbar figure is available",
    akbar.some((row) => /akbar/i.test(`${row.topic} ${row.person_name || ""}`)),
    `count=${akbar.length}`
  );
  const humayun = await findVerifiedImages(
    "Who was Humayun?",
    "Humayun was defeated and Akbar later became emperor.",
    [{ textbook_page_number: 4 }]
  );
  check(
    "Humayun does not borrow an Akbar image",
    humayun.every((row) => !/akbar/i.test(`${row.topic} ${row.person_name || ""} ${row.caption || ""}`)),
    humayun.map((row) => row.topic).join(" | ")
  );
  const sher = await findVerifiedImages("Who was Sher Shah Suri?", "Sher Shah Suri defeated Humayun.", [
    { textbook_page_number: 4 },
  ]);
  check("Sher Shah has no approved image", sher.length === 0);
  const taj = await findVerifiedImages("What is the Taj Mahal?", "The Taj Mahal is a marble monument.", [
    { textbook_page_number: 6 },
  ]);
  check("Taj Mahal does not show the Panch Mahal figure", taj.length === 0);
  const shivaji = await findVerifiedImages("Who was Shivaji?", "Shivaji established Maratha power.", [
    { textbook_page_number: 11 },
  ]);
  check(
    "Shivaji uses the approved Maratha textbook figure",
    shivaji.some((row) => /shivaji|maratha/i.test(`${row.topic} ${row.person_name || ""}`)),
    `count=${shivaji.length}`
  );
  const [gifRows] = await pool.query(
    "SELECT COUNT(*) AS n FROM verified_images WHERE media_kind = 'gif' AND verification_status = 'verified'"
  );
  check("No unrelated GIF is stored for display", Number(gifRows[0].n) === 0, `gif_rows=${gifRows[0].n}`);
}

async function httpAccess() {
  const anonSession = await api("/sessions", { method: "POST", body: "{}" });
  const anonConversation = await api("/conversations", {
    method: "POST",
    body: JSON.stringify({
      session_id: "11111111-1111-4111-8111-111111111111",
      title: "Anonymous check",
    }),
  });
  const anonHistory = await api("/conversations?session_id=11111111-1111-4111-8111-111111111111");
  const anonMessage = await api("/conversations/11111111-1111-4111-8111-111111111111/messages", {
    method: "POST",
    body: JSON.stringify({
      session_id: "11111111-1111-4111-8111-111111111111",
      message: "Who was Akbar?",
      language: "en",
    }),
  });
  const anonModule = await api("/econtent", {
    method: "POST",
    body: JSON.stringify({
      session_id: "11111111-1111-4111-8111-111111111111",
      topic: "Akbar",
      language: "en",
    }),
  });
  const anonPdf = await api("/econtent/11111111-1111-4111-8111-111111111111/pdf", {
    method: "POST",
    body: JSON.stringify({ session_id: "11111111-1111-4111-8111-111111111111" }),
  });
  check("Unauthenticated session creation is rejected", anonSession.status === 401);
  check("Unauthenticated conversation creation is rejected", anonConversation.status === 401);
  check("Unauthenticated history is rejected", anonHistory.status === 401);
  check("Unauthenticated chat message is rejected", anonMessage.status === 401);
  check("Unauthenticated learning module is rejected", anonModule.status === 401);
  check("Unauthenticated PDF download is rejected", anonPdf.status === 401);

  const stamp = Date.now();
  const studentEmail = `student.${stamp}@example.com`;
  const adminEmail = `teacher.${stamp}@example.com`;
  const password = `HistoryBot-${stamp}-Test`;
  const registered = await api("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      display_name: "Test Student",
      email: studentEmail,
      password,
    }),
  });
  check("Student registration", registered.status === 201 && registered.data.user?.role === "student");
  if (registered.data.user?.id) createdUserIds.push(registered.data.user.id);

  const rejectedAdmin = await api("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      display_name: "Not Admin",
      email: `other.${stamp}@example.com`,
      password,
      role: "admin",
    }),
  });
  check("Public admin registration is rejected", rejectedAdmin.status === 400);

  const badLogin = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: studentEmail, password: "wrong-password" }),
  });
  check("Invalid login is rejected", badLogin.status === 401);

  const studentToken = registered.data.token;
  const studentSession = registered.data.session_id;
  const denied = await api("/admin/summary", {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  check("Student is denied the admin API", denied.status === 403);

  const adminId = newId();
  await pool.query(
    `INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?, ?, ?, ?, 'admin')`,
    [adminId, adminEmail, "Test Teacher", await hashPassword(password)]
  );
  createdUserIds.push(adminId);
  const adminLogin = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: adminEmail, password }),
  });
  check("Admin login", adminLogin.status === 200 && adminLogin.data.user?.role === "admin");
  const adminToken = adminLogin.data.token;
  const adminSession = adminLogin.data.session_id;
  const summary = await api("/admin/summary", {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  check("Admin can open the dashboard API", summary.status === 200 && summary.data.title === "Teacher dashboard");

  const studentList = await api(`/conversations?session_id=${studentSession}`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  const adminList = await api(`/conversations?session_id=${adminSession}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  check("Student can use their own chat history", studentList.status === 200);
  check("Admin can use their own chat history", adminList.status === 200);
  const crossed = await api(`/conversations?session_id=${adminSession}`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  check("Student cannot open the admin history", crossed.status === 403);
  const teacherReadsStudent = await api(`/conversations?session_id=${studentSession}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  check("Teacher cannot open a student's private history", teacherReadsStudent.status === 403);

  const missing = "11111111-1111-4111-8111-111111111111";
  const studentPdf = await api(`/econtent/${missing}/pdf`, {
    method: "POST",
    headers: { Authorization: `Bearer ${studentToken}` },
    body: JSON.stringify({ session_id: studentSession }),
  });
  const adminPdf = await api(`/econtent/${missing}/pdf`, {
    method: "POST",
    headers: { Authorization: `Bearer ${adminToken}` },
    body: JSON.stringify({ session_id: adminSession }),
  });
  const stolenPdf = await api(`/econtent/${missing}/pdf`, {
    method: "POST",
    headers: { Authorization: `Bearer ${studentToken}` },
    body: JSON.stringify({ session_id: adminSession }),
  });
  check("Student can reach their own PDF route", studentPdf.status === 404);
  check("Admin can reach their own PDF route", adminPdf.status === 404);
  check("Student cannot download another account PDF", stolenPdf.status === 403);

  const [imageRows] = await pool.query(
    "SELECT id FROM verified_images WHERE verification_status = 'verified' ORDER BY textbook_page_number LIMIT 1"
  );
  const imageId = imageRows[0]?.id;
  check("A verified image id is available for access checks", Boolean(imageId));
  if (imageId) {
    const anonImage = await fetch(`${base}/images/${imageId}`);
    const studentImage = await fetch(`${base}/images/${imageId}`, {
      headers: { Authorization: `Bearer ${studentToken}` },
    });
    const teacherImage = await fetch(`${base}/images/${imageId}`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const studentBytes = new Uint8Array(await studentImage.arrayBuffer());
    const teacherBytes = new Uint8Array(await teacherImage.arrayBuffer());
    const imageMagic = (bytes) =>
      bytes.length >= 4 &&
      ((bytes[0] === 0x89 && bytes[1] === 0x50) ||
        (bytes[0] === 0x47 && bytes[1] === 0x49) ||
        (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff));
    check("Unauthenticated image access is rejected", anonImage.status === 401);
    check(
      "Authenticated student can load a textbook image",
      studentImage.status === 200 &&
        String(studentImage.headers.get("content-type") || "").startsWith("image/") &&
        imageMagic(studentBytes)
    );
    check(
      "Authenticated teacher can load a textbook image",
      teacherImage.status === 200 &&
        String(teacherImage.headers.get("content-type") || "").startsWith("image/") &&
        imageMagic(teacherBytes)
    );
  }

  const loggedOut = await api("/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${studentToken}` },
    body: "{}",
  });
  const afterLogout = await api("/auth/me", {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  check("Logout ends the student session", loggedOut.status === 200 && afterLogout.status === 401);
}

async function cleanup() {
  if (createdSessionIds.length) {
    const sessionMarks = createdSessionIds.map(() => "?").join(",");
    await pool.query(`DELETE FROM anonymous_sessions WHERE id IN (${sessionMarks})`, createdSessionIds);
  }
  if (!createdUserIds.length) return;
  const marks = createdUserIds.map(() => "?").join(",");
  await pool.query(`DELETE FROM auth_sessions WHERE user_id IN (${marks})`, createdUserIds);
  await pool.query(`DELETE FROM anonymous_sessions WHERE user_id IN (${marks})`, createdUserIds);
  await pool.query(`DELETE FROM users WHERE id IN (${marks})`, createdUserIds);
}

try {
  unitMedia();
  await databaseMedia();
  await httpAccess();
} catch (err) {
  check("Test run completed", false, err.message || String(err));
} finally {
  try {
    await cleanup();
  } catch (err) {
    console.log(`CLEANUP_FAIL ${err.message || err}`);
  }
  await pool.end();
}

const failed = results.filter((item) => !item.ok);
if (failed.length) process.exitCode = 1;

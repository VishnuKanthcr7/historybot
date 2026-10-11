import { createHash, randomBytes } from "node:crypto";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { newId } from "../utils/ids.js";
import { dummyPasswordHash, hashPassword, verifyPassword } from "./passwords.js";

const TOKEN_DAYS = 14;

export function publicUser(row) {
  return {
    id: row.id,
    email: row.email,
    display_name: row.display_name,
    role: row.role,
  };
}

function tokenHash(token) {
  return createHash("sha256").update(String(token)).digest("hex");
}

export async function createUser({ email, displayName, password, role }) {
  if (role !== "student" && role !== "admin") {
    throw new AppError(400, "VALIDATION_ERROR", "Invalid request.");
  }
  const id = newId();
  const passwordHash = await hashPassword(password);
  try {
    await pool.query(
      `INSERT INTO users (id, email, display_name, password_hash, role)
       VALUES (?, ?, ?, ?, ?)`,
      [id, email, displayName, passwordHash, role]
    );
  } catch (err) {
    if (err?.code === "ER_DUP_ENTRY") {
      throw new AppError(409, "EMAIL_IN_USE", "An account with this email already exists.");
    }
    throw err;
  }
  return { id, email, display_name: displayName, role };
}

export async function authenticate(email, password) {
  const [rows] = await pool.query(
    `SELECT id, email, display_name, password_hash, role FROM users WHERE email = ? LIMIT 1`,
    [email]
  );
  const row = rows[0];
  const stored = row?.password_hash || (await dummyPasswordHash());
  const match = await verifyPassword(password, stored);
  if (!row || !match) return null;
  return publicUser(row);
}

export async function issueToken(userId) {
  const token = randomBytes(32).toString("base64url");
  const id = newId();
  await pool.query(
    `INSERT INTO auth_sessions (id, user_id, token_hash, expires_at)
     VALUES (?, ?, ?, DATE_ADD(UTC_TIMESTAMP(3), INTERVAL ? DAY))`,
    [id, userId, tokenHash(token), TOKEN_DAYS]
  );
  return token;
}

export async function userFromToken(token) {
  if (!token) return null;
  const [rows] = await pool.query(
    `SELECT u.id, u.email, u.display_name, u.role, s.id AS session_row_id, s.expires_at
     FROM auth_sessions s
     JOIN users u ON u.id = s.user_id
     WHERE s.token_hash = ?
     LIMIT 1`,
    [tokenHash(token)]
  );
  const row = rows[0];
  if (!row) return null;
  if (new Date(row.expires_at).getTime() <= Date.now()) {
    await pool.query("DELETE FROM auth_sessions WHERE id = ?", [row.session_row_id]);
    return null;
  }
  return publicUser(row);
}

export async function revokeToken(token) {
  if (!token) return;
  await pool.query("DELETE FROM auth_sessions WHERE token_hash = ?", [tokenHash(token)]);
}

export async function ensureLearningSession(userId) {
  const [existing] = await pool.query(
    `SELECT id FROM anonymous_sessions WHERE user_id = ? ORDER BY last_seen_at DESC LIMIT 1`,
    [userId]
  );
  if (existing.length) {
    await pool.query("UPDATE anonymous_sessions SET last_seen_at = UTC_TIMESTAMP(3) WHERE id = ?", [
      existing[0].id,
    ]);
    return existing[0].id;
  }
  const id = newId();
  await pool.query("INSERT INTO anonymous_sessions (id, user_id) VALUES (?, ?)", [id, userId]);
  return id;
}

export function bearerToken(req) {
  const header = req.get("authorization") || "";
  const match = header.match(/^Bearer\s+([A-Za-z0-9_-]{20,})$/);
  return match ? match[1] : "";
}

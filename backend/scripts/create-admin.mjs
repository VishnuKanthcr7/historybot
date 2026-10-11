import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dotenv = require("dotenv");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
dotenv.config({ path: path.join(root, ".env") });

const { pool } = await import("../src/db/pool.js");
const { hashPassword } = await import("../src/services/passwords.js");
const { newId } = await import("../src/utils/ids.js");

function required(name) {
  const value = process.env[name];
  if (!value || !String(value).trim()) {
    throw new Error(`${name} is required in the environment for this command`);
  }
  return String(value).trim();
}

async function main() {
  const email = required("ADMIN_EMAIL").toLowerCase();
  const displayName = required("ADMIN_DISPLAY_NAME");
  const password = required("ADMIN_PASSWORD");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("ADMIN_EMAIL is not a valid email");
  if (displayName.length > 80) throw new Error("ADMIN_DISPLAY_NAME is too long");
  if (password.length < 8 || password.length > 128) {
    throw new Error("ADMIN_PASSWORD must be 8 to 128 characters");
  }

  const [rows] = await pool.query("SELECT id, role FROM users WHERE email = ? LIMIT 1", [email]);
  if (rows.length && rows[0].role !== "admin" && process.env.ADMIN_ALLOW_PROMOTE !== "1") {
    throw new Error("That email already belongs to a student. Refusing to change it.");
  }
  const passwordHash = await hashPassword(password);
  if (rows.length) {
    if (process.env.ADMIN_RESET_PASSWORD !== "1" && rows[0].role === "admin") {
      console.log("Admin account already exists. Password was not changed.");
      return;
    }
    await pool.query("UPDATE users SET display_name = ?, password_hash = ?, role = 'admin' WHERE id = ?", [
      displayName,
      passwordHash,
      rows[0].id,
    ]);
    const [revoked] = await pool.query("DELETE FROM auth_sessions WHERE user_id = ?", [rows[0].id]);
    console.log("Updated the admin account. The password was not printed.");
    console.log(`Signed out ${revoked.affectedRows} existing login session(s) for this account.`);
    return;
  }
  await pool.query(
    `INSERT INTO users (id, email, display_name, password_hash, role) VALUES (?, ?, ?, ?, 'admin')`,
    [newId(), email, displayName, passwordHash]
  );
  console.log("Created the admin account. The password was not printed.");
}

try {
  await main();
} catch (err) {
  console.error(err.message || "Could not create admin");
  process.exitCode = 1;
} finally {
  await pool.end();
}

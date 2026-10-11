import { randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";

const scrypt = promisify(scryptCb);
const KEY_LEN = 64;

export async function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const hash = (await scrypt(String(password), salt, KEY_LEN)).toString("hex");
  return `scrypt$${salt}$${hash}`;
}

let dummyHashPromise;
export function dummyPasswordHash() {
  if (!dummyHashPromise) dummyHashPromise = hashPassword("not-a-real-password");
  return dummyHashPromise;
}

export async function verifyPassword(password, stored) {
  const parts = String(stored || "").split("$");
  if (parts.length !== 3 || parts[0] !== "scrypt" || !parts[1] || !parts[2]) return false;
  const actual = Buffer.from(parts[2], "hex");
  const next = await scrypt(String(password), parts[1], KEY_LEN);
  if (actual.length !== next.length) return false;
  return timingSafeEqual(actual, next);
}

import dotenv from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../");
dotenv.config({ path: path.join(root, ".env") });

function required(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function parseCorsOrigin(raw) {
  const fallback = ["http://localhost:5173", "http://127.0.0.1:5173"];
  if (!raw || !String(raw).trim()) return fallback;
  const parts = String(raw)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  // Dev convenience: if only one of localhost/127.0.0.1 is listed, allow both.
  const set = new Set(parts);
  if (set.has("http://localhost:5173")) set.add("http://127.0.0.1:5173");
  if (set.has("http://127.0.0.1:5173")) set.add("http://localhost:5173");
  const list = [...set];
  return list.length === 1 ? list[0] : list;
}

export const config = {
  env: process.env.NODE_ENV || "development",
  port: Number(process.env.PORT || process.env.APP_PORT || 3000),
  corsOrigin: parseCorsOrigin(process.env.CORS_ORIGIN),
  mysql: {
    host: process.env.MYSQL_HOST || "localhost",
    port: Number(process.env.MYSQL_PORT || 3306),
    user: required("MYSQL_USER"),
    password: process.env.MYSQL_PASSWORD || "",
    database: process.env.MYSQL_DATABASE || "historybot",
  },
  rag: {
    url: (process.env.RAG_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, ""),
    secret: required("INTERNAL_RAG_SECRET"),
    timeoutMs: Number(process.env.RAG_TIMEOUT_MS || 180000),
    econtentTimeoutMs: Number(process.env.RAG_ECONTENT_TIMEOUT_MS || 900000),
  },
  rateLimit: {
    windowMs: Number(process.env.RATE_LIMIT_WINDOW_MS || 60000),
    max: Number(process.env.RATE_LIMIT_MAX_REQUESTS || 120),
  },
  maxMessageChars: 2000,
};

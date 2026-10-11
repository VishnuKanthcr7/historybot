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
  const fallback = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5176",
    "http://127.0.0.1:5176",
  ];
  if (!raw || !String(raw).trim()) return fallback;
  const parts = String(raw)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const set = new Set(parts);
  for (const origin of parts) {
    let url;
    try {
      url = new URL(origin);
    } catch {
      continue;
    }
    if (url.hostname === "localhost") {
      url.hostname = "127.0.0.1";
      set.add(url.origin);
    } else if (url.hostname === "127.0.0.1") {
      url.hostname = "localhost";
      set.add(url.origin);
    }
  }
  const list = [...set];
  return list.length === 1 ? list[0] : list;
}

function positiveInt(raw, fallback) {
  const value = Number.parseInt(String(raw ?? "").trim(), 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export const config = {
  env: process.env.NODE_ENV || "development",
  port: Number(process.env.PORT || process.env.APP_PORT || 3000),
  corsOrigin: parseCorsOrigin(process.env.FRONTEND_ORIGIN || process.env.CORS_ORIGIN),
  // Number of reverse-proxy hops to trust (0 = none). Only set when deployed behind a proxy.
  trustProxy: Number.parseInt(String(process.env.TRUST_PROXY || "0"), 10) || 0,
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
  aiLimit: {
    burstLimit: positiveInt(process.env.AI_BURST_LIMIT, 20),
    burstWindowMs: positiveInt(process.env.AI_BURST_WINDOW_MIN, 10) * 60 * 1000,
    dailyLimit: positiveInt(process.env.AI_DAILY_LIMIT, 200),
    // The daily AI limit resets at midnight in this time zone.
    dayTimeZone: process.env.AI_DAY_TIMEZONE || "Asia/Kolkata",
  },
  maxMessageChars: 2000,
};

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

export const config = {
  env: process.env.NODE_ENV || "development",
  port: Number(process.env.PORT || process.env.APP_PORT || 3000),
  corsOrigin: process.env.CORS_ORIGIN || "http://localhost:5173",
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
    max: Number(process.env.RATE_LIMIT_MAX_REQUESTS || 30),
  },
  maxMessageChars: 2000,
};

import { createApp } from "./app.js";
import { config } from "./config/env.js";
import { pingDb, pool } from "./db/pool.js";

const app = createApp();

try {
  await pingDb();
} catch {
  console.error("MySQL connection failed");
  process.exit(1);
}

const server = app.listen(config.port, "127.0.0.1", () => {
  console.log(`HistoryBot API listening on 127.0.0.1:${config.port}`);
});

// Learning-module generation may legitimately take up to RAG_ECONTENT_TIMEOUT_MS; Node's
// default 5-minute request timeout would cut it off first, so allow the RAG timeouts plus a margin.
const longestRagMs = Math.max(config.rag.timeoutMs, config.rag.econtentTimeoutMs);
server.requestTimeout = longestRagMs + 30000;
server.headersTimeout = Math.min(server.headersTimeout || 60000, server.requestTimeout);

process.on("unhandledRejection", (reason) => {
  console.error("unhandled_rejection", reason?.code || reason?.name || "Error");
});

let shuttingDown = false;
function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`${signal} received; closing HistoryBot API`);
  server.close(() => {
    pool.end().finally(() => process.exit(0));
  });
  setTimeout(() => process.exit(0), 10000).unref();
}
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

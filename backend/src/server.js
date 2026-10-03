import { createApp } from "./app.js";
import { config } from "./config/env.js";
import { pingDb } from "./db/pool.js";

const app = createApp();

try {
  await pingDb();
} catch {
  console.error("MySQL connection failed");
  process.exit(1);
}

app.listen(config.port, "127.0.0.1", () => {
  console.log(`HistoryBot API listening on 127.0.0.1:${config.port}`);
});

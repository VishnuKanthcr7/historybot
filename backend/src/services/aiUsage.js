import { pool } from "../db/pool.js";
import { config } from "../config/env.js";

// Calendar day for the daily AI limit, in the configured time zone (default Asia/Kolkata).
export function usageDay(now = new Date(), timeZone = config.aiLimit.dayTimeZone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type) => parts.find((part) => part.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

// Count one AI request for this account today and return the new total.
// One atomic statement: concurrent requests cannot read the same count.
// It runs before the AI call, so failed or retried requests are still counted.
export async function countAiRequest(userId, now = new Date()) {
  const day = usageDay(now);
  const [result] = await pool.query(
    `INSERT INTO ai_usage (user_id, usage_day, request_count, updated_at)
     VALUES (?, ?, 1, UTC_TIMESTAMP(3))
     ON DUPLICATE KEY UPDATE
       request_count = LAST_INSERT_ID(request_count + 1),
       updated_at = UTC_TIMESTAMP(3)`,
    [userId, day]
  );
  // affectedRows is 1 for a new row and 2 for an update; insertId carries LAST_INSERT_ID().
  const count = result.affectedRows === 1 ? 1 : Number(result.insertId);
  return { day, count };
}

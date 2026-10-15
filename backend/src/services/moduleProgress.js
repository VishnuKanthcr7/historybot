// Learning-module progress. Definitions (also shown on the dashboard):
//   opened    = the student generated or opened the module (first open recorded once; reopening only bumps open_count)
//   completed = an explicit "Mark complete" OR submitting the module's checkpoint quiz.
//   Opening or downloading the PDF is NOT completion.
import { pool } from "../db/pool.js";
import { recordUserEvent } from "./analytics.js";

export async function markModuleOpened(userId, econtentId) {
  await pool.query(
    `INSERT INTO module_progress (user_id, econtent_id, first_opened_at, last_opened_at, open_count)
     VALUES (?, ?, UTC_TIMESTAMP(3), UTC_TIMESTAMP(3), 1)
     ON DUPLICATE KEY UPDATE last_opened_at = UTC_TIMESTAMP(3), open_count = open_count + 1,
       first_opened_at = COALESCE(first_opened_at, UTC_TIMESTAMP(3))`,
    [userId, econtentId]
  );
  await recordUserEvent(userId, "MODULE_OPENED", { econtent_id: econtentId }, `open:${userId}:${econtentId}`);
}

export async function markModulePdf(userId, econtentId) {
  await pool.query(
    `INSERT INTO module_progress (user_id, econtent_id, pdf_downloads) VALUES (?, ?, 1)
     ON DUPLICATE KEY UPDATE pdf_downloads = pdf_downloads + 1`,
    [userId, econtentId]
  );
}

// Idempotent: the first completion wins; later calls change nothing and record no new event.
export async function markModuleCompleted(userId, econtentId, method, conn = pool) {
  await conn.query(
    `INSERT INTO module_progress (user_id, econtent_id, completed_at, completion_method) VALUES (?, ?, UTC_TIMESTAMP(3), ?)
     ON DUPLICATE KEY UPDATE completion_method = IF(completed_at IS NULL, VALUES(completion_method), completion_method),
       completed_at = COALESCE(completed_at, UTC_TIMESTAMP(3))`,
    [userId, econtentId, method]
  );
  await recordUserEvent(userId, "MODULE_COMPLETED", { econtent_id: econtentId, method }, `done:${userId}:${econtentId}`);
}

export async function moduleProgress(userId, econtentId) {
  const [rows] = await pool.query(
    "SELECT open_count, pdf_downloads, completed_at, completion_method FROM module_progress WHERE user_id = ? AND econtent_id = ?",
    [userId, econtentId]
  );
  const r = rows[0];
  return {
    completed: Boolean(r?.completed_at),
    completed_at: r?.completed_at || null,
    completion_method: r?.completion_method || null,
  };
}

import { z } from "zod";
import { pool } from "../db/pool.js";
import { newId, utcNow } from "../utils/ids.js";
import { recordEvent } from "../services/analytics.js";

const createSchema = z.object({
  language: z.enum(["en", "kn"]).optional(),
});

export async function createSession(req, res, next) {
  try {
    const body = createSchema.parse(req.body || {});
    const id = newId();
    const language = body.language || "en";
    await pool.query(
      "INSERT INTO anonymous_sessions (id, language) VALUES (?, ?)",
      [id, language]
    );
    await recordEvent({
      sessionId: id,
      eventType: "SESSION_STARTED",
      language,
    });
    res.status(201).json({
      session_id: id,
      created_at: utcNow(),
    });
  } catch (err) {
    next(err);
  }
}

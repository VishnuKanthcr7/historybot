// Research questionnaires (instruments). Students answer published, open instruments; teachers build,
// approve and publish them and see descriptive results. Placeholder shells can never be published.
import { z } from "zod";
import { pool } from "../db/pool.js";
import { AppError } from "../utils/errors.js";
import { newId } from "../utils/ids.js";
import { requireUuid } from "../services/quizData.js";
import { recordUserEvent } from "../services/analytics.js";
import { mean, median } from "../services/quizScoring.js";
import { pairedT } from "../services/stats.js";
import { PLACEHOLDER_TAG, publishProblem, scoreQuestionnaire, validValue } from "../services/questionnaireScoring.js";

function parseJson(value, fallback = null) {
  if (value == null) return fallback;
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

const round2 = (x) => (x == null || Number.isNaN(x) ? null : Math.round(x * 100) / 100);
const studentRef = (id) => `S-${String(id).replace(/-/g, "").slice(0, 8)}`;

function isOpen(inst, now = new Date()) {
  if (inst.status !== "published") return false;
  if (inst.available_from && new Date(inst.available_from) > now) return false;
  if (inst.available_until && new Date(inst.available_until) < now) return false;
  return true;
}

async function getInstrument(id, conn = pool) {
  requireUuid(id, "questionnaire id");
  const [rows] = await conn.query("SELECT * FROM research_instruments WHERE id = ?", [id]);
  if (!rows.length) throw new AppError(404, "NOT_FOUND", "Questionnaire not found.");
  return rows[0];
}

async function getItems(instrumentId, conn = pool) {
  const [rows] = await conn.query(
    "SELECT id, position, text, subscale, reverse_scored, requires_approval FROM research_items WHERE instrument_id = ? ORDER BY position",
    [instrumentId]
  );
  return rows.map((r) => ({ ...r, reverse_scored: Boolean(r.reverse_scored), requires_approval: Boolean(r.requires_approval) }));
}

function scaleOf(inst) {
  return { scaleMin: Number(inst.scale_min), scaleMax: Number(inst.scale_max), minRatio: Number(inst.min_answered_ratio) };
}

function publicInstrument(inst) {
  return {
    id: inst.id,
    title: inst.title,
    description: inst.description,
    scale_min: Number(inst.scale_min),
    scale_max: Number(inst.scale_max),
    scale_labels: parseJson(inst.scale_labels_json, []),
    available_from: inst.available_from,
    available_until: inst.available_until,
  };
}

// ---------- Students ----------
export async function listQuestionnaires(req, res, next) {
  try {
    const [rows] = await pool.query(
      `SELECT i.*, r.status AS my_status, r.submitted_at AS my_submitted_at,
              (SELECT COUNT(*) FROM research_items t WHERE t.instrument_id = i.id) AS item_count
       FROM research_instruments i LEFT JOIN research_responses r ON r.instrument_id = i.id AND r.user_id = ?
       WHERE i.status = 'published' ORDER BY i.published_at DESC`,
      [req.user.id]
    );
    res.json({
      questionnaires: rows.map((r) => ({
        ...publicInstrument(r),
        item_count: Number(r.item_count),
        open: isOpen(r),
        my_status: r.my_status || "not_started",
        my_submitted_at: r.my_submitted_at,
      })),
    });
  } catch (err) {
    next(err);
  }
}

async function studentInstrument(id, user) {
  const inst = await getInstrument(id);
  // A draft or archived questionnaire looks exactly like a missing one to students.
  if (inst.status !== "published" || user.role !== "student") throw new AppError(404, "NOT_FOUND", "Questionnaire not found.");
  return inst;
}

export async function getQuestionnaire(req, res, next) {
  try {
    const inst = await studentInstrument(req.params.instrumentId, req.user);
    const items = await getItems(inst.id);
    const [resp] = await pool.query("SELECT * FROM research_responses WHERE instrument_id = ? AND user_id = ?", [inst.id, req.user.id]);
    const values = {};
    if (resp.length) {
      const [vals] = await pool.query("SELECT item_id, value FROM research_response_items WHERE response_id = ?", [resp[0].id]);
      for (const v of vals) values[v.item_id] = v.value;
    }
    res.json({
      questionnaire: { ...publicInstrument(inst), open: isOpen(inst) },
      // Students see the item text only: no subscale names or reverse-scoring flags.
      items: items.map((i) => ({ id: i.id, position: i.position, text: i.text })),
      response: { status: resp[0]?.status || "not_started", submitted_at: resp[0]?.submitted_at || null, values },
    });
  } catch (err) {
    next(err);
  }
}

const saveBody = z.object({
  answers: z.record(z.string(), z.union([z.number().int(), z.null()])).default({}),
  submit: z.boolean().default(false),
});

export async function saveQuestionnaire(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const body = saveBody.parse(req.body || {});
    const inst = await studentInstrument(req.params.instrumentId, req.user);
    if (!isOpen(inst)) throw new AppError(409, "CLOSED", "This questionnaire is not open right now.");
    const items = await getItems(inst.id);
    const ids = new Set(items.map((i) => i.id));
    const { scaleMin, scaleMax } = scaleOf(inst);
    for (const [itemId, value] of Object.entries(body.answers)) {
      if (!ids.has(itemId)) throw new AppError(400, "VALIDATION_ERROR", "Unknown questionnaire item.");
      if (value !== null && !validValue(value, scaleMin, scaleMax)) {
        throw new AppError(400, "VALIDATION_ERROR", `Answers must be whole numbers from ${scaleMin} to ${scaleMax}.`);
      }
    }
    await conn.beginTransaction();
    await conn.query(
      `INSERT INTO research_responses (id, instrument_id, user_id) VALUES (?, ?, ?)
       ON DUPLICATE KEY UPDATE id = id`,
      [newId(), inst.id, req.user.id]
    );
    const [[resp]] = await conn.query("SELECT * FROM research_responses WHERE instrument_id = ? AND user_id = ? FOR UPDATE", [
      inst.id,
      req.user.id,
    ]);
    if (resp.status === "submitted") throw new AppError(409, "ALREADY_SUBMITTED", "You have already submitted this questionnaire.");
    for (const [itemId, value] of Object.entries(body.answers)) {
      await conn.query(
        `INSERT INTO research_response_items (response_id, item_id, value) VALUES (?, ?, ?)
         ON DUPLICATE KEY UPDATE value = VALUES(value)`,
        [resp.id, itemId, value]
      );
    }
    if (body.submit) {
      await conn.query("UPDATE research_responses SET status = 'submitted', submitted_at = UTC_TIMESTAMP(3) WHERE id = ?", [resp.id]);
    }
    await conn.commit();
    if (body.submit) {
      await recordUserEvent(req.user.id, "QUESTIONNAIRE_SUBMITTED", { instrument_id: inst.id }, `questionnaire:${resp.id}`);
    }
    res.json({ status: body.submit ? "submitted" : "in_progress", saved_at: new Date().toISOString() });
  } catch (err) {
    try {
      await conn.rollback();
    } catch {
      /* ignore */
    }
    next(err);
  } finally {
    conn.release();
  }
}

// ---------- Teachers ----------
function teacherInstrument(inst, items, extra = {}) {
  return {
    ...publicInstrument(inst),
    construct: inst.construct,
    phase: inst.phase,
    pre_instrument_id: inst.pre_instrument_id,
    min_answered_ratio: Number(inst.min_answered_ratio),
    status: inst.status,
    approval_note: inst.approval_note,
    approved_at: inst.approved_at,
    published_at: inst.published_at,
    is_shell: items ? items.some((i) => i.requires_approval) : undefined,
    validated: false,
    items,
    ...extra,
  };
}

export async function listInstruments(req, res, next) {
  try {
    const [rows] = await pool.query(
      `SELECT i.*, (SELECT COUNT(*) FROM research_items t WHERE t.instrument_id = i.id) AS item_count,
         (SELECT COUNT(*) FROM research_items t WHERE t.instrument_id = i.id AND t.requires_approval = 1) AS placeholder_count,
         (SELECT COUNT(*) FROM research_responses r WHERE r.instrument_id = i.id AND r.status = 'submitted') AS submitted
       FROM research_instruments i ORDER BY i.created_at`
    );
    res.json({
      instruments: rows.map((r) => ({
        ...teacherInstrument(r, null),
        item_count: Number(r.item_count),
        placeholder_count: Number(r.placeholder_count),
        is_shell: Number(r.placeholder_count) > 0,
        submitted: Number(r.submitted),
      })),
      note: "No validated scale is built in. Placeholder shells must be replaced with researcher-approved items before publishing.",
    });
  } catch (err) {
    next(err);
  }
}

export async function getInstrumentTeacher(req, res, next) {
  try {
    const inst = await getInstrument(req.params.instrumentId);
    const [[{ n }]] = await pool.query("SELECT COUNT(*) AS n FROM research_responses WHERE instrument_id = ?", [inst.id]);
    res.json({ instrument: teacherInstrument(inst, await getItems(inst.id), { responses: Number(n) }) });
  } catch (err) {
    next(err);
  }
}

const itemBody = z.object({
  text: z.string().trim().min(3).max(500),
  subscale: z.string().trim().min(1).max(80).default("Total"),
  reverse_scored: z.boolean().default(false),
});

const instrumentBody = z
  .object({
    title: z.string().trim().min(3).max(160),
    construct: z.string().trim().min(2).max(120),
    description: z.string().trim().max(1000).optional().default(""),
    scale_min: z.number().int().min(0).max(9).default(1),
    scale_max: z.number().int().min(1).max(10).default(5),
    scale_labels: z.array(z.string().trim().max(40)).max(11).default([]),
    min_answered_ratio: z.number().min(0.1).max(1).default(0.5),
    phase: z.enum(["none", "pre", "post"]).default("none"),
    pre_instrument_id: z.string().uuid().nullable().optional(),
    available_from: z.string().datetime({ offset: true }).nullable().optional(),
    available_until: z.string().datetime({ offset: true }).nullable().optional(),
    approval_note: z.string().trim().max(500).nullable().optional(),
    items: z.array(itemBody).max(80).optional(),
  })
  .refine((b) => b.scale_max > b.scale_min, { message: "The scale maximum must be above the minimum." })
  .refine((b) => !b.scale_labels.length || b.scale_labels.length === b.scale_max - b.scale_min + 1, {
    message: "Give one label per scale point, or none.",
  })
  .refine((b) => !(b.available_from && b.available_until) || new Date(b.available_until) > new Date(b.available_from), {
    message: "The closing time must be after the opening time.",
  });

async function writeItems(conn, instrumentId, items) {
  await conn.query("DELETE FROM research_items WHERE instrument_id = ?", [instrumentId]);
  let position = 1;
  for (const it of items) {
    await conn.query(
      `INSERT INTO research_items (id, instrument_id, position, text, subscale, reverse_scored, requires_approval) VALUES (?,?,?,?,?,?,?)`,
      [newId(), instrumentId, position, it.text, it.subscale, it.reverse_scored ? 1 : 0, it.text.includes(PLACEHOLDER_TAG) ? 1 : 0]
    );
    position += 1;
  }
}

async function checkPre(b, selfId = null) {
  if (b.phase !== "post") return null;
  if (!b.pre_instrument_id) return null;
  if (b.pre_instrument_id === selfId) throw new AppError(400, "VALIDATION_ERROR", "A questionnaire cannot be its own pre-test.");
  const pre = await getInstrument(b.pre_instrument_id);
  if (pre.phase !== "pre") throw new AppError(400, "VALIDATION_ERROR", "The linked questionnaire must have phase 'pre'.");
  return pre.id;
}

const dt = (v) => (v ? new Date(v) : null);

export async function createInstrument(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const b = instrumentBody.parse(req.body || {});
    const preId = await checkPre(b);
    const id = newId();
    await conn.beginTransaction();
    await conn.query(
      `INSERT INTO research_instruments (id, title, construct, description, scale_min, scale_max, scale_labels_json, min_answered_ratio,
         phase, pre_instrument_id, available_from, available_until, approval_note, status, created_by)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'draft', ?)`,
      [id, b.title, b.construct, b.description, b.scale_min, b.scale_max, JSON.stringify(b.scale_labels), b.min_answered_ratio,
        b.phase, preId, dt(b.available_from), dt(b.available_until), b.approval_note || null, req.user.id]
    );
    await writeItems(conn, id, b.items || []);
    await conn.commit();
    res.status(201).json({ instrument: teacherInstrument(await getInstrument(id), await getItems(id)) });
  } catch (err) {
    try {
      await conn.rollback();
    } catch {
      /* ignore */
    }
    next(err);
  } finally {
    conn.release();
  }
}

export async function updateInstrument(req, res, next) {
  const conn = await pool.getConnection();
  try {
    const inst = await getInstrument(req.params.instrumentId);
    const b = instrumentBody.parse(req.body || {});
    const [[{ n }]] = await conn.query("SELECT COUNT(*) AS n FROM research_responses WHERE instrument_id = ?", [inst.id]);
    const changesStructure =
      b.items !== undefined || b.scale_min !== Number(inst.scale_min) || b.scale_max !== Number(inst.scale_max);
    if (inst.status === "published" && changesStructure) {
      throw new AppError(409, "PUBLISHED", "Archive this questionnaire before changing its items or scale; responses depend on them.");
    }
    if (Number(n) > 0 && changesStructure) {
      throw new AppError(409, "HAS_RESPONSES", "Students have already answered, so the items and scale cannot change.");
    }
    const preId = await checkPre(b, inst.id);
    await conn.beginTransaction();
    await conn.query(
      `UPDATE research_instruments SET title=?, construct=?, description=?, scale_min=?, scale_max=?, scale_labels_json=?,
         min_answered_ratio=?, phase=?, pre_instrument_id=?, available_from=?, available_until=?, approval_note=?, updated_at=UTC_TIMESTAMP(3)
       WHERE id=?`,
      [b.title, b.construct, b.description, b.scale_min, b.scale_max, JSON.stringify(b.scale_labels), b.min_answered_ratio, b.phase,
        preId, dt(b.available_from), dt(b.available_until), b.approval_note || null, inst.id]
    );
    if (b.items !== undefined) await writeItems(conn, inst.id, b.items);
    await conn.commit();
    res.json({ instrument: teacherInstrument(await getInstrument(inst.id), await getItems(inst.id)) });
  } catch (err) {
    try {
      await conn.rollback();
    } catch {
      /* ignore */
    }
    next(err);
  } finally {
    conn.release();
  }
}

const statusBody = z.object({ status: z.enum(["draft", "published", "archived"]) });

export async function setInstrumentStatus(req, res, next) {
  try {
    const inst = await getInstrument(req.params.instrumentId);
    const { status } = statusBody.parse(req.body || {});
    if (status === "published") {
      const problem = publishProblem(inst, await getItems(inst.id));
      if (problem) throw new AppError(400, "VALIDATION_ERROR", problem);
    }
    if (status === "draft" && inst.status !== "draft") {
      const [[{ n }]] = await pool.query("SELECT COUNT(*) AS n FROM research_responses WHERE instrument_id = ?", [inst.id]);
      if (Number(n) > 0) throw new AppError(409, "HAS_RESPONSES", "Students have already answered. Archive it instead.");
    }
    await pool.query(
      `UPDATE research_instruments SET status = ?,
         published_at = IF(? = 'published', COALESCE(published_at, UTC_TIMESTAMP(3)), published_at),
         approved_by = IF(? = 'published', ?, approved_by), approved_at = IF(? = 'published', UTC_TIMESTAMP(3), approved_at),
         updated_at = UTC_TIMESTAMP(3) WHERE id = ?`,
      [status, status, status, req.user.id, status, inst.id]
    );
    res.json({ instrument: teacherInstrument(await getInstrument(inst.id), await getItems(inst.id)) });
  } catch (err) {
    next(err);
  }
}

function describe(values) {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return { n: 0, mean: null, median: null, sd: null, min: null, max: null };
  const m = mean(v);
  const sd = v.length > 1 ? Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / (v.length - 1)) : null;
  return { n: v.length, mean: round2(m), median: round2(median(v)), sd: round2(sd), min: Math.min(...v), max: Math.max(...v) };
}

// Scored submitted responses of one instrument. Range filters submitted_at (IST-inclusive range from analytics).
async function scoredResponses(inst, items, range = null) {
  const [resp] = await pool.query(
    `SELECT r.id, r.user_id, r.submitted_at FROM research_responses r JOIN users u ON u.id = r.user_id AND u.role = 'student'
     WHERE r.instrument_id = ? AND r.status = 'submitted' ${range ? "AND r.submitted_at >= ? AND r.submitted_at < ?" : ""}
     ORDER BY r.submitted_at`,
    range ? [inst.id, range.start, range.end] : [inst.id]
  );
  const out = [];
  for (const r of resp) {
    const [vals] = await pool.query("SELECT item_id, value FROM research_response_items WHERE response_id = ?", [r.id]);
    const values = Object.fromEntries(vals.map((v) => [v.item_id, v.value]));
    out.push({ ...r, values, score: scoreQuestionnaire(items, values, scaleOf(inst)) });
  }
  return out;
}

export async function instrumentResults(req, res, next) {
  try {
    const { parseRange } = await import("./analyticsController.js");
    const range = parseRange(req.query);
    const inst = await getInstrument(req.params.instrumentId);
    const items = await getItems(inst.id);
    const scored = await scoredResponses(inst, items, range);
    const [[started]] = await pool.query(
      `SELECT COUNT(*) AS n FROM research_responses r JOIN users u ON u.id = r.user_id AND u.role = 'student'
       WHERE r.instrument_id = ? AND r.status = 'in_progress'`,
      [inst.id]
    );
    const subscaleNames = [...new Set(items.map((i) => i.subscale))];
    const subscales = subscaleNames.map((name) => {
      const scores = scored.map((r) => r.score.subscales.find((s) => s.subscale === name)?.score ?? null);
      return { subscale: name, ...describe(scores.filter((x) => x != null)), insufficient: scores.filter((x) => x == null).length };
    });
    const itemStats = items.map((it) => {
      const vals = scored.map((r) => r.values[it.id]).filter((x) => x != null);
      return {
        id: it.id, position: it.position, text: it.text, subscale: it.subscale, reverse_scored: it.reverse_scored,
        answered: vals.length, missing: scored.length - vals.length, ...describe(vals.map(Number)),
      };
    });
    let prePost = null;
    if (inst.phase === "post" && inst.pre_instrument_id) {
      const pre = await getInstrument(inst.pre_instrument_id);
      const preScored = await scoredResponses(pre, await getItems(pre.id));
      const preBy = new Map(preScored.map((r) => [r.user_id, r]));
      prePost = subscaleNames.map((name) => {
        const pairs = scored
          .filter((r) => preBy.has(r.user_id))
          .map((r) => ({
            pre: preBy.get(r.user_id).score.subscales.find((s) => s.subscale === name)?.score ?? null,
            post: r.score.subscales.find((s) => s.subscale === name)?.score ?? null,
          }))
          .filter((p) => p.pre != null && p.post != null);
        const avg = (v) => (v.length ? round2(mean(v)) : null);
        return {
          subscale: name,
          paired_n: pairs.length,
          mean_pre: avg(pairs.map((p) => p.pre)),
          mean_post: avg(pairs.map((p) => p.post)),
          mean_gain: avg(pairs.map((p) => p.post - p.pre)),
          paired_t: pairedT(pairs.map((p) => p.post - p.pre)),
        };
      });
      prePost = {
        pre_title: pre.title,
        subscales: prePost,
        unmatched_post: scored.filter((r) => !preBy.has(r.user_id)).map((r) => studentRef(r.user_id)),
        unmatched_pre: preScored.filter((r) => !scored.some((s) => s.user_id === r.user_id)).map((r) => studentRef(r.user_id)),
        note: "Matched students only. Descriptive; not evidence of what caused any change.",
      };
    }
    res.json({
      instrument: teacherInstrument(inst, items),
      range: { from: range.from, to: range.to },
      submitted: scored.length,
      in_progress: Number(started.n),
      subscales,
      items: itemStats,
      pre_post: prePost,
      scoring:
        "Subscale score = mean of answered items after reverse-scoring; reported only when at least " +
        `${Math.round(Number(inst.min_answered_ratio) * 100)}% of that subscale's items were answered. Missing answers are not zero. No cutoffs.`,
      validated: false,
      validity_note: inst.status === "published"
        ? `Items approved by the researcher: ${inst.approval_note || "(no note)"}. Results are descriptive.`
        : "Draft: not yet approved for use.",
    });
  } catch (err) {
    next(err);
  }
}

export async function questionnaireCsv(range, instrumentId) {
  if (!instrumentId) throw new AppError(400, "VALIDATION_ERROR", "Choose a questionnaire.");
  const inst = await getInstrument(String(instrumentId));
  const items = await getItems(inst.id);
  const scored = await scoredResponses(inst, items, range);
  const subscaleNames = [...new Set(items.map((i) => i.subscale))];
  const ist = (d) => (d ? `${new Date(new Date(d).getTime() + 330 * 60 * 1000).toISOString().slice(0, 19).replace("T", " ")} IST` : "");
  const header = [
    "questionnaire", "student_ref", "submitted_at_ist", "answered", "missing",
    ...subscaleNames.map((s) => `subscale:${s}`), ...items.map((i) => `item_${i.position}${i.reverse_scored ? "_R" : ""}`),
  ];
  const rows = scored.map((r) => [
    inst.title, studentRef(r.user_id), ist(r.submitted_at), r.score.answered, r.score.missing,
    ...subscaleNames.map((s) => r.score.subscales.find((x) => x.subscale === s)?.score ?? ""),
    ...items.map((i) => (r.values[i.id] == null ? "" : r.values[i.id])),
  ]);
  return { header, rows };
}

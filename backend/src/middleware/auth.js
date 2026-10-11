import rateLimit from "express-rate-limit";
import { AppError } from "../utils/errors.js";
import { config } from "../config/env.js";
import { bearerToken, userFromToken } from "../services/accounts.js";
import { countAiRequest } from "../services/aiUsage.js";

const DAILY_LIMIT_MESSAGE = "You have reached today's question limit. Please try again tomorrow.";

export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 15,
  standardHeaders: true,
  legacyHeaders: false,
  validate: { xForwardedForHeader: false },
  handler: (_req, res) => {
    res.status(429).json({
      error: { code: "RATE_LIMITED", message: "Too many sign-in attempts. Please wait and try again." },
    });
  },
});

export async function optionalAuth(req, _res, next) {
  try {
    const token = bearerToken(req);
    if (!token) {
      req.user = null;
      next();
      return;
    }
    const user = await userFromToken(token);
    // An expired, revoked, or unknown token is treated as anonymous so public
    // routes (login, register, health) still work. Protected routes reject it
    // below with 401 UNAUTHENTICATED, which tells the browser to clear it.
    req.user = user || null;
    req.authTokenInvalid = !user;
    next();
  } catch (err) {
    next(err);
  }
}

export async function requireAuth(req, _res, next) {
  try {
    if (!req.user) throw new AppError(401, "UNAUTHENTICATED", "Please log in again.");
    next();
  } catch (err) {
    next(err);
  }
}

export async function requireAdmin(req, _res, next) {
  try {
    if (!req.user) throw new AppError(401, "UNAUTHENTICATED", "Please log in again.");
    if (req.user.role !== "admin") {
      throw new AppError(403, "FORBIDDEN", "Admin access required.");
    }
    next();
  } catch (err) {
    next(err);
  }
}

function aiLimitHandler(message) {
  return (_req, res) => {
    res.status(429).json({
      error: { code: "RATE_LIMITED", message },
    });
  };
}

// Per-account limits for routes that call the AI (chat answers, learning modules).
// Keyed by the signed-in user id, so they must run after requireAuth.
// The burst counter lives in memory; the daily counter is stored in MySQL (ai_usage).
export const aiBurstLimiter = rateLimit({
  windowMs: config.aiLimit.burstWindowMs,
  max: config.aiLimit.burstLimit,
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => `user:${req.user.id}`,
  validate: { xForwardedForHeader: false },
  handler: aiLimitHandler(
    "You have asked a lot of questions in a short time. Please wait a few minutes and try again."
  ),
});

// In-memory daily limiter, used only if the ai_usage table is not available yet
// (before node backend/scripts/migrate-ai-usage.mjs has been run).
const memoryDailyLimiter = rateLimit({
  windowMs: 24 * 60 * 60 * 1000,
  max: config.aiLimit.dailyLimit,
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => `user:${req.user.id}`,
  validate: { xForwardedForHeader: false },
  handler: aiLimitHandler(DAILY_LIMIT_MESSAGE),
});

let warnedNoUsageTable = false;

// Persistent per-account daily limit (MySQL ai_usage). Survives backend restarts.
// Counts the attempt before the AI call, so errors and retries cannot get around it.
export async function aiDailyLimiter(req, res, next) {
  const limit = config.aiLimit.dailyLimit;
  let count;
  try {
    ({ count } = await countAiRequest(req.user.id));
  } catch (err) {
    if (err && (err.code === "ER_NO_SUCH_TABLE" || err.errno === 1146)) {
      if (!warnedNoUsageTable) {
        warnedNoUsageTable = true;
        console.warn("ai_usage table missing; using the in-memory daily AI limit. Run backend/scripts/migrate-ai-usage.mjs.");
      }
      return memoryDailyLimiter(req, res, next);
    }
    return next(err);
  }
  res.setHeader("RateLimit-Limit", String(limit));
  res.setHeader("RateLimit-Remaining", String(Math.max(0, limit - count)));
  if (count > limit) {
    return res.status(429).json({ error: { code: "RATE_LIMITED", message: DAILY_LIMIT_MESSAGE } });
  }
  return next();
}

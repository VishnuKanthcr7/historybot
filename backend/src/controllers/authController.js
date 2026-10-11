import { z } from "zod";
import { AppError } from "../utils/errors.js";
import {
  authenticate,
  bearerToken,
  createUser,
  ensureLearningSession,
  issueToken,
  publicUser,
  revokeToken,
} from "../services/accounts.js";

const registerSchema = z
  .object({
    email: z.string().trim().email().max(255),
    password: z.string().min(8).max(128),
    display_name: z.string().trim().min(1).max(80),
  })
  .strict();

const loginSchema = z
  .object({
    email: z.string().trim().email().max(255),
    password: z.string().min(1).max(128),
  })
  .strict();

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

export async function register(req, res, next) {
  try {
    if (req.body && Object.prototype.hasOwnProperty.call(req.body, "role")) {
      throw new AppError(400, "VALIDATION_ERROR", "Invalid request.");
    }
    const body = registerSchema.parse(req.body || {});
    const email = normalizeEmail(body.email);
    const user = await createUser({
      email,
      displayName: body.display_name.trim(),
      password: body.password,
      role: "student",
    });
    const token = await issueToken(user.id);
    const sessionId = await ensureLearningSession(user.id);
    res.status(201).json({
      token,
      user: publicUser(user),
      session_id: sessionId,
    });
  } catch (err) {
    next(err);
  }
}

export async function login(req, res, next) {
  try {
    const body = loginSchema.parse(req.body || {});
    const user = await authenticate(normalizeEmail(body.email), body.password);
    if (!user) {
      throw new AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.");
    }
    const token = await issueToken(user.id);
    const sessionId = await ensureLearningSession(user.id);
    res.json({
      token,
      user,
      session_id: sessionId,
    });
  } catch (err) {
    next(err);
  }
}

export async function logout(req, res, next) {
  try {
    await revokeToken(bearerToken(req));
    res.json({ status: "ok" });
  } catch (err) {
    next(err);
  }
}

export async function me(req, res, next) {
  try {
    const sessionId = await ensureLearningSession(req.user.id);
    res.json({
      user: req.user,
      session_id: sessionId,
    });
  } catch (err) {
    next(err);
  }
}

import { z } from "zod";
import { AppError } from "../utils/errors.js";
import { recordUserEvent } from "../services/analytics.js";
import {
  authenticate,
  bearerToken,
  ROLL_RE,
  createUser,
  authenticateByRoll,
  createStudentByRoll,
  currentCohort,
  ensureLearningSession,
  issueToken,
  publicUser,
  revokeToken,
} from "../services/accounts.js";

// Student sign-up: full name + two-digit roll number + password. No email/phone.
const registerSchema = z
  .object({
    display_name: z.string().trim().min(2).max(80),
    roll_number: z.string().trim().regex(ROLL_RE),
    password: z.string().min(8).max(128),
    confirm_password: z.string().max(128).optional(),
  })
  .strict();

// Login: roll number (students) or email (teachers, and students who signed up with email earlier).
const loginSchema = z
  .object({
    email: z.string().trim().email().max(255).optional(),
    roll_number: z.string().trim().regex(ROLL_RE).optional(),
    password: z.string().min(1).max(128),
  })
  .strict()
  .refine((b) => Boolean(b.email) !== Boolean(b.roll_number));

const legacyRegisterSchema = z
  .object({
    email: z.string().trim().email().max(255),
    password: z.string().min(8).max(128),
    display_name: z.string().trim().min(1).max(80),
  })
  .strict();

const REGISTER_MESSAGES = {
  display_name: "Please type your full name.",
  roll_number: "Roll number must be two digits, from 01 to 99. Example: 07.",
  password: "Password must have at least 8 characters.",
};

function registerError(err) {
  const field = err?.issues?.[0]?.path?.[0];
  return new AppError(400, "VALIDATION_ERROR", REGISTER_MESSAGES[field] || "Please check the form and try again.");
}

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

export async function register(req, res, next) {
  try {
    if (req.body && Object.prototype.hasOwnProperty.call(req.body, "role")) {
      throw new AppError(400, "VALIDATION_ERROR", "Invalid request.");
    }
    // Test-only legacy path: email sign-up stays available to the automated
    // suites when STUDENT_EMAIL_SIGNUP=1 is set on a TEST instance. Never set it in production.
    if (process.env.STUDENT_EMAIL_SIGNUP === "1" && req.body && req.body.email && !req.body.roll_number) {
      const legacy = legacyRegisterSchema.parse(req.body);
      const user = await createUser({
        email: normalizeEmail(legacy.email),
        displayName: legacy.display_name.trim(),
        password: legacy.password,
        role: "student",
      });
      const token = await issueToken(user.id);
      const sessionId = await ensureLearningSession(user.id);
      await recordUserEvent(user.id, "USER_REGISTERED", null, `register:${user.id}`);
      return res.status(201).json({ token, user: publicUser(user), session_id: sessionId });
    }
    const parsed = registerSchema.safeParse(req.body || {});
    if (!parsed.success) throw registerError(parsed.error);
    const body = parsed.data;
    if (body.confirm_password !== undefined && body.confirm_password !== body.password) {
      throw new AppError(400, "VALIDATION_ERROR", "The two passwords are not the same. Please type them again.");
    }
    const user = await createStudentByRoll({
      rollNumber: body.roll_number,
      displayName: body.display_name.replace(/\s+/g, " ").trim(),
      password: body.password,
      cohort: currentCohort(),
    });
    const token = await issueToken(user.id);
    const sessionId = await ensureLearningSession(user.id);
    await recordUserEvent(user.id, "USER_REGISTERED", null, `register:${user.id}`);
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
    const user = body.roll_number
      ? await authenticateByRoll(body.roll_number, currentCohort(), body.password)
      : await authenticate(normalizeEmail(body.email), body.password);
    if (!user) {
      throw new AppError(
        401,
        "INVALID_CREDENTIALS",
        body.roll_number ? "Roll number or password is wrong. Please try again." : "Email or password is incorrect."
      );
    }
    const token = await issueToken(user.id);
    const sessionId = await ensureLearningSession(user.id);
    // A sign-in is recorded as an event; it is not attendance.
    await recordUserEvent(user.id, "USER_SIGNED_IN");
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

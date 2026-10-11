import { Router } from "express";
import { pingDb } from "../db/pool.js";
import { createSession } from "../controllers/sessionsController.js";
import {
  createConversation,
  getConversation,
  listConversations,
  postMessage,
} from "../controllers/conversationsController.js";
import { createEcontent, downloadEcontentPdf, getEcontent } from "../controllers/econtentController.js";
import { getImage } from "../controllers/imagesController.js";
import { login, logout, me, register } from "../controllers/authController.js";
import { adminSummary } from "../controllers/adminController.js";
import {
  aiBurstLimiter,
  aiDailyLimiter,
  authLimiter,
  optionalAuth,
  requireAdmin,
  requireAuth,
} from "../middleware/auth.js";

export const router = Router();

router.use(optionalAuth);

router.get("/health", async (_req, res, next) => {
  try {
    await pingDb();
    res.json({ status: "ok", mysql: "ok" });
  } catch (err) {
    next(err);
  }
});

router.post("/sessions", requireAuth, createSession);
router.post("/conversations", requireAuth, createConversation);
router.get("/conversations", requireAuth, listConversations);
router.get("/conversations/:conversationId", requireAuth, getConversation);
router.post("/conversations/:conversationId/messages", requireAuth, aiBurstLimiter, aiDailyLimiter, postMessage);
router.post("/econtent", requireAuth, aiBurstLimiter, aiDailyLimiter, createEcontent);
router.get("/econtent/:econtentId", requireAuth, getEcontent);
router.post("/econtent/:econtentId/pdf", requireAuth, downloadEcontentPdf);
router.get("/images/:imageId", requireAuth, getImage);
router.post("/auth/register", authLimiter, register);
router.post("/auth/login", authLimiter, login);
router.post("/auth/logout", logout);
router.get("/auth/me", requireAuth, me);
router.get("/admin/summary", requireAdmin, adminSummary);

import { Router } from "express";
import { pingDb } from "../db/pool.js";
import { createSession } from "../controllers/sessionsController.js";
import {
  createConversation,
  getConversation,
  postMessage,
} from "../controllers/conversationsController.js";

export const router = Router();

router.get("/health", async (_req, res, next) => {
  try {
    await pingDb();
    res.json({ status: "ok", mysql: "ok" });
  } catch (err) {
    next(err);
  }
});

router.post("/sessions", createSession);
router.post("/conversations", createConversation);
router.get("/conversations/:conversationId", getConversation);
router.post("/conversations/:conversationId/messages", postMessage);

import { Router } from "express";
import { pingDb } from "../db/pool.js";
import { createSession } from "../controllers/sessionsController.js";
import {
  createConversation,
  getConversation,
  listConversations,
  postMessage,
} from "../controllers/conversationsController.js";
import { completeEcontent, createEcontent, downloadEcontentPdf, getEcontent } from "../controllers/econtentController.js";
import {
  createInstrument,
  getInstrumentTeacher,
  getQuestionnaire,
  instrumentResults,
  listInstruments,
  listQuestionnaires,
  saveQuestionnaire,
  setInstrumentStatus,
  updateInstrument,
} from "../controllers/researchController.js";
import { getImage } from "../controllers/imagesController.js";
import { login, logout, me, register } from "../controllers/authController.js";
import { adminSummary } from "../controllers/adminController.js";
import {
  autosaveAttempt,
  createCheckpoint,
  createRevisionChallenge,
  getAttempt,
  listQuizzes,
  myQuizHistory,
  startAttempt,
  submitAttempt,
} from "../controllers/quizController.js";
import {
  createQuestion,
  createTeacherQuiz,
  draftFromPassage,
  listQuestions,
  listTeacherQuizzes,
  previewTeacherQuiz,
  quizResults,
  searchPassages,
  setQuestionStatus,
  setQuizStatus,
  updateQuestion,
  updateTeacherQuiz,
} from "../controllers/teacherQuizController.js";
import {
  achievement,
  overview,
  reportCsv,
  studentProfile,
  students,
  timeseries,
  topics,
} from "../controllers/analyticsController.js";
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
router.post("/econtent/:econtentId/complete", requireAuth, completeEcontent);
router.get("/images/:imageId", requireAuth, getImage);
router.post("/auth/register", authLimiter, register);
router.post("/auth/login", authLimiter, login);
router.post("/auth/logout", logout);
router.get("/auth/me", requireAuth, me);
router.get("/admin/summary", requireAdmin, adminSummary);

// Students: quizzes and learning activities (server-scored).
router.get("/quizzes", requireAuth, listQuizzes);
router.post("/quizzes/:quizId/attempts", requireAuth, startAttempt);
router.get("/attempts/:attemptId", requireAuth, getAttempt);
router.post("/attempts/:attemptId/autosave", requireAuth, autosaveAttempt);
router.post("/attempts/:attemptId/submit", requireAuth, submitAttempt);
router.get("/me/quiz-history", requireAuth, myQuizHistory);
router.post("/activities/revision", requireAuth, createRevisionChallenge);
router.post("/activities/checkpoint", requireAuth, createCheckpoint);

// Teachers (role admin): question bank, quizzes, analytics and reports.
router.get("/teacher/questions", requireAdmin, listQuestions);
router.post("/teacher/questions", requireAdmin, createQuestion);
router.post("/teacher/questions/draft-from-passage", requireAdmin, draftFromPassage);
router.post("/teacher/questions/:questionId", requireAdmin, updateQuestion);
router.post("/teacher/questions/:questionId/status", requireAdmin, setQuestionStatus);
router.get("/teacher/passages", requireAdmin, searchPassages);
router.get("/teacher/quizzes", requireAdmin, listTeacherQuizzes);
router.post("/teacher/quizzes", requireAdmin, createTeacherQuiz);
router.get("/teacher/quizzes/:quizId", requireAdmin, previewTeacherQuiz);
router.post("/teacher/quizzes/:quizId", requireAdmin, updateTeacherQuiz);
router.post("/teacher/quizzes/:quizId/status", requireAdmin, setQuizStatus);
router.get("/teacher/quizzes/:quizId/results", requireAdmin, quizResults);
router.get("/teacher/analytics/overview", requireAdmin, overview);
router.get("/teacher/analytics/students", requireAdmin, students);
router.get("/teacher/analytics/students/:userId", requireAdmin, studentProfile);
router.get("/teacher/analytics/topics", requireAdmin, topics);
router.get("/teacher/analytics/timeseries", requireAdmin, timeseries);
router.get("/teacher/analytics/achievement", requireAdmin, achievement);
router.get("/teacher/reports/:kind.csv", requireAdmin, reportCsv);

// Research questionnaires: students answer published ones; teachers build, approve, publish and analyse.
router.get("/questionnaires", requireAuth, listQuestionnaires);
router.get("/questionnaires/:instrumentId", requireAuth, getQuestionnaire);
router.post("/questionnaires/:instrumentId/responses", requireAuth, saveQuestionnaire);
router.get("/teacher/instruments", requireAdmin, listInstruments);
router.post("/teacher/instruments", requireAdmin, createInstrument);
router.get("/teacher/instruments/:instrumentId", requireAdmin, getInstrumentTeacher);
router.post("/teacher/instruments/:instrumentId", requireAdmin, updateInstrument);
router.post("/teacher/instruments/:instrumentId/status", requireAdmin, setInstrumentStatus);
router.get("/teacher/instruments/:instrumentId/results", requireAdmin, instrumentResults);

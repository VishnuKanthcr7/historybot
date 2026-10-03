import express from "express";
import cors from "cors";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import { config } from "./config/env.js";
import { router as v1 } from "./routes/v1.js";
import { errorHandler, AppError } from "./utils/errors.js";

export function createApp() {
  const app = express();
  app.disable("x-powered-by");
  app.use(helmet());
  app.use(
    cors({
      origin: config.corsOrigin,
      methods: ["GET", "POST"],
    })
  );
  app.use(express.json({ limit: "32kb" }));
  app.use(
    rateLimit({
      windowMs: config.rateLimit.windowMs,
      max: config.rateLimit.max,
      standardHeaders: true,
      legacyHeaders: false,
      handler: (_req, res) => {
        res.status(429).json({
          error: { code: "RATE_LIMITED", message: "Too many requests." },
        });
      },
    })
  );
  app.use("/api/v1", v1);
  app.use((_req, _res, next) => {
    next(new AppError(404, "NOT_FOUND", "Not found."));
  });
  app.use(errorHandler);
  return app;
}

# Deployment readiness plan

Status at 2026-10-11 (final dev run). Nothing has been committed, pushed or deployed.

## 1. Before going live

1. **Review and commit** the working-tree changes (stage 2, stage 3 and the final run;
   see `docs/final-status-report.md` for the file list). Backups of every original are in
   `final-dev-backup-20261011\` (and the earlier stage backups).
2. **Database**: run `node backend\scripts\migrate-ai-usage.mjs` (already applied on the dev
   machine; idempotent, takes a mysqldump first). Earlier migrations: `migrate-auth.mjs`,
   `scripts/sql/001-004`.
3. **Environment** (`.env`, never committed). Names only:
   - Required: `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`, `INTERNAL_RAG_SECRET` (long random),
     `OPENAI_API_KEY`, `OPENAI_MODEL`.
   - Recommended for clarity: `LLM_PROVIDER=openai` (current file says `ollama`; with a key set
     the service still uses OpenAI, see `docs/llm-provider.md`).
   - Optional: `LLM_FALLBACK_PROVIDER=ollama` only if a local Ollama should answer when OpenAI is down.
   - Never set `HISTORYBOT_LLM_PROVIDER` in production (test-only override).
   - `FRONTEND_ORIGIN` = the public site origin (CORS). `NODE_ENV=production`.
   - `AI_DAILY_LIMIT` (default 200/account/day), `AI_BURST_LIMIT` (20), `AI_BURST_WINDOW_MIN` (10),
     `AI_DAY_TIMEZONE` (Asia/Kolkata).
   - `TRUST_PROXY=1` when behind nginx/a load balancer (else rate limits see one IP for everyone).
   - `RAG_TIMEOUT_MS` (180000), `RAG_ECONTENT_TIMEOUT_MS` (900000); the API server's request
     timeout follows these automatically.
4. **Frontend build**: set `VITE_API_BASE_URL=https://<api host>` at build time
   (`npm run build` in `frontend/`); the default is `http://127.0.0.1:3000`, which only works locally.
   Serve `frontend/dist` with an SPA fallback to `index.html`.
5. **Network**: the API listens on 127.0.0.1 only; put it behind a TLS reverse proxy. Keep the RAG
   service (port 8000) private: it trusts only `X-Internal-Secret` and must not be exposed.
6. **Admin account**: `node backend\scripts\create-admin.mjs` (public sign-up only creates students).

## 2. Restart order (the code changes go live only after restarts)

1. Stop the RAG service (dev machine: PID 51196), then from the project root:
   `python scripts\rag_internal_server.py`. Check the first log line:
   `HistoryBot RAG llm_provider=openai model=<model> reason=OPENAI_API_KEY is configured fallback=none`.
2. Restart the backend (dev machine: node PID 43860): `npm start` in `backend/`.
3. Check `GET /api/v1/health` and one signed-in question.

## 3. Behaviour changes users/operators will notice

- If OpenAI fails, students get "Answer service is unavailable" instead of a silent Ollama answer
  (unless `LLM_FALLBACK_PROVIDER=ollama`). The RAG log shows `HistoryBot RAG query failed: LlmError: ...`.
- The daily AI limit survives restarts (MySQL `ai_usage`) and resets at midnight IST.
- Answers no longer add general-knowledge sentences that the textbook does not support.

## 4. Known limitations

- Kannada questions: no Kannada textbook is indexed (`kannada_corpus_unavailable`), so Kannada
  answers are refusals. Needs the Kannada textbook ingested.
- Local llama3 (test mode) sometimes writes long exam sentences or mixes facts; production uses OpenAI.
- `fact_layer_smoke` (integrity missing=2) and `fact_planner_regression`
  (corpus-successor-father-pronoun) fail identically on the original code (pre-existing).
- No password reset / account deletion flow yet; expired auth sessions are removed on use only.
- Only 4 verified images (textbook pages 3, 4, 6, 11); add more with `docs/adding-images.md`.

## 5. Rollback

Restore files from `final-dev-backup-20261011\<path>` (and stage backups), restart both services.
The `ai_usage` table is additive and can stay (the old code ignores it); the DB dump taken before
the migration is in `tmp\backups\`.

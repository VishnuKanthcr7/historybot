# Starting HistoryBot (Windows laptop, PowerShell)

Repo: `C:\Users\vkant\Projects\historybot`. Secrets live in `.env` (never commit it or print it). Keep llama3 unloaded.

1. **MySQL:** must be running (service), database `historybot`.
2. **RAG service:** `python scripts/rag_internal_server.py` (internal port 8000).
3. **Backend:** `cd backend; npm start` (port 3000). To restart, stop the old `node src/server.js` process first.
4. **Frontend (dev):** `cd frontend; npm run dev` → http://localhost:5173
5. **Public tunnel:** `cloudflared tunnel --url http://localhost:3000`. The URL changes on each restart, so set `VITE_API_BASE_URL` to it and rebuild.
6. **Deploy:** `cd frontend; $env:VITE_API_BASE_URL="<tunnel>/api/v1"; npm run build; netlify deploy --prod --dir dist --site historybot-vsku`

## Migrations (each one dumps the database to `tmp/backups/` first, and can be re-run safely)
`node backend/scripts/migrate-auth.mjs`, `migrate-ai-usage.mjs`, `migrate-quiz.mjs`, then `migrate-006.mjs`. Then run `node backend/scripts/audit-question-bank.mjs --apply --report docs/question-bank-audit.md`.

## Tests (against a TEST backend on :3100 and a test RAG on :8100; never production)
- **Node suites:** set `HISTORYBOT_TEST_API=http://127.0.0.1:3100/api/v1`, then run `node backend/scripts/<suite>.mjs` for quiz-unit-test, research-unit-test, quiz-test, privacy-test, auth-media-test, module-flow-test, smoke-test and e2e-research-flow.
- **Browser checks:** first run `npm run build` with `VITE_API_BASE_URL=http://127.0.0.1:3100` and serve it with `npx vite preview --port 4173`. Then run `node scripts/quiz_ui_check.cjs` and `node scripts/ui_audit.cjs` (5 viewports).
- **Python:** `python scripts/final_unit_tests.py`.
- **Rate limits:** the auth rate limiter is in memory, so restart the test backend between suites if registrations start returning 429.

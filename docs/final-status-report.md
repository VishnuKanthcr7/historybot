# HistoryBot final status report (final dev run, 2026-10-11)

Scope: textbook-grounded Class 9 History tutor (Karnataka State Board), Express API + FastAPI RAG +
MySQL + ChromaDB + React. All work was done on the dev laptop. Nothing was committed (HEAD is still
`2b14666`), pushed or deployed; `.env` was not edited; the main RAG (PID 51196) and main backend
(PID 43860) were not restarted. **OpenAI calls made by any test: 0.**

## 1. Features (as delivered in the working tree)
- Student sign-up/sign-in (scrypt passwords, 14-day bearer tokens), teacher/admin accounts (created only by script), private per-account chat history.
- Textbook-only answers with page citations; refusals for off-textbook topics ("This topic is not available in the textbook."); follow-ups, "explain again/simpler", bullet/point counts, tables, exam answers, misspelt textbook names.
- Learning modules (e-content) with objectives, explanation, people, terms, timeline, events, key points, exam questions, MCQs, revision, and PDF download.
- Verified textbook images (and GIF support) shown only beside answers citing the matching page; served to signed-in users only.
- Per-account AI limits: burst (20/10 min, memory) and daily (200/day, MySQL, resets midnight IST, survives restarts).
- Production LLM: OpenAI. Local Ollama only in explicit test mode.

## 2. Defects fixed in this run (root cause -> fix)
| Defect | Root cause | Fix |
|---|---|---|
| "What is zabti?" refused | every passage cut at 700 chars; "Zabti" sat at char 679+ | focus-aware trimming keeps sentences with the asked term; refusal guard retries once when every key term is in the evidence |
| Shahaji's capture attributed to Shivaji ("He was captured") | model compressed "his father, Shahaji, was captured" | prompt rule + deterministic `_fix_swapped_subjects` restores the passage's subject |
| Stray full stops after headings, bold lines, table rows, bullets; `**` in PDFs | `_strip_callouts` added "." to every line; econtent collapsed newlines; PDF printed raw markdown | structural-line detection, list items keep markers, newline-preserving econtent, PDF renders `#`/`**bold**` lines as headings |
| General-knowledge sentences with textbook citations (jagir, Quit India) | model added outside facts | sentence-level support filter drops unsupported sentences/names/years |
| "akbr", "shershah", "dagh" refused | domain gate; rare 4-letter terms; vector search missed the only "dagh-mahali" chunk | difflib name correction (cutoff 0.85), rare-term rule, lexical rescue of chunks naming a rare asked term |
| Long bullet / exam sentences | model ignores length notes | bullets/exam points over 22 words cut at the first clause break (text only removed) |
| Numbered lists with gaps after a dropped item | filter removed item 2 of 1-5 | renumbering |
| "What is the GDP of India?" answered with unrelated passages (found by the new smoke test; introduced by the zabti refusal guard) | "gdp" (3 letters) was not a key term, so the guard thought the evidence covered the question | guard terms include short distinctive words |
| "Kalinga" answered as "Kalinjar" (introduced by the spelling corrector) | difflib 0.80 cutoff | cutoff 0.85 |
| Answer restated twice ("Explanation: According to the textbook, ...") | small-model repetition | repeated-sentence filter |
| "I still don't understand" sometimes repeated the previous answer verbatim | model ignored "do not repeat" | one retry asking for new short sentences when >=3 prior sentences are repeated |
| Provider: `LLM_PROVIDER=ollama` + key would silently mean OpenAI-with-Ollama-fallback; earlier draft would have switched prod to Ollama | implicit rules | explicit resolution order, test-only override, no silent fallback (section 5) |
| AI daily limit reset on every backend restart | in-memory limiter | MySQL `ai_usage`, atomic upsert, counted before the AI call |
| Oversized JSON body -> 500; malformed module id -> 500-path | missing error mapping/validation | 413 PAYLOAD_TOO_LARGE; 400 for non-UUID ids |
| Learning module: "Shivaji.:" labels, title "Shivaji.", MCQ answer "Dadoji Kondadeo." (not equal to its option), "[Page 13].", "Ashtapradhan: Ashtapradhan:", "Shivaji appointed Shaista Khan" (it was Aurangzeb) | sanitizer added full stops to labels; term meaning kept a "Term:" lead-in; list rows guessed "he" = module subject | label-aware sanitizing, no full stop after citations, lead-in removed, pronouns in list rows resolved only from the textbook sentence before them (else "he" kept) |
| Node would cut learning-module requests at 5 min although RAG allows 15 | default `server.requestTimeout` | timeout follows RAG timeouts; graceful shutdown; RAG failures now logged (type + short message) |
| Chat labels failed WCAG contrast; answers not announced to screen readers; GIFs autoplay for reduced-motion users | brass 10-11px text; no live region | navy labels, "Answer ready" live region, GIFs behind "Show animation" when reduced motion is set |
| Old smoke test used anonymous sessions and the live :3000 (paid calls) | outdated after accounts | rewritten: authenticated, test backend only, refuses to ask unless the RAG reports provider=ollama |
| phase17/18/19 refusal check | expected the old wording only | also accepts the current NOT_IN_TEXTBOOK wording (old wording still accepted) |

## 3. Test results (all AI tests on Ollama llama3 with OpenAI blocked)
| Test | Original code | Final |
|---|---|---|
| final_answer_quality_regression (33 cases, new) | not run on original; run 1 of new code 24/33 | run 2 31/33, run 3 31/33, run 4 32/33; every failing case fixed and rechecked 11/11 PASS (16:01-16:13) |
| Shahaji repeat (shivaji-short + shivaji-direct x3) | FAIL (run 1) | 6/6 (run 2), 6/6 final recheck; run 4 5/6 was a checker false positive (now precise) |
| final_unit_tests (new) | - | 71/71 PASS |
| llm_provider_unit (mocked HTTP) | - | 15/15 PASS |
| fact_layer_unit | ALL PASS | ALL PASS |
| phase21c_unit | PASS | PASS |
| fact_layer_smoke | 1 FAIL (integrity missing=2) | same 1 FAIL (pre-existing) |
| fact_planner_regression | 1 FAIL (corpus-successor-father-pronoun) | same 1 FAIL (pre-existing) |
| smoke-test.mjs (authenticated, rewritten) | old version incompatible with accounts | 18/18 PASS |
| privacy-test.mjs (new) | - | 28/28 PASS |
| auth-media-test.mjs | 37 checks | 41/41 PASS (4 new future-asset checks) |
| ai-usage-test.mjs | - | 10/10 PASS |
| reliability.ps1 (RAG down / LLM down) | - | 6/6 + 6/6 PASS; 502, failure logged, no fallback, 0 OpenAI |
| Learning-module PDF (Shivaji) | stray "**"/full stops | 4 pages, 1 textbook image, 0 `**`, 0 ".:", 0 "].", correct Shahaji and Shaista Khan attribution |
| Frontend `vite build` | OK | OK |
| Mocked browser UI check + axe (WCAG 2 A/AA) | - | 13/13 PASS, 0 violations on /, /login, /signup, /teacher/login, /start, /chat |
| BLOCKED / not done | | live-site checks with OpenAI (would cost money); Kannada answers (no Kannada corpus) |

Notes: llama3 output varies between runs; sentence-length checks can flicker. Production uses OpenAI.

## 4. Security findings
- OK: parameterised SQL; scrypt + timing-safe compare; same message for unknown email and wrong password; tokens stored as SHA-256; role cannot be self-assigned; ownership checked on sessions, conversations, modules, PDFs; images require sign-in and are path-restricted to `data/images/`; helmet headers; no secrets in health or errors.
- Fixed: 413 instead of 500 for large bodies; 400 for malformed module ids.
- Recommend: set `TRUST_PROXY` behind a proxy; keep RAG port private; add password reset and account deletion; periodic purge of expired `auth_sessions`; set `VITE_API_BASE_URL` for production builds. The daily AI counter also counts rejected requests (deliberate: errors cannot bypass it).

## 5. Provider and cost behaviour
Resolution: `HISTORYBOT_LLM_PROVIDER` (test only) > OpenAI when `OPENAI_API_KEY` is set > `LLM_PROVIDER`.
With the current `.env` (`LLM_PROVIDER=ollama` + key) production resolves to **OpenAI**, fallback **none**
(verified on the laptop with `describe_provider()`, no call made). The live RAG (PID 51196, started
08-10 10:06, after the last client.py commit) runs the old code: OpenAI with a silent Ollama fallback.
After restart: OpenAI, and a clear "Answer service is unavailable" if OpenAI fails (set
`LLM_FALLBACK_PROVIDER=ollama` to keep a fallback on purpose). Optional clarity line: `LLM_PROVIDER=openai`.
Cost controls: 20 AI requests/10 min and 200/day per account. Extra model calls only on the refusal guard
and re-explain retry paths.

## 6. Deployment readiness and remaining steps
See `docs/deployment-readiness.md`. Remaining: review + commit; set production env (FRONTEND_ORIGIN,
VITE_API_BASE_URL, TRUST_PROXY, NODE_ENV=production); TLS reverse proxy; keep RAG private; restart services;
ingest Kannada textbook if Kannada is required; add more verified images.

## 7. Teacher account
Public sign-up only creates students. From the project root:
`set ADMIN_EMAIL=...& set ADMIN_DISPLAY_NAME=...& set ADMIN_PASSWORD=...& node backend\scripts\create-admin.mjs`
(PowerShell: `$env:ADMIN_EMAIL="..."` etc.). It will not change an existing admin's password unless
`ADMIN_RESET_PASSWORD=1`, and will not promote a student unless `ADMIN_ALLOW_PROMOTE=1`. Sign in at `/teacher/login`.

## 8. Run locally
1. MySQL80 running; Ollama only if testing locally.
2. RAG: `python scripts\rag_internal_server.py` (port 8000).
3. API: `cd backend; npm start` (port 3000).
4. Frontend: `cd frontend; npm run dev` (http://localhost:5173).
Tests: `docs/testing.md`.

## 9. Restarts needed to go live (not done)
1. RAG: `Stop-Process -Id 51196`, then from `C:\Users\vkant\Projects\historybot`: `python scripts\rag_internal_server.py`.
   Expect `HistoryBot RAG llm_provider=openai model=gpt-6.1-sol reason=OPENAI_API_KEY is configured fallback=none`.
2. Backend: `Stop-Process -Id 43860` (node src/server.js; its cmd.exe wrapper PID 46952 then exits or can be closed), then `cd backend; npm start`.
   (`ai_usage` migration already applied.)
3. Frontend: rebuild/redeploy `frontend/dist` (dev server picks changes up automatically).

## 10. Files changed in this run
- backend/scripts/ai-usage-test.mjs (new)
- backend/scripts/auth-media-test.mjs (changed)
- backend/scripts/migrate-ai-usage.mjs (new)
- backend/scripts/privacy-test.mjs (new)
- backend/scripts/seed-verified-images.mjs (changed)
- backend/scripts/smoke-test.mjs (changed)
- backend/src/app.js (changed)
- backend/src/config/env.js (changed)
- backend/src/controllers/econtentController.js (changed)
- backend/src/middleware/auth.js (changed)
- backend/src/server.js (changed)
- backend/src/services/aiUsage.js (new)
- backend/src/services/images.js (changed)
- backend/src/utils/errors.js (changed)
- docs/adding-images.md (new)
- docs/deployment-readiness.md (new)
- docs/llm-provider.md (new)
- docs/testing.md (new)
- frontend/src/components/MessageBubble.jsx (changed)
- frontend/src/components/MessageList.jsx (changed)
- frontend/src/i18n/labels.js (changed)
- rag/engine/answer.py (changed)
- rag/engine/econtent.py (changed)
- rag/engine/sanitize.py (changed)
- rag/internal_api.py (changed)
- rag/llm/client.py (changed)
- rag/llm/config.py (changed)
- rag/pdf/render.py (changed)
- rag/prompts/econtent.py (changed)
- rag/prompts/tutor.py (changed)
- scripts/final_answer_quality_regression.py (new)
- scripts/final_unit_tests.py (new)
- scripts/llm_provider_unit.py (new)
- scripts/ollama_test_guard.py (new)
- scripts/phase17_regression.py (changed)
- scripts/phase18_regression.py (changed)
- scripts/phase19_regression.py (changed)
- scripts/rag_internal_server.py (changed)
- scripts/sql/004_ai_usage.sql (new)

(Stage 2/3 and homepage changes from earlier stages are also uncommitted; see `git status`.)

## 11. Backups and data
- Originals before first change in this run: `final-dev-backup-20261011\<path>`; earlier: `stage2-backup-20261011`, `stage3-backup-20261011`, `homepage-backup-20261011*`.
- DB dump before the additive `ai_usage` migration: `tmp\backups\historybot-pre-ai-usage-2026-10-11T08-42-38-670Z.sql`.
- Data intact: tests deleted only rows they created. After the final run: users 0, test users 0, auth_sessions 0, ai_usage 0; historical rows unchanged (anonymous_sessions 128, conversations 371, messages 1664, econtent_documents 36, analytics_events 2220, verified_images 4).
- Evidence: `tmp\final-dev\PROGRESS.md`, `runs.log`, `final-answer-quality.run{1,3,4}.json`, `final-answer-quality.recheck.json`, `shahaji-final-{1,2,3}.json`, `learning-module-final.pdf`.

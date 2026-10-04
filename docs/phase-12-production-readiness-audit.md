# Phase 12 — Production readiness and deployment audit

**Date:** 2026-10-04  
**Base commit inspected:** `235967c977359abb8e1b4d48aa1a50344d7f26a9` (`phase-11c-reliability`)  
**Scope:** Audit only. No architecture redesign, no database migration, no deploy, no Hostinger purchase, no production LLM change, no Chroma rebuild.

**Conservative production-readiness estimate: ~42%.**  
Local English RAG works. The stack is not yet a public internet service.

---

## 1. Executive summary

HistoryBot is a textbook-grounded Class 9 History assistant: React/Vite frontend, Express public API, MySQL conversation store, internal FastAPI RAG, persistent Chroma, local Ollama `llama3` chat, and Ollama `nomic-embed-text` embeddings.

It is **not production-ready** for a public Karnataka classroom deployment. The application is still a **localhost-bound development topology**. The LLM client **only implements Ollama**. PDF fonts named in `data/fonts/README.md` are **not in the repository**. Kannada UI exists, but **Kannada textbook ingest is not classroom-ready** (Nudi converter still missing). Verified images are **not present as files** in the tree inspected.

Express can be exposed **behind a reverse proxy with fixes**, not as a raw public Node process with development defaults.

**Do not buy hosting until:** production environment variables and HTTPS/CORS/API URL are specified, an LLM+embedding strategy that does not depend on laptop Ollama/`llama3` is implemented in code, MySQL uses a dedicated non-root user, PDF fonts (and any verified images to ship) are packaged, process management and reverse-proxy topology are chosen, and a go/no-go is made on English-only vs bilingual launch.

---

## 2. Current architecture

**Actual request path (current code):**

```
Browser (Vite :5173 in development)
  → Express 127.0.0.1:3000  /api/v1
       → MySQL 8  database `historybot`
       → Python FastAPI 127.0.0.1:8000  /internal/*  (header X-Internal-Secret)
            → Chroma  data/chroma  collection historybot_class9_ss_v2
            → Ollama 127.0.0.1:11434
                 → embeddings: nomic-embed-text (768-d)
                 → chat: llama3
            → ReportLab PDF (data/fonts + optional data/images)
```

| Piece | Current |
|---|---|
| Frontend | React 19 + Vite 8 + Tailwind. Routes `/`, `/chat`. `BrowserRouter`. Session UUID in `localStorage`. |
| Public API | Express 5, Node ≥20, Helmet, CORS, 30 req/60s, JSON 32kb, Zod, parameterized SQL. Binds **127.0.0.1**. |
| RAG | FastAPI via `python scripts/rag_internal_server.py`. Docs/OpenAPI disabled. Binds **127.0.0.1:8000**. |
| Persistence | MySQL tables below. Chroma ignored by git (`data/chroma/**`). |
| Generated PDFs | Built in memory and returned; `data/generated/` gitignored. |
| Source textbooks | Gitignored under `data/textbooks/**`. Not served by Express. |

---

## 3. Frontend audit

| Check | Finding |
|---|---|
| Production build | **`npm run build` succeeded** (Vite 8.3.2, ~16s). Output `frontend/dist/` (gitignored). `index.html` 0.51 kB; CSS ~9.9 kB; JS ~408 kB / 128 kB gzip. |
| API base URL | `VITE_API_BASE_URL` baked at **build time**. Default fallback `http://localhost:3000/api/v1`. |
| Env | `frontend/.env.example` is localhost only. No production example. |
| Routing | `/` Home, `/chat` Chat, `*` → `/`. Refresh of `/chat` needs **SPA rewrite** on the static host. |
| Mobile / desktop | Chat header wraps; history is a drawer on small screens (`md:hidden`). Desktop sidebar. Not exhaustively device-tested in this audit. |
| Error states | `AppContext` surfaces `ApiError` friendly strings (network, RAG down, 429, session). Markdown links stripped; `rehype-sanitize` used. |
| Loading | “Thinking from your textbook…” |
| Empty chat | Copy exists. Home/Chat still mention **Chapter 5** in how-it-works copy (stale vs Phase 11 Ch.17). |
| History / new chat | List + create via API; `historybot_current_conversation_id` restored after refresh if session still valid. |
| PDF download | Blob download from `POST /econtent/:id/pdf`. |
| Citations | Page labels via `SourceCite`; no PDF URLs. |
| E-content UI | Panel with sections + PDF button. |
| Images | `<img src={API}/images/{uuid}>`. **No `onError` fallback.** Content-Type from API is always `image/png`. |
| Backend unavailable | Network error string. Composer disabled until `ready`; session create failure still sets `ready` true with error banner. |

**Vite `dev` / `preview` bind `localhost:5173`.** Production must serve `dist/` with a static server or CDN, not `npm run dev`.

---

## 4. Backend audit

| Check | Finding |
|---|---|
| PORT | `PORT` or `APP_PORT`, default 3000. |
| HOST | **Hardcoded `127.0.0.1`** in `backend/src/server.js`. |
| CORS | Single origin `CORS_ORIGIN` or `http://localhost:5173`. **Not a wildcard.** |
| Helmet | Enabled; `Cross-Origin-Resource-Policy: cross-origin` (needed if frontend and API are on different origins). |
| Rate limits | 30 / 60s per IP (configurable). Applies to all `/api/v1` including health. **No `trust proxy`** — behind nginx, limits may collapse to one IP. |
| JSON body | 32kb. |
| Zod | Sessions, conversations, messages (max 2000 chars), e-content. |
| SQL | `mysql2` placeholders. Ownership checks on conversation and e-content. |
| Errors | Zod → 400; `AppError`; MySQL `ER_*` → 503 `DATABASE_ERROR`; else 500 `INTERNAL_ERROR` without stack. Logs `unhandled_error` + code/name only. |
| Internal Python | `X-Internal-Secret` from `INTERNAL_RAG_SECRET`. Timeouts 180s chat / 300s e-content. Failed RAG → 502/504 **generic** messages (Python font `FileNotFoundError` detail is **not** forwarded by Express). |
| Public vs internal | Public: `/health`, sessions, conversations, messages, e-content, images. Python `/internal/*` is a separate process. Health checks **MySQL only**, not RAG. |
| `DAILY_LLM_BUDGET` | Present in `.env.example`, **unused in code**. |

### Can Express be safely exposed to the public internet?

**WITH FIXES**

Why not “YES”: development CORS/API URL; no TLS in-app (must be proxy); no `trust proxy`; bind is loopback (correct **only** if nginx/Caddy sits on the same host); anonymous UUID is the entire credential; e-content/PDF can pin a worker for minutes with no daily budget; `LLM_PROVIDER` cannot leave Ollama without a code change.

Why not “NO”: Helmet, CORS allowlist, body limit, rate limit, parameterized SQL, ownership checks, no stack traces in JSON, RAG secret, textbooks not statically served.

---

## 5. Python / RAG audit

| Item | Current | Linux VPS |
|---|---|---|
| Startup | `python scripts/rag_internal_server.py` (requires `INTERNAL_RAG_SECRET`) | Same; systemd/supervisor; project venv |
| Port | `RAG_INTERNAL_PORT` default 8000 | Keep internal |
| Host | **127.0.0.1** | Keep 127.0.0.1; **do not publish 8000** |
| Auth | `X-Internal-Secret` constant-time equality **not** used (plain `!=`) | Same secret as Express; firewall still required |
| Chroma | `PROJECT_ROOT / data / chroma` via `pathlib` | Relative paths work on Linux |
| Ollama | Chat + embeddings to `127.0.0.1:11434` | Must be replaced or installed; **llama3 not practical on a small VPS** |
| Models | `llama3`, `nomic-embed-text` | See LLM section |
| Filesystem | Chroma dir, optional `data/images`, `data/fonts`, ingest under `data/extracted` (gitignored) | Linux paths; no `C:\` hardcoded in runtime code |
| PDF | ReportLab; fonts `NotoSans-Regular.ttf`, `NotoSansKannada-Regular.ttf` | Must exist on disk |
| Python deps | `rag/requirements.txt`: `chromadb==0.5.23`, `reportlab==4.4.4` | Plus FastAPI/uvicorn/pydantic (imported; **not pinned in requirements.txt**) |

**Windows-specific paths:** none hardcoded in application Python/JS. Persistence uses `Path`. Local inspect showed `C:\Users\vkant\Projects\historybot\data\chroma` only as a resolved Windows path.

**Gap:** `rag/llm/client.py` raises if `LLM_PROVIDER != "ollama"`. Env vars `LLM_BASE_URL` / `LLM_API_KEY` exist but are **not wired**.

FastAPI PDF handler returns `detail=str(exc)` on missing fonts (path-ish message). Express maps non-OK PDF to a generic 502.

---

## 6. Chroma audit

Inspected **read-only** on this machine (no rebuild, no delete).

| Item | Value |
|---|---|
| Persistence directory | `data/chroma` (~**9.4 MB** on disk) |
| Collections | `historybot_class9_ss` (**67** docs, Phase 5 Ch.5) — **not active** |
| Active | `historybot_class9_ss_v2` (**161** docs) |
| Embedding model | `nomic-embed-text` |
| Distance | cosine (`hnsw:space`) |
| Dimension | **768** (sampled from v2) |
| Portable to Linux? | **Probably**, if Chroma 0.5.x matches; safer to **rebuild from ingest artifacts** than to copy a Windows SQLite/HNSW dir blindly |
| Remain local on VPS? | **Yes** — current code is a local PersistentClient, not Chroma Cloud |
| Backup? | **Yes** — stop writes, copy `data/chroma/` |
| Rebuild from source? | **Yes** — ingest scripts + Ollama embeddings; textbooks and `data/extracted` are gitignored and must be present privately |

**v2 metadata fields (from indexer):**  
`chunk_id`, `source_id`, `source_type`, `authority`, `language`, `document_name`, `publisher`, `chapter`, `topic`, `section`, `source_file`, `ingest_version`, `pdf_page_number`, `printed_page_number`, `textbook_page_number`, `citation_label`, `retrieval_excluded`, `embedding_model`.

Chroma telemetry errors (`capture() takes 1 positional argument`) appear on inspect; `ANONYMIZED_TELEMETRY` is set false in `chroma_store.py`. Cosmetic, not a deploy blocker.

---

## 7. LLM audit

| Item | Current |
|---|---|
| Exact model name | `llama3` (`OLLAMA_MODEL` / `LLM_MODEL` default) |
| Provider in code | Ollama `/api/chat`, `stream: false` |
| Embeddings | Separate: `nomic-embed-text` via `/api/embeddings` |
| RTX 2050 | **Not referenced in code.** Local Ollama *may* use a Windows NVIDIA GPU if the OS/Ollama runtime does. Production Linux VPS typically has **no GPU**. |
| Practical on low-cost VPS? | **Self-hosted `llama3` (8B-class): no.** RAM/disk/CPU make it a poor fit for a cheap VPS and classroom latency. **Embeddings-only** `nomic-embed-text` is much smaller and *might* run on CPU. |
| Disk (order of magnitude, not a vendor spec) | Chat weights commonly several GB; embed model hundreds of MB. Do not treat this as a purchase SKU. |

**Do not assume production will run Ollama.** The adapter must be extended before a public launch that does not ship a GPU box.

### Production LLM **requirements** (provider not chosen)

- OpenAI-compatible HTTP chat completions (or a thin adapter behind `LLM_PROVIDER`)
- HTTPS to the provider
- Auth via env (`LLM_API_KEY`), never in git
- Grounded answers from retrieved chunks; temperature already low (~0.1)
- Streaming **optional** (current UI is non-streaming)
- Context long enough for ~5–12 chunks + 4+4 history turns + instructions
- Kannada generation **if** bilingual launch is in scope (quality not guaranteed today)
- Predictable per-token or per-request pricing
- Rate limits that survive a class period of simultaneous students
- Contract: no training on submitted student questions if the research/privacy bar requires it
- Latency acceptable for Indian school networks (chat currently allows 180s; that is too slow for a public UX even if the provider is faster)
- **Matching 768-d embeddings** (`nomic-embed-text` or an equivalent that will **not** silently mismatch Chroma)

---

## 8. MySQL audit

| Item | Value |
|---|---|
| Database | `historybot` |
| Charset / collation | `utf8mb4` / `utf8mb4_unicode_ci` |
| Tables | `anonymous_sessions`, `conversations`, `messages`, `analytics_events`, `econtent_documents`, `verified_images` |
| FKs | Conversations → sessions **CASCADE**; messages → conversations **CASCADE**; analytics session **CASCADE**, conversation **SET NULL**; e-content session **CASCADE**, conversation **SET NULL** |
| Indexes | PK UUIDs; `last_seen_at`; `(session_id, updated_at)`; `(conversation_id, created_at)`; analytics `(event_type, created_at)`, `session_id`; e-content `(session_id, created_at)`; images `topic`, `status` |
| Extra image columns | `alt_text`, `textbook_page_number` used in code; added by seed script / `002_verified_image_columns.sql` notes |
| Connection | `mysql2` pool, `connectionLimit: 10`, `charset utf8mb4`, `timezone: Z` |
| Credentials | Project root `.env` (`MYSQL_USER`, `MYSQL_PASSWORD`, …). `.env` is **gitignored**. |
| Root used by app? | **Yes on this development machine** (`MYSQL_USER=root`). **Must not** be the production application user. |

**Production requires:** dedicated DB user; privileges limited to `historybot`; local socket or private network only (not public 3306); backups; pooling (already present). Remote MySQL from a separate host is optional, not required if all processes share one VPS.

---

## 9. Privacy / analytics audit

**Intentionally stored**

| Data | Where |
|---|---|
| Anonymous session UUID | MySQL + `localStorage` |
| Conversation UUID, title (often first 80 chars of the question) | MySQL |
| Full question and answer text | `messages.content` |
| Language `en`/`kn` | sessions, messages, analytics |
| Timestamps UTC | DATETIME(3) |
| Source page JSON, internal `chunk_ids` (assistant rows; **not** sent by `publicSources`) | MySQL |
| E-content JSON body | `econtent_documents` |
| Analytics events | `SESSION_STARTED`, `QUESTION_ASKED`, `ANSWER_GENERATED`, `LANGUAGE_CHANGED` (schema; confirm writers), `E_CONTENT_GENERATED`, `PDF_DOWNLOADED`, `NEW_CHAT` |
| `topic_text` | First 255 chars of the question/topic on some events |
| `metadata_json` | e.g. `{ grounded: bool }` |
| `user_agent_hash` column | **Exists; not written** by current `createSession` |

**Not collected by design:** student name, phone, email, address, password, login.

**Accidental PII:** any name/phone/school a student **types into the chat** is stored in `messages` and may be copied into `analytics_events.topic_text` (255 chars) and conversation titles. Session UUID in `localStorage` is a bearer token: anyone with the UUID can read that session’s history.

No student login/registration exists (correct for this product).

---

## 10. Copyright / source handling

| Risk | Status |
|---|---|
| Original textbooks in `public/` or frontend static | **No** |
| Express static textbook route | **None found** |
| Citations as download links | **No** — page numbers and labels only |
| `source_file` / `pdf_page_number` in public JSON | Stripped by `publicSources` (chunk_id, pdf page, document file name not returned to browser) |
| Filesystem paths in API errors | Express generic. Python font error string is internal unless the RAG port is exposed |
| Generated PDF embeds textbook pages? | **No raster of textbook pages.** ReportLab text + optional **verified image files** from `data/images/` |
| Git | `*.pdf` and `data/textbooks/**` ignored |

**Exposure to fix operationally:** never put textbooks under a web root; never reverse-proxy `/data`; keep ingest PDFs only on the VPS with tight file permissions.

---

## 11. Security audit

| Issue | Severity | Notes |
|---|---|---|
| Hardcoded API keys in repo | Not found in scanned source | Secrets belong in `.env` |
| `.env` in git | **Ignored** (`git check-ignore` confirms) | |
| SQL injection | Mitigated | Placeholders + Zod UUIDs |
| Path traversal (images) | Mitigated on Express | Must start `data/images/`, no `..` |
| Path traversal (Python PDF images) | Weaker | `IMAGE_ROOT / file_path` without the same prefix check (internal-only today) |
| SSRF | RAG URL from env | Do not let users supply URLs |
| Internal endpoints | Bound 127.0.0.1 + secret | Publishing :8000 or :11434 is a **P0 ops failure** |
| Unrestricted e-content/PDF | Session UUID only | Cost/DoS; no daily budget |
| CORS `*` | **No** | |
| Stack traces to browser | **No** (Express) | |
| Prompt injection | Partial | Grounding + leak markers (`wikipedia`, `ollama`, …); not a full security boundary |
| Anonymous session abuse | Real | Guessing UUIDs is hard; stealing from a shared browser is easy |
| `INTERNAL_RAG_SECRET` empty | Process exits (Python) / Express `required()` | Must be unique and long in production |

---

## 12. Hosting requirements

Estimates from **this codebase**, not a Hostinger SKU list. No web pricing research.

| Layer | Minimum (practical) | Recommended |
|---|---|---|
| **Frontend** | Static files from `vite build` (~0.5 MB). SPA fallback. HTTPS. | Same + cache headers / optional CDN |
| **Backend** | Node 20+, 1 process, loopback + reverse proxy | 2 Node workers or one Node + restart policy |
| **Python** | 3.11-ish venv, FastAPI/uvicorn, Chroma, ReportLab | systemd, logs, restart on fail |
| **Chroma** | ~10 MB now; grow with chapters | Tens of MB–low GB with full-book ingest |
| **MySQL** | Small InnoDB; utf8mb4 | Automated dump |
| **LLM** | **External API** (or a separate GPU host). Not `llama3` on a cheap VPS | Same |
| **Embeddings** | CPU `nomic-embed-text` **or** matching API | Keep dim 768 |
| **Storage** | App + venv + fonts + private textbooks + Chroma + MySQL | + backup volume |
| **Bandwidth** | Chat JSON small; PDFs/images moderate | Class concurrent use |
| **RAM** | **4 GB** if **no** llama3, MySQL+Node+Python+embed coexist | **8 GB** |
| **CPU** | **2 vCPU** | **4 vCPU** |
| **Disk** | **40 GB** (OS + MySQL + private PDFs + logs) | **80 GB** |

If someone insists on self-hosting `llama3` on the same box, treat RAM as **16 GB+** and drop “low-cost VPS” as a goal. This audit does **not** recommend that.

---

## 13. Hostinger compatibility (conceptual)

No plan selected.

| Component | A. Shared hosting | B. VPS | C. Separate services |
|---|---|---|---|
| Frontend static | **POSSIBLE WITH WORKAROUND** (if SPA rewrite + HTTPS) | **SUPPORTED** | **SUPPORTED** (object storage / pages) |
| Node Express | **NOT SUITABLE** (loopback RAG, long timeouts, process control) | **SUPPORTED** | **SUPPORTED** |
| Python RAG | **NOT SUITABLE** | **SUPPORTED** | **SUPPORTED** |
| Chroma on disk | **NOT SUITABLE** | **SUPPORTED** | **POSSIBLE WITH WORKAROUND** (still need a diskful Python host) |
| MySQL | **POSSIBLE WITH WORKAROUND** (remote DB + app elsewhere; 3306 must not be public) | **SUPPORTED** | **SUPPORTED** |
| Ollama llama3 | **NOT SUITABLE** | **NOT SUITABLE** on small VPS / **POSSIBLE WITH WORKAROUND** on a large GPU-class VPS | **SUPPORTED** as external API instead of Ollama |

**Shared hosting is not suitable for HistoryBot as a whole.** A **VPS (or equivalent always-on VM)** is required for Node + Python + Chroma. Frontend may live on the same VPS or a static host.

---

## 14. Recommended deployment topology

One topology that matches **current code** (LLM swapped at the adapter, not in the browser):

```
Student browser
  → HTTPS  (example: www or apex domain)
       static React (dist/)
  → HTTPS  (example: api. subdomain)
       reverse proxy (TLS terminate, SPA headers, /api → Node)
            → Express 127.0.0.1:3000
                 → MySQL  (localhost, unix socket or 127.0.0.1:3306)
                 → Python RAG 127.0.0.1:8000  + X-Internal-Secret
                      → Chroma  ./data/chroma
                      → Embedding endpoint (local nomic or compatible API)
                      → Chat LLM HTTPS API  (not public Ollama)
                      → fonts + verified images on disk
```

**Ollama :11434 and FastAPI :8000 stay off the public firewall.**

---

## 15. Domain / HTTPS

Do not purchase in this phase.

| Item | Recommendation |
|---|---|
| Frontend | Apex or `www` (example shape only: `https://historybot.example`) |
| API | Same origin `/api/v1` **or** `https://api.example` |
| HTTPS | **Required** (session UUID in JSON; mixed content would break) |
| CORS | Exact frontend origin(s), no `*` |
| Env | `CORS_ORIGIN`, `VITE_API_BASE_URL` (build), `PUBLIC_APP_URL`, MySQL, `INTERNAL_RAG_SECRET`, LLM/embed endpoints, `NODE_ENV=production` |

If API is a subdomain, keep Helmet CORP `cross-origin` for `/images`. Prefer **same-site** `/api` to simplify cookies later (not used today).

---

## 16. Backup / recovery

| Asset | Backup? | Rebuild? | Public? |
|---|---|---|---|
| MySQL `historybot` | **Must** (sessions, chats, analytics, e-content, image metadata) | Schema yes; student chats **no** | **No** |
| Chroma `data/chroma` | Should | **Yes** from ingest | **No** |
| Source PDFs / extracted JSON | **Private** copy | Ingest from textbooks | **Never public** |
| Verified images + fonts | **Must** if not in git | Fonts from OFL; images from seed | Images may be public **via UUID API only** |
| `.env` / secrets | Encrypted offline | Recreate | **Never** in public backups |
| `data/generated` | No | Regenerable | No |
| node_modules / venv | No | `npm ci` / pip | — |

Minimal practice: daily MySQL dump + weekly Chroma tarball + private textbook archive, all encrypted, not in the web root.

---

## 17. Failure behavior

| Failure | Current | Improvement needed |
|---|---|---|
| MySQL down at boot | Express `process.exit(1)` | Process manager restart; user sees site static but API dead |
| MySQL down at runtime | 503 `DATABASE_ERROR` / friendly frontend | OK |
| Python RAG down | 502 `RAG_UNAVAILABLE` + UI sentence | OK |
| Chroma missing/corrupt | RAG exception → 502 | Health should detect; do not leak paths |
| Ollama / LLM down | Same 502 | Faster fail; distinguish “answers unavailable” |
| LLM timeout | 504 `RAG_TIMEOUT` | 180–300s is too long for UX |
| PDF fail | 502 PDF unavailable | Ensure fonts packaged |
| E-content ungrounded | 200 with `grounded: false` + message | OK |
| Invalid session / conversation | 404/403 + UI “start a new chat” | Stale `localStorage` UUID needs clearer reset |
| Rate limit | 429 JSON + UI | `trust proxy` |
| Unknown route | 404 `NOT_FOUND` | OK |
| Frontend 500 JSON | Generic “Something went wrong” | Confirm `dist` never prints stacks (it does not) |

Stack traces and Windows paths must not appear in the browser. They currently do not via Express JSON.

---

## 18. P0 — must fix before public launch

1. **Production config:** `VITE_API_BASE_URL`, `CORS_ORIGIN`, `NODE_ENV=production`, strong `INTERNAL_RAG_SECRET`, HTTPS reverse proxy, SPA `/chat` rewrite.  
2. **LLM adapter:** wire a non-Ollama production provider (env already sketched; **code still Ollama-only**). Do not ship public traffic to laptop `llama3`.  
3. **Embeddings:** keep 768-d `nomic-embed-text` (or compatible) available at query time.  
4. **Never publish** Python 8000, Ollama 11434, or MySQL 3306.  
5. **Dedicated MySQL user** (not `root`), least privilege, local-only.  
6. **PDF fonts on disk** (`NotoSans-Regular.ttf`, `NotoSansKannada-Regular.ttf`); they are documented but **not in the repo**.  
7. **Process manager + boot order** (MySQL → RAG → Express) and log rotation.  
8. **Launch-scope decision:** English-only public vs bilingual. Kannada textbook ingest is **not** classroom-ready; do not advertise Kannada as production-quality without ingest.

---

## 19. P1 — should fix before client demo

1. Kannada Nudi ingest / honest UI copy that Kannada answers are not from the Kannada textbook.  
2. Package **verified images** or disable image UI if files are empty.  
3. Image `onError` fallback; do not assume PNG.  
4. `trust proxy` + rate-limit correctness behind nginx.  
5. `/health` should include RAG (and maybe embeddings) without leaking internals.  
6. Cap e-content/PDF cost (`DAILY_LLM_BUDGET` or equivalent) so a demo cannot stall the VM.  
7. Stale “Chapter 5” frontend copy vs KTBS 2026–27 Ch.17.  
8. Pin FastAPI/uvicorn/pydantic in `rag/requirements.txt`.  
9. Python PDF image path allowlist (defense in depth).  
10. Backup scripts and a restore drill.  
11. README still describes an earlier phase — operators will follow the wrong runbook.

---

## 20. P2 — can fix after launch

1. Structured logging, request IDs, uptime monitoring.  
2. School-NAT-friendly rate limits (session-based, not only IP).  
3. Clearer recovery when `localStorage` session is missing on the server.  
4. Chroma Linux copy vs rebuild policy documented in ops runbook.  
5. Reduce chat timeout toward a real SLA.  
6. Helmet/HSTS at proxy.  
7. Unused `user_agent_hash`.  
8. Broader chapter coverage beyond current v2 corpus.  
9. Constant-time secret compare on RAG header.

---

## 21. P3 — future enhancement

1. Streaming tokens.  
2. Student login (explicitly out of scope now).  
3. Hosted Chroma or split embedding service.  
4. CDN for static assets.  
5. GPU self-host LLM.  
6. Native Kannada OCR/converter when a licensed tool exists.  
7. Admin analytics UI (would be a new privacy surface).

---

## 22. Final production checklist

### Functional

- [ ] Home loads over HTTPS  
- [ ] Search/chat grounded answers + citations  
- [ ] New chat  
- [ ] History list and restore after refresh (`/chat` rewrite)  
- [ ] Follow-up uses last 4+4 turns  
- [ ] E-content sections  
- [ ] PDF download (fonts present)  
- [ ] Images or graceful empty  
- [ ] English quality on Chapter 17 topics  
- [ ] Kannada: either working from Kannada evidence **or** UI does not claim that  

### Security

- [ ] HTTPS everywhere  
- [ ] CORS allowlist  
- [ ] Secrets only in server env  
- [ ] Rate limits with trusted proxy  
- [ ] SQL still parameterized  
- [ ] Internal RAG not on public NIC  
- [ ] Textbooks not downloadable  

### Performance

- [ ] Chat latency acceptable on Indian broadband (target well under current 180s cap)  
- [ ] E-content does not block the VM for 300s under load  
- [ ] PDF generation  
- [ ] Rough concurrent-user test (class-sized)  

### Data

- [ ] MySQL migrations/schema applied  
- [ ] Chroma v2 present or rebuilt  
- [ ] Encrypted backups  
- [ ] Analytics fields reviewed for PII in free text  

### Deployment

- [ ] `npm run build` with production `VITE_API_BASE_URL`  
- [ ] Env documented  
- [ ] Domain + DNS + TLS  
- [ ] systemd/pm2 + reverse proxy  
- [ ] Logs and restart  
- [ ] Firewall  

---

## 23. What must be completed before purchasing hosting

1. Decide **English-only vs bilingual** launch and write that on the homepage.  
2. Implement **production LLM + embedding** path in code (still do not lock a vendor in this document).  
3. Prepare **production `.env` template** (no secrets committed): CORS, API URL, DB user, RAG secret, LLM keys.  
4. Add **OFL fonts** (and images if the demo needs them) to the deploy artifact.  
5. Choose **VPS-shaped** hosting (not shared PHP hosting). Specific Hostinger plan is **out of scope**.  
6. Write a one-page **runbook**: start order, nginx sketch, backup, what ports stay closed.  
7. Confirm **legal** use of KTBS/NCERT files on a public server (private disk vs redistribution).  
8. Do **not** deploy, migrate Odoo/Postgres, or rebuild Chroma as part of buying a plan.

---

## Appendix A — Localhost / Windows / dev dependencies

| Dependency | CURRENT | PRODUCTION | BLOCKER |
|---|---|---|---|
| Frontend origin | Vite `localhost:5173` | HTTPS static host | **Yes** if unchanged |
| API URL | `http://localhost:3000/api/v1` | HTTPS API or same-origin `/api` | **Yes** |
| CORS | `http://localhost:5173` | Real origin | **Yes** |
| Express bind | `127.0.0.1` | Keep + reverse proxy | No (if VPS proxy) |
| Python bind | `127.0.0.1:8000` | Keep internal | No |
| Ollama | Local `llama3` + nomic | API and/or small embed runtime | **Yes** for chat |
| Chroma | `data/chroma` on Windows disk | Same layout on Linux | No if copied/rebuilt |
| MySQL | `localhost`, user **root** locally | Dedicated user, local socket | **Yes** (root) |
| Filesystem textbooks | gitignored local PDFs | Private VPS disk | Ops yes |
| Hardcoded `C:\` | Not in runtime source | N/A | No |
| `NODE_ENV=development` | Example default | `production` | Should |
| `npm run dev` | Required today | **Forbidden** as prod server | **Yes** if used as prod |
| `python` uvicorn | Dev start script | systemd | Yes as a runbook item |
| Windows GPU | Possible via Ollama | Not assumed | No |

## Appendix B — Frontend build evidence

```
vite v8.3.2 building client environment for production...
✓ 199 modules transformed.
dist/index.html                   0.51 kB │ gzip:   0.32 kB
dist/assets/index-DR51kEfG.css    9.89 kB │ gzip:   3.05 kB
dist/assets/index-CFBU2C08.js   408.09 kB │ gzip: 127.60 kB
✓ built in 15.97s
```

No code was changed to make the build pass.

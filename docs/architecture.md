# HistoryBot architecture (Phase 1 approved)

Concise lock for implementation. Full Phase 1 discussion lives in the project chat.

## Request path

Student browser → React/Vite → Express API → Python RAG (localhost) → Chroma → LLM adapter → grounded response → Express → student.

## Stack

- **Frontend:** React + Vite + Tailwind (static). Routes: `/` home, `/chat`.
- **Public API:** Express (sessions, chat orchestration, analytics, rate limits, CORS).
- **RAG:** Python ingest + retrieve + e-content JSON + ReportLab PDF.
- **MySQL:** `historybot` database only. Never PostgreSQL_For_Odoo.
- **Chroma:** `data/chroma/`, collection `historybot_class9_ss`.
- **Dev LLM:** Ollama `llama3`. **Embeddings:** `nomic-embed-text`.
- **Prod LLM:** `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`. Provider not locked.

## Grounding

Retrieve → drop weak hits → prompt only with chunks → cite pages. If insufficient:

`This topic is not available in the provided textbook.`

No Wikipedia fallback.

## Data (MySQL, Phase 3)

`anonymous_sessions`, `conversations`, `messages`, `analytics_events`, `econtent_documents`, `verified_images`.

## Chunk metadata

`document_name`, `chapter`, `page_number`, `section`, `chunk_id`, `source_file`, `ingest_version`.

## Memory

Last 4 user + 4 assistant turns, truncated; always re-retrieve for the current question.

## Images

Local curated files + `verified` status only. No random web portraits.

## Hosting

Static frontend on Hostinger (or similar). Node + Python + Chroma on a VPS. Shared Hostinger is not assumed to run Ollama or llama3.

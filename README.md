# HistoryBot

HistoryBot is a planned AI-powered textbook learning assistant for **Karnataka State Board Class 9 Social Science / History**. It is being built as a real research product, not a generic chatbot.

**CURRENT STATUS:** Phase 2 project foundation only. Application features are **PLANNED**, not implemented.

## Target

- Board: Karnataka State Board
- Class: 9
- Subject: Social Science / History
- Initial corpus: **Mughals and Marathas**, textbook pages **3–16**
- Authoritative source: the client-supplied textbook PDF (not yet ingested)

## Research context

- **Research scholar:** Pandurang Vajranthi
- **Registration:** PHD23EDR09
- **University:** Vijayanagara Sri Krishnadevaraya University (VSKU), Bellary
- **Guide:** Dr. Sushma N. Jogan, Assistant Professor
- **Department:** Department of Studies in Education
- **Research topic:** The Impact of Crossover Instructional Modules through Artificial Intelligence on Digital Attitude, Social Engagement and Academic Achievement in Social Science at Secondary Level.

## Purpose

Students should feel a teacher is explaining **this textbook**. The system must not silently use Wikipedia or general knowledge. If retrieval cannot support an answer, it must say the topic is not available in the provided textbook.

There is **no student login, registration, image upload, or camera**.

## Core features (PLANNED)

- Textbook-grounded question answering (RAG)
- Simple Class 9 English and simple Kannada
- Textbook page / source citations
- Multi-turn chat, new chat, anonymous session history
- Structured E-content (about a 40-minute module)
- Professional E-content PDF download
- Verified historical images only (no guessed portraits)
- Privacy-conscious anonymous analytics
- Public HTTPS deployment

## Architecture (PLANNED — approved Phase 1)

```
Student browser
  → React + Vite frontend (static)
  → Express public API
  → Python RAG service (localhost)
  → Chroma + LLM adapter
  → Grounded answer + page citations
  → Express → student
```

| Layer | Planned technology |
|---|---|
| Frontend | React + Vite + Tailwind |
| Backend | Node.js + Express |
| RAG / ingest / PDF | Python 3.10 |
| Relational DB | MySQL 8 (`historybot` database — not created yet) |
| Vector store | ChromaDB on disk (`data/chroma/`) |
| Development LLM | Ollama `llama3` |
| Development embeddings | Ollama `nomic-embed-text` |
| Production LLM | OpenAI-compatible HTTP via env (`LLM_BASE_URL`). **Provider not locked.** |

MySQL (PLANNED) stores anonymous sessions, conversations, messages, analytics events, E-content records, and verified image metadata. **Do not use** the unrelated Odoo PostgreSQL instance.

**Cursor / Grok is the development assistant only.** It is not the website’s runtime AI.

## Textbook grounding (PLANNED)

PDF → page-aware extraction → cleaning → chunking with metadata (document, chapter, page, section, chunk id, source) → embeddings → Chroma → retrieval validation → LLM on retrieved context only → page citations or a clear refusal.

## Anonymous analytics (PLANNED)

Cookie-backed anonymous session UUID. Events such as session started, question asked, language changed, E-content generated, PDF downloaded. No claim to identify individual students.

## E-content and PDF (PLANNED)

Grounded structured modules; omit unsupported sections rather than invent facts. PDFs via Python ReportLab with bundled Kannada-capable fonts (fonts not added in this phase).

## Deployment concept (PLANNED)

- Frontend: static hosting (e.g. Hostinger public folder)
- Backend + Python RAG + Chroma: small VPS (Hostinger shared hosting is not assumed to run an LLM)
- MySQL: bundled Hostinger MySQL or VPS
- Production chat model: remote API, not Ollama on shared hosting

## Repository layout

```
frontend/    PLANNED React app (empty in Phase 2)
backend/     PLANNED Express API (empty in Phase 2)
rag/         PLANNED Python RAG (empty in Phase 2)
data/        textbooks, chroma, fonts, images (placeholders)
docs/        architecture and phase notes
scripts/     future ingest / migrate helpers
tests/       future tests
```

Textbook PDFs must not be committed (see `.gitignore`).

## Development phases

See [docs/development-phases.md](docs/development-phases.md).

## Local setup

Not applicable yet. Do not install npm/pip packages until the phase that needs them. Copy `.env.example` to `.env` only when configuration begins (Phase 3+).

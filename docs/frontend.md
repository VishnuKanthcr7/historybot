# HistoryBot frontend (Phase 8)

Student UI is React + Vite + Tailwind. It talks **only** to the public Express API.

```
Browser (localhost:5173)
  → GET/POST http://localhost:3000/api/v1/...
```

The browser must not call `:8000`, MySQL, Chroma, or Ollama.

## Start

1. Python RAG: `python scripts/rag_internal_server.py`
2. Express: `cd backend` then `npm start`
3. Frontend: `cd frontend` then `npm install` (first time) and `npm run dev`

Open `http://localhost:5173` (must be **localhost**, not `127.0.0.1`, so CORS matches `CORS_ORIGIN`).

## Environment

`frontend/.env` (gitignored) and `frontend/.env.example`:

```text
VITE_API_BASE_URL=http://localhost:3000/api/v1
```

No secrets in `VITE_` variables.

## Routes

| Path | Page |
|---|---|
| `/` | Home — research identity + start learning |
| `/chat` | Academic chat |

`/chat?q=...` sends that question once after an anonymous session exists.

## Anonymous session

On first load, `POST /api/v1/sessions`. `session_id` is stored in `localStorage`. Conversation **metadata** (id + title) is stored per session in localStorage because Phase 7 has no list-conversations endpoint. Opening a chat uses `GET /api/v1/conversations/:id?session_id=`.

## Language

`en` / `kn` sent on each `POST .../messages`. Major UI labels are translated. The whole site is not a complete localization.

## Sources

Uses `message.sources[].textbook_page_number` only. No chunk IDs.

Reload restores `historybot_current_conversation_id` via `GET /conversations/:id`. Untitled sidebar rows (`New Chat` / `ಹೊಸ ಚಾಟ್`) are renamed from the first question.

## Limitation

Not production-ready. Chat history list is local to the browser. Kannada answer quality is still the Phase 6 model. Asking a new topic in a thread that already has strong context can still retrieve the previous topic (Phase 6 RAG, not a frontend fallback).

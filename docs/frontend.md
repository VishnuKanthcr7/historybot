# HistoryBot frontend

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

Optional image seed after extracting textbook crops:

```text
python scripts/extract_chapter5_images.py
node backend/scripts/seed-verified-images.mjs
```

## Environment

`frontend/.env` (gitignored) and `frontend/.env.example`:

```text
VITE_API_BASE_URL=http://localhost:3000/api/v1
```

No secrets in `VITE_` variables.

## Routes

| Path | Page |
|---|---|
| `/` | Home — hero, ask box, how it works, research context |
| `/chat` | Chat, history sidebar, optional learning module / PDF |

`/chat?q=...` sends that question once after an anonymous session exists.

## Anonymous session

On first load, `POST /api/v1/sessions`. `session_id` is stored in `localStorage`. Conversation list comes from `GET /api/v1/conversations?session_id=`. Opening a chat uses `GET /api/v1/conversations/:id?session_id=`.

Clearing site data forgets the session id; server rows remain (expected).

## Language

`en` / `kn` sent on each message and e-content request. Major UI labels are translated. The whole site is not a complete localization.

## Sources and figures

Uses `message.sources[].textbook_page_number` only. Verified textbook crops may appear when the topic matches. No chunk IDs, paths, or internet image search.

## E-content / PDF

`Make a learning module` calls `POST /econtent`. `Download PDF` posts to `/econtent/:id/pdf` and saves a blob. Duplicate clicks are blocked while a request is in flight.

## Limitation

Not production-ready. Kannada generation quality follows local llama3. Topic switching is heuristic, not perfect.

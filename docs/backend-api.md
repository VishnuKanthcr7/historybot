# HistoryBot backend API (Phase 7)

Public API is **Express**. The browser must not call MySQL, Chroma, Ollama, or the Python RAG port.

```
Browser → Express :3000 → MySQL historybot
                        → Python RAG 127.0.0.1:8000 → Chroma + Ollama
```

## Run locally

From the repo root, start the internal RAG service (keep it running):

```text
python scripts/rag_internal_server.py
```

In another terminal:

```text
cd backend
npm start
```

Requires `.env` with `MYSQL_*` and `INTERNAL_RAG_SECRET` (never commit `.env`).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | API + MySQL ping |
| POST | `/api/v1/sessions` | Anonymous session UUID |
| POST | `/api/v1/conversations` | `{ session_id, title? }` |
| GET | `/api/v1/conversations?session_id=` | Conversation list for **this** session |
| GET | `/api/v1/conversations/:id?session_id=` | Messages for **this** session only |
| POST | `/api/v1/conversations/:id/messages` | `{ session_id, message, language }` |
| POST | `/api/v1/econtent` | `{ session_id, conversation_id?, topic, language }` grounded module |
| GET | `/api/v1/econtent/:id?session_id=` | Stored module for this session |
| POST | `/api/v1/econtent/:id/pdf` | `{ session_id }` PDF download |
| GET | `/api/v1/images/:id` | Verified textbook figure (PNG) |

`language`: `en` or `kn`. Message length 1–2000 characters.

Successful assistant payload:

```json
{
  "message": {
    "id": "...",
    "role": "assistant",
    "content": "...",
    "language": "en",
    "grounded": true,
    "sources": [{ "textbook_page_number": 10 }],
    "created_at": "..."
  }
}
```

## Errors

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid request." } }
```

Codes include `VALIDATION_ERROR`, `SESSION_NOT_FOUND`, `CONVERSATION_NOT_FOUND`, `FORBIDDEN`, `RAG_UNAVAILABLE`, `RAG_TIMEOUT`, `RATE_LIMITED`, `NOT_FOUND`, `DATABASE_ERROR`.

## Analytics (anonymous)

Uses existing enum: `SESSION_STARTED`, `NEW_CHAT`, `QUESTION_ASKED`, `ANSWER_GENERATED`, `E_CONTENT_GENERATED`, `PDF_DOWNLOADED`. No name/email/phone/IP.

## Internal RAG

`POST http://127.0.0.1:8000/internal/query`, `/internal/econtent`, `/internal/econtent/pdf` with header `X-Internal-Secret`. Not public.

## Security

Helmet, CORS (`CORS_ORIGIN`), rate limit, 32kb JSON body, parameterized SQL, UUID checks, no static `/data` or textbook PDF.

## Tests

With both processes running:

```text
cd backend
npm run smoke
```

RAG-down check (Express up, Python stopped):

```text
RAG_DOWN=1 npm run smoke
```

Not production-ready. Kannada quality follows Phase 6 llama3 limits.

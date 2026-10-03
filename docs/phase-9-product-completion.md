# Phase 9 — Core product completion

Status: COMPLETE (awaiting review). Not production-ready. Deployment was not started.

## What this phase did

Reuse Phase 6–8. No new database engine. No Chroma rebuild. `LLM_PROVIDER=ollama` unchanged.

## RAG / topic switching

`rag/engine/classify.py` labels `STANDALONE`, `NEW_TOPIC`, `FOLLOW_UP`.

- Named-topic change (Babar → Shivaji) is `NEW_TOPIC`: retrieval uses the latest question only.
- Pronoun follow-ups use the last student question for rewrite, not the full assistant dump.
- Exercise chunks are down-ranked (`+0.12` distance), not deleted.
- `RAG_DISTANCE_THRESHOLD` stays **0.55** (env-configurable).

Observed (local llama3, 2026-10-03):

| Case | Result |
|---|---|
| Who was Babar? then Who was Shivaji? | NEW_TOPIC, Shivaji pages 10 |
| Who was Shivaji? then What did he do in administration? | FOLLOW_UP, rewrite to Shivaji administration, pages 10–11 |
| GDP of India | refusal |
| Wikipedia / Plassey injection | refusal |

## Kannada

Retrieval still rewrites to English. Generation asks for Kannada script and regenerates if the answer has no Kannada characters. Quality remains **weak** (local llama3). Example for `ಶಿವಾಜಿ ಯಾರು?` used Kannada script and page 10, but wording is awkward and not classroom-ready.

## E-content

`generate_econtent` retrieves textbook evidence and asks llama3 for JSON sections. Unsupported topics (`World War II`, `GDP`) are blocked if those phrases are not in the evidence. Supported topics omit empty sections. Student API never sees chunk IDs.

Analytics event: existing `E_CONTENT_GENERATED` (not a new enum value).

## PDF

Python ReportLab, fonts in `data/fonts/` (Noto Sans + Noto Sans Kannada, SIL OFL). Header/footer, page numbers, structured sections, textbook page citations, optional textbook-crop figures. Temp PDFs in `data/generated/` (gitignored). No filesystem paths in the PDF body.

## Verified images

Crops from the Chapter 5 textbook PDF only:

- Akbar portrait (printed page 3)
- Akbar’s kingdom map (page 4)
- Panch Mahal (page 6)
- Maratha Kingdom / Shivaji ruling areas map (page 11)

There is **no** confidently cropped Taj Mahal or Red Fort figure and **no** Shivaji portrait (map only). License text states these are textbook crops for this prototype, not a public-domain photograph license.

Served as `GET /api/v1/images/:id` (no file path in JSON).

## Conversation list

`GET /api/v1/conversations?session_id=` returns id, title, timestamps for that session only. Frontend uses this list; localStorage keeps the anonymous session id.

## Analytics (anonymous, existing table)

`SESSION_STARTED`, `NEW_CHAT`, `QUESTION_ASKED`, `ANSWER_GENERATED`, `E_CONTENT_GENERATED`, `PDF_DOWNLOADED`.

No name, email, phone, dashboard.

## Schema

Additive only on `verified_images`: `textbook_page_number`, `alt_text` via seed script. No DROP. `historybot` was not reset. Odoo/Postgres untouched.

## Security

Helmet CORP `cross-origin` so `:5173` can load `:3000` images. E-content/PDF require session ownership. Internal RAG secret unchanged. No `VITE_` secrets.

## Limitations

- llama3 is slow and Kannada is poor.
- E-content JSON can still mix awkward phrasing; sections are omitted when empty but the model can still be sloppy inside a supported topic.
- Threshold 0.55 is still provisional.
- Clearing browser data loses the anonymous session id (expected).
- Not deployed.

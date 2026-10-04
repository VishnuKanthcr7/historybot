# Phase 20 — E-content and PDF quality

## 1. Existing E-content pipeline

Inspected implementation (not docs):

1. React `Chat.jsx` → `requestEcontent(last user question)` → Express `POST /api/v1/econtent`.
2. Express `econtentController` calls FastAPI `POST /internal/econtent` (timeout `RAG_ECONTENT_TIMEOUT_MS`).
3. `generate_econtent` retrieves primary textbook chunks, builds a Phase 17/19 evidence pack (`BROAD_TOPIC`), runs `generate_from_plan` for the detailed explanation, then fills remaining JSON fields.
4. Grounded JSON is stored in MySQL `econtent_documents`.
5. `POST /econtent/:id/pdf` sends stored JSON to `render_econtent_pdf` (ReportLab, bundled Noto Sans + Noto Sans Kannada).
6. Frontend `EcontentPanel` renders sections and `downloadEcontentPdf`.

Phase 19 leftover: optional JSON fields were filled after many LLM section calls (5–8 minutes), introductions mentioned “evidence”, citations were group pages without per-item validation, PDF treated `##` as plain text, and the UI could stringify objects.

Not changed: llama3, nomic-embed-text, Chroma `historybot_class9_ss_v2`, retrieval architecture, Express/React app shape.

## 2. Changes made

- **Module assembly:** title, introduction, learning objectives, people, terms, timeline, key points, revision, and exam/MCQ fallbacks are built from the filtered coverage plan and textbook sentences. One optional LLM call remains for exam/MCQ JSON; malformed or ungrounded output is dropped and replaced by pack-internal questions.
- **Language:** student text is stripped of RAG/internal phrasing. Introductions no longer mention evidence packs.
- **Terms:** only family-relevant labels (Mughal / Maratha / Ahom) that actually occur in the plan chunks. Definitions are textbook sentences, not external glosses.
- **People:** coverage-group rulers (or Ahom names found in those chunks) with page lists. One-off unrelated names are not promoted.
- **Timeline:** years `12xx–18xx` copied from chunk sentences; omitted if fewer than two dated sentences.
- **Citation validation:** every listed page must belong to the evidence pack. Section, person, term, exam, and MCQ pages are filtered. Unused pack pages are not attached to every section.
- **Empty-section protection:** placeholders (`null`, `{}`) dropped; empty arrays omitted; no supplementary-book field.
- **PDF:** `##` headings in the detailed explanation render as headings; per-section textbook pages; no “Additional school-book” labels; Noto fonts unchanged. Bold Noto file is optional (falls back to regular).
- **Frontend:** richer detailed-explanation headings, Answer labels on exam/MCQ, page notes, section citation list, no `JSON.stringify` of objects, wait banner while a module generates, default E-content timeout 15 minutes so a complete module is not cut off.

## 3. Mughals module result — GOOD

- Time: **143.5 s** (re-run after term/citation hardening).
- Groups in explanation: Babur, Sher Shah, Akbar, Shah Jahan, Aurangzeb.
- People: those five rulers, each with pages.
- Terms: Mansab, Taj Mahal, Jagir, Vakil, Diwan (Din-e-Ilahi omitted — not in this pack’s chunks).
- Citations used: printed pages **3, 4, 5, 7, 8, 9, 10, 11**. No Ahom-only pages.
- PDF: **PASS**, 18 451 bytes, section page citations present.

## 4. Shivaji module result — GOOD

- Time: **91.6 s**.
- Explanation covers Shivaji with related Maratha framing from the pack, not a generic extra-textbook biography.
- Terms include Ashtapradhan, Chauth, Sardeshmukhi, guerrilla warfare, Swarajya, Jagir.
- Pages: **9, 12, 13, 14, 15**.
- PDF: **PASS**, 16 531 bytes.

## 5. Maratha module result — GOOD

- Time: **206.8 s**.
- Not Shivaji-only: Baji Rao I and Madhav Rao I groups plus Peshwa term when present in evidence.
- Pages: **9, 11–17**.
- PDF: **PASS**, 19 045 bytes.

## 6. Ahom Dynasty — GOOD (supported in Ch. 17)

- Time: **80.6 s** (re-run after dropping Mughal terms from Ahom-only plans).
- People: Sukaphaa, Lachit Borphukan, Gadadhar Singha when those strings appear in Ahom chunks.
- Terms: Saraighat, Charaideo only.
- Pages: **1, 2, 3, 17**.
- PDF: **PASS**, 16 164 bytes.

## 7. Citation validation

Pack pages are the allow-list. Section citations map titles (Babur, Akbar, Aurangzeb, Shivaji, etc.) to those pages. Ahom no longer cites Taj Mahal. Mughals does not cite Ahom pages 1–2. A citation with no remaining valid page is omitted rather than invented.

## 8. JSON validation

Malformed model JSON is ignored for that section only. Allowed keys are fixed. Empty/placeholder values are removed so the frontend never renders `{}` or `null`. One failed exam/MCQ call does not delete the detailed explanation.

## 9. PDF validation

All four PDFs start with `%PDF`, are non-empty, include HistoryBot chrome and page numbers, render headings, and contain textbook page lines. No `chunk_id`, drive paths, raw JSON, RAG terms, or supplementary-source labels in extracted text.

Fonts: `data/fonts/NotoSans-Regular.ttf` and `NotoSansKannada-Regular.ttf` (SIL OFL). `NotoSans-Bold.ttf` is not present; headings use the regular face.

## 10. Frontend E-content result

`EcontentPanel` now separates `##` lesson headings, shows page notes on people/terms/questions, labels MCQ answers, and lists section pages. `Chat.jsx` shows a waiting message while generation runs. The learning-module button remains disabled until there is a user question (unchanged). Live chat page at `http://localhost:5173/chat` shows **Make a learning module**. Full in-browser generate+download was not waited through (2–3 minutes per topic plus API stack); download still uses `blob` + `Content-Disposition` PDF, not JSON.

## 11. PDF download result

API path unchanged: stored module → ReportLab → `application/pdf` attachment. Script-generated PDFs are valid. No raw JSON download path.

## 12. Generation times

| Topic | Seconds | PDF |
|-------|---------|-----|
| Mughals | 143.5 | PASS |
| Shivaji | 91.6 | PASS |
| Marathas | 206.8 | PASS |
| Ahom Dynasty | 80.6 | PASS |

Faster than Phase 19’s 5–8 minute modules because most JSON fields are deterministic. Correctness was not traded for speed: detailed explanation still uses section-by-section generation.

## 13. Remaining limitations

- **P2:** Multi-call detailed explanation is still the slow part (~1.5–3.5 minutes).
- **P2:** Din-e-Ilahi may be omitted from the Mughals term list when that passage is not in the pack.
- **P2:** Noto Bold is missing; PDF headings are regular weight.
- **P2:** Exam/MCQ fallback questions can sound organisational (“which person is in this section”) when the model JSON fails validation.
- **P2:** Shivaji modules may still include a “The Marathas” coverage group from neighbouring textbook text.
- No P0 grounding failures in this suite. Do not claim the modules are complete or hallucination-free.

Do not start Phase 21 from this document.

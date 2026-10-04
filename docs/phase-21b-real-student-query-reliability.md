# Phase 21B — Real student query reliability

## Source policy

Student-facing facts still come only from the indexed Karnataka State Board Class 9 Social Science 2026–27 English textbook (Chroma `historybot_class9_ss_v2`). No Wikipedia, web, NCERT, supplementary PDFs, or llama3 memory. Kannada remains unavailable until a Unicode corpus exists.

## Observed browser failures and root causes

| ID | Query | Root cause |
| --- | --- | --- |
| A | `tell me about shivaji` failed while `who was shivaji?` passed | Casual phrasing stayed DIRECT. Semantic search for “tell me about …” often missed the distance/overlap gate, so the topic map was never seeded. |
| B | `tell me everything about the mughals` | Broad pack mixed in Ahom-framed chunks and over-weighted early pages. |
| C | Akbar + current PM | `minister` inside “prime minister” was treated as administration; mixed query contaminated Akbar retrieval. |
| D | `give me 10 mcqs about the mughals` | Exam fallback wrote 3 open questions, not A/B/C/D MCQs, and stopped at 5. |
| E | `more` after MCQs | Follow-up was rewritten as generic retrieval, not MORE_OF_PREVIOUS_TASK=MCQ. |
| F | easy English | Prompt hint existed; output still copied dense textbook sentences. |
| G | extra citations | Plan path cited every section page in the pack, not pages supporting the final answer. |

## Changes

- `rag/engine/intent.py`: conversational padding, more-task, MCQ count, easy-English, entity focus query.
- Named-entity retrieval seeds from the existing topic map when aliases match, without lowering `RAG_DISTANCE_THRESHOLD`.
- `tell me about <person>` → EXPLANATION; `everything/teach me about the mughals` → BROAD_TOPIC.
- Mixed off-domain clauses no longer set the administration facet.
- Mughal broad packs drop Ahom-primary chunks and page-1 TOC material.
- Deterministic 10-item MCQs from the EvidencePack; `more` / `more questions` continue MCQs when the previous task was MCQ.
- Citations use `supporting_evidence` overlap, not the full pack page list.
- Verified images prefer the asked person; Taj images only if Taj is in the question or answer.

## Tests

`scripts/phase21b_query_reliability.py` covers the browser failures plus paraphrases.

## Known limitations

- Local llama3 is still slow on broad/MCQ turns.
- MCQ distractors are other textbook sentences and can look long or slightly OCR-noisy.
- Akbar textbook chunks still mention Sher Shah/Humayun as surrounding narrative; mixed PM questions now refuse the PM part and keep Akbar-grouped evidence.
- Do not claim 100% accuracy or hallucination-free behaviour.

# Phase 21C — Student answer quality, MCQ integrity, conversation-state integration

## Source policy

Student-facing facts still come only from the indexed Karnataka State Board Class 9 Social Science 2026–27 English textbook (Chroma `historybot_class9_ss_v2`). No Wikipedia, web, NCERT, supplementary PDFs, paid APIs, or llama3 memory. Kannada remains unavailable until a Unicode Nudi corpus exists.

## 1. Real browser failures (after Phase 21B)

| ID | Query | Browser result |
| --- | --- | --- |
| A | `tell me about shivaji` | PASS. Must not regress. |
| B | `bro can you explain akbar in easy english` | Partial: finds Akbar but can open with Sher Shah and still sounds textbook-like. |
| C | `tell me everything about the mughals` | PASS (Babur–Aurangzeb, no Ahom). Must not regress. |
| D | mixed Akbar + current PM | PASS functionally. Must not regress. |
| E | `give me 10 mcqs about the mughals` | Ten items, but 1–5 repeated as 6–10; options were long unrelated sentences. |
| F | `more` after those MCQs | **Exact same 10 MCQs again.** Isolated Python tests had passed. |
| G | `tell me about bajirao in easy english` | Topic detection OK; answer used only a thin slice of page 15. |

## 2. Root causes

The browser `more` break was not mainly inside the isolated MCQ function.

1. **Express `loadHistory` sliced every message to 2000 characters.** Ten MCQs were far longer, so Python often received a truncated previous answer.
2. **RAG `task` was not persisted.** Fingerprints, task type, topic, and count were dropped after the HTTP response.
3. **Python inferred MCQ continuation only from last user + last assistant text.** After truncation, skip-stems were incomplete, so the generator rebuilt the same first items.
4. **The generator itself repeated templates.** Three stem patterns over the same sentences produced questions 1–5 again as 6–10 even on the first turn.
5. **Easy English and “tell me about” used a small LLM section budget** (`max_tokens=280`, few chunks), so Baji Rao answers collapsed to one or two facts even when more textbook sentences existed.
6. **Neighbouring-ruler lead-in** came from untrimmed chunk prefixes (Sher Shah text before Akbar in the same passage), not from a wrong topic map.

Isolated Phase 21B tests passed “more” because they passed the **full** previous answer in-process.

## 3. Architecture changes

No new tables, no Chroma replacement, no textbook replacement, no Odoo/PostgreSQL change.

- Assistant `messages.chunk_ids` JSON may now be either a chunk-id array (old) or `{historybot_task: true, ids, type, topic, entity, count, fingerprints, generation_index}`.
- Express `loadHistory` loads `chunk_ids`, does not truncate MCQ task messages to 2000 chars, and sends `task_state` to `/internal/query`.
- FastAPI `QueryRequest` accepts `task_state`; history items may include `task_state`.
- `answer_question(..., task_state=)` prefers persisted task type over guessing from truncated text.

Frontend `sendMessage` already sends the same `conversation_id` + `session_id`. That path was not the break.

## 4. MCQ algorithm

Deterministic evidence-to-slot pipeline (no extra llama3 call):

1. Build the usual coverage plan from the EvidencePack.
2. Extract short facts (language, place, year, office, work, term, person) with patterns over textbook text.
3. Build four short options from other facts of the same kind in the pack. Person distractors may use other section titles in the same pack.
4. Skip a question if four grounded options cannot be formed. Do not invent extra historical facts to pad distractors.
5. Fingerprint `normalize(question + answer)`.
6. Round-robin across coverage groups so a Mughal set is not all Babur.
7. If the safe unique count is below the request, return the safe set and say the textbook does not support more of this kind.

## 5. Conversation-state changes

Stored on the assistant message, not as student PII:

- `type`: `MCQ` or `EXPLAIN`
- `topic` / `entity`
- `count`
- `fingerprints` (short hashes, not full question text)
- `generation_index`

`more`, `more questions`, `give me more`, `another 10`, `continue`, `more mcqs`, `next 10`, `give me another set` continue that task.

## 6. Integration tests

- `scripts/phase21c_unit.py` — intent, fingerprints, MCQ uniqueness (Chroma pack, no Express).
- `scripts/phase21c_integration.py` — public Express session/conversation/messages path.
- `scripts/phase21c_browser_sim.py` — truncated history vs persisted `task_state`, plus the 18-query matrix in-process.

## 7. Answer completeness

Entity EXPLANATION packs keep more same-entity chunks (up to 12, seed 8). Single-person sections may use more passage text and a higher token budget so “tell me about X” can use the facts that are actually in the pack. The model is still forbidden to add outside facts.

## 8. Easy English

Easy English is applied **after** the EvidencePack is built. It is a style instruction on the same passages (“do not drop facts to make it simple”), not a retrieval filter.

## 9. Citations

Section combiner appends `[Page N]` / `[Pages …]` from that group’s pages. A global citation list is omitted when section tags are already present. Source chips still use `supporting_evidence` on the final text.

## 10. Images

`namedPerson` now includes Baji Rao so Akbar/Shivaji images are not attached to a Baji Rao question. No web image search. If no verified Baji Rao image exists, none is shown.

## 11. Performance

MCQ generation does not call llama3. `more` does not regenerate the previous fingerprint set; it skips those hashes. Broad explanations still make one llama3 call per coverage section. Completeness raises tokens only for small (one- or two-group) explanation plans, not for five-ruler Mughal overviews.

## 12. Remaining limitations

- Single-person MCQ sets (Shivaji, Akbar, Baji Rao) often cannot safely reach 5–10 unique 4-option items because distractor pools are smaller than a dynasty-wide Mughal pack. The generator stops rather than inventing options. `another 10` after a thin Akbar set may return a limit note instead of 10 new questions.
- Slot extractors can miss facts that are only implied, and can still write somewhat generic “which person is this section about?” items when richer slots are missing.
- Akbar passages in the textbook still mention Sher Shah; focusing the passage on the Akbar mention reduces but does not guarantee a Sher Shah-free first sentence.
- Easy English still depends on local llama3 paraphrasing quality.
- Local llama3 often paraphrases only the first Baji Rao sentences. If that output is much shorter than the packed passages, Phase 21C now falls back to a longer extract from the same EvidencePack rather than inventing facts. Easy English may then be less smooth.
- An older RAG process can remain bound to port 8000; Express must talk to a RAG process that loaded the 21C code (`task_state` + new MCQ builder). Integration was verified on a 21C RAG at 8001 / Express 3001.
- Do not claim 100% accuracy, hallucination-free behaviour, or production-readiness.

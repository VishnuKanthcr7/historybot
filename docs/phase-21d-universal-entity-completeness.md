# Phase 21D — Universal entity completeness and Easy English coverage

Student-facing facts still come only from the indexed Karnataka State Board Class 9 Social Science 2026–27 English textbook (Chroma `historybot_class9_ss_v2`). No Wikipedia, web, NCERT, supplementary PDFs, paid APIs, or llama3 memory. Kannada remains unavailable until a Unicode Nudi corpus exists.

This is not claimed production-ready and not claimed 100% accurate.

## 1. Original Baji Rao failure

Query: `tell me about bajirao in easy english`

Public-path answer collapsed to roughly:

> Thus he established the fame of the Marathas. Baji rao I: After the death of Balaji Vishwanath, his eldest son, Baji Rao I, was appointed as Peshwa. Although he was only 19 years old, he was an unparalleled warrior.

Pages 15–16 of the textbook also contain campaigns (Gujarat, Malwa, Karnataka), Chauth/Sardeshmukhi, the Bhopal battle, Narmada–Chambal compensation, Salcet/Basin/Janjira, Pune as centre, and the later Maratha union names. Those facts were not in the student answer.

## 2. Root cause

Retrieval was not the main failure. After entity collection, the EvidencePack already held three Baji Rao–subject chunks on pages 15–16 (Bhopal, Chauth, etc.), and the entity coverage plan had five groups.

The collapse happened after generation:

1. Easy English / llama3 sometimes shortened the rewrite.
2. Completeness validation treated `[Pages 15, 16]` as an unsupported proper name (`Pages`), so `validate_answer` failed on an otherwise grounded draft.
3. The structured fallback then called `readable_extract` with a 3-sentence / 42-word cap, which kept only the appointment/warrior fragment (including a broken OCR join: “With the intention of expanding the Thus he established…”).
4. Alias substring matching had also been able to treat “Balaji Baji Rao” as Baji Rao I; that is now masked generically by neighbouring-title first tokens, not by a Baji Rao `if`.

Easy English did not shrink the pack. It did not need to: the pack was already complete. Validation + extractive fallback discarded the rest.

## 3. Architecture change

No new Chroma collection, no textbook change, no Odoo, no paid APIs, llama3 unchanged.

- New `rag/engine/entity.py`: generic entity subject scoring, segment split on `Name :` headings, complete primary-chunk collection, evidence groups derived from retrieved sentences.
- `build_evidence_pack` EXPLANATION + detected entity uses `collect_entity_chunks` (topic map + same/adjacent pages, exclude other-heading / incidental mention).
- `generate_entity_explanation`: extractive complete draft from groups → one llama3 rewrite (Easy English is style only) → at most one targeted regen → keep the draft if still thin or missing groups.
- If `validate_answer` still fails, fallback rebuilds from the **entity plan**, not from the 3-sentence extract.
- Citation labels `Page`/`Pages` are not treated as unsupported claims.

## 4. Universal entity evidence algorithm

For any detected textbook entity key (from existing `TOPIC_ALIASES` / `RULER_KEYS`):

1. Start from topic-map chunks for that key plus retrieval hits.
2. Expand to same printed page and adjacent pages in the primary corpus.
3. Split OCR blobs on heading-like `Title :` boundaries.
4. Keep a segment only if subject score ≥ 3: heading starts with the longest matching alias, dominant named entity, or the segment leads with the entity. Other-heading and incidental mention are excluded.
5. Generic prefix mask: if an alias match is immediately preceded by another catalogued entity’s first title token, do not count it (this is how “Balaji Baji Rao” is not treated as Baji Rao I, without a person-specific branch).
6. Deduplicate OCR repeats; preserve page order.

There is no `if entity == "bajirao"`.

## 5. Coverage validation

Groups are created only when sentences match generic cues (appointment/age, campaign/battle, tax/rule, fame/glory, leftover details). Empty groups are omitted.

After generation, each group is COVERED if distinctive markers from its sentences appear in the answer. Missing important groups trigger **one** regen that injects the missing extractive evidence, then a draft fallback. No unbounded loop.

Target: ≥ 90% of important groups when the textbook actually contains them. Do not invent groups.

## 6. Easy English behaviour

Easy English is a rewrite instruction on the complete draft:

- Class 9 short sentences and simple words
- Keep names, places, events, and taxes that are in the draft
- Do not summarise away textbook facts merely to be short

It does not change retrieval, pack size, or coverage targets.

## 7. Fallback behaviour

Fallback must use the full entity groups. It must not emit the first two OCR sentences only.

Sentences that dangle on `the`/`of`/`and` (broken OCR) are skipped. Duplicate heading copies inside a chunk are deduped.

## 8. Citation behaviour

Page labels come from groups actually represented in the final text. Baji Rao answers after the fix cite `[Pages 15, 16]`, matching the pack. Unrelated retrieved pages are not added.

## 9. Regression results

`scripts/phase21c_unit.py`: PASS.

`scripts/phase21d_regression.py` (in-process llama3 + Express `127.0.0.1:3001` → RAG `127.0.0.1:8001`): **31 / 31 PASS**.

Includes: Baji Rao / Easy English completeness (Bhopal/Malwa/Chauth-class facts), Shivaji, Akbar, Babur, Sher Shah / Shah Jahan / Aurangzeb packs, Marathas + Mughals (no Ahom), mixed Akbar + current PM, Wikipedia refusal, Mughal MCQs + `more` (no stem overlap), Baji Rao `more` / `what did he do?` / switch to Akbar, Express Baji Rao + `more` + MCQ `more`.

Port 8000 was still occupied by an Access-Denied process, so the Vite UI default (`localhost:3000`) could not load this code. Public-path verification of 21D used Express **3001** against RAG **8001**.

## 10. Browser / public path

| Path | Result |
| --- | --- |
| In-process `answer_question("tell me about bajirao in easy english")` | ~197–215 words; Peshwa at 19, Pune, Gujarat, Malwa, Karnataka, Nizam/Bhopal, Portuguese/Siddhis, Shivaji II; `[Pages 15, 16]`. |
| Express POST `/conversations/:id/messages` on :3001 | Same complete Easy English answer (201, 197 words); `more` stayed on Baji Rao. |
| Vite `localhost:5173` → Express :3000 → RAG :8000 | **Still the pre-21D thin answer** (appointment/warrior only, page 15). RAG PID on 8000 could not be killed (`Access is denied`). Default UI is not running 21D until that process is replaced. |

## 11. Remaining limitations

- llama3 still paraphrases (e.g. “collected taxes” instead of always saying Chauth and Sardeshmukhi). Extractive draft retains those words when the rewrite is rejected as thin.
- OCR joins and heading duplicates remain in source chunks; heuristics skip some fragments but not all.
- Topic-switch extractive fallback can still leak a neighbouring heading sentence inside a mixed page blob (seen once in an Akbar switch preview mentioning Shah Jahan).
- Entity collection depends on the existing alias catalog. A person with no alias key is not a first-class entity pack.
- Port 8000 leftover process blocks the default UI until an administrator can stop it.
- Not production-ready; not 100% fact coverage.

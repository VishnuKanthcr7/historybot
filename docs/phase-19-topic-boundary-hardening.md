# Phase 19 — Topic boundary and answer quality hardening

## 1. Phase 18 baseline

Phase 18 (`6b9fbf0e5327bfda3ca74e30c1a9ec8110181350`) already:

- built a coverage plan from the final evidence pack
- generated broad answers section-by-section
- regenerated missing groups once
- cited pages from groups that appeared in the final answer
- kept the approved Class 9 Karnataka 2026–27 English textbook as the only student-facing factual source

Remaining Phase 18 issues:

- Aurangzeb evidence was often merged into neighbouring Shah Jahan / Akbar groups (`max(ruler_counts)` on mixed chunks).
- Ahom material on early chapter pages could enter Mughal (and sometimes Maratha) packs because “Mughal” appeared in Ahom–Mughal war passages, or because one Aurangzeb mention overrode an Ahom-framed chunk.
- Some section lead-ins named “evidence” or repeated the heading.
- Optional E-content JSON fields (learning objectives, people, key points) were sometimes omitted when the JSON call failed.

## 2. Aurangzeb grouping issue

Root cause: `_group_key` assigned a chunk to the ruler with the highest name count. A Shah Jahan page that mentioned Aurangzeb as prince, or an Ahom page that mentioned Aurangzeb once, won the Aurangzeb slot. Meanwhile dedicated Aurangzeb chunks on printed pages 8–9 were dropped by one-chunk-per-page diversification, so the plan never had an Aurangzeb group.

Fix:

- Prefer an Aurangzeb group only when the passage is headed “Aurangzeb” or Aurangzeb mentions strictly outnumber other named rulers.
- After Mughal pack assembly, `fill_missing_rulers` inserts a missing Babur / Sher Shah / Akbar / Shah Jahan / Aurangzeb chunk from the topic map if the pack lacks that group.
- Mixed OCR that starts with leftover Taj Mahal text and then “Aurangzeb” is trimmed at the first Aurangzeb mention before section generation.

## 3. Ahom contamination issue

Root cause: topic tags treated “Ahom + Mughal” as Mughal evidence. Page-number filters (`page <= 2`) missed later Ahom–Mughal struggle chunks. A single Aurangzeb mention on an Ahom-framed Charaideo / Sukaphaa passage assigned that chunk to Aurangzeb.

Fix:

- `ahom_primary_chunk` scores Ahom hints (`ahom`, `charaideo`, `sukaphaa`, `lachit`, `saraighat`, `jayadhwaj`) against named-ruler counts. If the passage is Ahom-framed, it is not Mughal/Maratha evidence even if Aurangzeb appears once.
- `primarily_other_dynasty` drops Ahom-primary chunks for both Mughal and Maratha families.
- `filter_plan` drops the `ahom` group unless the question is about the Ahoms.
- Comparison context is kept when a named Mughal/Maratha ruler dominates the chunk.

Ahom is **exposed** for explicit questions. Indexed Ch. 17 pages 1–3 (and exercise page 17) support “Explain the Ahom Dynasty.”

## 4. Topic / entity boundary solution

Grouping uses the chunk’s own text and metadata, not “everything on this printed page is the same topic.”

- `chunk_group_key` / `_heading_key` read the chunk body and short heading lines.
- One printed page can contribute both a Shah Jahan chunk and an Aurangzeb chunk.
- Maratha continuation after Sambhaji (Rajaram, recapture) is grouped as Maratha when those names dominate, not as an Aurangzeb administration section.
- Shivaji administration remains entity-filtered (pages 12 and 14 in this run); unrelated Aurangzeb muhtasib material is not included.

Relevant context that names another ruler for comparison is not auto-deleted. Unrelated Ahom-only narrative is removed from Mughal and Maratha answers.

## 5. Section lead-in and heading improvements

- Section prompts forbid “according to the evidence”, “retrieved evidence”, “chunks”, RAG, Chroma, and model talk.
- Generated text is stripped of those lead-ins and of a duplicated heading line under `## Title`.
- Headings come only from groups present in the filtered plan (e.g. Babur, Sher Shah, Akbar, Shah Jahan, Aurangzeb). No memorised textbook outline is injected.

DIRECT questions still use the Phase 18 short pipeline (no coverage plan).

## 6. Citation changes

- Chat citations still use `section_pages` of groups that appear in the final answer.
- E-content adds `section_citations` (group title → printed pages), e.g. Babur → [3], Aurangzeb → [9].
- Module-level `textbook_source_pages` is the union of those used pages, not the entire raw retrieval set.
- Mughals broad answer in this run cited 3, 4, 5, 7, 8, 9, 10, 11 (not Ahom-only 1–2).

## 7. E-content changes

Architecture unchanged (pack → coverage `detailed_explanation` → remaining JSON specs).

If the model omits a field, `_fill_grounded_gaps` fills only from existing coverage groups:

- learning objectives named after grounded group titles
- key points / important people / exam answers from `readable_extract` of those groups
- revision from the already-generated explanation

Facts are not invented to fill JSON. MCQs are not synthesised extractively (wrong options would be ungrounded).

## 8. PDF verification

`render_econtent_pdf` was not restyled.

| Module  | ok   | bytes | debug / supplement / RAG terms |
|---------|------|-------|--------------------------------|
| Mughals | true | 20611 | none                           |
| Shivaji | true | 17870 | none                           |

## 9. Regression results

Script: `scripts/phase19_regression.py`. Approximate wall time ~41 minutes for the full suite.

Coverage grades below are the pipeline `coverage.grade` (group-name coverage), not a new scorer.

### Direct

| id | question | groups | pages | citations | time s | verdict |
|----|----------|--------|-------|-----------|--------|---------|
| D1 | Who was Babar? | (direct) | 3 | 3 | 26.6 | PASS |
| D2 | Who was Akbar? | (direct) | 5–7 | 5 | 32.2 | PASS |
| D3 | Who was Shivaji? | (direct) | 12–13 | 13 | 62.1 | PASS |
| D4 | What was Din-e-Ilahi? | (direct) | 6 | 6 | 11.4 | PASS |
| D5 | Who built the Taj Mahal? | (direct) | 8–9 | 8, 9 | 5.1 | PASS |

### Explanation

| id | question | groups | citations | cov | time s | verdict |
|----|----------|--------|-----------|-----|--------|---------|
| E1 | Explain Shivaji's administration. | shivaji | 12, 14 | GOOD | 42.8 | PASS (no Aurangzeb admin / Ahom) |
| E2 | Explain Akbar's administration. | sher, akbar | 5, 7, 8 | GOOD | 59.8 | PASS |
| E3 | Explain Mughal administration. | akbar, shahjahan | 5, 7, 8, 10, 11 | GOOD | 58.2 | PASS |
| E4 | Explain Maratha administration. | maratha, shivaji, bajirao, balaji, madhav | 9, 12, 14–16 | GOOD | 145.3 | PASS |

### Broad / boundary

| id | question | groups | citations | cov | time s | verdict |
|----|----------|--------|-----------|-----|--------|---------|
| B1 | Explain the Mughals in detail. | babar, sher, akbar, shahjahan, **aurangzeb** | 3–5, 7–11 | GOOD | 110.2 | PASS; headings Babur / Sher Shah / Akbar / Shah Jahan / Aurangzeb; no Ahom |
| B2 | Explain the Marathas in detail. | maratha, shivaji, bajirao, madhav | 9, 11–17 | GOOD | 188.6 | PASS; no Ahom |
| B3 | Tell me more about Shivaji. | maratha, shivaji | 9, 12–15 | GOOD | 68.1 | PASS |
| A1 | Explain the Ahom Dynasty. | ahom | 1, 2, 3, 17 | GOOD | 35.2 | PASS (topic supported in Ch. 17) |

### Follow-up

| id | sequence | cov | time s | verdict |
|----|----------|-----|--------|---------|
| F1 | Who was Babar? → What did he do after that? | GOOD | 32.1 | PASS |
| F2 | Who was Shivaji? → Tell me more about his administration. | GOOD | 102.4 | PASS |
| F3 | Tell me about the Mughals. → Tell me more about Akbar. | GOOD | 172.6 | PASS |

### Unsupported / injection

N1 GDP, N2 Plassey, M1 exact birth date, M2 facts not in the textbook, I1 Wikipedia, I2 another book, I3 training: all **PASS** (refuse or limited-phrase as required). No fallback used on grounded chat cases.

### E-content

| topic | cov | wanted fields present | section citations | ahom | time s | verdict |
|-------|-----|------------------------|-------------------|------|--------|---------|
| Mughals | GOOD | learning_objectives, detailed_explanation, important_people, key_points, exam_questions, revision | Babur[3], Sher Shah[4,5], Akbar[7,8,10], Shah Jahan[9,11], Aurangzeb[9] | no | 465 | PASS |
| Shivaji | GOOD | same wanted set | Marathas[13–15], Shivaji[9,12–14] | no | 330 | PASS |
| Marathas | GOOD | same wanted set | Marathas[11,15], Shivaji[9,12–14], Baji Rao I[16], Madhav Rao I[17] | no | 476 | PASS |

No P0 grounding failures were recorded (`unsupported_claims` empty on inspected broad/Ahom answers). Textbook-only path unchanged (llama3, nomic-embed-text, `historybot_class9_ss_v2`).

## 10. Remaining issues

- **P2:** Some sections still open with a short repeated name before the first sentence (partially stripped).
- **P2:** Multi-call generation remains slow (Mughals ~110s, Marathas ~189s, E-content 5–8 min). No aggressive latency cuts this phase.
- **P2:** Akbar-administration plans can still include a neighbouring Sher Shah group when both appear in the pack.
- **P2:** Mughal packs may still retrieve a leftover Maratha page (e.g. 17) that `filter_plan` drops from sections; it is not cited if unused.
- **P2:** Ahom answers may include exercise page 17 in the citation union.
- **P2:** OCR-split pages still produce uneven Sher Shah / Akbar depth.

No P0 textbook-invention failures were found in this suite. Do not start Phase 20 from this document.

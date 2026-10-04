# Phase 18 — Evidence-to-answer coverage

**Date:** 2026-10-04  
**Base commit:** `1baa33a1e8e10ffbf14cb3bcb489e5b844477898` (Phase 17)  
**Model unchanged:** Ollama `llama3`  
**Chroma unchanged:** `historybot_class9_ss_v2` / `nomic-embed-text`

---

## 1. Root cause

Phase 17 packs for “Explain the Mughals in detail” already held pages **3–11**. Generation still failed because:

1. **One-shot prompting.** All chunks went into a single llama3 call (~1200 tokens out, long context). The model started at the first pages (Ahom/Mughal heading, Babur) and never reached later groups.  
2. **Validator all-or-nothing.** Any unsupported proper name in that long draft discarded the whole answer.  
3. **Fallback used the same mixed pack as bullets**, so students saw TOC/early-page fragments (Phase 17 remainder: Akbar snippet + chapter header; no Shah Jahan/Aurangzeb).

The pack was not empty. The **generation strategy** could not consume it.

---

## 2. Coverage-plan design

`rag/engine/coverage.py` builds groups **only from the FINAL pack**:

- Dominant ruler / topic aliases in each chunk (`extract_topics`, `ruler_counts`)  
- Merge Taj→Shah Jahan, Din-e-Ilahi→Akbar, mansab→Akbar when those keys appear  
- Drop TOC/map/OCR-spaced chunks  
- Drop Maratha-only groups from a Mughals question (and the reverse)

Each group: `key`, textbook-derived `title`, `pages`, `chunks`, `markers`.

No hard-coded Mughal syllabus. If Sher Shah is in the pack, a Sher Shah group appears because the **KTBS chapter** contains him.

---

## 3. Generation strategy

| Type | Strategy |
|---|---|
| DIRECT | Unchanged single llama3 call |
| EXPLANATION / FOLLOW-UP admin | One short section **per coverage group** (usually 1–3) |
| BROAD_TOPIC | Section-by-section from groups, then combine with `##` headings |

Each section sees **only that group’s chunks** (≤4, 280 tokens, 90s timeout). Combined answer is Class 9 English with headings taken from group titles (Babur, Akbar, Shah Jahan, …).

---

## 4. Validation

After combine:

- Existing `validate_answer` / `unsupported_named_items` on the **full** answer vs the pack  
- Coverage score vs group markers: GOOD ≥80%, PARTIAL ≥50%, FAIL otherwise  

Does **not** require every chunk sentence.

---

## 5. Targeted regeneration

If markers for a group are missing: **one** strict rewrite of **that section only**, still using the same pack chunks. No extra retrieval. No model knowledge.

---

## 6. Safe fallback

If a section still fails validation or the LLM times out: **readable sentences** from that group (8–42 words, skip TOC/map/spaced OCR), not raw Chroma and not mid-word bullets.

If the combined coverage is FAIL: rebuild all groups extractively. Prefix remains that only the textbook is used.

---

## 7. Citation coverage

Cited pages are those of **groups whose markers appear in the final answer**, not the entire pack dump. Broad Mughals cited **3, 4, 5, 7, 8, 9, 10, 11**. Supplementary labels are not used.

---

## 8. E-content changes

Same coverage plan + section generation fills `detailed_explanation` / `class9_textbook` **before** JSON extras. Other keys (timeline, exam Qs, MCQs, revision) use **round-robin chunks across groups**, not the first 8 of the pack. Empty HTTP modules are not returned if the pack has text. JSON keys that fail are omitted, not invented.

PDF: existing ReportLab path; empty keys skipped; no debug paths; no Additional school-book heading. Kannada still unavailable.

---

## 9. Regression results

`scripts/phase18_regression.py`  
`tmp/phase18-regression.json` (gitignored)

| Bucket | Result |
|---|---|
| DIRECT D1–D5 | **5/5 PASS** |
| EXPLANATION E1–E4 | **4/4 PASS**, coverage GOOD; Shivaji admin without muhtasib/Aurangzeb admin |
| BROAD B1–B3 | **3/3 PASS**, coverage GOOD |
| Unsupported / injection | **7/7 PASS** |
| Follow-up F1–F3 | **3/3 PASS** |
| **Chat total** | **19/19 + 3/3 follow-ups** |

First e-content attempt crashed (`build_evidence_pack` import dropped). Import restored; resume completed.

---

## 10. Broad Mughals result

Question: “Explain the Mughals in detail.”

- Pack pages: 3–11 (plus leftover 14/17 not used as Maratha groups)  
- Evidence groups generated: **mughal, babar, sher, akbar, shahjahan**  
- Missing groups: **none of those**  
- Citations: **3, 4, 5, 7, 8, 9, 10, 11**  
- Fallback: false  
- Answer has separate **Babur, Sher Shah, Akbar, Shah Jahan** sections, not page-10-only  

**Honest gap:** Aurangzeb did not form its own group (those chunks were absorbed into Shah Jahan / Akbar counts). The answer is substantially more complete than Phase 17, but is **not** a full named Aurangzeb section.

---

## 11. Broad Marathas result

Groups: **shivaji, maratha, aurangzeb, bajirao, madhav**. Not Shivaji-only. Coverage GOOD.

---

## 12. Shivaji result

“Tell me more about Shivaji”: groups shivaji (+ aurangzeb where the textbook describes the conflict). Focused on Shivaji. PASS.

Administration explanation: coverage GOOD, no Aurangzeb bans/muhtasibs.

---

## 13. Remaining limitations

- **P1** Aurangzeb (and some other co-mentioned rulers) can be merged into a neighbour group, so they may not get a heading.  
- **P1** Opening “Mughal rule” group can still narrate Ahom–Mughal clashes from page 3 evidence.  
- **P2** Section lead-ins sometimes say “Here is a short section on…”.  
- **P2** E-content may omit learning_objectives / important_people when JSON fails; detailed_explanation is filled.  
- Latency is worse (many llama3 section calls). Not optimized this phase.

No P0 of “correct pack, empty/wrong-person student answer” on this regression set.

---

Phase 19 was not started.

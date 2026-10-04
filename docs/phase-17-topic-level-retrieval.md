# Phase 17 — Topic-level retrieval and evidence-pack correction

**Date:** 2026-10-04  
**Base commit:** `ae1c2ef08828cfe8d190e2f89a6b054b96f93a21` (Phase 16)  
**Model unchanged:** Ollama `llama3`  
**Embeddings/Chroma unchanged:** `nomic-embed-text`, `historybot_class9_ss_v2` (not rebuilt)

---

## 1. Current retrieval architecture (before this phase)

Student chat (`rag/engine/answer.py`) did:

1. Normalize the question; casual/Kannada/injection shortcuts.  
2. Classify answer **mode** (NORMAL vs DETAILED) from wording (`explain` / `in detail`).  
3. Classify **intent** (STANDALONE / FOLLOW_UP / NEW_TOPIC).  
4. Rewrite follow-ups by prefixing the previous topic (`babar What did he do after that?`).  
5. **Vector search** `retrieve_primary` (`top_k` 10 or 14).  
6. `select_evidence` by distance + token overlap (keep 4–5).  
7. `retrieve_same_pages` for those printed pages.  
8. `expand_evidence` with **page_window 1–2** if overlap ≥ 1 or shared `extract_topics` keys.  
9. Generate with llama3 → validate named claims → **extractive fallback over the selected list**.  
10. Cite via `supporting_evidence` on the generated text.

E-content used the same vector + expand path with `max_keep=8`, then section JSON. Empty Mughals modules happened when `evidence_matches_topic` required the token `mughals` while chunks say `Mughal`.

There was **no evidence-pack object**, **no textbook-derived topic map**, and **no question-type-specific retrieval** (DIRECT vs EXPLANATION vs BROAD_TOPIC).

---

## 2. Problems discovered in Phase 16

| ID | Symptom | Cause in the old pipeline |
|---|---|---|
| P0 | “Explain the Mughals in detail” stayed near **page 10** | Semantic nearest chunks were late “contributions / trade / administration”. Expansion only walked **±2 pages**, so Babur–Akbar–Shah Jahan never entered the pack. |
| P0 | Shivaji administration fallback quoted **Aurangzeb** | DETAILED `page_window=2` + same-page load on mixed pages (esp. **printed 9**: Taj + Aurangzeb + “After Shivaji died…”). Fallback dumped **all selected chunks**, not the admin section. |
| P1 | “What did he do after that?” under-covered Babur | Rewrite kept the name, but search for “after that” did not load the rest of the Babur topic pages. |
| P1 | Mixed “not in the textbook” / exact date | Model answered nearby textbook lines and treated the request as fulfilled. |
| P1 | Mughals e-content empty | Topic overlap `mughals` ≠ `mughal`; all sections omitted → refusal. Citations for other modules used 1–2 pages because the pack was tiny. |

---

## 3. Evidence-pack design

New module: `rag/engine/pack.py`.

`EvidencePack` holds:

- ordered **chunks** (final pack only)
- **question_type**, **topics**, **entity**, **facet**
- **pages**, **retrieved_pages** (raw vector pages)
- **reasons** (why chunks were kept)

Pipeline is now:

```
raw retrieval
→ topic map / type-specific gather
→ same-page continuation (same entity/facet only)
→ entity/facet filter
→ EvidencePack
→ generation
→ validation
→ retry
→ extractive fallback from pack.chunks only
→ citations from pack.chunks that overlap the answer
```

The pack is **relevant, complete enough, topic-bounded, page-ordered**. It does not maximize chunk count (DIRECT ≤ 6, EXPLANATION ≤ 10, BROAD ≤ 12, **page-stratified** so late pages are not dropped).

---

## 4. Topic classification

`classify_question_type` (`rag/engine/classify.py`):

| Type | Examples |
|---|---|
| DIRECT | Who was Babar? What was Din-e-Ilahi? |
| EXPLANATION | Explain Shivaji's administration. Explain Mughal administration. |
| BROAD_TOPIC | Explain the Mughals in detail. Tell me more about Shivaji. |
| FOLLOW_UP | What did he do after that? Tell me more about his administration. |

Intent `FOLLOW_UP` + administration facet reuses the **explanation** pack (Shivaji admin), not the whole biography.

Token overlap now aliases `mughals→mughal`, `marathas→maratha`, `babur→babar` so topic matching works on the KTBS wording.

---

## 5. Broad-topic retrieval

`rag/engine/topic_map.py` builds a **topic → printed pages / chunk ids** index with `collection.get` on **existing** `primary_textbook` chunks only. No Chroma rebuild. No hand-written battle lists.

For “Explain the Mughals in detail”:

1. Topics `{mughal}` expand to the **Mughal family** keys that actually appear in those chunks (Babur, Humayun, Akbar, Shah Jahan, Taj, Aurangzeb, mansab, Sher Shah as a chapter section, etc.).  
2. Ahoms-only opening pages and Maratha-dominant pages (≥11 with more Maratha keys than Mughal keys) are dropped.  
3. Chunks are **round-robin sampled by page** so pages 3–11 are all representable in 12 slots.

Phase 16 vector-only pack: ~page **10**.  
Phase 17 map pack (coverage test): **pages 1, 3–11, …** and **covers expected {3,5,6,8,9,10}**.

Marathas in detail similarly covers **12–15**.

The outline is **not** a generic Mughal syllabus. If a name is not in the KTBS chapter, it is not in the map.

---

## 6. Section / page grouping

- Same printed page: other primary chunks on that page are added **only if** they survive entity/facet filters (Taj on page 9 is not pulled into Shivaji administration).  
- Facet `administration` requires admin vocabulary (`ashtapradhan`, `ryotwari`, `chauth`, `mansab`, `vakil`, …) and rejects rival-ruler-dominant chunks.  
- TOC / map OCR chunks (`CHAPTER – 17`, Arabian Sea + Bay of Bengal) are dropped from packs.  
- Exercise pages are skipped unless the question asks for exercises.

---

## 7. Entity filtering

Ruler keys come from `TOPIC_ALIASES` counts in the **chunk text**.

For Shivaji + administration:

- Keep chunks whose dominant person is Shivaji **and** that contain admin terms (`Administration : Shivaji`, jahagir, Chauth, …).  
- Drop “After Shivaji died, he imprisoned Sambhaji” (Aurangzeb narrative; rival counts ≥ Shivaji).  

Live pack for “Explain Shivaji's administration.”: **pages 12, 14** (not 9).

Contextual Shivaji–Aurangzeb fighting can remain on **person-broad** “Tell me more about Shivaji,” where the facet is not administration.

---

## 8. Fallback safety

Fallback runs only on **`pack.chunks`**, ranked by query overlap (≥2 tokens preferred).

If nothing relevant remains, the student text is:

“The provided textbook does not give enough information to answer this fully.”

It does not iterate raw Chroma hits. Citations for fallback also go through `supporting_evidence` on those pack chunks.

**Remaining issue:** if validation still fails on a **broad** pack, llama3 can fall back to early-page bullets (chapter header / Akbar slice). Pack completeness ≠ generation completeness. See §14.

---

## 9. Follow-up handling

- Pronouns resolve via previous `extract_topics` (`he` → Babur).  
- FOLLOW_UP with no previous entity asks: “Which person or event from the textbook should I continue with?”  
- Babur + “after that” loads **Babur topic-map chunks**, not only the “after that” embedding. Sequence A in regression: **PASS** (entity stayed Babur).  
- Shivaji + “his administration” uses the **admin explanation pack** (pages **12, 14**): **PASS**.  
- Mughals → “Tell me more about Akbar” is **NEW_TOPIC / BROAD person Akbar** (does not replay the whole dynasty): **PASS** (`resolved_topic=akbar`).

---

## 10. Citation mapping

Citations are computed from the **final pack** with `supporting_evidence`, not from every retrieved neighbour.

Supplementary PDFs are still excluded on the student path.

Broad answers may cite several pages. Direct answers usually cite one supporting page.

E-content citation can still collapse to 1–2 pages if the generated JSON only overlaps those pages — pack pages are wider than cited pages (see §12).

---

## 11. E-content retrieval

`generate_econtent` now builds a **BROAD_TOPIC evidence pack** (same map as chat) before section JSON.

If title/intro/class9 JSON all fail, it fills `class9_textbook` from **extractive pack snippets** instead of returning an empty module. It does not skip named-entity validation on JSON sections.

No supplementary PDFs. No general-knowledge outline.

---

## 12. Mughals E-content fix

**Root cause:** `overlap_count("Mughals", chunk)` was 0 because chunks say “Mughal”, so `evidence_matches_topic` refused the whole module.

**Fix:** alias `mughals→mughal` + topic-map pack + extractive `class9_textbook` if JSON is empty.

**Retest:** `grounded=true`, keys include title, introduction, class9_textbook, historical_context, detailed_explanation, timeline, exam_questions, mcqs, revision. Pack pages **3–11** (plus some later mixed pages). **Cited pages still [6]** — generation/citation overlap, not empty retrieval.

Shivaji e-content: grounded, pack 12–15, cited 9 and 13.  
Marathas e-content: grounded, pack 11–17, cited 11–12.

---

## 13. Regression results

Script: `scripts/phase17_regression.py` (plus remainder run in `scripts/phase17_remainder.py` after the first process stopped during F3/e-content).

Raw logs: `tmp/phase17-eval.log`, `tmp/phase17-remainder.json` (gitignored).

### Chat cases (first run)

| ID | Question | Type | Pack pages | Result |
|---|---|---|---|---|
| D1 | Who was Babar? | DIRECT | 3 | Answered from p.3; script AND-required “babur”+“babar” (false FAIL). Manual: PASS |
| D2 | Who was Akbar? | DIRECT | 5–7 | PASS |
| D3 | Who was Shivaji? | DIRECT | 12–13 | PASS |
| D4 | Din-e-Ilahi | DIRECT | 6 | PASS (no Ghalib) |
| D5 | Taj Mahal | DIRECT | 8–9 | PASS |
| E1 | Shivaji's administration | EXPLANATION | **12, 14** | PASS (no Aurangzeb admin / muhtasib) |
| E2 | Akbar's administration | EXPLANATION | 5, 7, 8 | PASS |
| E3 | Mughal administration | EXPLANATION | 5, 7–11, 14 | PASS |
| E4 | Maratha administration | EXPLANATION | 12, 14–16 | PASS |
| B1 | Mughals in detail | BROAD | **3–11** | Pack PASS vs expected pages; **generation FAIL** (fallback; under-named later emperors) |
| B2 | Marathas in detail | BROAD | 11–17 | PASS |
| B3 | Tell me more about Shivaji | BROAD | 12–15 | PASS |
| N1–N2 | GDP, Plassey | — | — | PASS refuse |
| M1 | Exact birth date | — | 12–13 | PASS phrase |
| M2 | Facts not in textbook | — | — | PASS refuse outside |
| I1–I3 | Wikipedia / another book / training | — | — | PASS refuse |

### Follow-up

| Seq | Result |
|---|---|
| Babar → after that | PASS entity; pack includes p.3 (also p.10 noise) |
| Shivaji → his administration | PASS; pack **12, 14** |
| Mughals → more about Akbar | PASS; type BROAD_TOPIC, topic **akbar** |

### Page coverage (required)

| Question | Expected | Evidence-pack pages | Covers expected |
|---|---|---|---|
| Explain the Mughals in detail. | 3, 5, 6, 8, 9, 10 | 1, 3–11, 14, 17 | **Yes** |
| Explain Shivaji's administration. | 14 | **12, 14** | **Yes** |
| Explain the Marathas in detail. | 12–15 | 1, 9, 11–17 | **Yes** |

Vector `retrieved_pages` for Mughals can still be a late/mixed subset; **the pack no longer equals that subset**.

---

## 14. Remaining limitations

**P1 — Broad generation vs pack.** The Mughals pack now includes Akbar / Shah Jahan / Aurangzeb pages, but llama3 may still fail validation and **fallback**, or mention only the first chunks. Context size and validator strictness remain. Do not shrink the model until this is acceptable.

**P1 — E-content citations thinner than the pack.** Modules are no longer empty; `supporting_evidence` on JSON still cites 1–2 pages.

**P1 — Residual mixed pages** on some dynasty packs (page 14/17, Sher Shah on Mughal admin, page 9 on Marathas). Filters reduced the P0 Aurangzeb-admin leak; they are not perfect OCR topic labels.

**P2 — Follow-up “after that”** can still attach an extra non-Babur page (p.10 in F1).

No new P0 of the Phase 16 kind (wrong-person admin pack / single late Mughal page) on the **pack** itself.

---

## Code changes

| File | Role |
|---|---|
| `rag/engine/topic_map.py` | Textbook-derived topic index from current Chroma primary chunks |
| `rag/engine/pack.py` | EvidencePack builder, entity/facet filters, page diversification |
| `rag/engine/classify.py` | `classify_question_type` |
| `rag/engine/evidence.py` | Token aliases (mughals/marathas/babur) |
| `rag/engine/answer.py` | Pack pipeline, mixed refusals, exact-date prefix, fallback from pack only, broad prompt |
| `rag/engine/econtent.py` | Topic-level pack + extractive core if JSON empty |
| `rag/engine/normalize.py` | Extra injection / outside-textbook patterns |
| `scripts/phase17_regression.py` | Required regression harness |

Not changed: llama3, nomic-embed-text, `historybot_class9_ss_v2`, MySQL, frontend, supplementary student retrieve.

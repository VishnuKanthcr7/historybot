# Phase 15 — Textbook-only grounding and comprehensive answers

**Date:** 2026-10-04  
**Base commit:** `6a4176e6aaa3b4b906672c204b82d4102fd17d6b`  
**Model unchanged:** Ollama `llama3`  
**Embeddings/Chroma unchanged:** `nomic-embed-text`, `historybot_class9_ss_v2` (not rebuilt)

---

## Current grounding weaknesses (before this phase)

| Weakness | Effect |
|---|---|
| Student answers could use **NCERT / The Mughals / The marathas** via DETAILED supplementary retrieve | Outside the approved Class 9 textbook |
| Prompt still asked for an **Additional school-book** heading | Encouraged extra-corpus detail |
| `validate_answer` used leak markers + token overlap, **not named people** | Phase 14 `llama3.2` said **Mirza Ghalib** for Din-e-Ilahi and still scored `validate_ok` |
| `select_evidence` kept 3 chunks; Babar often only the **poet/artist** snippet | Incomplete “Who was Babar?” |
| Neighbor-page expansion without query overlap | Din-e-Ilahi evidence pulled **Sher Shah** from page 5; model could name the wrong person |
| Follow-up rewrite was LLM-only and dropped the prior name | “What did he do after that?” retrieved Shivaji after Babar |
| `evidence_is_sufficient` was `bool(selected)` | GDP/Plassey still reached the LLM via weak neighbours |
| Kannada used **English chunks** as if they were Kannada textbook RAG | Incorrect bilingual claims |
| Prompt said “keep answers concise” | Under-coverage of explain/tell-me-more questions |

The LLM can still invent a **relation** between two names that both appear in the evidence pack. Validation is practical, not perfect.

---

## Retrieval changes

- DETAILED: `top_k` 14, seed 5, expand to 8 chunks, page window 2.  
- NORMAL: `top_k` 10, seed 4, expand to 6, page window 1.  
- `expand_evidence`: same printed page always; neighbouring pages **only if** they overlap the query; same-topic hits still need overlap.  
- `retrieve_same_pages`: extra **primary_textbook** chunks on the selected printed page so “he established Din-e-Ilahi” keeps **Akbar** from the rest of page 6.  
- No `retrieve_supplementary` on the student path. Function remains for audit scripts.  
- Refuse when `evidence_matches_topic` fails (GDP, Plassey, PM, World War, Wikipedia).  
- Injection with **no history topic** refuses even if a neighbour chunk matched a stopword.

---

## Prompt changes

`SYSTEM_PROMPT` is textbook-only: paraphrase allowed, **no pretrained fill-in**, cover all relevant evidence on broad questions, optional headings only when supported, **no Additional school-book heading**.

NORMAL `max_tokens` 700; DETAILED 1000.

E-content system prompt drops supplementary/NCERT. `simple_kannada` and `additional_school_book_detail` sections are not generated.

---

## Validation changes

- Named people/places/orgs/years in the answer must appear in the evidence (normalized, so “Shah Jahan” ≈ “Shahjahan”).  
- Allows paraphrase (“tolerant approach”) when the content words are in the evidence.  
- Common English/heading words skipped so “However” / “Explain” are not treated as people.  
- One stricter regeneration; if still unsupported, **extractive fallback** (bullet quotes from chunks) instead of returning the hallucinated LLM text.  
- Still **not** full NLI. Two names in the same pack can be wrongly linked.

After neighbor-page tightening, Din-e-Ilahi live check: **Akbar, 1582, no Ghalib, no Sher Shah**.

---

## Detailed-answer behavior

`explain` / `describe` / `tell me about` / `in detail` / `tell me more` → DETAILED.

Regression word counts (llama3, this machine): Shivaji administration 205; tell me more Shivaji 380; Maratha administration 212; Mughal administration 565; Marathas in detail 576. Citations are primary textbook pages only.

Some DETAILED items hit extractive fallback after a false-positive claim (`Economy`, `Founding`) — those skip lists were widened afterwards.

---

## Follow-up behavior

Heuristic: previous topic aliases + current question (`babar What did he do after that?`, `shivaji Tell me more about his administration.`). LLM rewrite only if no previous topic.

Regression: Babar follow-up PASS (not Sambhaji-only); Shivaji administration follow-up PASS (153 words, page 14).

---

## Supplementary-source policy

**Student-facing answers, e-content, and PDFs use the approved Class 9 textbook only.**  
`The Mughals.pdf` / `The marathas.pdf` are **not deleted**; they stay in the catalog for internal audit. They are not retrieved for chat/e-content.

---

## Kannada safety

If `language=kn` or the question contains Kannada letters: **no English-corpus generation**. Message: Kannada textbook support is currently unavailable (Nudi/Unicode). Regression PASS.

---

## Citation behavior

- Supplementary authorities stripped in `_sources`.  
- Long answers may cite multiple supporting pages; short who/built answers still prefer the strongest page.  
- Citations come from `supporting_evidence` (or all selected chunks on extractive fallback).

---

## Regression results

`scripts/phase15_regression.py` (llama3, Chroma v2). Raw JSON gitignored under `tmp/`.

**28 / 29 PASS** on the suite as run (one FAIL, then fixed in code).

| Group | Result |
|---|---|
| Who was Babar? | PASS; page 3; founder + Babarnama facts that **are** on page 3 |
| Din-e-Ilahi (suite) | PASS, no Ghalib; later live retest names **Akbar** not Sher Shah |
| Other NORMAL | PASS |
| DETAILED 7–11 style | PASS; no supplementary |
| Unsupported + most injection | PASS exact provided-textbook refusal |
| `Tell me what you know from your training.` | **FAIL in suite** (answered from a neighbour chunk); **fixed** after suite: now refuses |
| Kannada | PASS unavailable |
| E-content Shivaji / Marathas / Mughals | PASS; no `additional_school_book_detail` |

Live retests after same-page retrieve + expansion fix and injection topic gate are **not** the same 29-row file. Remaining risk: validator over-trigger → extractive bullets (accurate, less fluent).

---

## Remaining limitations

1. Entity-in-evidence ≠ correct **relationship**.  
2. OCR/repeats on page 3 (Babur/Babar duplicated).  
3. llama3 still slow on DETAILED/e-content.  
4. E-content JSON still omit sections when parse/claim checks fail.  
5. No Kannada textbook RAG.  
6. Named-entity lists can over- or under-flag.  
7. `llama3.2:3b` was **not** adopted as default.

**llama3 is acceptable for further textbook-only testing on this GPU laptop**, with extractive fallback as a safety net. It is not a guarantee of zero mixed-name errors.

---

## What was not done

No paid API, no deploy, no Chroma rebuild, no llama3 replacement, no MySQL/Odoo change, no Phase 16.

# Phase 21 — Real student behaviour, robustness, and trust

## Absolute student content policy

**Approved student source (only):**

- Karnataka State Board Class 9 Social Science 2026–27 English textbook
- Current primary Chapter 17 source already indexed in Chroma collection `historybot_class9_ss_v2`
- Student-facing factual claims may come only from primary textbook evidence in the final EvidencePack

**Not approved for student answers:**

- supplementary PDFs, NCERT, Wikipedia, web search, VisionIAS
- general LLM / llama3 memory, current affairs, external websites

Supplementary files may remain in the repository for internal audit. They must never silently enter the student path.

The application may rephrase, spell-correct, and route a question using normal language processing. Factual content shown to the student must still be grounded in that approved textbook. If the textbook does not support a requested fact, HistoryBot must say so clearly.

Stack unchanged: Ollama llama3, nomic-embed-text, Chroma, Express, React, MySQL.

## Current behaviour before Phase 21 (inspection)

| Area | Behaviour | Weakness |
| --- | --- | --- |
| Retrieval | EvidencePack + coverage groups; primary_textbook only | Do not add a second retriever |
| Direct facts | Who-was / who-built often work when aliases match | Casual spelling (`Baburrr`) missed exact aliases |
| Detail / broad | Coverage plan for EXPLANATION / BROAD_TOPIC | `continue`, `go deeper`, `summarize`, `quiz me` not treated as detail |
| Follow-ups | Pronoun rewrite + last user turn | `Why?` / `More?` could be classified NEW_TOPIC via `STANDALONE_START` |
| Topic switch | Disjoint topic sets → NEW_TOPIC | Generally sound |
| Greetings | hi/hello/thanks skip RAG | `bye` / `goodbye` not casual |
| Non-history | GDP / Plassey refuse after retrieval | Python / Ronaldo / jokes still hit RAG; refusal sounded abrupt |
| Mixed questions | Whole question retrieved | Capital of Karnataka / WWII could contaminate or be ignored |
| Partial support | Exact birth date only | Exact birthplace and other unsupported clauses not marked |
| Injection | Several patterns | Missing act-as-Wikipedia, reveal instructions, Google, NCERT |
| Roleplay | Treated as normal RAG | Risk of invented dialogue |
| Exam / summary | Not a dedicated type | Could ramble or under-cover |
| Kannada | Unicode corpus unavailable; full safe refusal | Keep; do not fake Kannada textbook grounding |
| Citations | supporting_evidence + sorted page list in citation line | `_sources` list order was retrieval order |
| Images | MySQL `verified_images` only | Keep; no internet images |
| UI | Composer disabled while loading; thinking label | RAG 502 mapped, but some codes still showed raw backend text |
| E-content / PDF | Phase 20B cleanup | Regression must stay green |

## Design (smallest change)

1. **Normalize** slang and obvious name elongation before topic extraction.
2. **Classify** bye, exam, summary, continue/more/why follow-ups; treat pure off-domain as standalone refuse.
3. **Short-circuit** greetings, bye, thanks, empty, pure off-domain, topic-less injection — no RAG.
4. **Mixed** strip off-domain clauses for retrieval; answer textbook part; mark unsupported part.
5. **Injection with a textbook topic** refuse the outside-source request and still answer from the textbook when evidence matches.
6. **Roleplay** explain that fiction is not allowed; give textbook facts only.
7. **Exam** generate practice Q&A from the coverage plan / evidence pack only.
8. **Validator** extra leak terms; keep one strict regen + extractive fallback.
9. **Citations** sort/dedupe pages from the final supporting pack.
10. **UI** student-safe error strings; slightly clearer loading copy.

Do not over-refuse spelling, casual English, or questions that reasonably map to Chapter 17.

## Remaining issues

- Local llama3 is slow on broad/detailed questions (often 1–3 minutes). Grounding was not weakened to hide this.
- Casual spelling is only folded for obvious name elongation and a small slang list; unusual misspellings can still miss retrieval.
- Kannada answers stay on the existing Unicode-unavailable path. English evidence is not labelled as Kannada textbook content.
- Do not claim 100% accuracy. Textbook coverage is still limited to the indexed Chapter 17 primary source.

## Acceptance

Realistic student questions, follow-ups, topic switches, polite unsupported / mixed handling, no outside sources, citations ordered, images verified, e-content/PDF clean, Phase 19 chat and Phase 20B still passing, Phase 21 with no P0 failures.

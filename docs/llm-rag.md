# Phase 6 — Grounded LLM / RAG engine

**Status:** COMPLETE (awaiting review before Phase 7 Express APIs).

This phase does **not** claim 100% accuracy or zero hallucinations. It is a conservative textbook-grounded tutor over Chapter 5 only.

## LLM

- **Provider:** `LLM_PROVIDER=ollama` (Phase 6)
- **Model:** `llama3` via local Ollama (`OLLAMA_BASE_URL`, default `http://127.0.0.1:11434`)
- **Embeddings:** `nomic-embed-text` (unchanged)
- Cursor/Grok is not used at runtime
- Abstraction lives in `rag/llm/client.py` so a later OpenAI-compatible provider can be added without rewriting the engine

## Flow

```
question
  → normalize
  → optional follow-up rewrite (llama3, rewrite only)
  → embed rewritten query (nomic-embed-text)
  → Chroma historybot_class9_ss (top_k=5)
  → evidence filter (distance + token overlap)
  → llama3 answer from evidence only
  → lightweight validation (one stricter retry max)
  → answer + printed textbook page citations
```

## Retrieval

- Collection: `historybot_class9_ss` (not rebuilt)
- `RAG_TOP_K=5`
- Multiple chunks are considered, not rank 1 only
- Starting `RAG_DISTANCE_THRESHOLD=0.55` (from Phase 5: guerilla hits ~0.50, strong hits ~0.15–0.31). This is a **starting** value, not a proven accuracy cutoff.
- Chunks also need either distance ≤ `0.32` **or** at least one overlapping content token
- After filtering, the **best 3** chunks are sent to the LLM

## Citations

Student-facing pages are **printed textbook pages**. Format:

`Source: Textbook page 12`  
or `Source: Textbook pages 10–12` / comma-separated if not a continuous range

PDF page numbers stay in the structured `sources` array for later APIs, not as the student citation.

## Follow-ups

Last 4 user + 4 assistant messages, each truncated to 2000 characters. History is used only to rewrite the search question. Every turn still retrieves from Chroma.

## Prompt injection

User text is treated as a question. Requests to ignore the textbook, use Wikipedia, or reveal the system prompt are not obeyed. The system prompt forbids leaking internals.

## Refusal

English: `This topic is not available in the textbook.`  
Kannada: `ಈ ವಿಷಯ ನೀಡಲಾದ ಪಠ್ಯಪುಸ್ತಕದಲ್ಲಿ ಲಭ್ಯವಿಲ್ಲ.`

## Commands

```text
python scripts/evaluate_chapter5_rag.py
```

## Known limitations

- llama3 Kannada quality is uneven; Kannada questions are rewritten to English **for retrieval only**, then answered in Kannada from the same evidence
- Vector search can still surface weakly related Chapter 5 passages
- Citations list pages of selected evidence, which can include a nearby related page
- Answer validation is lightweight (leaks, invented pages, a few extra-corpus terms), not a full fact checker
- Query rewrite is itself an LLM step and can be imperfect

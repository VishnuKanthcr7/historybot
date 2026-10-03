# Phase 5 — Vector database

**Status:** COMPLETE (awaiting review before Phase 6 LLM answers).

## Setup

- **Engine:** ChromaDB 0.5.23, persistent client
- **Path:** `data/chroma/` (gitignored; regenerate with the index script)
- **Collection:** `historybot_class9_ss`
- **Space:** cosine (`hnsw:space=cosine`)
- **Embedding model:** Ollama `nomic-embed-text` (local, 768 dimensions)
- **Not used:** llama3, Chroma default ONNX embedder, any cloud API

Install Python deps for this layer:

```text
pip install -r rag/requirements.txt
```

## Source

Phase 4 file `data/extracted/chapter5_chunks.json` — **67** chunks, Chapter 5 only (PDF 3–16 / textbook 1–14).

## Process

1. Load approved chunks (reject wrong count, duplicate IDs, Chapter 6 text).
2. Inspect existing collection. If count is neither 0 nor 67, **stop** (no delete).
3. Embed each chunk with `POST {OLLAMA_HOST}/api/embeddings` model `nomic-embed-text`.
4. `upsert` into Chroma with deterministic **id = chunk_id**.

## Metadata stored with each vector

`chunk_id`, `document_name`, `chapter`, `section`, `source_file`, `ingest_version`, `pdf_page_number`, `textbook_page_number`, `embedding_model`

Document text is the original Phase 4 chunk text.

## IDs and duplicates

- ID is the Phase 4 `chunk_id` (example: `kseeb_c9_ss2_ch5_pdf3_tb1_01`).
- Re-running the indexer **upserts** the same IDs; count stays 67.
- If `ingest_version` changes later but `chunk_id` stays the same, upsert **overwrites** the old vector (one current version in the collection).
- If a future ingest must keep two versions, change IDs to include `ingest_version` before indexing. Do not delete blindly.

## Retrieval

- Chat: `top_k = 5`
- E-content (later): `top_k = 12`
- Query embedding: same `nomic-embed-text`
- Distance: cosine distance (lower is closer). Approximate similarity ≈ `1 - distance`.
- **No confidence cutoff yet** — values must be reviewed with the LLM phase.
- This phase does **not** generate answers.

## Commands

```text
python scripts/index_chapter5_chroma.py
python scripts/test_chapter5_retrieval.py
```

## Validation (this machine)

- Collection count: **67** after index and after reopen
- Unique IDs: 67
- Embedding dimension: **768** on all records
- Chapter: THE MOGHULS AND THE MARATHAS only
- Chapter 6 / BHAKTI PANTH: not present
- Re-index: still 67 (no duplicates)
- Persistence: close client, reopen, count 67, query still works

## Retrieval notes (not 100% accurate)

Stronger hits: Babar establishing Moghul rule (textbook p.1); Din-e-Ilahi definition (p.5); Taj Mahal / Shahjahan (p.6).

Weaker: “guerilla warfare” — a justice-system chunk ranked above chunks that actually mention guerilla training. Shivaji administration mixed biography/Peshwa chunks with Asthapradhan/revenue chunks. Rank 2–5 for some queries are related Chapter 5 text, not always the best sentence.

Do not lock a similarity threshold until Phase 6 grounding tests.

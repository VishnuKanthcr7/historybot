"""Index approved Phase 4 chunks into Chroma. Idempotent upsert by chunk_id."""

from __future__ import annotations

import json
from pathlib import Path

from .chroma_store import get_client, get_or_create_collection, inspect_collection
from .config import (
    ALLOWED_CHAPTER,
    CHUNKS_PATH,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EXPECTED_CHUNK_COUNT,
)
from .embeddings import embed_text


class IndexConflictError(RuntimeError):
    pass


METADATA_KEYS = (
    "chunk_id",
    "document_name",
    "chapter",
    "section",
    "source_file",
    "ingest_version",
    "pdf_page_number",
    "textbook_page_number",
)


def load_approved_chunks(path: Path | None = None) -> list[dict]:
    chunks_path = path or CHUNKS_PATH
    if not chunks_path.exists():
        raise FileNotFoundError(f"Phase 4 chunks not found: {chunks_path}")
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    if len(chunks) != EXPECTED_CHUNK_COUNT:
        raise IndexConflictError(
            f"Expected {EXPECTED_CHUNK_COUNT} Phase 4 chunks, found {len(chunks)}"
        )
    ids = [item["chunk_id"] for item in chunks]
    if len(ids) != len(set(ids)):
        raise IndexConflictError("Phase 4 chunks contain duplicate chunk_id values")
    for item in chunks:
        if item.get("chapter") != ALLOWED_CHAPTER:
            raise IndexConflictError(f"Unexpected chapter in chunk {item.get('chunk_id')}")
        if "BHAKTI PANTH" in item.get("text", "") or "CHAPTER - 6" in item.get("text", ""):
            raise IndexConflictError(f"Chapter 6 text found in chunk {item.get('chunk_id')}")
        missing = [key for key in METADATA_KEYS if key not in item]
        if missing:
            raise IndexConflictError(f"Chunk {item.get('chunk_id')} missing {missing}")
    return chunks


def index_chunks(chunks: list[dict] | None = None) -> dict:
    chunks = chunks or load_approved_chunks()
    client = get_client()
    existing = inspect_collection(client)
    if existing:
        conflict = _conflict_if_incompatible(existing, chunks)
        if conflict:
            raise IndexConflictError(conflict)

    collection = get_or_create_collection(client)
    ids = [item["chunk_id"] for item in chunks]
    documents = [item["text"] for item in chunks]
    metadatas = [_metadata(item) for item in chunks]
    embeddings = [embed_text(text, model=EMBEDDING_MODEL) for text in documents]

    dimensions = {len(vector) for vector in embeddings}
    if len(dimensions) != 1:
        raise IndexConflictError(f"Inconsistent embedding dimensions: {dimensions}")

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    count = collection.count()
    return {
        "collection": COLLECTION_NAME,
        "count": count,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": next(iter(dimensions)),
        "ids": ids,
        "had_existing_collection": existing is not None,
        "existing_count_before": existing["count"] if existing else 0,
    }


def _metadata(chunk: dict) -> dict:
    return {
        "chunk_id": str(chunk["chunk_id"]),
        "document_name": str(chunk["document_name"]),
        "chapter": str(chunk["chapter"]),
        "section": str(chunk.get("section") or "body"),
        "source_file": str(chunk["source_file"]),
        "ingest_version": int(chunk["ingest_version"]),
        "pdf_page_number": int(chunk["pdf_page_number"]),
        "textbook_page_number": int(chunk["textbook_page_number"]),
        "embedding_model": EMBEDDING_MODEL,
    }


def _conflict_if_incompatible(existing: dict, chunks: list[dict]) -> str | None:
    if existing["count"] == 0:
        return None
    existing_ids = set(existing["sample_ids"])
    approved_ids = {item["chunk_id"] for item in chunks}
    if existing["count"] == len(chunks):
        return None
    unexpected = existing_ids - approved_ids
    if unexpected:
        return (
            f"Collection {COLLECTION_NAME} already has {existing['count']} records "
            f"that do not match the approved {len(chunks)} Phase 4 chunks. "
            "Stopped without deleting. Sample unexpected ids: "
            + ", ".join(sorted(unexpected)[:5])
        )
    if existing["count"] not in (0, len(chunks)):
        return (
            f"Collection {COLLECTION_NAME} count is {existing['count']}, "
            f"expected 0 or {len(chunks)}. Stopped without deleting."
        )
    return None

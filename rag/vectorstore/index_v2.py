"""Index Phase 11 chunks into historybot_class9_ss_v2. Does not touch the old collection."""

from __future__ import annotations

import json
from pathlib import Path

from rag.ingestion.v2 import PHASE11_DIR
from rag.sources.catalog import EXCLUDED_SOURCE_FILES
from rag.vectorstore.chroma_store import get_client, get_or_create_collection, inspect_collection
from rag.vectorstore.config import COLLECTION_NAME, COLLECTION_NAME_V2, EMBEDDING_MODEL
from rag.vectorstore.embeddings import embed_text

METADATA_KEYS = (
    "chunk_id",
    "source_id",
    "source_type",
    "authority",
    "language",
    "document_name",
    "publisher",
    "chapter",
    "topic",
    "section",
    "source_file",
    "ingest_version",
    "pdf_page_number",
    "printed_page_number",
    "textbook_page_number",
    "citation_label",
    "retrieval_excluded",
)


def load_phase11_chunks(path: Path | None = None) -> list[dict]:
    chunks_path = path or (PHASE11_DIR / "chunks.json")
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    ids = [item["chunk_id"] for item in chunks]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Phase 11 chunks contain duplicate IDs.")
    for item in chunks:
        missing = [key for key in METADATA_KEYS if key not in item and key != "retrieval_excluded"]
        if missing:
            raise RuntimeError(f"{item.get('chunk_id')} missing {missing}")
        if item.get("source_file") in EXCLUDED_SOURCE_FILES:
            raise RuntimeError(f"Excluded source in chunks: {item.get('source_file')}")
        if item.get("language") == "kn" and "CzsÁåAiÀÄ" in (item.get("text") or ""):
            raise RuntimeError("Raw Nudi text must not be indexed.")
    return chunks


def index_phase11(chunks: list[dict] | None = None) -> dict:
    chunks = chunks or load_phase11_chunks()
    client = get_client()
    old = inspect_collection(client, COLLECTION_NAME)
    collection = get_or_create_collection(client, COLLECTION_NAME_V2)
    ids = [item["chunk_id"] for item in chunks]
    documents = [item["text"] for item in chunks]
    metadatas = [_metadata(item) for item in chunks]
    embeddings = [embed_text(text, model=EMBEDDING_MODEL) for text in documents]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    after = inspect_collection(client, COLLECTION_NAME)
    if old and after and old["count"] != after["count"]:
        raise RuntimeError("Old Chroma collection count changed during Phase 11 indexing.")
    return {
        "old_collection": COLLECTION_NAME,
        "old_count": old["count"] if old else None,
        "collection": COLLECTION_NAME_V2,
        "count": collection.count(),
        "unique_ids": len(set(collection.get(include=[])["ids"] or [])),
        "embedding_model": EMBEDDING_MODEL,
    }


def _metadata(chunk: dict) -> dict:
    return {
        "chunk_id": str(chunk["chunk_id"]),
        "source_id": str(chunk["source_id"]),
        "source_type": str(chunk["source_type"]),
        "authority": str(chunk["authority"]),
        "language": str(chunk["language"]),
        "document_name": str(chunk["document_name"]),
        "publisher": str(chunk.get("publisher") or ""),
        "chapter": str(chunk["chapter"]),
        "topic": str(chunk.get("topic") or ""),
        "section": str(chunk.get("section") or "body"),
        "source_file": str(chunk["source_file"]),
        "ingest_version": int(chunk["ingest_version"]),
        "pdf_page_number": int(chunk["pdf_page_number"]),
        "printed_page_number": int(chunk["printed_page_number"]),
        "textbook_page_number": int(chunk["textbook_page_number"]),
        "citation_label": str(chunk.get("citation_label") or ""),
        "retrieval_excluded": bool(chunk.get("retrieval_excluded")),
        "embedding_model": EMBEDDING_MODEL,
    }

"""Patch v2 collection metadata/documents. Does not touch historybot_class9_ss."""

from __future__ import annotations

from rag.ingestion.chunk_quality import assess_chunk
from rag.ingestion.clean import strip_ocr_artifacts
from rag.vectorstore.chroma_store import get_client, inspect_collection
from rag.vectorstore.config import COLLECTION_NAME, COLLECTION_NAME_V2, EMBEDDING_MODEL
from rag.vectorstore.embeddings import embed_text


def patch_v2_quality() -> dict:
    client = get_client()
    old_before = inspect_collection(client, COLLECTION_NAME)
    collection = client.get_collection(name=COLLECTION_NAME_V2)
    data = collection.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    documents = data.get("documents") or []
    metadatas = data.get("metadatas") or []

    excluded = []
    ocr_cleaned = 0
    for chunk_id, document, meta in zip(ids, documents, metadatas):
        meta = dict(meta or {})
        cleaned = strip_ocr_artifacts(document or "")
        quality = assess_chunk(
            {
                "text": document or "",
                "source_type": meta.get("source_type"),
                "chunk_id": chunk_id,
            }
        )
        meta["retrieval_excluded"] = bool(quality["excluded"])
        if quality["excluded"]:
            excluded.append({"chunk_id": chunk_id, "reason": quality["reason"]})
        kwargs = {"ids": [chunk_id], "metadatas": [meta]}
        if cleaned != (document or ""):
            kwargs["documents"] = [cleaned]
            kwargs["embeddings"] = [embed_text(cleaned, model=EMBEDDING_MODEL)]
            ocr_cleaned += 1
        collection.update(**kwargs)

    old_after = inspect_collection(client, COLLECTION_NAME)
    if old_before and old_after and old_before["count"] != old_after["count"]:
        raise RuntimeError("Old Chroma collection count changed during Phase 11B patch.")
    mughal_ids = [i for i, m in zip(ids, metadatas) if (m or {}).get("source_type") == "supplementary_mughal"]
    return {
        "old_collection": COLLECTION_NAME,
        "old_count": old_after["count"] if old_after else None,
        "new_collection": COLLECTION_NAME_V2,
        "new_count": collection.count(),
        "mughal_total": len(mughal_ids),
        "mughal_excluded": len(excluded),
        "mughal_valid": len(mughal_ids) - len(excluded),
        "excluded": excluded,
        "ocr_documents_cleaned": ocr_cleaned,
    }

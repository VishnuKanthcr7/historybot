"""Chroma retrieval using Ollama query embeddings."""

from __future__ import annotations

from rag.ingestion.chunk_quality import is_retrieval_excluded
from rag.ingestion.clean import strip_ocr_artifacts
from .chroma_store import get_existing_collection, get_or_create_collection, list_collections
from .config import ACTIVE_COLLECTION, CHAT_TOP_K, COLLECTION_NAME, EMBEDDING_MODEL
from .embeddings import embed_text


def retrieve(query: str, top_k: int = CHAT_TOP_K, collection_name: str | None = None, where: dict | None = None) -> list[dict]:
    name = collection_name or _active_collection()
    if name == COLLECTION_NAME:
        collection = get_or_create_collection(name=COLLECTION_NAME)
    else:
        collection = get_existing_collection(name)
    query_embedding = embed_text(query, model=EMBEDDING_MODEL)
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": max(top_k + 8, top_k),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    result = collection.query(**kwargs)
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    rows = []
    for index, chunk_id in enumerate(ids):
        meta = metadatas[index] if index < len(metadatas) else {}
        text = documents[index] if index < len(documents) else ""
        distance = distances[index] if index < len(distances) else None
        similarity = None if distance is None else round(1.0 - float(distance), 4)
        text = strip_ocr_artifacts(text or "")
        row = {
            "chunk_id": chunk_id,
            "distance": None if distance is None else round(float(distance), 4),
            "cosine_similarity_approx": similarity,
            "textbook_page_number": meta.get("textbook_page_number") or meta.get("printed_page_number"),
            "printed_page_number": meta.get("printed_page_number") or meta.get("textbook_page_number"),
            "pdf_page_number": meta.get("pdf_page_number"),
            "section": meta.get("section"),
            "chapter": meta.get("chapter"),
            "ingest_version": meta.get("ingest_version"),
            "source_id": meta.get("source_id"),
            "source_type": meta.get("source_type") or "primary_textbook",
            "authority": meta.get("authority") or "primary",
            "language": meta.get("language") or "en",
            "document_name": meta.get("document_name"),
            "citation_label": meta.get("citation_label"),
            "retrieval_excluded": meta.get("retrieval_excluded"),
            "text": text or "",
            "preview": (text or "").replace("\n", " ")[:220],
        }
        if is_retrieval_excluded(row):
            continue
        rows.append(row)
        if len(rows) >= top_k:
            break
    return rows


def retrieve_primary(query: str, top_k: int = CHAT_TOP_K, language: str = "en") -> list[dict]:
    source_type = "primary_kannada_textbook" if language == "kn" else "primary_textbook"
    hits = retrieve(query, top_k=top_k, where={"source_type": source_type})
    if language == "kn" and not hits:
        hits = retrieve(query, top_k=top_k, where={"source_type": "primary_textbook"})
    return hits


def retrieve_same_pages(query: str, pages: list[int], source_type: str = "primary_textbook", per_page: int = 8) -> list[dict]:
    """Load other chunks on the same printed pages so pronouns like 'he' keep their subject."""
    rows = []
    seen = set()
    for page in sorted({int(p) for p in pages if p is not None}):
        try:
            hits = retrieve(query, top_k=per_page, where={"printed_page_number": page})
        except Exception:
            continue
        for hit in hits:
            if hit.get("source_type") != source_type:
                continue
            chunk_id = hit.get("chunk_id")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            rows.append(hit)
    return rows


def retrieve_supplementary(query: str, top_k: int = CHAT_TOP_K) -> list[dict]:
    from rag.engine.classify import extract_topics

    topics = extract_topics(query)
    maratha = topics & {"shivaji", "maratha", "sambhaji", "bajirao", "peshwa", "madhav", "raigad", "guerilla"}
    mughal = topics & {
        "mansab",
        "akbar",
        "babar",
        "humayun",
        "jahangir",
        "shahjahan",
        "aurangzeb",
        "taj",
        "din",
        "sher",
        "mughal",
    }
    if maratha and not mughal:
        where = {"source_type": "supplementary_maratha"}
    elif mughal and not maratha:
        where = {"source_type": "supplementary_mughal"}
    else:
        where = {"authority": "approved_supplementary"}
    return retrieve(query, top_k=top_k, where=where)


def _active_collection() -> str:
    names = list_collections()
    if ACTIVE_COLLECTION in names:
        return ACTIVE_COLLECTION
    return COLLECTION_NAME

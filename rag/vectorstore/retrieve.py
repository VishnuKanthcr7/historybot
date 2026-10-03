"""Chroma retrieval using Ollama query embeddings. No LLM answers."""

from __future__ import annotations

from .chroma_store import get_or_create_collection
from .config import CHAT_TOP_K, EMBEDDING_MODEL
from .embeddings import embed_text


def retrieve(query: str, top_k: int = CHAT_TOP_K) -> list[dict]:
    collection = get_or_create_collection()
    query_embedding = embed_text(query, model=EMBEDDING_MODEL)
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
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
        rows.append(
            {
                "chunk_id": chunk_id,
                "distance": None if distance is None else round(float(distance), 4),
                "cosine_similarity_approx": similarity,
                "textbook_page_number": meta.get("textbook_page_number"),
                "pdf_page_number": meta.get("pdf_page_number"),
                "section": meta.get("section"),
                "chapter": meta.get("chapter"),
                "ingest_version": meta.get("ingest_version"),
                "text": text or "",
                "preview": (text or "").replace("\n", " ")[:220],
            }
        )
    return rows

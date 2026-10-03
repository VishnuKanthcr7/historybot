"""Persistent Chroma client. Embeddings are supplied by the caller (Ollama)."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.api.models.Collection import Collection

from .config import CHROMA_PATH, COLLECTION_NAME, EMBEDDING_MODEL


def get_client(path=None):
    chroma_path = Path(path or CHROMA_PATH)
    chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_path))


def list_collections(client=None) -> list[str]:
    client = client or get_client()
    return [item.name for item in client.list_collections()]


def inspect_collection(client=None, name: str = COLLECTION_NAME) -> dict | None:
    client = client or get_client()
    names = list_collections(client)
    if name not in names:
        return None
    collection = client.get_collection(name=name)
    count = collection.count()
    sample = collection.get(limit=min(5, count) or 1, include=["metadatas", "documents"])
    return {
        "name": name,
        "count": count,
        "metadata": collection.metadata,
        "sample_ids": sample.get("ids") or [],
        "sample_metadatas": sample.get("metadatas") or [],
    }


def get_or_create_collection(client=None) -> Collection:
    client = client or get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": EMBEDDING_MODEL,
            "project": "historybot",
        },
    )

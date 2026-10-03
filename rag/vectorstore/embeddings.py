"""Ollama embeddings via local HTTP. Never uses llama3 for embeddings."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .config import EMBEDDING_MODEL, OLLAMA_HOST


class EmbeddingError(RuntimeError):
    pass


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_HOST", OLLAMA_HOST).rstrip("/")


def embed_texts(texts: list[str], model: str = EMBEDDING_MODEL) -> list[list[float]]:
    if model != EMBEDDING_MODEL:
        raise EmbeddingError(f"Phase 5 only allows {EMBEDDING_MODEL}, got {model}")
    return [embed_text(text, model=model) for text in texts]


def embed_text(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    if model != EMBEDDING_MODEL:
        raise EmbeddingError(f"Phase 5 only allows {EMBEDDING_MODEL}, got {model}")
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    url = f"{ollama_base_url()}/api/embeddings"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc
    embedding = body.get("embedding")
    if not embedding:
        raise EmbeddingError("Ollama returned no embedding vector")
    return embedding

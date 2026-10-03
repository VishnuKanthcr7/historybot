"""Conservative evidence filtering. Starting thresholds, not a guarantee of accuracy."""

from __future__ import annotations

import re

from rag.llm.config import RAG_DISTANCE_THRESHOLD, RAG_MIN_TOKEN_OVERLAP, RAG_STRONG_DISTANCE

STOPWORDS = {
    "what", "who", "whom", "which", "when", "where", "why", "how",
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for",
    "was", "were", "is", "are", "did", "does", "do", "his", "her",
    "their", "this", "that", "these", "those", "with", "from", "into",
    "about", "like", "main", "features", "according", "textbook", "please",
    "tell", "me", "give", "explain", "describe",
}


def content_tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z]{4,}|[\u0C80-\u0CFF]{3,}", text.lower())
    return {word for word in words if word not in STOPWORDS}


def overlap_count(query: str, chunk_text: str) -> int:
    query_tokens = content_tokens(query)
    if not query_tokens:
        return 0
    chunk_tokens = content_tokens(chunk_text)
    return len(query_tokens & chunk_tokens)


def select_evidence(question: str, retrieval_query: str, hits: list[dict]) -> list[dict]:
    combined_query = f"{question} {retrieval_query}"
    kept = []
    for hit in hits:
        distance = hit.get("distance")
        if distance is None:
            continue
        if distance > RAG_DISTANCE_THRESHOLD:
            continue
        overlap = overlap_count(combined_query, hit.get("text") or "")
        hit = {**hit, "token_overlap": overlap}
        if distance <= RAG_STRONG_DISTANCE or overlap >= RAG_MIN_TOKEN_OVERLAP:
            kept.append(hit)
    kept.sort(key=lambda item: (item.get("distance") if item.get("distance") is not None else 9, -item.get("token_overlap", 0)))
    return kept[:3]


def evidence_is_sufficient(selected: list[dict]) -> bool:
    return bool(selected)

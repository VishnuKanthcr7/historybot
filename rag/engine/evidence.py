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


EXERCISE_HINTS = (
    "exercises",
    "fill in the blanks",
    "answer the following",
    "project work",
    "activities",
)


def looks_like_exercise_chunk(hit: dict) -> bool:
    blob = f"{hit.get('section') or ''} {(hit.get('text') or '')[:280]}".lower()
    return any(hint in blob for hint in EXERCISE_HINTS)


def question_asks_for_exercise(question: str) -> bool:
    lowered = (question or "").lower()
    return any(word in lowered for word in ("exercise", "fill in", "blank", "project work"))


def select_evidence(question: str, retrieval_query: str, hits: list[dict], max_keep: int = 3) -> list[dict]:
    combined_query = f"{question} {retrieval_query}"
    wants_exercise = question_asks_for_exercise(combined_query)
    kept = []
    for hit in hits:
        distance = hit.get("distance")
        if distance is None:
            continue
        adjusted = float(distance)
        if looks_like_exercise_chunk(hit) and not wants_exercise:
            # Keep exercise chunks available, but prefer factual narrative pages.
            adjusted += 0.12
        if adjusted > RAG_DISTANCE_THRESHOLD:
            continue
        overlap = overlap_count(combined_query, hit.get("text") or "")
        item = {**hit, "token_overlap": overlap, "adjusted_distance": round(adjusted, 4)}
        if adjusted <= RAG_STRONG_DISTANCE or overlap >= RAG_MIN_TOKEN_OVERLAP:
            kept.append(item)
    kept.sort(
        key=lambda item: (
            item.get("adjusted_distance") if item.get("adjusted_distance") is not None else 9,
            -item.get("token_overlap", 0),
        )
    )
    return kept[:max_keep]


def evidence_is_sufficient(selected: list[dict]) -> bool:
    return bool(selected)


def evidence_matches_topic(topic: str, retrieval_query: str, selected: list[dict]) -> bool:
    if not selected:
        return False
    blob = " ".join(item.get("text") or "" for item in selected)
    lowered = blob.lower()
    topic_l = f"{topic or ''} {retrieval_query or ''}".lower()
    blocked = (
        "world war",
        "gdp",
        "prime minister",
        "plassey",
        "wikipedia",
    )
    for term in blocked:
        if term in topic_l:
            return term in lowered
    return overlap_count(f"{topic} {retrieval_query}", blob) >= 1

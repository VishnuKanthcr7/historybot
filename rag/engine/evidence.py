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
        "visionias",
    )
    for term in blocked:
        if term in topic_l:
            return term in lowered
    return overlap_count(f"{topic} {retrieval_query}", blob) >= 1


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def expand_evidence(
    question: str,
    retrieval_query: str,
    selected: list[dict],
    hits: list[dict],
    max_keep: int = 6,
    page_window: int = 1,
) -> list[dict]:
    """Add nearby/same-topic textbook chunks so broad questions are not under-covered."""
    if not selected:
        return []
    from rag.engine.classify import extract_topics

    combined = f"{question} {retrieval_query}"
    query_topics = extract_topics(combined)
    by_id = {item.get("chunk_id"): item for item in selected if item.get("chunk_id")}
    pages = {p for item in selected if (p := _page(item)) is not None}
    ordered = sorted(
        hits,
        key=lambda item: (
            0 if _page(item) in pages else 1,
            abs((_page(item) or 99) - min(pages)) if pages and _page(item) is not None else 99,
            item.get("distance") if item.get("distance") is not None else 9,
        ),
    )
    for hit in ordered:
        if len(by_id) >= max_keep:
            break
        chunk_id = hit.get("chunk_id")
        if not chunk_id or chunk_id in by_id:
            continue
        page = _page(hit)
        near = page is not None and pages and any(abs(page - other) <= page_window for other in pages)
        same_page = page is not None and page in pages
        hit_topics = extract_topics(hit.get("text") or "")
        topic_hit = bool(query_topics and hit_topics & query_topics)
        distance = hit.get("distance")
        close = distance is not None and float(distance) <= RAG_DISTANCE_THRESHOLD
        overlap = overlap_count(combined, hit.get("text") or "")
        if same_page:
            pass
        elif near and overlap >= 1:
            pass
        elif topic_hit and close and overlap >= 1:
            pass
        else:
            continue
        by_id[chunk_id] = {
            **hit,
            "token_overlap": overlap,
            "adjusted_distance": round(float(distance), 4) if distance is not None else None,
        }
    return sorted(
        by_id.values(),
        key=lambda item: (_page(item) or 99, item.get("distance") if item.get("distance") is not None else 9),
    )[:max_keep]

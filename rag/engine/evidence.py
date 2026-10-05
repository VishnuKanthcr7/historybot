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
    aliases = {
        "mughals": "mughal",
        "marathas": "maratha",
        "babur": "babar",
        "ahoms": "ahom",
        "hindus": "hindu",
        "ministers": "minister",
        "temples": "temple",
    }
    return {aliases.get(word, word) for word in words if word not in STOPWORDS}


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
    from rag.engine.classify import TOPIC_ALIASES, extract_topics

    blob = " ".join(item.get("text") or "" for item in selected)
    lowered = blob.lower()
    topic_l = f"{topic or ''} {retrieval_query or ''}".lower()
    query_topics = extract_topics(topic_l)
    blob_topics = extract_topics(blob)
    blocked = (
        "world war",
        "gdp",
        "prime minister",
        "plassey",
        "napoleon",
        "wikipedia",
        "visionias",
    )
    if not query_topics:
        for term in blocked:
            if term in topic_l:
                return term in lowered
        return evidence_subject_match(f"{topic} {retrieval_query}", selected)
    # Named aliases with zero primary coverage are unsupported.
    covered = {key for key in query_topics if primary_has_topic(key)}
    if not covered:
        return False
    if covered & blob_topics:
        return True
    for key in covered:
        aliases = [alias for alias in TOPIC_ALIASES.get(key, (key,)) if alias.isascii()]
        if any(alias in lowered for alias in aliases):
            return True
    return False


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

def primary_has_topic(topic_key: str) -> bool:
    """True when the primary topic map has at least one chunk/page for the key."""
    if not topic_key:
        return False
    from rag.engine.topic_map import build_topic_index, chunks_for_topics

    index = build_topic_index()
    entry = index.get(topic_key) or {}
    if entry.get("pages"):
        return True
    return bool(chunks_for_topics({topic_key}))


def topic_supported_by_primary(question: str) -> bool | None:
    """False when named aliases lack primary coverage; None if no aliases extracted."""
    from rag.engine.classify import extract_topics

    topics = extract_topics(question or "")
    if not topics:
        return None
    return any(primary_has_topic(key) for key in topics)


def evidence_subject_match(question: str, selected: list[dict]) -> bool:
    """Require selected evidence to mention extracted topic aliases."""
    from rag.engine.classify import TOPIC_ALIASES, extract_topics

    if not selected:
        return False
    topics = extract_topics(question or "")
    blob = " ".join(item.get("text") or "" for item in selected).lower()
    if not topics:
        # Distinctive token must appear; avoid weak one-token false grounding.
        tokens = content_tokens(question)
        if not tokens:
            return False
        hits = [tok for tok in tokens if tok in blob]
        if len(hits) >= 2:
            return True
        if len(hits) == 1 and len(hits[0]) >= 5:
            return True
        return False
    covered = [key for key in topics if primary_has_topic(key)]
    if not covered:
        return False
    for key in covered:
        aliases = [alias for alias in TOPIC_ALIASES.get(key, (key,)) if alias.isascii()]
        if any(alias in blob for alias in aliases):
            return True
    return False

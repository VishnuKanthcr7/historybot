"""Keep student-facing citations to pages that support the final answer."""

from __future__ import annotations

from rag.engine.evidence import STOPWORDS, content_tokens

CITATION_GENERIC = STOPWORDS | {
    "battle",
    "india",
    "indian",
    "history",
    "king",
    "kings",
    "kingdom",
    "empire",
    "army",
    "war",
    "year",
    "years",
    "century",
    "north",
    "south",
    "east",
    "west",
    "ruler",
    "rulers",
    "died",
    "also",
    "after",
    "before",
    "during",
    "established",
    "administration",
}


def citation_tokens(text: str) -> set[str]:
    return {token for token in content_tokens(text) if token not in CITATION_GENERIC}


def supporting_evidence(answer: str, evidence: list[dict], min_overlap: int = 2) -> list[dict]:
    answer_tokens = citation_tokens(answer or "")
    scored = []
    for item in evidence:
        overlap = len(answer_tokens & citation_tokens(item.get("text") or ""))
        if overlap >= min_overlap:
            scored.append({**item, "answer_overlap": overlap})
    scored.sort(key=lambda item: (-item.get("answer_overlap", 0), item.get("adjusted_distance") or 9))
    if scored:
        best = scored[0]["answer_overlap"]
        scored = [item for item in scored if item["answer_overlap"] >= max(min_overlap, best - 1)]
        return _dedupe_pages(scored)
    if evidence:
        return _dedupe_pages(evidence[:1])
    return []


def _dedupe_pages(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        key = (
            item.get("source_type"),
            item.get("printed_page_number") or item.get("textbook_page_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

"""Keep student-facing citations to pages that support the final answer."""

from __future__ import annotations

import re

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
    "mahal",
    "fort",
    "time",
    "period",
}

PHRASES = (
    "taj mahal",
    "tajmahal",
    "din-e-ilahi",
    "din e ilahi",
    "third battle of panipat",
    "madhav rao",
    "baji rao",
    "shah jahan",
    "shahjahan",
    "guerilla",
    "guerrilla",
)

SHORT_PROPER = {"taj", "zat", "din", "agra"}


def citation_tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z]{3,}|[\u0C80-\u0CFF]{3,}", (text or "").lower())
    kept = set()
    for word in words:
        if word in CITATION_GENERIC:
            continue
        if len(word) >= 4 or word in SHORT_PROPER:
            kept.add(word)
    return kept


def supporting_evidence(answer: str, evidence: list[dict], min_overlap: int = 2) -> list[dict]:
    answer_text = answer or ""
    answer_tokens = citation_tokens(answer_text)
    phrases = [phrase for phrase in PHRASES if phrase in answer_text.lower()]
    scored = []
    for item in evidence:
        text = item.get("text") or ""
        lowered = text.lower()
        overlap = len(answer_tokens & citation_tokens(text))
        bonus = 0
        for phrase in phrases:
            if phrase in lowered:
                bonus += 5
        score = overlap + bonus
        if score >= min_overlap or bonus:
            scored.append({**item, "answer_overlap": score})
    scored.sort(key=lambda item: (-item.get("answer_overlap", 0), item.get("adjusted_distance") or 9))
    if not scored:
        return _dedupe_pages(evidence[:1]) if evidence else []
    best = scored[0]["answer_overlap"]
    kept = [
        item
        for item in scored
        if item["answer_overlap"] >= max(min_overlap, int(best * 0.8))
        and item["answer_overlap"] >= best - 3
    ]
    short = len(answer_text.split()) <= 22
    if short:
        kept = kept[:1]
    else:
        kept = kept[:8]
    return _dedupe_pages(kept)


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

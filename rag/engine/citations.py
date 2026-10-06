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
        return []
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
    # Per-sentence attribution: every answer sentence credits the page it actually came from.
    ids = {id(item) for item in kept}
    keys = {(item.get("chunk_id"), item.get("printed_page_number")) for item in kept}
    for item in sentence_supporting_evidence(answer_text, evidence):
        key = (item.get("chunk_id"), item.get("printed_page_number"))
        if id(item) not in ids and key not in keys:
            kept.append(item)
            ids.add(id(item))
            keys.add(key)
    kept.sort(key=_page_order)
    return _dedupe_pages(kept)


def _page_order(item: dict) -> int:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 9999


def _attr_stems(text: str) -> set[str]:
    stems = {token[:6] for token in citation_tokens(text)}
    stems.update(re.findall(r"\b\d{2,4}\b", text or ""))
    return stems


def _attribution_units(answer: str) -> list[str]:
    units = []
    for line in (answer or "").splitlines():
        line = re.sub(r"\[Pages?\s*[0-9,\s\-]+\]", " ", line).strip()
        if not line or line.startswith(("Source", "#")):
            continue
        units.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
    return units


def sentence_supporting_evidence(answer: str, evidence: list[dict]) -> list[dict]:
    """Chunk(s) that best support each individual answer sentence."""
    chunk_stems = [_attr_stems(item.get("text") or "") for item in evidence]
    picked: list[dict] = []
    for unit in _attribution_units(answer):
        stems = _attr_stems(unit)
        if len(stems) < 3 or not chunk_stems:
            continue
        scored = sorted(((len(stems & cs), idx) for idx, cs in enumerate(chunk_stems)), key=lambda p: (-p[0], p[1]))
        best = scored[0][0]
        if best < max(3, -(-len(stems) // 2)):
            continue
        top = [idx for score, idx in scored[:2] if score == best]
        for idx in top:
            if evidence[idx] not in picked:
                picked.append(evidence[idx])
        # A sentence can combine facts from two pages: credit a chunk that supplies the rest.
        residual = stems - set().union(*(chunk_stems[idx] for idx in top))
        for score, idx in scored:
            if idx in top or score < 3:
                continue
            if residual & chunk_stems[idx]:
                if evidence[idx] not in picked:
                    picked.append(evidence[idx])
                break
    return picked


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

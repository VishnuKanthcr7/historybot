"""Universal entity evidence: subject vs mention, complete packs, coverage groups.

No person-specific branches. Groups are created only from textbook sentences.
"""

from __future__ import annotations

import re
from collections import defaultdict

from rag.engine.classify import TOPIC_ALIASES, extract_topics
from rag.engine.evidence import looks_like_exercise_chunk
from rag.engine.topic_map import RULER_KEYS, chunks_for_topics, load_primary_chunks, looks_like_map_chunk

HEADING_RE = re.compile(
    r"\b([A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,4})\s*:",
)
SEGMENT_SPLIT = re.compile(
    r"(?=\b[A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,4}\s*:)",
)

GROUP_RULES = (
    ("identity", ("born", "son of", "appointed", "years old", "came to power", "ascended", "became")),
    ("actions", ("conquer", "campaign", "battle", "war", "defeated", "declared", "marched", "attack", "fought")),
    ("administration", ("tax", "chauth", "sardeshmukhi", "ruled", "efficiency", "minister", "administration", "official")),
    ("achievements", ("glory", "fame", "called", "established", "re-established", "image")),
)

GROUP_HEADINGS = {
    "identity": "Who was this person?",
    "actions": "What did they do?",
    "administration": "How did they rule?",
    "achievements": "Why does the textbook mention them?",
    "details": "Important points",
}

STOP_MARKERS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "were",
    "was",
    "his",
    "her",
    "they",
    "their",
    "after",
    "before",
    "also",
    "only",
    "into",
    "over",
    "under",
    "textbook",
    "thus",
    "hence",
    "although",
    "when",
    "then",
    "north",
    "south",
    "india",
}


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _aliases(entity: str) -> tuple[str, ...]:
    return tuple(alias for alias in TOPIC_ALIASES.get(entity, (entity,)) if alias.isascii())


def _mentions(text: str, entity: str) -> int:
    lowered = (text or "").lower()
    others_first = []
    for key, title in _titles().items():
        if key != entity and title:
            others_first.append(title.split()[0].lower())
    total = 0
    for alias in _aliases(entity):
        for match in re.finditer(re.escape(alias), lowered):
            prefix = lowered[max(0, match.start() - 16) : match.start()].rstrip()
            if any(prefix.endswith(first) for first in others_first):
                continue
            total += 1
    return total


def _titles() -> dict[str, str]:
    from rag.engine.coverage import GROUP_TITLE

    return GROUP_TITLE


def _alias_catalog() -> list[tuple[str, str]]:
    rows = []
    for key, aliases in TOPIC_ALIASES.items():
        for alias in aliases:
            if alias.isascii() and len(alias) >= 4:
                rows.append((key, alias.lower()))
        title = _titles().get(key)
        if title:
            rows.append((key, title.lower()))
    rows.sort(key=lambda item: len(item[1]), reverse=True)
    return rows


def heading_entity_key(text: str) -> str | None:
    """Longest alias that the opening heading starts with."""
    blob = " ".join((text or "").split())
    if not blob:
        return None
    match = HEADING_RE.search(blob[:180])
    heading = (match.group(1) if match else blob[:80]).lower().strip()
    heading = re.sub(r"\s+", " ", heading)
    best_key = None
    best_len = 0
    for key, alias in _alias_catalog():
        if heading == alias or heading.startswith(alias + " ") or heading.startswith(alias + ":"):
            if len(alias) > best_len:
                best_key = key
                best_len = len(alias)
    return best_key



def _other_ruler_keys(entity: str) -> set[str]:
    return {key for key in RULER_KEYS if key != entity}


def _alias_pattern(entity: str) -> str:
    aliases = sorted(_aliases(entity), key=len, reverse=True)
    if not aliases:
        return re.escape(entity)
    return "|".join(re.escape(alias) for alias in aliases)


def _is_posthumous_bleed(text: str, entity: str) -> bool:
    """True when the sentence is about events after the entity died (successor/next ruler)."""
    if not text or not entity:
        return False
    low = text.lower()
    pat = _alias_pattern(entity)
    if re.search(rf"\bafter\s+(?:the\s+)?(?:death|demise)\s+of\s+(?:{pat})\b", low):
        return True
    if re.search(rf"\bafter\s+(?:{pat})\s+(?:died|was\s+killed|was\s+murdered|passed\s+away)\b", low):
        return True
    if re.search(rf"\bwhen\s+(?:{pat})\s+(?:died|passed\s+away|was\s+killed)\b", low):
        return True
    if re.search(rf"\b(?:following|upon)\s+(?:the\s+)?death\s+of\s+(?:{pat})\b", low):
        return True
    if re.search(rf"^(?:{pat})\s*:\s*after\s+", low):
        return True
    # Successor-as-Who bleed: "After Akbar, his elder son Jahangir ruled..."
    if re.search(
        rf"\bafter\s+(?:{pat})\s*,?\s+(?:his|her)\s+(?:elder\s+|younger\s+)?(?:son|daughter|brother|successor)\b",
        low,
    ):
        return True
    if re.search(
        rf"\bafter\s+(?:{pat})\s*,\s+[a-z][a-z.\s]{{0,40}}?\b(?:ruled|became|was\s+appointed|took\s+over|succeeded)\b",
        low,
    ):
        return True
    return False


def _entity_object_only(text: str, entity: str) -> bool:
    """Entity appears mainly as object (son of X / defeated X / imprisoned X), not as actor."""
    if not text or not entity:
        return False
    low = " ".join(text.lower().split())
    pat = _alias_pattern(entity)
    objectish = re.search(
        rf"\b(?:son of|daughter of|father of|mother of|defeated|imprisoned|killed|tortured|succeeded|successor of)\s+(?:{pat})\b",
        low,
    )
    if not objectish:
        return False
    start = low[: max(0, objectish.start())]
    if _mentions(start, entity) > 0:
        return False
    for other in _other_ruler_keys(entity):
        if _mentions(start, other) > 0:
            return True
    if re.match(r"^(?:he|she|they)\b", low):
        return True
    return False


def _looks_corrupt_sentence(text: str) -> bool:
    """Drop smashed / OCR-corrupt fragments that invent wrong grammar."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return True
    words = clean.split()
    if len(words) < 5:
        return True
    if re.match(
        r"^(?:[a-z]{1,3}|cting|i assembled|o power|eauty|rule in|was an|were \d|st famous|he Mughals)\b",
        clean,
    ):
        return True
    if re.search(
        r"\b(?:relationship|between|history of)\b.*\band\s+[A-Z][A-Za-z].{0,40}\b(?:fought|defeated|conquered|imprisoned)\b",
        clean,
        re.I,
    ):
        return True
    # "history of Akbar emerged" / glued name+verb after of
    if re.search(
        r"\b(?:history of|story of|life of)\s+[A-Z][A-Za-z]+(?:\s+(?:[IVX]{1,4}|[A-Z][A-Za-z]+))?\s+(emerged|was|were|became|launched|fought|declared|assumed|conquered|defeated|appointed|established|wrote|built)\b",
        clean,
    ):
        return True
    if re.search(r"do you know this", clean, re.I):
        return True
    if re.search(r"\bafter\s+[A-Z][A-Za-z][A-Za-z.\s]{0,24}died,\s+he\b", clean, re.I):
        return True
    if re.match(r"^[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s*:\s*", clean) and "after the death" in clean.lower():
        return True
    # Dangling unresolved referent / OCR smash mid-clause.
    if re.search(r"\bprotested against this\b", clean, re.I):
        return True
    if re.search(r",\s+With\s+(?:an\s+intention|the\s+intention|a\s+view)\b", clean):
        return True
    if re.search(r"\bWhen\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}\s+protested against this,\s*With\b", clean):
        return True
    return False


def entity_subject_score(text: str, entity: str) -> tuple[int, str]:
    from rag.engine.pack import dominant_ruler, ruler_counts

    if not text or not entity:
        return 0, "empty"
    if _looks_corrupt_sentence(text):
        return 0, "corrupt"
    if _is_posthumous_bleed(text, entity):
        return 0, "posthumous-bleed"
    if _entity_object_only(text, entity):
        return 0, "object-mention"
    mentions = _mentions(text, entity)
    if mentions <= 0:
        return 0, "no-mention"
    heading = heading_entity_key(text)
    if heading == entity:
        return 5 + min(mentions, 3), "heading-subject"
    if heading and heading in RULER_KEYS and heading != entity:
        return 0, "other-heading"
    dominant = dominant_ruler(text)
    if dominant == entity:
        return 4 + min(mentions, 2), "dominant-subject"
    if dominant and dominant != entity and mentions <= ruler_counts(text).get(dominant, 0):
        return 0, "incidental-mention"
    start = " ".join(text.split())[:160].lower()
    if heading is None and any(alias in start for alias in _aliases(entity)):
        if _mentions(start, entity) > 0:
            return 3, "leads-with-entity"
    return 1, "mention-only"


def split_entity_segments(text: str) -> list[str]:
    blob = " ".join((text or "").split())
    if not blob:
        return []
    parts = [part.strip() for part in SEGMENT_SPLIT.split(blob) if part.strip()]
    return parts or [blob]


def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in chunks:
        focused = " ".join((item.get("text") or "").split())
        key = re.sub(r"[^a-z0-9]+", "", focused[:120].lower())
        if len(key) < 20 or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect_entity_chunks(entity: str, extra: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """All primary chunks whose subject is the entity, plus nearby page continuations."""
    from rag.engine.pack import _merge, _order, ahom_primary_chunk, looks_like_toc

    mapped = chunks_for_topics({entity}) if entity else []
    pages = {_page(item) for item in mapped if _page(item) is not None}
    if extra:
        pages |= {_page(item) for item in extra if _page(item) is not None}
        mapped = _merge(mapped, extra)
    nearby = []
    for item in load_primary_chunks():
        page = _page(item)
        if page is None:
            continue
        if page in pages or (pages and min(abs(page - p) for p in pages) == 1):
            nearby.append(item)
    merged = _merge(mapped, nearby)
    kept = []
    excluded = []
    for item in merged:
        text = item.get("text") or ""
        if looks_like_toc(text) or looks_like_map_chunk(text) or looks_like_exercise_chunk(item):
            excluded.append({**item, "exclusion_reason": "toc-or-exercise"})
            continue
        if ahom_primary_chunk(item) and entity != "ahom":
            excluded.append({**item, "exclusion_reason": "ahom-primary"})
            continue
        segments = split_entity_segments(text)
        useful = []
        reasons = []
        for segment in segments:
            score, reason = entity_subject_score(segment, entity)
            if score >= 3:
                useful.append(segment)
                reasons.append(reason)
        if not useful:
            score, reason = entity_subject_score(text, entity)
            if score < 3:
                excluded.append({**item, "exclusion_reason": reason, "subject_score": score})
                continue
            useful = [text]
            reasons = [reason]
        kept.append(
            {
                **item,
                "text": " ".join(useful),
                "subject_score": max(entity_subject_score(part, entity)[0] for part in useful),
                "relevance_reason": ",".join(sorted(set(reasons))),
            }
        )
    kept = _dedupe_chunks(_order(kept))
    return kept, excluded


def _entity_sentences(chunks: list[dict], entity: str) -> list[dict]:
    rows = []
    seen = set()
    for item in chunks:
        page = _page(item)
        for segment in split_entity_segments(item.get("text") or ""):
            score, _reason = entity_subject_score(segment, entity)
            if score < 3:
                continue
            for sent in re.split(r"(?<=[.!?])\s+", segment):
                clean = re.sub(r"\s+", " ", sent).strip()
                clean = re.sub(
                    r"^(?:[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s*:\s*",
                    "",
                    clean,
                ).strip()
                words = clean.split()
                if len(words) < 5 or len(words) > 90:
                    continue
                if words[-1].lower().strip(".,;:") in {"the", "of", "and", "to", "a", "an", "with", "for", "in"}:
                    continue
                sent_score, sent_reason = entity_subject_score(clean, entity)
                if sent_score < 3:
                    continue
                key = re.sub(r"[^a-z0-9]+", "", clean.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"text": clean, "page": page, "chunk": item, "reason": sent_reason})
    return rows


def _assign_group(sentence: str) -> str:
    low = sentence.lower()
    for key, needles in GROUP_RULES:
        if any(needle in low for needle in needles):
            return key
    return "details"


def _markers_from_sentences(sentences: list[str], entity: str) -> list[str]:
    aliases = set(_aliases(entity))
    title_bits = set()
    for alias in aliases:
        title_bits.update(alias.split())
    found: list[str] = []
    seen = set()
    for sent in sentences:
        for word in re.findall(r"\b[A-Z][A-Za-z]{3,}\b", sent) + re.findall(r"\b(1[4-9]\d{2})\b", sent):
            low = word.lower()
            if low in STOP_MARKERS or low in title_bits or any(low in alias for alias in aliases):
                continue
            if low not in seen:
                seen.add(low)
                found.append(low)
    if not found:
        for sent in sentences:
            for word in re.findall(r"[A-Za-z]{6,}", sent.lower()):
                if word in STOP_MARKERS or word in title_bits:
                    continue
                if word not in seen:
                    seen.add(word)
                    found.append(word)
    return found[:8]


def build_entity_plan(question: str, chunks: list[dict], entity: str | None = None) -> list:
    from rag.engine.coverage import CoverageGroup
    from rag.engine.pack import detect_entity

    del question
    entity = entity or detect_entity(extract_topics(" ".join(item.get("text") or "" for item in chunks)))
    if not entity:
        return []
    rows = _entity_sentences(chunks, entity)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[_assign_group(row["text"])].append(row)
    groups = []
    for key in ("identity", "actions", "administration", "achievements", "details"):
        rows_for = buckets.get(key) or []
        if not rows_for:
            continue
        pages = sorted({row["page"] for row in rows_for if row["page"] is not None})
        chunk_map = {}
        for row in rows_for:
            chunk = row["chunk"]
            cid = chunk.get("chunk_id") or id(chunk)
            if cid not in chunk_map:
                chunk_map[cid] = {**chunk, "text": row["text"]}
            else:
                chunk_map[cid]["text"] = f"{chunk_map[cid]['text']} {row['text']}"
        sentences = [row["text"] for row in rows_for]
        groups.append(
            CoverageGroup(
                key=f"{entity}:{key}",
                title=GROUP_HEADINGS.get(key) or key.title(),
                pages=pages,
                chunks=list(chunk_map.values()),
                markers=_markers_from_sentences(sentences, entity) or list(_aliases(entity)[:2]),
            )
        )
    return groups


def entity_readable(groups: list) -> str:
    dangling = {"the", "of", "and", "to", "a", "an", "with", "for", "in"}
    parts = []
    seen = set()
    for group in groups:
        entity = None
        if getattr(group, "key", None) and ":" in group.key:
            entity = group.key.split(":", 1)[0]
        sentences = []
        for item in group.chunks:
            for sent in re.split(r"(?<=[.!?])\s+", item.get("text") or ""):
                clean = re.sub(r"\s+", " ", sent).strip()
                clean = re.sub(
                    r"^(?:[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s*:\s*",
                    "",
                    clean,
                ).strip()
                words = clean.split()
                if len(words) < 5:
                    continue
                if words[-1].lower().strip(".,;:") in dangling:
                    continue
                if entity:
                    score, _reason = entity_subject_score(clean, entity)
                    if score < 3:
                        continue
                key = re.sub(r"[^a-z0-9]+", "", clean.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                sentences.append(clean)
        if not sentences:
            continue
        parts.append(" ".join(sentences[:12]))
    return "\n\n".join(parts)

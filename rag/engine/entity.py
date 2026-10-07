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
    (
        "administration",
        (
            "tax",
            "chauth",
            "sardeshmukhi",
            "ruled",
            "efficiency",
            "minister",
            "administration",
            "administrative",
            "official",
            "revenue",
            "ryotwari",
            "judicial",
            "justice",
            "province",
            "subha",
            "mansab",
            "pargana",
            "hierarchy",
            "hierarchies",
            "governor",
            "executive",
            "judiciary",
        ),
    ),
    ("achievements", ("glory", "fame", "called", "established", "re-established", "image")),
)
# "Name II" / "Name, the second" is a later person or epithet.
# "Name, the second emperor/king" is an appositive about that same person.
# "Name I" still matches the unnumbered name.
_LATER_REGNAL_RE = re.compile(
    r"(?:"
    r"\s+(?:ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\b"
    r"|"
    r"\s*,\s*the\s+(?:second|third|fourth|fifth)\b"
    r"(?!\s+(?:[a-z]+\s+){0,2}(?:emperor|king|ruler|sultan|monarch|peshwa|shah)\b)"
    r")",
    re.I,
)
# Chunk overlap glues a short leftover ("yun") onto the next sentence.
# A real function word ("he", "the") is not that leftover.
_LEADING_STUB_RE = re.compile(r"^([a-z]{1,4})\s+(?=[A-Z][a-z])")
_STUB_WORDS = {
    "he", "she", "it", "his", "her", "the", "and", "but", "for", "was", "were",
    "who", "its", "our", "may", "not", "had", "has", "did", "one", "two", "all",
    "any", "this", "that", "they", "them", "with", "from", "into", "over", "such",
    "when", "then", "also", "only", "after", "before", "while", "their", "there",
}

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


ARTICLE_WORDS = {"the", "a", "an"}

# Textbook term introduction that refers back: "<context>. These were called 'Mansabs' ..."
TERM_BACKREF_RE = re.compile(
    r"^(?:these|this|those|such|they)(?:\s+[a-z]+)?\s+(?:were|was|are|is)\s+(?:called|known|named|termed)\b",
    re.I,
)


def keep_term_antecedents(sentences: list[str], keep: list[bool], entity: str | None) -> list[bool]:
    """Keep a short 'these/they were called' definition with the sentence it continues."""
    out = list(keep)
    for idx in range(1, len(sentences)):
        current = (sentences[idx] or "").strip()
        if out[idx - 1] and not out[idx] and TERM_BACKREF_RE.match(current):
            out[idx] = True
    if not entity or entity in RULER_KEYS:
        return out
    for idx in range(1, len(sentences)):
        prev = (sentences[idx - 1] or "").strip()
        if (
            keep[idx]
            and not keep[idx - 1]
            and TERM_BACKREF_RE.match((sentences[idx] or "").strip())
            and len(prev.split()) >= 5
            and not _looks_corrupt_sentence(prev)
        ):
            out[idx - 1] = True
    return out


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _aliases(entity: str) -> tuple[str, ...]:
    return tuple(alias for alias in TOPIC_ALIASES.get(entity, (entity,)) if alias.isascii())


def repair_leading_stub(text: str) -> str:
    """Drop a chunk-overlap fragment glued onto a complete sentence.

    The fragment and the sentence share one full stop, so discarding the line
    as corrupt also discards the identity it states.
    """
    clean = re.sub(r"\s+", " ", text or "").strip()
    match = _LEADING_STUB_RE.match(clean)
    if not match or match.group(1) in _STUB_WORDS:
        return clean
    rest = clean[match.end() :].strip()
    if len(rest.split()) < 5:
        return clean
    return rest


def _later_regnal(lowered: str, end: int) -> bool:
    """True when the matched name is followed by a later regnal number (II, III, ...)."""
    return bool(_LATER_REGNAL_RE.match(lowered[end:]))


def epithet_only_rulers(text: str) -> set[str]:
    """Rulers who appear in text only as a later-regnal epithet.

    "called Shivaji II" names an epithet. It is not a question about Shivaji.
    A bare mention of that same name anywhere in the text still counts as the person.
    """
    lowered = (text or "").lower()
    epithets: set[str] = set()
    for key in RULER_KEYS:
        bare = 0
        later = 0
        for alias in _aliases(key):
            for match in re.finditer(_alias_pattern(alias), lowered):
                name_end = match.end()
                if match.group(0).endswith("s") and not alias.lower().endswith("s"):
                    name_end -= 1
                if _later_regnal(lowered, name_end):
                    later += 1
                else:
                    bare += 1
        if later and not bare:
            epithets.add(key)
    return epithets


def _alias_pattern(alias: str) -> str:
    # Optional plural s, but not a letter that continues a different word.
    return r"(?<![a-z])" + re.escape(alias.lower()) + r"s?(?![a-z])"


def _mentions(text: str, entity: str) -> int:
    lowered = (text or "").lower()
    others_first = []
    for key, title in _titles().items():
        if key != entity and title:
            first = title.split()[0].lower()
            # "The Peshwas"/"The Marathas" must not make "the Mansabdari system" a non-mention.
            if first in ARTICLE_WORDS:
                continue
            others_first.append(first)
    total = 0
    for alias in _aliases(entity):
        for match in re.finditer(_alias_pattern(alias), lowered):
            name_end = match.end()
            if match.group(0).endswith("s") and not alias.lower().endswith("s"):
                name_end -= 1
            if _later_regnal(lowered, name_end):
                continue
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
    clean = repair_leading_stub(text)
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
    # Chunk-overlap smash: "...achievements of These were called 'Mansabs'..."
    if re.search(r"\b(?:of|to|and|in|with|for|by|the|a|an)\s+(?:These|This|Those)\s+(?:were|was|is|are)\b", clean):
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
    # Overlap smash: "...Jaisingh called With an intention to stop..."
    if re.search(r"\b[a-z]+\s+With\s+(?:an|the)\s+intention\b", clean):
        return True
    # Heading glued onto the next clause: "Shivaji In addition to defeating..."
    if re.search(r"\b[A-Za-z]+\s+In addition to\b", clean):
        return True
    # A participial continuation whose subject was the previous sentence's person.
    # The following purpose clause ("To achieve this, he ...") must not inherit that person;
    # the caller records this skip as a broken antecedent.
    if re.match(r"^In addition to\b", clean):
        return True
    if re.search(r"\bWhen\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}\s+protested against this,\s*With\b", clean):
        return True
    return False


def other_time_owner(sentence: str) -> str | None:
    """The ruler a sentence itself assigns its time to, such as "During Shah Jahan's time"."""
    text = " ".join((sentence or "").split())
    match = re.match(
        r"^(?:during|in)\s+(?:the\s+)?(?:time|reign|rule|period|era)\s+of\s+"
        r"([A-Z][A-Za-z'\u2019\-]+(?:\s+[A-Z][A-Za-z'\u2019\-]+){0,3})",
        text,
    )
    if not match:
        match = re.match(
            r"^(?:during|in)\s+([A-Z][A-Za-z'\u2019\-]+(?:\s+[A-Z][A-Za-z'\u2019\-]+){0,3})"
            r"(?:'s|\u2019s)\s+(?:time|reign|rule|period|era)\b",
            text,
        )
    if not match:
        return None
    spans = _person_spans(match.group(1))
    if spans:
        return spans[0][2]
    return None


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
    owner = other_time_owner(text)
    if owner and owner != entity:
        return 0, "other-time"
    mentions = _mentions(text, entity)
    if mentions <= 0:
        return 0, "no-mention"
    from rag.engine.pack import PLACE_EVENT_KEYS

    heading = heading_entity_key(text)
    if heading == entity:
        return 5 + min(mentions, 3), "heading-subject"
    if heading and heading in RULER_KEYS and heading != entity and entity in RULER_KEYS:
        return 0, "other-heading"
    # The passage opens with this person. A parent or rival named inside that
    # sentence must not make the whole passage an incidental mention.
    opening = repair_leading_stub(text)
    first = re.split(r"(?<=[.!?])\s+", " ".join(opening.split()), maxsplit=1)[0]
    if _resolve_subject(first, None)[0] == entity:
        return 4, "opening-subject"
    # Place/event focus keys: a single clear mention is enough even beside a co-named ruler.
    if entity in PLACE_EVENT_KEYS:
        return 4 + min(mentions, 2), "place-event-subject"
    from rag.engine.pack import entity_has_agency

    dominant = dominant_ruler(text)
    if dominant == entity:
        return 4 + min(mentions, 2), "dominant-subject"
    if entity_has_agency(text, entity):
        return 3 + min(mentions, 2), "agency-co-mention"
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


def sentences_before_entity_heading(text: str, entity: str | None) -> set[str]:
    """Norms of sentences that precede this person's heading in the source text.

    Chunk overlap pastes that earlier section back after the heading. Those copies
    belong to the previous section, not to the person the heading introduces.
    """
    if not text or not entity:
        return set()
    blob = " ".join(text.split())
    heading_at = None
    for match in FOCUS_HEADING_RE.finditer(blob):
        people = [key for (_a, _b, key) in _person_spans(match.group(1))]
        key = people[0] if people else heading_entity_key(match.group(1) + " :")
        if key == entity:
            heading_at = match.start()
            break
    if heading_at is None:
        return set()
    norms: set[str] = set()
    for sent in re.split(r"(?<=[.!?])\s+", blob[:heading_at]):
        norm = re.sub(r"[^a-z0-9]+", " ", sent.lower()).strip()
        if len(norm.split()) >= 5:
            norms.add(norm)
    return norms


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
            segment = repair_leading_stub(segment)
            score, reason = entity_subject_score(segment, entity)
            if score < 3 and reason == "corrupt":
                # A chunk overlap can leave "i assembled..." in front of a complete
                # sentence ("Shivaji conquered ..."). Drop only the broken prefix.
                sentences = [
                    repair_leading_stub(part.strip())
                    for part in re.split(r"(?<=[.!?])\s+", segment)
                    if part.strip()
                ]
                while sentences and _looks_corrupt_sentence(sentences[0]):
                    sentences.pop(0)
                if sentences:
                    segment = " ".join(sentences)
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
                "pre_heading_norms": sentences_before_entity_heading(text, entity),
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
            if score < 3 and not item.get("focus_filtered"):
                continue
            cleaned = []
            flags = []
            reasons = []
            for sent in re.split(r"(?<=[.!?])\s+", segment):
                clean = repair_leading_stub(re.sub(r"\s+", " ", sent).strip())
                clean = re.sub(
                    r"^(?:[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s*:\s*",
                    "",
                    clean,
                ).strip()
                words = clean.split()
                definition = bool(TERM_BACKREF_RE.match(clean)) and len(words) >= 3
                ok = (definition or 5 <= len(words) <= 90) and words[-1].lower().strip(".,;:") not in {
                    "the", "of", "and", "to", "a", "an", "with", "for", "in"
                }
                sent_score, sent_reason = entity_subject_score(clean, entity) if ok else (0, "skip")
                if item.get("focus_filtered") and ok:
                    sent_score, sent_reason = 3, "focus-filtered"
                cleaned.append(clean)
                flags.append(ok and sent_score >= 3)
                reasons.append(sent_reason)
            final = keep_term_antecedents(cleaned, flags, entity)
            pending = ""
            for idx, clean in enumerate(cleaned):
                if not final[idx]:
                    continue
                if not flags[idx]:
                    # Antecedent of a term introduction: attach to the following kept sentence.
                    pending = clean
                    continue
                text = f"{pending} {clean}".strip() if pending else clean
                if FOCUS_ANAPHOR_RE.match(clean) and idx > 0:
                    previous = cleaned[idx - 1]
                    if previous and previous.lower() not in text.lower():
                        text = f"{previous} {text}".strip()
                pending = ""
                key = re.sub(r"[^a-z0-9]+", "", clean.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"text": text, "page": page, "chunk": item, "reason": reasons[idx]})
    return rows


def _assign_group(sentence: str) -> str:
    low = sentence.lower()
    for key, needles in GROUP_RULES:
        if any(re.search(rf"\b{re.escape(needle)}s?\b", low) for needle in needles):
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
            cleaned = []
            flags = []
            for sent in re.split(r"(?<=[.!?])\s+", item.get("text") or ""):
                clean = repair_leading_stub(re.sub(r"\s+", " ", sent).strip())
                clean = re.sub(
                    r"^(?:[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s*:\s*",
                    "",
                    clean,
                ).strip()
                words = clean.split()
                definition = bool(TERM_BACKREF_RE.match(clean)) and len(words) >= 3
                ok = (definition or len(words) >= 5) and words[-1].lower().strip(".,;:") not in dangling
                if ok and entity and not item.get("focus_filtered"):
                    score, _reason = entity_subject_score(clean, entity)
                    ok = score >= 3
                cleaned.append(clean)
                flags.append(ok)
            final = list(keep_term_antecedents(cleaned, flags, entity) if entity else flags)
            for index, clean in enumerate(cleaned):
                if FOCUS_ANAPHOR_RE.match(clean) and index > 0:
                    final[index - 1] = True
                    final[index] = True
            for clean, keep in zip(cleaned, final):
                if not keep:
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


# --- Subject-resolved evidence for single-person identity questions --------------
# Multi-person textbook passages ("After Shivaji died, he imprisoned Sambhaji...") must not
# hand another person's actions to the asked person. Each sentence's grammatical subject is
# resolved (explicit name, or a pronoun carried from the previous subject / heading) and
# only sentences whose subject is the focus person (or that describe "his ..." while the
# focus person is the current subject) are kept.

FOCUS_LEAD_RE = re.compile(
    r"^(?:but|and|thus|hence|therefore|so|then|later|also|however|moreover|"
    r"in this manner|in this way|at this juncture|as a result)\b,?\s*",
    re.I,
)
FOCUS_SUBORDINATE_RE = re.compile(
    r"^(?:when|after|since|as|although|though|while|because|before|once|with|due to|"
    r"in addition to|on|during|following)\b",
    re.I,
)
FOCUS_PRONOUN_RE = re.compile(r"^(?:he|she)\b", re.I)
FOCUS_NEUTRAL = {
    "the", "a", "an", "in", "his", "her", "their", "this", "these", "that", "those", "it",
    "there", "its", "such", "at", "by", "for", "of", "from", "to",
}
FOCUS_NOISE_RE = re.compile(r"@?KTBS\s*NOT\s+TO\s+BE\s+REPUBLISHED|@KTBS|Do you know this\?", re.I)
FOCUS_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
# Chunk-overlap smash: "...expanding the Thus he established..." / "...areas near He launched..."
FOCUS_SMASH_RE = re.compile(
    r"\b(the|a|an|of|to|near|and|in|with|for|by|including|from|at)\s+"
    r"(?=(?:Thus|He|She|They|This|These|Hence|But|When|After|Although|In addition|Due to)\b)"
)
FOCUS_DANGLING_RE = re.compile(
    r"\b(?:the|a|an|of|to|near|and|in|with|for|by|including|from|at|as|his|her|their)[.!?]?$", re.I
)


def _focus_alias_table() -> list[tuple[str, str]]:
    rows = []
    for key in RULER_KEYS:
        names = {alias.lower() for alias in _aliases(key)}
        title = _titles().get(key)
        if title:
            names.add(title.lower())
            if "-" in title:
                head = re.split(r"[\s\-]+", title.lower())[0]
                if len(head) >= 4:
                    names.add(head)
        for name in names:
            rows.append((key, name))
    rows.sort(key=lambda item: len(item[1]), reverse=True)
    return rows


def _person_spans(text: str) -> list[tuple[int, int, str]]:
    lowered = (text or "").lower()
    titles = _titles()
    spans: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []
    for key, name in _focus_alias_table():
        others_first = []
        for other, title in titles.items():
            if other != key and title:
                first = title.split()[0].lower()
                if first not in ARTICLE_WORDS and not name.startswith(first):
                    others_first.append(first)
        for match in re.finditer(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", lowered):
            if _later_regnal(lowered, match.end()):
                continue
            if any(a < match.end() and match.start() < b for a, b in taken):
                continue
            prefix = lowered[max(0, match.start() - 16) : match.start()].rstrip()
            if any(prefix.endswith(first) for first in others_first):
                continue
            spans.append((match.start(), match.end(), key))
            taken.append((match.start(), match.end()))
    spans.sort()
    return spans


def _resolve_subject(sentence: str, current: str | None) -> tuple[str | None, str, int]:
    """Return (subject key | 'OTHER' | None, how, pronoun_offset)."""
    text = sentence.strip()
    spans = _person_spans(text)
    off = 0
    lead = FOCUS_LEAD_RE.match(text)
    if lead:
        off = lead.end()
    head_keys: list[str] = []
    rest = text[off:]
    sub = FOCUS_SUBORDINATE_RE.match(rest)
    if sub:
        comma = rest.find(",")
        if comma > 0:
            head_keys = [key for (a, _b, key) in spans if off <= a < off + comma]
            off = off + comma + 1
        else:
            off = off + sub.end()
    while off < len(text) and text[off] in " ,;:":
        off += 1
    lead = FOCUS_LEAD_RE.match(text[off:])
    if lead:
        off += lead.end()
    tail = text[off:]
    if FOCUS_PRONOUN_RE.match(tail):
        if head_keys and not _is_posthumous_bleed(text, head_keys[-1]):
            return head_keys[-1], "pronoun-head", off
        return current, "pronoun", off
    for a, b, key in spans:
        if a == off:
            if text[b : b + 2] in ("'s", "\u2019s"):
                return "OTHER", "possessive", -1
            return key, "name", -1
    first = re.match(r"[A-Za-z][A-Za-z'\-]*", tail)
    word = first.group(0) if first else ""
    if word and word[0].isupper() and word.lower() not in FOCUS_NEUTRAL:
        return "OTHER", "other-name", -1
    later = [key for (a, _b, key) in spans if a >= off]
    if later:
        return later[0], "name-later", -1
    if re.search(r"\b(?:he|she)\b", tail, re.I):
        return current, "pronoun-inner", -1
    return None, "neutral", -1


# A sentence that only makes sense after the one before it ("Due to this, ... came to Baji Rao").
FOCUS_ANAPHOR_RE = re.compile(
    r"^(?:due to this|because of this|as a result|thus|hence|therefore|in addition to this|so)\b,?\s*", re.I
)
# "To achieve this, he ..." points at the immediately previous sentence, not an earlier person.
FOCUS_PURPOSE_RE = re.compile(r"^To\s+\w+\s+this\b", re.I)
FOCUS_HEADING_RE = re.compile(
    r"(?:^|(?<=[.!?])\s+)([A-Z][A-Za-z'\u2019\-]+(?:\s+[A-Za-z'\u2019\-]+){0,3})\s*:\s*"
)


def _focus_segments(text: str) -> list[tuple[str | None, str]]:
    """(heading, body) pairs; a heading only counts at text start or right after a sentence end."""
    blob = " ".join((text or "").split())
    out: list[tuple[str | None, str]] = []
    last = 0
    heading = None
    for match in FOCUS_HEADING_RE.finditer(blob):
        if re.match(r"(?:He|She|They|It|There|This)\b", match.group(1)):
            continue
        out.append((heading, blob[last:match.start()]))
        heading = match.group(1)
        last = match.end()
    out.append((heading, blob[last:]))
    return [(h, b.strip()) for h, b in out if b.strip()]


def _collapse_repeats(text: str) -> str:
    """Remove chunk-overlap duplicates: a run of words immediately repeated ("X Y Z X Y Z")."""
    words = (text or "").split()
    changed = True
    while changed:
        changed = False
        for size in range(min(60, len(words) // 2), 1, -1):
            for i in range(0, len(words) - 2 * size + 1):
                left = [re.sub(r"[^A-Za-z0-9]+", "", word).lower() for word in words[i : i + size]]
                right = [re.sub(r"[^A-Za-z0-9]+", "", word).lower() for word in words[i + size : i + 2 * size]]
                if left == right and any(left):
                    del words[i + size : i + 2 * size]
                    changed = True
                    break
            if changed:
                break
    return " ".join(words)


def entity_focus_evidence(chunks: list[dict], entity: str | None) -> list[dict]:
    """Keep only sentences whose resolved subject is the asked person (page-preserving)."""
    if not entity or entity not in RULER_KEYS or not chunks:
        return []
    title = _titles().get(entity) or entity
    focus_names = sorted({alias.lower() for alias in _aliases(entity)} | {title.lower()}, key=len, reverse=True)
    possessive = re.compile(
        r"(?<![a-z])(?:" + "|".join(re.escape(n) for n in focus_names) + r")(?:'s|\u2019s)", re.I
    )
    ordered = sorted(
        enumerate(chunks),
        key=lambda pair: ((_page(pair[1]) or 9999), str(pair[1].get("chunk_id") or ""), pair[0]),
    )
    out: list[dict] = []
    seen: set[str] = set()
    current: str | None = None
    last_page: int | None = None
    prev_sentence: tuple[str, bool] | None = None  # (pronoun-resolved text, kept?)
    for _idx, item in ordered:
        page = _page(item)
        if last_page is None or page is None or page - last_page > 1:
            current = None
            prev_sentence = None
        last_page = page
        kept: list[str] = []
        chunk_prev: tuple[str, bool] | None = None
        # Chunk overlap copies a previous person's sentence into the next section
        # ("Thus he ... Baji Rao I : ... Thus he ..."). The second copy must not
        # be reattached to the later person.
        chunk_seen: set[str] = set()
        clean = _collapse_repeats(FOCUS_NOISE_RE.sub(" ", item.get("text") or ""))
        clean = FOCUS_SMASH_RE.sub(lambda m: m.group(1) + ". ", clean)
        # Inserted box/caption title: "...Mughal Babarnama - (Tuzuk-e-Babari) Babar wrote..." -> drop the title fragment
        clean = re.sub(r"[^.!?]*\([^()]{0,60}\)\s+(?=[A-Z][a-z]+\s+[a-z])", " ", clean)
        for heading, body in _focus_segments(clean):
            if heading:
                # "Akbar's Hindu policy :" -> Akbar; "Din-e-Ilahi :" -> the term (not a person)
                people = [key for (_a, _b, key) in _person_spans(heading)]
                current = people[0] if people else heading_entity_key(heading + " :")
            for sentence in FOCUS_SENT_SPLIT.split(body):
                sentence = repair_leading_stub(" ".join(sentence.split()))
                if len(sentence.split()) < 3 or FOCUS_DANGLING_RE.search(sentence):
                    continue
                if re.match(
                    r"^(?:write an essay|answer the following|fill in the blanks|match the following|project work)\b",
                    sentence,
                    re.I,
                ):
                    prev_sentence = (sentence, False)
                    chunk_prev = (sentence, False)
                    continue
                if (
                    _looks_corrupt_sentence(sentence)
                    or (entity and _is_posthumous_bleed(sentence, entity))
                    or (entity and entity in epithet_only_rulers(sentence))
                ):
                    # A skipped sentence still breaks "this/he" so the next clause
                    # cannot inherit the person from before the skip.
                    prev_sentence = (sentence, False)
                    chunk_prev = (sentence, False)
                    continue
                raw_norm = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
                if raw_norm in chunk_seen or raw_norm in set(item.get("pre_heading_norms") or ()):
                    continue
                chunk_seen.add(raw_norm)
                before = current
                subject, how, pron = _resolve_subject(sentence, current)
                keep = False
                if subject == entity:
                    keep = True
                elif before == entity and subject in (None, "OTHER"):
                    # "Aurangzeb's successor ... him" is another ruler's sentence.
                    # A carried "him" must not pull that sentence onto the asked person.
                    keep = how != "possessive" and bool(
                        re.search(r"\b(?:his|him)\b", sentence, re.I)
                        or possessive.search(sentence)
                        or re.match(r"^(?:these|they|this)\b", sentence, re.I)
                    )
                elif before == entity and subject in RULER_KEYS:
                    keep = bool(re.search(r"\b(?:was|is)\s+(?:his|her)\b", sentence, re.I))
                elif subject in ("OTHER", None) and possessive.search(sentence):
                    keep = True
                if FOCUS_PURPOSE_RE.match(sentence) and how.startswith("pronoun"):
                    # "To achieve this, he ..." belongs to the previous sentence
                    # in this same passage. A chunk boundary must not lend it
                    # the asked person's subject from an earlier passage.
                    if chunk_prev is None or not chunk_prev[1]:
                        keep = False
                if subject in RULER_KEYS:
                    current = subject
                elif subject == "OTHER" and not keep:
                    current = None
                resolved_text = sentence
                if subject in RULER_KEYS and pron >= 0 and how.startswith("pronoun"):
                    name = _titles().get(subject) or subject
                    resolved_text = sentence[:pron] + name + sentence[pron + 2 :]
                    resolved_text = resolved_text[0].upper() + resolved_text[1:]
                previous = prev_sentence
                prev_sentence = (resolved_text, keep)
                chunk_prev = (resolved_text, keep)
                if not keep:
                    continue
                if FOCUS_ANAPHOR_RE.match(sentence):
                    if previous and not previous[1]:
                        # keep the dropped antecedent as context so "this" is not re-attached to the wrong fact
                        ctx = previous[0]
                        ctx_norm = re.sub(r"[^a-z0-9]+", " ", ctx.lower()).strip()
                        if ctx_norm not in seen:
                            seen.add(ctx_norm)
                            kept.append(ctx)
                    elif not previous:
                        sentence = FOCUS_ANAPHOR_RE.sub("", sentence)
                        sentence = sentence[0].upper() + sentence[1:]
                if subject == entity and pron >= 0 and how.startswith("pronoun"):
                    sentence = sentence[:pron] + title + sentence[pron + 2 :]
                    sentence = sentence[0].upper() + sentence[1:]
                elif subject != entity and re.match(r"^His\b", sentence):
                    # "His father, X, was ..." -> "<Focus>'s father, X, was ..." (no subject confusion)
                    sentence = title + "'s" + sentence[3:]
                norm = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
                if norm in seen:
                    continue
                seen.add(norm)
                kept.append(sentence)
        if kept:
            out.append({**item, "text": " ".join(kept), "focus_filtered": True})
    return out


_ACHIEVEMENT_Q_RE = re.compile(r"\b(?:achievements?|accomplishments?)\b", re.I)
_ACCOMPLISH_RE = re.compile(
    r"\b(?:conquer\w*|establish\w*|built|build(?:s|ing)?|organi[sz]\w*|appoint\w*|"
    r"abolish\w*|expand\w*|gain(?:ed|s)?|collect(?:ed|ion)?|coronation|crowned|"
    r"administrat\w*|divid\w*|introduc\w*|defeat\w*|found(?:ed|er|ing)\b|"
    r"construct\w*|train\w*|permit\w*|encourag\w*|re-established|ruled|"
    r"ascend\w*|wrote|translat\w*|brought|renam\w*)\b",
    re.I,
)


def achievement_answer(question: str, chunks: list[dict], entity: str | None) -> str | None:
    """Textbook sentences in which the asked person is the one who accomplished something.

    A later epithet ("called Shivaji II"), a summons by someone else, and what
    happened after the person died are not that person's achievements.
    """
    if not question or not entity or not _ACHIEVEMENT_Q_RE.search(question):
        return None
    if entity not in RULER_KEYS or not chunks:
        return None
    title = _titles().get(entity) or entity
    kept: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    focused = entity_focus_evidence(chunks, entity)
    for item in focused or chunks:
        page = _page(item)
        blob = " ".join((item.get("text") or "").split())
        for sentence in FOCUS_SENT_SPLIT.split(blob):
            sentence = " ".join(sentence.split()).strip()
            if len(sentence.split()) < 6:
                continue
            if _looks_corrupt_sentence(sentence) or _is_posthumous_bleed(sentence, entity):
                continue
            if entity in epithet_only_rulers(sentence):
                continue
            score, _why = entity_subject_score(sentence, entity)
            if score < 3:
                continue
            subject, _how, _off = _resolve_subject(sentence, None)
            if subject in RULER_KEYS and subject != entity:
                continue
            if not _ACCOMPLISH_RE.search(sentence):
                continue
            norm = re.sub(r"[^a-z0-9]+", "", sentence.lower())[:160]
            if not norm or norm in seen:
                continue
            seen.add(norm)
            kept.append((sentence, page))
    if not kept:
        return None
    pages = sorted({page for _sent, page in kept if page is not None})
    body = " ".join(sentence for sentence, _page_no in kept)
    if len(pages) == 1:
        label = f" [Page {pages[0]}]"
    elif pages:
        label = " [Pages " + ", ".join(str(page) for page in pages) + "]"
    else:
        label = ""
    return f"{title}\n\n{body}{label}"


_PLACE_Q_RE = re.compile(r"\bplaces?\b", re.I)
_PLACE_RE = re.compile(
    r"\b(?:conquer\w*|renam\w*|centre of operations|center of operations|"
    r"built a new fort|built\s+\w+\s+fort)\b",
    re.I,
)


def place_answer(question: str, chunks: list[dict], entity: str | None) -> str | None:
    """Sentences that name where the asked person expanded, conquered, or centred activity."""
    if not question or not entity or not _PLACE_Q_RE.search(question):
        return None
    if entity not in RULER_KEYS or not chunks:
        return None
    title = _titles().get(entity) or entity
    kept: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    focused = entity_focus_evidence(chunks, entity)
    for item in focused or chunks:
        page = _page(item)
        blob = " ".join((item.get("text") or "").split())
        for sentence in FOCUS_SENT_SPLIT.split(blob):
            sentence = " ".join(sentence.split()).strip()
            if len(sentence.split()) < 6:
                continue
            if _looks_corrupt_sentence(sentence) or _is_posthumous_bleed(sentence, entity):
                continue
            if entity in epithet_only_rulers(sentence):
                continue
            score, _why = entity_subject_score(sentence, entity)
            if score < 3:
                continue
            subject, _how, _off = _resolve_subject(sentence, None)
            if subject in RULER_KEYS and subject != entity:
                continue
            if not _PLACE_RE.search(sentence):
                continue
            norm = re.sub(r"[^a-z0-9]+", "", sentence.lower())[:160]
            if not norm or norm in seen:
                continue
            seen.add(norm)
            kept.append((sentence, page))
    if not kept:
        return None
    pages = sorted({page for _sent, page in kept if page is not None})
    body = " ".join(sentence for sentence, _page_no in kept)
    if len(pages) == 1:
        label = f" [Page {pages[0]}]"
    elif pages:
        label = " [Pages " + ", ".join(str(page) for page in pages) + "]"
    else:
        label = ""
    return f"{title}\n\n{body}{label}"


_CHRONOLOGY_Q_RE = re.compile(r"\bchronolog\w*\b", re.I)
_ADMIN_ONLY_RE = re.compile(
    r"\b(?:ryotwari|jahagir|ashapradhan|ministers?|judicial|panchayat|"
    r"revenue collection|administrative system|divided his kingdom)\b",
    re.I,
)


def chronology_answer(question: str, chunks: list[dict], entity: str | None) -> str | None:
    """Life events in textbook order. The model must not reshuffle them."""
    if not question or not entity or not _CHRONOLOGY_Q_RE.search(question):
        return None
    if entity not in RULER_KEYS or not chunks:
        return None
    title = _titles().get(entity) or entity
    kept: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    focused = entity_focus_evidence(chunks, entity)
    for item in focused or chunks:
        page = _page(item)
        blob = " ".join((item.get("text") or "").split())
        for sentence in FOCUS_SENT_SPLIT.split(blob):
            sentence = " ".join(sentence.split()).strip()
            sentence = re.sub(
                r"^The relationship between(?:\s+[A-Za-z]+){1,8}\s+(?=[A-Z])",
                "",
                sentence,
            ).strip()
            if len(sentence.split()) < 6:
                continue
            if _looks_corrupt_sentence(sentence) or _is_posthumous_bleed(sentence, entity):
                continue
            if entity in epithet_only_rulers(sentence) or _ADMIN_ONLY_RE.search(sentence):
                continue
            score, _why = entity_subject_score(sentence, entity)
            if score < 3:
                continue
            subject, _how, _off = _resolve_subject(sentence, None)
            if subject in RULER_KEYS and subject != entity:
                continue
            norm = re.sub(r"[^a-z0-9]+", "", sentence.lower())[:160]
            if not norm or norm in seen:
                continue
            seen.add(norm)
            kept.append((sentence, page))
    if len(kept) < 2:
        return None
    pages = sorted({page for _sent, page in kept if page is not None})
    body = " ".join(sentence for sentence, _page_no in kept)
    if len(pages) == 1:
        label = f" [Page {pages[0]}]"
    elif pages:
        label = " [Pages " + ", ".join(str(page) for page in pages) + "]"
    else:
        label = ""
    return f"{title}\n\n{body}{label}"


def drop_preheading_claims(answer: str, evidence: list[dict], entity: str | None) -> str:
    """Drop a claim that names the focus person when the textbook sentence is an earlier person's pronoun.

    Chunk boundaries copy "Thus he ..." from the previous section into the next heading.
    Rewriting that "he" as the later person states the wrong subject's action.
    """
    if not answer or not evidence or not entity or entity not in RULER_KEYS:
        return answer
    title_tokens = set(re.findall(r"[a-z0-9]+", (_titles().get(entity) or "").lower()))
    stop = {
        "thus", "hence", "this", "that", "with", "from", "were", "was", "his", "her",
        "the", "and", "only", "also", "into", "after", "before", "when", "then",
    }

    def tokens(text: str) -> set[str]:
        return {
            word
            for word in re.findall(r"[a-z]{4,}", (text or "").lower())
            if word not in stop and word not in title_tokens
        }

    def heading_norm_pos(blob: str) -> int | None:
        for match in FOCUS_HEADING_RE.finditer(blob):
            people = [key for (_a, _b, key) in _person_spans(match.group(1))]
            key = people[0] if people else heading_entity_key(match.group(1) + " :")
            if key == entity:
                return len(re.sub(r"[^a-z0-9]+", " ", blob[: match.start()].lower()))
        return None

    def claim_before_heading(chunk_text: str, answer_sentence: str) -> bool:
        """True when this claim's content words first appear before the focus person's heading."""
        blob = " ".join((chunk_text or "").split())
        head = heading_norm_pos(blob)
        if head is None:
            return False
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", answer_sentence.lower())
            if len(word) >= 4 and word not in stop and word not in title_tokens
        ]
        if len(words) < 2:
            return False
        norm = re.sub(r"[^a-z0-9]+", " ", blob.lower())
        start = 0
        while True:
            pos = norm.find(words[0], start)
            if pos < 0 or pos >= head:
                return False
            window = norm[pos : pos + 90]
            if all(word in window for word in words[:4]):
                return True
            start = pos + 1

    lines_out: list[str] = []
    for line in (answer or "").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "**", "Source", "[Page")):
            lines_out.append(line)
            continue
        kept: list[str] = []
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", stripped):
            sent = sent.strip()
            if not sent:
                continue
            subject, _how, _off = _resolve_subject(re.sub(r"\s*\[Pages?[^\]]*\]", "", sent).strip(), None)
            pred = tokens(sent)
            if subject != entity or len(pred) < 3:
                kept.append(sent)
                continue
            matched = False
            owned = False
            for item in evidence:
                text = item.get("text") or ""
                for ev in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
                    if len(pred & tokens(ev)) < max(3, int(0.6 * len(pred))):
                        continue
                    matched = True
                    if claim_before_heading(text, sent):
                        continue
                    ev_subject, ev_how, _ev_off = _resolve_subject(ev, entity)
                    if ev_subject == entity or not str(ev_how).startswith("pronoun"):
                        owned = True
            if matched and not owned:
                continue
            kept.append(sent)
        if kept:
            lines_out.append(" ".join(kept))
    return "\n".join(lines_out).strip()

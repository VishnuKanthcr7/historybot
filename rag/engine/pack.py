"""Build a topic-bounded, ordered evidence pack from the approved textbook."""

from __future__ import annotations

import re

from dataclasses import dataclass, field

from rag.engine.classify import TOPIC_ALIASES, extract_topics
from rag.engine.evidence import looks_like_exercise_chunk, overlap_count, select_evidence
from rag.engine.topic_map import (
    AHOM_FAMILY,
    MARATHA_FAMILY,
    MUGHAL_FAMILY,
    RULER_KEYS,
    chunk_has_facet,
    chunks_for_topics,
    dynasty_keys,
    load_primary_chunks,
    looks_like_map_chunk,
)
from rag.vectorstore.retrieve import retrieve_primary, retrieve_same_pages


@dataclass
class EvidencePack:
    chunks: list[dict] = field(default_factory=list)
    question_type: str = "DIRECT"
    topics: list[str] = field(default_factory=list)
    entity: str | None = None
    facet: str | None = None
    pages: list[int] = field(default_factory=list)
    retrieved_pages: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    raw_hits: list[dict] = field(default_factory=list)
    clarify: str | None = None

    def as_public(self) -> dict:
        return {
            "question_type": self.question_type,
            "topics": self.topics,
            "entity": self.entity,
            "facet": self.facet,
            "pages": self.pages,
            "retrieved_pages": self.retrieved_pages,
            "reasons": self.reasons,
            "chunk_count": len(self.chunks),
            "clarify": self.clarify,
        }


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def detect_facet(question: str) -> str | None:
    lowered = (question or "").lower()
    if "prime minister" in lowered:
        lowered = re.sub(r"\bcurrent prime minister\b|\bprime minister\b", " ", lowered)
    if any(word in lowered for word in ("administration", "administrative")):
        return "administration"
    if re.search(r"\bministers?\b", lowered) and "prime minister" not in (question or "").lower():
        return "administration"
    if any(word in lowered for word in ("religious", "religion", "din-e", "din e ilahi", "jizya")):
        return "religious"
    if any(word in lowered for word in ("taj", "architecture", "building")):
        return "architecture"
    if any(word in lowered for word in ("guerrilla", "guerilla", "warfare", "battle")):
        return "warfare"
    return None


def detect_entity(topic_keys: set[str]) -> str | None:
    for key in RULER_KEYS:
        if key in topic_keys:
            return key
    return None


def ruler_counts(text: str) -> dict[str, int]:
    lowered = (text or "").lower()
    counts = {}
    for key in RULER_KEYS:
        total = 0
        for alias in TOPIC_ALIASES.get(key, ()):
            if alias.isascii():
                total += lowered.count(alias)
        if total:
            counts[key] = total
    return counts


def dominant_ruler(text: str) -> str | None:
    counts = ruler_counts(text)
    if not counts:
        return None
    best = max(counts.values())
    leaders = [key for key, value in counts.items() if value == best]
    if len(leaders) == 1:
        return leaders[0]
    return None


def filter_entity_chunks(chunks: list[dict], entity: str | None, facet: str | None) -> list[dict]:
    if not entity:
        return chunks
    kept = []
    for item in chunks:
        text = item.get("text") or ""
        lowered = text.lower()
        aliases = TOPIC_ALIASES.get(entity, (entity,))
        mentions_entity = any(alias in lowered for alias in aliases if alias.isascii())
        dominant = dominant_ruler(text)
        if facet == "administration":
            if looks_like_toc(text) or looks_like_map_chunk(text):
                continue
            if (_page(item) or 0) <= 1 and "ahom" in lowered:
                continue
            counts = ruler_counts(text)
            rival = any(
                key != entity and counts.get(key, 0) >= counts.get(entity, 0)
                for key in counts
            )
            admin_core = any(
                term in lowered
                for term in (
                    "ashtapradhan",
                    "ashapradhan",
                    "ryotwari",
                    "chauth",
                    "sardeshmukhi",
                    "mansab",
                    "vakil",
                    "diwan",
                    "swarajya",
                    "jahagir",
                    "administrative system",
                    "administration : shivaji",
                    "the mughal administration",
                    "mughal administration",
                )
            )
            if mentions_entity and admin_core and not rival:
                kept.append({**item, "relevance_reason": "entity-admin-core"})
                continue
            if mentions_entity and chunk_has_facet(text, "administration") and dominant in {None, entity} and not rival:
                kept.append({**item, "relevance_reason": "entity-admin"})
                continue
            if dominant == entity and chunk_has_facet(text, "administration") and not rival:
                kept.append({**item, "relevance_reason": "entity-dominant-admin"})
                continue
            continue
        if mentions_entity and dominant in {None, entity}:
            kept.append({**item, "relevance_reason": "entity-primary"})
            continue
        if mentions_entity and dominant and dominant != entity:
            # Contextual mention (e.g. Shivaji vs Aurangzeb) — keep only if not another ruler's admin block.
            if facet is None and not chunk_has_facet(text, "administration"):
                kept.append({**item, "relevance_reason": "entity-context"})
            continue
        if dominant == entity:
            kept.append({**item, "relevance_reason": "entity-dominant"})
    return kept


def _merge(existing: list[dict], extra: list[dict]) -> list[dict]:
    by_id = {item.get("chunk_id"): item for item in existing if item.get("chunk_id")}
    for item in extra:
        chunk_id = item.get("chunk_id")
        if chunk_id and chunk_id not in by_id:
            by_id[chunk_id] = item
    return list(by_id.values())


def _order(chunks: list[dict]) -> list[dict]:
    return sorted(
        chunks,
        key=lambda item: (_page(item) or 99, item.get("distance") if item.get("distance") is not None else 9),
    )


def looks_like_toc(text: str) -> bool:
    lowered = (text or "").lower()
    return lowered.startswith("chapter") or "we will learn about" in lowered[:400]


NAMED_RULERS = {
    "babar",
    "humayun",
    "akbar",
    "jahangir",
    "shahjahan",
    "aurangzeb",
    "sher",
    "shivaji",
    "sambhaji",
    "bajirao",
    "balaji",
    "madhav",
}

AHOM_HINTS = ("ahom", "charaideo", "sukaphaa", "lachit", "saraighat", "jayadhwaj")


def ahom_primary_chunk(item: dict) -> bool:
    """True when the passage is framed around the Ahoms, even if a Mughal name appears once."""
    text = item.get("text") or ""
    lowered = text.lower()
    topics = set(item.get("topics") or extract_topics(text))
    ahom_score = sum(lowered.count(hint) for hint in AHOM_HINTS)
    if ahom_score == 0 and "ahom" not in topics:
        return False
    named_total = sum(ruler_counts(text).values())
    if ahom_score >= 2 and ahom_score >= named_total:
        return True
    if "ahom" in topics and named_total == 0 and not (topics & NAMED_RULERS):
        return True
    return False


def chunk_group_key(item: dict) -> str:
    """Assign a chunk from its own text, not from neighbouring page material."""
    if ahom_primary_chunk(item):
        return "ahom"
    text = item.get("text") or ""
    lowered = text.lower()
    counts = ruler_counts(text)
    aur = counts.get("aurangzeb", 0)
    head = " ".join(text.split())[:100].lower()
    others = max((value for key, value in counts.items() if key != "aurangzeb"), default=0)
    if head.startswith("aurangzeb") or "\naurangzeb" in lowered[:240]:
        return "aurangzeb"
    if aur >= 2 and aur > others:
        if counts.get("shivaji", 0) > aur:
            return "shivaji"
        return "aurangzeb"
    if "rajaram" in lowered or ("maratha" in lowered and counts.get("sambhaji", 0)):
        if not head.startswith("aurangzeb") and counts.get("shahjahan", 0) == 0:
            return "maratha"
    if counts:
        return max(counts, key=counts.get)
    topics = extract_topics(text)
    for key in (
        "babar",
        "humayun",
        "akbar",
        "jahangir",
        "shahjahan",
        "aurangzeb",
        "sher",
        "shivaji",
        "taj",
        "din",
        "guerilla",
        "mansab",
        "peshwa",
        "maratha",
        "mughal",
        "ahom",
    ):
        if key in topics:
            return key
    return "general"


def fill_missing_rulers(selected: list[dict], mapped: list[dict], keys: tuple[str, ...], max_keep: int = 12) -> list[dict]:
    present = {chunk_group_key(item) for item in selected}
    missing = [key for key in keys if key not in present]
    extras = []
    used = {item.get("chunk_id") for item in selected}
    for item in mapped:
        if not missing:
            break
        if item.get("chunk_id") in used or ahom_primary_chunk(item):
            continue
        key = chunk_group_key(item)
        if key in missing:
            extras.append(item)
            used.add(item.get("chunk_id"))
            missing = [item_key for item_key in missing if item_key != key]
    if not extras:
        return selected
    core = [item for item in selected if chunk_group_key(item) not in {"ahom"}]
    overflow = len(core) + len(extras) - max_keep
    if overflow > 0:
        drop_rank = {"shivaji": 0, "madhav": 0, "sambhaji": 0, "bajirao": 1, "general": 1, "mughal": 2}
        ranked = sorted(
            enumerate(core),
            key=lambda pair: (drop_rank.get(chunk_group_key(pair[1]), 5), pair[0]),
        )
        drop_ids = {core[idx].get("chunk_id") for idx, _item in ranked[:overflow]}
        core = [item for item in core if item.get("chunk_id") not in drop_ids]
    return _order(core + extras)


def primarily_other_dynasty(item: dict, family: set[str]) -> bool:
    tops = set(item.get("topics") or [])
    page = _page(item) or 0
    if family == MUGHAL_FAMILY:
        if ahom_primary_chunk(item):
            return True
        mar = len(tops & MARATHA_FAMILY)
        mug = len(tops & (MUGHAL_FAMILY - {"aurangzeb"}))
        if mar > mug and page >= 11:
            return True
    if family == MARATHA_FAMILY:
        if ahom_primary_chunk(item):
            return True
        if page <= 10 and "shivaji" not in tops and "maratha" not in tops:
            return True
        if page == 9 and "shivaji" in tops and chunk_has_facet(item.get("text") or "", "administration") is False:
            if dominant_ruler(item.get("text") or "") in {"aurangzeb", None} and "imprisoned" in (item.get("text") or "").lower():
                return True
    return False


def diversify_by_page(chunks: list[dict], max_keep: int) -> list[dict]:
    buckets: dict[int, list[dict]] = {}
    for item in chunks:
        buckets.setdefault(_page(item) or 0, []).append(item)
    pages = sorted(buckets)
    out: list[dict] = []
    while len(out) < max_keep and any(buckets[page] for page in pages):
        for page in pages:
            if buckets[page]:
                out.append(buckets[page].pop(0))
            if len(out) >= max_keep:
                break
    return _order(out)


def _pages(chunks: list[dict]) -> list[int]:
    return sorted({p for item in chunks if (p := _page(item)) is not None})


def add_same_page_continuations(selected: list[dict], entity: str | None, facet: str | None) -> list[dict]:
    pages = {p for item in selected if (p := _page(item)) is not None}
    extra = []
    for item in load_primary_chunks():
        if _page(item) not in pages:
            continue
        if looks_like_exercise_chunk(item) or looks_like_map_chunk(item.get("text") or ""):
            continue
        extra.append(item)
    merged = _merge(selected, extra)
    if entity:
        merged = filter_entity_chunks(merged, entity, facet)
    return merged


def build_evidence_pack(
    question: str,
    retrieval_query: str,
    question_type: str,
    raw_hits: list[dict] | None = None,
    history: list[dict] | None = None,
) -> EvidencePack:
    del history
    topics = extract_topics(f"{question} {retrieval_query}")
    entity = detect_entity(topics)
    facet = detect_facet(f"{question} {retrieval_query}")
    hits = list(raw_hits or retrieve_primary(retrieval_query, top_k=12, language="en"))
    pack = EvidencePack(
        question_type=question_type,
        topics=sorted(topics),
        entity=entity,
        facet=facet,
        raw_hits=hits,
        retrieved_pages=_pages(hits),
    )

    if question_type == "FOLLOW_UP" and facet == "administration" and entity:
        question_type = "EXPLANATION"
        pack.question_type = "FOLLOW_UP"
        pack.reasons.append("followup-admin-as-explanation")

    if question_type == "BROAD_TOPIC" and topics:
        family = dynasty_keys(topics)
        if entity and entity in {"shivaji", "akbar", "babar", "bajirao"} and "mughal" not in topics and "maratha" not in topics:
            mapped = chunks_for_topics({entity} | ({"guerilla"} if entity == "shivaji" else set()))
            mapped = filter_entity_chunks(mapped, entity, None)
            pack.reasons.append("broad-person-topic-map")
        else:
            mapped = chunks_for_topics(family)
            if family == MUGHAL_FAMILY:
                mapped = [
                    item
                    for item in mapped
                    if set(item.get("topics") or []) & MUGHAL_FAMILY
                    and not primarily_other_dynasty(item, MUGHAL_FAMILY)
                ]
                pack.reasons.append("broad-mughal-topic-map")
            else:
                mapped = [item for item in mapped if not primarily_other_dynasty(item, family)]
                pack.reasons.append("broad-topic-map")
        mapped = [item for item in mapped if not looks_like_map_chunk(item.get("text") or "") and not looks_like_toc(item.get("text") or "")]
        seed = select_evidence(question, retrieval_query, hits, max_keep=6)
        combined = [
            item
            for item in _merge(mapped, seed)
            if not looks_like_toc(item.get("text") or "")
            and not looks_like_map_chunk(item.get("text") or "")
            and not primarily_other_dynasty(item, family)
            and not ahom_primary_chunk(item)
            and ((_page(item) or 99) > 1 or family == AHOM_FAMILY)
        ]
        pack.chunks = diversify_by_page(combined, 12)
        pack.chunks = [item for item in pack.chunks if not ahom_primary_chunk(item)]
        if family == MUGHAL_FAMILY:
            pack.chunks = fill_missing_rulers(
                pack.chunks,
                mapped,
                ("babar", "sher", "akbar", "shahjahan", "aurangzeb"),
                12,
            )
            pack.reasons.append("ensure-mughal-rulers")
        pack.pages = _pages(pack.chunks)
        pack.reasons.append(f"kept:{len(pack.chunks)}")
        return pack

    if question_type == "EXPLANATION":
        seed = select_evidence(question, retrieval_query, hits, max_keep=8)
        same = retrieve_same_pages(retrieval_query, [_page(item) for item in seed if _page(item) is not None])
        same = [item for item in same if item.get("source_type") == "primary_textbook"]
        mapped = []
        if entity:
            mapped = chunks_for_topics({entity})
            if facet:
                mapped = [
                    item
                    for item in mapped
                    if chunk_has_facet(item.get("text") or "", facet)
                    or (entity in (item.get("topics") or []) and facet != "administration")
                ]
        elif topics & {"maratha"}:
            mapped = [
                item
                for item in chunks_for_topics(dynasty_keys({"maratha"}))
                if not facet or chunk_has_facet(item.get("text") or "", facet)
            ]
        elif topics & {"mughal"}:
            mapped = [
                item
                for item in chunks_for_topics(dynasty_keys({"mughal"}))
                if not facet or chunk_has_facet(item.get("text") or "", facet)
            ]
            if "sher" not in topics:
                mapped = [
                    item
                    for item in mapped
                    if dominant_ruler(item.get("text") or "") != "sher"
                    and "sher shah" not in (item.get("text") or "").lower()[:120]
                ]
        if entity:
            combined = _merge(seed, mapped)
            if facet == "administration":
                combined = add_same_page_continuations(combined, entity, facet)
            combined = filter_entity_chunks(combined, entity, facet)
            combined = [
                item
                for item in combined
                if chunk_group_key(item) == entity or dominant_ruler(item.get("text") or "") == entity
            ]
        else:
            combined = mapped or seed
            combined = [item for item in combined if not primarily_other_dynasty(item, dynasty_keys(topics or {"mughal"}))]
        combined = [
            item
            for item in combined
            if not looks_like_map_chunk(item.get("text") or "")
            and not looks_like_toc(item.get("text") or "")
            and not ahom_primary_chunk(item)
            and ((_page(item) or 99) > 1 or "ahom" in (item.get("topics") or []))
        ]
        pack.chunks = diversify_by_page(combined, 12)
        pack.pages = _pages(pack.chunks)
        pack.reasons.append("explanation-section")
        return pack

    # DIRECT and FOLLOW_UP (follow-up already rewritten into retrieval_query)
    seed_keep = 5 if question_type == "FOLLOW_UP" else 4
    seed = select_evidence(question, retrieval_query, hits, max_keep=seed_keep)
    same = retrieve_same_pages(retrieval_query, [_page(item) for item in seed if _page(item) is not None])
    same = [item for item in same if item.get("source_type") == "primary_textbook"]
    mapped = []
    if entity:
        mapped = [
            item
            for item in chunks_for_topics({entity})
            if not ahom_primary_chunk(item) and not looks_like_exercise_chunk(item)
        ]
        mapped = filter_entity_chunks(mapped, entity, facet)
        if not seed:
            seed = mapped[:4]
            pack.reasons.append("entity-topic-map-seed")
    if entity:
        combined = _merge(_merge(seed, mapped), same if question_type == "FOLLOW_UP" else [])
        combined = filter_entity_chunks(combined, entity, facet)
    else:
        combined = add_same_page_continuations(_merge(seed, same), entity, facet)
    combined = [item for item in combined if not looks_like_exercise_chunk(item)]
    if question_type != "FOLLOW_UP":
        combined = [item for item in combined if not looks_like_map_chunk(item.get("text") or "")]
        combined = [item for item in combined if not ahom_primary_chunk(item)]
        if entity:
            combined = [item for item in combined if (_page(item) or 99) > 1]
    cap = 8 if question_type == "FOLLOW_UP" else 6
    pack.chunks = _order(combined)[:cap]
    pack.pages = _pages(pack.chunks)
    pack.reasons.append("direct-or-followup")
    return pack

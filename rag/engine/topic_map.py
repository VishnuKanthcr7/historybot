"""Topic-page map derived only from indexed primary textbook chunks."""

from __future__ import annotations

from functools import lru_cache

from rag.engine.classify import TOPIC_ALIASES, extract_topics
from rag.engine.evidence import looks_like_exercise_chunk
from rag.vectorstore.chroma_store import get_existing_collection
from rag.vectorstore.config import ACTIVE_COLLECTION

MUGHAL_FAMILY = {
    "mughal",
    "babar",
    "humayun",
    "akbar",
    "jahangir",
    "shahjahan",
    "aurangzeb",
    "taj",
    "din",
    "mansab",
    "sher",
}
MARATHA_FAMILY = {
    "maratha",
    "shivaji",
    "sambhaji",
    "peshwa",
    "bajirao",
    "balaji",
    "madhav",
    "guerilla",
    "raigad",
}
AHOM_FAMILY = {"ahom"}
RULER_KEYS = (
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
)
FACET_TERMS = {
    "administration": (
        "administration",
        "administrative",
        "minister",
        "mansab",
        "mansabdari",
        "ashtapradhan",
        "ashapradhan",
        "chauth",
        "sardeshmukhi",
        "ryotwari",
        "vakil",
        "diwan",
        "subha",
        "jagir",
        "jahagir",
        "peshwa",
        "swarajya",
        "province",
    ),
    "religious": (
        "din-e-ilahi",
        "din e ilahi",
        "ibadat",
        "jizya",
        "hindu policy",
        "religious",
        "sal-i-kul",
        "peace with all",
    ),
    "architecture": ("taj", "mahal", "fort", "architecture", "mosque"),
    "warfare": ("guerrilla", "guerilla", "panipat", "battle", "fort"),
}


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hit_from_chroma(chunk_id: str, text: str, meta: dict) -> dict:
    meta = meta or {}
    return {
        "chunk_id": chunk_id,
        "text": text or "",
        "textbook_page_number": meta.get("textbook_page_number") or meta.get("printed_page_number"),
        "printed_page_number": meta.get("printed_page_number") or meta.get("textbook_page_number"),
        "pdf_page_number": meta.get("pdf_page_number"),
        "section": meta.get("section"),
        "chapter": meta.get("chapter"),
        "source_id": meta.get("source_id"),
        "source_type": meta.get("source_type") or "primary_textbook",
        "authority": meta.get("authority") or "primary",
        "language": meta.get("language") or "en",
        "document_name": meta.get("document_name"),
        "citation_label": meta.get("citation_label"),
        "distance": None,
        "topics": sorted(extract_topics(text or "")),
    }


@lru_cache(maxsize=1)
def load_primary_chunks() -> tuple[dict, ...]:
    client = get_existing_collection(ACTIVE_COLLECTION)
    data = client.get(include=["documents", "metadatas"])
    rows = []
    for chunk_id, doc, meta in zip(data.get("ids") or [], data.get("documents") or [], data.get("metadatas") or []):
        meta = meta or {}
        if meta.get("source_type") != "primary_textbook":
            continue
        rows.append(_hit_from_chroma(chunk_id, doc or "", meta))
    return tuple(rows)


def chunk_has_facet(text: str, facet: str) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in FACET_TERMS.get(facet, ()))


def looks_like_map_chunk(text: str) -> bool:
    lowered = (text or "").lower()
    return "arabian sea" in lowered and "bay of bengal" in lowered


def build_topic_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for item in load_primary_chunks():
        page = _page(item)
        for topic in item.get("topics") or []:
            entry = index.setdefault(topic, {"pages": set(), "chunk_ids": [], "sections": set()})
            if page is not None:
                entry["pages"].add(page)
            entry["chunk_ids"].append(item["chunk_id"])
            if item.get("section"):
                entry["sections"].add(str(item["section"])[:80])
    serializable = {}
    for topic, entry in index.items():
        serializable[topic] = {
            "pages": sorted(entry["pages"]),
            "chunk_ids": entry["chunk_ids"],
            "sections": sorted(entry["sections"])[:12],
        }
    return serializable


def chunks_for_topics(topic_keys: set[str], *, include_exercises: bool = False) -> list[dict]:
    wanted = set(topic_keys)
    rows = []
    for item in load_primary_chunks():
        topics = set(item.get("topics") or [])
        if not topics & wanted:
            continue
        if not include_exercises and looks_like_exercise_chunk(item):
            continue
        rows.append(item)
    rows.sort(key=lambda item: (_page(item) or 99, item.get("chunk_id") or ""))
    return rows


def dynasty_keys(topic_keys: set[str]) -> set[str]:
    keys = set(topic_keys)
    maratha_named = keys & {"maratha", "shivaji", "sambhaji", "peshwa", "bajirao", "balaji", "madhav", "guerilla", "raigad"}
    mughal_named = keys & {"mughal", "babar", "humayun", "akbar", "jahangir", "shahjahan", "aurangzeb", "taj", "din", "mansab", "sher"}
    if maratha_named and not (mughal_named - {"mughal", "aurangzeb"}):
        return MARATHA_FAMILY
    if mughal_named:
        return MUGHAL_FAMILY
    if keys & AHOM_FAMILY:
        return AHOM_FAMILY
    return keys


def public_topic_map() -> dict:
    """Student-safe summary: topic keys and printed pages only."""
    index = build_topic_index()
    return {
        topic: {"pages": entry["pages"]}
        for topic, entry in sorted(index.items())
        if topic in TOPIC_ALIASES
    }

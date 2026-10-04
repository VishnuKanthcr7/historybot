"""Coverage plans and section generation from a FINAL evidence pack only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.engine.classify import TOPIC_ALIASES, extract_topics
from rag.engine.pack import looks_like_toc, ruler_counts
from rag.engine.topic_map import MARATHA_FAMILY, MUGHAL_FAMILY, RULER_KEYS, dynasty_keys, looks_like_map_chunk
from rag.engine.validate import unsupported_named_items
from rag.llm.client import LlmError, complete
from rag.prompts.tutor import SYSTEM_PROMPT

GROUP_TITLE = {
    "babar": "Babur",
    "humayun": "Humayun",
    "akbar": "Akbar",
    "jahangir": "Jahangir",
    "shahjahan": "Shah Jahan",
    "aurangzeb": "Aurangzeb",
    "sher": "Sher Shah",
    "shivaji": "Shivaji",
    "sambhaji": "Sambhaji",
    "peshwa": "The Peshwas",
    "bajirao": "Baji Rao I",
    "balaji": "Balaji Vishwanath",
    "madhav": "Madhav Rao I",
    "taj": "Taj Mahal",
    "din": "Din-e-Ilahi",
    "guerilla": "Guerrilla warfare",
    "mansab": "Mansabdari system",
    "maratha": "The Marathas",
    "mughal": "Mughal rule",
    "administration": "Administration",
}

MERGE_INTO = {
    "taj": "shahjahan",
    "din": "akbar",
    "mansab": "akbar",
    "guerilla": "shivaji",
    "sambhaji": "shivaji",
}


@dataclass
class CoverageGroup:
    key: str
    title: str
    pages: list[int]
    chunks: list[dict] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)

    def as_public(self) -> dict:
        return {"key": self.key, "title": self.title, "pages": self.pages, "chunk_count": len(self.chunks)}


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _usable_chunk(item: dict) -> bool:
    text = item.get("text") or ""
    if looks_like_toc(text) or looks_like_map_chunk(text):
        return False
    if _spaced_ocr(text):
        return False
    return len(text.split()) >= 20


def _spaced_ocr(text: str) -> bool:
    return bool(re.search(r"(?:\b[A-Za-z]\s){8,}", text or ""))


def _group_key(item: dict) -> str:
    text = item.get("text") or ""
    counts = ruler_counts(text)
    if counts:
        return max(counts, key=counts.get)
    topics = extract_topics(text)
    for key in RULER_KEYS + ("taj", "din", "guerilla", "mansab", "peshwa", "maratha", "mughal"):
        if key in topics:
            return key
    return "general"


def build_coverage_plan(chunks: list[dict]) -> list[CoverageGroup]:
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in chunks:
        if not _usable_chunk(item):
            continue
        key = _group_key(item)
        key = MERGE_INTO.get(key, key)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(item)
    if "general" in buckets and len(buckets) > 1:
        order = [key for key in order if key != "general"]
    groups = []
    for key in order:
        items = buckets.get(key) or []
        if not items:
            continue
        aliases = list(TOPIC_ALIASES.get(key, (key,)))
        title = GROUP_TITLE.get(key) or aliases[0].title()
        pages = sorted({p for item in items if (p := _page(item)) is not None})
        groups.append(
            CoverageGroup(
                key=key,
                title=title,
                pages=pages,
                chunks=items,
                markers=[alias for alias in aliases if alias.isascii()] or [key],
            )
        )
    return groups[:8]


def filter_plan(question: str, plan: list[CoverageGroup]) -> list[CoverageGroup]:
    topics = extract_topics(question)
    family = dynasty_keys(topics)
    if family == MUGHAL_FAMILY and "shivaji" not in topics:
        return [group for group in plan if group.key not in MARATHA_FAMILY]
    if family == MARATHA_FAMILY and "akbar" not in topics:
        drop = {"babar", "humayun", "akbar", "jahangir", "shahjahan", "sher", "taj", "din", "mansab"}
        return [group for group in plan if group.key not in drop]
    return plan


def group_covered(answer: str, group: CoverageGroup) -> bool:
    low = (answer or "").lower()
    if not group.markers:
        return bool((answer or "").strip())
    return any(marker.lower() in low for marker in group.markers)


def coverage_score(answer: str, plan: list[CoverageGroup]) -> dict:
    expected = [group.key for group in plan]
    generated = [group.key for group in plan if group_covered(answer, group)]
    missing = [key for key in expected if key not in generated]
    total = len(expected) or 1
    ratio = len(generated) / total
    if ratio >= 0.8:
        grade = "GOOD"
    elif ratio >= 0.5:
        grade = "PARTIAL"
    else:
        grade = "FAIL"
    return {
        "expected": expected,
        "generated": generated,
        "missing": missing,
        "grade": grade,
        "ratio": round(ratio, 2),
    }


def readable_extract(chunks: list[dict], limit: int = 3) -> str:
    sentences = []
    seen = set()
    for item in chunks:
        text = " ".join((item.get("text") or "").split())
        if looks_like_toc(text) or looks_like_map_chunk(text) or _spaced_ocr(text):
            continue
        for sent in re.split(r"(?<=[.!?])\s+", text):
            words = sent.split()
            if len(words) < 8 or len(words) > 42:
                continue
            key = sent[:60].lower()
            if key in seen:
                continue
            seen.add(key)
            sentences.append(sent.strip())
            if len(sentences) >= limit:
                return " ".join(sentences)
    return " ".join(sentences)


def generate_section(question: str, group: CoverageGroup, strict: bool = False) -> str:
    blocks = []
    for item in group.chunks[:4]:
        page = _page(item)
        text = " ".join((item.get("text") or "").split())[:900]
        blocks.append(f"[printed_page={page}]\n{text}")
    extra = " Use only names and dates that appear in the evidence." if strict else ""
    user = (
        f"Student question: {question}\n"
        f"Write a short Class 9 section titled {group.title}. "
        f"Use ONLY the evidence below. 4 to 8 short sentences.{extra}\n"
        "Do not mention people who are not in this evidence. Do not add page numbers.\n\n"
        f"Evidence:\n{chr(10).join(blocks)}"
    )
    try:
        raw = complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0 if strict else 0.1,
            max_tokens=280,
            timeout=90,
        )
    except (LlmError, TimeoutError, OSError):
        return readable_extract(group.chunks)
    text = (raw or "").strip()
    if unsupported_named_items(text, group.chunks):
        try:
            raw = complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user + "\nSTRICT: omit any name not in the evidence."},
                ],
                temperature=0.0,
                max_tokens=240,
                timeout=90,
            )
            text = (raw or "").strip()
        except (LlmError, TimeoutError, OSError):
            text = ""
        if not text or unsupported_named_items(text, group.chunks):
            return readable_extract(group.chunks)
    return text


def combine_sections(question: str, sections: list[tuple[CoverageGroup, str]]) -> str:
    parts = [f"Here is what the Class 9 textbook says about this topic, in simple English."]
    for group, body in sections:
        body = (body or "").strip()
        if not body:
            continue
        parts.append(f"## {group.title}\n\n{body}")
    if len(parts) == 1:
        return "The provided textbook does not give enough information to answer this fully."
    return "\n\n".join(parts)


def generate_from_plan(question: str, chunks: list[dict], question_type: str) -> dict:
    plan = filter_plan(question, build_coverage_plan(chunks))
    if question_type == "EXPLANATION" and len(plan) <= 1:
        plan = plan or [
            CoverageGroup(
                key="topic",
                title="Explanation",
                pages=sorted({p for item in chunks if (p := _page(item)) is not None}),
                chunks=chunks,
                markers=[],
            )
        ]
    sections: list[tuple[CoverageGroup, str]] = []
    used_extractive = False
    for group in plan:
        body = generate_section(question, group)
        if body == readable_extract(group.chunks):
            used_extractive = True
        sections.append((group, body))
    answer = combine_sections(question, sections)
    score = coverage_score(answer, plan)
    regenerated = False
    if score["missing"] and question_type in {"BROAD_TOPIC", "EXPLANATION"}:
        regenerated = True
        by_key = {group.key: group for group in plan}
        rebuilt = []
        for group, body in sections:
            if group.key in score["missing"]:
                extra = generate_section(question, group, strict=True)
                if not group_covered(extra, group):
                    extra = readable_extract(group.chunks) or extra
                    used_extractive = True
                rebuilt.append((group, extra))
            else:
                rebuilt.append((group, body))
        sections = rebuilt
        answer = combine_sections(question, sections)
        score = coverage_score(answer, plan)
    if score["grade"] == "FAIL":
        answer = combine_sections(
            question,
            [(group, readable_extract(group.chunks) or body) for group, body in sections],
        )
        used_extractive = True
        score = coverage_score(answer, plan)
        score["grade"] = score["grade"] if score["generated"] else "FAIL"
    return {
        "answer": answer,
        "plan": [group.as_public() for group in plan],
        "coverage": score,
        "regenerated": regenerated,
        "fallback_used": used_extractive and score["grade"] != "GOOD",
        "section_pages": {group.key: group.pages for group, _body in sections if group_covered(answer, group)},
    }

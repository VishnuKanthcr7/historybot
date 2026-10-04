"""Grounded structured E-content from the approved Class 9 textbook only."""

from __future__ import annotations

import json
import re

from rag.engine.answer import _public_hits, _sources, _unavailable
from rag.engine.citations import supporting_evidence
from rag.engine.classify import classify_casual
from rag.engine.evidence import evidence_is_sufficient, evidence_matches_topic
from rag.engine.normalize import looks_kannada, looks_like_injection, normalize_question
from rag.engine.pack import build_evidence_pack
from rag.engine.validate import unsupported_named_items
from rag.llm.client import LlmError, complete
from rag.prompts.econtent import ECONTENT_SYSTEM, SECTION_SPECS
from rag.prompts.tutor import KANNADA_UNAVAILABLE, refusal_text
from rag.vectorstore.retrieve import retrieve_primary

ALLOWED_KEYS = (
    "title",
    "introduction",
    "learning_objectives",
    "class9_textbook",
    "easy_english",
    "historical_context",
    "detailed_explanation",
    "important_people",
    "important_terms",
    "timeline",
    "main_events",
    "important_places",
    "key_points",
    "exam_questions",
    "mcqs",
    "revision",
)

ECONTENT_TOP_K = 16
SECTION_TIMEOUT = 75


def generate_econtent(topic: str, language: str = "en") -> dict:
    language = "kn" if language == "kn" else "en"
    topic = normalize_question(topic)
    if language == "kn" or looks_kannada(topic):
        refused = _refused("kn", topic, [], [])
        refused["answer"] = KANNADA_UNAVAILABLE
        refused["validation_reason"] = "kannada_corpus_unavailable"
        return refused
    if classify_casual(topic) or looks_like_injection(topic):
        return _refused(language, topic, [], [])
    retrieval_query = topic
    primary_hits = retrieve_primary(retrieval_query, top_k=ECONTENT_TOP_K, language="en")
    pack = build_evidence_pack(topic, retrieval_query, "BROAD_TOPIC", raw_hits=primary_hits)
    primary_selected = pack.chunks
    if not evidence_is_sufficient(primary_selected) or not evidence_matches_topic(
        topic, retrieval_query, primary_selected
    ):
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    content: dict = {}
    ordered = list(primary_selected)
    for spec in SECTION_SPECS:
        if spec.get("supplement") or spec["keys"] == ("simple_kannada",):
            continue
        packed = _pack(ordered[: spec.get("max_chunks", 8)], "TEXTBOOK")
        parsed = _ask_section(topic, spec, packed, primary_selected)
        if not parsed:
            parsed = _ask_section(topic, spec, packed, primary_selected, strict=True)
        if not parsed:
            continue
        for key in spec["keys"]:
            value = parsed.get(key)
            if _usable(value):
                content[key] = value

    if not content.get("title") and not content.get("introduction") and not content.get("class9_textbook"):
        content["title"] = topic
        content["introduction"] = (
            "This module uses only the Class 9 Karnataka textbook. "
            "Some generated sections were skipped because they could not be grounded."
        )
        content["class9_textbook"] = _extractive_overview(primary_selected, topic)
        if not content["class9_textbook"]:
            return _refused(language, retrieval_query, primary_hits, primary_selected)

    blob = json.dumps(content, ensure_ascii=False)
    sources = _sources(supporting_evidence(blob, primary_selected, min_overlap=1))
    content["textbook_source_pages"] = sorted(
        {
            int(item["printed_page_number"] or item["textbook_page_number"])
            for item in sources
            if item.get("printed_page_number") is not None or item.get("textbook_page_number") is not None
        }
    )
    return {
        "answer": refusal_text(language) if not content else "",
        "title": content.get("title") or topic,
        "language": language,
        "grounded": True,
        "content": content,
        "sources": sources,
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(primary_hits),
        "selected_chunk_ids": [item["chunk_id"] for item in primary_selected],
        "used_supplementary": False,
        "evidence_pack": pack.as_public(),
    }


def _extractive_overview(items: list[dict], topic: str) -> str:
    lines = []
    seen = set()
    for item in items:
        text = " ".join((item.get("text") or "").split())
        if len(text) < 50:
            continue
        key = text[:70].lower()
        if key in seen:
            continue
        seen.add(key)
        snippet = text if len(text) <= 280 else text[:277].rsplit(" ", 1)[0] + "..."
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        lines.append(f"Printed page {page}: {snippet}")
        if len(lines) >= 8:
            break
    if not lines:
        return ""
    return (
        f"The Class 9 textbook covers {topic} in these passages. "
        "No extra books are used.\n\n" + "\n\n".join(lines)
    )


def _refused(language: str, retrieval_query: str, hits: list, selected: list) -> dict:
    base = _unavailable(language, retrieval_query, hits, selected)
    base["title"] = ""
    base["content"] = None
    return base


def _pack(items: list[dict], label: str) -> str:
    if not items:
        return f"[{label}] (none)"
    return "\n".join(
        f"[{label}; printed_page={item.get('printed_page_number') or item.get('textbook_page_number')}]\n"
        f"{(item.get('text') or '')[:1100]}"
        for item in items
    )


def _ask_section(topic: str, spec: dict, packed: str, evidence: list[dict], strict: bool = False) -> dict:
    keys = list(spec["keys"])
    extra = " If evidence is thin, omit the key. JSON object only. No names or dates unless they appear in the evidence."
    if strict:
        extra = " STRICT: omit any claim not clearly in the evidence. JSON object only."
    user = (
        f"Output language: en\n"
        f"Student topic: {topic}\n"
        f"Fill ONLY these JSON keys: {json.dumps(keys)}\n"
        f"{spec['instruction']}{extra}\n\n"
        f"Evidence:\n{packed}\n"
    )
    try:
        raw = complete(
            [
                {"role": "system", "content": ECONTENT_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.0 if strict else 0.1,
            max_tokens=spec.get("max_tokens", 350),
            timeout=SECTION_TIMEOUT,
        )
    except (LlmError, TimeoutError, OSError):
        return {}
    parsed = _parse_content(raw)
    kept = {key: parsed[key] for key in keys if key in parsed}
    blob = json.dumps(kept, ensure_ascii=False)
    if unsupported_named_items(blob, evidence):
        return {}
    return kept


def _parse_content(raw: str) -> dict:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    cleaned = {}
    for key in ALLOWED_KEYS:
        value = parsed.get(key)
        if _usable(value):
            cleaned[key] = value
    return cleaned


def _usable(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_usable(item) for item in value)
    if isinstance(value, dict):
        return any(_usable(item) for item in value.values())
    return True

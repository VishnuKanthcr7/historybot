"""Grounded structured E-content. Sectioned generation, primary first."""

from __future__ import annotations

import json
import re

from rag.engine.answer import _public_hits, _sources, _unavailable
from rag.engine.citations import supporting_evidence
from rag.engine.classify import classify_casual
from rag.engine.evidence import evidence_is_sufficient, evidence_matches_topic, select_evidence
from rag.engine.normalize import looks_kannada, looks_like_injection, normalize_question, rewrite_for_retrieval
from rag.llm.client import LlmError, complete
from rag.llm.config import RAG_TOP_K
from rag.prompts.econtent import ECONTENT_SYSTEM, SECTION_SPECS
from rag.prompts.tutor import refusal_text
from rag.vectorstore.retrieve import retrieve_primary, retrieve_supplementary

ALLOWED_KEYS = (
    "title",
    "introduction",
    "learning_objectives",
    "class9_textbook",
    "easy_english",
    "simple_kannada",
    "historical_context",
    "detailed_explanation",
    "important_people",
    "important_terms",
    "timeline",
    "main_events",
    "additional_school_book_detail",
    "important_places",
    "key_points",
    "exam_questions",
    "mcqs",
    "revision",
)

ECONTENT_TOP_K = max(RAG_TOP_K, 8)
SECTION_TIMEOUT = 75


def generate_econtent(topic: str, language: str = "en") -> dict:
    language = "kn" if language == "kn" else "en"
    topic = normalize_question(topic)
    if classify_casual(topic) or looks_like_injection(topic):
        return _refused(language, topic, [], [])
    needs_rewrite = language == "kn" or looks_kannada(topic)
    retrieval_query = rewrite_for_retrieval(topic, [], force=needs_rewrite)
    primary_hits = retrieve_primary(retrieval_query, top_k=ECONTENT_TOP_K, language=language)
    primary_selected = select_evidence(topic, retrieval_query, primary_hits, max_keep=5)
    if not evidence_is_sufficient(primary_selected) or not evidence_matches_topic(topic, retrieval_query, primary_selected):
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    supp_hits = retrieve_supplementary(retrieval_query, top_k=ECONTENT_TOP_K)
    supp_selected = select_evidence(topic, retrieval_query, supp_hits, max_keep=3)
    selected = list(primary_selected) + list(supp_selected)

    content: dict = {}
    for spec in SECTION_SPECS:
        keys = spec["keys"]
        if language != "kn" and keys == ("simple_kannada",):
            continue
        evidence = supp_selected if spec.get("supplement") else primary_selected
        if spec.get("supplement") and not evidence:
            continue
        packed = _pack(evidence[: spec.get("max_chunks", 3)], spec.get("label") or "PRIMARY")
        parsed = _ask_section(topic, language, spec, packed)
        if not parsed:
            parsed = _ask_section(topic, language, spec, packed, strict=True)
        if not parsed:
            continue
        for key in keys:
            value = parsed.get(key)
            if _usable(value):
                content[key] = value

    if not content.get("title") and not content.get("introduction") and not content.get("class9_textbook"):
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    extra_text = str(content.get("additional_school_book_detail") or "")
    primary_blob = json.dumps(
        {k: v for k, v in content.items() if k != "additional_school_book_detail"},
        ensure_ascii=False,
    )
    primary_sources = _sources(supporting_evidence(primary_blob, primary_selected))
    extra_sources = _sources(supporting_evidence(extra_text, supp_selected)) if extra_text else []
    sources = primary_sources + extra_sources
    content["textbook_source_pages"] = sorted(
        {
            int(item["printed_page_number"] or item["textbook_page_number"])
            for item in sources
            if item.get("authority") != "approved_supplementary"
            and (item.get("printed_page_number") is not None or item.get("textbook_page_number") is not None)
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
        "retrieved": _public_hits(primary_hits + supp_hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "used_supplementary": bool(extra_sources),
    }


def _refused(language: str, retrieval_query: str, hits: list, selected: list) -> dict:
    base = _unavailable(language, retrieval_query, hits, selected)
    base["title"] = ""
    base["content"] = None
    return base


def _pack(items: list[dict], label: str) -> str:
    if not items:
        return f"[{label}] (none)"
    return "\n".join(
        f"[{label}; printed_page={item.get('printed_page_number') or item.get('textbook_page_number')}]\n{(item.get('text') or '')[:900]}"
        for item in items
    )


def _ask_section(topic: str, language: str, spec: dict, packed: str, strict: bool = False) -> dict:
    keys = list(spec["keys"])
    extra = " If evidence is thin, omit the key. JSON object only."
    if strict:
        extra = " STRICT: omit any claim not clearly in the evidence. JSON object only."
    user = (
        f"Output language: {language}\n"
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
    return {key: parsed[key] for key in keys if key in parsed}


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

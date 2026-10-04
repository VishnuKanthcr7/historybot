"""Lightweight checks on the LLM answer. One optional regeneration only."""

from __future__ import annotations

import re

from rag.engine.evidence import content_tokens
from rag.engine.normalize import looks_kannada
from rag.prompts.tutor import KANNADA_SAFE_FALLBACK, refusal_text

LEAK_MARKERS = (
    "wikipedia",
    "as an ai",
    "language model",
    "vector database",
    "embedding",
    "chroma",
    "system prompt",
    "ollama",
)

PRIMARY_HEADING = re.compile(r"^##\s*From your Class 9 textbook\s*$", re.I | re.M)
EXTRA_HEADING = re.compile(r"^##\s*Additional school-book detail\s*$", re.I | re.M)


def is_refusal(answer: str, language: str) -> bool:
    text = (answer or "").strip()
    expected = refusal_text(language)
    return expected in text or "not available in the textbook" in text.lower()


def is_kannada_safe_fallback(answer: str) -> bool:
    return KANNADA_SAFE_FALLBACK in (answer or "")


def extract_mentioned_pages(answer: str) -> set[int]:
    pages = set()
    for match in re.finditer(r"(?:page|pages)\s+(\d+)(?:\s*[–-]\s*(\d+))?", answer, re.I):
        start = int(match.group(1))
        pages.add(start)
        if match.group(2):
            pages.add(int(match.group(2)))
    return pages


def split_detailed_sections(answer: str) -> tuple[str, str] | None:
    text = (answer or "").strip()
    if not PRIMARY_HEADING.search(text) or not EXTRA_HEADING.search(text):
        return None
    primary = PRIMARY_HEADING.split(text, maxsplit=1)
    if len(primary) < 2:
        return None
    rest = primary[1]
    extra_split = EXTRA_HEADING.split(rest, maxsplit=1)
    if len(extra_split) < 2:
        return None
    return extra_split[0].strip(), extra_split[1].strip()


def validate_answer(
    answer: str,
    language: str,
    evidence: list[dict],
    grounded_expected: bool,
    mode: str = "NORMAL",
    primary: list[dict] | None = None,
    supplement: list[dict] | None = None,
) -> tuple[bool, str]:
    text = (answer or "").strip()
    if not text:
        return False, "empty_answer"
    lowered = text.lower()
    if any(marker in lowered for marker in LEAK_MARKERS):
        return False, "internal_or_external_leak"
    if not grounded_expected:
        return True, "ok_ungrounded"
    if is_refusal(text, language):
        return False, "model_refused_despite_evidence"
    if language == "kn":
        kn_ok, kn_reason = validate_kannada_output(text)
        if not kn_ok:
            return False, kn_reason
    allowed_pages = {
        int(item.get("textbook_page_number") or item.get("printed_page_number"))
        for item in evidence
        if item.get("textbook_page_number") is not None or item.get("printed_page_number") is not None
    }
    mentioned = extract_mentioned_pages(text)
    if mentioned and not mentioned.issubset(allowed_pages):
        return False, "invented_page_citation"
    evidence_blob = " ".join(item.get("text") or "" for item in evidence).lower()
    extra_terms = ("plassey", "gdp", "prime minister", "wikipedia")
    for term in extra_terms:
        if term in lowered and term not in evidence_blob:
            return False, f"unsupported_term:{term}"
    if "@ktbs" in lowered:
        return False, "ocr_artifact"
    if mode == "DETAILED" and supplement:
        ok, reason = validate_detailed_separation(text, primary or [], supplement)
        if not ok:
            return False, reason
    return True, "ok"


def validate_kannada_output(text: str) -> tuple[bool, str]:
    if not looks_kannada(text):
        return False, "kannada_script_missing"
    if _kannada_loops(text):
        return False, "kannada_repetition"
    letters = re.findall(r"[A-Za-z\u0C80-\u0CFF]", text)
    kn_letters = [ch for ch in letters if "\u0C80" <= ch <= "\u0CFF"]
    if letters and (len(kn_letters) / len(letters)) < 0.55:
        return False, "kannada_too_much_english"
    kn_tokens = re.findall(r"[\u0C80-\u0CFF]+", text)
    if len(kn_tokens) < 6:
        return False, "kannada_too_short"
    unique = set(kn_tokens)
    if len(unique) < 5:
        return False, "kannada_low_variety"
    return True, "ok"


def validate_detailed_separation(answer: str, primary: list[dict], supplement: list[dict]) -> tuple[bool, str]:
    parts = split_detailed_sections(answer)
    if not parts:
        return False, "detailed_headings_missing"
    primary_section, extra_section = parts
    if not primary_section or not extra_section:
        return False, "detailed_section_empty"
    primary_tokens = content_tokens(" ".join(item.get("text") or "" for item in primary))
    supp_tokens = content_tokens(" ".join(item.get("text") or "" for item in supplement))
    supp_unique = supp_tokens - primary_tokens
    leaked = content_tokens(primary_section) & supp_unique
    if len(leaked) >= 3:
        return False, "supplement_facts_in_primary_section"
    return True, "ok"


def _kannada_loops(text: str) -> bool:
    tokens = re.findall(r"[\u0C80-\u0CFF]+", text or "")
    if len(tokens) < 8:
        return False
    phrase = " ".join(tokens[:4])
    rest = " ".join(tokens[4:])
    if phrase and rest.count(phrase) >= 2:
        return True
    for token in set(tokens):
        if len(token) >= 4 and tokens.count(token) >= 6:
            return True
    return False

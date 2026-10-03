"""Lightweight checks on the LLM answer. One optional regeneration only."""

from __future__ import annotations

import re

from rag.prompts.tutor import refusal_text

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


def is_refusal(answer: str, language: str) -> bool:
    text = (answer or "").strip()
    expected = refusal_text(language)
    return expected in text or "not available in the textbook" in text.lower()


def extract_mentioned_pages(answer: str) -> set[int]:
    pages = set()
    for match in re.finditer(r"(?:page|pages)\s+(\d+)(?:\s*[–-]\s*(\d+))?", answer, re.I):
        start = int(match.group(1))
        pages.add(start)
        if match.group(2):
            pages.add(int(match.group(2)))
    return pages


def validate_answer(answer: str, language: str, evidence: list[dict], grounded_expected: bool) -> tuple[bool, str]:
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
    allowed_pages = {int(item["textbook_page_number"]) for item in evidence if item.get("textbook_page_number") is not None}
    mentioned = extract_mentioned_pages(text)
    if mentioned and not mentioned.issubset(allowed_pages):
        return False, "invented_page_citation"
    evidence_blob = " ".join(item.get("text") or "" for item in evidence).lower()
    # Obvious extra-corpus names that must appear in evidence if used in the answer.
    extra_terms = ("plassey", "gdp", "prime minister", "wikipedia")
    for term in extra_terms:
        if term in lowered and term not in evidence_blob:
            return False, f"unsupported_term:{term}"
    return True, "ok"

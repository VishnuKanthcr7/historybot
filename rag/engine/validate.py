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
    lowered = text.lower()
    if "not available in the provided textbook" in lowered or "not available in the textbook" in lowered:
        return True
    if "kannada textbook support is currently unavailable" in lowered:
        return True
    expected = refusal_text(language)
    return expected in text or "ಲಭ್ಯವಿಲ್ಲ" in text


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
    extra_terms = ("plassey", "gdp", "prime minister", "wikipedia", "visionias", "world war")
    for term in extra_terms:
        if term in lowered and term not in evidence_blob:
            return False, f"unsupported_term:{term}"
    if "@ktbs" in lowered:
        return False, "ocr_artifact"
    if mode == "DETAILED" and supplement:
        ok, reason = validate_detailed_separation(text, primary or [], supplement)
        if not ok:
            return False, reason
    bad = unsupported_named_items(text, evidence)
    if bad:
        return False, "unsupported_claim:" + ",".join(bad[:6])
    return True, "ok"


CLAIM_SKIP = {
    "class",
    "karnataka",
    "history",
    "historybot",
    "textbook",
    "source",
    "introduction",
    "main",
    "points",
    "detailed",
    "explanation",
    "important",
    "people",
    "terms",
    "events",
    "key",
    "remember",
    "simple",
    "words",
    "board",
    "student",
    "question",
    "english",
    "section",
    "chapter",
    "primary",
    "evidence",
    "india",
    "indian",
    "social",
    "science",
    "state",
    "society",
    "after",
    "before",
    "during",
    "this",
    "that",
    "they",
    "their",
    "then",
    "from",
    "your",
    "king",
    "kings",
    "kingdom",
    "empire",
    "army",
    "north",
    "south",
    "east",
    "west",
    "however",
    "therefore",
    "although",
    "because",
    "explain",
    "according",
    "moreover",
    "besides",
    "finally",
    "firstly",
    "secondly",
    "using",
    "based",
    "under",
    "over",
    "between",
    "among",
    "through",
    "without",
    "within",
    "later",
    "early",
    "several",
    "various",
    "another",
    "other",
    "many",
    "some",
    "such",
    "most",
    "more",
    "also",
    "only",
    "even",
    "still",
    "both",
    "each",
    "these",
    "those",
    "there",
    "where",
    "which",
    "while",
    "what",
    "when",
    "who",
    "whom",
    "whose",
    "expansion",
    "administration",
    "system",
    "policy",
    "period",
    "order",
    "religion",
    "religious",
    "tolerance",
    "approach",
    "towards",
    "different",
    "religions",
}


def _norm_claim(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _supported_in_evidence(phrase: str, evidence_norm: str, evidence_lower: str) -> bool:
    compact = _norm_claim(phrase)
    if len(compact) < 4:
        return True
    if compact in evidence_norm:
        return True
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", phrase.lower())
        if token not in CLAIM_SKIP and len(token) > 2
    ]
    if not tokens:
        return True
    return all(token in evidence_lower for token in tokens)


def unsupported_named_items(answer: str, evidence: list[dict]) -> list[str]:
    """Reject new people/places/years/orgs. Allows paraphrase of supported names."""
    blob = " ".join(item.get("text") or "" for item in evidence)
    evidence_lower = blob.lower()
    evidence_norm = _norm_claim(blob)
    body_lines = []
    for line in (answer or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        body_lines.append(line)
    text = "\n".join(body_lines)
    flagged: list[str] = []

    def add(item: str) -> None:
        lowered = item.strip()
        if not lowered or lowered in flagged:
            return
        if any(marker in lowered.lower() for marker in ("textbook", "karnataka", "historybot", "class 9")):
            return
        if not _supported_in_evidence(lowered, evidence_norm, evidence_lower):
            flagged.append(lowered)

    for match in re.finditer(r"\b([A-Z][a-zA-Z']+(?:[\s-][A-Z][a-zA-Z']+){1,3})\b", text):
        add(match.group(1))
    for match in re.finditer(r"\b([A-Z][a-z]{4,})\b", text):
        add(match.group(1))
    for match in re.finditer(r"\b([A-Z]{3,})\b", text):
        add(match.group(1))
    for match in re.finditer(r"\b(1[0-9]{3}|20[0-2][0-9])\b", text):
        year = match.group(1)
        if year not in blob and year not in evidence_lower:
            add(year)
    return flagged


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

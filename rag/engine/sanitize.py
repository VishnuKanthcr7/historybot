"""Generic student-facing text cleanup. No topic-specific branches."""

from __future__ import annotations

import re

_OCR_SPACED = re.compile(r"(?:\b[A-Za-z]\s){4,}[A-Za-z]\b")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_DUP_WORD = re.compile(r"\b([A-Za-z][A-Za-z'\-]{1,28})(?:\s+\1\b)+", re.I)
_DUP_PHRASE = re.compile(r"\b(.{12,60}?)\b(?:\s+\1\b)+", re.I)
_DANGLING_END = re.compile(
    r"(?:\s+(?:the|of|and|to|a|an|with|for|in|on|by|from|at|as|or|that|which|who|whom|whose|their|his|her|its))+$",
    re.I,
)
_BAD_JOIN_FRAG = re.compile(
    r"\b(near|of|the|and|to|for|with|from|by|in|on|at|as)\s+(He|She|They|It|His|Her|Their|This|That|When|After|Before|During|While|Although|However)\b"
)
_LEADING_FRAGMENT = re.compile(
    r"^(?:st|nd|rd|th|ed|ing|ion|tions?|ment|ments?|ally|ness)\b[\s,.-]*",
    re.I,
)


def _collapse_ocr_spacing(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        chunk = match.group(0)
        letters = re.findall(r"[A-Za-z]", chunk)
        if len(letters) < 5:
            return chunk
        tokens = chunk.split()
        if sum(1 for t in tokens if len(t) == 1) < max(5, int(0.75 * len(tokens))):
            return chunk
        return "".join(letters)

    return _OCR_SPACED.sub(repl, text or "")


def _fix_broken_joins(text: str) -> str:
    """Repair smashed sentence joins without splitting multi-word proper names.

    Drop dangling prepositions / stranded filler nouns before a new-sentence
    capital. Repeat a few times so leftovers clean fully. Finally insert a
    period if a sentence-starter capital remains glued after a content word.
    """
    text = text or ""
    starters = (
        "He|She|They|It|His|Her|Their|This|That|When|After|Before|During|While|Although|However"
    )
    prep = r"near|of|the|and|to|for|with|from|by|in|on|at|as"
    filler = r"areas|parts|region|regions|place|places|side|sides|including"
    for _ in range(4):
        nxt = re.sub(rf"\b(?:{prep})\s+({starters})\b", r"\1", text)
        nxt = re.sub(rf"\b(?:{filler})\s+({starters})\b", r"\1", nxt)
        if nxt == text:
            break
        text = nxt
    text = re.sub(
        rf"\b([A-Za-z][\w'\-]*)\s+({starters})\b",
        r"\1. \2",
        text,
    )
    # Missing period before a capitalized name + verb (e.g. history of Akbar emerged).
    text = re.sub(
        r"\bof\s+([A-Z][A-Za-z]+(?:\s+(?:[IVX]{1,4}|[A-Z][A-Za-z]+))?)\s+(emerged|was|were|became|launched|fought|declared|assumed|conquered|defeated|appointed|established|wrote|built)\b",
        r"of \1. \1 \2",
        text,
    )
    # Smashed "history/relationship ... and Name Verb" -> split or drop glue.
    text = re.sub(
        r"\b(history of|relationship between)\s+([^.]{3,60}?)\s+and\s+([A-Z][A-Za-z][A-Za-z.\s]{0,40}?)\s+(fought|defeated|conquered|imprisoned|declared|launched)\b",
        r"\1 \2. \3 \4",
        text,
    )
    # Strip leftover "Name :" prefixes mid-answer (OCR heading bleed).
    text = re.sub(
        r"(?:(?<=[.!?\s])|^)([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s*:\s+(?=After\b|When\b|He\b|She\b|The\b)",
        "",
        text,
    )
    # Collapse duplicated "history of Name Verb" smash leftovers into "Name Verb".
    text = re.sub(
        r"\b(?:history of|story of|life of)\s+([A-Z][A-Za-z]+(?:\s+(?:[IVX]{1,4}|[A-Z][A-Za-z]+))?)\s+(emerged|was|were|became|launched|fought|declared|assumed|conquered|defeated|appointed|established|wrote|built)\b",
        r"\1 \2",
        text,
    )
    # ", With an intention..." is usually an OCR smash after a dangling clause.
    text = re.sub(
        r",\s+(With\s+(?:an\s+intention|the\s+intention|a\s+view)\b)",
        r". \1",
        text,
    )
    # Drop dangling "When Name protested against this," clauses with no object.
    text = re.sub(
        r"\bWhen\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}\s+protested against this,?\s*",
        "",
        text,
        flags=re.I,
    )
    return text


def _dedupe_overlapping_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    out: list[str] = []
    for part in parts:
        sent = part.strip()
        if not sent:
            continue
        norm = re.sub(r"[^a-z0-9]+", "", sent.lower())
        if len(norm) < 12:
            out.append(sent)
            continue
        dropped = False
        for idx, prev in enumerate(out):
            prev_norm = re.sub(r"[^a-z0-9]+", "", prev.lower())
            if not prev_norm:
                continue
            if norm == prev_norm or (norm in prev_norm and len(norm) >= 24) or (prev_norm in norm and len(prev_norm) >= 24):
                if len(norm) > len(prev_norm):
                    out[idx] = sent
                dropped = True
                break
            prev_words = prev.split()
            cur_words = sent.split()
            overlap = 0
            max_check = min(len(prev_words), len(cur_words), 14)
            for n in range(max_check, 3, -1):
                if [w.lower() for w in prev_words[-n:]] == [w.lower() for w in cur_words[:n]]:
                    overlap = n
                    break
            if overlap:
                out[idx] = " ".join(prev_words + cur_words[overlap:])
                dropped = True
                break
        if not dropped:
            out.append(sent)
    return " ".join(out)


def _trim_incomplete_tail(text: str) -> str:
    text = (text or "").rstrip()
    if not text:
        return text
    # Keep labeled choices / answer keys intact (A. option, Answer: B).
    if re.match(r"^[A-D]\.\s*\S", text) or re.match(r"^Answer:\s*[A-D]\s*$", text, re.I):
        return text
    page = ""
    m = re.search(r"(\s*\[Pages?\s+[0-9,\s]+\])\s*$", text, re.I)
    if m:
        page = m.group(1)
        text = text[: m.start()].rstrip()
    # Avoid stripping "Answer: A" via dangling article "a" (case-insensitive).
    if not re.search(r":\s*[A-Z]$", text):
        text = _DANGLING_END.sub("", text).rstrip(" ,;:-")
    # Avoid treating single-letter labels ("A.") as sentence terminators.
    chunks = re.split(r"(?<=[a-z0-9][.!?])\s+", text)
    if not chunks or chunks == [text]:
        # Fallback: also allow split after 2+ letter capitals (e.g. "OK. Next").
        chunks = re.split(r"(?<=[A-Za-z]{2}[.!?])\s+", text)
    if len(chunks) >= 2 and not re.search(r"[.!?]$", chunks[-1].strip()) and len(chunks[-1].split()) <= 4:
        text = " ".join(chunks[:-1]).rstrip()
    return (text + page).strip()


def _trim_leading_fragment(text: str) -> str:
    text = (text or "").lstrip()
    text = _LEADING_FRAGMENT.sub("", text).lstrip(" ,;:-")
    # Drop a leading lowercase run before the first capital/markdown marker.
    if text and text[0].islower() and not text.startswith("http"):
        m = re.search(r"[.!?]\s+([A-Z])", text)
        if m:
            text = text[m.start(1) :]
        else:
            m2 = re.search(r"\b([A-Z][A-Za-z].*)", text)
            if m2 and m2.start(1) <= 24:
                text = m2.group(1)
    return text



def _collapse_internal_overlap(text: str) -> str:
    """Remove duplicated/overlapping word runs inside a single sentence."""
    words = (text or "").split()
    changed = True
    guard = 0
    while changed and len(words) > 8 and guard < 8:
        guard += 1
        changed = False
        n = len(words)
        for length in range(min(28, n // 2), 4, -1):
            found = False
            for i in range(0, n - length):
                chunk = words[i : i + length]
                for j in range(i + 1, n - length + 1):
                    if words[j : j + length] != chunk:
                        continue
                    words = words[:j] + words[j + length :]
                    changed = True
                    found = True
                    break
                if found:
                    break
            if found:
                break
    return " ".join(words)



def _drop_corrupt_student_sentences(text: str) -> str:
    """Drop unresolved-referent / OCR-smash sentences after join repair."""
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    kept: list[str] = []
    for part in parts:
        sent = part.strip()
        if not sent:
            continue
        if re.search(r"\bprotested against this\b", sent, re.I):
            continue
        if re.search(r",\s+With\s+(?:an\s+intention|the\s+intention|a\s+view)\b", sent):
            continue
        if re.search(r"\brelationship between\b.{0,40}\band\s+[A-Z].{0,30}\bfought\b", sent, re.I):
            continue
        kept.append(sent)
    return " ".join(kept)


def sanitize_student_text(text: str) -> str:
    """Clean splices, OCR spacing, and duplicated overlaps for student display."""
    if not text or not text.strip():
        return text or ""
    blocks = re.split(r"(\n\s*\n)", text)
    cleaned_blocks: list[str] = []
    for block in blocks:
        if not block.strip() or re.fullmatch(r"\n\s*\n", block):
            cleaned_blocks.append(block)
            continue
        lines = block.splitlines()
        out_lines: list[str] = []
        for line in lines:
            raw = line
            stripped = raw.strip()
            if (
                stripped.startswith("#")
                or stripped.startswith("Source:")
                or re.match(r"^[A-D]\.\s+\S", stripped)
                or re.match(r"^Answer:\s*[A-D]\s*$", stripped, re.I)
            ):
                out_lines.append(raw)
                continue
            prefix = ""
            body = raw
            bullet = re.match(r"^(\s*(?:[-*]\s+|\d+\.\s+|\*\*[^*]+\*\*\s*))", raw)
            if bullet:
                prefix = bullet.group(1)
                body = raw[len(prefix) :]
            body = _collapse_ocr_spacing(body)
            body = _DUP_WORD.sub(r"\1", body)
            body = _DUP_PHRASE.sub(r"\1", body)
            body = _fix_broken_joins(body)
            body = _drop_corrupt_student_sentences(body)
            body = _dedupe_overlapping_sentences(body)
            body = _collapse_internal_overlap(body)
            body = _MULTI_SPACE.sub(" ", body).strip()
            body = _trim_leading_fragment(body)
            body = _trim_incomplete_tail(body)
            out_lines.append(prefix + body if body else raw.rstrip())
        cleaned_blocks.append("\n".join(out_lines))
    result = "".join(cleaned_blocks)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def sanitize_structured(value):
    """Recursively sanitize strings inside lists/dicts used by e-content."""
    if isinstance(value, str):
        return sanitize_student_text(value)
    if isinstance(value, list):
        return [sanitize_structured(item) for item in value]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in {"pages", "options", "type"}:
                out[key] = item
            else:
                out[key] = sanitize_structured(item)
        return out
    return value

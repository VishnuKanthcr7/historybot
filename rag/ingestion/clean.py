"""Light cleaning of extraction artifacts. Does not change textbook meaning."""

from __future__ import annotations

import re
import unicodedata

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[ \t]+")
_OCR_MARKERS = re.compile(
    r"@KTBS(?:\s+NOT TO BE REPUBLISHED)?|NOT TO BE REPUBLISHED",
    re.I,
)


def clean_page_text(raw_text: str, textbook_page_number: int) -> str:
    text = unicodedata.normalize("NFC", raw_text.replace("\r\n", "\n").replace("\r", "\n"))
    text = text.replace("\u00ad", "")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _join_narrow_column_words(text)
    text = strip_ocr_artifacts(text)
    text = _strip_printed_page_number(text, textbook_page_number)
    text = text.replace("•\t", "• ")
    text = text.replace("•\n", "• ")
    lines = [_MULTI_SPACE.sub(" ", line).rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def strip_ocr_artifacts(text: str) -> str:
    """Remove publisher watermarks. Does not rewrite historical sentences."""
    cleaned = _OCR_MARKERS.sub(" ", text or "")
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    cleaned = _MULTI_NEWLINE.sub("\n\n", cleaned)
    return cleaned.strip()


def _strip_printed_page_number(text: str, textbook_page_number: int) -> str:
    first, _, rest = text.partition("\n")
    if first.strip() == str(textbook_page_number):
        return rest.lstrip("\n")
    return text


def _join_narrow_column_words(text: str) -> str:
    """Join one-word-per-line runs from narrow sidebars without rewriting facts."""
    lines = text.split("\n")
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        if len(buf) >= 4:
            out.append(" ".join(buf))
        else:
            out.extend(buf)
        buf.clear()

    for line in lines:
        token = line.strip()
        is_single = bool(token) and (" " not in token) and len(token) <= 16
        if is_single and not token.endswith((":", ".", "?", "!")):
            buf.append(token)
            continue
        flush()
        out.append(line)
    flush()
    return "\n".join(out)

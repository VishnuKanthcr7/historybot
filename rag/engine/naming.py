"""Respectful naming in generated, student-facing text.

The researcher asked that generated text refer to "Chhatrapati Shivaji Maharaj"
rather than the bare "Shivaji". This is applied to text HistoryBot writes
(answers, learning modules, PDF body). It is NOT applied to verbatim textbook
excerpts (source quotes) or to text inside quotation marks, so quotations stay
exactly as printed. "Shivaji II" (a different person/epithet) is left alone.
"""

from __future__ import annotations

import re

FULL_NAME = "Chhatrapati Shivaji Maharaj"

# Bare "Shivaji" not already part of the full name, not "Shivaji II", not "Shivaji Maharaj",
# and not a longer word (e.g. "Shivajinagar").
_BARE = re.compile(
    r"(?<![A-Za-z])(?<!Chhatrapati )(?<!Chatrapati )(?<!Chhatrapathi )Shivaji(?![A-Za-z])(?!\s+(?:II|Maharaj)\b)"
)
# Spans left untouched: straight or curly double-quoted text, and single curly quotes.
_QUOTED = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d]*\u201d|\u2018[^\u2019\n]{3,}\u2019")


def full_name(text):
    if not isinstance(text, str) or "Shivaji" not in text:
        return text
    out = []
    last = 0
    for m in _QUOTED.finditer(text):
        out.append(_BARE.sub(FULL_NAME, text[last : m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_BARE.sub(FULL_NAME, text[last:]))
    return "".join(out)


_SKIP_KEYS = {"excerpt", "quote", "quotes", "source_text", "verbatim", "citation_label", "document_name", "chunk_id", "sources"}


def apply(value, key: str | None = None):
    """Recursively apply full_name to generated structures, skipping verbatim/source fields."""
    if key in _SKIP_KEYS:
        return value
    if isinstance(value, str):
        return full_name(value)
    if isinstance(value, list):
        return [apply(v, key) for v in value]
    if isinstance(value, dict):
        return {k: apply(v, k) for k, v in value.items()}
    return value

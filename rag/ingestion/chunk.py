"""Page-preserving chunking for later RAG. No embeddings in this phase."""

from __future__ import annotations

import re

from .config import (
    CHAPTER,
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    CHUNK_OVERLAP_RATIO,
    CHUNK_TARGET_CHARS,
    DOCUMENT_NAME,
    INGEST_VERSION,
    SOURCE_FILE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9I•])")
_HEADING_HINTS = (
    "in this chapter you learn",
    "do you know this?",
    "exercises",
    "activities",
    "project work",
    "fill in the blanks",
    "answer the following",
)


def chunk_pages(pages: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for page in pages:
        page_chunks = _chunk_page(page["text"], page["pdf_page_number"], page["textbook_page_number"])
        chunks.extend(page_chunks)
    return chunks


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    lower = stripped.lower()
    if any(lower.startswith(h) or lower == h for h in _HEADING_HINTS):
        return True
    if stripped.isupper() and 8 <= len(stripped) <= 80:
        return True
    if re.match(r"^(CHAPTER|Rule of |Babar|Humayun|Akbar|Jahangir|Shahjahan|Aurangzeb|Shivaji|Maratha|Peshwa|Bajirao|Madhav Rao)", stripped):
        return True
    if re.match(r"^[IVX]+\.\s", stripped):
        return True
    return False


def _chunk_page(text: str, pdf_page: int, textbook_page: int) -> list[dict]:
    sentences = _sentences_with_headings(text)
    packed = _pack_sentences(sentences)
    out = []
    prev_text = ""
    for index, body in enumerate(packed, start=1):
        overlap = ""
        if prev_text:
            overlap_len = max(40, int(len(prev_text) * CHUNK_OVERLAP_RATIO))
            overlap = prev_text[-overlap_len:].lstrip()
            # prefer overlapping from a sentence start
            parts = _SENTENCE_SPLIT.split(overlap)
            if len(parts) > 1:
                overlap = parts[-1]
        chunk_text = body if not overlap else f"{overlap} {body}".strip()
        if len(chunk_text) > CHUNK_MAX_CHARS + 120:
            chunk_text = body
        chunk_id = f"kseeb_c9_ss2_ch5_pdf{pdf_page}_tb{textbook_page}_{index:02d}"
        section = _section_from_text(body)
        out.append(
            {
                "chunk_id": chunk_id,
                "document_name": DOCUMENT_NAME,
                "chapter": CHAPTER,
                "section": section,
                "source_file": SOURCE_FILE,
                "ingest_version": INGEST_VERSION,
                "pdf_page_number": pdf_page,
                "textbook_page_number": textbook_page,
                "text": chunk_text,
                "char_count": len(chunk_text),
            }
        )
        prev_text = body
    return out


def _sentences_with_headings(text: str) -> list[str]:
    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in paragraph.split("\n") if ln.strip()]
        buf: list[str] = []
        for line in lines:
            if _is_heading(line) and buf:
                units.extend(_split_sentences(" ".join(buf)))
                buf = []
                units.append(line)
            elif _is_heading(line):
                units.append(line)
            else:
                buf.append(line)
        if buf:
            units.extend(_split_sentences(" ".join(buf)))
    return [u for u in units if u.strip()]


def _split_sentences(block: str) -> list[str]:
    block = re.sub(r"\s+", " ", block).strip()
    if not block:
        return []
    parts = _SENTENCE_SPLIT.split(block)
    return [p.strip() for p in parts if p.strip()]


def _pack_sentences(units: list[str]) -> list[str]:
    packed: list[str] = []
    current = ""
    pending_heading = ""

    def emit() -> None:
        nonlocal current, pending_heading
        piece = current.strip()
        if piece:
            packed.append(piece)
        current = ""

    for unit in units:
        prefix = f"{pending_heading} {unit}".strip() if pending_heading else unit
        if _is_heading(unit) and not current:
            pending_heading = f"{pending_heading} {unit}".strip() if pending_heading else unit
            continue
        if _is_heading(unit) and current:
            if len(current) >= CHUNK_MIN_CHARS:
                emit()
                pending_heading = unit
                continue
            prefix = f"{current} {unit}".strip()
            pending_heading = ""
        candidate = f"{current} {prefix}".strip() if current else prefix
        pending_heading = ""
        if len(candidate) <= CHUNK_MAX_CHARS or not current:
            current = candidate
            if len(current) >= CHUNK_TARGET_CHARS and not _is_heading(unit):
                emit()
            continue
        emit()
        current = prefix
        if len(current) >= CHUNK_TARGET_CHARS:
            emit()
    if pending_heading:
        current = f"{current} {pending_heading}".strip()
    if current:
        if packed and len(current) < CHUNK_MIN_CHARS:
            packed[-1] = f"{packed[-1]} {current}".strip()
        else:
            packed.append(current.strip())
    return packed


def _section_from_text(text: str) -> str:
    first = text.strip().split("\n", 1)[0][:120]
    if _is_heading(first):
        return first[:80]
    match = re.match(
        r"^(Babar|Humayun|Akbar|Jahangir|Shahjahan|Aurangzeb|Shivaji|The Maratha|Peshwa|Bajirao|Madhav Rao|EXERCISES|Do you know this\?)",
        text.strip(),
        re.I,
    )
    if match:
        return match.group(1)
    return "body"

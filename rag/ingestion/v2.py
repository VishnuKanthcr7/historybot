"""Phase 11 page extraction, quality gates, and chunking. Does not rewrite facts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from rag.ingestion.chunk import chunk_pages
from rag.ingestion.chunk_quality import assess_chunk
from rag.ingestion.clean import clean_page_text
from rag.ingestion.config import EXTRACTED_DIR, INGEST_VERSION
from rag.ingestion.nudi import converter_status, convert_nudi_to_unicode, looks_like_raw_nudi
from rag.sources.catalog import EXCLUDED_SOURCE_FILES, find_source

PHASE11_DIR = EXTRACTED_DIR / "phase11"
INGEST_VERSION_V2 = 2
MIN_RELIABLE_CHARS = 280
CROP_JUNK = re.compile(r"\bwas an the\b|\bthe  were\b")


def extract_source_pages(source: dict, convert_nudi: bool = False) -> dict:
    path: Path = source["path"]
    if path is None or not path.exists():
        raise FileNotFoundError(f"Source PDF missing: {source['source_id']}")
    if path.name in EXCLUDED_SOURCE_FILES:
        raise ValueError(f"Excluded source cannot be ingested: {path.name}")

    doc = pymupdf.open(path)
    pages = []
    excluded = []
    try:
        start = source["pdf_page_start"]
        end = min(source["pdf_page_end"], doc.page_count)
        if doc.page_count < start:
            raise ValueError(f"{path.name} has {doc.page_count} pages; need PDF page {start}.")
        for pdf_page in range(start, end + 1):
            raw = doc[pdf_page - 1].get_text("text") or ""
            printed = _printed_page(raw, pdf_page, source)
            text = raw
            if convert_nudi:
                text = convert_nudi_to_unicode(raw)
            elif looks_like_raw_nudi(raw) and source.get("language") == "kn":
                excluded.append(
                    {
                        "pdf_page_number": pdf_page,
                        "reason": "raw_nudi_without_converter",
                    }
                )
                continue
            cleaned = clean_page_text(text, printed)
            quality = _page_quality(cleaned, source)
            record = {
                **{k: source[k] for k in (
                    "source_id",
                    "source_type",
                    "authority",
                    "language",
                    "document_name",
                    "publisher",
                    "chapter",
                    "topic",
                    "citation_label",
                    "id_prefix",
                )},
                "source_file": path.name,
                "ingest_version": INGEST_VERSION_V2,
                "pdf_page_number": pdf_page,
                "printed_page_number": printed,
                "textbook_page_number": printed,
                "raw_text": raw,
                "text": cleaned,
                "char_count": len(cleaned),
                "usable": quality["usable"],
                "quality_notes": quality["notes"],
            }
            if quality["usable"]:
                pages.append(record)
            else:
                excluded.append(
                    {
                        "pdf_page_number": pdf_page,
                        "printed_page_number": printed,
                        "reason": quality["notes"],
                        "char_count": len(cleaned),
                    }
                )
    finally:
        doc.close()
    chunks = chunk_pages(pages)
    excluded_chunks = []
    for chunk in chunks:
        quality = assess_chunk(chunk)
        chunk["retrieval_excluded"] = quality["excluded"]
        chunk["quality_notes"] = quality["reason"]
        if quality["excluded"]:
            excluded_chunks.append({"chunk_id": chunk["chunk_id"], "reason": quality["reason"]})
    return {
        "source_id": source["source_id"],
        "pages": pages,
        "excluded_pages": excluded,
        "chunks": chunks,
        "excluded_chunks": excluded_chunks,
    }


def _printed_page(raw: str, pdf_page: int, source: dict) -> int:
    first = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
    if first.isdigit():
        return int(first)
    # KTBS 2026–27 Chapter 17: PDF 3 -> printed 1
    if source["source_id"] == "ktbs_2026_en_ch17":
        return pdf_page - 2
    if source["source_id"] == "ktbs_2026_kn_ch17":
        return pdf_page - 2
    if source["source_id"] == "ncert_mughals":
        return pdf_page + 38
    if source["source_id"] == "ncert_marathas":
        return pdf_page + 60
    return pdf_page


def _page_quality(text: str, source: dict) -> dict:
    notes = []
    usable = True
    if len((text or "").strip()) < MIN_RELIABLE_CHARS:
        usable = False
        notes.append("too_short")
    if "\ufffd" in (text or ""):
        usable = False
        notes.append("replacement_characters")
    if source["source_type"] == "supplementary_mughal":
        # Keep pages with known crop artifacts if remaining prose is long enough.
        if CROP_JUNK.search(text or "") and len(text) < 600:
            usable = False
            notes.append("severe_crop")
        elif CROP_JUNK.search(text or ""):
            notes.append("crop_artifact_kept_unfixed")
    return {"usable": usable, "notes": ",".join(notes) or "ok"}


def run_phase11_extract() -> dict:
    PHASE11_DIR.mkdir(parents=True, exist_ok=True)
    nudi = converter_status()
    results = []
    all_chunks = []
    all_pages = []

    english = extract_source_pages(find_source("ktbs_2026_en_ch17"))
    _require_english_mapping(english)
    results.append(_summary(english))
    all_chunks.extend(english["chunks"])
    all_pages.extend(_public_pages(english["pages"]))

    kannada_status = {
        "source_id": "ktbs_2026_kn_ch17",
        "ingested": False,
        "reason": nudi["note"],
        "converter": nudi,
        "chunk_count": 0,
    }
    if nudi["available"]:
        try:
            kn_source = find_source("ktbs_2026_kn_ch17")
            kannada = extract_source_pages(kn_source, convert_nudi=True)
            if any(looks_like_raw_nudi(chunk["text"]) for chunk in kannada["chunks"]):
                raise RuntimeError("Converted Kannada chunks still look like Nudi ASCII.")
            results.append(_summary(kannada))
            all_chunks.extend(kannada["chunks"])
            all_pages.extend(_public_pages(kannada["pages"]))
            kannada_status = {
                "source_id": "ktbs_2026_kn_ch17",
                "ingested": True,
                "reason": "converted",
                "converter": nudi,
                "chunk_count": len(kannada["chunks"]),
            }
        except Exception as exc:
            kannada_status["reason"] = str(exc)

    for source_id in ("ncert_mughals", "ncert_marathas"):
        extracted = extract_source_pages(find_source(source_id))
        results.append(_summary(extracted))
        all_chunks.extend(extracted["chunks"])
        all_pages.extend(_public_pages(extracted["pages"]))

    ids = [item["chunk_id"] for item in all_chunks]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate chunk_id values in Phase 11 extract.")
    for chunk in all_chunks:
        if chunk.get("source_file") in EXCLUDED_SOURCE_FILES:
            raise RuntimeError(f"Excluded file leaked into chunks: {chunk.get('source_file')}")

    payload = {
        "ingest_version": INGEST_VERSION_V2,
        "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
        "legacy_ingest_version_unchanged": INGEST_VERSION,
        "kannada": kannada_status,
        "sources": results,
        "chunk_count": len(all_chunks),
        "counts_by_source_type": _count(all_chunks, "source_type"),
        "counts_by_language": _count(all_chunks, "language"),
        "counts_by_authority": _count(all_chunks, "authority"),
    }
    _write(PHASE11_DIR / "pages.json", all_pages)
    _write(PHASE11_DIR / "chunks.json", all_chunks)
    _write(PHASE11_DIR / "summary.json", payload)
    payload["chunks"] = all_chunks
    return payload


def _require_english_mapping(extracted: dict) -> None:
    pages = extracted["pages"]
    if not pages:
        raise RuntimeError("English Chapter 17 produced no pages.")
    first, last = pages[0], pages[-1]
    if first["pdf_page_number"] != 3 or first["printed_page_number"] != 1:
        raise RuntimeError(
            f"English mapping failed: PDF {first['pdf_page_number']} -> printed {first['printed_page_number']}"
        )
    if last["pdf_page_number"] != 20 or last["printed_page_number"] != 18:
        raise RuntimeError(
            f"English end mapping failed: PDF {last['pdf_page_number']} -> printed {last['printed_page_number']}"
        )
    joined = "\n".join(page["text"] for page in pages)
    if "CHAPTER" not in pages[0]["text"] or "AHOM" not in pages[0]["text"].upper():
        raise RuntimeError("English Chapter 17 heading not found on PDF page 3.")
    if "BHAKTI" in joined.upper() and "CHAPTER – 18" in joined.upper():
        raise RuntimeError("Chapter 18 leaked into Chapter 17 extract.")


def _public_pages(pages: list[dict]) -> list[dict]:
    return [{k: v for k, v in page.items() if k != "raw_text"} for page in pages]


def _summary(extracted: dict) -> dict:
    return {
        "source_id": extracted["source_id"],
        "page_count": len(extracted["pages"]),
        "chunk_count": len(extracted["chunks"]),
        "excluded_pages": extracted["excluded_pages"],
        "excluded_chunks": extracted.get("excluded_chunks") or [],
        "pdf_pages": [p["pdf_page_number"] for p in extracted["pages"]],
        "printed_pages": [p["printed_page_number"] for p in extracted["pages"]],
    }


def _count(chunks: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for item in chunks:
        label = str(item.get(key) or "unknown")
        out[label] = out.get(label, 0) + 1
    return out


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

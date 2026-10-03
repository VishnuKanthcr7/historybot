"""Run Chapter 5 ingest (PDF pages 3–16) and write JSON artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .chunk import chunk_pages
from .clean import clean_page_text
from .config import CHAPTER, EXTRACTED_DIR, INGEST_VERSION, PDF_PAGE_END, PDF_PAGE_START, SOURCE_PDF
from .extract import extract_pages
from .visuals import detect_visuals

CHAPTER_6_PATTERN = re.compile(r"CHAPTER\s*[-–—]?\s*6\b|\bBHAKTI PANTH\b", re.I)


def run_ingest(pdf_path: Path | None = None) -> dict:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    raw_pages = extract_pages(pdf_path)
    pages = []
    for item in raw_pages:
        cleaned = clean_page_text(item["raw_text"], item["textbook_page_number"])
        page = {**item, "text": cleaned, "char_count": len(cleaned)}
        pages.append(page)

    chunks = chunk_pages(pages)
    visuals = detect_visuals(pdf_path)
    validation = validate(pages, chunks)

    pages_out = [{k: v for k, v in p.items() if k != "raw_text"} for p in pages]
    _write_json(EXTRACTED_DIR / "chapter5_pages.json", pages_out)
    _write_json(EXTRACTED_DIR / "chapter5_chunks.json", chunks)
    _write_json(EXTRACTED_DIR / "chapter5_visuals.json", visuals)

    summary = {
        "ingest_version": INGEST_VERSION,
        "source_pdf": str(SOURCE_PDF.name),
        "pdf_pages": f"{PDF_PAGE_START}-{PDF_PAGE_END}",
        "processed_page_count": len(pages),
        "chapter": CHAPTER,
        "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
        "ocr_used": False,
        "char_count_per_page": [
            {
                "pdf_page_number": p["pdf_page_number"],
                "textbook_page_number": p["textbook_page_number"],
                "char_count": p["char_count"],
            }
            for p in pages
        ],
        "total_extracted_characters": sum(p["char_count"] for p in pages),
        "chunk_count": len(chunks),
        "chunk_char_min": min((c["char_count"] for c in chunks), default=0),
        "chunk_char_max": max((c["char_count"] for c in chunks), default=0),
        "chunk_char_avg": round(sum(c["char_count"] for c in chunks) / len(chunks), 1) if chunks else 0,
        "visual_count": len(visuals),
        "validation": validation,
    }
    _write_json(EXTRACTED_DIR / "chapter5_ingest_summary.json", summary)
    return summary


def validate(pages: list[dict], chunks: list[dict]) -> dict:
    pdf_pages = [p["pdf_page_number"] for p in pages]
    mapping_ok = all(p["textbook_page_number"] == p["pdf_page_number"] - 2 for p in pages)
    joined = "\n".join(p["text"] for p in pages)
    first = pages[0]["text"] if pages else ""
    last = pages[-1]["text"] if pages else ""
    required = ("chunk_id", "pdf_page_number", "textbook_page_number", "chapter", "source_file", "ingest_version")
    missing_meta = [c["chunk_id"] for c in chunks if any(not c.get(k) and c.get(k) != 0 for k in required)]
    missing_pages = [c["chunk_id"] for c in chunks if not c.get("pdf_page_number") or not c.get("textbook_page_number")]
    checks = {
        "processed_pages_exactly_3_to_16": pdf_pages == list(range(3, 17)),
        "processed_page_count_14": len(pages) == 14,
        "pdf3_maps_to_textbook1": bool(pages) and pages[0]["pdf_page_number"] == 3 and pages[0]["textbook_page_number"] == 1,
        "pdf16_maps_to_textbook14": bool(pages) and pages[-1]["pdf_page_number"] == 16 and pages[-1]["textbook_page_number"] == 14,
        "chapter_title_detected": "THE MOGHULS AND THE MARATHAS" in first,
        "chapter_5_heading_detected": bool(re.search(r"CHAPTER\s*[-–—]?\s*5", first, re.I)),
        "chapter_6_not_present": not bool(CHAPTER_6_PATTERN.search(joined)),
        "ends_with_exercises": "EXERCISES" in last,
        "every_chunk_has_required_metadata": len(missing_meta) == 0,
        "no_chunk_without_page_numbers": len(missing_pages) == 0,
        "ocr_not_used": True,
    }
    checks["all_passed"] = all(checks.values())
    checks["failed"] = [name for name, ok in checks.items() if name != "all_passed" and not ok]
    return checks


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

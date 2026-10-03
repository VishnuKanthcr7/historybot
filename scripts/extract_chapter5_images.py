"""Crop Chapter 5 textbook figures. Does not download internet images."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymupdf

from rag.ingestion.config import SOURCE_PDF

OUT_DIR = ROOT / "data" / "images"
MANIFEST = ROOT / "data" / "extracted" / "chapter5_image_manifest.json"

# Only figures whose caption or nearby heading is identifiable in the ingest notes.
CROPS = [
    {
        "slug": "akbar-portrait",
        "topic": "Akbar",
        "person_name": "Akbar",
        "pdf_page": 5,
        "textbook_page": 3,
        "bbox": [336.6, 270.7, 464.5, 449.3],
        "caption": "Akbar (textbook figure)",
        "alt_text": "Portrait labelled Akbar in the Class 9 Social Science textbook.",
        "verified": True,
    },
    {
        "slug": "akbar-kingdom-map",
        "topic": "Akbar's kingdom",
        "person_name": "Akbar",
        "pdf_page": 6,
        "textbook_page": 4,
        "bbox": [99.8, 52.9, 410.0, 399.0],
        "caption": "Akbar’s kingdom (textbook map)",
        "alt_text": "Map labelled Akbar’s kingdom in the Class 9 Social Science textbook.",
        "verified": True,
    },
    {
        "slug": "panch-mahal",
        "topic": "Panch Mahal",
        "person_name": None,
        "pdf_page": 8,
        "textbook_page": 6,
        "bbox": [275.2, 45.1, 467.2, 173.0],
        "caption": "Panch mahal at Fatehpur Sikri (textbook figure)",
        "alt_text": "Textbook illustration of Panch mahal at Fatehpur Sikri.",
        "verified": True,
    },
    {
        "slug": "maratha-kingdom-map",
        "topic": "Maratha Kingdom",
        "person_name": "Shivaji",
        "pdf_page": 13,
        "textbook_page": 11,
        "bbox": [105.0, 51.7, 405.2, 413.8],
        "caption": "Maratha Kingdom (textbook map)",
        "alt_text": "Map labelled Maratha Kingdom in the Class 9 Social Science textbook.",
        "verified": True,
    },
]


def main() -> int:
    if not SOURCE_PDF.exists():
        raise SystemExit(f"Textbook PDF missing: {SOURCE_PDF}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(SOURCE_PDF)
    written = []
    try:
        for item in CROPS:
            page = doc[item["pdf_page"] - 1]
            rect = pymupdf.Rect(*item["bbox"])
            pix = page.get_pixmap(clip=rect, dpi=140)
            rel = f"data/images/{item['slug']}.png"
            dest = ROOT / rel
            pix.save(dest)
            row = {
                **item,
                "file_path": rel.replace("\\", "/"),
                "source": "KSEEB Class 9 Social Science Part 2, Chapter 5 (embedded textbook figure)",
                "license": (
                    "Not a separately licensed stock image. Cropped from the project textbook PDF "
                    "for this educational HistoryBot prototype only. Do not treat as a public-domain "
                    "or Creative Commons photograph."
                ),
                "verification_status": "verified" if item["verified"] else "unverified",
                "verified_by": "phase-9-textbook-crop",
            }
            written.append(row)
            print("WROTE", dest, dest.stat().st_size)
    finally:
        doc.close()
    MANIFEST.write_text(json.dumps(written, ensure_ascii=False, indent=2), encoding="utf-8")
    print("MANIFEST", MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

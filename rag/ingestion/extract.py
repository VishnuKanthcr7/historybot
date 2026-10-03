"""Page-aware PDF text extraction. Does not rewrite textbook facts."""

from __future__ import annotations

import pymupdf

from .config import (
    CHAPTER,
    DOCUMENT_NAME,
    INGEST_VERSION,
    PDF_PAGE_END,
    PDF_PAGE_START,
    PDF_TO_TEXTBOOK_PAGE,
    SOURCE_FILE,
    SOURCE_PDF,
)


def extract_pages(pdf_path=None) -> list[dict]:
    path = pdf_path or SOURCE_PDF
    if not path.exists():
        raise FileNotFoundError(f"Textbook PDF not found: {path}")

    doc = pymupdf.open(path)
    try:
        if doc.page_count < PDF_PAGE_END:
            raise ValueError(
                f"PDF has {doc.page_count} pages; need through PDF page {PDF_PAGE_END}."
            )
        pages = []
        for pdf_page in range(PDF_PAGE_START, PDF_PAGE_END + 1):
            page = doc[pdf_page - 1]
            raw = page.get_text("text") or ""
            pages.append(
                {
                    "document_name": DOCUMENT_NAME,
                    "chapter": CHAPTER,
                    "source_file": SOURCE_FILE,
                    "ingest_version": INGEST_VERSION,
                    "pdf_page_number": pdf_page,
                    "textbook_page_number": PDF_TO_TEXTBOOK_PAGE[pdf_page],
                    "raw_text": raw,
                    "char_count_raw": len(raw),
                }
            )
        return pages
    finally:
        doc.close()

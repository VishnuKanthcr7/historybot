"""Phase 4 ingest configuration. Chapter 5 only (PDF pages 3–16)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PDF = PROJECT_ROOT / "data" / "textbooks" / "KSEEB-Class-9-Social-Science-Part-2-Textbook.pdf"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"

SOURCE_FILE = "KSEEB-Class-9-Social-Science-Part-2-Textbook.pdf"
DOCUMENT_NAME = "KSEEB Class 9 Social Science Part 2"
CHAPTER = "THE MOGHULS AND THE MARATHAS"
INGEST_VERSION = 1

PDF_PAGE_START = 3
PDF_PAGE_END = 16

# PDF page number -> printed textbook page number
PDF_TO_TEXTBOOK_PAGE = {pdf: pdf - 2 for pdf in range(PDF_PAGE_START, PDF_PAGE_END + 1)}

CHUNK_MIN_CHARS = 400
CHUNK_MAX_CHARS = 700
CHUNK_TARGET_CHARS = 550
CHUNK_OVERLAP_RATIO = 0.15

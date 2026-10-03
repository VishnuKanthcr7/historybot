"""Approved Phase 11 source files. VisionIAS and costume notes stay excluded."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEXTBOOKS = PROJECT_ROOT / "data" / "textbooks"
SOURCES_DIR = TEXTBOOKS / "sources"

PRIMARY_ENGLISH_FILE = "9th English SS Part - 2 2026-27.pdf"
SUPPLEMENT_MUGHAL_FILE = "The Mughals.pdf"
SUPPLEMENT_MARATHA_FILE = "The marathas.pdf"

EXCLUDED_SOURCE_FILES = frozenset(
    {
        "2d239-the-mughal-empire.pdf",
        "4839a-maratha-empire.pdf",
        "The mughalss.pdf",
        "Who was Shivaji_.pdf",
    }
)

SOURCES = {
    "ktbs_2026_en_ch17": {
        "source_id": "ktbs_2026_en_ch17",
        "source_type": "primary_textbook",
        "authority": "primary",
        "language": "en",
        "document_name": "KTBS Class 9 Social Science Part 2 (English) 2026-27",
        "publisher": "Karnataka Textbook Society",
        "chapter": "THE AHOM DYNASTY, THE Mughals AND THE MARATHAS",
        "topic": "Ahoms, Mughals and Marathas",
        "citation_label": "Class 9 Karnataka State Board 2026–27 textbook",
        "path": SOURCES_DIR / PRIMARY_ENGLISH_FILE,
        "pdf_page_start": 3,
        "pdf_page_end": 20,
        "id_prefix": "ktbs2026_en_ch17",
    },
    "ktbs_2026_kn_ch17": {
        "source_id": "ktbs_2026_kn_ch17",
        "source_type": "primary_kannada_textbook",
        "authority": "primary",
        "language": "kn",
        "document_name": "KTBS Class 9 Social Science Part 2 (Kannada) 2026-27",
        "publisher": "Karnataka Textbook Society",
        "chapter": "ಆಹೋಮ್ ರಾಜವಂಶ, ಮೊಘಲರು ಮತ್ತು ಮರಾಠರು",
        "topic": "Ahoms, Mughals and Marathas",
        "citation_label": "Class 9 Karnataka State Board 2026–27 Kannada textbook",
        "path": None,
        "pdf_page_start": 3,
        "pdf_page_end": 20,
        "id_prefix": "ktbs2026_kn_ch17",
        "requires_nudi": True,
    },
    "ncert_mughals": {
        "source_id": "ncert_mughals",
        "source_type": "supplementary_mughal",
        "authority": "approved_supplementary",
        "language": "en",
        "document_name": "The Mughals (16th to 17th Century)",
        "publisher": "NCERT / CIET",
        "chapter": "THE MUGHALS",
        "topic": "Mughal empire",
        "citation_label": "Additional school-book source: The Mughals",
        "path": SOURCES_DIR / SUPPLEMENT_MUGHAL_FILE,
        "pdf_page_start": 1,
        "pdf_page_end": 10,
        "id_prefix": "ncert_mughals",
    },
    "ncert_marathas": {
        "source_id": "ncert_marathas",
        "source_type": "supplementary_maratha",
        "authority": "approved_supplementary",
        "language": "en",
        "document_name": "The Rise of the Marathas",
        "publisher": "NCERT",
        "chapter": "The Rise of the Marathas",
        "topic": "Marathas",
        "citation_label": "Additional school-book source: The Rise of the Marathas",
        "path": SOURCES_DIR / SUPPLEMENT_MARATHA_FILE,
        "pdf_page_start": 1,
        "pdf_page_end": 22,
        "id_prefix": "ncert_marathas",
    },
}


def find_kannada_pdf() -> Path | None:
    if not SOURCES_DIR.is_dir():
        return None
    matches = sorted(SOURCES_DIR.glob("*Kannada*2026-27.pdf"))
    return matches[0] if matches else None


def find_source(source_id: str) -> dict:
    item = dict(SOURCES[source_id])
    if source_id == "ktbs_2026_kn_ch17":
        item["path"] = find_kannada_pdf()
    return item

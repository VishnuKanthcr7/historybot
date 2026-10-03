"""Record textbook visuals on ingested pages. Does not fetch internet images."""

from __future__ import annotations

import pymupdf

from .config import PDF_PAGE_END, PDF_PAGE_START, PDF_TO_TEXTBOOK_PAGE, SOURCE_PDF

MIN_IMAGE_WIDTH = 40
MIN_IMAGE_HEIGHT = 40


def detect_visuals(pdf_path=None) -> list[dict]:
    path = pdf_path or SOURCE_PDF
    doc = pymupdf.open(path)
    visuals: list[dict] = []
    try:
        for pdf_page in range(PDF_PAGE_START, PDF_PAGE_END + 1):
            page = doc[pdf_page - 1]
            textbook_page = PDF_TO_TEXTBOOK_PAGE[pdf_page]
            image_blocks = [b for b in page.get_text("dict")["blocks"] if b.get("type") == 1]
            captions = _nearby_captions(page)
            for block in image_blocks:
                x0, y0, x1, y1 = block["bbox"]
                width, height = x1 - x0, y1 - y0
                if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                    visuals.append(
                        {
                            "pdf_page_number": pdf_page,
                            "textbook_page_number": textbook_page,
                            "visual_type": "decorative_or_glyph",
                            "width_pt": round(width, 1),
                            "height_pt": round(height, 1),
                            "bbox": [round(v, 1) for v in block["bbox"]],
                            "caption_guess": None,
                            "notes": "Too small to treat as a photograph or map. Likely a glyph/icon.",
                        }
                    )
                    continue
                caption = _best_caption(captions, y0, y1)
                visuals.append(
                    {
                        "pdf_page_number": pdf_page,
                        "textbook_page_number": textbook_page,
                        "visual_type": _classify(caption, width, height),
                        "width_pt": round(width, 1),
                        "height_pt": round(height, 1),
                        "bbox": [round(v, 1) for v in block["bbox"]],
                        "caption_guess": caption,
                        "notes": "Embedded in the textbook PDF. Not downloaded from the internet.",
                    }
                )
        return visuals
    finally:
        doc.close()


def _nearby_captions(page) -> list[tuple[float, str]]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        text = "".join(
            span.get("text", "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ).strip()
        if not text:
            continue
        out.append((block["bbox"][1], text[:160]))
    return out


def _best_caption(captions: list[tuple[float, str]], y0: float, y1: float) -> str | None:
    nearby = []
    for y, text in captions:
        if abs(y - y0) < 90 or abs(y - y1) < 90:
            if len(text) <= 80:
                nearby.append(text)
    if nearby:
        return nearby[0]
    return None


def _classify(caption: str | None, width: float, height: float) -> str:
    label = (caption or "").lower()
    if "kingdom" in label or "map" in label or width > 250 and height > 250:
        return "map"
    if any(word in label for word in ("taj", "fort", "mahal", "panch", "monument")):
        return "photograph_or_monument"
    if any(word in label for word in ("akbar", "shivaji", "babar", "portrait")):
        return "portrait_or_photograph"
    return "textbook_image"

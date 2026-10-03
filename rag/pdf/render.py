"""ReportLab PDF for grounded E-content. Uses bundled Unicode fonts only."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = Path(os.environ.get("PDF_FONT_DIR") or ROOT / "data" / "fonts")
IMAGE_ROOT = ROOT

NAVY = HexColor("#1e3a5f")
BRASS = HexColor("#9a6b2f")
INK = HexColor("#1c1917")
RULE = HexColor("#ddd4c4")
PAPER = HexColor("#f6f1e8")

FONT_REG = "HistoryBotSans"
FONT_BOLD = "HistoryBotSans-Bold"


def _register_fonts() -> tuple[str, str]:
    regular = FONT_DIR / "NotoSans-Regular.ttf"
    kannada = FONT_DIR / "NotoSansKannada-Regular.ttf"
    bold = FONT_DIR / "NotoSans-Bold.ttf"
    if not regular.exists() or not kannada.exists():
        raise FileNotFoundError(
            "Unicode PDF fonts missing. Place NotoSans-Regular.ttf and "
            "NotoSansKannada-Regular.ttf in data/fonts/ (SIL Open Font License)."
        )
    pdfmetrics.registerFont(TTFont(FONT_REG, str(regular)))
    # Kannada glyphs live in the Kannada file; ReportLab uses one face per style.
    # Register Kannada as the body face so English + Kannada both render.
    pdfmetrics.registerFont(TTFont("HistoryBotKannada", str(kannada)))
    if bold.exists():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
        return FONT_REG, FONT_BOLD
    return FONT_REG, FONT_REG


def _has_kannada(text: str) -> bool:
    return any("\u0C80" <= ch <= "\u0CFF" for ch in str(text or ""))


def render_econtent_pdf(document: dict, images: list[dict] | None = None) -> bytes:
    body_font, heading_font = _register_fonts()
    buffer = BytesIO()
    content = document.get("content") or {}
    language = document.get("language") or "en"
    title = document.get("title") or content.get("title") or "HistoryBot E-content"
    sources = document.get("sources") or []
    title_font = "HistoryBotKannada" if language == "kn" or _has_kannada(title) else heading_font

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont(heading_font, 9)
        canvas.drawString(18 * mm, A4[1] - 9 * mm, "HistoryBot")
        canvas.setFont(body_font, 8)
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 9 * mm, "Class 9 History · Textbook-grounded")
        canvas.setFillColor(BRASS)
        canvas.rect(0, 0, A4[0], 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont(body_font, 8)
        canvas.drawString(18 * mm, 5 * mm, "Karnataka State Board Social Science")
        canvas.drawRightString(A4[0] - 18 * mm, 5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "HBTitle",
            fontName=title_font,
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "HBH",
            fontName=heading_font,
            fontSize=12,
            leading=16,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "HBBody",
            fontName=body_font,
            fontSize=10,
            leading=14,
            textColor=INK,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "HBKn",
            fontName="HistoryBotKannada",
            fontSize=11,
            leading=16,
            textColor=INK,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "HBMeta",
            fontName=body_font,
            fontSize=9,
            leading=12,
            textColor=BRASS,
        )
    )

    story = []
    story.append(Paragraph(_esc(title), styles["HBTitle"]))
    lang_label = "Kannada" if language == "kn" else "English"
    story.append(Paragraph(f"Language: {lang_label}", styles["HBMeta"]))
    story.append(Paragraph("Answers are taken only from the prescribed Class 9 textbook.", styles["HBMeta"]))
    story.append(Spacer(1, 6))

    section_order = [
        ("introduction", "Introduction"),
        ("learning_objectives", "Learning objectives"),
        ("easy_english", "Easy English explanation"),
        ("simple_kannada", "Simple Kannada explanation"),
        ("historical_context", "Historical context"),
        ("important_people", "Important people"),
        ("important_terms", "Important terms"),
        ("timeline", "Timeline / events"),
        ("detailed_explanation", "Detailed explanation"),
        ("key_points", "Key points"),
        ("exam_questions", "Exam-oriented questions"),
        ("revision", "Revision"),
        ("mcqs", "Multiple-choice questions"),
    ]
    for key, heading in section_order:
        value = content.get(key)
        if not value:
            continue
        style = styles["HBKn"] if key == "simple_kannada" else styles["HBBody"]
        block = [Paragraph(_esc(heading), styles["HBH"])]
        block.extend(_flow_value(value, style, styles["HBBody"]))
        story.append(KeepTogether(block))

    if images:
        story.append(Paragraph("Textbook figures", styles["HBH"]))
        for item in images:
            path = IMAGE_ROOT / str(item.get("file_path") or "")
            if not path.is_file():
                continue
            caption = item.get("caption") or item.get("alt_text") or item.get("topic") or ""
            try:
                img = Image(str(path), width=90 * mm, height=70 * mm, kind="proportional")
            except Exception:
                continue
            story.append(img)
            story.append(Paragraph(_esc(caption), styles["HBMeta"]))

    pages = sorted(
        {
            int(item.get("textbook_page_number"))
            for item in sources
            if item.get("textbook_page_number") is not None
        }
        | {int(p) for p in (content.get("textbook_source_pages") or []) if str(p).isdigit()}
    )
    if pages:
        story.append(Paragraph("Textbook source pages", styles["HBH"]))
        joined = ", ".join(str(p) for p in pages)
        story.append(Paragraph(_esc(f"Textbook pages {joined}"), styles["HBBody"]))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="HistoryBot",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _flow_value(value, style, fallback):
    flows = []
    if isinstance(value, str):
        flows.append(Paragraph(_esc(value).replace("\n", "<br/>"), style))
        return flows
    if isinstance(value, list):
        items = []
        for entry in value:
            if isinstance(entry, str):
                items.append(ListItem(Paragraph(_esc(entry), fallback)))
            elif isinstance(entry, dict):
                text = _dict_line(entry)
                if text:
                    items.append(ListItem(Paragraph(_esc(text), fallback)))
        if items:
            flows.append(ListFlowable(items, bulletType="bullet", leftIndent=12))
        return flows
    if isinstance(value, dict):
        flows.append(Paragraph(_esc(_dict_line(value)), fallback))
    return flows


def _dict_line(entry: dict) -> str:
    if "question" in entry and "answer" in entry:
        opts = entry.get("options")
        extra = ""
        if isinstance(opts, list) and opts:
            extra = " Options: " + "; ".join(str(o) for o in opts)
        return f"Q: {entry.get('question')} {extra} A: {entry.get('answer')}"
    if "name" in entry:
        return f"{entry.get('name')}: {entry.get('note') or ''}".strip(": ")
    if "term" in entry:
        return f"{entry.get('term')}: {entry.get('meaning') or ''}".strip(": ")
    if "event" in entry:
        when = entry.get("when") or ""
        return f"{when} — {entry.get('event')}".strip(" —")
    return " ".join(str(v) for v in entry.values() if v)


def _esc(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

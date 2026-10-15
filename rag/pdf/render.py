"""ReportLab PDF for grounded E-content. Uses bundled Unicode fonts only."""

from __future__ import annotations

import os
import re
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
            keepWithNext=1,
        )
    )
    styles.add(
        ParagraphStyle(
            "HBSub",
            fontName=heading_font,
            fontSize=10.5,
            leading=14,
            textColor=NAVY,
            spaceBefore=6,
            spaceAfter=2,
            keepWithNext=1,
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
    # A note that belongs to the following text (never left alone at the bottom of a page).
    styles.add(ParagraphStyle("HBMetaNext", parent=styles["HBMeta"], keepWithNext=1))

    story = []
    story.append(Paragraph(_esc(title), styles["HBTitle"]))
    lang_label = "Kannada" if language == "kn" else "English"
    story.append(Paragraph(f"Language: {lang_label}", styles["HBMeta"]))
    story.append(
        Paragraph(
            "Textbook content comes first and cites printed page numbers. The section "
            "'Additional historical explanation' is general history added to help you understand; "
            "it is not from the textbook pages.",
            styles["HBMeta"],
        )
    )
    story.append(Spacer(1, 6))

    section_order = [
        ("introduction", "Introduction"),
        ("learning_objectives", "Learning objectives"),
        ("detailed_explanation", "Detailed explanation"),
        ("additional_explanation", "Additional historical explanation"),
        ("important_people", "Important people"),
        ("important_terms", "Important terms"),
        ("timeline", "Timeline"),
        ("main_events", "Main events"),
        ("key_points", "Key points"),
        ("exam_questions", "Exam-oriented questions"),
        ("mcqs", "Multiple-choice questions"),
        ("revision", "Revision"),
    ]
    citations = content.get("section_citations") or {}
    for key, heading in section_order:
        value = content.get(key)
        if not value:
            continue
        if key == "additional_explanation":
            story.append(Paragraph(_esc(heading), styles["HBH"]))
            story.append(Paragraph("General history, not from the textbook pages.", styles["HBMetaNext"]))
            story.extend(_flow_markdown(value, styles))
            continue
        if key == "detailed_explanation":
            story.append(Paragraph(_esc(heading), styles["HBH"]))
            story.extend(_flow_markdown(value, styles))
            cite = _cite_line(citations.get("Detailed explanation") or citations.get(heading))
            if cite:
                story.append(Paragraph(_esc(cite), styles["HBMeta"]))
            continue
        block = [Paragraph(_esc(heading), styles["HBH"])]
        block.extend(_flow_value(value, styles["HBBody"], styles["HBBody"]))
        cite_pages = citations.get(heading)
        if cite_pages:
            block.append(Paragraph(_esc(_cite_line(cite_pages)), styles["HBMeta"]))
        story.append(KeepTogether(block))

    if images:
        figures_heading = Paragraph("Figures and images", styles["HBH"])
        for item in images:
            path = IMAGE_ROOT / str(item.get("file_path") or "")
            if not path.is_file():
                continue
            caption = item.get("caption") or item.get("alt_text") or item.get("topic") or ""
            try:
                img = Image(str(path), width=90 * mm, height=70 * mm, kind="proportional")
            except Exception:
                continue
            # Image, caption and credit stay on one page.
            figure = [img, Paragraph(_esc(caption), styles["HBMeta"])]
            credit = " · ".join(
                str(part) for part in (item.get("source"), item.get("license")) if part
            )
            if credit:
                figure.append(Paragraph(_esc(credit[:400]), styles["HBMeta"]))
            figure.append(Spacer(1, 6))
            if figures_heading is not None:
                # The section heading always sits on the same page as its first figure.
                figure.insert(0, figures_heading)
                figures_heading = None
            story.append(KeepTogether(figure))

    source_lines = []
    textbook_label = "Class 9 Karnataka State Board 2026–27 textbook"
    for item in sources or []:
        if (item.get("authority") or "") == "approved_supplementary":
            continue
        if "additional" in str(item.get("citation_label") or "").lower():
            continue
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        if page is None:
            continue
        source_lines.append(f"Source: {item.get('citation_label') or textbook_label}, page {page}")
    if citations:
        story.append(Paragraph("Section page citations", styles["HBH"]))
        # (loop variable must not shadow `title`, which is the PDF's document title below)
        for section_title, pages in citations.items():
            line = _cite_line(pages)
            if line:
                story.append(Paragraph(_esc(f"{section_title} — {line}"), styles["HBBody"]))
    extra_pages = [int(p) for p in (content.get("textbook_source_pages") or []) if str(p).isdigit()]
    if extra_pages and not source_lines:
        source_lines.append(
            "Source: " + textbook_label + ", pages " + ", ".join(str(p) for p in sorted(set(extra_pages)))
        )
    if source_lines:
        story.append(Paragraph("Sources", styles["HBH"]))
        for line in source_lines:
            story.append(Paragraph(_esc(line), styles["HBBody"]))

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


_BOLD_HEADING_RE = re.compile(r"^\*\*([^*]+)\*\*:?$")
_INLINE_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")


def _inline_markup(text: str) -> str:
    """Escape text and drop markdown ** markers instead of printing asterisks.

    Plain text on purpose: the embedded body fonts have no registered bold face.
    """
    return _esc(_INLINE_BOLD_RE.sub(r"\1", text))


def _flow_markdown(text: str, styles) -> list:
    flows = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            flows.append(Paragraph("<br/>".join(_inline_markup(line) for line in paragraph), styles["HBBody"]))
            paragraph.clear()

    for line in str(text or "").strip().splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        heading, style = None, "HBSub"
        if stripped.startswith("#"):
            heading, style = stripped.lstrip("#").strip(), "HBH"
        else:
            match = _BOLD_HEADING_RE.match(stripped)
            if match:
                heading = match.group(1).strip().rstrip(":")
        if heading and len(heading) > 90:
            # A run-on "# Heading sentence sentence..." line from the model is body text, not a heading.
            paragraph.append(heading)
            continue
        if heading:
            flush()
            flows.append(Paragraph(_inline_markup(heading), styles[style]))
            continue
        paragraph.append(stripped)
    flush()
    return flows


def _cite_line(pages) -> str:
    values = []
    for page in pages or []:
        try:
            value = int(page)
        except (TypeError, ValueError):
            continue
        if value not in values:
            values.append(value)
    if not values:
        return ""
    if len(values) == 1:
        return f"Textbook page {values[0]}"
    return "Textbook pages " + ", ".join(str(page) for page in values)


def _dict_line(entry: dict) -> str:
    cite = _cite_line(entry.get("pages"))
    suffix = f" ({cite})" if cite else ""
    if "question" in entry and "answer" in entry:
        opts = entry.get("options")
        extra = ""
        if isinstance(opts, list) and opts:
            extra = " Options: " + "; ".join(str(o) for o in opts)
        qtype = entry.get("type")
        prefix = f"[{qtype}] " if qtype else ""
        return f"{prefix}Q: {entry.get('question')} {extra} A: {entry.get('answer')}{suffix}"
    if "name" in entry:
        return f"{entry.get('name')}: {entry.get('note') or ''}{suffix}".strip(": ")
    if "term" in entry:
        return f"{entry.get('term')}: {entry.get('meaning') or ''}{suffix}".strip(": ")
    if "event" in entry:
        when = entry.get("when") or ""
        return f"{when} — {entry.get('event')}{suffix}".strip(" —")
    return " ".join(str(v) for key, v in entry.items() if v and key != "pages")


def _esc(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

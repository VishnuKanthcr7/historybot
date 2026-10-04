"""Phase 20 E-content and PDF quality regression."""

from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path

from rag.engine.econtent import generate_econtent
from rag.pdf.render import render_econtent_pdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "phase20-regression.json"
LOG = ROOT / "tmp" / "phase20-eval.log"
PROGRESS = ROOT / "tmp" / "phase20-progress.jsonl"

AHOM = ("ahom", "lachit", "saraighat", "charaideo", "sukaphaa")
INTERNAL = (
    "chroma",
    "evidence pack",
    "vector database",
    "retrieved chunks",
    "chunk_id",
    "ollama",
    "according to the evidence",
)
WANTED = (
    "title",
    "introduction",
    "learning_objectives",
    "detailed_explanation",
    "important_people",
    "key_points",
    "exam_questions",
    "mcqs",
    "revision",
)

TOPICS = [
    {"id": "EC_Mughals", "topic": "Mughals", "need": ["babur", "akbar", "aurangzeb"], "forbid_ahom": True, "forbid_only_shivaji": False},
    {"id": "EC_Shivaji", "topic": "Shivaji", "need": ["shivaji"], "forbid_ahom": True},
    {"id": "EC_Marathas", "topic": "Marathas", "need": ["shivaji"], "need_any": ["peshwa", "baji", "madhav", "maratha"], "forbid_ahom": True},
    {"id": "EC_Ahom", "topic": "Ahom Dynasty", "need": ["ahom"], "ahom": True},
]


def log(msg: str) -> None:
    print(msg, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(msg.rstrip() + "\n")


def pdf_text(pdf: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return pdf.decode("latin-1", errors="ignore")
    reader = PdfReader(BytesIO(pdf))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def grade(case: dict, result: dict, elapsed: float) -> dict:
    content = result.get("content") or {}
    blob = json.dumps(content, ensure_ascii=False).lower()
    detailed = (content.get("detailed_explanation") or "").lower()
    sections = [key for key in WANTED if content.get(key)]
    omitted = [key for key in WANTED if not content.get(key)]
    if content.get("timeline"):
        sections.append("timeline")
    if content.get("important_terms"):
        sections.append("important_terms")
    reasons = []
    verdict = "PASS"
    if not result.get("grounded") or not detailed.strip():
        reasons.append("not-grounded")
        verdict = "FAIL"
    for term in case.get("need") or []:
        if term not in detailed and term not in blob:
            reasons.append(f"need:{term}")
            verdict = "FAIL"
    if case.get("need_any") and not any(term in blob for term in case["need_any"]):
        reasons.append("need-any-maratha")
        verdict = "FAIL"
    if case.get("forbid_ahom") and any(marker in detailed for marker in AHOM):
        reasons.append("ahom-contamination")
        verdict = "FAIL"
    if any(term in blob for term in INTERNAL):
        reasons.append("internal-terms")
        if verdict != "FAIL":
            verdict = "PARTIAL"
    empty = [key for key in ("detailed_explanation", "exam_questions", "mcqs", "revision") if not content.get(key)]
    if empty:
        reasons.append("empty:" + ",".join(empty))
        verdict = "FAIL"
    cites = content.get("section_citations") or {}
    if "Aurangzeb" in cites and case["topic"] == "Mughals" and not cites.get("Aurangzeb"):
        reasons.append("aurangzeb-cite-empty")
        verdict = "FAIL"
    if case["topic"] == "Mughals" and "Aurangzeb" not in (content.get("detailed_explanation") or ""):
        if verdict != "FAIL":
            verdict = "PARTIAL"
        reasons.append("aurangzeb-heading-missing")
    pack_pages = (result.get("evidence_pack") or {}).get("pages") or []
    used = content.get("textbook_source_pages") or []
    extra = [page for page in used if pack_pages and page not in pack_pages]
    if extra:
        reasons.append(f"cite-outside-pack:{extra}")
        verdict = "FAIL"
    if not cites:
        reasons.append("no-section-citations")
        if verdict != "FAIL":
            verdict = "PARTIAL"
    people = content.get("important_people") or []
    if people and any(not item.get("pages") for item in people if isinstance(item, dict)):
        reasons.append("people-missing-pages")
        if verdict != "FAIL":
            verdict = "PARTIAL"
    return {
        "id": case["id"],
        "question": case["topic"],
        "type": "ECONTENT",
        "topic": case["topic"],
        "evidence_pages": pack_pages,
        "sections_generated": sections,
        "sections_omitted": omitted,
        "citations": cites,
        "used_pages": used,
        "grounded": bool(result.get("grounded")),
        "coverage": (result.get("coverage") or {}).get("grade"),
        "generation_time": round(elapsed, 1),
        "reasons": reasons,
        "verdict": verdict,
        "pass": verdict != "FAIL",
        "keys": list(content.keys()),
    }


def pdf_grade(topic: str, result: dict) -> dict:
    content = result.get("content") or {}
    try:
        pdf = render_econtent_pdf(
            {
                "title": result.get("title") or topic,
                "language": "en",
                "content": content,
                "sources": result.get("sources") or [],
            },
            images=[],
        )
    except Exception as exc:
        return {"topic": topic, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:250], "verdict": "FAIL"}
    text = pdf_text(pdf).lower()
    issues = []
    if len(pdf) < 1000 or not pdf.startswith(b"%PDF"):
        issues.append("empty-or-not-pdf")
    if b"chunk_id" in pdf or b"C:\\\\" in pdf:
        issues.append("debug")
    if "additional school-book" in text:
        issues.append("supplement")
    if any(term in text for term in ("chroma", "evidence pack", "vector database")):
        issues.append("rag-terms")
    if "{" in text and '"title"' in text:
        issues.append("raw-json")
    if "historybot" not in text:
        issues.append("missing-brand")
    if "detailed explanation" not in text and "babur" not in text and "shivaji" not in text and "ahom" not in text:
        issues.append("missing-body")
    verdict = "FAIL" if issues else "PASS"
    return {
        "topic": topic,
        "ok": not issues,
        "bytes": len(pdf),
        "issues": issues,
        "verdict": verdict,
        "has_section_cites": "textbook page" in text or "section page" in text,
    }


def load_done() -> dict:
    done = {}
    if not PROGRESS.exists():
        return done
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            done[item.get("id")] = item
    return done


def save_row(row: dict) -> None:
    with PROGRESS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    done = load_done()
    rows = []
    pdf_rows = []
    for case in TOPICS:
        if case["id"] in done:
            rows.append(done[case["id"]])
            log("resume " + case["id"])
            continue
        log(case["id"] + " " + case["topic"])
        start = time.perf_counter()
        result = generate_econtent(case["topic"], "en")
        elapsed = time.perf_counter() - start
        row = grade(case, result, elapsed)
        pdf_row = pdf_grade(case["topic"], result) if result.get("grounded") else {"topic": case["topic"], "ok": False, "verdict": "FAIL", "issues": ["no-module"]}
        row["pdf"] = pdf_row
        if pdf_row.get("verdict") == "FAIL" and row["verdict"] != "FAIL":
            row["verdict"] = "PARTIAL"
            row["pass"] = True
            row["reasons"].append("pdf:" + ",".join(pdf_row.get("issues") or []))
        rows.append(row)
        pdf_rows.append(pdf_row)
        save_row(row)
        log(" " + row["verdict"] + " t=" + str(row["generation_time"]) + " sections=" + str(row["sections_generated"]) + " " + str(row["reasons"]))
        log("  pdf " + str(pdf_row.get("verdict")) + " " + str(pdf_row.get("bytes")) + " " + str(pdf_row.get("issues")))

    report = {
        "econtent": rows,
        "pdf": pdf_rows or [row.get("pdf") for row in rows],
        "pass": sum(1 for row in rows if row.get("verdict") == "PASS"),
        "partial": sum(1 for row in rows if row.get("verdict") == "PARTIAL"),
        "fail": sum(1 for row in rows if row.get("verdict") == "FAIL"),
        "total": len(rows),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log("wrote " + str(OUT) + " " + str(report["pass"]) + "P/" + str(report["partial"]) + "part/" + str(report["fail"]) + "F")


if __name__ == "__main__":
    main()

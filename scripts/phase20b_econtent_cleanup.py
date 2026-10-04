"""Phase 20B e-content evidence cleanup checks."""

from __future__ import annotations

import json
import time
from pathlib import Path

from rag.engine.coverage import build_coverage_plan, filter_plan
from rag.engine.econtent import (
    _is_student_sentence,
    _key_points_from_plan,
    _normalize_ocr_text,
    _people_from_plan,
    _sorted_pages,
    _terms_from_plan,
    _timeline_from_plan,
    generate_econtent,
)
from rag.engine.pack import build_evidence_pack
from rag.pdf.render import render_econtent_pdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "phase20b-regression.json"
OCR_BAD = (
    "do you know this",
    "mughals in india",
    "who established mughal do you",
    "new seven wonders",
    "e and is often listed",
)


def _mughal_plan():
    pack = build_evidence_pack("Mughals", "Mughals", "BROAD_TOPIC")
    return pack, filter_plan("Mughals", build_coverage_plan(pack.chunks))


def test_ocr_rejection() -> dict:
    junk = "MughalS IN INDIA (1526 – 1707) Babur Babur, who established Mughal Do you know this?"
    cleaned = _normalize_ocr_text(junk)
    ok = (not _is_student_sentence(junk)) and "do you know this" not in cleaned.lower()
    aur = 'e and is often listed among the new seven wonders of the word.” Aurangzeb Aurangzeb received good military training in his childhood and became a capable soldier.'
    aur_clean = _normalize_ocr_text(aur)
    ok = ok and aur_clean.lower().startswith("aurangzeb") and "seven wonders" not in aur_clean.lower()
    return {"id": "ocr_rejection", "pass": ok, "cleaned_babur": cleaned[:80], "cleaned_aurangzeb": aur_clean[:80]}


def test_page_order() -> dict:
    pages = _sorted_pages([3, 4, 5, 7, 8, 10, 9, 11, 3])
    return {"id": "page_ordering", "pass": pages == [3, 4, 5, 7, 8, 9, 10, 11], "pages": pages}


def test_plan_sections() -> dict:
    _pack, plan = _mughal_plan()
    people = {item["name"]: item for item in _people_from_plan(plan)}
    terms = {item["term"]: item for item in _terms_from_plan(plan)}
    timeline, events = _timeline_from_plan(plan)
    keys = _key_points_from_plan(plan)
    blob = json.dumps({"people": people, "terms": terms, "events": events, "keys": keys}, ensure_ascii=False).lower()
    ocr = [marker for marker in OCR_BAD if marker in blob]
    needed = ["Babur", "Akbar", "Shah Jahan", "Aurangzeb"]
    missing_people = [name for name in needed if name not in people]
    people_ok = True
    for name in needed:
        note = (people.get(name) or {}).get("note") or ""
        if not note or any(marker in note.lower() for marker in OCR_BAD):
            people_ok = False
    term_ok = True
    for term in ("Mansab", "Jagir", "Vakil", "Diwan"):
        if term in terms:
            meaning = terms[term]["meaning"].lower()
            if "duties of the king" in meaning or meaning.count(",") >= 3:
                term_ok = False
    pages_ok = all(_sorted_pages(item.get("pages")) == list(item.get("pages") or []) for item in people.values())
    events_ok = bool(events) and not any(marker in " ".join(events).lower() for marker in OCR_BAD)
    keys_ok = bool(keys) and not any(marker in " ".join(keys).lower() for marker in OCR_BAD)
    times_ok = True
    if timeline:
        years = []
        for row in timeline:
            try:
                years.append(int(str(row["when"])[:4]))
            except ValueError:
                times_ok = False
        times_ok = times_ok and years == sorted(years)
        times_ok = times_ok and not any(marker in json.dumps(timeline).lower() for marker in OCR_BAD)
    return {
        "id": "plan_cleanup",
        "pass": (not ocr) and (not missing_people) and people_ok and term_ok and pages_ok and events_ok and keys_ok and times_ok,
        "missing_people": missing_people,
        "people": {name: (people.get(name) or {}).get("note", "")[:160] for name in needed},
        "terms_present": list(terms),
        "term_meanings": {k: v["meaning"][:160] for k, v in terms.items()},
        "timeline": timeline,
        "main_events": events[:6],
        "key_points": keys,
        "ocr": ocr,
    }


def test_mughals_module() -> dict:
    start = time.perf_counter()
    result = generate_econtent("Mughals", "en")
    elapsed = time.perf_counter() - start
    content = result.get("content") or {}
    blob = json.dumps(content, ensure_ascii=False).lower()
    ocr = [marker for marker in OCR_BAD if marker in blob]
    people = {item.get("name"): item for item in content.get("important_people") or []}
    terms = {item.get("term"): item for item in content.get("important_terms") or []}
    used = content.get("textbook_source_pages") or []
    pages_ok = used == sorted(set(used))
    pdf_ok = False
    pdf_bytes = 0
    try:
        pdf = render_econtent_pdf(
            {"title": result.get("title") or "Mughals", "language": "en", "content": content, "sources": result.get("sources") or []},
            images=[],
        )
        pdf_ok = pdf.startswith(b"%PDF") and b"chunk_id" not in pdf and b"Additional school-book" not in pdf
        pdf_bytes = len(pdf)
    except Exception as exc:
        pdf_ok = False
        pdf_bytes = 0
        ocr.append(f"pdf:{type(exc).__name__}")
    revision = content.get("revision") or ""
    events = content.get("main_events") or []
    ok = (
        bool(result.get("grounded"))
        and not ocr
        and pages_ok
        and all(name in people for name in ("Babur", "Akbar", "Shah Jahan", "Aurangzeb"))
        and bool(content.get("key_points"))
        and bool(revision)
        and bool(events)
        and pdf_ok
        and "do you know this" not in blob
    )
    return {
        "id": "mughals_module",
        "pass": ok,
        "generation_time": round(elapsed, 1),
        "ocr": ocr,
        "pages": used,
        "people": {name: (people.get(name) or {}).get("note", "")[:180] for name in ("Babur", "Akbar", "Shah Jahan", "Aurangzeb")},
        "terms": {k: v.get("meaning", "")[:180] for k, v in terms.items()},
        "timeline": content.get("timeline") or [],
        "main_events": events[:6],
        "key_points": content.get("key_points") or [],
        "revision": revision[:500],
        "pdf_ok": pdf_ok,
        "pdf_bytes": pdf_bytes,
        "coverage": (result.get("coverage") or {}).get("grade"),
    }


def main() -> None:
    rows = [test_ocr_rejection(), test_page_order(), test_plan_sections(), test_mughals_module()]
    report = {
        "rows": rows,
        "pass": sum(1 for row in rows if row.get("pass")),
        "total": len(rows),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in rows:
        print(row["id"], "PASS" if row.get("pass") else "FAIL", flush=True)
    print("wrote", OUT, report["pass"], "/", report["total"], flush=True)


if __name__ == "__main__":
    main()

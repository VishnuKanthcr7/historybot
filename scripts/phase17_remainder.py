"""Finish Phase 17 remainder: B1, F3, e-content, coverage."""

from __future__ import annotations

import json
from pathlib import Path

from rag.engine.answer import answer_question
from rag.engine.classify import classify_question_type
from rag.engine.econtent import generate_econtent
from rag.engine.pack import build_evidence_pack
from rag.vectorstore.retrieve import retrieve_primary

OUT = Path(__file__).resolve().parents[1] / "tmp" / "phase17-remainder.json"


def cited(res: dict) -> list[int]:
    pages = []
    for item in res.get("sources") or []:
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        if page is not None:
            pages.append(int(page))
    return sorted(set(pages))


def pages_of(hits: list[dict]) -> list[int]:
    return sorted(
        {
            int(item.get("printed_page_number") or item.get("textbook_page_number"))
            for item in hits
            if item.get("printed_page_number") is not None or item.get("textbook_page_number") is not None
        }
    )


def main() -> None:
    out: dict = {}
    print("B1", flush=True)
    result = answer_question("Explain the Mughals in detail.", "en")
    low = (result.get("answer") or "").lower()
    print(
        " names",
        "akbar" in low,
        "shah" in low,
        "aurangzeb" in low,
        "bab" in low,
        flush=True,
    )
    print(" pack", (result.get("evidence_pack") or {}).get("pages"), "cite", cited(result), flush=True)
    out["B1"] = {
        "answer": (result.get("answer") or "")[:1500],
        "pack": result.get("evidence_pack"),
        "cited": cited(result),
        "fallback": result.get("fallback_used"),
        "names": {
            "akbar": "akbar" in low,
            "shah": "shah" in low,
            "aurangzeb": "aurangzeb" in low,
            "babur": "babur" in low or "babar" in low,
        },
    }

    print("F3", flush=True)
    first = answer_question("Tell me about the Mughals.", "en")
    second = answer_question(
        "Tell me more about Akbar.",
        "en",
        history=[
            {"role": "user", "content": "Tell me about the Mughals."},
            {"role": "assistant", "content": first.get("answer") or ""},
        ],
    )
    print(
        " akbar",
        "akbar" in (second.get("answer") or "").lower(),
        "type",
        second.get("question_type"),
        "topic",
        second.get("resolved_topic"),
        flush=True,
    )
    out["F3"] = {
        "type": second.get("question_type"),
        "topic": second.get("resolved_topic"),
        "answer": (second.get("answer") or "")[:900],
        "cited": cited(second),
        "pack": second.get("evidence_pack"),
        "pass": "akbar" in (second.get("answer") or "").lower() and "shivaji" not in (second.get("answer") or "").lower(),
    }

    for topic in ("Shivaji", "Mughals", "Marathas"):
        print("ECONTENT", topic, flush=True)
        result = generate_econtent(topic, "en")
        content = result.get("content") or {}
        keys = list(content.keys()) if isinstance(content, dict) else []
        print(" grounded", result.get("grounded"), "keys", keys[:12], "pages", cited(result), flush=True)
        out[topic] = {
            "grounded": result.get("grounded"),
            "keys": keys,
            "pages": cited(result),
            "pack": result.get("evidence_pack"),
            "title": result.get("title"),
            "pass": bool(result.get("grounded")) and bool(content),
        }

    for label, question, expected in (
        ("mughals", "Explain the Mughals in detail.", {3, 5, 6, 8, 9, 10}),
        ("shivaji_admin", "Explain Shivaji's administration.", {14}),
        ("marathas", "Explain the Marathas in detail.", {12, 13, 14, 15}),
    ):
        qtype = classify_question_type(question)
        hits = retrieve_primary(question, top_k=16, language="en")
        pack = build_evidence_pack(question, question, qtype, hits)
        print("COV", label, pack.pages, "covers", expected.issubset(set(pack.pages)), flush=True)
        out[f"cov_{label}"] = {
            "retrieved": pages_of(hits),
            "pack": pack.pages,
            "expected": sorted(expected),
            "covers": expected.issubset(set(pack.pages)),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()

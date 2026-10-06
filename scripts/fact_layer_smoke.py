"""Corpus smoke test for the fact index. Uses primary textbook chunks only."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.facts import compile_question, corpus_index, try_fact_answer
from rag.engine.topic_map import load_primary_chunks


CASES = [
    ("father", "Who was Babur's father?", "supported", ["umar", "babur"]),
    ("son", "Whose son was Baji Rao I?", "supported", ["balaji", "baji"]),
    ("age", "At what age did Akbar assume power?", "supported", ["14"]),
    ("birthplace", "Where was Akbar born?", "supported", ["amarkot"]),
    ("birthplace-2", "Where was Shivaji born?", "supported", ["shivneri"]),
    ("appointment", "Who was appointed as Peshwa after Balaji Vishwanath?", "supported", ["baji", "peshwa"]),
    ("quantity", "How much compensation did Baji Rao receive?", "supported", ["50 lakh"]),
    ("location", "Where did Nizam-ul-Mulk lose?", "supported", ["bhopal"]),
    ("outcome", "What was the outcome near Bhopal?", "supported", ["maratha"]),
    ("definition", "What was Din-e-Ilahi?", "supported", ["din", "akbar"]),
    ("list", "Which ministers assisted Akbar?", "supported", ["vakil", "diwan"]),
    ("chronology", "Who came after Shivaji?", "supported", ["sambhaji"]),
    ("rephrase", "Who was the father of Humayun?", "supported", ["babur"]),
    ("false-not-stated", "Did Akbar appoint Baji Rao?", "not_stated", ["does not state"]),
    ("false-contradict", "Did Baji Rao lose near Bhopal?", "contradicted", ["does not state", "bhopal"]),
    ("unknown", "Who was the father of Zorblatt?", "not_stated", ["does not state"]),
    ("march", "Who tried to march towards Delhi?", "supported", ["nizam", "delhi"]),
]


def main() -> int:
    failed = []
    chunks = list(load_primary_chunks())
    def _flat(text: str) -> str:
        cleaned = re.sub(r"@?KTBS\s*NOT\s+TO\s+BE\s+REPUBLISHED|@KTBS", " ", text or "", flags=re.I)
        cleaned = (
            cleaned.replace("\u2019", "'")
            .replace("\u2018", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\ufffd", " ")
        )
        return re.sub(r"\s+", " ", cleaned).lower()

    by_id = {item.get("chunk_id"): _flat(item.get("text") or "") for item in chunks}
    index = corpus_index()
    print(f"chunks {len(chunks)} facts {len(index.facts)}")
    missing = [
        fact.fact_id
        for fact in index.facts
        if _flat(fact.span) not in (by_id.get(fact.chunk_id) or "")
        and _flat(fact.sentence) not in (by_id.get(fact.chunk_id) or "")
    ]
    ok = bool(index.facts) and not missing and all(fact.printed_page and fact.chunk_id and fact.source_id for fact in index.facts)
    print(("PASS" if ok else "FAIL"), "integrity", f"missing={len(missing)}")
    if not ok:
        failed.append("integrity")

    broad = compile_question("Tell me about Baji Rao") is None and compile_question("Explain the Marathas") is None
    print(("PASS" if broad else "FAIL"), "broad-fallback")
    if not broad:
        failed.append("broad-fallback")

    for case_id, question, status, needles in CASES:
        result = try_fact_answer(question, index=index)
        text = ((result or {}).get("answer") or "").lower()
        got = None if result is None else result.get("fact_status")
        good = got == status and all(needle in text for needle in needles)
        if status != "not_stated" and not (result or {}).get("sources"):
            good = False
        print(("PASS" if good else "FAIL"), case_id, got)
        if not good:
            print(" ", text[:220].replace("\n", " "))
            failed.append(case_id)
    print(f"\n{len(failed)} failed" if failed else "\nALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

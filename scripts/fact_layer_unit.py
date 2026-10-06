"""Generic fact-layer unit tests. Synthetic names only; no corpus and no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.facts import compile_question, index_chunks, try_fact_answer

CHUNK = {
    "chunk_id": "synthetic-1",
    "source_id": "synthetic",
    "source_type": "primary_textbook",
    "printed_page_number": 4,
    "citation_label": "Synthetic textbook",
    "text": (
        "PersonA was the ruler of PlaceC. "
        "PersonB was the father of PersonA. "
        "After the death of PersonB, PersonA was appointed as OfficeD. "
        "PersonA succeeded PersonB. "
        "PersonA assumed power at the age of 19. "
        "PersonA was born at PlaceC. "
        "PersonA received 50 lakh rupees as war compensation. "
        "This event happened in 1526. "
        "PersonA abolished TaxF. "
        "Near PlaceC, PersonB lost to GroupE. "
        "These payments were called TermG. "
        "PersonA's ministers were Mone, Mtwo, Mthree, and Mfour. "
        "PersonA ruled the valley. Later PersonB succeeded him. "
        "GroupE defeated PersonB in the open field. "
        "PersonB was defeated by GroupE in the open field. "
        "The record places PersonA and PersonB side by side."
    ),
}


def _answer(question: str) -> dict:
    index = index_chunks([CHUNK])
    result = try_fact_answer(question, index=index)
    return result or {"answer": "", "fact_status": "fallback"}


def main() -> int:
    failed = []

    def check(case_id: str, ok: bool, detail: str = "") -> None:
        print(("PASS" if ok else "FAIL"), case_id, detail)
        if not ok:
            failed.append(case_id)

    index = index_chunks([CHUNK])
    parents = [fact for fact in index.facts if fact.predicate == "parent"]
    check(
        "parent-direction",
        any(
            fact.roles["parent"].norm == "personb" and fact.roles["child"].norm == "persona"
            for fact in parents
        )
        and not any(
            fact.roles["parent"].norm == "persona" and fact.roles["child"].norm == "personb"
            for fact in parents
        ),
    )
    check(
        "cooccurrence-no-link",
        not any(
            {fact.roles.get("agent", None) and fact.roles["agent"].norm, fact.roles.get("patient", None) and fact.roles["patient"].norm}
            == {"persona", "personb"}
            for fact in index.facts
        ),
    )
    check(
        "span-inside-chunk",
        all(fact.span.lower() in CHUNK["text"].lower() or fact.sentence.lower() in CHUNK["text"].lower() for fact in index.facts),
    )
    check("broad-fallback", compile_question("Explain everything about PersonA") is None)
    check("tell-me-fallback", compile_question("Tell me about PersonA") is None)

    cases = [
        ("identity", "Was PersonA the ruler of PlaceC?", "supported", "ruler of placec"),
        ("parent", "Who was the father of PersonA?", "supported", "personb"),
        ("child", "Who was the son of PersonB?", "supported", "persona"),
        ("not-swapped", "Who was the father of PersonB?", "not_stated", "does not state"),
        ("appointment", "Who was appointed as OfficeD after PersonB?", "supported", "persona"),
        ("age", "At what age did PersonA assume power?", "supported", "19"),
        ("birthplace", "Where was PersonA born?", "supported", "placec"),
        ("amount", "How much compensation did PersonA receive?", "supported", "50 lakh rupees"),
        ("location", "Where did PersonB lose?", "supported", "placec"),
        ("outcome", "What was the outcome near PlaceC?", "supported", "groupe"),
        ("action", "Which tax did PersonA abolish?", "supported", "taxf"),
        ("definition", "What is TermG?", "supported", "termg"),
        ("list", "Which ministers assisted PersonA?", "supported", "mone"),
        ("chronology", "Who came after PersonA?", "supported", "personb"),
        ("false-not-stated", "Did PersonZ appoint PersonA?", "not_stated", "does not state"),
        ("false-contradict", "Did PersonA lose near PlaceC?", "contradicted", "personb"),
        ("false-identity", "Was PersonA a member of GroupE?", "contradicted", "does not state"),
        ("unknown", "Who was the father of Zorblatt?", "not_stated", "does not state"),
        ("rephrase", "Who was PersonA's parent?", "supported", "personb"),
        ("passive", "Was PersonB defeated by GroupE?", "supported", "groupe"),
        ("active", "Did GroupE defeat PersonB?", "supported", "personb"),
    ]
    for case_id, question, status, needle in cases:
        result = _answer(question)
        text = (result.get("answer") or "").lower()
        ok = result.get("fact_status") == status and needle in text
        check(case_id, ok, f"status={result.get('fact_status')} text={text[:180]!r}")

    list_answer = _answer("Which ministers assisted PersonA?")["answer"].lower()
    check("list-members", all(name in list_answer for name in ("mone", "mtwo", "mthree", "mfour")))
    passive = _answer("Was PersonB defeated by GroupE?")
    active = _answer("Did GroupE defeat PersonB?")
    check(
        "active-passive-same-roles",
        passive.get("fact_status") == "supported" and active.get("fact_status") == "supported",
    )
    print(f"\n{len(failed)} failed" if failed else "\nALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generic fact-layer unit tests. Synthetic names only; no corpus and no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.facts import compile_question, corpus_index, index_chunks, try_fact_answer

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

    def lead(question: str) -> str:
        return (_answer(question).get("answer") or "").split("\n", 1)[0].strip().rstrip(".")

    check("parent-lead", lead("Who was the father of PersonA?") == "PersonB")
    check("child-lead", lead("Who was the son of PersonB?") == "PersonA")
    check("chronology-lead", lead("Who came after PersonA?") == "PersonB")

    list_answer = _answer("Which ministers assisted PersonA?")["answer"].lower()
    check("list-members", all(name in list_answer for name in ("mone", "mtwo", "mthree", "mfour")))
    passive = _answer("Was PersonB defeated by GroupE?")
    active = _answer("Did GroupE defeat PersonB?")
    check(
        "active-passive-same-roles",
        passive.get("fact_status") == "supported" and active.get("fact_status") == "supported",
    )

    def indexed(text: str):
        return index_chunks(
            [
                {
                    "chunk_id": "slot",
                    "source_id": "synthetic",
                    "source_type": "primary_textbook",
                    "printed_page_number": 1,
                    "citation_label": "Synthetic textbook",
                    "text": text,
                }
            ]
        ).facts

    def role_text(facts) -> list[str]:
        return [span.text for fact in facts for span in fact.roles.values()]

    kept = indexed("PersonA defeated PersonB in the open field.")
    check(
        "entity-in-sentence",
        any(
            fact.predicate == "defeated"
            and fact.roles["agent"].norm == "persona"
            and fact.roles["patient"].norm == "personb"
            for fact in kept
        ),
    )
    place_facts = indexed("PlaceC was his capital. He defeated PersonB in the open field.")
    check(
        "place-not-person",
        not any(span.norm == "placec" for fact in place_facts for span in fact.roles.values()),
    )
    heading_facts = indexed("NOTES IN REGION. He defeated PersonB in the open field.")
    check(
        "heading-not-person",
        not any(
            token in span.norm.split()
            for fact in heading_facts
            for span in fact.roles.values()
            for token in ("notes", "region")
        ),
    )
    ocr_facts = indexed("Do you know this? PersonA established a dynasty in the valley.")
    check(
        "ocr-fragment-rejected",
        not any("know" in span.norm for fact in ocr_facts for span in fact.roles.values())
        and any(
            fact.predicate == "established" and fact.roles["agent"].norm == "persona" for fact in ocr_facts
        ),
    )
    doubled = indexed("PersonA PersonA was the father of PersonB.")
    check(
        "doubled-name-rejected",
        not any(span.text.lower() == "persona persona" for fact in doubled for span in fact.roles.values())
        and any(
            fact.predicate == "parent"
            and fact.roles["parent"].norm == "persona"
            and fact.roles["child"].norm == "personb"
            for fact in doubled
        ),
    )
    gap = indexed("PersonA ruled the valley. The cities of WestC grew quickly. He defeated PersonB.")
    check(
        "pronoun-not-promoted",
        not any(
            fact.predicate == "defeated"
            and fact.roles.get("agent") is not None
            and fact.roles["agent"].norm == "persona"
            for fact in gap
        ),
    )
    father = indexed("PersonB was the father of PersonA.")
    check(
        "father-son-remains",
        any(
            fact.predicate == "parent"
            and fact.roles["parent"].norm == "personb"
            and fact.roles["child"].norm == "persona"
            for fact in father
        ),
    )
    built = index_chunks(
        [
            {
                "chunk_id": "built",
                "source_id": "synthetic",
                "source_type": "primary_textbook",
                "printed_page_number": 6,
                "citation_label": "Synthetic textbook",
                "text": (
                    "PersonA built MonumentOne. "
                    "PersonA built MonumentTwo. "
                    "PersonA built MonumentThree. "
                    "PersonA built MonumentFour."
                ),
            }
        ]
    )
    built_answer = (try_fact_answer("What did PersonA build?", index=built) or {}).get("answer") or ""
    built_norm = built_answer.lower()
    check(
        "build-object-surfaced",
        "monumentfour" in built_norm
        and "persona built monumentfour" in built_norm
        and "page 6" in built_norm,
    )
    who_built = (try_fact_answer("Who built MonumentFour?", index=built) or {})
    check(
        "who-built-unchanged",
        who_built.get("fact_status") == "supported" and "persona" in (who_built.get("answer") or "").lower(),
    )

    successor = indexed("PersonA succeeded PersonB.")
    check(
        "successor-remains",
        any(
            fact.predicate == "succeeded"
            and fact.roles["later"].norm == "persona"
            and fact.roles["earlier"].norm == "personb"
            for fact in successor
        ),
    )

    compiled = compile_question("Was PersonB the father of PersonA?")
    check(
        "yesno-compiles-as-parent",
        compiled is not None
        and compiled.act == "yesno"
        and compiled.predicate == "parent"
        and compiled.binds.get("parent") == "personb"
        and compiled.binds.get("child") == "persona",
    )
    who_parent = compile_question("Who was the father of PersonA?")
    check(
        "who-parent-unchanged",
        who_parent is not None and who_parent.act == "wh" and who_parent.predicate == "parent" and who_parent.open_role == "parent",
    )

    synthetic = index_chunks([CHUNK])

    def status_of(question: str, index=None) -> str:
        result = try_fact_answer(question, index=synthetic if index is None else index)
        return "fallback" if result is None else str(result.get("fact_status") or "")

    check("yesno-father-supported", status_of("Was PersonB the father of PersonA?") == "supported")
    check("yesno-son-supported", status_of("Was PersonA the son of PersonB?") == "supported")
    check("yesno-father-contradicted", status_of("Was PersonA the father of PersonB?") == "contradicted")
    check("yesno-son-contradicted", status_of("Was PersonB the son of PersonA?") == "contradicted")
    check("yesno-father-not-stated", status_of("Was PersonZ the father of PersonA?") == "not_stated")
    check("yesno-defeat-contradicted", status_of("Did PersonB defeat GroupE?") == "contradicted")
    check("yesno-defeat-not-stated", status_of("Did PersonZ defeat PersonB?") == "not_stated")
    check("yesno-office-supported", status_of("Was PersonA appointed as OfficeD?") == "supported")
    check("yesno-office-not-stated", status_of("Was PersonZ appointed as OfficeD?") == "not_stated")

    directed = index_chunks(
        [
            {
                "chunk_id": "proposition",
                "source_id": "synthetic",
                "source_type": "primary_textbook",
                "printed_page_number": 2,
                "citation_label": "Synthetic textbook",
                "text": "PersonA succeeded PersonB. PersonC defeated PersonD. PersonE appointed PersonA as OfficeD.",
            }
        ]
    )

    def directed_status(question: str) -> str:
        return status_of(question, directed)

    check("yesno-successor-supported", directed_status("Was PersonA the successor of PersonB?") == "supported")
    check("yesno-successor-contradicted", directed_status("Was PersonB the successor of PersonA?") == "contradicted")
    check("yesno-successor-not-stated", directed_status("Was PersonZ the successor of PersonA?") == "not_stated")
    check("yesno-predecessor-supported", directed_status("Was PersonB the predecessor of PersonA?") == "supported")
    check("yesno-predecessor-contradicted", directed_status("Was PersonA the predecessor of PersonB?") == "contradicted")
    check("yesno-defeat-supported", directed_status("Did PersonC defeat PersonD?") == "supported")
    check("yesno-defeat-reversed", directed_status("Did PersonD defeat PersonC?") == "contradicted")
    check("yesno-appoint-supported", directed_status("Did PersonE appoint PersonA?") == "supported")
    check("yesno-appoint-contradicted", directed_status("Did PersonA appoint PersonE?") == "contradicted")

    def usable(span) -> bool:
        return span is not None and span.text and 1 <= len(span.text.split()) <= 6 and "?" not in span.text

    def has_swap(index, predicate, left_role, left_norm, right_role, right_norm) -> bool:
        for fact in index.facts:
            if fact.predicate != predicate and not (
                predicate in {"after", "succeeded"} and fact.predicate in {"after", "succeeded"}
            ):
                continue
            left = fact.roles.get(left_role)
            right = fact.roles.get(right_role)
            if left is not None and right is not None and left.norm == left_norm and right.norm == right_norm:
                return True
        return False

    corpus = corpus_index()
    parent_fact = next(
        (
            fact
            for fact in corpus.facts
            if fact.predicate == "parent"
            and usable(fact.roles.get("parent"))
            and usable(fact.roles.get("child"))
            and fact.roles.get("kin") is not None
            and fact.roles["kin"].norm == "father"
            and not has_swap(
                corpus,
                "parent",
                "parent",
                fact.roles["child"].norm,
                "child",
                fact.roles["parent"].norm,
            )
        ),
        None,
    )
    check("corpus-parent-found", parent_fact is not None)
    if parent_fact is not None:
        parent_name = parent_fact.roles["parent"].text
        child_name = parent_fact.roles["child"].text
        check(
            "corpus-father-supported",
            status_of(f"Was {parent_name} the father of {child_name}?", corpus) == "supported",
        )
        check(
            "corpus-father-contradicted",
            status_of(f"Was {child_name} the father of {parent_name}?", corpus) == "contradicted",
        )
        check(
            "corpus-son-supported",
            status_of(f"Was {child_name} the son of {parent_name}?", corpus) == "supported",
        )
        check(
            "corpus-father-not-stated",
            status_of(f"Was Zorblattqx the father of {child_name}?", corpus) == "not_stated",
        )
    succession_fact = next(
        (
            fact
            for fact in corpus.facts
            if fact.predicate in {"after", "succeeded"}
            and usable(fact.roles.get("earlier"))
            and usable(fact.roles.get("later"))
            and not has_swap(
                corpus,
                "succeeded",
                "earlier",
                fact.roles["later"].norm,
                "later",
                fact.roles["earlier"].norm,
            )
        ),
        None,
    )
    check("corpus-successor-found", succession_fact is not None)
    if succession_fact is not None:
        earlier_name = succession_fact.roles["earlier"].text
        later_name = succession_fact.roles["later"].text
        check(
            "corpus-successor-supported",
            status_of(f"Was {later_name} the successor of {earlier_name}?", corpus) == "supported",
        )
        check(
            "corpus-successor-contradicted",
            status_of(f"Was {earlier_name} the successor of {later_name}?", corpus) == "contradicted",
        )
        check(
            "corpus-successor-not-stated",
            status_of(f"Was Zorblattqx the successor of {earlier_name}?", corpus) == "not_stated",
        )
    defeat_fact = next(
        (
            fact
            for fact in corpus.facts
            if fact.predicate == "defeated"
            and usable(fact.roles.get("agent"))
            and usable(fact.roles.get("patient"))
            and not has_swap(
                corpus,
                "defeated",
                "agent",
                fact.roles["patient"].norm,
                "patient",
                fact.roles["agent"].norm,
            )
        ),
        None,
    )
    check("corpus-defeat-found", defeat_fact is not None)
    if defeat_fact is not None:
        winner = defeat_fact.roles["agent"].text
        loser = defeat_fact.roles["patient"].text
        check("corpus-defeat-supported", status_of(f"Did {winner} defeat {loser}?", corpus) == "supported")
        check("corpus-defeat-contradicted", status_of(f"Did {loser} defeat {winner}?", corpus) == "contradicted")
        check("corpus-defeat-not-stated", status_of(f"Did Zorblattqx defeat {loser}?", corpus) == "not_stated")
    office_fact = next(
        (
            fact
            for fact in corpus.facts
            if fact.predicate == "appointed_as"
            and usable(fact.roles.get("patient"))
            and usable(fact.roles.get("office"))
        ),
        None,
    )
    check("corpus-office-found", office_fact is not None)
    if office_fact is not None:
        appointee = office_fact.roles["patient"].text
        office = office_fact.roles["office"].text
        check(
            "corpus-office-supported",
            status_of(f"Was {appointee} appointed as {office}?", corpus) == "supported",
        )
        check(
            "corpus-office-not-stated",
            status_of(f"Was Zorblattqx appointed as {office}?", corpus) == "not_stated",
        )
        agent = office_fact.roles.get("agent")
        if usable(agent) and not has_swap(corpus, "appointed_as", "agent", office_fact.roles["patient"].norm, "patient", agent.norm):
            check(
                "corpus-appoint-supported",
                status_of(f"Did {agent.text} appoint {appointee}?", corpus) == "supported",
            )
            check(
                "corpus-appoint-contradicted",
                status_of(f"Did {appointee} appoint {agent.text}?", corpus) == "contradicted",
            )
    print(f"\n{len(failed)} failed" if failed else "\nALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

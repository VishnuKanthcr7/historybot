"""Dynamic planner regression. Synthetic names exercise the mechanism.

Corpus questions at the end check the same mechanism on the textbook index.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.facts import (
    NOT_STATED,
    _expand_pronouns,
    compile_question,
    corpus_index,
    index_chunks,
    try_fact_answer,
)
from rag.engine.planner import AMBIGUOUS, TOO_DEEP, build_plan, try_planned_answer

CHUNK = {
    "chunk_id": "plan-1",
    "source_id": "synthetic",
    "source_type": "primary_textbook",
    "printed_page_number": 4,
    "citation_label": "Synthetic textbook",
    "text": (
        "PersonC was the father of PersonB. "
        "PersonB was the father of PersonA. "
        "After the death of PersonE, PersonA was appointed as OfficeD. "
        "PersonA succeeded PersonE. "
        "PersonA built MonumentOne. "
        "GroupE defeated PersonB. "
        "PersonA and PersonB attended the same court."
    ),
}
AMBIGUOUS_CHUNK = {
    "chunk_id": "plan-2",
    "source_id": "synthetic",
    "source_type": "primary_textbook",
    "printed_page_number": 5,
    "citation_label": "Synthetic textbook",
    "text": (
        "PersonB was the father of PersonA. "
        "PersonC was the father of PersonF. "
        "PersonA was appointed as OfficeD. "
        "PersonF was appointed as OfficeD."
    ),
}


def _first(answer: str) -> str:
    return (answer or "").strip().split("\n", 1)[0].strip()


def main() -> int:
    failed = []

    def check(case_id: str, ok: bool, detail: str = "") -> None:
        print(("PASS" if ok else "FAIL"), case_id, detail)
        if not ok:
            failed.append(case_id)

    index = index_chunks([CHUNK])
    ambiguous = index_chunks([AMBIGUOUS_CHUNK])

    def planned(question: str, history=None, fact_index=None):
        return try_planned_answer(question, history, fact_index or index) or {}

    def fact(question: str, history=None, fact_index=None):
        return try_fact_answer(question, history, fact_index or index) or {}

    direct = fact("Who was the father of PersonA?")
    check("A-direct", direct.get("fact_status") == "supported" and _first(direct.get("answer")) == "PersonB.")
    check("A-not-multihop", build_plan("Who was the father of PersonA?") is None and planned("Who was the father of PersonA?") == {})

    check(
        "B-reverse",
        fact("Who was the son of PersonB?").get("fact_status") == "supported"
        and _first(fact("Who was the son of PersonB?").get("answer")) == "PersonA.",
    )
    yes = fact("Was PersonB the father of PersonA?")
    check("C-yes", yes.get("fact_status") == "supported" and (yes.get("answer") or "").startswith("Yes."))
    no = fact("Was PersonA the father of PersonB?")
    check("D-no", no.get("fact_status") == "contradicted" and (no.get("answer") or "").startswith("No."))
    missing = fact("Was PersonZ the father of PersonA?")
    check("E-not-stated", missing.get("fact_status") == "not_stated" and missing.get("answer") == NOT_STATED)
    built = fact("Did PersonA build MonumentOne?")
    check(
        "F-built",
        fact("Did PersonA construct MonumentOne?").get("fact_status") == "supported"
        and (built.get("answer") or "").startswith("Yes. PersonA built MonumentOne."),
    )
    check(
        "G-appointment",
        "persona" in (fact("Who was appointed as OfficeD after PersonE?").get("answer") or "").lower()
        and fact("Who was appointed as OfficeD after PersonE?").get("fact_status") == "supported",
    )
    check(
        "H-successor",
        fact("Who succeeded PersonE?").get("fact_status") == "supported"
        and _first(fact("Who succeeded PersonE?").get("answer")) == "PersonA.",
    )
    check("I-father-son", direct.get("fact_status") == "supported" and "personb was the father of persona" in (direct.get("answer") or "").lower())

    two = planned("Who was the father of the person who was appointed as OfficeD after PersonE?")
    two_first = _first(two.get("answer"))
    check(
        "J-two-hop",
        two.get("fact_status") == "supported" and two_first == "PersonB." and "page 4" in (two.get("answer") or "").lower(),
    )
    check("L-intermediate-not-final", two_first != "PersonA." and "persona" in (two.get("answer") or "").lower())
    three = planned("Who was the father of the father of the person who succeeded PersonE?")
    check("K-three-hop", three.get("fact_status") == "supported" and _first(three.get("answer")) == "PersonC.")
    chain = build_plan("Who was the father of the father of the person who succeeded PersonE?")
    check("L-plan-binds-previous", bool(chain) and chain["steps"][1]["binds_previous"] and chain["steps"][2]["binds_previous"])
    second = planned("Who was the son of the person who was appointed as OfficeD after PersonE?")
    check(
        "M-unsupported-second",
        second.get("answer") == NOT_STATED and "persona" not in (second.get("answer") or "").lower(),
    )
    many = planned("Who was the father of the person who was appointed as OfficeD?", fact_index=ambiguous)
    check("N-ambiguity", many.get("answer") == AMBIGUOUS and "persona" not in (many.get("answer") or "").lower())

    history = [
        {"role": "user", "content": "Who succeeded PersonE?"},
        {"role": "assistant", "content": fact("Who succeeded PersonE?").get("answer")},
    ]
    follow = fact("Who was his father?", history)
    check("O-follow-up", follow.get("fact_status") == "supported" and _first(follow.get("answer")) == "PersonB.")
    switched = [
        {"role": "user", "content": "Who succeeded PersonE?"},
        {"role": "assistant", "content": "PersonA.\n\nPersonA succeeded PersonE."},
        {"role": "user", "content": "Tell me about PersonC."},
    ]
    topic = fact("Who was his father?", switched)
    check(
        "P-topic-switch",
        topic.get("answer") == NOT_STATED and "personb" not in (topic.get("answer") or "").lower(),
    )
    check("Q-stale-entity-dropped", _first(topic.get("answer")) != "PersonB.")

    check("R-explanation-not-planned", build_plan("Explain the administration of PersonA") is None)
    check("S-why-not-planned", build_plan("Why was PersonA important?") is None)
    check("T-how-not-planned", build_plan("How did PersonA govern?") is None)
    check("U-comparison-not-planned", build_plan("Compare PersonA and PersonB") is None)
    check("V-list-not-forced", build_plan("List the achievements of PersonA") is None)
    buildings = fact("Which buildings did PersonA build?")
    check(
        "V-buildings",
        buildings.get("fact_status") == "supported" and "monumentone" in (buildings.get("answer") or "").lower(),
    )
    check(
        "W-chronology",
        fact("Who came after PersonE?").get("fact_status") == "supported"
        and _first(fact("Who came after PersonE?").get("answer")) == "PersonA.",
    )
    check("X-quantity-not-planned", build_plan("How much compensation did PersonA receive?") is None)
    check("Y-mcq-not-planned", build_plan("Give me mcqs about PersonA") is None)
    check("Z-econtent-not-planned", build_plan("Create a learning module on PersonA") is None)

    deep = planned("Who was the father of the son of the father of the son of PersonC?")
    check("max-hops", deep.get("answer") == TOO_DEEP and "person" not in (deep.get("answer") or "").lower())
    cooccur = planned("Who was the father of the person who attended the same court?")
    check("cooccurrence-not-proof", cooccur.get("answer") == NOT_STATED)
    defeat = planned("Who was the father of the person who defeated PersonB?")
    check("defeat-hop-not-intermediate", defeat.get("answer") == NOT_STATED and "groupe" not in (defeat.get("answer") or "").lower())
    it_yes = planned("Was it MonumentOne?", [{"role": "user", "content": "What did PersonA build?"}])
    check(
        "it-follow-up",
        it_yes.get("fact_status") == "supported" and (it_yes.get("answer") or "").startswith("Yes. PersonA built MonumentOne."),
    )
    it_no = planned("Was it MonumentZ?", [{"role": "user", "content": "What did PersonA build?"}])
    check("it-not-stated", it_no.get("answer") == NOT_STATED)
    pages = {row.get("printed_page_number") for row in two.get("sources") or []}
    check("cited-page-matches-evidence", pages == {4})

    corpus = corpus_index()

    def corpus_fact(question, history=None):
        return try_fact_answer(question, history, corpus) or {}

    def corpus_plan(question, history=None):
        return try_planned_answer(question, history, corpus) or {}

    father = corpus_fact("Who was the father of Baji Rao I?")
    check(
        "corpus-father",
        build_plan("Who was the father of Baji Rao I?") is None
        and father.get("fact_status") == "supported"
        and _first(father.get("answer")) == "Balaji Vishwanath.",
    )
    son_yes = corpus_fact("Was Baji Rao I the son of Balaji Vishwanath?")
    check("corpus-yes", son_yes.get("fact_status") == "supported" and (son_yes.get("answer") or "").startswith("Yes. Baji Rao I was the son of Balaji Vishwanath."))
    son_no = corpus_fact("Was Balaji Vishwanath the son of Baji Rao I?")
    check("corpus-no", son_no.get("fact_status") == "contradicted" and (son_no.get("answer") or "").startswith("No."))
    diwan = corpus_fact("Did Shah Jahan build Diwan-i-Khas?")
    construct = corpus_fact("Did Shah Jahan construct Diwan-i-Khas?")
    check(
        "corpus-build",
        diwan.get("fact_status") == "supported"
        and (diwan.get("answer") or "").startswith("Yes. Shah Jahan built Diwan-i-Khas.")
        and construct.get("fact_status") == "supported"
        and (construct.get("answer") or "").startswith("Yes. Shah Jahan built Diwan-i-Khas."),
    )
    check("corpus-unknown-build", corpus_fact("Did PersonZ build MonumentZ?").get("answer") == NOT_STATED)
    successor = corpus_fact("Who succeeded Shivaji?")
    check("corpus-successor", successor.get("fact_status") == "supported" and _first(successor.get("answer")) == "Sambhaji.")

    appointed = corpus_plan("Who was the father of the person who was appointed as Peshwa after Balaji Vishwanath?")
    index = corpus_index()
    appointees = [
        fact.roles["patient"].text
        for fact in index.facts
        if fact.predicate == "appointed_as"
        and fact.roles.get("office") is not None
        and fact.roles["office"].norm == "peshwa"
        and fact.roles.get("patient") is not None
        and "appointed" in fact.sentence.lower()
        and "balaji vishwanath" in fact.sentence.lower()
    ]
    appointee = appointees[0] if len(appointees) == 1 else ""
    father_of_appointee = _first(corpus_fact(f"Who was the father of {appointee}?").get("answer")) if appointee else ""
    check(
        "corpus-two-hop-father",
        appointed.get("fact_status") == "supported"
        and _first(appointed.get("answer")) == father_of_appointee
        and _first(appointed.get("answer")) != f"{appointee}."
        and _first(appointed.get("answer")) == "Balaji Vishwanath.",
    )
    became = corpus_plan("Who was the son of the person who became Peshwa after Balaji Vishwanath?")
    check("corpus-son-not-intermediate", became.get("answer") == NOT_STATED)

    succeeded_father = corpus_plan("Who was the father of the person who succeeded Shivaji?")
    successor_name = _first(successor.get("answer")).rstrip(".")
    father_of_successor = _first(corpus_fact(f"Who was the father of {successor_name}?").get("answer"))
    check(
        "corpus-successor-father",
        succeeded_father.get("fact_status") == "supported"
        and _first(succeeded_father.get("answer")) == father_of_successor
        and _first(succeeded_father.get("answer")) != f"{successor_name}.",
    )
    follow_history = [
        {"role": "user", "content": "Who was Baji Rao I?"},
        {"role": "assistant", "content": "Baji Rao I was a Peshwa of the Marathas."},
    ]
    baji_father = corpus_fact("Who was his father?", follow_history)
    check("corpus-pronoun", baji_father.get("fact_status") == "supported" and _first(baji_father.get("answer")) == "Balaji Vishwanath.")
    office_history = follow_history + [
        {"role": "user", "content": "Who was his father?"},
        {"role": "assistant", "content": baji_father.get("answer") or "Balaji Vishwanath."},
    ]
    office_expanded = _expand_pronouns("What office did he hold?", office_history).lower()
    office = corpus_fact("What office did he hold?", office_history)
    check(
        "corpus-office-stays-on-topic",
        "baji rao" in office_expanded
        and "balaji" not in office_expanded
        and office.get("fact_status") == "supported"
        and "peshwa" in (office.get("answer") or "").lower(),
    )
    more_history = office_history + [
        {"role": "user", "content": "What office did he hold?"},
        {"role": "assistant", "content": office.get("answer") or "Peshwa."},
    ]
    more_expanded = _expand_pronouns("Tell me more about him.", more_history).lower()
    check("corpus-more-stays-on-topic", "baji rao" in more_expanded and "balaji" not in more_expanded)
    akbar_history = follow_history + [
        {"role": "user", "content": "Tell me about Akbar."},
        {"role": "assistant", "content": "Akbar expanded the Mughal administration."},
    ]
    akbar_father = corpus_fact("Who was his father?", akbar_history)
    check(
        "corpus-switch-akbar",
        "balaji" not in _first(akbar_father.get("answer")).lower()
        and "baji" not in _first(akbar_father.get("answer")).lower(),
    )
    from rag.engine.answer import answer_question
    from rag.engine.normalize import trim_history

    successor_history = trim_history(
        [
            {"role": "user", "content": "Who succeeded Shivaji?"},
            {"role": "assistant", "content": successor.get("answer") or "Sambhaji."},
        ]
    )
    successor_father = answer_question("Who was his father?", history=successor_history)
    check(
        "corpus-successor-father-pronoun",
        _first(successor_father.get("answer")) == "Shivaji."
        and "balaji" not in (successor_father.get("answer") or "").lower(),
    )
    check("corpus-explain-not-planned", build_plan("Explain Akbar's administration.") is None)
    check("corpus-why-not-planned", build_plan("Why was Akbar important?") is None)
    check("corpus-compare-not-planned", build_plan("Compare Mughals and Marathas.") is None)
    listed = corpus_plan("List Shah Jahan's buildings mentioned in the textbook.")
    check("corpus-buildings", listed.get("fact_status") == "supported" and "diwan" in (listed.get("answer") or "").lower())
    check("corpus-mcq-not-planned", build_plan("Give me multiple choice questions about Shivaji") is None)
    check("corpus-econtent-not-planned", build_plan("Create a learning module on the Marathas") is None)

    if failed:
        print(f"{len(failed)} failed")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

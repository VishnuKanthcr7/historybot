"""Stress questions generated from the loaded fact index.

The oracle is the index itself. A case fails only when the answer path
disagrees with that index. Index rows whose role text is not in the source
sentence are reported separately and are not treated as answer-path failures.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.answer import answer_question
from rag.engine.facts import NOT_STATED, compile_question, corpus_index, lookup, norm_text, try_fact_answer
from rag.engine.planner import AMBIGUOUS, TOO_DEEP, build_plan, try_planned_answer

OUT = ROOT / "tmp" / "fact-stress.json"


def usable(span) -> bool:
    if span is None or not span.text:
        return False
    text = span.text.strip()
    if not text or "?" in text or "do you know" in text.lower():
        return False
    words = text.split()
    return 1 <= len(words) <= 6


def grounded(fact, span) -> bool:
    if span is None:
        return False
    sentence = norm_text(fact.sentence)
    if span.norm and span.norm in sentence:
        return True
    tokens = [token for token in (span.norm or "").split() if len(token) >= 4]
    return bool(tokens) and all(token in sentence for token in tokens)


class Case:
    def __init__(self, group, question, expect, detail, page=None, norms=None, lead="", kind="fact", history=None, index_issue=False):
        self.group = group
        self.question = question
        self.expect = expect
        self.detail = detail
        self.page = page
        self.norms = norms or []
        self.lead = lead
        self.kind = kind
        self.history = history
        self.index_issue = index_issue


def _span(fact, role):
    return fact.roles.get(role)


def _text(span) -> str:
    return span.text.strip(" ,;:.")


def add(cases, *args, **kwargs):
    cases.append(Case(*args, **kwargs))


def generate(index) -> list[Case]:
    cases: list[Case] = []
    parents = [fact for fact in index.facts if fact.predicate == "parent" and usable(_span(fact, "parent")) and usable(_span(fact, "child"))]
    succession = [
        fact
        for fact in index.facts
        if fact.predicate in {"after", "succeeded"} and usable(_span(fact, "earlier")) and usable(_span(fact, "later"))
    ]
    built = [fact for fact in index.facts if fact.predicate == "built" and usable(_span(fact, "agent")) and usable(_span(fact, "object"))]
    appointed = [fact for fact in index.facts if fact.predicate == "appointed_as" and usable(_span(fact, "patient")) and usable(_span(fact, "office"))]
    defeated = [fact for fact in index.facts if fact.predicate == "defeated" and usable(_span(fact, "agent")) and usable(_span(fact, "patient"))]
    ages = [fact for fact in index.facts if fact.predicate == "age" and usable(_span(fact, "subject")) and _span(fact, "value")]
    births = [fact for fact in index.facts if fact.predicate == "birthplace" and usable(_span(fact, "subject")) and usable(_span(fact, "value"))]
    quantities = [fact for fact in index.facts if fact.predicate == "quantity" and usable(_span(fact, "subject")) and _span(fact, "value_text")]
    definitions = [fact for fact in index.facts if fact.predicate == "definition" and usable(_span(fact, "term"))]
    members = [fact for fact in index.facts if fact.predicate == "member_of" and usable(_span(fact, "member"))]

    def has_parent(child_norm: str):
        hits = [fact for fact in parents if fact.roles["child"].norm == child_norm and grounded(fact, fact.roles["parent"])]
        return hits

    def has_child(parent_norm: str):
        return [fact for fact in parents if fact.roles["parent"].norm == parent_norm and grounded(fact, fact.roles["child"])]

    for fact in parents:
        parent, child, kin = fact.roles["parent"], fact.roles["child"], fact.roles.get("kin")
        kin_word = kin.norm if kin is not None and kin.norm in {"father", "mother"} else "father"
        child_word = "son" if kin_word == "father" else "daughter"
        issue = not (grounded(fact, parent) and grounded(fact, child))
        variants = [
            f"Who was the {kin_word} of { _text(child) }?",
            f"Who is the {kin_word} of { _text(child) }?",
            f"Who was {_text(child)}'s {kin_word}?",
            f"Whose {child_word} was {_text(child)}?",
        ]
        for question in variants:
            add(cases, "A", question, "supported", f"{kin_word} {_text(parent)}", fact.printed_page, [parent.norm], parent.norm, index_issue=issue)
        if not any(other.roles["child"].norm == parent.norm for other in parents):
            add(cases, "ADV", f"Who was the father of {_text(parent)}?", "not_stated", "known parent is not a child")
        add(cases, "B", f"Who was the {child_word} of {_text(parent)}?", "supported", f"{child_word} {_text(child)}", fact.printed_page, [child.norm], child.norm, index_issue=issue)
        add(cases, "C", f"Was {_text(parent)} the {kin_word} of {_text(child)}?", "supported", "yes", fact.printed_page, [parent.norm, child.norm], index_issue=issue)
        add(cases, "C", f"Was {_text(child)} the {child_word} of {_text(parent)}?", "supported", "yes son", fact.printed_page, [parent.norm, child.norm], index_issue=issue)
        add(cases, "C", f"Was {_text(child)} the {kin_word} of {_text(parent)}?", "contradicted", "reversed", fact.printed_page, index_issue=issue)
        add(cases, "C", f"Was Zorblattqx the {kin_word} of {_text(child)}?", "not_stated", "unknown parent", index_issue=issue)
        add(cases, "ADV", f"Was {_text(child)} the brother of {_text(parent)}?", "not_stated", "unstated kin", index_issue=issue)

    for fact in succession:
        earlier, later = fact.roles["earlier"], fact.roles["later"]
        issue = not (grounded(fact, earlier) and grounded(fact, later))
        for question in (
            f"Who came after {_text(earlier)}?",
            f"Who succeeded {_text(earlier)}?",
            f"who succeeded {_text(earlier)}?",
        ):
            add(cases, "K", question, "supported", f"after {_text(later)}", fact.printed_page, [later.norm], later.norm, index_issue=issue)
        add(cases, "K", f"Who came before {_text(later)}?", "supported", f"before {_text(earlier)}", fact.printed_page, [earlier.norm], earlier.norm, index_issue=issue)
        add(cases, "C", f"Was {_text(later)} the successor of {_text(earlier)}?", "supported", "yes successor", fact.printed_page, [earlier.norm, later.norm], index_issue=issue)
        add(cases, "C", f"Was {_text(earlier)} the successor of {_text(later)}?", "contradicted", "reversed successor", fact.printed_page, index_issue=issue)
        add(cases, "C", f"Was Zorblattqx the successor of {_text(earlier)}?", "not_stated", "unknown successor", index_issue=issue)
        parents_of_later = has_parent(later.norm)
        if len(parents_of_later) == 1 and not issue:
            parent = parents_of_later[0].roles["parent"]
            add(
                cases, "D",
                f"Who was the father of the person who succeeded {_text(earlier)}?",
                "supported", f"father of successor {_text(parent)}",
                parents_of_later[0].printed_page, [parent.norm], parent.norm, kind="plan",
            )
            grand = has_parent(parent.norm)
            if len(grand) == 1:
                gparent = grand[0].roles["parent"]
                add(
                    cases, "D",
                    f"Who was the father of the father of the person who succeeded {_text(earlier)}?",
                    "supported", f"grandfather {_text(gparent)}",
                    grand[0].printed_page, [gparent.norm], gparent.norm, kind="plan",
                )
            else:
                add(
                    cases, "D",
                    f"Who was the father of the father of the person who succeeded {_text(earlier)}?",
                    "not_stated", "no exact grandfather", kind="plan",
                )
        if not has_child(later.norm) and not issue:
            add(
                cases, "D",
                f"Who was the son of the person who succeeded {_text(earlier)}?",
                "not_stated", "no exact son of successor", kind="plan",
            )
        add(
            cases, "D",
            f"Who was the father of the son of the father of the son of {_text(earlier)}?",
            "too_deep", "four hops", kind="plan",
        )

    for fact in built:
        agent, obj = fact.roles["agent"], fact.roles["object"]
        if obj.text.lower().startswith("and ") or obj.text[:1].islower():
            continue
        issue = not (grounded(fact, agent) and grounded(fact, obj))
        add(cases, "A", f"Who built {_text(obj)}?", "supported", f"builder {_text(agent)}", fact.printed_page, [agent.norm], index_issue=issue)
        add(cases, "A", f"Who built the {_text(obj)}?", "supported", "builder the", fact.printed_page, [agent.norm], index_issue=issue)
        add(cases, "J", f"What did {_text(agent)} build?", "supported", f"includes {_text(obj)}", fact.printed_page, [obj.norm], index_issue=issue)
        add(cases, "J", f"Which buildings did {_text(agent)} build?", "supported", "building list", fact.printed_page, [obj.norm], index_issue=issue)
        add(cases, "J", f"List {_text(agent)}'s buildings mentioned in the textbook.", "supported", "list buildings", fact.printed_page, [obj.norm], kind="plan", index_issue=issue)
        add(cases, "C", f"Did {_text(agent)} build {_text(obj)}?", "supported", "yes build", fact.printed_page, [agent.norm, obj.norm], index_issue=issue)
        add(cases, "C", f"Did {_text(agent)} construct {_text(obj)}?", "supported", "yes construct", fact.printed_page, [agent.norm, obj.norm], index_issue=issue)
        add(cases, "C", f"Did Zorblattqx build {_text(obj)}?", "not_stated", "unknown builder", index_issue=issue)
        add(
            cases, "E", f"Was it {_text(obj)}?", "supported", "it follow-up", fact.printed_page, [obj.norm], kind="plan",
            history=[{"role": "user", "content": f"What did {_text(agent)} build?"}], index_issue=issue,
        )

    for fact in appointed:
        patient, office = fact.roles["patient"], fact.roles["office"]
        issue = not (grounded(fact, patient) and grounded(fact, office))
        add(cases, "C", f"Was {_text(patient)} appointed as {_text(office)}?", "supported", "yes office", fact.printed_page, [patient.norm, office.norm], index_issue=issue)
        add(cases, "C", f"Was Zorblattqx appointed as {_text(office)}?", "not_stated", "unknown appointee", index_issue=issue)
        agent = fact.roles.get("agent")
        if usable(agent) and grounded(fact, agent):
            add(cases, "C", f"Did {_text(agent)} appoint {_text(patient)}?", "supported", "yes appoint", fact.printed_page, [agent.norm, patient.norm], index_issue=issue)
            add(cases, "C", f"Did {_text(patient)} appoint {_text(agent)}?", "contradicted", "reversed appoint", fact.printed_page, index_issue=issue)
        earlier = None
        if "after the death of" in fact.sentence.lower() or " after " in fact.sentence.lower():
            for other in succession:
                if other.roles["later"].norm == patient.norm and other.printed_page == fact.printed_page:
                    earlier = other.roles["earlier"]
                    break
        # Use the sentence itself when it names a predecessor via the after-fact on the same page.
        sentence_after = [
            other for other in succession
            if other.chunk_id == fact.chunk_id and other.roles["later"].norm == patient.norm
        ]
        if len(sentence_after) == 1 and usable(sentence_after[0].roles["earlier"]):
            earlier_span = sentence_after[0].roles["earlier"]
            add(
                cases, "A",
                f"Who was appointed as {_text(office)} after {_text(earlier_span)}?",
                "supported", f"appointed {_text(patient)}", fact.printed_page, [patient.norm], index_issue=issue,
            )
            parent_hits = has_parent(patient.norm)
            if len(parent_hits) == 1 and grounded(parent_hits[0], parent_hits[0].roles["parent"]):
                parent = parent_hits[0].roles["parent"]
                add(
                    cases, "D",
                    f"Who was the father of the person who was appointed as {_text(office)} after {_text(earlier_span)}?",
                    "supported", f"father of appointee {_text(parent)}", parent_hits[0].printed_page,
                    [parent.norm], parent.norm, kind="plan",
                )
                add(
                    cases, "D",
                    f"Who was the son of the person who became {_text(office)} after {_text(earlier_span)}?",
                    "not_stated" if not has_child(patient.norm) else "supported",
                    "son of appointee",
                    kind="plan",
                    norms=[has_child(patient.norm)[0].roles["child"].norm] if len(has_child(patient.norm)) == 1 else [],
                    lead=has_child(patient.norm)[0].roles["child"].norm if len(has_child(patient.norm)) == 1 else "",
                )

    offices: dict[str, set[str]] = {}
    for fact in appointed:
        office = fact.roles["office"]
        patient = fact.roles["patient"]
        if usable(office) and usable(patient):
            offices.setdefault(office.norm, set()).add(patient.norm)
    for fact in appointed:
        office = fact.roles["office"]
        if usable(office) and len(offices.get(office.norm, ())) > 1:
            add(
                cases, "D",
                f"Who was the father of the person who was appointed as {_text(office)}?",
                "ambiguous", "several appointees", kind="plan",
            )
            break

    for fact in defeated:
        agent, patient = fact.roles["agent"], fact.roles["patient"]
        if not usable(agent) or not usable(patient):
            continue
        issue = not (grounded(fact, agent) and grounded(fact, patient))
        add(cases, "C", f"Did {_text(agent)} defeat {_text(patient)}?", "supported", "yes defeat", fact.printed_page, [agent.norm, patient.norm], index_issue=issue)
        add(cases, "C", f"Did {_text(patient)} defeat {_text(agent)}?", "contradicted", "reversed defeat", fact.printed_page, index_issue=issue)
        add(cases, "C", f"Did Zorblattqx defeat {_text(patient)}?", "not_stated", "third party", index_issue=issue)
        parent_hits = [item for item in parents if item.roles["child"].norm == agent.norm and grounded(item, item.roles["parent"])]
        if len(parent_hits) == 1:
            parent = parent_hits[0].roles["parent"]
            add(
                cases, "D",
                f"Who was the father of the person who defeated {_text(patient)}?",
                "supported", f"father of victor {_text(parent)}",
                parent_hits[0].printed_page, [parent.norm], parent.norm, kind="plan", index_issue=issue,
            )
        else:
            add(
                cases, "D",
                f"Who was the father of the person who defeated {_text(patient)}?",
                "not_stated", "no single father of victor", kind="plan", index_issue=issue,
            )

    for fact in ages:
        subject, value = fact.roles["subject"], fact.roles["value"]
        add(cases, "A", f"At what age did {_text(subject)} assume power?", "supported", value.text, fact.printed_page, [norm_text(value.text)], index_issue=not grounded(fact, subject))
    for fact in births:
        subject, value = fact.roles["subject"], fact.roles["value"]
        add(cases, "A", f"Where was {_text(subject)} born?", "supported", value.text, fact.printed_page, [value.norm], index_issue=not grounded(fact, subject))
    for fact in quantities:
        subject, value = fact.roles["subject"], fact.roles["value_text"]
        context = fact.roles.get("context")
        name = _text(subject).split(" as ")[0]
        if context is not None and context.norm == "compensation":
            question = f"How much compensation did {name} receive?"
        else:
            question = f"How much did {name} receive?"
        add(cases, "A", question, "supported", value.text, fact.printed_page, [norm_text(value.text)], index_issue=not grounded(fact, subject))
    for fact in definitions[:20]:
        term = fact.roles["term"]
        add(cases, "A", f"What is {_text(term)}?", "supported", "definition", fact.printed_page, [term.norm], index_issue=not grounded(fact, term))

    if succession:
        fact = succession[0]
        earlier, later = fact.roles["earlier"], fact.roles["later"]
        if not (not grounded(fact, earlier) or not grounded(fact, later)):
            answer = try_fact_answer(f"Who succeeded {_text(earlier)}?", index=index)
            lead = ((answer or {}).get("answer") or "").split("\n", 1)[0]
            history = [
                {"role": "user", "content": f"Who succeeded {_text(earlier)}?"},
                {"role": "assistant", "content": (answer or {}).get("answer") or lead},
            ]
            parent_hits = has_parent(later.norm)
            if len(parent_hits) == 1:
                parent = parent_hits[0].roles["parent"]
                add(cases, "E", "Who was his father?", "supported", "pronoun to successor", parent_hits[0].printed_page, [parent.norm], parent.norm, history=history)
            other = next((item for item in parents if item.roles["child"].norm != later.norm), None)
            if other is not None:
                switched = history + [
                    {"role": "user", "content": f"Tell me about {_text(other.roles['child'])}."},
                    {"role": "assistant", "content": f"{_text(other.roles['child'])} is discussed in the textbook."},
                ]
                switched_parent = has_parent(other.roles["child"].norm)
                if len(switched_parent) == 1:
                    parent = switched_parent[0].roles["parent"]
                    add(cases, "E", "Who was his father?", "supported", "topic switch", switched_parent[0].printed_page, [parent.norm], parent.norm, history=switched)
                else:
                    add(cases, "E", "Who was his father?", "not_stated", "topic switch has no father", history=switched)

    broad = [
        ("F", "Explain the Maratha administration."),
        ("F", "Tell me about the Mughal empire in the textbook."),
        ("G", "Why was this policy introduced?"),
        ("H", "How did this event happen?"),
        ("I", "Compare the Mughals and the Marathas."),
        ("K", "Put these events in chronological order."),
        ("L", "Give me multiple choice questions about the chapter."),
        ("L", "Create a learning module on the Marathas."),
    ]
    for group, question in broad:
        add(cases, group, question, "not_planned", "existing rag path", kind="route")

    safety = [
        ("SAFE", "What is Python?", "boundary"),
        ("SAFE", "Who is Elon Musk?", "outside"),
        ("SAFE", "What is quantum computing?", "outside"),
        ("SAFE", "Who won the latest cricket match?", "outside"),
        ("SAFE", "Tell me today's news.", "outside"),
        ("SAFE", "ಯಾರು ಬಾಜಿ ರಾವ್?", "kannada"),
    ]
    for group, question, expect in safety:
        add(cases, group, question, expect, "safety", kind="api")
    return cases


def _pages(result) -> list[int]:
    pages = []
    for source in (result or {}).get("sources") or []:
        page = source.get("printed_page_number") or source.get("textbook_page_number")
        if page is not None:
            pages.append(int(page))
    return pages


def _lead(answer: str) -> str:
    return norm_text((answer or "").strip().split("\n", 1)[0].strip().rstrip("."))


def evaluate(case: Case, index) -> dict:
    started = time.perf_counter()
    if case.kind == "route":
        planned = build_plan(case.question)
        ok = planned is None
        verdict = "PASS" if ok else "FAIL"
        failure = "" if ok else "PLANNER_BUG"
        return _row(case, verdict, failure, "" if planned is None else "planned", "", int((time.perf_counter() - started) * 1000))
    if case.kind == "api":
        if case.expect == "kannada":
            result = answer_question(case.question, "kn")
            ok = result.get("validation_reason") == "kannada_corpus_unavailable" or result.get("mode") == "KANNADA_UNAVAILABLE"
        else:
            result = answer_question(case.question, "en")
            reason = str(result.get("validation_reason") or "")
            answer = result.get("answer") or ""
            ok = result.get("grounded") is False and (
                "textbook" in answer.lower() or reason in {"off_domain_or_unsupported", "outside_textbook_request"} or "not" in answer.lower()
            )
            ok = ok and "elon" not in answer.lower() and "quantum" not in answer.lower() and "cricket" not in answer.lower()
        verdict = "PASS" if ok else "FAIL"
        failure = "" if ok else "RETRIEVAL_BUG"
        return _row(case, verdict, failure, (result.get("answer") or "")[:240], result.get("validation_reason") or "", int((time.perf_counter() - started) * 1000))

    runner = try_planned_answer if case.kind == "plan" else try_fact_answer
    result = runner(case.question, case.history, index)
    elapsed = int((time.perf_counter() - started) * 1000)
    answer = "" if result is None else (result.get("answer") or "")
    status = "decline" if result is None else str(result.get("fact_status") or "")
    if case.index_issue:
        return _row(case, "INDEX", "FACT_INDEX_BUG", answer[:240], status, elapsed)
    if case.expect == "not_planned":
        ok = build_plan(case.question) is None
        return _row(case, "PASS" if ok else "FAIL", "" if ok else "PLANNER_BUG", "", "", elapsed)
    if case.expect == "not_stated":
        ok = status == "not_stated" and NOT_STATED in answer
        failure = "" if ok else ("UNSUPPORTED_FRAME" if result is None else "REAL_PRODUCTION_BUG")
        return _row(case, "PASS" if ok else "FAIL", failure, answer[:240], status, elapsed)
    if case.expect == "too_deep":
        ok = TOO_DEEP in answer
        return _row(case, "PASS" if ok else "FAIL", "" if ok else "PLANNER_BUG", answer[:240], status, elapsed)
    if case.expect == "ambiguous":
        ok = AMBIGUOUS in answer or status == "ambiguous"
        return _row(case, "PASS" if ok else "FAIL", "" if ok else "PLANNER_BUG", answer[:240], status, elapsed)
    if case.expect == "contradicted":
        ok = status == "contradicted" and answer.lower().startswith("no.")
        failure = "" if ok else ("UNSUPPORTED_FRAME" if result is None else "REAL_PRODUCTION_BUG")
        return _row(case, "PASS" if ok else "FAIL", failure, answer[:240], status, elapsed)
    answer_norm = norm_text(answer)
    missing = [norm for norm in case.norms if norm not in answer_norm]
    lead_ok = True
    if case.lead and case.kind != "plan":
        compiled = compile_question(case.question)
        if compiled is not None and compiled.predicate in {"parent", "after", "succeeded"} and compiled.act == "wh":
            lead_ok = case.lead in _lead(answer) or _lead(answer) in case.lead
    page_ok = case.page is None or case.page in _pages(result)
    if case.kind == "plan" and case.lead:
        lead_ok = case.lead in _lead(answer) or _lead(answer) in case.lead
    ok = status == "supported" and not missing and lead_ok and page_ok
    failure = ""
    if not ok:
        if result is None:
            failure = "UNSUPPORTED_FRAME"
        elif status != "supported":
            failure = "REAL_PRODUCTION_BUG"
        elif missing or not lead_ok:
            failure = "ANSWER_RENDERING_BUG"
        elif not page_ok:
            failure = "SOURCE_CITATION_BUG"
        else:
            failure = "REAL_PRODUCTION_BUG"
    return _row(case, "PASS" if ok else "FAIL", failure, answer[:240], status, elapsed)


def _row(case: Case, verdict: str, failure: str, actual: str, status: str, elapsed: int) -> dict:
    return {
        "group": case.group,
        "question": case.question,
        "expect": case.expect,
        "detail": case.detail,
        "verdict": verdict,
        "failure": failure,
        "status": status,
        "actual": actual,
        "ms": elapsed,
        "kind": case.kind,
    }


def main() -> int:
    index = corpus_index()
    cases = generate(index)
    started = time.perf_counter()
    rows = [evaluate(case, index) for case in cases]
    elapsed = round(time.perf_counter() - started, 1)
    counted = [row for row in rows if row["verdict"] != "INDEX"]
    verdicts = Counter(row["verdict"] for row in counted)
    failures = Counter(row["failure"] for row in counted if row["verdict"] == "FAIL")
    by_group = {}
    for row in counted:
        bucket = by_group.setdefault(row["group"], Counter())
        bucket[row["verdict"]] += 1
    summary = {
        "facts": len(index.facts),
        "cases": len(rows),
        "scored": len(counted),
        "index_issues": sum(1 for row in rows if row["verdict"] == "INDEX"),
        "verdicts": dict(verdicts),
        "failures": dict(failures),
        "by_group": {key: dict(value) for key, value in sorted(by_group.items())},
        "seconds": elapsed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("--- failures ---")
    for row in counted:
        if row["verdict"] == "FAIL":
            print(row["failure"], row["group"], row["expect"], row["question"])
            print(" ", row["status"], row["actual"][:180].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

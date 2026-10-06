"""Corpus-wide fact-layer regression harness.

Questions are derived from the loaded fact index. Expected values are the
fact's own role spans and page, not a handwritten answer key.
This file does not change production RAG behavior.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.facts import corpus_index, norm_text, try_fact_answer
from rag.engine.topic_map import load_primary_chunks

OUT = ROOT / "tmp" / "fact-corpus-harness.json"
PRONOUNS = {"he", "she", "him", "his", "her", "they", "them", "it"}
PERSON_ROLES = {"parent", "child", "subject", "agent", "patient", "later", "earlier", "owner", "member"}
LEAD_PREDICATES = {"parent", "after", "succeeded"}


@dataclass
class Case:
    category: str
    question: str
    fact_id: str
    page: int | None
    predicate: str
    expect: str
    expect_norms: list[str] = field(default_factory=list)
    lead_norm: str = ""
    detail: str = ""
    who_question: bool = False


@dataclass
class Result:
    category: str
    question: str
    fact_id: str
    page: int | None
    predicate: str
    expect: str
    expected: str
    actual: str
    status: str
    verdict: str
    failure: str = ""


def _span(fact, role: str):
    span = fact.roles.get(role)
    if span is None:
        return None
    text = re.sub(r"\s+", " ", span.text or "").strip(" ,;:.")
    if not text or span.norm in PRONOUNS or len(span.norm) < 2:
        return None
    if len(text.split()) > 8:
        return None
    return span


def _text(span) -> str:
    return re.sub(r"\s+", " ", span.text).strip(" ,;:.")


def _usable_pair(left, right) -> bool:
    return left is not None and right is not None and left.norm != right.norm


def _name_match(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return False
    if expected == actual or expected in actual or actual in expected:
        return True
    exp = {token for token in expected.split() if len(token) >= 3}
    got = {token for token in actual.split() if len(token) >= 3}
    return bool(exp) and exp <= got


def _lead(answer: str) -> str:
    return norm_text((answer or "").split("\n", 1)[0].strip().rstrip("."))


def _pages(result: dict) -> list[int]:
    pages = []
    for source in result.get("sources") or []:
        page = source.get("printed_page_number")
        if page is not None:
            pages.append(int(page))
    return pages


def _has_pair(index, predicate: str, left_role: str, left: str, right_role: str, right: str) -> bool:
    for fact in index.facts:
        if fact.predicate != predicate:
            continue
        left_span = fact.roles.get(left_role)
        right_span = fact.roles.get(right_role)
        if left_span and right_span and left_span.norm == left and right_span.norm == right:
            return True
    return False


def _case(category, question, fact, expect, norms, detail, lead="", who=False) -> Case:
    return Case(
        category=category,
        question=question,
        fact_id=fact.fact_id,
        page=fact.printed_page,
        predicate=fact.predicate,
        expect=expect,
        expect_norms=norms,
        lead_norm=lead,
        detail=detail,
        who_question=who,
    )


def generate_cases(index) -> list[Case]:
    cases: list[Case] = []
    for fact in index.facts:
        cases.extend(_cases_for_fact(index, fact))
    cases.extend(_unknown_cases(index))
    cases.extend(_entity_cases(index))
    return cases


def _cases_for_fact(index, fact) -> list[Case]:
    kind = fact.kind
    predicate = fact.predicate
    made: list[Case] = []
    if predicate == "parent":
        made.extend(_parent_cases(index, fact))
    elif predicate in {"after", "succeeded"}:
        made.extend(_succession_cases(index, fact))
    elif predicate == "appointed_as":
        made.extend(_appointment_cases(fact))
    elif predicate in {"lost_to", "defeated"}:
        made.extend(_conflict_cases(index, fact))
    elif predicate == "assisted":
        made.extend(_assist_cases(index, fact))
    elif predicate in {"built", "established"}:
        made.extend(_built_cases(fact))
    elif predicate == "abolished":
        made.extend(_abolish_cases(fact))
    elif predicate == "wrote":
        made.extend(_wrote_cases(fact))
    elif predicate == "moved_toward":
        made.extend(_motion_cases(fact))
    elif predicate == "age":
        made.extend(_age_cases(fact))
    elif predicate == "birthplace":
        made.extend(_birth_cases(fact))
    elif predicate == "quantity":
        made.extend(_quantity_cases(fact))
    elif predicate == "definition":
        made.extend(_definition_cases(fact))
    elif predicate == "identity":
        made.extend(_identity_cases(fact))
    elif predicate == "member_of":
        made.extend(_list_cases(index, fact))
    elif predicate == "ruler_of":
        made.extend(_ruler_cases(fact))
    else:
        made.append(
            Case(
                category="NA",
                question="",
                fact_id=fact.fact_id,
                page=fact.printed_page,
                predicate=predicate,
                expect="not_applicable",
                detail=f"no question frame for {kind}/{predicate}",
            )
        )
    if not made:
        made.append(
            Case(
                category="NA",
                question="",
                fact_id=fact.fact_id,
                page=fact.printed_page,
                predicate=predicate,
                expect="not_applicable",
                detail="roles missing for a grammatical question",
            )
        )
    made.extend(_integrity_cases(fact))
    return made


def _parent_cases(index, fact) -> list[Case]:
    parent = _span(fact, "parent")
    child = _span(fact, "child")
    kin = _span(fact, "kin")
    if not _usable_pair(parent, child) or kin is None:
        return []
    kin_word = kin.norm if kin.norm in {"father", "mother"} else "father"
    child_word = "son" if kin_word == "father" else "daughter"
    out = [
        _case(
            "A",
            f"Who was the {kin_word} of {_text(child)}?",
            fact,
            "supported",
            [parent.norm],
            f"{kin_word} of {_text(child)} is {_text(parent)}",
            lead=parent.norm,
            who=True,
        ),
        _case(
            "K",
            f"Who is {_text(child)}'s {kin_word}?",
            fact,
            "supported",
            [parent.norm],
            f"alternate possessive {kin_word}",
            lead=parent.norm,
            who=True,
        ),
        _case(
            "B",
            f"Who was the {child_word} of {_text(parent)}?",
            fact,
            "supported",
            [child.norm],
            f"{child_word} of {_text(parent)} is {_text(child)}",
            lead=child.norm,
            who=True,
        ),
        _case(
            "C",
            f"Was {_text(parent)} the {kin_word} of {_text(child)}?",
            fact,
            "supported",
            [parent.norm, child.norm],
            f"positive {kin_word}",
        ),
    ]
    if not _has_pair(index, "parent", "parent", child.norm, "child", parent.norm):
        out.append(
            _case(
                "C",
                f"Was {_text(child)} the {kin_word} of {_text(parent)}?",
                fact,
                "rejected",
                [],
                f"reversed {kin_word}",
            )
        )
    return out


def _succession_cases(index, fact) -> list[Case]:
    earlier = _span(fact, "earlier")
    later = _span(fact, "later")
    if not _usable_pair(earlier, later):
        return []
    out = [
        _case(
            "A",
            f"Who came after {_text(earlier)}?",
            fact,
            "supported",
            [later.norm],
            f"after {_text(earlier)} is {_text(later)}",
            lead=later.norm,
            who=True,
        ),
        _case(
            "I",
            f"Who came before {_text(later)}?",
            fact,
            "supported",
            [earlier.norm],
            f"before {_text(later)} is {_text(earlier)}",
            lead=earlier.norm,
            who=True,
        ),
        _case(
            "B",
            f"Who succeeded {_text(earlier)}?",
            fact,
            "supported",
            [later.norm],
            f"successor of {_text(earlier)}",
            lead=later.norm,
            who=True,
        ),
        _case(
            "K",
            f"What happened after {_text(earlier)}?",
            fact,
            "supported",
            [later.norm],
            "chronology alternate",
        ),
    ]
    later_has_successor = any(
        (span := other.roles.get("earlier")) is not None and span.norm == later.norm
        for other in index.facts
        if other.predicate in {"after", "succeeded"}
    )
    if not later_has_successor:
        out.append(
            _case(
                "C",
                f"Who came after {_text(later)}?",
                fact,
                "rejected",
                [],
                "no successor is indexed for the later person",
                who=True,
            )
        )
    return out


def _appointment_cases(fact) -> list[Case]:
    patient = _span(fact, "patient")
    office = _span(fact, "office")
    if patient is None or office is None:
        return []
    out = [
        _case(
            "A",
            f"Who was appointed as {_text(office)}?",
            fact,
            "supported",
            [patient.norm],
            f"appointed {_text(office)}",
            lead=patient.norm,
            who=True,
        ),
        _case(
            "G",
            f"What office was {_text(patient)} appointed to?",
            fact,
            "supported",
            [office.norm],
            "office attribute",
        ),
    ]
    agent = _span(fact, "agent")
    if agent is not None:
        out.append(
            _case(
                "C",
                f"Did {_text(agent)} appoint {_text(patient)}?",
                fact,
                "supported",
                [patient.norm],
                "positive appointment",
            )
        )
    return out


def _conflict_cases(index, fact) -> list[Case]:
    patient = _span(fact, "patient")
    agent = _span(fact, "agent")
    place = _span(fact, "location")
    out = []
    if patient is not None and place is not None:
        out.append(
            _case(
                "A",
                f"Where did {_text(patient)} lose?",
                fact,
                "supported",
                [place.norm],
                f"lose location {_text(place)}",
            )
        )
        out.append(
            _case(
                "H",
                f"What was the outcome near {_text(place)}?",
                fact,
                "supported",
                [patient.norm],
                "event outcome",
            )
        )
    if _usable_pair(agent, patient):
        out.append(
            _case(
                "B",
                f"Did {_text(patient)} defeat {_text(agent)}?",
                fact,
                "rejected",
                [],
                "reversed defeat",
            )
        )
        winner_is_also_a_loser = any(
            (span := other.roles.get("patient")) is not None
            and span.norm == agent.norm
            and (
                place is None
                or (other.roles.get("location") is not None and other.roles["location"].norm == place.norm)
            )
            for other in index.facts
            if other.predicate in {"lost_to", "defeated"}
        )
        if not winner_is_also_a_loser:
            question = (
                f"Did {_text(agent)} lose near {_text(place)}?"
                if place is not None
                else f"Did {_text(agent)} lose?"
            )
            out.append(_case("C", question, fact, "rejected", [], "winner asked as the loser"))
        out.append(
            _case(
                "H",
                f"Who defeated {_text(patient)}?",
                fact,
                "supported",
                [agent.norm],
                "event participant",
                lead=agent.norm,
                who=True,
            )
        )
    return out


def _assist_cases(index, fact) -> list[Case]:
    agent = _span(fact, "agent")
    patient = _span(fact, "patient")
    if not _usable_pair(agent, patient):
        return []
    out = [
        _case(
            "A",
            f"Who did {_text(agent)} assist?",
            fact,
            "supported",
            [patient.norm],
            f"{_text(agent)} assisted {_text(patient)}",
        )
    ]
    if not _has_pair(index, "assisted", "agent", patient.norm, "patient", agent.norm):
        out.append(
            _case(
                "B",
                f"Did {_text(patient)} assist {_text(agent)}?",
                fact,
                "rejected",
                [],
                "reversed assistance",
            )
        )
    return out


def _built_cases(fact) -> list[Case]:
    agent = _span(fact, "agent")
    obj = _span(fact, "object")
    if agent is None or obj is None:
        return []
    verb = "built" if fact.predicate == "built" else "established"
    return [
        _case(
            "A",
            f"Who {verb} {_text(obj)}?",
            fact,
            "supported",
            [agent.norm],
            f"{verb} by {_text(agent)}",
            lead=agent.norm,
            who=True,
        ),
        _case(
            "K",
            f"What did {_text(agent)} {verb}?",
            fact,
            "supported",
            [obj.norm],
            f"object of {verb}",
        ),
    ]


def _abolish_cases(fact) -> list[Case]:
    agent = _span(fact, "agent")
    obj = _span(fact, "object")
    if agent is None or obj is None:
        return []
    return [
        _case(
            "A",
            f"Which tax did {_text(agent)} abolish?",
            fact,
            "supported",
            [obj.norm],
            f"abolished {_text(obj)}",
        )
    ]


def _wrote_cases(fact) -> list[Case]:
    agent = _span(fact, "agent")
    obj = _span(fact, "object")
    if agent is None or obj is None:
        return []
    return [
        _case(
            "A",
            f"What did {_text(agent)} write?",
            fact,
            "supported",
            [obj.norm],
            f"wrote {_text(obj)}",
        )
    ]


def _motion_cases(fact) -> list[Case]:
    agent = _span(fact, "agent")
    dest = _span(fact, "destination")
    if agent is None or dest is None:
        return []
    return [
        _case(
            "A",
            f"Who tried to march towards {_text(dest)}?",
            fact,
            "supported",
            [agent.norm],
            f"marched toward {_text(dest)}",
            lead=agent.norm,
            who=True,
        ),
        _case(
            "H",
            f"Where did {_text(agent)} march?",
            fact,
            "supported",
            [dest.norm],
            "event place",
        ),
    ]


def _age_cases(fact) -> list[Case]:
    subject = _span(fact, "subject")
    value = _span(fact, "value")
    if subject is None or value is None:
        return []
    return [
        _case(
            "A",
            f"At what age did {_text(subject)} assume power?",
            fact,
            "supported",
            [value.norm],
            f"age {_text(value)}",
        ),
        _case(
            "G",
            f"How old was {_text(subject)}?",
            fact,
            "supported",
            [value.norm],
            "age attribute",
        ),
    ]


def _birth_cases(fact) -> list[Case]:
    subject = _span(fact, "subject")
    value = _span(fact, "value")
    if subject is None or value is None:
        return []
    return [
        _case(
            "A",
            f"Where was {_text(subject)} born?",
            fact,
            "supported",
            [value.norm],
            f"born {_text(value)}",
        ),
        _case(
            "G",
            f"What was {_text(subject)}'s birthplace?",
            fact,
            "supported",
            [value.norm],
            "birthplace attribute",
        ),
    ]


def _quantity_cases(fact) -> list[Case]:
    subject = _span(fact, "subject")
    value = _span(fact, "value_text") or _span(fact, "value")
    if subject is None or value is None:
        return []
    context = fact.roles.get("context")
    if context is not None and context.norm == "compensation":
        question = f"How much compensation did {_text(subject)} receive?"
    else:
        question = f"How much did {_text(subject)} receive?"
    return [
        _case("A", question, fact, "supported", [value.norm], f"quantity {_text(value)}"),
        _case(
            "J",
            f"What amount is associated with {_text(subject)}?",
            fact,
            "supported",
            [value.norm],
            "quantity alternate",
        ),
    ]


def _definition_cases(fact) -> list[Case]:
    term = _span(fact, "term")
    if term is None or len(term.norm) < 4:
        return []
    return [
        _case(
            "F",
            f"What was {_text(term)}?",
            fact,
            "supported",
            [term.norm],
            f"definition {_text(term)}",
        ),
        _case(
            "F",
            f"What is {_text(term)}?",
            fact,
            "supported",
            [term.norm],
            "definition alternate",
        ),
        _case(
            "F",
            f"Explain {_text(term)}.",
            fact,
            "decline",
            [],
            "definition explain stays on the evidence-pack path",
        ),
    ]


def _identity_cases(fact) -> list[Case]:
    subject = _span(fact, "subject")
    if subject is None:
        return []
    out = [
        _case(
            "E",
            f"Who was {_text(subject)}?",
            fact,
            "decline",
            [],
            "bare identity stays on the evidence-pack path",
        )
    ]
    complement = _span(fact, "complement")
    if complement is not None and complement.norm.split()[0] in {"a", "an", "the"}:
        out.append(
            _case(
                "C",
                f"Was {_text(subject)} {_text(complement)}?",
                fact,
                "supported",
                [subject.norm],
                f"identity {_text(complement)}",
            )
        )
    return out


def _list_cases(index, fact) -> list[Case]:
    owner = _span(fact, "owner")
    context = _span(fact, "context")
    if fact.order_key not in {None, "1"}:
        return []
    if owner is None or context is None or "minister" not in context.norm:
        return []
    members = []
    for other in index.facts:
        if other.list_id and other.list_id == fact.list_id and other.predicate == "member_of":
            member = _span(other, "member")
            if member is not None:
                members.append(member.norm)
    if len(members) < 2:
        return []
    return [
        _case(
            "A",
            f"Which ministers assisted {_text(owner)}?",
            fact,
            "supported",
            members,
            "list members " + ", ".join(members),
        )
    ]


def _ruler_cases(fact) -> list[Case]:
    agent = _span(fact, "agent")
    place = _span(fact, "place")
    if agent is None or place is None:
        return []
    return [
        _case(
            "G",
            f"Where did {_text(agent)} rule?",
            fact,
            "supported",
            [place.norm],
            f"ruled {_text(place)}",
        )
    ]


def _integrity_cases(fact) -> list[Case]:
    sentence = norm_text(fact.sentence)
    missing = []
    for role, span in fact.roles.items():
        if span is None or not span.norm or span.norm in PRONOUNS:
            continue
        tokens = [token for token in span.norm.split() if len(token) >= 4]
        if tokens and not any(token in sentence for token in tokens):
            missing.append(role)
    if not missing:
        return []
    return [
        _case(
            "INDEX",
            "",
            fact,
            "role_in_sentence",
            [],
            "roles missing from source sentence: " + ", ".join(missing),
        )
    ]


def _unknown_cases(index) -> list[Case]:
    blob = " ".join(fact.sentence for fact in index.facts).lower()
    token = "Zorblattqx"
    if token.lower() in blob:
        token = "Zorblattqx9"
    dummy = Case(
        category="D",
        question="",
        fact_id="unknown",
        page=None,
        predicate="unknown",
        expect="not_stated",
        detail="entity absent from the index",
    )
    questions = [
        f"Who was the father of {token}?",
        f"Who was the son of {token}?",
        f"Where was {token} born?",
        f"At what age did {token} assume power?",
        f"Who came after {token}?",
        f"How much compensation did {token} receive?",
        f"Where did {token} lose?",
    ]
    return [
        Case(
            category="D",
            question=question,
            fact_id="unknown",
            page=None,
            predicate="unknown",
            expect="not_stated",
            detail=dummy.detail,
        )
        for question in questions
    ]


def _entity_cases(index) -> list[Case]:
    seen = set()
    out = []
    for fact in index.facts:
        for role in PERSON_ROLES:
            span = _span(fact, role)
            if span is None or span.norm in seen or len(span.norm) < 4:
                continue
            seen.add(span.norm)
            name = _text(span)
            for category, question in (
                ("E", f"Who was {name}?"),
                ("E", f"Tell me about {name}."),
                ("E", f"Explain {name}."),
            ):
                out.append(
                    Case(
                        category=category,
                        question=question,
                        fact_id=fact.fact_id,
                        page=fact.printed_page,
                        predicate="entity",
                        expect="decline",
                        detail="broad entity question uses the evidence-pack path",
                    )
                )
    return out


def _page_ok(result: dict, case: Case, index) -> bool:
    if case.page is None:
        return True
    pages = _pages(result)
    if case.page in pages:
        return True
    for fact in index.facts:
        if fact.printed_page not in pages or fact.predicate != case.predicate:
            continue
        for norm in case.expect_norms:
            for span in fact.roles.values():
                if span is not None and _name_match(norm, span.norm):
                    return True
    return False


def evaluate_case(case: Case, index) -> Result:
    expected = case.detail
    if case.expect == "not_applicable":
        return Result(
            case.category, case.question, case.fact_id, case.page, case.predicate,
            case.expect, expected, "", "not_applicable", "NOT_APPLICABLE",
        )
    if case.expect == "role_in_sentence":
        return Result(
            "INDEX", case.question, case.fact_id, case.page, case.predicate,
            "role_in_sentence", expected, case.detail, "role_not_in_sentence", "FAIL", "role_not_in_sentence",
        )
    result = try_fact_answer(case.question, index=index)
    actual = "" if result is None else (result.get("answer") or "")
    status = "decline" if result is None else str(result.get("fact_status") or "")
    failure = ""
    if case.expect == "decline":
        verdict = "PASS" if result is None else "FAIL"
        failure = "" if result is None else "intercepted_broad"
    elif case.expect == "not_stated":
        if status == "not_stated":
            verdict = "PASS"
        elif status == "supported":
            verdict, failure = "FAIL", "hallucinated"
        else:
            verdict, failure = "FAIL", "fell_through" if result is None else "wrong_status"
    elif case.expect == "rejected":
        if status in {"not_stated", "contradicted"}:
            verdict = "PASS"
        elif status == "supported":
            verdict, failure = "FAIL", "affirmed_reversal"
        else:
            verdict, failure = "FAIL", "fell_through"
    else:
        answer_norm = norm_text(actual)
        if result is None:
            verdict, failure = "FAIL", "fell_through"
        elif status != "supported":
            verdict, failure = "FAIL", "missed_fact"
        elif case.who_question and case.lead_norm and not _name_match(case.lead_norm, _lead(actual)):
            if all(_name_match(norm, answer_norm) or norm in answer_norm for norm in case.expect_norms):
                verdict, failure = "FAIL", "answer_is_sentence"
            else:
                verdict, failure = "FAIL", "wrong_lead"
        elif case.expect_norms and not all(norm in answer_norm or _name_match(norm, answer_norm) for norm in case.expect_norms):
            verdict, failure = "FAIL", "missing_value"
        elif not _page_ok(result, case, index):
            verdict, failure = "FAIL", "wrong_page"
        else:
            verdict = "PASS"
    return Result(
        case.category, case.question, case.fact_id, case.page, case.predicate,
        case.expect, expected, actual[:500], status, verdict, failure,
    )


def _parse_mcqs(answer: str) -> list[dict]:
    items = []
    for block in re.split(r"\n\s*\n", answer or ""):
        stem = re.match(r"\s*\d+\.\s+(.+)", block)
        if not stem:
            continue
        options = dict(re.findall(r"^([A-D])\.\s+(.+)$", block, re.M))
        letter = re.search(r"Answer:\s*([A-D])", block)
        if not letter or letter.group(1) not in options:
            continue
        correct = options[letter.group(1)]
        distractors = [text for key, text in options.items() if key != letter.group(1)]
        items.append({"stem": stem.group(1).strip(), "correct": correct.strip(), "distractors": distractors})
    return items


def evaluate_mcqs(chunks: list[dict]) -> list[Result]:
    from rag.engine.mcq import mcqs_from_pack

    blob = "\n".join(item.get("text") or "" for item in chunks).lower()
    names = []
    seen = set()
    index = corpus_index()
    for fact in index.facts:
        for role in PERSON_ROLES:
            span = _span(fact, role)
            if span is None or span.norm in seen or len(span.text.split()) > 4:
                continue
            if span.norm not in blob:
                continue
            seen.add(span.norm)
            names.append(_text(span))
    results = []
    flat_chunks = []
    for chunk in chunks:
        flat_chunks.append(re.sub(r"\s+", " ", chunk.get("text") or "").lower())
    for name in names:
        needle = name.lower()
        selected = [chunk for chunk, flat in zip(chunks, flat_chunks) if needle in flat]
        if not selected:
            results.append(
                Result("L", f"MCQ about {name}", "mcq", None, "mcq", "grounded", name, "", "not_applicable", "NOT_APPLICABLE")
            )
            continue
        try:
            answer, _fps = mcqs_from_pack(f"give me questions about {name}", selected, count=10)
        except Exception as exc:
            results.append(
                Result("L", f"MCQ about {name}", "mcq", None, "mcq", "grounded", name, str(exc), "error", "FAIL", "mcq_error")
            )
            continue
        items = _parse_mcqs(answer)
        if not items:
            results.append(
                Result(
                    "L", f"MCQ about {name}", "mcq", None, "mcq", "grounded", name,
                    (answer or "")[:240], "empty", "NOT_APPLICABLE",
                )
            )
            continue
        quiz = re.sub(r"\s+", " ", answer or "").lower()
        failure = ""
        name_tokens = [token for token in norm_text(name).split() if len(token) >= 5]
        if name_tokens and not any(token[:5] in quiz for token in name_tokens):
            failure = "mcq_wrong_person"
        for item in items:
            correct = re.sub(r"\s+", " ", item["correct"]).lower()
            if failure:
                break
            if not any(correct and correct in flat for flat in flat_chunks):
                failure = "mcq_ungrounded"
                break
            if any(re.sub(r"\s+", " ", option).lower() == correct for option in item["distractors"]):
                failure = "mcq_distractor_marked_correct"
                break
        results.append(
            Result(
                "L",
                f"MCQ about {name}",
                "mcq",
                None,
                "mcq",
                "grounded",
                f"{len(items)} grounded questions about {name}",
                (answer or "")[:400],
                "grounded" if not failure else failure,
                "PASS" if not failure else "FAIL",
                failure,
            )
        )
    return results


def summarize(results: list[Result]) -> dict:
    counts = Counter(item.verdict for item in results)
    by_category = defaultdict(Counter)
    failures = []
    for item in results:
        by_category[item.category][item.verdict] += 1
        if item.verdict == "FAIL":
            failures.append(asdict(item))
    applicable = counts["PASS"] + counts["FAIL"]
    coverage = round(100 * counts["PASS"] / applicable, 1) if applicable else 0.0
    fail_counts = Counter(item["failure"] for item in failures)
    return {
        "facts_scanned": None,
        "cases": len(results),
        "pass": counts["PASS"],
        "fail": counts["FAIL"],
        "not_applicable": counts["NOT_APPLICABLE"],
        "coverage_percent": coverage,
        "by_category": {key: dict(value) for key, value in sorted(by_category.items())},
        "failure_categories": dict(fail_counts.most_common()),
        "failures": failures,
    }


def main() -> int:
    index = corpus_index()
    chunks = list(load_primary_chunks())
    cases = generate_cases(index)
    results = [evaluate_case(case, index) for case in cases if case.expect != "skip"]
    print(f"fact questions evaluated {len(results)}", flush=True)
    results.extend(evaluate_mcqs(chunks))
    report = summarize(results)
    report["facts_scanned"] = len(index.facts)
    report["chunks_scanned"] = len(chunks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"facts_scanned {report['facts_scanned']}")
    print(f"cases {report['cases']}")
    print(f"PASS {report['pass']}")
    print(f"FAIL {report['fail']}")
    print(f"NOT_APPLICABLE {report['not_applicable']}")
    print(f"coverage_percent {report['coverage_percent']}")
    print("by_category")
    for key, value in report["by_category"].items():
        print(f"  {key} {value}")
    print("failure_categories")
    for key, value in report["failure_categories"].items():
        print(f"  {key} {value}")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

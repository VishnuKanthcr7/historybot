"""Bounded textbook query plans over the existing fact index.

The planner only chains questions the fact compiler already understands.
It does not invent entities, and it never returns an intermediate hop as the
final answer.
"""

from __future__ import annotations

import re

from rag.engine.facts import (
    NOT_STATED,
    FactQuery,
    _clean_slot,
    _expand_pronouns,
    _sources,
    _sentence_text,
    compile_question,
    corpus_index,
    lookup,
    norm_text,
)

MAX_HOPS = 3
TOO_DEEP = (
    "That question needs more reasoning steps than this textbook assistant currently supports."
)
AMBIGUOUS = "The prescribed textbook names more than one match, so a single answer is not stated."

_KIN = r"father|mother|parent|son|daughter"
_OUTER = re.compile(
    rf"^who\s+(?:was|is|were|are)\s+the\s+({_KIN})\s+of\s+(.+)$",
    re.I,
)
_PERSON = re.compile(
    r"^the\s+(?:person|ruler|king|emperor|sultan|monarch)\s+who\s+(.+)$",
    re.I,
)
_COORDINATED = re.compile(r",?\s+and\s+(?=(?:who|what|where|when)\b)", re.I)
_ANAPHORA = re.compile(
    r"\b(?:that|this)\s+(?:person|ruler|king|emperor|sultan|monarch)(?:['’]s)?\b",
    re.I,
)
_ROLE = r"person|ruler|king|emperor|sultan|monarch"
_DEEPER = re.compile(rf"^the\s+({_KIN})\s+of\s+(.+)$", re.I)
_BROAD = re.compile(
    r"\b(explain|tell me about|describe|compare|comparison|why|how|list|mcqs?|"
    r"multiple choice|quiz|learning module|e-?content)\b",
    re.I,
)


def _fold(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().rstrip("?")).strip()


def _clause_question(clause: str) -> str | None:
    """Turn a relative clause into a direct question the fact compiler already accepts."""
    text = _fold(clause)
    text = re.sub(r"^(?:who|that)\s+", "", text, flags=re.I)
    match = re.match(
        r"^(?:was|were)\s+appointed\s+as\s+(?:the\s+)?(.+?)\s+after\s+(?:the\s+death\s+of\s+)?(.+)$",
        text,
        re.I,
    )
    if match:
        return f"Who was appointed as {match.group(1)} after {match.group(2)}?"
    match = re.match(r"^(?:was|were)\s+appointed\s+as\s+(?:the\s+)?(.+)$", text, re.I)
    if match:
        return f"Who was appointed as {match.group(1)}?"
    match = re.match(
        r"^became\s+(?:the\s+)?(.+?)\s+after\s+(?:the\s+death\s+of\s+)?(.+)$",
        text,
        re.I,
    )
    if match:
        return f"Who was appointed as {match.group(1)} after {match.group(2)}?"
    match = re.match(r"^succeeded\s+(.+)$", text, re.I)
    if match:
        return f"Who succeeded {match.group(1)}?"
    match = re.match(
        r"^(?:returned|came back|regained)\s+(?:to\s+)?(?:power|the throne)\s+after\s+(?:the\s+death\s+of\s+)?(.+)$",
        text,
        re.I,
    )
    if match:
        return f"Who returned to power after {match.group(1)}?"
    match = re.match(r"^came\s+after\s+(.+)$", text, re.I)
    if match:
        return f"Who came after {match.group(1)}?"
    match = re.match(rf"^(?:was|were)\s+the\s+({_KIN})\s+of\s+(.+)$", text, re.I)
    if match:
        return f"Who was the {match.group(1)} of {match.group(2)}?"
    match = re.match(r"^(?:built|constructed)\s+(?:the\s+)?(.+)$", text, re.I)
    if match:
        return f"Who built {match.group(1)}?"
    match = re.match(r"^defeated\s+(.+)$", text, re.I)
    if match:
        return f"Who defeated {match.group(1)}?"
    match = re.match(r"^(?:abolished|abolishes)\s+(?:the\s+)?(.+)$", text, re.I)
    if match:
        obj = re.sub(r"\s+on\b.*$", "", match.group(1), flags=re.I).strip()
        return f"Who abolished {obj}?"
    if re.match(r"^who\b", text, re.I):
        return text if text.endswith("?") else text + "?"
    return None


def _defeated_query(clause: str) -> FactQuery | None:
    match = re.match(r"^defeated\s+(.+)$", _fold(clause), re.I)
    if not match:
        return None
    patient = norm_text(_clean_slot(match.group(1)))
    if not patient:
        return None
    return FactQuery("wh", "defeated", {"patient": patient}, "agent", surface="defeated")


def build_plan(question: str, history: list[dict] | None = None) -> dict | None:
    """A multi-hop plan, or None when the existing direct fact path should run."""
    text = _fold(_expand_pronouns(question or "", history))
    if not text or _BROAD.search(text):
        return None
    wrappers: list[str] = []
    seen: set[str] = set()
    while text not in seen:
        seen.add(text)
        match = _OUTER.match(text)
        if not match:
            return None
        kin, rest = match.group(1).lower(), match.group(2).strip()
        wrappers.append(kin)
        person = _PERSON.match(rest)
        if person:
            inner = _clause_question(person.group(1))
            unresolved = inner is None and _defeated_query(person.group(1)) is None
            steps = _steps(inner, person.group(1), list(reversed(wrappers)), unresolved)
            return _plan(steps, unresolved)
        deeper = _DEEPER.match(rest)
        if deeper:
            text = f"who was the {deeper.group(1)} of {deeper.group(2)}"
            continue
        if len(wrappers) < 2:
            return None
        inner = f"Who was the {wrappers[-1]} of {rest}?"
        steps = _steps(inner, "", list(reversed(wrappers[:-1])), False)
        return _plan(steps, False)
    return None


def _steps(inner: str | None, clause: str, kins: list[str], unresolved: bool) -> list[dict]:
    steps = [
        {
            "step_id": 1,
            "question": inner or "",
            "clause": clause,
            "binds_previous": False,
            "answer_type": "person",
        }
    ]
    for kin in kins:
        steps.append(
            {
                "step_id": len(steps) + 1,
                "question": f"Who was the {kin} of {{entity}}?",
                "clause": "",
                "binds_previous": True,
                "answer_type": "person",
                "predicate": "parent",
                "surface": kin,
            }
        )
    return steps


def _plan(steps: list[dict], unresolved: bool) -> dict:
    return {
        "mode": "multi_hop",
        "question_type": "multi_hop",
        "steps": steps,
        "final_target": "person",
        "max_hops": MAX_HOPS,
        "unresolved": unresolved,
        "too_deep": len(steps) > MAX_HOPS,
    }


def _query_for(step: dict, entity: str) -> FactQuery | None:
    if step.get("binds_previous"):
        question = str(step["question"]).format(entity=entity)
        return compile_question(question)
    if step.get("question"):
        compiled = compile_question(str(step["question"]))
        if compiled is not None:
            return compiled
    return _defeated_query(str(step.get("clause") or ""))


def _exact_bound_facts(query: FactQuery, facts: list, entity: str) -> list:
    """A hop may use only the exact entity the previous hop verified."""
    if not entity:
        return facts
    wanted = norm_text(entity)
    kept = []
    for fact in facts:
        mismatched = False
        for role, value in query.binds.items():
            if value != wanted:
                continue
            span = fact.roles.get(role)
            if span is not None and span.norm != wanted:
                mismatched = True
        if not mismatched:
            kept.append(fact)
    return kept


def _values(query: FactQuery, facts: list) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    seen: set[str] = set()
    role = query.open_role
    if not role:
        return []
    for fact in facts:
        span = fact.roles.get(role)
        if span is None or not span.text or not span.norm or span.norm in seen:
            continue
        seen.add(span.norm)
        found.append((span.text.strip(" ,;:."), fact))
    return found


def _payload(answer: str, status: str, facts: list, question: str) -> dict:
    sources = _sources(facts) if status == "supported" else []
    pages = [row["printed_page_number"] for row in sources]
    label = sources[0]["citation_label"] if sources else ""
    if pages and label:
        if len(pages) == 1:
            cite = f"Source: {label}, page {pages[0]}"
        else:
            cite = f"Source: {label}, pages " + ", ".join(str(page) for page in pages)
        if cite not in answer:
            answer = f"{answer}\n\n{cite}"
    return {
        "answer": answer,
        "language": "en",
        "grounded": status == "supported",
        "sources": sources,
        "retrieval_query": question,
        "retrieved": [],
        "selected_chunk_ids": [fact.chunk_id for fact in facts if getattr(fact, "chunk_id", "")],
        "validation_reason": f"fact_{status}",
        "intent": "STANDALONE",
        "mode": "NORMAL",
        "question_type": "DIRECT",
        "resolved_topic": None,
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
        "fallback_used": False,
        "fact_status": status,
        "fact_predicate": "multi_hop",
    }


def _building_list(question: str, index) -> dict | None:
    """A request for one person's buildings uses the existing built facts."""
    text = _fold(question)
    match = re.match(
        r"^(?:list|what are|which are)\s+(.+?)'s\s+(?:buildings|monuments|structures)\b",
        text,
        re.I,
    )
    if not match:
        match = re.match(
            r"^(?:list|what are|which are)\s+(?:the\s+)?(?:buildings|monuments|structures)\s+(?:of|built by)\s+(.+)$",
            text,
            re.I,
        )
    if not match:
        return None
    name = re.sub(r"\s+mentioned\b.*$", "", match.group(1), flags=re.I).strip()
    if not name:
        return None
    from rag.engine.facts import try_fact_answer

    return try_fact_answer(f"Which buildings did {name} build?", index=index)


def _it_followup(question: str, history: list[dict] | None, index) -> dict | None:
    """Bind 'Was it Y?' to the single builder asked about in the previous turn."""
    match = re.match(r"^was\s+it\s+(.+?)\??$", _fold(question), re.I)
    if not match or not history:
        return None
    previous = ""
    for item in reversed(history):
        if item.get("role") == "user":
            previous = str(item.get("content") or "")
            break
    query = compile_question(previous)
    if query is None or query.predicate != "built" or "agent" not in query.binds:
        return None
    status, facts = lookup(index, query)
    if status != "supported":
        return None
    agents = []
    seen = set()
    for fact in facts:
        span = fact.roles.get("agent")
        if span is None or not span.text or span.norm in seen:
            continue
        seen.add(span.norm)
        agents.append(span.text.strip(" ,;:."))
    if len(agents) != 1:
        return _payload(AMBIGUOUS, "ambiguous", [], question)
    from rag.engine.facts import try_fact_answer

    return try_fact_answer(f"Did {agents[0]} build {match.group(1)}?", index=index)


def execute_plan(plan: dict, index, question: str) -> dict:
    if plan.get("too_deep"):
        return _payload(TOO_DEEP, "not_stated", [], question)
    if plan.get("unresolved") or not plan.get("steps"):
        return _payload(NOT_STATED, "not_stated", [], question)
    entity = ""
    chain = []
    for step in plan["steps"]:
        query = _query_for(step, entity)
        if query is None or query.act != "wh" or not query.open_role:
            return _payload(NOT_STATED, "not_stated", [], question)
        status, facts = lookup(index, query)
        facts = _exact_bound_facts(query, facts, entity if step.get("binds_previous") else "")
        if status != "supported" or not facts:
            return _payload(NOT_STATED, "not_stated", [], question)
        values = _values(query, facts)
        if len(values) != 1:
            return _payload(AMBIGUOUS if len(values) > 1 else NOT_STATED, "ambiguous" if len(values) > 1 else "not_stated", [], question)
        entity, fact = values[0]
        chain.append((entity, fact))
    final = chain[-1][0]
    sentences = []
    seen = set()
    for step_entity, fact in chain:
        if step_entity != final and step_entity not in seen:
            seen.add(step_entity)
            sentences.append(f"{step_entity}.")
        text = _sentence_text(fact)
        if text and text not in seen:
            seen.add(text)
            sentences.append(text)
    body = f"{final}.\n\n" + " ".join(sentences)
    return _payload(body, "supported", [fact for _, fact in chain], question)


def _split_coordinated(question: str) -> list[str] | None:
    """Two or three explicit questions joined by 'and who/what/where/when'."""
    text = _fold(question)
    parts = [part.strip(" ,") for part in _COORDINATED.split(text) if part.strip(" ,")]
    if len(parts) < 2:
        return None
    return parts


def _bind_anaphora(clause: str, entity: str) -> str:
    if not entity:
        return clause

    def _replace(match: re.Match) -> str:
        if match.group(0).lower().endswith("'s") or match.group(0).endswith("’s"):
            return f"{entity}'s"
        return entity

    return _ANAPHORA.sub(_replace, clause)


def _answer_unit(question: str, index) -> tuple[dict | None, str]:
    """Answer one clause. The string is the single verified person, when there is one."""
    plan = build_plan(question)
    if plan is not None:
        result = execute_plan(plan, index, question)
        entity = ""
        if result.get("fact_status") == "supported":
            entity = (result.get("answer") or "").strip().split("\n", 1)[0].strip().rstrip(".")
        return result, entity
    query = compile_question(question)
    if query is None:
        return None, ""
    from rag.engine.facts import try_fact_answer

    result = try_fact_answer(question, index=index)
    if result is None or result.get("fact_status") != "supported":
        return result, ""
    status, facts = lookup(index, query)
    values = _values(query, facts) if status == "supported" else []
    if len(values) == 1:
        return result, values[0][0]
    opened = (result.get("answer") or "").strip().split("\n", 1)[0].strip().rstrip(".")
    return result, opened


def _strip_citation(answer: str) -> str:
    lines = [line for line in (answer or "").splitlines() if not line.strip().startswith("Source:")]
    return "\n".join(lines).strip()


def _coordinated_answer(question: str, index) -> dict | None:
    parts = _split_coordinated(question)
    if not parts:
        return None
    if len(parts) > MAX_HOPS:
        return _payload(TOO_DEEP, "not_stated", [], question)
    blocks = []
    sources = []
    entity = ""
    for part in parts:
        clause = _bind_anaphora(part, entity) if entity else part
        if not clause.endswith("?"):
            clause += "?"
        result, entity = _answer_unit(clause, index)
        if result is None:
            return None
        if result.get("fact_status") != "supported":
            failed = dict(result)
            failed["retrieval_query"] = question
            return failed
        blocks.append(_strip_citation(result.get("answer") or ""))
        sources.extend(result.get("sources") or [])
        if not entity:
            return _payload(NOT_STATED, "not_stated", [], question)
    pages = []
    label = ""
    for source in sources:
        page = source.get("printed_page_number")
        if page is not None and page not in pages:
            pages.append(page)
        label = label or source.get("citation_label") or ""
    body = "\n\n".join(block for block in blocks if block)
    if pages and label:
        if len(pages) == 1:
            cite = f"Source: {label}, page {pages[0]}"
        else:
            cite = f"Source: {label}, pages " + ", ".join(str(page) for page in pages)
        body = f"{body}\n\n{cite}"
    payload = _payload(body, "supported", [], question)
    payload["sources"] = sources
    payload["fact_predicate"] = "multi_part"
    return payload


def _described_person_question(question: str, index) -> dict | None:
    """'Who was the ruler who <did something>?' is the person that clause names."""
    match = re.match(
        rf"^who\s+(?:was|is|were|are)\s+the\s+(?:{_ROLE})\s+who\s+(.+)$",
        _fold(question),
        re.I,
    )
    if not match:
        return None
    inner = _clause_question(match.group(1))
    if not inner:
        return None
    from rag.engine.facts import try_fact_answer

    return try_fact_answer(inner, index=index)


def try_planned_answer(
    question: str,
    history: list[dict] | None = None,
    index=None,
) -> dict | None:
    """Answer a compositional question, or return None so the direct fact path can run."""
    fact_index = index if index is not None else corpus_index()
    listed = _building_list(question, fact_index)
    if listed is not None:
        return listed
    followed = _it_followup(question, history, fact_index)
    if followed is not None:
        return followed
    coordinated = _coordinated_answer(question, fact_index)
    if coordinated is not None:
        return coordinated
    described = _described_person_question(question, fact_index)
    if described is not None:
        return described
    plan = build_plan(question, history)
    if plan is None:
        return None
    return execute_plan(plan, fact_index, question)

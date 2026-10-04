"""Grounded structured E-content from the approved Class 9 textbook only."""

from __future__ import annotations

import json
import re

from rag.engine.answer import _public_hits, _sources, _unavailable
from rag.engine.citations import supporting_evidence
from rag.engine.classify import TOPIC_ALIASES, classify_casual
from rag.engine.evidence import evidence_is_sufficient, evidence_matches_topic
from rag.engine.normalize import looks_kannada, looks_like_injection, normalize_question
from rag.engine.pack import build_evidence_pack
from rag.engine.coverage import (
    _clean_student_text,
    build_coverage_plan,
    filter_plan,
    generate_from_plan,
    readable_extract,
)
from rag.engine.topic_map import AHOM_FAMILY, MARATHA_FAMILY, MUGHAL_FAMILY, RULER_KEYS
from rag.engine.validate import unsupported_named_items
from rag.llm.client import LlmError, complete
from rag.prompts.econtent import ECONTENT_SYSTEM
from rag.prompts.tutor import KANNADA_UNAVAILABLE, refusal_text
from rag.vectorstore.retrieve import retrieve_primary

ALLOWED_KEYS = (
    "title",
    "introduction",
    "learning_objectives",
    "detailed_explanation",
    "important_people",
    "important_terms",
    "timeline",
    "main_events",
    "key_points",
    "exam_questions",
    "mcqs",
    "revision",
    "section_citations",
    "textbook_source_pages",
)

PLACEHOLDER_RE = re.compile(r"^\s*(null|none|\{\}|\[\]|todo|tbd|n/a)\s*$", re.I)
YEAR_RE = re.compile(r"\b(1[2-8]\d{2})(?:\s*[-–]\s*(1[2-8]\d{2}))?\b")
META_RE = re.compile(
    r"(?i)\b(chroma|evidence pack|vector database|retrieval|chunks?|RAG|Ollama|LLM|nomic-embed|according to the evidence)\b"
)

TERM_PATTERNS = (
    ("Din-e-Ilahi", ("din-e-ilahi", "din e ilahi", "dine ilahi", "din-i-ilahi")),
    ("Mansabdari", ("mansabdari",)),
    ("Mansab", ("mansab",)),
    ("Ashtapradhan", ("ashtapradhan", "ashapradhan")),
    ("Chauth", ("chauth",)),
    ("Sardeshmukhi", ("sardeshmukhi",)),
    ("Guerrilla warfare", ("guerrilla", "guerilla")),
    ("Taj Mahal", ("taj mahal", "tajmahal")),
    ("Swarajya", ("swarajya",)),
    ("Jagir", ("jagir", "jahagir")),
    ("Peshwa", ("peshwa",)),
    ("Vakil", ("vakil",)),
    ("Diwan", ("diwan",)),
    ("Saraighat", ("saraighat",)),
    ("Charaideo", ("charaideo",)),
)

ECONTENT_TOP_K = 16
SECTION_TIMEOUT = 75

EXAM_SPEC = {
    "keys": ("exam_questions", "mcqs"),
    "instruction": (
        "Write 3 exam_questions as objects {type,question,answer} with types "
        "very_short, short, and descriptive, and 2 mcqs as {question,options,answer}. "
        "Use only textbook facts in the passages. Distractor options must also be names or terms from the passages. "
        "Dates only if they appear in the passages."
    ),
    "max_tokens": 420,
}


def generate_econtent(topic: str, language: str = "en") -> dict:
    language = "kn" if language == "kn" else "en"
    topic = normalize_question(topic)
    if language == "kn" or looks_kannada(topic):
        refused = _refused("kn", topic, [], [])
        refused["answer"] = KANNADA_UNAVAILABLE
        refused["validation_reason"] = "kannada_corpus_unavailable"
        return refused
    if classify_casual(topic) or looks_like_injection(topic):
        return _refused(language, topic, [], [])
    retrieval_query = topic
    primary_hits = retrieve_primary(retrieval_query, top_k=ECONTENT_TOP_K, language="en")
    pack = build_evidence_pack(topic, retrieval_query, "BROAD_TOPIC", raw_hits=primary_hits)
    primary_selected = pack.chunks
    if not evidence_is_sufficient(primary_selected) or not evidence_matches_topic(
        topic, retrieval_query, primary_selected
    ):
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    covered = generate_from_plan(topic, primary_selected, "BROAD_TOPIC")
    plan = filter_plan(topic, build_coverage_plan(primary_selected))
    detailed = _clean_student_text(covered.get("answer") or "")
    if not detailed.strip():
        detailed = readable_extract(primary_selected, 8)
    if not detailed.strip():
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    allowed_pages = _pages(primary_selected)
    content = _assemble_module(topic, plan, detailed)
    _maybe_exam_from_model(topic, plan, primary_selected, content)
    _fill_exam_fallback(content, plan)
    content = _sanitize_content(content)
    content = _validate_section_citations(content, plan, primary_selected, allowed_pages, covered)

    if not _usable(content.get("detailed_explanation")):
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    used_pages = list(content.get("textbook_source_pages") or [])
    sources = _sources(
        [
            item
            for item in primary_selected
            if _page(item) in set(used_pages)
        ]
    )
    if not sources:
        sources = _sources(supporting_evidence(content["detailed_explanation"], primary_selected, min_overlap=1))
    return {
        "answer": "",
        "title": content.get("title") or topic,
        "language": language,
        "grounded": True,
        "content": content,
        "sources": sources,
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(primary_hits),
        "selected_chunk_ids": [item["chunk_id"] for item in primary_selected],
        "used_supplementary": False,
        "evidence_pack": pack.as_public(),
        "coverage": {
            "plan": covered.get("plan"),
            "grade": (covered.get("coverage") or {}).get("grade"),
            "missing": (covered.get("coverage") or {}).get("missing"),
            "omitted_sections": [
                key for key in ("timeline", "important_terms", "mcqs", "exam_questions") if not content.get(key)
            ],
        },
    }


def _assemble_module(topic: str, plan, detailed: str) -> dict:
    titles = [group.title for group in plan]
    people = _people_from_plan(plan)
    terms = _terms_from_plan(plan)
    timeline, events = _timeline_from_plan(plan)
    key_points = [readable_extract(group.chunks, 1) for group in plan[:6]]
    key_points = [_clean_student_text(point) for point in key_points if point]
    intro = _introduction(topic, titles)
    objectives = [
        f"Identify the main people and topics in this Class 9 lesson on {topic}."
    ]
    for title in titles[:5]:
        objectives.append(f"Explain what the Class 9 textbook says about {title}.")
    if terms:
        objectives.append("Recall important terms from this lesson.")
    revision = " ".join(key_points[:4]) if key_points else detailed[:700]
    content = {
        "title": f"Class 9 learning module: {topic}",
        "introduction": intro,
        "learning_objectives": objectives[:6],
        "detailed_explanation": detailed,
        "key_points": key_points,
        "revision": _clean_student_text(revision),
    }
    if people:
        content["important_people"] = people
    if terms:
        content["important_terms"] = terms
    if timeline:
        content["timeline"] = timeline
    if events:
        content["main_events"] = events
    return content


def _introduction(topic: str, titles: list[str]) -> str:
    if not titles:
        named = topic
    elif len(titles) == 1:
        named = titles[0]
    elif len(titles) == 2:
        named = f"{titles[0]} and {titles[1]}"
    else:
        named = ", ".join(titles[:-1]) + f", and {titles[-1]}"
    return (
        f"This Class 9 learning module on {topic} is based only on the Karnataka textbook. "
        f"It explains {named} in simple English so you can revise for class and exams."
    )


def _people_from_plan(plan) -> list[dict]:
    people = []
    seen = set()
    for group in plan:
        if group.key not in RULER_KEYS and group.key not in {"peshwa"}:
            extra = _named_people_in_group(group)
            people.extend(extra)
            continue
        note = _clean_student_text(readable_extract(group.chunks, 1))
        if not note:
            continue
        name = group.title
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        people.append({"name": name, "note": note[:280], "pages": list(group.pages)})
    return people


def _named_people_in_group(group) -> list[dict]:
    blob = " ".join(item.get("text") or "" for item in group.chunks).lower()
    found = []
    mapping = (("sukaphaa", "Sukaphaa"), ("lachit", "Lachit Borphukan"), ("gadadhar", "Gadadhar Singha"))
    for needle, label in mapping:
        if needle in blob:
            note = _sentence_with(group.chunks, needle)
            if note:
                found.append({"name": label, "note": note[:280], "pages": list(group.pages)})
    return found


FAMILY_TERMS = {
    "ahom": {"Saraighat", "Charaideo"},
    "mughal": {"Din-e-Ilahi", "Mansabdari", "Mansab", "Taj Mahal", "Jagir", "Vakil", "Diwan"},
    "maratha": {
        "Ashtapradhan",
        "Chauth",
        "Sardeshmukhi",
        "Guerrilla warfare",
        "Swarajya",
        "Peshwa",
        "Jagir",
    },
}


def _plan_families(plan) -> set[str]:
    keys = {group.key for group in plan}
    families = set()
    if keys & AHOM_FAMILY:
        families.add("ahom")
    if keys & (MUGHAL_FAMILY | {"sher"}):
        families.add("mughal")
    if keys & MARATHA_FAMILY:
        families.add("maratha")
    return families


def _terms_from_plan(plan) -> list[dict]:
    families = _plan_families(plan)
    allowed = set()
    for family in families:
        allowed |= FAMILY_TERMS.get(family, set())
    if families == {"ahom"}:
        allowed = FAMILY_TERMS["ahom"]
    terms = []
    seen = set()
    for label, needles in TERM_PATTERNS:
        if allowed and label not in allowed:
            continue
        for group in plan:
            blob = " ".join((item.get("text") or "").lower() for item in group.chunks)
            if not any(needle in blob for needle in needles):
                continue
            if families == {"ahom"} and group.key != "ahom":
                continue
            meaning = _sentence_with(group.chunks, needles[0])
            if not meaning or label.lower() in seen:
                continue
            seen.add(label.lower())
            terms.append({"term": label, "meaning": meaning[:280], "pages": list(group.pages)})
            break
    return terms


def _timeline_from_plan(plan) -> tuple[list[dict], list[str]]:
    timeline = []
    events = []
    seen = set()
    for group in plan:
        for item in group.chunks:
            text = " ".join((item.get("text") or "").split())
            for sent in re.split(r"(?<=[.!?])\s+", text):
                match = YEAR_RE.search(sent)
                if not match:
                    continue
                year = match.group(1)
                if int(year) > 1850:
                    continue
                key = sent[:80].lower()
                if key in seen or len(sent.split()) < 6:
                    continue
                seen.add(key)
                when = match.group(0).replace("–", "-")
                page = _page(item)
                entry = {"when": when, "event": sent.strip()[:220], "pages": [page] if page is not None else list(group.pages)}
                timeline.append(entry)
                events.append(sent.strip()[:220])
                if len(timeline) >= 6:
                    return timeline, events
    if len(timeline) < 2:
        return [], events[:6]
    return timeline, events


def _sentence_with(chunks: list[dict], needle: str) -> str:
    for item in chunks:
        text = " ".join((item.get("text") or "").split())
        for sent in re.split(r"(?<=[.!?])\s+", text):
            if needle.lower() in sent.lower() and len(sent.split()) >= 6:
                return _clean_student_text(sent.strip())
    return readable_extract(chunks, 1)


def _maybe_exam_from_model(topic: str, plan, evidence: list[dict], content: dict) -> None:
    packed = _pack(_diverse_chunks(plan, 6) or evidence[:6], "TEXTBOOK")
    parsed = _ask_section(topic, EXAM_SPEC, packed, evidence)
    if not parsed:
        parsed = _ask_section(topic, EXAM_SPEC, packed, evidence, strict=True)
    if not parsed:
        return
    questions = _clean_exam(parsed.get("exam_questions"), evidence)
    mcqs = _clean_mcqs(parsed.get("mcqs"), evidence, plan)
    if questions:
        content["exam_questions"] = questions
    if mcqs:
        content["mcqs"] = mcqs


def _fill_exam_fallback(content: dict, plan) -> None:
    people = content.get("important_people") or []
    terms = content.get("important_terms") or []
    if not content.get("exam_questions"):
        questions = []
        if people:
            questions.append(
                {
                    "type": "very_short",
                    "question": f"Who was {people[0]['name']}?",
                    "answer": people[0].get("note") or people[0]["name"],
                    "pages": people[0].get("pages") or [],
                }
            )
        if terms:
            questions.append(
                {
                    "type": "short",
                    "question": f"What was {terms[0]['term']} according to the Class 9 textbook?",
                    "answer": terms[0].get("meaning") or terms[0]["term"],
                    "pages": terms[0].get("pages") or [],
                }
            )
        if plan:
            group = plan[0] if len(plan) == 1 else plan[min(1, len(plan) - 1)]
            answer = readable_extract(group.chunks, 3)
            if answer:
                questions.append(
                    {
                        "type": "descriptive",
                        "question": f"Explain {group.title} as given in the Class 9 textbook.",
                        "answer": answer,
                        "pages": list(group.pages),
                    }
                )
        if questions:
            content["exam_questions"] = questions
    if not content.get("mcqs"):
        names = [item["name"] for item in people if item.get("name")]
        if len(names) >= 3:
            correct = names[0]
            options = names[:4]
            content["mcqs"] = [
                {
                    "question": f"Which person is described in this Class 9 lesson in the {correct} section?",
                    "options": options,
                    "answer": correct,
                    "pages": people[0].get("pages") or [],
                }
            ]
            if len(names) >= 4:
                content["mcqs"].append(
                    {
                        "question": f"Which of these people is covered in this Class 9 lesson besides {correct}?",
                        "options": names[1:5] if len(names) > 4 else names[1:4] + [names[0]],
                        "answer": names[1],
                        "pages": people[1].get("pages") or [],
                    }
                )


def _clean_exam(raw, evidence: list[dict]) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question or not answer or PLACEHOLDER_RE.match(answer):
            continue
        blob = json.dumps({"q": question, "a": answer}, ensure_ascii=False)
        if unsupported_named_items(blob, evidence):
            continue
        pages = _pages(supporting_evidence(blob, evidence, min_overlap=1))
        out.append({"type": item.get("type") or "short", "question": question, "answer": answer, "pages": pages})
        if len(out) >= 3:
            break
    return out


def _clean_mcqs(raw, evidence: list[dict], plan) -> list[dict]:
    if not isinstance(raw, list):
        return []
    blob_all = " ".join(item.get("text") or "" for item in evidence).lower()
    allowed_names = {group.title.lower() for group in plan}
    for aliases in TOPIC_ALIASES.values():
        for alias in aliases:
            if alias.isascii():
                allowed_names.add(alias.lower())
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        options = item.get("options")
        if not isinstance(options, list):
            continue
        options = [str(opt).strip() for opt in options if str(opt).strip()]
        if not question or not answer or len(options) < 3:
            continue
        if answer.lower() not in blob_all and answer.lower() not in {opt.lower() for opt in options}:
            continue
        if not any(answer.lower() == opt.lower() or answer.lower() in opt.lower() for opt in options):
            continue
        if unsupported_named_items(json.dumps(item, ensure_ascii=False), evidence):
            continue
        pages = _pages(supporting_evidence(question + " " + answer, evidence, min_overlap=1))
        out.append({"question": question, "options": options[:4], "answer": answer, "pages": pages})
        if len(out) >= 2:
            break
    return out


def _validate_section_citations(content: dict, plan, chunks: list[dict], allowed_pages: list[int], covered: dict) -> dict:
    allowed = set(allowed_pages)
    citations = {}
    detailed_pages = []
    for pages in (covered.get("section_pages") or {}).values():
        detailed_pages.extend(pages or [])
    if not detailed_pages:
        detailed_pages = _pages(supporting_evidence(content.get("detailed_explanation") or "", chunks, min_overlap=1))
    citations["Detailed explanation"] = _filter_pages(detailed_pages, allowed)
    citations["Introduction"] = _filter_pages(detailed_pages[:4], allowed)
    for group in plan:
        citations[group.title] = _filter_pages(group.pages, allowed)
    for person in content.get("important_people") or []:
        person["pages"] = _filter_pages(person.get("pages") or [], allowed)
        if person.get("name") and person["pages"]:
            citations[person["name"]] = person["pages"]
        elif not person.get("pages"):
            person["pages"] = citations.get(person.get("name") or "", [])
    for term in content.get("important_terms") or []:
        term["pages"] = _filter_pages(term.get("pages") or [], allowed)
        if term.get("term") and term["pages"]:
            citations[term["term"]] = term["pages"]
    for row in content.get("timeline") or []:
        row["pages"] = _filter_pages(row.get("pages") or [], allowed)
    for row in content.get("exam_questions") or []:
        row["pages"] = _filter_pages(row.get("pages") or [], allowed)
    for row in content.get("mcqs") or []:
        row["pages"] = _filter_pages(row.get("pages") or [], allowed)
    citations = {key: pages for key, pages in citations.items() if pages}
    content["section_citations"] = citations
    used = sorted({page for pages in citations.values() for page in pages})
    content["textbook_source_pages"] = used
    return content


def _filter_pages(pages, allowed: set[int]) -> list[int]:
    out = []
    for page in pages or []:
        try:
            value = int(page)
        except (TypeError, ValueError):
            continue
        if value in allowed and value not in out:
            out.append(value)
    return out


def _sanitize_content(content: dict) -> dict:
    cleaned = {}
    for key in ALLOWED_KEYS:
        value = _scrub(content.get(key))
        if _usable(value):
            cleaned[key] = value
    return cleaned


def _scrub(value):
    if isinstance(value, str):
        text = META_RE.sub("", value)
        text = re.sub(r" {2,}", " ", text).strip()
        if PLACEHOLDER_RE.match(text):
            return ""
        return text
    if isinstance(value, list):
        return [item for item in (_scrub(item) for item in value) if _usable(item)]
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items() if _usable(_scrub(item)) or key in {"pages", "options"}}
    return value


def _diverse_chunks(plan_or_chunks, limit: int) -> list[dict]:
    if plan_or_chunks and hasattr(plan_or_chunks[0], "chunks"):
        buckets = [list(group.chunks) for group in plan_or_chunks]
        out = []
        while len(out) < limit and any(buckets):
            for bucket in buckets:
                if bucket:
                    out.append(bucket.pop(0))
                if len(out) >= limit:
                    break
        return out
    return list(plan_or_chunks)[:limit]


def _refused(language: str, retrieval_query: str, hits: list, selected: list) -> dict:
    base = _unavailable(language, retrieval_query, hits, selected)
    base["title"] = ""
    base["content"] = None
    return base


def _pack(items: list[dict], label: str) -> str:
    if not items:
        return f"[{label}] (none)"
    return "\n".join(
        f"[{label}; printed_page={item.get('printed_page_number') or item.get('textbook_page_number')}]\n"
        f"{(item.get('text') or '')[:1100]}"
        for item in items
    )


def _ask_section(topic: str, spec: dict, packed: str, evidence: list[dict], strict: bool = False) -> dict:
    keys = list(spec["keys"])
    extra = " If evidence is thin, omit the key. JSON object only."
    if strict:
        extra = " STRICT: omit any claim not clearly in the evidence. JSON object only."
    user = (
        f"Output language: en\n"
        f"Student topic: {topic}\n"
        f"Fill ONLY these JSON keys: {json.dumps(keys)}\n"
        f"{spec['instruction']}{extra}\n\n"
        f"Textbook passages:\n{packed}\n"
    )
    try:
        raw = complete(
            [
                {"role": "system", "content": ECONTENT_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.0 if strict else 0.1,
            max_tokens=spec.get("max_tokens", 350),
            timeout=SECTION_TIMEOUT,
        )
    except (LlmError, TimeoutError, OSError):
        return {}
    parsed = _parse_content(raw)
    kept = {key: parsed[key] for key in keys if key in parsed}
    blob = json.dumps(kept, ensure_ascii=False)
    if unsupported_named_items(blob, evidence):
        return {}
    return kept


def _parse_content(raw: str) -> dict:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    cleaned = {}
    for key in ALLOWED_KEYS:
        value = parsed.get(key)
        if _usable(value):
            cleaned[key] = value
    return cleaned


def _usable(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and not PLACEHOLDER_RE.match(value)
    if isinstance(value, list):
        return any(_usable(item) for item in value)
    if isinstance(value, dict):
        return any(key not in {"pages", "options"} and _usable(item) for key, item in value.items()) or bool(value.get("name") or value.get("term") or value.get("question"))
    return True


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pages(items: list[dict]) -> list[int]:
    out = []
    for item in items or []:
        page = _page(item) if isinstance(item, dict) else None
        if page is not None and page not in out:
            out.append(page)
    return out

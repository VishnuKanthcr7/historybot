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
from rag.engine.sanitize import sanitize_student_text, sanitize_structured
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
HEADING_JUNK_RE = re.compile(
    r"(?i)mughals?\s+in\s+india\s*(?:\([^)]*\))?|do you know this\??|"
    r"babarnama\s*[–-]\s*\([^)]*\)|unesco world heritage|new seven wonders of the word"
)
EVENT_HINTS = (
    "established",
    "wrote",
    "built",
    "construction",
    "imprisoned",
    "seized",
    "appointed",
    "ascended",
    "celebrated",
    "constructed",
    "defeated",
    "encouraged",
    "translated",
    "conquered",
    "launched",
    "campaign",
    "authority to collect",
    "war compensation",
    "administrative centre",
    "administrative center",
    "declared war",
    "re-established",
    "restored",
    "gained the authority",
    "escaped",
    "coronation",
    "assembled",
    "trained",
    "prison",
    "felicitated",
    "strengthened",
    "independent kingdom",
)
TERM_EXPLAIN_HINTS = (
    "system",
    "called",
    "known as",
    "means",
    "meant",
    "ranking",
    "was a",
    "were a",
    "is a",
    "are a",
    "consisted",
    "divided",
    "types of",
    "type of",
    "land tax",
    "taxation",
    "prime minister",
)

# Cues that only record collection/use events — not definitions of what the term IS.
TERM_EVENT_ONLY_CUES = (
    "authority to collect",
    "gained the authority",
    "permitted him to collect",
    "permitted to collect",
    "collect chauth",
    "collect sardeshmukhi",
    "to collect",
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
        "very_short answers must be ONE concise identification sentence (e.g. Who was X?). "
        "short answers: 1-2 brief textbook sentences. "
        "descriptive answers: 2-4 relevant textbook-supported detail sentences. "
        "Do not make every answer long. Use only textbook facts in the passages. "
        "Distractor options must also be names or terms from the passages. "
        "Dates only if they appear in the passages. "
        "For term questions (What was Chauth?), prefer definitional wording; "
        "if the passages only show how a term was used and never define it, say so plainly—"
        "do not invent rates or meanings."
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
    from rag.engine.classify import extract_topics
    from rag.engine.evidence import topic_supported_by_primary
    from rag.engine.pack import detect_entity

    entity_key = detect_entity(extract_topics(topic))
    supported = topic_supported_by_primary(topic)
    if supported is False:
        return _refused(language, retrieval_query, primary_hits, [])
    pack_type = "EXPLANATION" if entity_key else "BROAD_TOPIC"
    pack = build_evidence_pack(topic, retrieval_query, pack_type, raw_hits=primary_hits)
    primary_selected = pack.chunks
    if not evidence_is_sufficient(primary_selected) or not evidence_matches_topic(
        topic, retrieval_query, primary_selected
    ):
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    covered = generate_from_plan(topic, primary_selected, "EXPLANATION" if entity_key else "BROAD_TOPIC")
    plan = filter_plan(topic, build_coverage_plan(primary_selected))
    detailed = sanitize_student_text(_clean_student_text(covered.get("answer") or ""))
    if not detailed.strip():
        detailed = readable_extract(primary_selected, 8)
    if not detailed.strip():
        return _refused(language, retrieval_query, primary_hits, primary_selected)

    allowed_pages = _pages(primary_selected)
    content = _assemble_module(topic, plan, detailed, entity=pack.entity or entity_key)
    _maybe_exam_from_model(topic, plan, primary_selected, content)
    _fill_exam_fallback(content, plan)
    _repair_exam_questions(content, plan)
    # Re-apply pronoun clarity to exam answers added after assemble.
    content = _clarify_content(
        content,
        plan,
        pack.entity or entity_key,
        content.get("title") or topic,
    )
    content = _sanitize_content(content)
    # Drop any exam rows whose answers were scrubbed empty, then repair gaps.
    if content.get("exam_questions") is not None:
        content["exam_questions"] = [
            row
            for row in (content.get("exam_questions") or [])
            if isinstance(row, dict) and str(row.get("answer") or "").strip()
        ]
        if not content["exam_questions"]:
            content.pop("exam_questions", None)
            _fill_exam_fallback(content, plan)
        _repair_exam_questions(content, plan)
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



_PRONOUN_LEAD_RE = re.compile(
    r"^(But\s+|However,\s+|Then\s+|Thus\s+|Therefore,\s+|So\s+)?"
    r"(he|she|they|this|that|it)\b",
    re.I,
)
_GROUP_WORDS = {
    "marathas", "mughals", "portuguese", "siddhis", "ahoms", "british",
    "dutch", "french", "english", "people", "members",
}
_PRONOUN_STOP = {
    "The", "When", "After", "Before", "During", "While", "Although", "However",
    "Then", "Thus", "Therefore", "Due", "With", "In", "On", "At", "By", "From",
    "And", "But", "This", "That", "These", "Those", "His", "Her", "Their", "Its",
    "Hence", "Later", "Also", "Since", "Because", "Although", "India", "North",
    "South", "East", "West", "Class", "History", "Chapter",
}


def _known_person_names(plan=None, entity: str | None = None, display: str | None = None) -> list[str]:
    """Collect textbook person/ruler names for pronoun resolution (generic)."""
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = (name or "").strip(" ,.;:")
        if not name or len(name) < 3:
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(name)

    if display:
        add(display)
    if entity:
        from rag.engine.coverage import GROUP_TITLE

        add(GROUP_TITLE.get(entity) or entity.replace("_", " ").title())
        for alias in TOPIC_ALIASES.get(entity, ()):
            if alias.isascii() and " " in alias or alias[:1].isupper():
                add(alias.title() if alias.islower() else alias)
    for aliases in TOPIC_ALIASES.values():
        for alias in aliases:
            if not alias.isascii():
                continue
            if " " in alias or "-" in alias:
                add(alias.title() if alias.islower() else alias)
    # Frequent Class 9 actors that appear as pronoun antecedents.
    for extra in (
        "Nizam-ul-Mulk",
        "Nizam",
        "Bahadur Shah I",
        "Aurangzeb",
        "Shahu",
        "Tarabai",
        "Sambhaji",
        "Balaji Vishwanath",
        "Sadashivrao Bhau",
        "Ahmed Shah Abdali",
        "Hyder Ali",
        "Safdarjung",
    ):
        add(extra)
    for group in plan or []:
        title = getattr(group, "title", None)
        if title:
            add(str(title))
    # Longest first so "Baji Rao I" wins over "Baji".
    names.sort(key=lambda n: len(n), reverse=True)
    return names


def _names_in_sentence(sent: str, known: list[str]) -> list[str]:
    low = (sent or "").lower()
    found = []
    covered = []
    for name in known:
        needle = name.lower()
        # Word-boundary-ish match so "Nizam" does not hit inside "Nizam-ul-Mulk".
        pattern = r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])"
        if not re.search(pattern, low):
            continue
        # Skip shorter names already spanned by a longer match.
        span = re.search(pattern, low)
        if span and any(span.start() >= a and span.end() <= b for a, b in covered):
            continue
        found.append(name)
        if span:
            covered.append((span.start(), span.end()))
    return found


def _last_singular_actor(sent: str, known: list[str]) -> str | None:
    """Best-effort singular person antecedent from a prior sentence.

    Prefer the rightmost person name by character position (usually the
    subject of the final clause), skipping group labels.
    """
    low = (sent or "").lower()
    if not low:
        return None
    positioned: list[tuple[int, str]] = []
    for name in known:
        needle = name.lower()
        if needle in _GROUP_WORDS:
            continue
        pattern = r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])"
        for match in re.finditer(pattern, low):
            positioned.append((match.start(), name))
    if not positioned:
        return None
    # Rightmost match wins; if ties, longer name wins.
    positioned.sort(key=lambda row: (row[0], len(row[1])))
    return positioned[-1][1]


def _clarify_pronoun_sentence(
    sent: str,
    prior: str | None,
    known: list[str],
    default_subject: str | None = None,
) -> str | None:
    """Resolve leading/ambiguous he/she/they/this/that/it using adjacent evidence.

    Returns None when the sentence should be dropped (unresolvable dangling pronoun).
    Does not invent names outside known/default subjects from textbook evidence.
    """
    sent = (sent or "").strip()
    if not sent:
        return sent
    m = _PRONOUN_LEAD_RE.match(sent)
    if not m:
        # Mid-sentence "this" without a noun: light touch only for "Due to this," / "In addition to this,"
        if re.match(r"^(Due to this|In addition to this|Because of this)\b", sent, re.I):
            antecedent_event = None
            if prior and re.search(r"\bbattle\b", prior, re.I):
                antecedent_event = "the battle"
            elif prior and re.search(r"\bwar\b", prior, re.I):
                antecedent_event = "the war"
            if antecedent_event:
                sent = re.sub(
                    r"^(Due to this|In addition to this|Because of this)\b",
                    lambda mm: mm.group(1).replace(" this", f" {antecedent_event}"),
                    sent,
                    count=1,
                    flags=re.I,
                )
        # Resolve mid-sentence he/she when no person is named in the sentence and
        # the referent is clear from prior sentence or the module subject.
        # Skip hostile "lost to the X" cases when default_subject is from that side.
        if re.search(r"\b(he|she)\b", sent, re.I) and not _names_in_sentence(sent, known):
            actor = _last_singular_actor(prior or "", known) if prior else None
            if not actor:
                actor = default_subject
            if actor:
                hostile = re.search(
                    r"\b(he|she)\s+lost\s+to\s+the\s+(marathas|mughals)\b",
                    sent,
                    re.I,
                )
                if hostile and actor.lower() in hostile.group(0).lower():
                    return None if _PRONOUN_LEAD_RE.match(sent) else sent
                sent = re.sub(r"\bhe\b", actor, sent, count=1, flags=re.I)
                # Only replace she if we used she match first; keep simple one-pass for he/she:
                if re.search(r"\bshe\b", sent, re.I) and not re.search(re.escape(actor), sent):
                    sent = re.sub(r"\bshe\b", actor, sent, count=1, flags=re.I)
        return sent

    pronoun = m.group(2).lower()
    prefix = m.group(1) or ""
    rest = sent[m.end() :].lstrip()
    actor = _last_singular_actor(prior or "", known) if prior else None
    if pronoun in {"he", "she"}:
        # Without an adjacent antecedent, do NOT guess the module subject —
        # that invents the wrong person (e.g. Nizam's "he lost" vs Baji Rao).
        if not actor:
            return None
        rebuilt = f"{prefix}{actor} {rest}".strip()
        if rebuilt and rebuilt[0].islower():
            rebuilt = rebuilt[0].upper() + rebuilt[1:]
        # Avoid "But But" style; normalize space.
        rebuilt = re.sub(r"\s+", " ", rebuilt)
        return rebuilt
    if pronoun == "they":
        # Prefer a group name from the prior sentence.
        groups = [
            n for n in _names_in_sentence(prior or "", known)
            if n.lower() in _GROUP_WORDS or n.lower().endswith("s")
        ]
        if groups:
            rebuilt = f"{prefix}{groups[-1]} {rest}".strip()
            return rebuilt[0].upper() + rebuilt[1:] if rebuilt else None
        # Unclear plural — drop rather than guess.
        return None
    if pronoun in {"this", "that", "it"}:
        # Dangling demonstrative subject: drop unless we can name a prior battle/war/event noun.
        if prior and re.search(r"\b(battle|war|treaty|agreement|campaign)\b", prior, re.I):
            noun = re.search(r"\b(battle|war|treaty|agreement|campaign)\b", prior, re.I)
            label = f"the {noun.group(1).lower()}"
            rebuilt = f"{prefix}{label} {rest}".strip()
            return rebuilt[0].upper() + rebuilt[1:] if rebuilt else None
        return None
    return sent


def _clarify_text(
    text: str,
    known: list[str],
    default_subject: str | None = None,
) -> str:
    """Clarify ambiguous pronouns across a multi-sentence student text block."""
    if not (text or "").strip():
        return text or ""
    # Preserve bullet / newline structure for revision lists.
    lines = text.split("\n")
    out_lines: list[str] = []
    for line in lines:
        raw = line
        prefix = ""
        body = raw
        bullet = re.match(r"^(\s*(?:[-*\u2022]\s+|\d+\.\s+))", raw)
        if bullet:
            prefix = bullet.group(1)
            body = raw[len(prefix) :]
        parts = re.split(r"(?<=[.!?])\s+", body.strip()) if body.strip() else []
        clarified: list[str] = []
        prev = None
        for part in parts:
            part = part.strip()
            if not part:
                continue
            fixed = _clarify_pronoun_sentence(part, prev, known, default_subject)
            if not fixed:
                continue
            clarified.append(fixed if fixed.endswith((".", "!", "?")) or len(parts) == 1 else fixed)
            prev = fixed
        if not clarified and body.strip():
            # Single fragment without terminal punct.
            fixed = _clarify_pronoun_sentence(body.strip(), None, known, default_subject)
            if fixed:
                out_lines.append(prefix + fixed)
            continue
        joined = " ".join(clarified).strip()
        out_lines.append(prefix + joined if joined else raw.rstrip())
    return "\n".join(out_lines).strip()

def _clarify_content(content: dict, plan, entity: str | None, display: str) -> dict:
    known = _known_person_names(plan, entity=entity, display=display)
    default = display
    for key in (
        "introduction",
        "detailed_explanation",
        "revision",
    ):
        if content.get(key):
            content[key] = _clarify_text(content[key], known, default)
    for key in ("key_points", "main_events", "learning_objectives"):
        rows = content.get(key)
        if isinstance(rows, list):
            content[key] = [
                _clarify_text(item, known, default) if isinstance(item, str) else item
                for item in rows
                if not isinstance(item, str) or _clarify_text(item, known, default)
            ]
            content[key] = [item for item in content[key] if item]
    for person in content.get("important_people") or []:
        if person.get("note"):
            person["note"] = _clarify_text(person["note"], known, person.get("name") or default)
    for term in content.get("important_terms") or []:
        if term.get("meaning"):
            term["meaning"] = _clarify_text(term["meaning"], known, default)
    for row in content.get("timeline") or []:
        if row.get("event"):
            row["event"] = _clarify_text(row["event"], known, default)
    for row in content.get("exam_questions") or []:
        if row.get("answer"):
            row["answer"] = _clarify_text(row["answer"], known, default)
    return content


def _first_sentence(text: str) -> str:
    text = _strip_sentence_prefix((text or "").strip())
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    sent = (parts[0] if parts else text).strip()
    if sent and not sent.endswith((".", "!", "?")):
        sent += "."
    return sent


def _limit_sentences(text: str, max_sentences: int) -> str:
    text = _strip_sentence_prefix((text or "").strip())
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    kept = parts[: max(1, max_sentences)]
    out = " ".join(kept).strip()
    if out and not out.endswith((".", "!", "?")):
        out += "."
    return out


def _shape_exam_answer(answer: str, qtype: str, question: str = "") -> str:
    """Enforce very_short / short / descriptive length styles without new facts."""
    answer = _strip_sentence_prefix(sanitize_student_text(answer or ""))
    if not answer:
        return ""
    qtype = (qtype or "short").lower().strip()
    qlow = (question or "").lower()
    if qtype in {"very_short", "very short", "vsa"} or qlow.startswith("who was") or qlow.startswith("who is"):
        # Prefer a direct identification / role sentence over a long multi-event opener.
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", answer) if p.strip()]
        role_cues = (
            "appointed as", "peshwa", "emperor", "king", "sultan", "chatrapati",
            "coronation", "was the", "were the", "known as", "called",
        )
        best = None
        for part in parts:
            low = part.lower()
            if any(cue in low for cue in role_cues) and len(part.split()) <= 30:
                best = part
                break
        if best is None and parts:
            # Shortest reasonably informative sentence.
            ranked = sorted(parts, key=lambda s: len(s.split()))
            best = next((s for s in ranked if len(s.split()) >= 4), parts[0])
        chosen = best or answer
        if chosen and not chosen.endswith((".", "!", "?")):
            chosen += "."
        return chosen
    if qtype in {"short", "sa"}:
        return _limit_sentences(answer, 2)
    if qtype in {"descriptive", "long", "la"}:
        return _limit_sentences(answer, 4)
    return _limit_sentences(answer, 2)


def _assemble_module(topic: str, plan, detailed: str, entity: str | None = None) -> dict:
    if entity:
        plan = [group for group in plan if _group_matches_entity(group, entity)] or plan
    display = _display_topic_name(topic, entity, plan)
    titles = [group.title for group in plan]
    used: set[str] = set()
    # Terms first so role definitions (e.g. Peshwa) keep their defining sentences.
    terms = _terms_from_plan(plan, used=used)
    people = _people_from_plan(plan, entity=entity, used=used)
    timeline, events = _timeline_from_plan(plan, entity=entity, used=used)
    key_points = _key_points_from_plan(plan, entity=entity, used=used)
    detailed = _enrich_detailed(detailed, plan, entity)
    intro = _introduction(display, titles)
    objectives = [
        f"Identify the main people connected with {display} in the Class 9 textbook.",
        f"Explain the major events and facts the Class 9 textbook records about {display}.",
    ]
    if terms:
        objectives.append(f"Define important terms linked to {display} using textbook meanings.")
    if timeline or events:
        objectives.append(f"Recall the chronological main events related to {display}.")
    objectives.append(f"Revise the key points about {display} for class and exams.")
    revision = _revision_from_points(
        key_points, people, events=events, terms=terms, display=display
    )
    content = {
        "title": f"Class 9 History: {display}",
        "introduction": intro,
        "learning_objectives": objectives[:6],
        "detailed_explanation": detailed,
        "key_points": key_points,
        "revision": revision,
    }
    if people:
        content["important_people"] = people
    if terms:
        content["important_terms"] = terms
    if timeline:
        content["timeline"] = timeline
    if events:
        content["main_events"] = events
    content = _clarify_content(content, plan, entity, display)
    return content


def _introduction(topic: str, titles: list[str]) -> str:
    focus = topic
    if titles:
        extra = [t for t in titles if t.lower() not in focus.lower()]
        if extra:
            if len(extra) == 1:
                named = extra[0]
            elif len(extra) == 2:
                named = f"{extra[0]} and {extra[1]}"
            else:
                named = ", ".join(extra[:-1]) + f", and {extra[-1]}"
            return (
                f"This Class 9 History module on {focus} is based only on the Karnataka textbook. "
                f"It covers {named} in clear English for classwork and exam revision."
            )
    return (
        f"This Class 9 History module on {focus} is based only on the Karnataka textbook. "
        f"It explains the main supported facts in clear English for classwork and exam revision."
    )


def _normalize_ocr_text(text: str) -> str:
    """Remove heading/OCR wrappers without adding new facts."""
    text = " ".join((text or "").split())
    text = re.sub(r"(?i)^.{0,120}new seven wonders of the word\.?\s*[\u201d\u201c\"]?\s*", "", text)
    text = HEADING_JUNK_RE.sub(" ", text)
    text = re.sub(r"(?i)(?:taj mahal:?\s*)+(?:the mughal king,?\s*)+", " ", text)
    text = re.sub(r"(?i)\bbabur,?\s*who established mughal\b", " ", text)
    text = re.sub(r"(?i)\b(?:babur|babar)(?:\s+(?:babur|babar))+\b", "Babur", text)
    text = re.sub(r"(?i)art and architecture\s*:\s*", "", text)
    # Strip raw chunk heading prefixes like "Baji rao I : " repeated mid-text
    text = re.sub(
        r"(?i)(?:(?<=^)|(?<=[.!?]\s))([A-Z][A-Za-z0-9 .\'-]{0,40}?)\s*:\s+",
        "",
        text,
    )
    text = re.sub(r"\b([A-Za-z][A-Za-z'\u2019-]{1,24})(?:\s+\1\b)+", r"\1", text)
    text = re.sub(r"\b(.{8,70}?)\b(?:\s+\1\b)+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" :,-")
    return text


def _is_student_sentence(text: str) -> bool:
    sent = (text or "").strip()
    sent = re.sub(r"(?i)^[A-Z][A-Za-z0-9 .\'-]{0,40}?\s*:\s+", "", sent).strip()
    words = sent.split()
    if len(words) < 7 or len(words) > 60:
        return False
    if not re.search(r"[.!?]$", sent):
        return False
    if re.match(r"^[a-z]", sent):
        return False
    if re.search(r"(?:\b[A-Za-z]\s){6,}", sent):
        return False
    if HEADING_JUNK_RE.search(sent):
        return False
    low = sent.lower()
    if "who established mughal" in low and "empire" not in low and "rule" not in low:
        return False
    if sent.lower().startswith(("chapter", "we will learn", "taj mahal:")):
        return False
    if re.search(r"\b(chroma|chunk_id|evidence pack)\b", sent, re.I):
        return False
    # Drop obvious OCR/splice debris from textbook extraction
    if re.search(r"\bthe thus\b", low):
        return False
    if re.search(r"\bexpanding the thus\b", low):
        return False
    if re.search(r"\bintention of expanding the\s+(?:thus|he)\b", low):
        return False
    if "glory of the baji rao" in low:
        return False
    # Reject near-duplicate glued OCR ("X not only ... X not only")
    if re.search(r"\b(.{12,40}?)\b(?:\s+\1\b)", low):
        # allow mild repeats; reject if a long phrase repeats
        if re.search(r"(\b\w+(?:\s+\w+){4,}\b).*\1", low):
            return False
    return True


def _iter_clean_sentences(chunks: list[dict], known_names: list[str] | None = None):
    seen = set()
    known = known_names or _known_person_names()
    for item in chunks or []:
        page = _page(item)
        raw = _normalize_ocr_text(item.get("text") or "")
        raw_parts = []
        for sent in re.split(r"(?<=[.!?])\s+", raw):
            sent = re.sub(r"(?i)^[A-Z][A-Za-z0-9 .\'-]{0,40}?\s*:\s+", "", sent.strip()).strip()
            if not sent:
                continue
            raw_parts.append(sent)
        clarified_parts: list[str] = []
        prev = None
        for sent in raw_parts:
            fixed = _clarify_pronoun_sentence(sent, prev, known, default_subject=None)
            if fixed is None:
                # Drop unresolvable dangling pronoun continuations.
                # Still advance prev from original if it named someone.
                if _names_in_sentence(sent, known):
                    prev = sent
                continue
            clarified_parts.append(fixed)
            prev = fixed
        for sent in clarified_parts:
            if not _is_student_sentence(sent if sent.endswith((".", "!", "?")) else sent + "."):
                # Keep already-valid sentences; probe with period if needed.
                if not _is_student_sentence(sent):
                    continue
            key = sent[:70].lower()
            if key in seen:
                continue
            seen.add(key)
            yield sent, page, item


def _score_person_sentence(sent: str, aliases: tuple[str, ...]) -> int:
    low = sent.lower()
    if not any(alias in low for alias in aliases if alias.isascii()):
        return 0
    score = 3
    if any(hint in low for hint in EVENT_HINTS):
        score += 2
    if low.startswith(tuple(alias for alias in aliases if alias.isascii())):
        score += 2
    return score


def _is_definitional_term_sentence(sent: str, needle: str) -> bool:
    """True when the sentence explains what the term IS (not only an event-use)."""
    low = (sent or "").lower()
    if needle not in low:
        return False
    if any(cue in low for cue in TERM_EVENT_ONLY_CUES) and not any(
        hint in low for hint in TERM_EXPLAIN_HINTS
    ):
        # Pure collection/authority event with no definitional wording.
        if not re.search(rf"{re.escape(needle)}\s*\(", low):
            return False
    if any(hint in low for hint in TERM_EXPLAIN_HINTS):
        return True
    if re.search(rf"{re.escape(needle)}\s*\([^)]{{0,40}}\)", low):
        return True
    if re.search(rf"\b(?:called|known as)\s+{re.escape(needle)}\b", low):
        return True
    if re.search(rf"\b{re.escape(needle)}\b(?:\s+\w+){{0,3}}\s+(?:was|were|is|are)\s+a\b", low):
        return True
    return False


def _is_event_only_term_sentence(sent: str, needle: str) -> bool:
    low = (sent or "").lower()
    if needle not in low:
        return False
    if _is_definitional_term_sentence(sent, needle):
        return False
    return any(cue in low for cue in TERM_EVENT_ONLY_CUES) or (
        "collect" in low and "tax" in low
    )


def _score_term_sentence(sent: str, needle: str) -> int:
    low = sent.lower()
    if needle not in low:
        return 0
    if "duties of the king" in low:
        return 0
    definitional = _is_definitional_term_sentence(sent, needle)
    event_only = _is_event_only_term_sentence(sent, needle)
    # Long name-lists without an explanatory cue are weak.
    if re.search(r",.+,.*\band\b", sent) and not definitional and not event_only:
        return 0
    if event_only and not definitional:
        # Keep a weak positive so callers can emit an honest non-definition note.
        return 1
    score = 1
    if definitional:
        score += 8
    elif any(
        cue in low
        for cue in ("appointed as", "minister", "warfare", "supervisors", "assist", "tax")
    ):
        score += 3
    if re.search(rf"\bthe {re.escape(needle)}", low):
        score += 2
    if low.startswith(needle):
        score += 2
    if re.search(rf"{re.escape(needle)}\s*\(", low):
        score += 3
    return score


def _pick_sentences(
    chunks: list[dict],
    aliases: tuple[str, ...],
    limit: int = 2,
    used: set[str] | None = None,
) -> tuple[str, list[int]]:
    ranked = []
    for sent, page, _item in _iter_clean_sentences(chunks):
        sent = _strip_sentence_prefix(sent)
        if not sent:
            continue
        score = _score_person_sentence(sent, aliases)
        if score <= 0:
            continue
        key = _sentence_key(sent)
        if used and key in used:
            score -= 5
        ranked.append((score, len(sent), sent, page))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    picked = []
    pages = []
    local: set[str] = set()
    for _score, _length, sent, page in ranked:
        key = _sentence_key(sent)
        if key in local:
            continue
        if used and key in used and picked:
            continue
        local.add(key)
        picked.append(sent)
        if page is not None and page not in pages:
            pages.append(page)
        if len(picked) >= limit:
            break
    return " ".join(picked), _sorted_pages(pages)


def _display_topic_name(topic: str, entity: str | None, plan) -> str:
    """Professional module title from entity/plan — never the raw user question."""
    from rag.engine.coverage import GROUP_TITLE

    if entity and GROUP_TITLE.get(entity):
        return GROUP_TITLE[entity]
    if plan:
        title = getattr(plan[0], "title", None)
        if title and len(str(title).split()) <= 8:
            return str(title)
    cleaned = re.sub(
        r"(?i)^(tell me about|explain|what is|who is|describe|write about)\s+",
        "",
        (topic or "").strip(),
    )
    cleaned = cleaned.strip(" ?.!,:")
    if cleaned and len(cleaned) <= 60 and not cleaned.endswith("?"):
        return cleaned.title() if cleaned.islower() else cleaned
    if entity:
        return entity.replace("_", " ").title()
    return "Class 9 History topic"


def _sentence_key(sent: str) -> str:
    return re.sub(r"\s+", " ", (sent or "").strip().lower())[:90]


def _strip_sentence_prefix(sent: str) -> str:
    sent = (sent or "").strip()
    sent = re.sub(r"(?i)^[A-Z][A-Za-z0-9 .\'-]{0,40}?\s*:\s+", "", sent)
    return sent.strip()


def _reserve_sentence(sent: str, used: set[str]) -> bool:
    key = _sentence_key(sent)
    if not key or key in used:
        return False
    used.add(key)
    return True


def _fact_pool(plan, entity: str | None = None) -> list[tuple[str, int | None]]:
    """Distinct clean textbook sentences for packing e-content sections."""
    pool: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    for group in plan or []:
        for sent, page, _item in _iter_clean_sentences(group.chunks):
            sent = _strip_sentence_prefix(sent)
            if not sent:
                continue
            if entity and not _packing_sentence_ok(sent, entity):
                continue
            key = _sentence_key(sent)
            if key in seen:
                continue
            seen.add(key)
            pool.append((sent, page))
    return pool


def _enrich_detailed(detailed: str, plan, entity: str | None) -> str:
    """Add unused major textbook facts to the explanation without inventing."""
    base = sanitize_student_text((detailed or "").strip())
    # Drop trailing incomplete fragment before a page label
    base = re.sub(
        r"(?i)\b(but also|and also|with the intention of(?: expanding)?(?: the)?)\s*(\[Pages? [^\]]+\])\s*$",
        r"\2",
        base,
    )
    base = re.sub(r"\s{2,}", " ", base).strip()
    used = {_sentence_key(s) for s in re.split(r"(?<=[.!?])\s+", base) if s.strip()}
    # Also mark shorter stems already covered in the prose
    base_low = base.lower()
    extras: list[str] = []
    for sent, _page in _fact_pool(plan, entity=entity):
        if not _reserve_sentence(sent, used):
            continue
        # Skip if most content words already appear in the explanation
        words = [w for w in re.findall(r"[a-z0-9]{4,}", sent.lower()) if w not in {"with", "from", "that", "this", "were", "have", "been"}]
        if words:
            hit = sum(1 for w in words if w in base_low)
            if hit / max(len(words), 1) >= 0.6:
                continue
        low = sent.lower()
        major = (
            any(h in low for h in EVENT_HINTS)
            or bool(YEAR_RE.search(sent))
            or any(h in low for h in TERM_EXPLAIN_HINTS)
            or "conquered" in low
            or "peshwa" in low
        )
        if not major:
            continue
        if len(sent.split()) < 8:
            continue
        extras.append(sent if sent.endswith((".", "!", "?")) else sent + ".")
        total_words = len(base.split()) + sum(len(x.split()) for x in extras)
        if total_words > 260 or len(extras) >= 5:
            break
    if not extras:
        return base
    add = " ".join(extras)
    if not base:
        return sanitize_student_text(add)
    m = re.search(r"(\s*\[Pages? [^\]]+\])\s*$", base)
    if m:
        core = base[: m.start()].rstrip()
        core = re.sub(r"(?i)\b(but also|and also)\s*$", "", core).rstrip(" ,;")
        if core and not core.endswith((".", "!", "?", "]")):
            core += "."
        return sanitize_student_text(f"{core} {add}{m.group(1)}")
    core = re.sub(r"(?i)\b(but also|and also)\s*$", "", base).rstrip(" ,;")
    if core and not core.endswith((".", "!", "?", "]")):
        core += "."
    return sanitize_student_text(f"{core} {add}")


def _format_term_meaning(term: str, sentences: list[str], definitional: bool = True) -> str:
    """Build a concise textbook-grounded meaning; avoid raw chunk prefixes.

    When only event-use evidence exists (no definitional wording), return an
    honest non-definition note instead of pasting the collection-event sentence
    as if it were a definition. Never invent rates or outside meanings.
    """
    cleaned = []
    needles = []
    for label, opts in TERM_PATTERNS:
        if label.lower() == term.lower():
            needles = list(opts)
            break
    if not needles:
        needles = [term.lower()]
    for sent in sentences:
        sent = _strip_sentence_prefix(sanitize_student_text(sent or ""))
        if not sent:
            continue
        if not sent.endswith((".", "!", "?")):
            sent = sent + "."
        cleaned.append(sent)
    if not cleaned:
        return ""
    if not definitional:
        use = ""
        for sent in cleaned:
            low = sent.lower()
            if not any(n in low for n in needles):
                continue
            # Prefer the shortest clause that still names the term.
            parts = re.split(r",\s+", sent.rstrip("."))
            hit = [p.strip() for p in parts if any(n in p.lower() for n in needles)]
            clause = hit[-1] if hit else sent.rstrip(".")
            clause = clause.strip(" ,;")
            # Reject awkward mid-phrase fragments ("Malwa and gained the authority...").
            bad_start = clause.lower().startswith(
                ("and ", "or ", "but ", "malwa ", "gujarat ", "with the intention")
            )
            if (
                bad_start
                or len(clause.split()) > 22
                or not re.search(r"\b(collect|tax|authority)\b", clause, re.I)
            ):
                return (
                    f"The Class 9 textbook does not give an explicit definition of {term}; "
                    f"it only records that {term} was collected as a tax in the events described for this topic."
                )
            if not clause.endswith((".", "!", "?")):
                clause += "."
            if clause and clause[0].islower():
                clause = clause[0].upper() + clause[1:]
            use = clause
            break
        if not use:
            return (
                f"The Class 9 textbook does not give an explicit definition of {term}; "
                f"it only records how it was used in this topic."
            )
        return (
            f"The Class 9 textbook does not give an explicit definition of {term}; "
            f"it only records how it was used. {use}"
        )
    primary = cleaned[0]
    low = primary.lower()
    term_l = term.lower()
    if len(cleaned) > 1 and _sentence_key(cleaned[1]) != _sentence_key(primary):
        # Prefer a second sentence only if it stays definitional.
        if any(_is_definitional_term_sentence(cleaned[1], n) for n in needles):
            primary = f"{primary} {cleaned[1]}"
    if term_l not in low and not any(term_l in c.lower() for c in cleaned):
        return f"{term}: {primary}"
    return primary



def _group_matches_entity(group, entity: str) -> bool:
    if not entity:
        return True
    key = getattr(group, "key", "") or ""
    if key == entity or key.startswith(f"{entity}:"):
        return True
    aliases = tuple(alias for alias in TOPIC_ALIASES.get(entity, (entity,)) if alias.isascii())
    blob = " ".join((item.get("text") or "") for item in (group.chunks or [])).lower()
    return any(alias in blob for alias in aliases)


def _sentence_about_entity(sent: str, entity: str | None) -> bool:
    if not entity:
        return True
    from rag.engine.entity import entity_subject_score

    score, _reason = entity_subject_score(sent, entity)
    if score >= 3:
        return True
    aliases = [alias for alias in TOPIC_ALIASES.get(entity, (entity,)) if alias.isascii()]
    low = (sent or "").lower()
    if not any(alias in low for alias in aliases):
        return False
    # Reject sentences dominated by a different ruler alias.
    from rag.engine.pack import dominant_ruler

    dominant = dominant_ruler(sent)
    return dominant in {None, entity}


def _packing_sentence_ok(sent: str, entity: str | None) -> bool:
    """E-content packing filter for an already entity-scoped plan.

    Keeps pronoun continuations ("he conquered...") from the same ruler section
    without inventing facts, while still rejecting other-ruler dominance.
    Does not change chat entity-boundary behavior.
    """
    if not entity:
        return True
    if _sentence_about_entity(sent, entity):
        return True
    from rag.engine.pack import dominant_ruler

    dominant = dominant_ruler(sent)
    if dominant and dominant != entity:
        return False
    # If another ruler alias is explicitly named, skip.
    from rag.engine.classify import TOPIC_ALIASES

    low = (sent or "").lower()
    for other, aliases in TOPIC_ALIASES.items():
        if other == entity:
            continue
        for alias in aliases:
            if alias.isascii() and len(alias) >= 4 and alias.lower() in low:
                # Allow shared context mentions of family terms; block other people names
                if other in {"maratha", "mughal", "ahom", "administration", "peshwa"}:
                    continue
                return False
    return True


def _people_from_plan(plan, entity: str | None = None, used: set[str] | None = None) -> list[dict]:
    people = []
    seen = set()
    used = used if used is not None else set()
    for group in plan:
        group_entity = group.key.split(":", 1)[0] if ":" in group.key else group.key
        is_rulerish = group_entity in RULER_KEYS or group_entity == "peshwa" or group.key in RULER_KEYS
        if entity and group_entity != entity and is_rulerish:
            continue
        if entity and group_entity != entity and not is_rulerish:
            extra = [
                row
                for row in _named_people_in_group(group)
                if _packing_sentence_ok(row.get("note") or "", entity)
            ]
            for row in extra:
                for part in re.split(r"(?<=[.!?])\s+", row.get("note") or ""):
                    _reserve_sentence(part, used)
            people.extend(extra)
            continue
        if not entity and not is_rulerish:
            people.extend(_named_people_in_group(group))
            continue
        if not is_rulerish:
            continue
        alias_key = group_entity if group_entity in TOPIC_ALIASES else (entity or group.key)
        aliases = tuple(
            alias for alias in TOPIC_ALIASES.get(alias_key, (alias_key,)) if alias.isascii()
        ) + (group.title.lower(),)
        note, pages = _pick_sentences(group.chunks, aliases, limit=3, used=used)
        note = _strip_sentence_prefix(note)
        # Ensure a role/office cue remains in the people note when the textbook has one
        role_cues = ("appointed as", "peshwa", "emperor", "king", "sultan", "chatrapati", "coronation")
        if note and not any(cue in note.lower() for cue in role_cues):
            for sent, page, _item in _iter_clean_sentences(group.chunks):
                sent = _strip_sentence_prefix(sent)
                if not any(cue in sent.lower() for cue in role_cues):
                    continue
                if entity and not _packing_sentence_ok(sent, entity):
                    continue
                note = f"{sent} {note}".strip()
                if page is not None and page not in pages:
                    pages = _sorted_pages(list(pages) + [page])
                break
        if not note or (entity and not _packing_sentence_ok(note, entity)):
            parts = []
            for sent, page, _item in _iter_clean_sentences(group.chunks):
                sent = _strip_sentence_prefix(sent)
                if entity and not _packing_sentence_ok(sent, entity):
                    continue
                if not _reserve_sentence(sent, used) and parts:
                    continue
                _reserve_sentence(sent, used)
                parts.append(sent)
                if page is not None and page not in pages:
                    pages.append(page)
                if len(parts) >= 3:
                    break
            note = " ".join(parts)
        if not note:
            continue
        for part in re.split(r"(?<=[.!?])\s+", note):
            _reserve_sentence(part, used)
        if entity:
            from rag.engine.coverage import GROUP_TITLE

            name = GROUP_TITLE.get(entity) or entity.replace("_", " ").title()
        else:
            name = group.title
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        note = sanitize_student_text(note)
        if len(note) > 480:
            cut = note[:480]
            if "." in cut:
                cut = cut.rsplit(".", 1)[0] + "."
            note = cut
        people.append(
            {
                "name": name,
                "note": note,
                "pages": pages or _sorted_pages(group.pages),
            }
        )
    return people


def _named_people_in_group(group) -> list[dict]:
    mapping = (("sukaphaa", "Sukaphaa"), ("lachit", "Lachit Borphukan"), ("gadadhar", "Gadadhar Singha"))
    found = []
    for needle, label in mapping:
        note, pages = _pick_sentences(group.chunks, (needle, label.lower()), limit=2)
        if note:
            found.append({"name": label, "note": note[:400], "pages": pages or _sorted_pages(group.pages)})
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


def _terms_from_plan(plan, used: set[str] | None = None) -> list[dict]:
    families = _plan_families(plan)
    allowed = set()
    for family in families:
        allowed |= FAMILY_TERMS.get(family, set())
    if families == {"ahom"}:
        allowed = FAMILY_TERMS["ahom"]
    terms = []
    seen = set()
    used = used if used is not None else set()
    for label, needles in TERM_PATTERNS:
        if allowed and label not in allowed:
            continue
        for group in plan:
            blob = " ".join((item.get("text") or "").lower() for item in group.chunks)
            if not any(needle in blob for needle in needles):
                continue
            if families == {"ahom"} and group.key != "ahom":
                continue
            ranked = []
            for sent, page, _item in _iter_clean_sentences(group.chunks):
                sent = _strip_sentence_prefix(sent)
                best = max(_score_term_sentence(sent, needle) for needle in needles)
                if best <= 0:
                    continue
                key = _sentence_key(sent)
                if key in used:
                    best -= 3
                ranked.append((best, sent, page))
            ranked.sort(reverse=True)
            if not ranked:
                continue
            # Prefer definitional sentences; fall back to event-only with honest note.
            def_rows = []
            event_rows = []
            for best, sent, page in ranked:
                if any(_is_definitional_term_sentence(sent, n) for n in needles):
                    def_rows.append((best, sent, page))
                elif best > 0 or any(_is_event_only_term_sentence(sent, n) for n in needles):
                    # Event-only may score <=0 after used-penalty; still usable for honest notes.
                    event_rows.append((max(best, 1), sent, page))
            pool = def_rows if def_rows else event_rows
            definitional = bool(def_rows)
            chosen: list[tuple[str, int | None]] = []
            local = set(used)
            for best, sent, page in pool:
                if chosen and best <= 0 and definitional:
                    continue
                if definitional:
                    if not _reserve_sentence(sent, local) and chosen:
                        continue
                    if _sentence_key(sent) not in local:
                        local.add(_sentence_key(sent))
                # Event-only honest notes may share a sentence across related terms.
                chosen.append((sent, page))
                # One sentence is enough for an honest non-definition note.
                limit = 2 if definitional else 1
                if len(chosen) >= limit:
                    break
            if not chosen:
                continue
            # Prefer fewer high-quality items: skip weak event-only terms that
            # are barely about the label (score 1 noise), unless the term is
            # clearly named in a collect/tax use sentence.
            if not definitional:
                top = chosen[0][0]
                if not any(_is_event_only_term_sentence(top, n) for n in needles):
                    continue
            meaning = _format_term_meaning(
                label, [s for s, _p in chosen], definitional=definitional
            )
            pages = _sorted_pages([p for _s, p in chosen if p is not None] or group.pages)
            if not meaning or label.lower() in seen:
                continue
            seen.add(label.lower())
            for s, _p in chosen:
                _reserve_sentence(s, used)
            # Honest notes can be a bit longer; keep room for the caveat.
            cap = 480 if not definitional else 420
            terms.append({"term": label, "meaning": meaning[:cap], "pages": pages})
            break
    return terms


def _timeline_from_plan(
    plan, entity: str | None = None, used: set[str] | None = None
) -> tuple[list[dict], list[str]]:
    timeline = []
    events = []
    seen = set()
    used = used if used is not None else set()
    for group in plan:
        for sent, page, _item in _iter_clean_sentences(group.chunks):
            sent = _strip_sentence_prefix(sent)
            if not _is_student_sentence(sent if sent.endswith((".", "!", "?")) else sent + "."):
                continue
            if entity and not _packing_sentence_ok(sent, entity):
                continue
            match = YEAR_RE.search(sent)
            is_event = any(hint in sent.lower() for hint in EVENT_HINTS)
            if match:
                year = int(match.group(1))
                if year > 1850:
                    continue
                key = _sentence_key(sent)
                if key in seen:
                    continue
                seen.add(key)
                when = match.group(0).replace("–", "-")
                timeline.append(
                    {
                        "when": when,
                        "event": sent,
                        "pages": _sorted_pages([page] if page is not None else group.pages),
                        "_sort": year,
                    }
                )
                _reserve_sentence(sent, used)
            if is_event:
                key = _sentence_key(sent)
                if key in {_sentence_key(e) for e in events}:
                    continue
                if key in seen and not match:
                    continue
                if key in used and len(events) >= 3:
                    continue
                # Skip near-duplicates of already chosen events
                if any(key[:40] == _sentence_key(e)[:40] or key in _sentence_key(e) or _sentence_key(e) in key for e in events):
                    continue
                events.append(sent)
                seen.add(key)
                _reserve_sentence(sent, used)
    timeline.sort(key=lambda row: (row["_sort"], row["when"]))
    for row in timeline:
        row.pop("_sort", None)
    if len(timeline) < 1:
        timeline = []
    return timeline, events[:8]


def _key_points_from_plan(
    plan, entity: str | None = None, used: set[str] | None = None
) -> list[str]:
    points = []
    used = used if used is not None else set()

    def _too_similar(candidate: str) -> bool:
        cand = re.sub(r"\s+", " ", (candidate or "").strip().lower())
        for existing in points:
            ex = re.sub(r"\s+", " ", (existing or "").strip().lower())
            if not cand or not ex:
                continue
            if cand == ex or cand in ex or ex in cand:
                return True
            if cand[:40] and cand[:40] == ex[:40]:
                return True
        return False

    ranked_pool = []
    for sent, _page in _fact_pool(plan, entity=entity):
        probe = sent if sent.endswith((".", "!", "?")) else sent + "."
        if not _is_student_sentence(probe):
            continue
        low = sent.lower()
        weight = 0
        if any(h in low for h in EVENT_HINTS):
            weight += 2
        if YEAR_RE.search(sent):
            weight += 2
        if any(h in low for h in TERM_EXPLAIN_HINTS):
            weight += 1
        if "conquered" in low or "appointed" in low or "coronation" in low:
            weight += 2
        if _sentence_key(sent) not in used:
            weight += 3
        ranked_pool.append((weight, len(sent), sent))
    ranked_pool.sort(reverse=True)
    for weight, _ln, sent in ranked_pool:
        if _too_similar(sent):
            continue
        key = _sentence_key(sent)
        if key in used and len(points) >= 4:
            continue
        used.add(key)
        points.append(sanitize_student_text(sent))
        if len(points) >= 8:
            return points
    if len(points) >= 3:
        return points[:8]
    for group in plan[:6]:
        if len(points) >= 8:
            break
        for sent, _page, _item in _iter_clean_sentences(group.chunks):
            sent = _strip_sentence_prefix(sent)
            if entity and not _packing_sentence_ok(sent, entity):
                continue
            if _too_similar(sent):
                continue
            key = _sentence_key(sent)
            used.add(key)
            points.append(sanitize_student_text(sent))
            if len(points) >= 6:
                break
    return points[:8]


def _revision_from_points(
    key_points: list[str],
    people: list[dict],
    events: list[str] | None = None,
    terms: list[dict] | None = None,
    display: str | None = None,
) -> str:
    lines: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        text = _strip_sentence_prefix(sanitize_student_text(text or ""))
        if not text:
            return
        if not text.endswith((".", "!", "?")):
            text = text + "."
        if not _reserve_sentence(text, seen):
            return
        lines.append(text)

    for point in key_points or []:
        _add(point)
        if len(lines) >= 4:
            break
    for ev in events or []:
        if len(lines) >= 6:
            break
        _add(ev)
    for person in people or []:
        if len(lines) >= 6:
            break
        note = (person.get("note") or "").split(".")[0].strip()
        if person.get("name") and note:
            _add(f"{person['name']}: {note}.")
    for term in terms or []:
        if len(lines) >= 7:
            break
        meaning = (term.get("meaning") or "").split(".")[0].strip()
        if term.get("term") and meaning:
            _add(f"{term['term']}: {meaning}.")
    if not lines:
        return ""
    return "\n".join(f"• {line}" for line in lines[:7])


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


def _repair_exam_questions(content: dict, plan) -> None:
    """Ensure exam answers are non-empty and typed lengths differ."""
    rows = list(content.get("exam_questions") or [])
    people = content.get("important_people") or []
    terms = content.get("important_terms") or []
    events = content.get("main_events") or []
    key_points = content.get("key_points") or []
    fixed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        q = str(row.get("question") or "").strip()
        ans = str(row.get("answer") or "").strip()
        qtype = str(row.get("type") or "short").lower()
        if not q:
            continue
        if not ans:
            if qtype in {"very_short", "very short"} and people:
                ans = _shape_exam_answer(people[0].get("note") or people[0].get("name") or "", "very_short", q)
                row["pages"] = row.get("pages") or people[0].get("pages") or []
            elif qtype == "short" and terms:
                raw = terms[0].get("meaning") or terms[0].get("term") or ""
                if "does not give an explicit definition" in raw.lower():
                    ans = _limit_sentences(raw, 2)
                else:
                    ans = _shape_exam_answer(raw, "short", q)
                row["pages"] = row.get("pages") or terms[0].get("pages") or []
            elif qtype in {"descriptive", "long"}:
                parts = []
                for sent in list(events) + list(key_points):
                    sent = _strip_sentence_prefix(sent)
                    if sent:
                        parts.append(sent)
                    if len(parts) >= 3:
                        break
                ans = _shape_exam_answer(" ".join(parts), "descriptive", q)
            if not ans:
                continue
        else:
            ans = _shape_exam_answer(ans, qtype, q)
            if not ans:
                continue
        row["answer"] = ans
        if qtype in {"very_short", "short", "descriptive"}:
            row["type"] = qtype
        fixed.append(row)
    have = {(r.get("type") or "").lower() for r in fixed}
    if "very_short" not in have and people:
        q = f"Who was {people[0]['name']}?"
        fixed.insert(
            0,
            {
                "type": "very_short",
                "question": q,
                "answer": _shape_exam_answer(people[0].get("note") or people[0]["name"], "very_short", q),
                "pages": people[0].get("pages") or [],
            },
        )
    if "short" not in have and terms:
        q = f"What was {terms[0]['term']} according to the Class 9 textbook?"
        raw = terms[0].get("meaning") or terms[0]["term"]
        ans = (
            _limit_sentences(raw, 2)
            if "does not give an explicit definition" in raw.lower()
            else _shape_exam_answer(raw, "short", q)
        )
        fixed.append(
            {"type": "short", "question": q, "answer": ans, "pages": terms[0].get("pages") or []}
        )
    if "descriptive" not in have and (events or key_points or people):
        title = people[0]["name"] if people else (plan[0].title if plan else "this topic")
        q = f"Explain the main events connected with {title} as given in the Class 9 textbook."
        parts = list(events)[:3] or list(key_points)[:3]
        fixed.append(
            {
                "type": "descriptive",
                "question": q,
                "answer": _shape_exam_answer(" ".join(parts), "descriptive", q),
                "pages": (people[0].get("pages") if people else []) or [],
            }
        )
    content["exam_questions"] = [r for r in fixed if str(r.get("answer") or "").strip()][:5]


def _fill_exam_fallback(content: dict, plan) -> None:
    people = content.get("important_people") or []
    terms = content.get("important_terms") or []
    events = content.get("main_events") or []
    key_points = content.get("key_points") or []
    if not content.get("exam_questions"):
        questions = []
        used_ans: set[str] = set()
        if people:
            raw_ans = _strip_sentence_prefix(people[0].get("note") or people[0]["name"])
            q = f"Who was {people[0]['name']}?"
            ans = _shape_exam_answer(raw_ans, "very_short", q)
            questions.append(
                {
                    "type": "very_short",
                    "question": q,
                    "answer": ans,
                    "pages": people[0].get("pages") or [],
                }
            )
            _reserve_sentence(ans, used_ans)
        if terms:
            raw_ans = _strip_sentence_prefix(terms[0].get("meaning") or terms[0]["term"])
            q = f"What was {terms[0]['term']} according to the Class 9 textbook?"
            # Keep honest non-definition notes intact (may be 2 sentences).
            if "does not give an explicit definition" in raw_ans.lower():
                short_ans = _limit_sentences(raw_ans, 2)
            else:
                short_ans = _shape_exam_answer(raw_ans, "short", q)
            questions.append(
                {
                    "type": "short",
                    "question": q,
                    "answer": short_ans or raw_ans,
                    "pages": terms[0].get("pages") or [],
                }
            )
            _reserve_sentence(short_ans or raw_ans, used_ans)
        desc_parts = []
        for sent in list(events) + list(key_points):
            sent = _strip_sentence_prefix(sent)
            if not sent:
                continue
            if not _reserve_sentence(sent, used_ans):
                continue
            desc_parts.append(sent)
            if len(desc_parts) >= 3:
                break
        pages: list[int] = []
        if not desc_parts and plan:
            group = plan[0] if len(plan) == 1 else plan[min(1, len(plan) - 1)]
            aliases = tuple(
                alias for alias in TOPIC_ALIASES.get(group.key, (group.key,)) if alias.isascii()
            )
            answer, pages = _pick_sentences(
                group.chunks, aliases or (group.title.lower(),), limit=2, used=used_ans
            )
            answer = _strip_sentence_prefix(answer)
            if not answer:
                picked = list(_iter_clean_sentences(group.chunks))
                if picked:
                    answer = _strip_sentence_prefix(picked[0][0])
                    pages = _sorted_pages([picked[0][1]])
            if answer:
                desc_parts = [answer]
                pages = pages or _sorted_pages(group.pages)
            else:
                pages = _sorted_pages(group.pages)
        else:
            if people:
                pages = people[0].get("pages") or []
            if plan:
                pages = pages or _sorted_pages(plan[0].pages)
        if desc_parts:
            title = people[0]["name"] if people else (plan[0].title if plan else "this topic")
            desc_q = (
                f"Explain the main events connected with {title} "
                f"as given in the Class 9 textbook."
            )
            questions.append(
                {
                    "type": "descriptive",
                    "question": desc_q,
                    "answer": _shape_exam_answer(" ".join(desc_parts), "descriptive", desc_q),
                    "pages": pages,
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
        qtype = item.get("type") or "short"
        answer = _shape_exam_answer(answer, str(qtype), question)
        if not answer:
            continue
        out.append({"type": qtype, "question": question, "answer": answer, "pages": pages})
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
    return sorted(out)


def _sanitize_content(content: dict) -> dict:
    cleaned = {}
    for key in ALLOWED_KEYS:
        value = _scrub(content.get(key))
        if _usable(value):
            cleaned[key] = sanitize_structured(value)
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
        f"{_normalize_ocr_text(item.get('text') or '')[:1100]}"
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
    return sorted(out)


def _sorted_pages(pages) -> list[int]:
    out = []
    for page in pages or []:
        try:
            value = int(page)
        except (TypeError, ValueError):
            continue
        if value not in out:
            out.append(value)
    return sorted(out)

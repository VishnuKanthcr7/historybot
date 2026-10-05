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
    "consisted",
    "divided",
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


def _iter_clean_sentences(chunks: list[dict]):
    seen = set()
    for item in chunks or []:
        page = _page(item)
        raw = _normalize_ocr_text(item.get("text") or "")
        for sent in re.split(r"(?<=[.!?])\s+", raw):
            sent = re.sub(r"(?i)^[A-Z][A-Za-z0-9 .\'-]{0,40}?\s*:\s+", "", sent.strip()).strip()
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


def _score_term_sentence(sent: str, needle: str) -> int:
    low = sent.lower()
    if needle not in low:
        return 0
    # Long name-lists without an explanatory cue are weak definitions,
    # but keep sentences that clearly describe collection/taxes/authority/roles.
    explanatory = any(hint in low for hint in TERM_EXPLAIN_HINTS) or any(
        cue in low
        for cue in (
            "collect",
            "tax",
            "authority",
            "appointed as",
            "minister",
            "system",
            "warfare",
            "supervisors",
            "assist",
        )
    )
    if re.search(r",.+,.*\band\b", sent) and not explanatory:
        return 0
    if "duties of the king" in low:
        return 0
    score = 1
    if explanatory:
        score += 4
    if re.search(rf"\bthe {re.escape(needle)}", low):
        score += 2
    if low.startswith(needle):
        score += 2
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


def _format_term_meaning(term: str, sentences: list[str]) -> str:
    """Build a concise textbook-grounded meaning; avoid raw chunk prefixes."""
    cleaned = []
    for sent in sentences:
        sent = _strip_sentence_prefix(sanitize_student_text(sent or ""))
        if not sent:
            continue
        if not sent.endswith((".", "!", "?")):
            sent = sent + "."
        cleaned.append(sent)
    if not cleaned:
        return ""
    primary = cleaned[0]
    low = primary.lower()
    term_l = term.lower()
    if len(cleaned) > 1 and _sentence_key(cleaned[1]) != _sentence_key(primary):
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
            chosen: list[tuple[str, int | None]] = []
            local = set(used)
            for best, sent, page in ranked:
                if chosen and best <= 0:
                    continue
                if not _reserve_sentence(sent, local) and chosen:
                    continue
                if _sentence_key(sent) not in local:
                    local.add(_sentence_key(sent))
                chosen.append((sent, page))
                if len(chosen) >= 2:
                    break
            if not chosen:
                continue
            meaning = _format_term_meaning(label, [s for s, _p in chosen])
            pages = _sorted_pages([p for _s, p in chosen if p is not None] or group.pages)
            if not meaning or label.lower() in seen:
                continue
            seen.add(label.lower())
            for s, _p in chosen:
                _reserve_sentence(s, used)
            terms.append({"term": label, "meaning": meaning[:420], "pages": pages})
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


def _fill_exam_fallback(content: dict, plan) -> None:
    people = content.get("important_people") or []
    terms = content.get("important_terms") or []
    events = content.get("main_events") or []
    key_points = content.get("key_points") or []
    if not content.get("exam_questions"):
        questions = []
        used_ans: set[str] = set()
        if people:
            ans = _strip_sentence_prefix(people[0].get("note") or people[0]["name"])
            questions.append(
                {
                    "type": "very_short",
                    "question": f"Who was {people[0]['name']}?",
                    "answer": ans,
                    "pages": people[0].get("pages") or [],
                }
            )
            _reserve_sentence(ans, used_ans)
        if terms:
            ans = _strip_sentence_prefix(terms[0].get("meaning") or terms[0]["term"])
            short_ans = ans.split(".")[0].strip()
            if short_ans and not short_ans.endswith("."):
                short_ans += "."
            questions.append(
                {
                    "type": "short",
                    "question": f"What was {terms[0]['term']} according to the Class 9 textbook?",
                    "answer": short_ans or ans,
                    "pages": terms[0].get("pages") or [],
                }
            )
            _reserve_sentence(short_ans or ans, used_ans)
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
            questions.append(
                {
                    "type": "descriptive",
                    "question": (
                        f"Explain the main events connected with {title} "
                        f"as given in the Class 9 textbook."
                    ),
                    "answer": " ".join(desc_parts),
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

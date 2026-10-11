"""Textbook-only grounded answer engine. Approved Class 9 textbook is the sole student source."""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache

from rag.engine.citations import supporting_evidence
from rag.engine.classify import (
    FOLLOW_SHORT_RE,
    PRONOUN_RE,
    TOPIC_ALIASES,
    _folded,
    casual_reply,
    classify_answer_mode,
    classify_casual,
    classify_intent,
    classify_question_type,
    extract_topics,
    last_user_question,
    strip_leading_greeting,
)
from rag.engine.evidence import (
    STOPWORDS,
    content_tokens,
    evidence_is_sufficient,
    evidence_matches_topic,
    evidence_subject_match,
    overlap_count,
    topic_supported_by_primary,
)
from rag.engine.intent import (
    collect_task_state,
    entity_focus_query,
    infer_previous_task,
    is_more_followup,
    last_mcq_request,
    looks_like_mcq_request,
    previous_assistant,
    requested_item_count,
    revises_current_questions,
    wants_easy_english,
)
from rag.engine.mcq import mcqs_from_pack
from rag.engine.normalize import (
    heuristic_followup_query,
    looks_kannada,
    looks_like_injection,
    looks_like_roleplay,
    normalize_question,
    trim_history,
)
from rag.engine.pack import build_evidence_pack, detect_entity
from rag.engine.coverage import generate_from_plan
from rag.engine.depth import (
    classify_depth,
    depth_prompt_extra,
    filter_new_sentences,
    prefer_unused_chunks,
)
from rag.engine.sanitize import sanitize_student_text
from rag.engine.validate import enforce_evidence_support, is_refusal, unsupported_named_items, validate_answer
from rag.llm.client import complete
from rag.llm.config import RAG_TOP_K
from rag.prompts.tutor import (
    FINAL_ANSWER_PROMPT,
    KANNADA_UNAVAILABLE,
    NOT_IN_TEXTBOOK,
    REVISION_LABEL,
    SUPPLEMENT_LABEL,
    SYSTEM_PROMPT,
    TEXTBOOK_LABEL,
    refusal_text,
)
from rag.vectorstore.retrieve import retrieve_primary

_LOG = logging.getLogger("historybot.answer")

LIMITED_EN = (
    "The Class 9 Karnataka State Board 2026–27 textbook has limited information on this topic."
)
LIMITED_TERMS = ("mansab", "mansabdari", "sulh-i", "coparcenary", "nur jahan")

BOUNDARY_EN = (
    "I can help with Class 9 History and Social Science topics from your Karnataka State Board course. "
    f"{NOT_IN_TEXTBOOK}"
)
# Ordinary English that can appear in the textbook without naming its subject.
# A question is in-domain only when it has a textbook token outside this set,
# a known topic alias, or it is an anaphoric follow-up of the current question.
_GENERIC_WORDS = frozenset(
    {
        "abolish", "abolished", "about", "above", "across", "after", "again", "against", "along", "also",
        "although", "among", "another", "answer", "answers", "around", "assumed",
        "because", "become", "became", "been", "before", "being", "below", "between",
        "birth", "board", "born", "both", "built", "called", "came", "captured",
        "century", "chapter", "class", "compare", "constructed", "control",
        "controlled", "could", "country", "current", "death", "defeated", "describe",
        "died", "different", "during", "early", "eight", "eighteen", "eighty",
        "either", "eleven", "else", "emperor", "emperors", "especially", "established",
        "even", "every", "explain", "father", "fifteen", "fifth", "fifty", "first",
        "five", "following", "forty", "fourteen", "fourth", "from", "general", "give",
        "given", "great", "happened", "having", "help", "here", "history", "however",
        "hundred", "important", "including", "information", "into", "invaded", "just",
        "killed", "king", "kings", "known", "large", "later", "life", "like", "list",
        "lived", "major", "make", "many", "married", "minister", "more", "most",
        "mother", "much", "must", "name", "names", "next", "nine", "nineteen",
        "ninety", "number", "only", "onto", "other", "over", "page", "pages", "part",
        "parts", "people", "period", "person", "place", "places", "please", "power", "prime",
        "queen", "queens", "question", "questions", "received", "ruled", "ruler",
        "rulers", "ruling", "same", "second", "seven", "seventeen", "seventy",
        "several", "shall", "should", "show", "shown", "since", "sixteen", "sixty",
        "succeed", "succeeded",
        "small", "soldier", "soldiers", "solve", "solved", "some", "state", "states",
        "still", "student", "students", "such", "system", "taken", "tell", "textbook",
        "than", "that", "their", "them", "then", "there", "these", "they", "third",
        "thirteen", "thirty", "this", "those", "thousand", "three", "through", "time",
        "times", "today", "trained", "training", "twelve", "twenty", "type", "under",
        "until", "using", "very", "warfare", "were", "what", "when", "where", "which",
        "while", "whose", "with", "within", "without", "work", "world", "would",
        "write", "writing", "written", "year", "years", "young", "your",
    }
)
OUTSIDE_SOURCE_NOTE = (
    "I cannot look up Wikipedia, NCERT, the internet, or other books. I use your Class 9 "
    "Karnataka State Board textbook first and add a clearly labelled general explanation where it helps."
)
# History and social-science words that are in scope for a Class 9 student even when the
# prescribed chapter does not mention them (the answer is then supplementary, never cited).
_HISTORY_VOCAB = frozenset(
    """
    history historical historian ancient medieval modern civilisation civilization empire empires
    emperor dynasty dynasties kingdom kingdoms sultan sultanate sultans battle battles revolt revolts
    rebellion revolution revolutions movement independence freedom colonial colonialism colony
    colonies british portuguese dutch french company treaty invasion invasions conquest conquests
    administration revenue nobles nobility feudal feudalism monarchy republic parliament constitution
    democracy election elections rights citizen citizenship government governance civics economics
    economy poverty agriculture irrigation monsoon climate rivers geography plateau census
    mughal mughals maratha marathas rajput rajputs peshwa peshwas vijayanagara bahmani chola cholas
    chalukya chalukyas hoysala hoysalas rashtrakuta kadamba ganga satavahana maurya mauryan mauryas
    gupta guptas kushana harappa harappan indus vedic aryan buddha buddhism buddhist jainism jaina
    mahavira ashoka asoka kalinga chandragupta samudragupta harsha pulakeshi krishnadevaraya
    tipu hyder mysore wodeyar plassey buxar panipat haldighati talikota jallianwala gandhi nehru
    tilak gokhale bhagat subhas ambedkar swadeshi khilafat satyagraha dandi partition sepoy mutiny
    renaissance reformation crusades feudal napoleon industrial magna carta roman romans greek greeks
    egypt egyptian mesopotamia pharaoh pyramids temple temples monument monuments inscription
    inscriptions archaeology archaeological coins architecture fort forts painting miniature
    sufi bhakti saint saints religion religious trade traders merchants guild guilds
    """.split()
)
ROLEPLAY_NOTE = (
    "I cannot invent a fictional story or dialogue. Here is what the prescribed textbook says."
)
OFF_DOMAIN_CLAUSES = (
    (r"capital of karnataka", "the capital of Karnataka"),
    # A present-day "capital of <place>" ask. "capital of the ..." stays available
    # for a dynasty or kingdom the textbook actually discusses.
    (r"\bcapital of (?!the\b)", "that capital"),
    (r"world war", "World War II"),
    (r"world cup", "the World Cup"),
    (r"\bpython\b", "Python"),
    (r"cristiano|\bronaldo\b", "that person"),
    (r"tell me a joke|\ba joke\b|\bjokes\b", "jokes"),
    (r"\bweather\b", "today's weather"),
    (r"prime minister", "the current Prime Minister"),
    (r"\bncert\b", "NCERT"),
    (r"wikipedia", "Wikipedia"),
    (r"search google|search the internet", "the internet"),
    (r"exact birthplace|exact place of birth", "the exact birthplace"),
    (r"chatgpt|openai", "that request"),
    # Sport, films and celebrities are outside Class 9 History and Social Science.
    (r"\bcricket\b|\bipl\b|\bfootball\b|\bbollywood\b|\bmovies?\b|\bfilm stars?\b|\bcelebrit", "that topic"),
)


def _question_content_tokens(question: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z]{5,}", (question or "").lower())
        if token not in _GENERIC_WORDS
    }


@lru_cache(maxsize=1)
def _textbook_domain_tokens() -> frozenset[str]:
    """Words of the Class 9 textbook and its topic lists, minus ordinary English."""
    from rag.engine.topic_map import FACET_TERMS, load_primary_chunks

    tokens: set[str] = set()
    for aliases in TOPIC_ALIASES.values():
        for alias in aliases:
            tokens.update(re.findall(r"[a-z]{5,}", alias.lower()))
    for terms in FACET_TERMS.values():
        for term in terms:
            tokens.update(re.findall(r"[a-z]{5,}", term.lower()))
    for item in load_primary_chunks():
        tokens.update(re.findall(r"[a-z]{5,}", (item.get("text") or "").lower()))
    return frozenset(token for token in tokens if token not in _GENERIC_WORDS)


def _is_contextual_followup(question: str, domain: frozenset[str] | None) -> bool:
    """A follow-up continues the conversation. It does not name a new outside subject.

    The previous answer is not evidence. Only the current wording counts:
    a short continuation, or a pronoun whose other content words stay in the textbook.
    """
    if FOLLOW_SHORT_RE.match(_folded(question or "")):
        return True
    if not PRONOUN_RE.search(question or ""):
        return False
    tokens = _question_content_tokens(question)
    if domain is None:
        return not tokens
    return not (tokens - domain)


@lru_cache(maxsize=1)
def _short_textbook_terms() -> frozenset[str]:
    """Rare four-letter textbook words (terms such as a revenue or army office name).

    Common short words appear many times in the textbook; a term usually appears once or twice.
    """
    from collections import Counter

    from rag.engine.topic_map import load_primary_chunks

    counts: Counter[str] = Counter()
    for item in load_primary_chunks():
        counts.update(re.findall(r"\b[a-z]{4}\b", (item.get("text") or "").lower()))
    return frozenset(
        word for word, count in counts.items() if count <= 3 and word not in _GENERIC_WORDS and word not in STOPWORDS
    )


@lru_cache(maxsize=1)
def _textbook_name_vocab() -> tuple[frozenset[str], dict[str, str]]:
    """Capitalised textbook words (names, terms) and joined two-word names ("shershah" -> "Sher Shah")."""
    from rag.engine.topic_map import load_primary_chunks

    names: set[str] = set()
    joined: dict[str, str] = {}
    for item in load_primary_chunks():
        text = item.get("text") or ""
        names.update(word.lower() for word in re.findall(r"\b[A-Z][a-z]{3,}\b", text))
        for first, second in re.findall(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", text):
            joined.setdefault((first + second).lower(), f"{first} {second}")
    names -= set(_GENERIC_WORDS) | set(STOPWORDS)
    return frozenset(names), joined


def _correct_textbook_spelling(question: str) -> str:
    """Fix a misspelt textbook name or term ("akbr" -> "Akbar", "shershah" -> "Sher Shah").

    Only words that are not textbook words already are changed, and only to a close
    textbook name (difflib ratio >= 0.8). Ordinary words with no close name stay as typed.
    """
    import difflib

    names, joined = _textbook_name_vocab()
    domain = _textbook_domain_tokens()

    def fix(match: re.Match[str]) -> str:
        word = match.group(0)
        lowered = word.lower()
        if lowered in names or lowered in domain or lowered in _GENERIC_WORDS or lowered in STOPWORDS:
            return word
        if lowered in joined:
            return joined[lowered]
        # 0.85: 'akbr' -> 'akbar' (0.89) is corrected; 'kalinga' -> 'kalinjar' (0.80) is not.
        close = difflib.get_close_matches(lowered, names, n=1, cutoff=0.85)
        return close[0].capitalize() if close else word

    return re.sub(r"\b[A-Za-z]{4,}\b", fix, question or "")


def _current_question_outside_domain(question: str) -> bool:
    """True when this question itself is outside the Class 9 textbook domain."""
    if extract_topics(question):
        return False
    tokens = _question_content_tokens(question)
    if _is_contextual_followup(question, None) and not tokens:
        return False
    domain = _textbook_domain_tokens()
    if _is_contextual_followup(question, domain):
        return False
    if tokens & domain:
        return False
    if set(re.findall(r"[a-z]{4,}", (question or "").lower())) & _HISTORY_VOCAB:
        return False
    if set(re.findall(r"\b[a-z]{4}\b", (question or "").lower())) & _short_textbook_terms():
        return False
    return True


def answer_question(
    question: str,
    language: str = "en",
    history: list[dict] | None = None,
    task_state: dict | None = None,
) -> dict:
    language = "kn" if language == "kn" else "en"
    question = normalize_question(question)
    history = trim_history(history)
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    casual = classify_casual(question)
    if casual:
        return {
            "answer": casual_reply(casual, language),
            "language": language,
            "grounded": False,
            "sources": [],
            "retrieval_query": None,
            "retrieved": [],
            "selected_chunk_ids": [],
            "validation_reason": f"casual:{casual}",
            "intent": casual,
            "mode": "CASUAL",
            "used_supplementary": False,
            "regeneration_count": 0,
            "unsupported_claims": [],
        }

    if language == "kn" or looks_kannada(question):
        return _kannada_unavailable(question)

    rag_question = strip_leading_greeting(question)
    topics = extract_topics(rag_question)
    if re.search(r"\bkannada\b", rag_question, re.I) and not topics:
        return _kannada_unavailable(rag_question)
    off_labels = _off_domain_labels(rag_question)
    if off_labels and not topics:
        return _boundary(language, rag_question)
    # "Explain again more simply" / "I still don't understand" continues the
    # previous textbook question; it is not an off-domain question.
    reexplain_target = _reexplain_target(rag_question, history) if not topics else ""
    # "Can you explain this in more detail?" continues the previous textbook answer; it is
    # not an off-domain question. Only a bare request (no topic words of its own) qualifies.
    bare_depth = None if topics else _depth_request(rag_question, rag_question, history)
    depth_followup = bool(
        bare_depth
        and bare_depth["bare"]
        and bare_depth["followup"]
        and not _current_question_outside_domain(bare_depth["previous_question"])
    )
    # "Give an example", "What happened next?", "Role of the nobles?" continue the previous
    # in-scope answer; they are not off-domain questions.
    continuation = None if topics or reexplain_target or depth_followup else _continuation(rag_question, history)
    if not reexplain_target and not depth_followup and not continuation and not topics and _current_question_outside_domain(rag_question):
        # A misspelt textbook name ("akbr", "shershah") is not an outside topic.
        corrected = _correct_textbook_spelling(rag_question)
        if corrected != rag_question and not _current_question_outside_domain(corrected):
            rag_question = corrected
            topics = extract_topics(rag_question)
        else:
            return _boundary(language, rag_question)
    if looks_like_injection(rag_question) and not topics:
        return _unavailable(language, rag_question, [], [], intent=None, mode="NORMAL")
    if looks_like_roleplay(rag_question) and not topics:
        return _boundary(language, rag_question)
    if (
        re.search(r"\b(this chapter|the chapter|this topic)\b", rag_question, re.I)
        and not topics
        and not history
    ):
        return _clarify(language, rag_question, "STANDALONE", "NORMAL")
    # "Tell me something not in the textbook" is answered with labelled supplementary history.
    search_question = _strip_off_domain(rag_question) or rag_question
    if continuation and not extract_topics(search_question):
        search_question = f"{continuation['previous_question'].rstrip(' ?.!')}: {search_question}"
    if reexplain_target:
        # Retrieve for the same topic again; the style note asks for a simpler answer.
        search_question = reexplain_target
    stored_task = collect_task_state(history, task_state)
    previous_task = infer_previous_task(history, stored_task)
    more = not reexplain_target and (is_more_followup(search_question) or is_more_followup(rag_question))
    revise_questions = revises_current_questions(search_question) or revises_current_questions(rag_question)
    prior_mcq = last_mcq_request(history) if revise_questions else ""
    continue_mcq = bool(prior_mcq) or (previous_task == "MCQ" and more)
    if continue_mcq:
        previous = prior_mcq or last_user_question(history)
        search_question = previous or search_question
        if not extract_topics(search_question):
            if stored_task.get("entity") and stored_task["entity"] in TOPIC_ALIASES:
                search_question = f"mcqs about {TOPIC_ALIASES[stored_task['entity']][0]}"
            elif stored_task.get("topic"):
                search_question = f"mcqs about {stored_task['topic']}"
        mode = "DETAILED"
        intent = "FOLLOW_UP"
        question_type = "EXAM"
        retrieval_query = entity_focus_query(
            detect_entity(extract_topics(search_question)),
            extract_topics(search_question),
            "BROAD_TOPIC" if "mughal" in extract_topics(search_question) else "EXAM",
        ) or search_question
    elif more and previous_task == "EXPLAIN":
        previous = last_user_question(history)
        labels = [TOPIC_ALIASES[key][0] for key in extract_topics(previous) if key in TOPIC_ALIASES]
        if not labels and stored_task.get("entity") and stored_task["entity"] in TOPIC_ALIASES:
            labels = [TOPIC_ALIASES[stored_task["entity"]][0]]
        elif not labels and stored_task.get("topic"):
            labels = [str(stored_task["topic"])]
        search_question = f"tell me more about {' '.join(labels)}" if labels else search_question
        mode = classify_answer_mode(search_question)
        intent = "FOLLOW_UP"
        question_type = classify_question_type(search_question, None)
        if detect_entity(extract_topics(search_question)):
            question_type = "EXPLANATION"
        retrieval_query = entity_focus_query(
            detect_entity(extract_topics(search_question)),
            extract_topics(search_question),
            question_type,
        ) or search_question
    else:
        from rag.engine.facts import _expand_pronouns

        previous_user = last_user_question(history)
        # A question that just left history must not keep feeding the old person
        # into "he" or "his".
        if previous_user and _current_question_outside_domain(previous_user):
            pass
        else:
            search_question = _expand_pronouns(search_question, history) or search_question
        mode = classify_answer_mode(search_question)
        intent = classify_intent(search_question, history)
        question_type = classify_question_type(search_question, intent)
        # A follow-up that itself asks for an explanation of a named topic
        # must keep subject filtering. The FOLLOW_UP label only means the
        # chat continued; it must not switch to unfiltered chunk text.
        if question_type == "FOLLOW_UP" and extract_topics(search_question):
            standalone = classify_question_type(search_question, None)
            if standalone in {"EXPLANATION", "BROAD_TOPIC"}:
                question_type = standalone
        previous = last_user_question(history) if intent == "FOLLOW_UP" else ""
        if (
            intent == "FOLLOW_UP"
            and not depth_followup
            and not continuation
            and not extract_topics(previous)
            and not extract_topics(search_question)
        ):
            return _clarify(language, rag_question, intent, mode)
        focus = entity_focus_query(
            detect_entity(extract_topics(search_question)),
            extract_topics(search_question),
            question_type,
        )
        follow = ""
        if intent == "FOLLOW_UP" and previous and not extract_topics(search_question):
            follow = heuristic_followup_query(search_question, previous) or ""
        retrieval_query = _with_question_terms(search_question, focus or follow)

    depth_profile = classify_depth(
        search_question if not more else rag_question,
        more_followup=bool(more and previous_task == "EXPLAIN"),
    )
    if more and previous_task == "EXPLAIN":
        mode = depth_profile.mode
    elif not more:
        if depth_profile.mode == "DETAILED" and mode == "NORMAL":
            mode = "DETAILED"
        if depth_profile.mode == "ECONTENT":
            mode = "ECONTENT"
    if depth_profile.question_type_hint and question_type == "DIRECT" and depth_profile.depth in {
        "medium",
        "detail",
        "why",
        "how",
        "compare",
        "list",
        "more",
    }:
        question_type = depth_profile.question_type_hint
    top_k = depth_profile.top_k
    if question_type == "BROAD_TOPIC":
        top_k = max(top_k, 16)
    elif mode == "DETAILED":
        top_k = max(top_k, 14)
    top_k = max(RAG_TOP_K, top_k)
    t_retrieve = time.perf_counter()
    primary_hits = retrieve_primary(retrieval_query, top_k=top_k, language="en")
    timings["T1_retrieve_ms"] = round((time.perf_counter() - t_retrieve) * 1000, 1)
    if looks_like_mcq_request(search_question) or looks_like_mcq_request(rag_question):
        question_type = "EXAM"
    if question_type != "EXAM" and mode != "ECONTENT" and not continue_mcq:
        lookup = (search_question or "").strip()
        if retrieval_query and retrieval_query.lower() not in lookup.lower():
            lookup = f"{lookup} {retrieval_query}".strip()
        if lookup and lookup != retrieval_query:
            primary_hits = retrieve_primary(lookup, top_k=top_k, language="en")
            retrieval_query = lookup
        return _reasoned_history_answer(
            search_question,
            rag_question,
            language,
            retrieval_query,
            primary_hits,
            intent,
            mode,
            depth_profile,
            off_labels,
            history,
            t0,
            timings,
        )
    pack = build_evidence_pack(
        search_question,
        retrieval_query,
        "BROAD_TOPIC"
        if question_type == "EXAM" and "mughal" in extract_topics(search_question)
        else (question_type if question_type != "EXAM" else "EXPLANATION"),
        raw_hits=primary_hits,
        history=history,
    )
    primary_selected = pack.chunks
    timings["T2_pack_ms"] = round((time.perf_counter() - t_retrieve) * 1000, 1)
    if depth_profile.prefer_unused:
        used_ids = list(stored_task.get("used_chunk_ids") or stored_task.get("ids") or [])
        primary_selected = prefer_unused_chunks(primary_selected, used_ids)
        pack.chunks = primary_selected

    # Follow-ups often lack named topics ("Why is he important?"); gate on the
    # rewritten retrieval_query that carries the prior entity/topic.
    gate_question = retrieval_query if intent == "FOLLOW_UP" else search_question
    supported = topic_supported_by_primary(gate_question)
    if supported is False and not looks_like_injection(rag_question):
        # In scope but not in the textbook: a labelled supplementary answer, never a refusal.
        return _reasoned_history_answer(
            search_question, rag_question, language, retrieval_query, primary_hits, intent, mode,
            depth_profile, off_labels, history, t0, timings,
        )
    if supported is False:
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)

    if looks_like_injection(rag_question) and not extract_topics(gate_question):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if looks_like_injection(rag_question) and not evidence_matches_topic(
        gate_question, retrieval_query, primary_selected
    ):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if (
        not evidence_is_sufficient(primary_selected)
        or not evidence_matches_topic(gate_question, retrieval_query, primary_selected)
        or not evidence_subject_match(gate_question, primary_selected)
    ):
        if not looks_like_injection(rag_question):
            return _reasoned_history_answer(
                search_question, rag_question, language, retrieval_query, primary_hits, intent, mode,
                depth_profile, off_labels, history, t0, timings,
            )
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)

    selected = list(primary_selected)
    if "focused-person" in pack.reasons and selected:
        sentences = []
        seen_sentences = set()
        for item in selected:
            for part in re.split(r"(?<=[.!?])\s+", item.get("text") or ""):
                cleaned = " ".join(part.split())
                key = cleaned.lower()
                if cleaned and key not in seen_sentences:
                    seen_sentences.add(key)
                    sentences.append(cleaned)
        if sentences:
            sources = _sources(selected)
            answer = f"{' '.join(sentences)}\n\n{_citation_block(sources)}"
            result = _payload(
                answer,
                language,
                retrieval_query,
                primary_hits,
                selected,
                "focused_person",
                intent,
                mode,
                0,
                [],
                pack,
                fallback=False,
                sources=sources,
            )
            result["task"] = {
                "type": "EXPLAIN",
                "topic": pack.topics[0] if pack.topics else None,
                "entity": None,
                "used_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
                "depth": depth_profile.depth,
            }
            result["depth"] = depth_profile.as_public()
            timings["T8_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            result["timings"] = timings
            return result
    if question_type == "EXAM":
        mcq_turn = looks_like_mcq_request(search_question) or looks_like_mcq_request(rag_question) or continue_mcq
        if mcq_turn:
            count_source = rag_question if looks_like_mcq_request(rag_question) else search_question
            default_count = int(stored_task.get("count") or 10) if (more or revise_questions) else 10
            count = requested_item_count(count_source, default=default_count)
            exam, fingerprints = mcqs_from_pack(
                search_question,
                selected,
                count=count,
                previous_answer=previous_assistant(history) if (more or revise_questions) else "",
                previous_fingerprints=stored_task.get("fingerprints") if (more or revise_questions) else [],
                prefer_specific=revise_questions,
            )
            if exam:
                sources = _sources(supporting_evidence(_mcq_attribution_text(exam), selected, min_overlap=2))
                answer = _decorate_student_answer(rag_question, exam, off_labels)
                answer = f"{answer}\n\n{_citation_block(sources)}"
                result = _payload(
                    answer,
                    language,
                    retrieval_query,
                    primary_hits,
                    selected,
                    "mcq_from_pack",
                    intent,
                    mode,
                    0,
                    [],
                    pack,
                    fallback=False,
                    sources=sources,
                )
                result["task"] = {
                    "type": "MCQ",
                    "topic": pack.entity or (pack.topics[0] if pack.topics else None),
                    "entity": pack.entity,
                    "count": count,
                    "fingerprints": fingerprints,
                    "generation_index": int(stored_task.get("generation_index") or 0) + len(fingerprints),
                    "used_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
                    "depth": "exam",
                }
                timings["T8_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                result["timings"] = timings
                result["depth"] = {"depth": "exam", "mode": mode}
                return result
            return _unavailable(language, retrieval_query, primary_hits, selected, intent=intent, mode=mode)
        exam = _exam_from_pack(search_question, selected)
        if exam:
            sources = _sources(supporting_evidence(exam, selected, min_overlap=1))
            answer = _decorate_student_answer(rag_question, exam, off_labels)
            answer = f"{answer}\n\n{_citation_block(sources)}"
            return _payload(
                answer,
                language,
                retrieval_query,
                primary_hits,
                selected,
                "exam_from_pack",
                intent,
                mode,
                0,
                [],
                pack,
                fallback=False,
                sources=sources,
            )
    use_plan = question_type in {"BROAD_TOPIC", "EXPLANATION"} or (
        question_type == "FOLLOW_UP"
        and (pack.facet == "administration" or pack.entity or len(selected) >= 5)
    )
    if depth_profile.use_plan and question_type in {"DIRECT", "FOLLOW_UP"} and depth_profile.depth in {
        "medium", "detail", "why", "how", "compare", "list", "more"
    }:
        use_plan = True
    regenerations = 0
    coverage_info = None
    if use_plan:
        plan_type = "BROAD_TOPIC" if question_type == "BROAD_TOPIC" else "EXPLANATION"
        t_gen = time.perf_counter()
        covered = generate_from_plan(
            search_question,
            selected,
            plan_type,
            depth_profile=depth_profile,
            previous_answer=previous_assistant(history) if (more and previous_task == "EXPLAIN") else "",
        )
        timings["T3_generate_ms"] = round((time.perf_counter() - t_gen) * 1000, 1)
        coverage_info = covered
        regenerations = 1 if covered.get("regenerated") else 0
        raw = covered.get("answer") or ""
        ok, reason = validate_answer(
            raw,
            "en",
            selected,
            grounded_expected=True,
            mode=mode,
            primary=primary_selected,
            supplement=[],
        )
        claims = unsupported_named_items(raw, selected)
        if not ok:
            from rag.engine.coverage import (
                combine_entity_sections,
                combine_sections,
                filter_plan,
                readable_extract,
                build_coverage_plan,
            )
            from rag.engine.entity import build_entity_plan, entity_focus_evidence, entity_readable

            entity_key = pack.entity or detect_entity(extract_topics(search_question))
            focused_selected = entity_focus_evidence(selected, entity_key) if entity_key else []
            entity_plan = (
                build_entity_plan(search_question, focused_selected or selected, entity_key)
                if entity_key
                else []
            )
            if entity_plan:
                raw = combine_entity_sections(
                    entity_key,
                    [(group, entity_readable([group])) for group in entity_plan],
                )
            else:
                plan = filter_plan(search_question, build_coverage_plan(selected))
                raw = combine_sections(
                    search_question,
                    [(group, readable_extract(group.chunks)) for group in plan],
                )
            reason = f"{reason}+structured_fallback"
            claims = unsupported_named_items(raw, selected)
            covered["fallback_used"] = True
            coverage_info = covered
        raw = _strip_invented_pages(raw)
        raw, _ = _fix_swapped_subjects(raw, selected)
        raw = _apply_partial_refusals(rag_question, raw, selected)
        raw = _apply_why_motive_note(rag_question, raw, selected, pack.entity, depth_profile.depth)
        if more and previous_task == "EXPLAIN":
            prev = previous_assistant(history)
            filtered = filter_new_sentences(raw, prev)
            if filtered and len(filtered.split()) >= 40:
                raw = filtered
            if not raw.strip().lower().startswith("additional"):
                raw = "Additional textbook points:\n\n" + raw
        from rag.engine.entity import drop_preheading_claims

        raw = drop_preheading_claims(raw, selected, pack.entity)
        raw = _decorate_student_answer(rag_question, raw, off_labels)
        sources = _sources(supporting_evidence(raw, selected, min_overlap=2))
        if not sources:
            sources = _sources(supporting_evidence(raw, selected, min_overlap=1))
        if re.search(r"\[Page", raw):
            answer = raw
        else:
            answer = f"{raw}\n\n{_citation_block(sources)}"
        result = _payload(
            answer,
            language,
            retrieval_query,
            primary_hits,
            selected,
            reason,
            intent,
            mode,
            regenerations,
            claims,
            pack,
            fallback=bool(covered.get("fallback_used")),
            coverage=coverage_info,
            sources=sources,
        )
        result["task"] = {
            "type": "EXPLAIN",
            "topic": pack.entity or (pack.topics[0] if pack.topics else None),
            "entity": pack.entity,
            "used_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
            "depth": depth_profile.depth,
        }
        result["depth"] = depth_profile.as_public()
        timings["T8_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        result["timings"] = timings
        return result

    llm_evidence = _identity_focus_evidence(search_question, primary_selected, question_type, pack.entity)
    payload = _ask_llm(search_question, llm_evidence, mode, strict=False, question_type=question_type, depth_profile=depth_profile, entity=pack.entity)
    regenerations = 0
    ok, reason = validate_answer(
        payload["raw"],
        "en",
        selected,
        grounded_expected=True,
        mode=mode,
        primary=primary_selected,
        supplement=[],
    )
    if not ok:
        regenerations = 1
        payload = _ask_llm(search_question, llm_evidence, mode, strict=True, question_type=question_type, depth_profile=depth_profile, entity=pack.entity)
        ok, reason = validate_answer(
            payload["raw"],
            "en",
            selected,
            grounded_expected=True,
            mode=mode,
            primary=primary_selected,
            supplement=[],
        )
    claims = unsupported_named_items(payload.get("raw") or "", selected)
    if not ok or is_refusal(payload["raw"], "en"):
        if evidence_is_sufficient(selected) and not looks_like_injection(rag_question):
            raw = _safe_from_evidence(llm_evidence, search_question)
            reason = f"{reason}+extractive_fallback"
            sources = _sources(supporting_evidence(raw, llm_evidence, min_overlap=1))
            answer = f"{_decorate_student_answer(rag_question, raw, off_labels)}\n\n{_citation_block(sources)}"
            result = _payload(
                answer,
                language,
                retrieval_query,
                primary_hits,
                selected,
                reason,
                intent,
                mode,
                regenerations,
                claims,
                pack,
                fallback=True,
            )
            result["task"] = {
                "type": "EXPLAIN",
                "topic": pack.entity or (pack.topics[0] if pack.topics else None),
                "entity": pack.entity,
                "used_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
                "depth": depth_profile.depth,
            }
            result["depth"] = depth_profile.as_public()
            timings["T8_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            result["timings"] = timings
            return result
        result = _unavailable(language, retrieval_query, primary_hits, selected, intent=intent, mode=mode)
        result["validation_reason"] = reason
        result["regeneration_count"] = regenerations
        result["unsupported_claims"] = claims
        result["evidence_pack"] = pack.as_public()
        result["question_type"] = question_type
        return result

    raw = _strip_invented_pages(payload["raw"])
    raw, _ = _fix_swapped_subjects(raw, list(llm_evidence) + list(selected))
    from rag.engine.coverage import GROUP_TITLE
    from rag.engine.topic_map import RULER_KEYS

    title = GROUP_TITLE.get(pack.entity) if pack.entity in RULER_KEYS else None
    if question_type == "DIRECT":
        raw = enforce_evidence_support(raw, llm_evidence, title)
    raw = _keep_stated_identity(rag_question, raw, list(llm_evidence) + list(selected), title)
    raw = _apply_partial_refusals(rag_question, raw, selected)
    raw = _apply_why_motive_note(rag_question, raw, selected, pack.entity, depth_profile.depth)
    raw = _decorate_student_answer(rag_question, raw, off_labels)
    sources = _sources(supporting_evidence(raw, llm_evidence, min_overlap=1 if mode == "DETAILED" else 2))
    answer = f"{raw}\n\n{_citation_block(sources)}"
    result = _payload(
        answer,
        language,
        retrieval_query,
        primary_hits,
        selected,
        reason,
        intent,
        mode,
        regenerations,
        claims,
        pack,
        fallback=False,
    )
    result["task"] = {
        "type": "EXPLAIN",
        "topic": pack.entity or (pack.topics[0] if pack.topics else None),
        "entity": pack.entity,
        "used_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
        "depth": depth_profile.depth,
    }
    result["depth"] = depth_profile.as_public()
    timings["T8_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["timings"] = timings
    return result


_QUERY_STOP = {
    "how", "did", "does", "what", "who", "when", "where", "why", "type",
    "the", "his", "her", "their", "him", "them", "and", "with", "from", "that", "this",
    "into", "about", "have", "been", "your", "they", "used", "tell", "more",
    "was", "were", "important", "achievement", "achievements",
    "accomplishment", "accomplishments", "place", "places", "expansion",
}


def _with_question_terms(question: str, query: str) -> str:
    """Keep the entity focus, and add the question's own content words.

    Follow-up retrieval otherwise collapses to the person alone, so a question
    about warfare or a tax can miss the chunk that actually states it.
    """
    from rag.engine.entity import epithet_only_rulers

    epithets = epithet_only_rulers(question)
    entity = detect_entity(extract_topics(question) - epithets) or detect_entity(extract_topics(question))
    aliases = set()
    if entity and entity in TOPIC_ALIASES:
        aliases.update(alias.lower() for alias in TOPIC_ALIASES[entity])
    for key in epithets:
        if entity:
            aliases.update(alias.lower() for alias in TOPIC_ALIASES.get(key, ()) if isinstance(alias, str))
    tokens = []
    for token in re.findall(r"[a-z]{4,}", (question or "").lower()):
        if token in _QUERY_STOP or token in aliases or token in (query or "").lower():
            continue
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        return query
    return f"{query} {' '.join(tokens[:6])}".strip()


def _looks_limited(question: str) -> bool:
    lowered = (question or "").lower()
    return any(term in lowered for term in LIMITED_TERMS)


def _off_domain_labels(question: str) -> list[str]:
    lowered = (question or "").lower()
    labels = []
    for pattern, label in OFF_DOMAIN_CLAUSES:
        if re.search(pattern, lowered) and label not in labels:
            labels.append(label)
    return labels


def _strip_off_domain(question: str) -> str:
    text = question or ""
    replacements = (
        (r"what wikipedia says about", "tell me about"),
        (r"information from ncert about", "tell me about"),
        (r"from ncert about", "about"),
        (r"search google for", "tell me about"),
        (r"and what is the capital of karnataka", ""),
        (r"and world war ii", ""),
        (r"and also tell me who won the 2026 world cup", ""),
        (r"who won the 2026 world cup", ""),
        (r"and his exact date of birth", ""),
        (r"and tell me his exact birthplace", ""),
        (r"his exact birthplace", ""),
        (r"his exact date of birth", ""),
        (r"capital of karnataka", ""),
        (r"world war ii", ""),
        (r"world cup", ""),
        (r"\bwikipedia\b", ""),
        (r"\bncert\b", ""),
        (r"\bgoogle\b", ""),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.I)
    for pattern, _ in OFF_DOMAIN_CLAUSES:
        text = re.sub(pattern, " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" ,.")


def _decorate_student_answer(question: str, answer: str, off_labels: list[str] | None) -> str:
    parts: list[str] = []
    lowered = (question or "").lower()
    outside = looks_like_injection(question) or any(
        marker in lowered for marker in ("wikipedia", "ncert", "google", "another book", "internet")
    )
    if outside:
        parts.append(OUTSIDE_SOURCE_NOTE)
    if looks_like_roleplay(question):
        parts.append(ROLEPLAY_NOTE)
    parts.append((answer or "").strip())
    remaining = [label for label in (off_labels or []) if label not in {"Wikipedia", "NCERT", "the internet"}]
    if remaining:
        if len(remaining) == 1:
            parts.append(f"The prescribed textbook does not provide {remaining[0]}.")
        else:
            parts.append(
                "The prescribed textbook does not provide "
                + ", ".join(remaining[:-1])
                + f", or {remaining[-1]}."
            )
    return "\n\n".join(part for part in parts if part)


def _exam_from_pack(question: str, chunks: list[dict]) -> str:
    from rag.engine.coverage import build_coverage_plan, filter_plan, readable_extract

    plan = filter_plan(question, build_coverage_plan(chunks))
    if not plan:
        return ""
    lines = ["Practice questions from the prescribed Class 9 textbook:"]
    count = 0
    for group in plan[:8]:
        extract = readable_extract(group.chunks)
        sentence = ""
        for piece in re.split(r"(?<=[.!?])\s+", extract or ""):
            piece = piece.strip()
            if len(piece) >= 40:
                sentence = piece
                break
        if not sentence:
            continue
        count += 1
        lines.append(f"{count}. What does the textbook say about {group.title}?")
        lines.append(f"Answer: {sentence}")
        if count >= 5:
            break
    return "\n\n".join(lines) if count else ""


def _asks_outside_textbook(question: str) -> bool:
    lowered = (question or "").lower()
    return bool(
        re.search(
            r"\bnot in (?:this|the|your|our) (?:provided )?textbook\b"
            r"|\boutside (?:this|the|your) textbook\b",
            lowered,
        )
    )


def _outside_textbook(language: str, question: str) -> dict:
    return {
        "answer": (
            "I can only answer from your prescribed Class 9 Karnataka State Board textbook. "
            "Information that is not in the provided textbook cannot be given. "
            f"{NOT_IN_TEXTBOOK}"
        ),
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": question,
        "retrieved": [],
        "selected_chunk_ids": [],
        "validation_reason": "outside_textbook_request",
        "intent": None,
        "mode": "NORMAL",
        "question_type": "DIRECT",
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
        "fallback_used": False,
    }


def _boundary(language: str, question: str) -> dict:
    return {
        "answer": BOUNDARY_EN if language != "kn" else refusal_text("kn"),
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": question,
        "retrieved": [],
        "selected_chunk_ids": [],
        "validation_reason": "off_domain_or_unsupported",
        "intent": None,
        "mode": "NORMAL",
        "question_type": "DIRECT",
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
        "fallback_used": False,
    }


def _clarify(language: str, question: str, intent: str, mode: str) -> dict:
    return {
        "answer": "Which person or event from the textbook should I continue with?",
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": question,
        "retrieved": [],
        "selected_chunk_ids": [],
        "validation_reason": "followup_clarify",
        "intent": intent,
        "mode": mode,
        "question_type": "FOLLOW_UP",
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
        "fallback_used": False,
    }



def _stated_naming_reason(answer: str) -> str | None:
    """The sentence pair that says why someone was called a name, when the draft already has it."""
    link = re.compile(r"\b(?:hence|therefore|thus|because)\b", re.I)
    naming = re.compile(r"\b(?:called|known as|named)\b", re.I)
    for para in re.split(r"\n\s*\n", answer or ""):
        body = re.sub(r"^#+\s+.*$", "", para, flags=re.M).strip()
        if not body:
            continue
        pages = " ".join(re.findall(r"\[Pages?[^\]]+\]", body))
        plain = re.sub(r"\[Pages?[^\]]+\]", "", body)
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", plain) if part.strip()]
        for index, sentence in enumerate(sentences):
            if not naming.search(sentence):
                continue
            previous = sentences[index - 1] if index else ""
            if not (link.search(sentence) or link.search(previous)):
                continue
            parts = [part for part in (previous, sentence) if part]
            text = " ".join(parts)
            if pages:
                text = f"{text} {pages}"
            return text.strip()
    return None


def _apply_why_motive_note(question: str, answer: str, evidence: list[dict], entity: str | None, depth: str | None) -> str:
    """Drop a forced 'no motive' preface. Roles in the textbook are enough to explain why."""
    del question, evidence, entity, depth
    return re.sub(
        r"^\s*The prescribed textbook does not state a motive or reason for this\.\s*"
        r"(?:Here is the surrounding supported context from the textbook:?\s*)?",
        "",
        answer or "",
        count=1,
        flags=re.I,
    ).strip()


def _apply_partial_refusals(question: str, answer: str, evidence: list[dict]) -> str:
    lowered = (question or "").lower()
    blob = " ".join(item.get("text") or "" for item in evidence).lower()
    prefix = []
    if re.search(r"exact (date of )?birth|exact birth date", lowered):
        has_full_date = bool(
            re.search(r"\b\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b", blob)
            or re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}", blob)
        )
        if not has_full_date:
            prefix.append("The exact birth date is not available in the provided textbook.")
    if re.search(r"exact birthplace|exact place of birth", lowered):
        if not re.search(r"\bborn (at|in)\b.{0,40}", blob):
            prefix.append("The prescribed textbook does not provide the exact birthplace.")
    if not prefix:
        return answer
    return "\n\n".join(prefix + [answer])


def _payload(
    answer: str,
    language: str,
    retrieval_query: str,
    hits: list[dict],
    selected: list[dict],
    reason: str,
    intent: str | None,
    mode: str | None,
    regenerations: int,
    claims: list,
    pack,
    fallback: bool,
    coverage: dict | None = None,
    sources: list[dict] | None = None,
) -> dict:
    extra = {}
    if coverage:
        extra["coverage"] = {
            "plan": coverage.get("plan"),
            "expected": (coverage.get("coverage") or {}).get("expected"),
            "generated": (coverage.get("coverage") or {}).get("generated"),
            "missing": (coverage.get("coverage") or {}).get("missing"),
            "grade": (coverage.get("coverage") or {}).get("grade"),
            "regenerated": coverage.get("regenerated"),
        }
    return {
        "answer": sanitize_student_text(answer),
        "language": language,
        "grounded": True,
        "sources": sources if sources is not None else _sources(supporting_evidence(answer, selected, min_overlap=1)),
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected if item.get("chunk_id")],
        "validation_reason": reason,
        "intent": intent,
        "mode": mode,
        "question_type": pack.question_type,
        "resolved_topic": pack.entity or (pack.topics[0] if pack.topics else None),
        "evidence_pack": pack.as_public(),
        "used_supplementary": False,
        "regeneration_count": regenerations,
        "unsupported_claims": claims,
        "fallback_used": fallback,
        **extra,
    }


def _keep_stated_identity(question: str, raw: str, evidence: list[dict], title: str | None) -> str:
    """A who-was answer keeps the textbook sentence that states who the person was.

    Later events can stay. They do not replace "X was the eldest son of Y" or
    "X was the second king".
    """
    if not title or not re.match(r"\s*who\s+(?:was|is|were|are)\b", question or "", re.I):
        if not re.match(r"\s*who\s+(?:was|is|were|are)\b", question or "", re.I):
            return raw
        from rag.engine.classify import extract_topics
        from rag.engine.coverage import GROUP_TITLE
        from rag.engine.pack import detect_entity
        from rag.engine.topic_map import RULER_KEYS

        entity = detect_entity(extract_topics(question or ""))
        title = GROUP_TITLE.get(entity) if entity in RULER_KEYS else None
    if not title:
        return raw
    if re.search(r"\b(?:son|daughter)\s+of\b", raw or "", re.I) and re.search(r"\b(?:king|ruler)\b", raw or "", re.I):
        return raw
    from rag.engine.validate import _evidence_sentences

    identity = None
    for sentence in _evidence_sentences(evidence):
        if title.lower() not in sentence.lower():
            continue
        if re.search(
            r"\bwas the (?:eldest |elder |younger |second |first |third )?(?:son|daughter|king|ruler)\b",
            sentence,
            re.I,
        ):
            identity = sentence.strip()
            identity = re.sub(r"^([A-Z][\w''\-]+)\s+\1\b", r"\1", identity)
            break
    if not identity:
        return raw
    folded = re.sub(r"\s+", " ", (raw or "")).strip()
    if identity.lower() in folded.lower():
        return raw
    return f"{identity} {folded}".strip()


def _identity_focus_evidence(question: str, primary: list[dict], question_type: str, entity: str | None) -> list[dict]:
    """For a single-person DIRECT question, give the LLM only sentences whose subject is that person."""
    from rag.engine.entity import entity_focus_evidence
    from rag.engine.topic_map import RULER_KEYS

    if question_type != "DIRECT" or not entity or entity not in RULER_KEYS:
        return primary
    people = {key for key in extract_topics(question or "") if key in RULER_KEYS}
    if people != {entity}:
        return primary
    focused = entity_focus_evidence(primary, entity)
    if not focused or sum(len((item.get("text") or "").split()) for item in focused) < 25:
        return primary
    return focused


def _mcq_attribution_text(exam: str) -> str:
    """Only stems + correct options decide MCQ citation pages (distractors are not claims)."""
    lines = []
    for block in re.split(r"\n\s*\n", exam or ""):
        stem = re.match(r"\s*\d+\.\s+(.+)", block)
        if not stem:
            continue
        options = dict(re.findall(r"^([A-D])\.\s+(.+)$", block, re.M))
        letter = re.search(r"Answer:\s*([A-D])", block)
        correct = options.get(letter.group(1), "") if letter else ""
        lines.append(f"{stem.group(1).splitlines()[0].rstrip('?')} - {correct}.")
    return "\n".join(lines) or exam


def _model_passage(text: str) -> str:
    """Readable textbook sentences for the model. Fragments are omitted, not rewritten."""
    from rag.engine.entity import repair_leading_stub

    cleaned = repair_leading_stub(" ".join((text or "").split()))
    cleaned = re.sub(r"\b([A-Za-z][A-Za-z'\-]{1,28})(?:\s+\1\b)+", r"\1", cleaned)
    cleaned = re.sub(r"(?:\s+and)?\s+Do you know this\??", "", cleaned, flags=re.I)
    kept = []
    seen = set()
    for part in re.split(r"(?<=[.!?])\s+", cleaned):
        sentence = part.strip(" ;")
        sentence = re.sub(r"^(?:st|yun|cting|eauty)\s+", "", sentence)
        key = re.sub(r"\s+", " ", sentence.lower())
        words = key.split()
        # A complete short sentence such as "Humayun was his father." is evidence.
        # Only drop fragments that are too short to be a statement.
        if len(words) < 3 or key in seen:
            continue
        if len(words) < 5 and not re.search(r"\b(?:was|were|is|are|became|ruled)\b", key):
            continue
        seen.add(key)
        if sentence[-1:] not in ".!?":
            sentence += "."
        kept.append(sentence)
    return " ".join(kept)


_KEY_TERM_EXTRA_GENERIC = frozenset(
    {"battle", "battles", "wars", "empire", "kingdom", "dynasty", "policy", "policies", "reign",
     "rule", "simple", "simply", "easy", "short", "shorter", "points", "table", "answer", "words"}
)


def _key_terms(question: str) -> frozenset[str]:
    """Distinctive words of the question (names, terms), used to check the evidence for them."""
    return frozenset(
        token
        for token in content_tokens(question or "")
        if token not in _GENERIC_WORDS and token not in _KEY_TERM_EXTRA_GENERIC and token.isascii()
    )


_SHORT_COMMON = frozenset(
    {"who", "was", "did", "how", "why", "are", "his", "her", "its", "can", "you", "get", "has", "had",
     "one", "two", "use", "say", "the", "and", "for", "not", "but", "all", "any", "out", "now", "new"}
)


def _guard_terms(question: str) -> frozenset[str]:
    """Key terms plus short distinctive words ("GDP", "tax") for the refusal guard.

    The guard overrides a refusal only when every one of these is in a retrieved passage,
    so an off-textbook term such as "GDP" keeps the refusal.
    """
    short = {
        word
        for word in re.findall(r"\b[a-z]{3}\b", (question or "").lower())
        if word not in STOPWORDS and word not in _SHORT_COMMON and word not in _GENERIC_WORDS
    }
    return _key_terms(question) | frozenset(short)


def _evidence_has_key_terms(
    question: str, items: list[dict], terms: frozenset[str] | None = None
) -> tuple[frozenset[str], list[dict]]:
    """Key terms of the question and the passages that contain every one of them.

    Matching is by prefix of the word so "mansabdar" matches "mansabdari".
    """
    terms = _key_terms(question) if terms is None else terms
    if not terms:
        return terms, []
    matched = []
    for item in items or []:
        lowered = (item.get("text") or "").lower()
        if all(re.search(rf"\b{re.escape(term)}", lowered) for term in terms):
            matched.append(item)
    return terms, matched


@lru_cache(maxsize=1)
def _corpus_text() -> str:
    from rag.engine.topic_map import load_primary_chunks

    return " ".join((item.get("text") or "") for item in load_primary_chunks()).lower()


def _names_term_outside_textbook(question: str) -> bool:
    """True when the question names a key term that appears nowhere in the textbook.

    Misspelt textbook names are corrected first, and questions with a known topic alias never
    count, so 'mansabadri' or 'akbr' keep their textbook evidence.
    """
    corrected = _correct_textbook_spelling(question or "")
    if extract_topics(corrected):
        return False
    corpus = _corpus_text()
    # Only names count: a word written with a capital letter, or a known history word.
    # An ordinary English word the chapter happens not to use must not empty the evidence.
    capitalised = {word.lower() for word in re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]{3,}\b", corrected.strip())}
    terms = [
        term for term in _key_terms(corrected)
        if len(term) >= 4 and (term in capitalised or term in _HISTORY_VOCAB)
    ]
    return any(not re.search(rf"\b{re.escape(term)}", corpus) for term in terms)


def _lexical_rescue(question: str, hits: list[dict]) -> tuple[list[dict], int]:
    """Add textbook chunks that name a rare asked-about term the vector search missed.

    Only used when no retrieved passage names every key term and the term appears in at
    most three textbook chunks (a specific term, not a common word).
    """
    terms = _key_terms(question)
    if not terms:
        return hits, 0
    _, matched = _evidence_has_key_terms(question, hits)
    if matched:
        return hits, 0
    try:
        from rag.engine.topic_map import load_primary_chunks

        corpus = load_primary_chunks()
    except Exception:  # pragma: no cover - corpus unavailable
        return hits, 0
    _, found = _evidence_has_key_terms(question, list(corpus))
    if not found or len(found) > 3:
        return hits, 0
    seen = {item.get("chunk_id") for item in hits or []}
    extra = [item for item in found if item.get("chunk_id") not in seen]
    return extra + list(hits or []), len(extra)


_BULLET_LINE = re.compile(r"^(\s*(?:[-*\u2022]|\d{1,2}[.)])\s+)(.*)$")
_CLAUSE_BREAK = re.compile(
    r",\s+(?=(?:which|who|whom|whose|including|with|permitting|allowing|while|where|and\s+(?:a|an|the|also|he|she|they|it|his|her|their))\b)"
    r"|;\s+|\s+\u2014\s+"
)


def _wants_bullets(question: str) -> bool:
    """Bullets, points or an exam answer (which is asked for as short numbered points)."""
    return bool(re.search(r"\bbullets?\b|\bpoints\b|\bexam\b", question or "", re.I))


_NUMBERED_LINE = re.compile(r"^(\s*)(\d{1,2})([.)])(\s+)")


def _renumber_lists(answer: str) -> str:
    """Renumber each run of numbered lines 1, 2, 3... (after a dropped item left a gap)."""
    lines = (answer or "").split("\n")
    expected = 0
    for index, line in enumerate(lines):
        match = _NUMBERED_LINE.match(line)
        if match:
            expected += 1
            if int(match.group(2)) != expected:
                lines[index] = f"{match.group(1)}{expected}{match.group(3)}{match.group(4)}{line[match.end():]}"
        elif line.strip():
            expected = 0
    return "\n".join(lines)


def _shorten_long_bullets(answer: str, max_words: int = 22, min_head: int = 6) -> tuple[str, int]:
    """Cut an over-long bullet at its first clause break so each bullet stays one short fact.

    Only bullets longer than max_words are touched, and only when the kept head is a
    sentence of at least min_head words. Text is never added, only trailing clauses removed.
    """
    changed = 0
    lines = []
    for line in (answer or "").split("\n"):
        match = _BULLET_LINE.match(line)
        if match and len(match.group(2).split()) > max_words:
            body = match.group(2)
            for brk in _CLAUSE_BREAK.finditer(body):
                head = body[: brk.start()].rstrip(" ,;")
                if len(head.split()) >= min_head:
                    line = f"{match.group(1)}{head}."
                    changed += 1
                    break
        lines.append(line)
    return "\n".join(lines), changed


def _drop_repeated_sentences(answer: str, overlap: float = 0.85) -> tuple[str, int]:
    """Drop a sentence whose content words are (almost) all in one earlier sentence.

    Small models sometimes restate the answer ("Explanation: According to the textbook, ...").
    Structural lines (headings, tables, citations) are never touched.
    """
    from rag.engine.sanitize import is_structural_line

    seen: list[set[str]] = []
    dropped = 0
    out_lines = []
    for line in (answer or "").split("\n"):
        stripped = line.strip()
        if not stripped or is_structural_line(stripped) or stripped.lower().startswith("source:"):
            out_lines.append(line)
            continue
        kept = []
        for sentence in re.split(r"(?<=[.!?])\s+", stripped):
            words = {w for w in re.findall(r"[a-z]{3,}", sentence.lower()) if w not in STOPWORDS}
            if len(words) >= 5 and any(len(words & prev) / len(words) >= overlap for prev in seen):
                dropped += 1
                continue
            if words:
                seen.append(words)
            kept.append(sentence)
        if kept:
            prefix = line[: len(line) - len(line.lstrip())]
            out_lines.append(prefix + " ".join(kept))
    text = "\n".join(out_lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip(), dropped


def _repeated_prior_sentences(answer: str, previous: str) -> int:
    """How many sentences (over 5 words) of the answer appear word for word in the previous answer."""
    def sentences(text: str) -> list[str]:
        body = re.sub(r"\n*Source:.*$", "", text or "", flags=re.I | re.S)
        return [
            " ".join(part.lower().split())
            for part in re.split(r"(?<=[.!?])\s+|\n+", body)
            if len(part.split()) > 5
        ]

    prior = set(sentences(previous))
    return sum(1 for sentence in sentences(answer) if sentence in prior)


def _trim_passage(text: str, limit: int = 700, focus: set[str] | frozenset[str] | None = None) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit].rsplit(". ", 1)[0]
    head = f"{cut}." if cut else cleaned[:limit]
    lowered_head = head.lower()
    missing = {term for term in focus or () if term in cleaned.lower() and term not in lowered_head}
    if not missing:
        return head
    # The asked-about term sits past the cut. Keep the sentences that name it,
    # plus the sentence after each, so the model actually sees it.
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    wanted: set[int] = set()
    for index, sentence in enumerate(sentences):
        if any(term in sentence.lower() for term in missing):
            wanted.update({index, index + 1})
    tail = " ".join(sentences[index] for index in sorted(wanted) if index < len(sentences))
    budget = max(200, limit - len(tail))
    lead = cleaned[:budget].rsplit(". ", 1)[0]
    lead = f"{lead}." if lead and not lead.endswith(".") else lead
    if lead and lead.lower() not in tail.lower():
        return f"{lead} ... {tail}"
    return tail


def _evidence_score(question: str, text: str) -> int:
    """Prefer passages that state the relationship a kinship question is asking about."""
    score = overlap_count(question, text)
    if re.search(r"\b(succeed\w*|successor|father|mother|son|daughter|parent)\b", question or "", re.I):
        if re.search(r"\b(son of|daughter of|eldest son|came to power|succeeded|successor)\b", text or "", re.I):
            score += 12
    return score


def _prompt_evidence(
    question: str,
    hits: list[dict],
    keep: int = 6,
    trim: int = 700,
    used_ids: set[str] | None = None,
) -> list[dict]:
    """A few relevant passages, not the whole chapter.

    A "tell me more" request passes a larger keep/trim budget and the chunk ids the previous
    answer used, so passages the student has not seen yet rank a little higher.
    """
    pool = [item for item in hits or [] if (item.get("text") or "").strip()]
    focus = _key_terms(question)
    cleaned = []
    seen = set()
    for item in pool:
        key = item.get("chunk_id") or (item.get("text") or "")[:80]
        if key in seen:
            continue
        seen.add(key)
        copy = dict(item)
        copy["text"] = _model_passage(_trim_passage(item.get("text") or "", limit=trim, focus=focus))
        copy["_score"] = _evidence_score(question, copy["text"])
        if focus and any(term in copy["text"].lower() for term in focus):
            copy["_score"] += 5
        if used_ids and copy["_score"] > 0 and str(item.get("chunk_id") or "") not in used_ids:
            copy["_score"] += 2
        if copy["text"]:
            cleaned.append(copy)
    cleaned.sort(key=lambda item: item["_score"], reverse=True)
    kept = cleaned[:keep]
    question_terms = content_tokens(question)
    named = set()
    for key in extract_topics(question):
        named.add(key.lower())
        for alias in TOPIC_ALIASES.get(key, ()):
            if isinstance(alias, str):
                named.add(alias.lower())
    named = {token for token in named if token in content_tokens(" ".join(named))}

    def relevant_terms(text: str) -> set[str]:
        tokens = content_tokens(text)
        if named and not (tokens & named):
            return set()
        return tokens & question_terms

    def covered_by(items: list[dict]) -> set[str]:
        found = set()
        for entry in items:
            found |= relevant_terms(entry["text"])
        return found

    # A multi-part question can ask about succession and a defeat together.
    # A word counts as covered only in a passage that also names the person asked about.
    covered = covered_by(kept)
    swaps = 0
    while swaps < 2 and kept:
        missing = question_terms - covered
        if not missing:
            break
        best = None
        best_added: set[str] = set()
        for item in cleaned:
            if item in kept:
                continue
            added = relevant_terms(item["text"]) & missing
            if len(added) > len(best_added):
                best = item
                best_added = added
        if best is None:
            break
        replace_at = None
        for index in range(len(kept) - 1, -1, -1):
            others = covered_by(kept[:index] + kept[index + 1 :])
            unique = relevant_terms(kept[index]["text"]) - others
            if not unique:
                replace_at = index
                break
        if replace_at is None:
            break
        kept[replace_at] = best
        covered |= best_added
        swaps += 1
    for item in kept:
        item.pop("_score", None)
    return kept


_REEXPLAIN_RE = re.compile(
    r"\b(?:i\s+(?:still\s+)?(?:do\s*n[o']?t|did\s*n[o']?t|cannot|can'?t)\s+(?:understand|get\s+it|follow)"
    r"|not\s+clear|(?:i\s+am|i'?m)\s+(?:still\s+)?confused|confusing"
    r"|explain\s+(?:it\s+|that\s+|this\s+)?again|(?:even\s+)?more\s+simply|even\s+simpler|simpler\s+way)\b",
    re.I,
)
_SHORTER_RE = re.compile(r"\b(?:shorter|short answer|in short|briefly|brief|summari[sz]e|in a few lines|quick revision)\b", re.I)
_POINTS_RE = re.compile(
    r"\b(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\s+(?:bullet\s+)?(?:points?|bullets?|facts|lines)\b",
    re.I,
)
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_TABLE_RE = re.compile(r"\btable\b|\btabular\b", re.I)
_EXAM_ANSWER_RE = re.compile(r"\bexam\s+answer\b|\b\d+\s*marks?\b|\bfor (?:the|my) exam\b", re.I)


def _wants_reexplain(question: str) -> bool:
    return bool(_REEXPLAIN_RE.search(question or ""))


def _reexplain_target(question: str, history: list[dict] | None) -> str:
    """The earlier textbook question a 'please explain again' request refers to."""
    if not _wants_reexplain(question) or not history:
        return ""
    for item in reversed(history):
        if (item.get("role") or "").lower() != "user":
            continue
        text = (item.get("content") or "").strip()
        if text and not _wants_reexplain(text) and not _current_question_outside_domain(text):
            return text
    return ""


def _style_request_note(question: str, history: list[dict] | None) -> str:
    """Format the student asked for. Simple Class 9 English is always on (system prompt)."""
    text = question or ""
    notes: list[str] = []
    if _wants_reexplain(text):
        previous = previous_assistant(history)
        previous = re.sub(r"\n*Source:.*$", "", previous, flags=re.I | re.S).strip()[:1500]
        if previous:
            notes.append(
                "The student did not understand your previous answer, shown below. "
                "Explain the same textbook facts again in an even simpler way: shorter sentences, "
                "everyday words, one idea per sentence, and one small everyday example if it helps. "
                "Do not repeat the previous answer or its sentences.\n"
                f"Previous answer:\n{previous}"
            )
        else:
            notes.append(
                "The student finds this hard. Use the simplest words you can, very short sentences, "
                "and one idea per sentence."
            )
    match = _POINTS_RE.search(text)
    if match:
        raw = match.group(1).lower()
        count = int(raw) if raw.isdigit() else _NUMBER_WORDS.get(raw, 5)
        notes.append(
            f"Answer as exactly {count} bullet points, one fact in each. "
            "Each bullet is one short sentence of about 15 words or fewer."
        )
    elif re.search(r"\bbullets?\b|\bpoints\b", text, re.I):
        notes.append("Answer as short bullet points.")
    if _SHORTER_RE.search(text):
        notes.append("Keep it short: 2 to 4 short sentences or a few bullets. Keep the key facts.")
    if _TABLE_RE.search(text):
        notes.append(
            "Start with one direct sentence, then give a simple markdown table with short cells. "
            "Put only textbook facts in the table. If the textbook gives nothing for a cell, write: Not given in the textbook."
        )
    if _EXAM_ANSWER_RE.search(text):
        notes.append(
            "Write it as a clear exam answer: one opening sentence, then numbered points, then one closing sentence. "
            "Each numbered point is one or two short sentences of about 15 words or fewer."
        )
    if not notes:
        return ""
    notes.append("Start directly with the answer. Do not mention these instructions, the student, or the previous answer.")
    return "Format for this answer:\n- " + "\n- ".join(notes) + "\n"


def _drop_outside_context(answer: str) -> tuple[str, bool]:
    """Answers are textbook-only. Remove any 'Additional historical context' section the model adds."""
    parts = re.split(r"\n*\s*(?:\*\*|#+\s*)?Additional historical context\s*:?", answer or "", maxsplit=1, flags=re.I)
    if len(parts) == 1:
        return (answer or "").strip(), False
    return parts[0].strip(), True


def _is_not_found(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith(NOT_IN_TEXTBOOK.lower()):
        return True
    if NOT_IN_TEXTBOOK.lower() in lowered and len(text.split()) <= 40:
        return True
    sentences = [part for part in re.split(r"[.!?\n]+", text) if part.strip()]
    if len(sentences) > 1 or len(text.split()) > 40 or "|" in text:
        return False
    return bool(
        "not available in the textbook" in lowered
        or "not available in the provided textbook" in lowered
        or re.search(r"\b(?:do|does) not (?:give|provide|state|contain|cover)\b", text, re.I)
    )


def _pronoun_context(question: str, history: list[dict] | None, intent: str | None) -> str:
    """Earlier student questions, only when this question needs them for pronouns."""
    needs_prior = intent == "FOLLOW_UP" or bool(PRONOUN_RE.search(question or ""))
    if not needs_prior or not history:
        return ""
    recent = []
    for item in history:
        if (item.get("role") or "").lower() != "user":
            continue
        text = (item.get("content") or item.get("text") or "").strip()
        if text and text.lower() != (question or "").strip().lower():
            recent.append(text)
    recent = recent[-3:]
    if not recent:
        return ""
    lines = "\n".join(f"- {text}" for text in recent)
    note = ""
    if _current_question_outside_domain(recent[-1]):
        note = (
            "The previous question left History and Social Science. "
            "Do not treat an older person as the subject of this question.\n"
        )
    return (
        "Earlier student questions, use only to resolve pronouns in the current question:\n"
        f"{lines}\n"
        f"{note}"
    )


_PASSIVE_RE = re.compile(r"\b(was|were)\s+([a-z]+ed)\b", re.I)
_SUBJECT_TAIL_RE = re.compile(
    r"((?:(?:his|her|their)\s+[a-z]+,\s*)?[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)*)\s*,?\s*$"
)
_ANSWER_SUBJECT_RE = re.compile(r"^(\s*(?:[-*\u2022]|\d+[.)])?\s*)(He|She|[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?)\s+(was|were)\s+([a-z]+ed)\b")


def _evidence_subject(sentence: str, verb: str, participle: str) -> str:
    """The named subject right before 'was <participle>' in a textbook sentence, if any."""
    match = re.search(rf"\b{verb}\s+{participle}\b", sentence, re.I)
    if not match:
        return ""
    tail = _SUBJECT_TAIL_RE.search(sentence[: match.start()])
    return tail.group(1).strip() if tail else ""


def _fix_swapped_subjects(answer: str, evidence: list[dict]) -> tuple[str, int]:
    """Keep who did what as in the textbook.

    If an answer line says "He was captured by the Sultan" but the matching textbook sentence
    says "his father, Shahaji, was captured by the Sultan", put the textbook's subject back.
    Generic: works on any passive "was/were <verb>ed" with a named subject in the passage.
    """
    sentences = []
    for item in evidence or []:
        sentences.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", item.get("text") or "") if part.strip())
    if not sentences:
        return answer, 0
    fixed = 0
    out_lines = []
    for line in (answer or "").splitlines():
        match = _ANSWER_SUBJECT_RE.match(line)
        if not match:
            out_lines.append(line)
            continue
        prefix, subject, verb, participle = match.groups()
        after = content_tokens(line[match.end():][:80])
        best, best_score = "", 0
        for sentence in sentences:
            ev_subject = _evidence_subject(sentence, verb, participle)
            if not ev_subject:
                continue
            position = re.search(rf"\b{verb}\s+{participle}\b", sentence, re.I).end()
            score = len(after & content_tokens(sentence[position:][:80]))
            if score > best_score:
                best, best_score = ev_subject, score
        if not best or best_score < 1:
            out_lines.append(line)
            continue
        named = re.findall(r"[A-Z][\w'\-]+", best)
        if subject.lower() not in {"he", "she"} and any(name.lower() == subject.split()[-1].lower() for name in named):
            out_lines.append(line)
            continue
        if any(name in line[: match.start(3)] for name in named):
            out_lines.append(line)
            continue
        replacement = best[0].upper() + best[1:]
        if "," in replacement:
            replacement += ","
        out_lines.append(f"{prefix}{replacement} {line[match.start(3):]}")
        fixed += 1
    return "\n".join(out_lines), fixed


_SUPPORT_MIN_RATIO = 0.5


def _drop_unsupported_sentences(
    answer: str, support: list[dict], collect: list[str] | None = None
) -> tuple[str, int]:
    """Textbook-only safety net: drop answer sentences the textbook passages do not back.

    A sentence is dropped when fewer than half of its content words appear in the passages,
    or when it names a multi-word name or a year that the passages do not contain.
    Headings, table rows, short intros and "the textbook does not give ..." notes are kept.
    """
    from rag.engine.sanitize import is_structural_line
    from rag.engine.validate import _support_stems, unsupported_named_items

    if not answer or not support:
        return answer, 0
    support_text = " ".join(item.get("text") or "" for item in support)
    support_stems = _support_stems(support_text)
    generic = {word[:6] for word in _GENERIC_WORDS}
    dropped = 0
    out_lines = []
    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped or is_structural_line(stripped) or stripped.startswith("|"):
            out_lines.append(line)
            continue
        marker = re.match(r"^(\s*(?:[-*\u2022]|\d+[.)])\s+)", line)
        prefix = marker.group(1) if marker else ""
        kept = []
        for sentence in re.split(r"(?<=[.!?])\s+", line[len(prefix):]):
            text = sentence.strip()
            if not text:
                continue
            if text.endswith(":") or re.search(r"\btextbook\b", text, re.I):
                kept.append(text)
                continue
            stems = _support_stems(text) - generic
            ratio = len(stems & support_stems) / len(stems) if stems else 1.0
            named = [
                item for item in unsupported_named_items(text, support)
                if " " in item.strip() or re.fullmatch(r"\d{4}", item.strip())
            ]
            if (len(stems) >= 3 and ratio < _SUPPORT_MIN_RATIO) or named:
                dropped += 1
                if collect is not None:
                    collect.append(text)
                continue
            kept.append(text)
        if kept:
            out_lines.append(prefix + " ".join(kept))
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, dropped


# "Tell me more" / "explain in detail" / "elaborate" style requests, including a restated topic
# ("Can you tell me more about this, I mean the Mansabdari system?") and typo'd forms
# ("can you more on this i mean mansabadri system").
_DEPTH_CUE_RE = re.compile(
    r"\b(?:tell\s+(?:me\s+)?more|more\s+(?:details?|information|info|facts|points)"
    r"|more\s+(?:about|on)\b"
    r"|(?:can|could|will|would)\s+you\s+(?:please\s+)?(?:(?:tell|say|explain|write|give|share)\s+(?:me\s+|us\s+)?)?more\b"
    r"|(?:explain|say|write|tell|describe)\s+(?:me\s+)?(?:a\s+bit\s+|a\s+little\s+|some\s+)?more\b"
    r"|elaborate|in\s+(?:more\s+|greater\s+|full\s+|much\s+more\s+)?detail|detailed|go\s+deeper|deeper|in\s+depth"
    r"|expand\s+on|explain\s+(?:it|this|that)\s+(?:further|fully)|further\s+details?"
    r"|what\s+else|anything\s+else\s+about|more\s+deeply|(?:i\s+)?(?:want|need)\s+more)\b",
    re.I,
)
_DEPTH_NOT_RE = re.compile(r"\bmore\s+(?:mcqs?|questions|quiz\w*|simply|simple|easily)\b", re.I)
_DEPTH_FILLER = frozenset(
    """can could will would you please tell say explain write give share describe more about this that
    these those mean meant elaborate detail details detailed deeper depth deeply further expand fully
    else anything information info facts points want need little some topic again also okay actually
    really just like know understand learn""".split()
)
_DEPTH_QUESTION_WORDS = re.compile(r"^\s*(?:what|who|how|why|explain|describe|tell me about)\s+(?:is|was|were|are|the)?\s*", re.I)


def _depth_topic_words(text: str) -> set[str]:
    return {token for token in content_tokens(text or "") if token not in _DEPTH_FILLER}


def _depth_request(question: str, original: str, history: list[dict] | None) -> dict | None:
    """Detect a request for more depth and resolve its topic from the message plus history.

    Returns None for ordinary questions. "followup" is True when it continues the previous
    answer on the same topic; then the previous answer is passed so the model can expand it.
    """
    text = original or question or ""
    if not _DEPTH_CUE_RE.search(text) or _DEPTH_NOT_RE.search(text):
        return None
    if _wants_reexplain(text) or _SHORTER_RE.search(text):
        return None
    # The student's own topic words; none ("tell me more about him", "explain this in more
    # detail") means the topic is the previous question's.
    corrected = _correct_textbook_spelling(text)
    own_words = _depth_topic_words(corrected)
    previous_answer = re.sub(r"\n*Source:.*$", "", previous_assistant(history) or "", flags=re.I | re.S).strip()
    previous_question = ""
    for item in reversed(history or []):
        if (item.get("role") or "").lower() != "user":
            continue
        candidate = (item.get("content") or "").strip()
        if candidate and _depth_topic_words(_correct_textbook_spelling(candidate)):
            previous_question = candidate
            break
    prior_words = content_tokens(previous_question) | content_tokens(previous_answer)
    # Same topic when the distinctive words (not "system", "rule") were already in the
    # previous question or answer.
    distinctive = {word[:6] for word in (set(_key_terms(" ".join(own_words))) or own_words)}
    prior_stems = {word[:6] for word in prior_words}
    followup = bool(previous_answer) and (not own_words or bool(distinctive & prior_stems))
    if own_words:
        topic = " ".join(word for word in re.findall(r"[A-Za-z][A-Za-z'\-]*", corrected) if word.lower() in own_words)
    else:
        topic = _DEPTH_QUESTION_WORDS.sub("", previous_question).strip(" ?.!")
    if not topic:
        return None
    used: set[str] = set()
    if followup:
        for item in reversed(history or []):
            if (item.get("role") or "").lower() == "assistant":
                state = item.get("task_state") or {}
                used = {str(x) for x in (state.get("used_chunk_ids") or state.get("ids") or []) if x}
                break
    return {
        "topic": topic,
        "bare": not own_words,
        "followup": followup,
        "previous_answer": previous_answer[:1800] if followup else "",
        "previous_question": previous_question if followup else "",
        "used_ids": used,
    }


def _answer_units(text: str) -> list[set[str]]:
    """Sentences and bullet items of an answer as word sets (headings and the Source line skipped)."""
    body = re.sub(r"\n*Source:.*$", "", text or "", flags=re.I | re.S)
    units = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            continue
        line = re.sub(r"^(?:[-*\u2022]|\d{1,2}[.)])\s+", "", line).replace("**", "")
        for part in re.split(r"(?<=[.!?])\s+", line):
            words = set(re.findall(r"[a-z0-9]{3,}", part.lower()))
            if len(words) >= 4:
                units.append(words)
    return units


def _repeat_overlap(answer: str, previous: str, near: float = 0.6) -> float:
    """Share of the new answer's sentences/bullets that restate a sentence of the previous answer."""
    new_units = _answer_units(answer)
    old_units = _answer_units(previous)
    if not new_units or not old_units:
        return 0.0
    repeated = 0
    for unit in new_units:
        if any(len(unit & old) / len(unit | old) >= near for old in old_units):
            repeated += 1
    return round(repeated / len(new_units), 2)


def _sentence_jaccard(answer: str, previous: str) -> float:
    """Jaccard over normalised sentences (exact restatements)."""
    norm = lambda text: {" ".join(sorted(unit)) for unit in _answer_units(text)}
    a, b = norm(answer), norm(previous)
    return round(len(a & b) / len(a | b), 2) if (a | b) else 0.0


def _new_word_count(answer: str, previous: str) -> int:
    """Distinct content words (4+ letters) in the answer that the previous answer did not use."""
    strip = lambda text: re.sub(r"\n*Source:.*$", "", text or "", flags=re.I | re.S).lower()
    old = set(re.findall(r"[a-z]{4,}", strip(previous)))
    return len({word for word in re.findall(r"[a-z]{4,}", strip(answer)) if word not in old})


_REPEAT_LIMIT = 0.5
_DEPTH_TOP_K = 24
_DEPTH_KEEP = 10
_DEPTH_TRIM = 1100
_DEPTH_MAX_TOKENS = 1800


def _depth_instruction(depth: dict) -> str:
    topic = depth["topic"]
    lines = [
        f"The student wants a deeper explanation of: {topic}.",
        "Write a fuller explanation than a short summary. In the textbook part use only the passages:",
        "- start with one sentence that says what it is;",
        "- then 2 to 4 short '## ' headings that fit what the passages say (choose your own heading words), "
        "each with 2 to 4 sentences; leave out a heading rather than fill it with a vague sentence;",
        "- explain how the facts connect to each other, not just a list;",
        "- when a passage gives a term (a name of a rank, office, department or tax), give its meaning from the passage;",
        "- end with a 1 to 2 sentence summary.",
        f"Use every detail the passages give about {topic}. You may add related details from the same passages "
        f"(for example the ruler or administration around it), but introduce them as background and do not say "
        f"they are part of {topic} unless a passage says so.",
        "Do not say why it mattered, what effect it had, or that it was efficient unless a passage says so. "
        "Do not compare it with other rulers or kingdoms unless a passage does.",
        f"When the passages have nothing new about {topic}, do not say so and do not stop: put the new "
        f"information (background, how it worked in practice, examples, results) under the "
        f"'{SUPPLEMENT_LABEL}' label. Never present it as textbook content.",
    ]
    if depth.get("previous_answer"):
        lines.append(
            "The student has already read the previous answer below. Do NOT repeat its bullet points or sentences. "
            "Add the details it left out, and when you mention a fact again, explain what it connects to.\n"
            f"Previous answer:\n{depth['previous_answer']}"
        )
    return "\n".join(lines) + "\n"


def _depth_pool(topic: str, hits: list[dict]) -> list[dict]:
    """Passages for a depth request: those that name the topic, plus passages from the same textbook pages.

    A larger evidence budget must not pull in other rulers' passages that only share words
    ("infantry, cavalry"). If too little is left, the original hits are used.
    """
    terms = [term[:6] for term in _key_terms(topic) if len(term) >= 4]
    if not terms:
        return list(hits or [])

    def names_topic(item: dict) -> bool:
        lowered = (item.get("text") or "").lower()
        return any(re.search(rf"\b{re.escape(term)}", lowered) for term in terms)

    pages = {
        item.get("printed_page_number") or item.get("textbook_page_number")
        for item in hits or []
        if names_topic(item)
    }
    pages.discard(None)
    pool = [
        item for item in hits or []
        if names_topic(item) or (item.get("printed_page_number") or item.get("textbook_page_number")) in pages
    ]
    return pool if len(pool) >= 2 else list(hits or [])


_CONTINUE_RE = re.compile(
    r"\b(?:give|show|tell)\s+(?:me\s+)?(?:an?\s+|one\s+|some\s+)?examples?\b|\bfor\s+(?:an\s+)?example\b|\bexample\b"
    r"|\bwhat\s+happened\s+(?:next|after|then|later)\b|\bwhat\s+(?:came|comes)\s+next\b|\bafter\s+(?:that|this)\b"
    r"|\bthen\s+what\b|\brole\s+of\b|\bwhy\s+(?:was|did|is|were)\s+(?:it|this|that|they)\b"
    r"|\bhow\s+did\s+(?:it|this|that|they)\b|\bwhat\s+(?:was|were)\s+(?:its|their)\b|\bresults?\s+of\s+(?:it|this|that)\b",
    re.I,
)


def _continuation(question: str, history: list[dict] | None) -> dict | None:
    """A short follow-up that continues the previous in-scope answer ("give an example",
    "what happened next", "role of nobles"). Returns the previous question and answer."""
    text = (question or "").strip()
    if not history or not text or len(text.split()) > 16 or not _CONTINUE_RE.search(text):
        return None
    previous_answer = re.sub(r"\n*Source:.*$", "", previous_assistant(history) or "", flags=re.I | re.S).strip()
    if not previous_answer or previous_answer.startswith(BOUNDARY_EN[:40]):
        return None
    previous_question = ""
    for item in reversed(history):
        if (item.get("role") or "").lower() != "user":
            continue
        candidate = (item.get("content") or "").strip()
        if not candidate or candidate.lower() == text.lower():
            continue
        if _current_question_outside_domain(candidate) and not extract_topics(candidate):
            continue
        previous_question = candidate
        break
    if not previous_question:
        return None
    return {"previous_question": previous_question, "previous_answer": previous_answer[:1500]}


_SECTION_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:\*\*|__)?\s*(from\s+(?:your|the)\s+textbook|additional\s+historical\s+(?:explanation|context)"
    r"|additional\s+explanation|quick\s+revision)\s*:?\s*(?:\*\*|__)?\s*:?\s*$",
    re.I | re.M,
)


def _split_sections(raw: str) -> tuple[str, str, str, bool]:
    """Split a model answer into (textbook, supplement, revision, labelled)."""
    text = raw or ""
    marks = list(_SECTION_RE.finditer(text))
    if not marks:
        return text.strip(), "", "", False
    parts = {"textbook": [text[: marks[0].start()]], "supplement": [], "revision": []}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        label = mark.group(1).lower()
        key = "textbook" if "textbook" in label else ("revision" if "revision" in label else "supplement")
        parts[key].append(text[mark.end():end])
    join = lambda key: re.sub(r"\n{3,}", "\n\n", "\n".join(parts[key])).strip()
    return join("textbook"), join("supplement"), join("revision"), True


_PAGE_REF_RE = re.compile(r"\b(?:page|pg\.?|p\.)\s*\d+|\[page[^\]]*\]", re.I)


def _clean_supplement(text: str) -> str:
    """Supplementary text never carries a textbook page or claims to be the textbook."""
    out = []
    for line in (text or "").splitlines():
        if _PAGE_REF_RE.search(line):
            line = " ".join(
                part for part in re.split(r"(?<=[.!?])\s+", line) if not _PAGE_REF_RE.search(part)
            )
        line = re.sub(r"\b(?:the|your)\s+textbook\s+(?:says|states|mentions|explains)\s+(?:that\s+)?", "", line, flags=re.I)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


_ABSENCE_RE = re.compile(
    r"\b(?:textbook|passages?|chapter)\b[^.!?\n]*\b(?:does\s+not|do\s+not|doesn't|don't|did\s+not|no\s+(?:information|details?|mention)"
    r"|not\s+(?:mention|cover|give|say|talk|discuss|include|provide))\b"
    r"|\b(?:is|are)\s+not\s+(?:mentioned|covered|given|discussed)\s+in\s+(?:the|your|these)\s+(?:textbook|passages?)\b",
    re.I,
)


def _drop_absence_notes(text: str) -> str:
    """Remove 'the textbook does not mention ...' sentences from the textbook part."""
    out = []
    for line in (text or "").splitlines():
        marker = re.match(r"^(\s*(?:[-*\u2022]|\d+[.)])\s+)", line)
        prefix = marker.group(1) if marker else ""
        parts = [p for p in re.split(r"(?<=[.!?])\s+", line[len(prefix):]) if p.strip()]
        kept = [p for p in parts if not _ABSENCE_RE.search(p)]
        if parts and not kept:
            continue
        out.append(prefix + " ".join(kept) if parts else line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _drop_prior_repeats(text: str, previous: str, keep_one: bool, near: float = 0.6) -> str:
    """Remove sentences/bullets that restate a sentence of the previous answer."""
    old_units = _answer_units(previous)
    if not text or not old_units:
        return text or ""
    out, kept_any, first_dropped = [], False, ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            out.append(line)
            continue
        marker = re.match(r"^(\s*(?:[-*\u2022]|\d{1,2}[.)])\s+)", line)
        prefix = marker.group(1) if marker else ""
        kept = []
        for part in re.split(r"(?<=[.!?])\s+", line[len(prefix):]):
            words = set(re.findall(r"[a-z0-9]{3,}", part.lower().replace("**", "")))
            repeated = len(words) >= 4 and any(len(words & o) / len(words | o) >= near for o in old_units)
            if repeated:
                first_dropped = first_dropped or part.strip()
                continue
            if part.strip():
                kept.append(part.strip())
        if kept:
            kept_any = True
            out.append(prefix + " ".join(kept))
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    # Headings left without content are removed.
    result = re.sub(r"(?m)^#{1,4} [^\n]*\n+(?=#{1,4} |\Z)", "", result).strip()
    if keep_one and not kept_any and first_dropped:
        return first_dropped
    return result


def _compose_sections(textbook: str, supplement: str, revision: str) -> str:
    blocks = []
    if textbook.strip():
        blocks.append(f"**{TEXTBOOK_LABEL}**\n\n{textbook.strip()}")
    if supplement.strip():
        blocks.append(f"**{SUPPLEMENT_LABEL}**\n\n{supplement.strip()}")
    if revision.strip() and blocks:
        blocks.append(f"**{REVISION_LABEL}**\n\n{revision.strip()}")
    return "\n\n".join(blocks)


def _reasoned_history_answer(
    question: str,
    original_question: str,
    language: str,
    retrieval_query: str,
    hits: list[dict],
    intent: str | None,
    mode: str | None,
    depth_profile,
    off_labels: list[str] | None,
    history: list[dict] | None,
    t0: float,
    timings: dict,
) -> dict:
    """One model call over the retrieved passages. Textbook-only."""
    depth = _depth_request(question, original_question, history)
    if depth:
        # More passages and longer ones: retrieve again for the resolved topic (and the earlier
        # question it continues) and merge, so the model has material beyond the first answer.
        extra_query = " ".join(part for part in (depth["topic"], depth.get("previous_question") or "") if part)
        try:
            more_hits = retrieve_primary(extra_query, top_k=_DEPTH_TOP_K, language="en")
        except Exception:  # pragma: no cover - retrieval failure keeps the original hits
            more_hits = []
        seen = {item.get("chunk_id") for item in hits or []}
        hits = list(hits or []) + [item for item in more_hits if item.get("chunk_id") not in seen]
    focus_question = (
        " ".join(part for part in (depth["topic"], depth.get("previous_question") or "") if part) if depth else question
    )
    hits, lexical_rescued = _lexical_rescue(depth["topic"] if depth else question, hits)
    if depth:
        evidence = _prompt_evidence(
            focus_question, _depth_pool(depth["topic"], hits), keep=_DEPTH_KEEP, trim=_DEPTH_TRIM,
            used_ids=depth.get("used_ids"),
        )
    else:
        evidence = _prompt_evidence(question, hits)
    if topic_supported_by_primary(question) is False or (
        not depth and _names_term_outside_textbook(original_question or question)
    ):
        # A named topic the textbook does not cover (Kalinga, Quit India): the passages that were
        # retrieved only share common words, so nothing is shown or cited as textbook content.
        evidence = []
    prior = _pronoun_context(original_question or question, history, intent)
    style = _style_request_note(original_question or question, history)
    continuation = None if (depth or _wants_reexplain(original_question or question)) else _continuation(
        original_question or question, history
    )
    context_note = ""
    if continuation:
        context_note = (
            "This is a follow-up in the same chat. Earlier the student asked: "
            f"{continuation['previous_question']}\n"
            "Your previous answer (already read by the student; continue from it, add new information, "
            f"and do not repeat it):\n{continuation['previous_answer']}\n\n"
        )
    user = (
        f"{prior}"
        f"{context_note}"
        f"Student question: {original_question or question}\n"
        + (
            f"Question with pronouns resolved: {question}\n"
            if (question or "").strip().lower() != (original_question or question or "").strip().lower()
            else ""
        )
        + "\nAnswer the student directly, with the labelled parts.\n"
        "Read every passage, not only the first. "
        "If a passage says someone was another's child, was the next ruler, or came to power after that person, "
        "that is enough to say who succeeded whom and who the parent was. "
        "Answer every part. Use the passages for every part they support, under the textbook label. "
        f"Explain what the passages leave out under the '{SUPPLEMENT_LABEL}' label. "
        "Skip garbled words. Do not write page numbers.\n"
        f"{style}\n"
        + (_depth_instruction(depth) if depth else "")
        + (
            f"Textbook passages:\n{chr(10).join(_blocks(evidence, 'TEXTBOOK'))}"
            if evidence
            else "Textbook passages: none match this question. Leave out the textbook part and give only the "
            f"'{SUPPLEMENT_LABEL}' part. Do not mention a textbook page."
        )
    )
    broad = bool(depth) or (getattr(depth_profile, "depth", "") in {"detail", "broad", "econtent"}) or mode in {
        "DETAILED", "ECONTENT"
    }
    raw = complete(
        [
            {"role": "system", "content": FINAL_ANSWER_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=_DEPTH_MAX_TOKENS if broad else 1100,
    )
    depth_retry = False
    depth_overlap_first = None
    depth_exhausted = False
    previous_for_repeat = (depth or {}).get("previous_answer") or (continuation or {}).get("previous_answer") or ""
    if previous_for_repeat and not _is_not_found(raw or ""):
        previous = previous_for_repeat
        depth_overlap_first = _repeat_overlap(raw or "", previous)
        if depth_overlap_first >= _REPEAT_LIMIT:
            # The model restated the previous answer although the student asked to continue.
            depth_retry = True
            retry_raw = complete(
                [
                    {"role": "system", "content": FINAL_ANSWER_PROMPT},
                    {
                        "role": "user",
                        "content": user
                        + "\n\nYour last reply mostly repeated the previous answer. Write it again with NEW details: "
                        "use the passage details that the previous answer did not mention, explain how the facts "
                        "connect, and do not restate the previous answer's points. If the passages have "
                        f"nothing more, add new information under the '{SUPPLEMENT_LABEL}' label.",
                    },
                ],
                temperature=0.4,
                max_tokens=_DEPTH_MAX_TOKENS,
            )
            if retry_raw and not _is_not_found(retry_raw) and _repeat_overlap(retry_raw, previous) < depth_overlap_first:
                raw = retry_raw
            # Recorded for diagnostics only; a long answer is never cut or labelled for this.
            depth_exhausted = _repeat_overlap(raw or "", previous) >= _REPEAT_LIMIT and _new_word_count(raw or "", previous) < 20
    reexplain_retry = False
    if _wants_reexplain(original_question or question):
        previous = previous_assistant(history)
        if previous and _repeated_prior_sentences(raw or "", previous) >= 3:
            # The model restated its previous answer although the student said they did not
            # understand it. Ask once more, explicitly for new and shorter sentences.
            reexplain_retry = True
            retry_raw = complete(
                [
                    {"role": "system", "content": FINAL_ANSWER_PROMPT},
                    {
                        "role": "user",
                        "content": user
                        + "\n\nYour last reply repeated the previous answer word for word. "
                        "Write a NEW explanation: at most 6 very short sentences, everyday words, "
                        "and none of the previous answer's sentences.",
                    },
                ],
                temperature=0.4,
                max_tokens=600,
            )
            if retry_raw and _repeated_prior_sentences(retry_raw, previous) < _repeated_prior_sentences(raw or "", previous):
                raw = retry_raw
    raw = _strip_invented_pages(raw or "")
    if _is_not_found(raw):
        raw = ""
    textbook_part, supplement_part, revision_part, labelled = _split_sections(raw)
    dropped_outside = bool(supplement_part)
    if not evidence:
        # Nothing in the textbook matched: everything is supplementary and uncited.
        supplement_part = "\n\n".join(part for part in (textbook_part, supplement_part) if part.strip())
        textbook_part = ""
    # "The textbook does not mention X" is not a textbook fact: it must not stand alone under the
    # textbook label or earn a citation.
    textbook_part = _drop_absence_notes(textbook_part)
    if _is_not_found(textbook_part):
        textbook_part = ""
    textbook_part, subjects_fixed = _fix_swapped_subjects(textbook_part, evidence)
    moved: list[str] = []
    textbook_part, unsupported_dropped = _drop_unsupported_sentences(
        textbook_part, list(evidence) + list(hits or []), collect=moved
    )
    if moved:
        # Not backed by the passages: keep it, but only as supplementary explanation.
        supplement_part = "\n\n".join(part for part in (" ".join(moved), supplement_part) if part.strip())
    if not supplement_part.strip():
        textbook_part = _apply_why_motive_note(
            question, textbook_part, evidence, None, getattr(depth_profile, "depth", None)
        )
    if previous_for_repeat:
        # A follow-up must add new information: textbook sentences the student already read are
        # dropped (one is kept as the anchor), and a repeated supplement sentence is dropped too.
        textbook_part = _drop_prior_repeats(textbook_part, previous_for_repeat, keep_one=True)
        supplement_part = _drop_prior_repeats(supplement_part, previous_for_repeat, keep_one=False)
    if _SHORTER_RE.search(original_question or question or "") and textbook_part.strip():
        # "In a shorter way": the textbook answer alone; no extra section.
        supplement_part, revision_part = "", ""
    textbook_part, repeats_tb = _drop_repeated_sentences(textbook_part)
    supplement_part, repeats_sup = _drop_repeated_sentences(_clean_supplement(supplement_part))
    revision_part = _clean_supplement(revision_part)
    repeats_dropped = repeats_tb + repeats_sup
    if unsupported_dropped or repeats_dropped:
        textbook_part = _renumber_lists(textbook_part)
        supplement_part = _renumber_lists(supplement_part)
    bullets_shortened = 0
    if _wants_bullets(original_question or question):
        textbook_part, short_a = _shorten_long_bullets(textbook_part)
        supplement_part, short_b = _shorten_long_bullets(supplement_part)
        bullets_shortened = short_a + short_b

    def _ground(text: str) -> tuple[bool, list[dict]]:
        if _is_not_found(text):
            return True, []
        found = _sources(supporting_evidence(text, evidence, min_overlap=2))
        if not found:
            found = _sources(supporting_evidence(text, evidence, min_overlap=1))
        # No sources means nothing in the text is backed by a textbook passage.
        return (not found), found

    textbook_missing, sources = _ground(textbook_part) if evidence else (True, [])
    if textbook_missing and textbook_part.strip():
        # Text the passages do not back is never shown under the textbook label or cited.
        supplement_part = "\n\n".join(part for part in (textbook_part, supplement_part) if part.strip())
        textbook_part = ""
    not_found = not (textbook_part.strip() or supplement_part.strip())
    not_found_kind = ""
    refusal_guard = ""
    if not_found:
        guard_terms = _guard_terms(question)
        key_terms, term_hits = _evidence_has_key_terms(question, hits if evidence else [], guard_terms)
        _, term_evidence = _evidence_has_key_terms(question, evidence, guard_terms)
        if not evidence:
            not_found_kind = "no_evidence"
        elif not key_terms or not term_hits:
            not_found_kind = "key_term_not_retrieved"
        else:
            not_found_kind = "model_refused_with_evidence"
            focus_items = term_evidence or [
                {**item, "text": _model_passage(_trim_passage(item.get("text") or "", focus=key_terms))}
                for item in term_hits
            ]
            retry_user = (
                f"Student question: {original_question or question}\n\n"
                "The textbook passages below DO talk about this. "
                "Explain what they say about it, in simple English, using only these passages. "
                "Do not say the topic is unavailable. Do not write page numbers or labels.\n"
                f"{style}\n"
                f"Textbook passages:\n{chr(10).join(_blocks(focus_items[:4], 'TEXTBOOK'))}"
            )
            retry = complete(
                [
                    {"role": "system", "content": FINAL_ANSWER_PROMPT},
                    {"role": "user", "content": retry_user},
                ],
                temperature=0.1,
                max_tokens=800,
            )
            retry = _strip_invented_pages(retry or "")
            retry_tb, retry_sup, _retry_rev, _ = _split_sections(retry)
            retry_tb, _ = _drop_unsupported_sentences(retry_tb, list(focus_items) + list(hits or []))
            evidence_backup = evidence
            evidence = focus_items[:4] + [item for item in evidence_backup if item not in focus_items[:4]]
            retry_not_found, retry_sources = _ground(retry_tb)
            if not retry_not_found:
                textbook_part, sources, not_found = retry_tb, retry_sources, False
                supplement_part = _clean_supplement(retry_sup)
                refusal_guard = "retried"
            else:
                fallback = _safe_from_evidence(focus_items, question)
                fallback_sources = _sources(focus_items[:4])
                if fallback_sources and not fallback.startswith("The provided textbook does not give"):
                    textbook_part, sources, not_found = fallback, fallback_sources, False
                    refusal_guard = "extractive_fallback"
        _LOG.info(
            "reasoned_history not_found_kind=%s key_terms=%d term_hits=%d evidence=%d guard=%s",
            not_found_kind,
            len(key_terms),
            len(term_hits),
            len(evidence),
            refusal_guard or "none",
        )
    if not textbook_part.strip():
        sources = []
    if not_found:
        raw = NOT_IN_TEXTBOOK
    else:
        raw = _compose_sections(textbook_part, supplement_part, revision_part)
    raw = _decorate_student_answer(original_question, raw, off_labels)
    answer = raw if not sources else f"{raw}\n\n{_citation_block(sources)}"
    result = {
        "answer": sanitize_student_text(answer),
        "language": language,
        "grounded": bool(sources),
        "sources": sources,
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item.get("chunk_id") for item in evidence if item.get("chunk_id")],
        "validation_reason": "reasoned_history_not_found" if not_found else "reasoned_history",
        "intent": intent,
        "mode": mode or "NORMAL",
        "question_type": "DIRECT",
        "used_supplementary": bool(supplement_part.strip()) and not not_found,
        "answer_sections": {
            "textbook": bool(textbook_part.strip()) and not not_found,
            "supplement": bool(supplement_part.strip()) and not not_found,
            "revision": bool(revision_part.strip()) and not not_found,
            "labelled_by_model": labelled,
        },
        "supplement_moved_sentences": len(moved),
        "dropped_outside_context": False,
        "had_supplement_section": dropped_outside,
        "not_found_kind": not_found_kind if not_found else "",
        "refusal_guard": refusal_guard,
        "lexical_rescued": lexical_rescued,
        "bullets_shortened": bullets_shortened,
        "repeats_dropped": repeats_dropped,
        "reexplain_retry": reexplain_retry,
        "depth_request": (
            {"topic": depth["topic"], "followup": depth["followup"], "evidence": len(evidence),
             "overlap_first": depth_overlap_first, "retry": depth_retry, "exhausted": depth_exhausted}
            if depth else None
        ),
        "subjects_fixed": subjects_fixed,
        "unsupported_sentences_dropped": unsupported_dropped,
        "regeneration_count": 0,
        "unsupported_claims": [],
        "fallback_used": False,
    }
    if depth_profile is not None:
        result["depth"] = depth_profile.as_public()
        result["task"] = {
            "type": "EXPLAIN",
            "topic": None,
            "entity": None,
            "used_chunk_ids": result["selected_chunk_ids"],
            "depth": "more" if depth and depth.get("followup") else depth_profile.depth,
        }
    timings["T8_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["timings"] = timings
    return result


def _ask_llm(question: str, primary: list[dict], mode: str, strict: bool, question_type: str = "DIRECT", depth_profile=None, entity: str | None = None) -> dict:
    primary_blocks = _blocks(primary, "TEXTBOOK")
    extra = ""
    if strict:
        extra = (
            "\nSTRICT MODE: Use only names, dates, and events that appear in the evidence. "
            "If a detail is missing from the evidence, omit it. Do not guess."
        )
    # Simple Class 9 English is the default (SYSTEM_PROMPT). An explicit request
    # for easier words still asks for paraphrase instead of copied sentences.
    if re.search(r"simply|class 9 student|i don'?t understand|quick revision|easy english|simple english|easy language", question or "", re.I):
        extra += (
            "\nUse even simpler words and very short sentences. Do not add extra facts. "
            "Do not copy long textbook sentences unchanged; paraphrase the evidence simply."
        )
    format_note = _style_request_note(question, None)
    if format_note:
        extra += "\n" + format_note.strip()
    if wants_easy_english(question or "") or re.search(r"\btell me about\b", question or "", re.I):
        extra += (
            "\nIf this is a tell-me-about request, use short sections such as "
            "## Who was this person? ## What did they do? ## Important points. "
            "Only include a heading when the evidence supports it."
        )
    if looks_like_roleplay(question or ""):
        extra += "\nDo not write fiction or invented dialogue. State textbook facts only."
    if question_type == "EXAM":
        extra += "\nWrite short textbook-grounded practice questions and answers. Do not invent facts."
    if depth_profile is not None:
        extra += "\n" + depth_prompt_extra(depth_profile, chunks=primary, entity=entity, question=question)
    if question_type == "BROAD_TOPIC":
        primary_blocks = _blocks(primary, "TEXTBOOK", max_chars=650)
        user = (
            f"Language: en\nMode: DETAILED\nQuestion type: BROAD_TOPIC\n"
            f"Student question: {question}\n"
            "The evidence is ordered by textbook page. Cover EVERY person and section that appears in the evidence. "
            "Do not stop after the first page. Use simple Class 9 English. "
            "Do not add facts from other books or general knowledge.\n\n"
            f"TEXTBOOK evidence:\n{chr(10).join(primary_blocks)}\n"
            f"{extra}\n"
            "Do not add page numbers; the system will attach them."
        )
        max_tokens = 1200
    elif mode == "DETAILED":
        user = (
            f"Language: en\nMode: DETAILED\n"
            f"Student question: {question}\n"
            "Write a complete Class 9 explanation using ALL relevant facts in the evidence. "
            "Use optional headings only when the evidence supports them. "
            "Do not add facts from other books or general knowledge.\n\n"
            f"TEXTBOOK evidence:\n{chr(10).join(primary_blocks)}\n"
            f"{extra}\n"
            "Do not add page numbers; the system will attach them."
        )
        max_tokens = 1200 if question_type == "BROAD_TOPIC" else 1000
    else:
        user = (
            f"Language: en\nMode: NORMAL\n"
            f"Student question: {question}\n"
            "Start with one direct sentence if this is a Who/When/Who-built question. "
            "Then include every related fact that is actually in the evidence. "
            "Do not add extra biography from other books.\n\n"
            f"TEXTBOOK evidence:\n{chr(10).join(primary_blocks)}\n"
            f"{extra}\n"
            "Do not add page numbers; the system will attach them."
        )
        max_tokens = 700
    if depth_profile is not None:
        max_tokens = max(max_tokens, int(getattr(depth_profile, "max_tokens", max_tokens) or max_tokens))
    raw = complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.0 if strict else 0.1,
        max_tokens=max_tokens,
    )
    return {"raw": raw}


def _blocks(evidence: list[dict], label: str, max_chars: int | None = None) -> list[str]:
    blocks = []
    for item in evidence:
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        text = item.get("text") or ""
        if max_chars and len(text) > max_chars:
            text = text[: max_chars - 3].rsplit(" ", 1)[0] + "..."
        blocks.append(f"[{label}; printed_page={page}]\n{text}")
    return blocks or [f"[{label}] (none)"]


def _safe_from_evidence(evidence: list[dict], question: str = "") -> str:
    lines = [
        "Here is what the Class 9 Karnataka textbook says on this topic. "
        "No extra facts are added beyond the textbook."
    ]
    ranked = []
    seen = set()
    for item in evidence:
        text = " ".join((item.get("text") or "").split())
        if len(text) < 40:
            continue
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append((overlap_count(question, text), text))
    ranked.sort(key=lambda row: -row[0])
    kept = [text for score, text in ranked if not question or score >= 2][:4]
    if not kept:
        kept = [text for score, text in ranked if score >= 1][:3]
    for text in kept:
        snippet = text if len(text) <= 420 else text[:417].rsplit(" ", 1)[0] + "..."
        lines.append(f"• {snippet}")
    if len(lines) == 1:
        return (
            "The provided textbook does not give enough information to answer this fully.\n\n"
            "No extra facts are added beyond the textbook."
        )
    if len(kept) <= 1:
        lines.insert(1, "The provided textbook does not give enough information to answer this fully.")
    return "\n\n".join(lines)


def _kannada_unavailable(question: str) -> dict:
    return {
        "answer": KANNADA_UNAVAILABLE,
        "language": "kn",
        "grounded": False,
        "sources": [],
        "retrieval_query": question,
        "retrieved": [],
        "selected_chunk_ids": [],
        "validation_reason": "kannada_corpus_unavailable",
        "intent": None,
        "mode": "KANNADA_UNAVAILABLE",
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
    }


def _unavailable(
    language: str,
    retrieval_query: str,
    hits: list[dict],
    selected: list[dict],
    intent: str | None = None,
    mode: str | None = None,
) -> dict:
    return {
        "answer": refusal_text(language) if language == "kn" else BOUNDARY_EN,
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
        "validation_reason": "insufficient_evidence",
        "intent": intent,
        "mode": mode,
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
    }


def _limited(language: str, retrieval_query: str, hits: list[dict], selected: list[dict], intent: str, mode: str) -> dict:
    return {
        "answer": LIMITED_EN,
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item.get("chunk_id") for item in selected if item.get("chunk_id")],
        "validation_reason": "limited_primary_coverage",
        "intent": intent,
        "mode": mode,
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
    }


def _sources(selected: list[dict]) -> list[dict]:
    seen = []
    used = set()
    for item in selected:
        if (item.get("authority") or "primary") == "approved_supplementary":
            continue
        key = (
            item.get("chunk_id"),
            item.get("printed_page_number") or item.get("textbook_page_number"),
        )
        if key in used:
            continue
        used.add(key)
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        seen.append(
            {
                "textbook_page_number": page,
                "printed_page_number": page,
                "pdf_page_number": item.get("pdf_page_number"),
                "chunk_id": item.get("chunk_id"),
                "source_type": item.get("source_type") or "primary_textbook",
                "authority": "primary",
                "citation_label": item.get("citation_label")
                or "Class 9 Karnataka State Board 2026–27 textbook",
                "document_name": item.get("document_name"),
            }
        )
    seen.sort(
        key=lambda item: int(item["printed_page_number"])
        if str(item.get("printed_page_number") or "").isdigit()
        else 99
    )
    return seen


def _citation_block(sources: list[dict]) -> str:
    if not sources:
        return ""
    return _format_cite(
        sources[0].get("citation_label") or "Class 9 Karnataka State Board 2026–27 textbook",
        sources,
    )


def _format_cite(label: str, sources: list[dict]) -> str:
    pages = sorted(
        {
            int(item["printed_page_number"])
            for item in sources
            if item.get("printed_page_number") is not None
        }
    )
    if not pages:
        return f"Source: {label}"
    page_bit = f"page {pages[0]}" if len(pages) == 1 else "pages " + ", ".join(str(p) for p in pages)
    return f"Source: {label}, {page_bit}"


def _strip_invented_pages(answer: str) -> str:
    lines = []
    for line in answer.splitlines():
        lowered = line.strip().lower()
        if lowered.startswith("source:") or lowered.startswith("additional school-book"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _public_hits(hits: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": item.get("chunk_id"),
            "distance": item.get("distance"),
            "textbook_page_number": item.get("textbook_page_number"),
            "printed_page_number": item.get("printed_page_number"),
            "pdf_page_number": item.get("pdf_page_number"),
            "source_type": item.get("source_type"),
            "authority": item.get("authority"),
        }
        for item in hits
    ]

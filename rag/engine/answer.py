"""Textbook-only grounded answer engine. Approved Class 9 textbook is the sole student source."""

from __future__ import annotations

import re

from rag.engine.citations import supporting_evidence
from rag.engine.classify import (
    TOPIC_ALIASES,
    casual_reply,
    classify_answer_mode,
    classify_casual,
    classify_intent,
    classify_question_type,
    extract_topics,
    last_user_question,
    strip_leading_greeting,
)
from rag.engine.evidence import evidence_is_sufficient, evidence_matches_topic, overlap_count
from rag.engine.intent import (
    entity_focus_query,
    infer_previous_task,
    is_more_followup,
    looks_like_mcq_request,
    previous_assistant,
    requested_item_count,
    wants_easy_english,
)
from rag.engine.mcq import mcqs_from_pack
from rag.engine.normalize import (
    looks_kannada,
    looks_like_injection,
    looks_like_roleplay,
    normalize_question,
    rewrite_for_retrieval,
    trim_history,
)
from rag.engine.pack import build_evidence_pack, detect_entity
from rag.engine.coverage import generate_from_plan
from rag.engine.validate import is_refusal, unsupported_named_items, validate_answer
from rag.llm.client import complete
from rag.llm.config import RAG_TOP_K
from rag.prompts.tutor import KANNADA_UNAVAILABLE, SYSTEM_PROMPT, refusal_text
from rag.vectorstore.retrieve import retrieve_primary

LIMITED_EN = (
    "The Class 9 Karnataka State Board 2026–27 textbook has limited information on this topic."
)
LIMITED_TERMS = ("mansab", "mansabdari", "sulh-i", "coparcenary", "nur jahan")

BOUNDARY_EN = (
    "I can help with topics covered in your prescribed Class 9 Karnataka State Board textbook. "
    "This information is not available in the provided textbook."
)
OUTSIDE_SOURCE_NOTE = (
    "I can only use your prescribed Class 9 Karnataka State Board textbook, "
    "not Wikipedia, NCERT, the internet, or other books."
)
ROLEPLAY_NOTE = (
    "I cannot invent a fictional story or dialogue. Here is what the prescribed textbook says."
)
OFF_DOMAIN_CLAUSES = (
    (r"capital of karnataka", "the capital of Karnataka"),
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
)


def answer_question(
    question: str,
    language: str = "en",
    history: list[dict] | None = None,
) -> dict:
    language = "kn" if language == "kn" else "en"
    question = normalize_question(question)
    history = trim_history(history)
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
    if _asks_outside_textbook(rag_question):
        return _outside_textbook(language, rag_question)
    search_question = _strip_off_domain(rag_question) or rag_question
    previous_task = infer_previous_task(history)
    more = is_more_followup(search_question) or is_more_followup(rag_question)
    if more and previous_task == "MCQ":
        search_question = last_user_question(history) or search_question
        mode = "DETAILED"
        intent = "FOLLOW_UP"
        question_type = "EXAM"
        previous = last_user_question(history)
        retrieval_query = entity_focus_query(
            detect_entity(extract_topics(search_question)),
            extract_topics(search_question),
            "BROAD_TOPIC" if "mughal" in extract_topics(search_question) else "EXAM",
        ) or search_question
    elif more and previous_task == "EXPLAIN":
        previous = last_user_question(history)
        labels = [TOPIC_ALIASES[key][0] for key in extract_topics(previous) if key in TOPIC_ALIASES]
        search_question = f"tell me more about {' '.join(labels)}" if labels else search_question
        mode = classify_answer_mode(search_question)
        intent = "FOLLOW_UP"
        question_type = classify_question_type(search_question, None)
        retrieval_query = entity_focus_query(
            detect_entity(extract_topics(search_question)),
            extract_topics(search_question),
            question_type,
        ) or search_question
    else:
        mode = classify_answer_mode(search_question)
        intent = classify_intent(search_question, history)
        question_type = classify_question_type(search_question, intent)
        previous = last_user_question(history) if intent == "FOLLOW_UP" else ""
        if intent == "FOLLOW_UP" and not extract_topics(previous) and not extract_topics(search_question):
            return _clarify(language, rag_question, intent, mode)
        rewrite_history = []
        if intent == "FOLLOW_UP" and previous:
            rewrite_history = [{"role": "user", "content": previous}]
        focus = entity_focus_query(
            detect_entity(extract_topics(search_question)),
            extract_topics(search_question),
            question_type,
        )
        retrieval_query = focus or rewrite_for_retrieval(
            search_question, rewrite_history, force=bool(rewrite_history)
        )

    top_k = 16 if question_type == "BROAD_TOPIC" else (14 if mode == "DETAILED" else 10)
    top_k = max(RAG_TOP_K, top_k)
    primary_hits = retrieve_primary(retrieval_query, top_k=top_k, language="en")
    if looks_like_mcq_request(search_question) or looks_like_mcq_request(rag_question):
        question_type = "EXAM"
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

    if looks_like_injection(rag_question) and not extract_topics(search_question):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if looks_like_injection(rag_question) and not evidence_matches_topic(
        search_question, retrieval_query, primary_selected
    ):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if not evidence_is_sufficient(primary_selected) or not evidence_matches_topic(
        search_question, retrieval_query, primary_selected
    ):
        if _looks_limited(search_question) and evidence_is_sufficient(primary_selected):
            return _limited(language, retrieval_query, primary_hits, primary_selected, intent, mode)
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)

    selected = list(primary_selected)
    if question_type == "EXAM":
        mcq_turn = looks_like_mcq_request(search_question) or looks_like_mcq_request(rag_question) or (
            more and previous_task == "MCQ"
        )
        if mcq_turn:
            count = requested_item_count(search_question if looks_like_mcq_request(search_question) else rag_question)
            exam = mcqs_from_pack(
                search_question,
                selected,
                count=count,
                previous_answer=previous_assistant(history) if more else "",
            )
            if exam:
                sources = _sources(supporting_evidence(exam, selected, min_overlap=2))
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
                result["task"] = "MCQ"
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
        question_type == "FOLLOW_UP" and (pack.facet == "administration" or len(selected) >= 5)
    )
    regenerations = 0
    coverage_info = None
    if use_plan:
        plan_type = "BROAD_TOPIC" if question_type == "BROAD_TOPIC" else "EXPLANATION"
        covered = generate_from_plan(search_question, selected, plan_type)
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
            from rag.engine.coverage import combine_sections, filter_plan, readable_extract, build_coverage_plan

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
        raw = _apply_partial_refusals(rag_question, raw, selected)
        raw = _decorate_student_answer(rag_question, raw, off_labels)
        sources = _sources(supporting_evidence(raw, selected, min_overlap=2))
        if not sources:
            sources = _sources(supporting_evidence(raw, selected, min_overlap=1))
        answer = f"{raw}\n\n{_citation_block(sources)}"
        return _payload(
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

    payload = _ask_llm(search_question, primary_selected, mode, strict=False, question_type=question_type)
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
        payload = _ask_llm(search_question, primary_selected, mode, strict=True, question_type=question_type)
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
            raw = _safe_from_evidence(selected, search_question)
            reason = f"{reason}+extractive_fallback"
            sources = _sources(supporting_evidence(raw, selected, min_overlap=1))
            answer = f"{_decorate_student_answer(rag_question, raw, off_labels)}\n\n{_citation_block(sources)}"
            return _payload(
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
        result = _unavailable(language, retrieval_query, primary_hits, selected, intent=intent, mode=mode)
        result["validation_reason"] = reason
        result["regeneration_count"] = regenerations
        result["unsupported_claims"] = claims
        result["evidence_pack"] = pack.as_public()
        result["question_type"] = question_type
        return result

    raw = _strip_invented_pages(payload["raw"])
    raw = _apply_partial_refusals(rag_question, raw, selected)
    raw = _decorate_student_answer(rag_question, raw, off_labels)
    sources = _sources(supporting_evidence(raw, selected, min_overlap=1 if mode == "DETAILED" else 2))
    answer = f"{raw}\n\n{_citation_block(sources)}"
    return _payload(
        answer,
        language,
        retrieval_query,
        primary_hits,
        selected,
        reason,
        intent,
        mode,
        regenerations,
        [],
        pack,
        fallback=False,
    )


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
    return (
        "not in the textbook" in lowered
        or "not in the provided textbook" in lowered
        or "outside the textbook" in lowered
    )


def _outside_textbook(language: str, question: str) -> dict:
    return {
        "answer": (
            "I can only answer from your prescribed Class 9 Karnataka State Board textbook. "
            "Information that is not in the provided textbook cannot be given. "
            "This topic is not available in the provided textbook."
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
        "answer": answer,
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


def _ask_llm(question: str, primary: list[dict], mode: str, strict: bool, question_type: str = "DIRECT") -> dict:
    primary_blocks = _blocks(primary, "TEXTBOOK")
    extra = ""
    if strict:
        extra = (
            "\nSTRICT MODE: Use only names, dates, and events that appear in the evidence. "
            "If a detail is missing from the evidence, omit it. Do not guess."
        )
    if re.search(r"simply|class 9 student|i don'?t understand|quick revision|easy english|simple english|easy language", question or "", re.I):
        extra += (
            "\nWrite in very simple Class 9 English. Use short sentences. "
            "Use markdown headings and bullet points. Do not add extra facts. "
            "Do not copy long textbook sentences unchanged; paraphrase the evidence simply."
        )
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

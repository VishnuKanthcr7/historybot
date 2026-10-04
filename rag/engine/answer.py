"""Textbook-only grounded answer engine. Approved Class 9 textbook is the sole student source."""

from __future__ import annotations

import re

from rag.engine.citations import supporting_evidence
from rag.engine.classify import (
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
from rag.engine.normalize import (
    looks_kannada,
    looks_like_injection,
    normalize_question,
    rewrite_for_retrieval,
    trim_history,
)
from rag.engine.pack import build_evidence_pack
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
    if _asks_outside_textbook(rag_question):
        return _outside_textbook(language, rag_question)
    mode = classify_answer_mode(rag_question)
    intent = classify_intent(rag_question, history)
    question_type = classify_question_type(rag_question, intent)
    previous = last_user_question(history) if intent == "FOLLOW_UP" else ""
    if intent == "FOLLOW_UP" and not extract_topics(previous) and not extract_topics(rag_question):
        return _clarify(language, rag_question, intent, mode)
    rewrite_history = []
    if intent == "FOLLOW_UP" and previous:
        rewrite_history = [{"role": "user", "content": previous}]
    retrieval_query = rewrite_for_retrieval(rag_question, rewrite_history, force=bool(rewrite_history))

    top_k = 16 if question_type == "BROAD_TOPIC" else (14 if mode == "DETAILED" else 10)
    top_k = max(RAG_TOP_K, top_k)
    primary_hits = retrieve_primary(retrieval_query, top_k=top_k, language="en")
    pack = build_evidence_pack(
        rag_question,
        retrieval_query,
        question_type,
        raw_hits=primary_hits,
        history=history,
    )
    primary_selected = pack.chunks

    if looks_like_injection(rag_question) and not extract_topics(rag_question):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if looks_like_injection(rag_question) and not evidence_matches_topic(
        rag_question, retrieval_query, primary_selected
    ):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if not evidence_is_sufficient(primary_selected) or not evidence_matches_topic(
        rag_question, retrieval_query, primary_selected
    ):
        if _looks_limited(rag_question) and evidence_is_sufficient(primary_selected):
            return _limited(language, retrieval_query, primary_hits, primary_selected, intent, mode)
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)

    selected = list(primary_selected)
    use_plan = question_type in {"BROAD_TOPIC", "EXPLANATION"} or (
        question_type == "FOLLOW_UP" and (pack.facet == "administration" or len(selected) >= 5)
    )
    regenerations = 0
    coverage_info = None
    if use_plan:
        plan_type = "BROAD_TOPIC" if question_type == "BROAD_TOPIC" else "EXPLANATION"
        covered = generate_from_plan(rag_question, selected, plan_type)
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

            plan = filter_plan(rag_question, build_coverage_plan(selected))
            raw = combine_sections(
                rag_question,
                [(group, readable_extract(group.chunks)) for group in plan],
            )
            reason = f"{reason}+structured_fallback"
            claims = unsupported_named_items(raw, selected)
            covered["fallback_used"] = True
            coverage_info = covered
        raw = _strip_invented_pages(raw)
        raw = _apply_partial_refusals(rag_question, raw, selected)
        cite_pages = set()
        for pages in (covered.get("section_pages") or {}).values():
            cite_pages.update(pages or [])
        if not cite_pages:
            sources = _sources(supporting_evidence(raw, selected, min_overlap=1))
        else:
            sources = _sources(
                [
                    item
                    for item in selected
                    if (item.get("printed_page_number") or item.get("textbook_page_number")) in cite_pages
                ]
            )
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

    payload = _ask_llm(rag_question, primary_selected, mode, strict=False, question_type=question_type)
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
        payload = _ask_llm(rag_question, primary_selected, mode, strict=True, question_type=question_type)
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
            raw = _safe_from_evidence(selected, rag_question)
            reason = f"{reason}+extractive_fallback"
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
    if "exact" in lowered and "date" in lowered:
        has_full_date = bool(
            re.search(r"\b\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b", blob)
            or re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}", blob)
        )
        if not has_full_date:
            prefix.append("The exact birth date is not available in the provided textbook.")
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
        "answer": refusal_text(language),
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

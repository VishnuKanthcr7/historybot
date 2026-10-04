"""Textbook-only grounded answer engine. Approved Class 9 textbook is the sole student source."""

from __future__ import annotations

from rag.engine.citations import supporting_evidence
from rag.engine.classify import (
    casual_reply,
    classify_answer_mode,
    classify_casual,
    classify_intent,
    extract_topics,
    last_user_question,
    strip_leading_greeting,
)
from rag.engine.evidence import (
    evidence_is_sufficient,
    evidence_matches_topic,
    expand_evidence,
    select_evidence,
)
from rag.engine.normalize import (
    looks_kannada,
    looks_like_injection,
    normalize_question,
    rewrite_for_retrieval,
    trim_history,
)
from rag.engine.validate import is_refusal, unsupported_named_items, validate_answer
from rag.llm.client import complete
from rag.llm.config import RAG_TOP_K
from rag.prompts.tutor import KANNADA_UNAVAILABLE, SYSTEM_PROMPT, refusal_text
from rag.vectorstore.retrieve import retrieve_primary, retrieve_same_pages

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
    mode = classify_answer_mode(rag_question)
    intent = classify_intent(rag_question, history)
    rewrite_history = []
    if intent == "FOLLOW_UP":
        previous = last_user_question(history)
        if previous:
            rewrite_history = [{"role": "user", "content": previous}]
    retrieval_query = rewrite_for_retrieval(rag_question, rewrite_history, force=bool(rewrite_history))

    top_k = max(RAG_TOP_K, 14) if mode == "DETAILED" else max(RAG_TOP_K, 10)
    primary_hits = retrieve_primary(retrieval_query, top_k=top_k, language="en")
    seed_keep = 5 if mode == "DETAILED" else 4
    primary_selected = select_evidence(rag_question, retrieval_query, primary_hits, max_keep=seed_keep)
    same_pages = retrieve_same_pages(
        retrieval_query,
        [
            item.get("printed_page_number") or item.get("textbook_page_number")
            for item in primary_selected
        ],
    )
    merged_hits = list(primary_hits)
    seen_ids = {item.get("chunk_id") for item in merged_hits}
    for hit in same_pages:
        if hit.get("chunk_id") not in seen_ids:
            merged_hits.append(hit)
            seen_ids.add(hit.get("chunk_id"))
    primary_selected = expand_evidence(
        rag_question,
        retrieval_query,
        primary_selected,
        merged_hits,
        max_keep=8 if mode == "DETAILED" else 6,
        page_window=2 if mode == "DETAILED" else 1,
    )

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
    payload = _ask_llm(rag_question, primary_selected, mode, strict=False)
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
        payload = _ask_llm(rag_question, primary_selected, mode, strict=True)
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
            raw = _safe_from_evidence(selected)
            reason = f"{reason}+extractive_fallback"
            sources = _sources(selected)
            answer = f"{raw}\n\n{_citation_block(sources)}"
            return {
                "answer": answer,
                "language": "en",
                "grounded": True,
                "sources": sources,
                "retrieval_query": retrieval_query,
                "retrieved": _public_hits(primary_hits),
                "selected_chunk_ids": [item["chunk_id"] for item in selected],
                "validation_reason": reason,
                "intent": intent,
                "mode": mode,
                "used_supplementary": False,
                "regeneration_count": regenerations,
                "unsupported_claims": claims,
            }
        result = _unavailable(language, retrieval_query, primary_hits, selected, intent=intent, mode=mode)
        result["validation_reason"] = reason
        result["regeneration_count"] = regenerations
        result["unsupported_claims"] = claims
        return result

    raw = _strip_invented_pages(payload["raw"])
    sources = _sources(supporting_evidence(raw, primary_selected, min_overlap=1 if mode == "DETAILED" else 2))
    answer = f"{raw}\n\n{_citation_block(sources)}"
    return {
        "answer": answer,
        "language": "en",
        "grounded": True,
        "sources": sources,
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(primary_hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": reason,
        "intent": intent,
        "mode": mode,
        "used_supplementary": False,
        "regeneration_count": regenerations,
        "unsupported_claims": [],
    }


def _looks_limited(question: str) -> bool:
    lowered = (question or "").lower()
    return any(term in lowered for term in LIMITED_TERMS)


def _ask_llm(question: str, primary: list[dict], mode: str, strict: bool) -> dict:
    primary_blocks = _blocks(primary, "TEXTBOOK")
    extra = ""
    if strict:
        extra = (
            "\nSTRICT MODE: Use only names, dates, and events that appear in the evidence. "
            "If a detail is missing from the evidence, omit it. Do not guess."
        )
    if mode == "DETAILED":
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
        max_tokens = 1000
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


def _blocks(evidence: list[dict], label: str) -> list[str]:
    blocks = []
    for item in evidence:
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        blocks.append(f"[{label}; printed_page={page}]\n{item.get('text') or ''}")
    return blocks or [f"[{label}] (none)"]


def _safe_from_evidence(evidence: list[dict]) -> str:
    lines = [
        "Here is what the Class 9 Karnataka textbook says on this topic. "
        "No extra facts are added beyond the textbook."
    ]
    seen = set()
    for item in evidence:
        text = " ".join((item.get("text") or "").split())
        if len(text) < 40:
            continue
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        snippet = text if len(text) <= 420 else text[:417].rsplit(" ", 1)[0] + "..."
        lines.append(f"• {snippet}")
    if len(lines) == 1:
        lines.append("The provided textbook does not give enough information for a fuller answer.")
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

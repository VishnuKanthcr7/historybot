"""Source-aware grounded answer engine. Primary KTBS 2026–27 first."""

from __future__ import annotations

from rag.engine.citations import supporting_evidence
from rag.engine.classify import (
    casual_reply,
    classify_answer_mode,
    classify_casual,
    classify_intent,
    last_user_question,
    strip_leading_greeting,
)
from rag.engine.evidence import evidence_is_sufficient, select_evidence
from rag.engine.normalize import (
    looks_kannada,
    looks_like_injection,
    normalize_question,
    rewrite_for_retrieval,
    trim_history,
)
from rag.engine.validate import is_refusal, split_detailed_sections, validate_answer
from rag.llm.client import complete
from rag.llm.config import RAG_TOP_K
from rag.prompts.tutor import KANNADA_SAFE_FALLBACK, SYSTEM_PROMPT, refusal_text
from rag.vectorstore.retrieve import retrieve_primary, retrieve_supplementary

LIMITED_EN = (
    "The Class 9 Karnataka State Board 2026–27 textbook has limited information on this topic."
)
LIMITED_KN = "ಈ ವಿಷಯದ ಬಗ್ಗೆ 2026–27ನೇ ತರಗತಿ 9 ಪಠ್ಯಪುಸ್ತಕದಲ್ಲಿ ಸೀಮಿತ ಮಾಹಿತಿ ಇದೆ."
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
        }

    rag_question = strip_leading_greeting(question)
    mode = classify_answer_mode(rag_question)
    intent = classify_intent(rag_question, history)
    rewrite_history = []
    if intent == "FOLLOW_UP":
        previous = last_user_question(history)
        if previous:
            rewrite_history = [{"role": "user", "content": previous}]
    kannada_input = language == "kn" or looks_kannada(rag_question)
    needs_rewrite = bool(rewrite_history) or kannada_input
    retrieval_query = rewrite_for_retrieval(rag_question, rewrite_history, force=needs_rewrite)

    primary_hits = retrieve_primary(retrieval_query, top_k=RAG_TOP_K, language=language)
    primary_selected = select_evidence(rag_question, retrieval_query, primary_hits)
    supp_hits: list[dict] = []
    supp_selected: list[dict] = []
    use_supplement = (
        mode == "DETAILED"
        and language != "kn"
        and not looks_like_injection(rag_question)
    )
    if use_supplement:
        supp_hits = retrieve_supplementary(retrieval_query, top_k=RAG_TOP_K)
        supp_selected = select_evidence(rag_question, retrieval_query, supp_hits, max_keep=3)

    if looks_like_injection(rag_question) and not evidence_is_sufficient(primary_selected):
        return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)
    if not evidence_is_sufficient(primary_selected):
        if _looks_limited(rag_question) and not use_supplement:
            return _limited(language, retrieval_query, primary_hits, primary_selected, intent, mode)
        if not (use_supplement and evidence_is_sufficient(supp_selected)):
            return _unavailable(language, retrieval_query, primary_hits, primary_selected, intent=intent, mode=mode)

    selected = list(primary_selected)
    if use_supplement:
        selected.extend(supp_selected)

    payload = _ask_llm(rag_question, language, primary_selected, supp_selected if use_supplement else [], mode, strict=False)
    ok, reason = validate_answer(
        payload["raw"],
        language,
        selected,
        grounded_expected=True,
        mode=mode if use_supplement else "NORMAL",
        primary=primary_selected,
        supplement=supp_selected if use_supplement else [],
    )
    if not ok:
        payload = _ask_llm(
            rag_question,
            language,
            primary_selected,
            supp_selected if use_supplement else [],
            mode if use_supplement else "NORMAL",
            strict=True,
        )
        ok, reason = validate_answer(
            payload["raw"],
            language,
            selected,
            grounded_expected=True,
            mode=mode if use_supplement else "NORMAL",
            primary=primary_selected,
            supplement=supp_selected if use_supplement else [],
        )
    if language == "kn" and not ok:
        return _kannada_fallback(retrieval_query, primary_hits + supp_hits, selected, intent, mode, reason)
    if not ok and use_supplement and evidence_is_sufficient(primary_selected):
        payload = _ask_llm(rag_question, language, primary_selected, [], "NORMAL", strict=True)
        selected = list(primary_selected)
        use_supplement = False
        ok, reason = validate_answer(
            payload["raw"],
            language,
            selected,
            grounded_expected=True,
            mode="NORMAL",
            primary=primary_selected,
            supplement=[],
        )
    if not ok or is_refusal(payload["raw"], language):
        if language == "kn":
            return _kannada_fallback(retrieval_query, primary_hits + supp_hits, selected, intent, mode, reason)
        result = _unavailable(language, retrieval_query, primary_hits + supp_hits, selected, intent=intent, mode=mode)
        result["validation_reason"] = reason
        return result

    raw = _strip_invented_pages(payload["raw"])
    if use_supplement and split_detailed_sections(raw):
        primary_section, extra_section = split_detailed_sections(raw)
        primary_sources = _sources(supporting_evidence(primary_section, primary_selected))
        extra_sources = _sources(supporting_evidence(extra_section, supp_selected))
        answer = _format_detailed(primary_section, extra_section, primary_sources, extra_sources)
        sources = primary_sources + extra_sources
    else:
        use_supplement = False
        sources = _sources(supporting_evidence(raw, primary_selected))
        answer = f"{raw}\n\n{_citation_block(sources)}"
    return {
        "answer": answer,
        "language": language,
        "grounded": True,
        "sources": sources,
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(primary_hits + supp_hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": reason,
        "intent": intent,
        "mode": mode,
        "used_supplementary": bool(use_supplement and supp_selected),
    }


def _looks_limited(question: str) -> bool:
    lowered = (question or "").lower()
    return any(term in lowered for term in LIMITED_TERMS)


def _ask_llm(question: str, language: str, primary: list[dict], supplement: list[dict], mode: str, strict: bool) -> dict:
    primary_blocks = _blocks(primary, "PRIMARY")
    extra = ""
    if strict:
        extra = (
            "\nSTRICT MODE: If any part of the answer is not clearly supported by the evidence, "
            "output only the required not-available sentence."
        )
    kannada_rule = ""
    if language == "kn":
        kannada_rule = (
            "\nWrite 2 to 4 short sentences in Kannada script only. "
            "Do not repeat the same phrase. Do not transliterate. "
            "If you cannot write clear Kannada from the evidence, output only the not-available Kannada sentence."
        )
    if mode == "DETAILED" and supplement:
        user = (
            f"Language: {language}\nMode: DETAILED\n"
            f"Student question: {question}\n"
            "Write two labelled sections exactly, with those headings on their own lines:\n"
            "## From your Class 9 textbook\n"
            "Write only facts from PRIMARY evidence here. Do not mention NCERT or extra books here.\n"
            "## Additional school-book detail\n"
            "Write only facts from SUPPLEMENTARY evidence here. Do not copy PRIMARY sentences here.\n"
            "Do not merge the sections. Do not omit the headings.\n"
            f"PRIMARY evidence:\n{chr(10).join(primary_blocks)}\n\n"
            f"SUPPLEMENTARY evidence:\n{chr(10).join(_blocks(supplement, 'SUPPLEMENTARY'))}\n"
            f"{extra}{kannada_rule}\n"
            "Do not add page numbers; the system will attach them."
        )
        max_tokens = 700
    else:
        user = (
            f"Language: {language}\nMode: NORMAL\n"
            f"Student question: {question}\n"
            "If this is a short factual Who/When question, start with one direct sentence.\n"
            "Use PRIMARY evidence only. Do not add extra biography from other books.\n\n"
            f"PRIMARY evidence:\n{chr(10).join(primary_blocks)}\n"
            f"{extra}{kannada_rule}\n"
            "Answer using only the evidence. Do not add page numbers; the system will attach them."
        )
        max_tokens = 450
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
        kind = item.get("source_type") or label
        blocks.append(f"[{label}; {kind}; printed_page={page}]\n{item.get('text') or ''}")
    return blocks or [f"[{label}] (none)"]


def _kannada_fallback(retrieval_query: str, hits: list[dict], selected: list[dict], intent: str | None, mode: str | None, reason: str) -> dict:
    return {
        "answer": KANNADA_SAFE_FALLBACK,
        "language": "kn",
        "grounded": False,
        "sources": [],
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": reason,
        "intent": intent,
        "mode": mode,
        "used_supplementary": False,
    }


def _format_detailed(primary_section: str, extra_section: str, primary_sources: list[dict], extra_sources: list[dict]) -> str:
    parts = [
        "## From your Class 9 textbook",
        "",
        primary_section.strip(),
        "",
        _citation_block(primary_sources),
        "",
        "## Additional school-book detail",
        "",
        extra_section.strip(),
        "",
        _citation_block(extra_sources),
    ]
    return "\n".join(parts).strip()


def _unavailable(language: str, retrieval_query: str, hits: list[dict], selected: list[dict], intent: str | None = None, mode: str | None = None) -> dict:
    return {
        "answer": refusal_text(language),
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": "insufficient_evidence",
        "intent": intent,
        "mode": mode,
        "used_supplementary": False,
    }


def _limited(language: str, retrieval_query: str, hits: list[dict], selected: list[dict], intent: str, mode: str) -> dict:
    return {
        "answer": LIMITED_KN if language == "kn" else LIMITED_EN,
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": "limited_primary_coverage",
        "intent": intent,
        "mode": mode,
        "used_supplementary": False,
    }


def _sources(selected: list[dict]) -> list[dict]:
    seen = []
    used = set()
    for item in selected:
        key = (
            item.get("chunk_id"),
            item.get("printed_page_number") or item.get("textbook_page_number"),
            item.get("source_type"),
        )
        if key in used:
            continue
        used.add(key)
        page = item.get("printed_page_number") or item.get("textbook_page_number")
        authority = item.get("authority") or "primary"
        label = item.get("citation_label") or (
            "Class 9 Karnataka State Board 2026–27 textbook"
            if authority == "primary"
            else item.get("document_name") or "Additional school-book source"
        )
        seen.append(
            {
                "textbook_page_number": page,
                "printed_page_number": page,
                "pdf_page_number": item.get("pdf_page_number"),
                "chunk_id": item.get("chunk_id"),
                "source_type": item.get("source_type"),
                "authority": authority,
                "citation_label": label,
                "document_name": item.get("document_name"),
            }
        )
    return seen


def _citation_block(sources: list[dict]) -> str:
    primary = [item for item in sources if item.get("authority") != "approved_supplementary"]
    extra = [item for item in sources if item.get("authority") == "approved_supplementary"]
    lines = []
    if primary:
        lines.append(_format_cite(primary[0]["citation_label"], primary))
    if extra:
        by_label: dict[str, list] = {}
        for item in extra:
            by_label.setdefault(item["citation_label"], []).append(item)
        for label, group in by_label.items():
            lines.append(_format_cite(label, group))
    return "\n".join(lines)


def _format_cite(label: str, sources: list[dict]) -> str:
    pages = sorted({int(item["printed_page_number"]) for item in sources if item.get("printed_page_number") is not None})
    if not pages:
        return f"Source: {label}"
    page_bit = f"page {pages[0]}" if len(pages) == 1 else "pages " + ", ".join(str(p) for p in pages)
    if "Additional" in (label or ""):
        return f"{label}, {page_bit}"
    return f"Source: {label}, {page_bit}"


def _strip_invented_pages(answer: str) -> str:
    lines = []
    for line in answer.splitlines():
        if line.strip().lower().startswith("source:"):
            continue
        if line.strip().lower().startswith("additional school-book source:"):
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

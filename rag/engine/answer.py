"""Grounded Chapter 5 answer engine. Textbook evidence only."""

from __future__ import annotations

from rag.engine.evidence import evidence_is_sufficient, select_evidence
from rag.engine.normalize import (
    looks_kannada,
    looks_like_injection,
    normalize_question,
    rewrite_for_retrieval,
    trim_history,
)
from rag.engine.validate import is_refusal, validate_answer
from rag.llm.client import complete
from rag.llm.config import MAX_REGENERATIONS, RAG_TOP_K
from rag.prompts.tutor import SYSTEM_PROMPT, refusal_text
from rag.vectorstore.retrieve import retrieve


def answer_question(
    question: str,
    language: str = "en",
    history: list[dict] | None = None,
) -> dict:
    language = "kn" if language == "kn" else "en"
    question = normalize_question(question)
    history = trim_history(history)
    needs_rewrite = bool(history) or language == "kn" or looks_kannada(question)
    retrieval_query = rewrite_for_retrieval(question, history, force=needs_rewrite)
    hits = retrieve(retrieval_query, top_k=RAG_TOP_K)
    selected = select_evidence(question, retrieval_query, hits)
    if looks_like_injection(question) and not evidence_is_sufficient(selected):
        return _unavailable(language, retrieval_query, hits, selected)
    if not evidence_is_sufficient(selected):
        return _unavailable(language, retrieval_query, hits, selected)

    payload = _ask_llm(question, language, selected, strict=False)
    ok, reason = validate_answer(payload["raw"], language, selected, grounded_expected=True)
    if not ok and MAX_REGENERATIONS >= 1:
        payload = _ask_llm(question, language, selected, strict=True)
        ok, reason = validate_answer(payload["raw"], language, selected, grounded_expected=True)
    if not ok or is_refusal(payload["raw"], language):
        result = _unavailable(language, retrieval_query, hits, selected)
        result["validation_reason"] = reason
        return result

    sources = _sources(selected)
    answer = _strip_invented_pages(payload["raw"])
    answer = f"{answer}\n\n{_citation_line(sources)}"
    return {
        "answer": answer,
        "language": language,
        "grounded": True,
        "sources": sources,
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": reason,
    }


def _ask_llm(question: str, language: str, evidence: list[dict], strict: bool) -> dict:
    blocks = []
    for item in evidence:
        blocks.append(
            f"[chunk_id={item['chunk_id']}; textbook_page={item['textbook_page_number']}; "
            f"pdf_page={item['pdf_page_number']}]\n{item.get('text') or ''}"
        )
    extra = ""
    if strict:
        extra = (
            "\nSTRICT MODE: If any part of the answer is not clearly supported by the evidence, "
            "output only the required not-available sentence."
        )
    user = (
        f"Language: {language}\n"
        f"Student question: {question}\n\n"
        f"Textbook evidence:\n{chr(10).join(blocks)}\n"
        f"{extra}\n"
        "Answer using only the evidence. Do not add page numbers; the system will attach them."
    )
    raw = complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.0 if strict else 0.1,
        max_tokens=450,
    )
    return {"raw": raw}


def _unavailable(language: str, retrieval_query: str, hits: list[dict], selected: list[dict]) -> dict:
    return {
        "answer": refusal_text(language),
        "language": language,
        "grounded": False,
        "sources": [],
        "retrieval_query": retrieval_query,
        "retrieved": _public_hits(hits),
        "selected_chunk_ids": [item["chunk_id"] for item in selected],
        "validation_reason": "insufficient_evidence",
    }


def _sources(selected: list[dict]) -> list[dict]:
    seen = []
    used = set()
    for item in selected:
        key = (
            item.get("chunk_id"),
            item.get("textbook_page_number"),
            item.get("pdf_page_number"),
        )
        if key in used:
            continue
        used.add(key)
        seen.append(
            {
                "textbook_page_number": item.get("textbook_page_number"),
                "pdf_page_number": item.get("pdf_page_number"),
                "chunk_id": item.get("chunk_id"),
            }
        )
    return seen


def _citation_line(sources: list[dict]) -> str:
    pages = sorted({int(item["textbook_page_number"]) for item in sources if item.get("textbook_page_number") is not None})
    if not pages:
        return ""
    if len(pages) == 1:
        return f"Source: Textbook page {pages[0]}"
    consecutive = pages[-1] - pages[0] == len(pages) - 1
    if consecutive:
        return f"Source: Textbook pages {pages[0]}–{pages[-1]}"
    return "Source: Textbook pages " + ", ".join(str(page) for page in pages)


def _strip_invented_pages(answer: str) -> str:
    # Engine-owned citations; drop model-added page lines.
    lines = []
    for line in answer.splitlines():
        if line.strip().lower().startswith("source:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _public_hits(hits: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": item.get("chunk_id"),
            "distance": item.get("distance"),
            "textbook_page_number": item.get("textbook_page_number"),
            "pdf_page_number": item.get("pdf_page_number"),
        }
        for item in hits
    ]

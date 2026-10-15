"""Localhost-only FastAPI wrapper around grounded answer + e-content + PDF."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

from rag.engine.answer import answer_question
from rag.engine.econtent import generate_econtent
from rag.pdf.render import render_econtent_pdf

_LOG = logging.getLogger("historybot.internal_api")


def _log_failure(endpoint: str, exc: Exception) -> None:
    # Type and short message only (no question text, no keys) so failures can be diagnosed.
    print(f"HistoryBot RAG {endpoint} failed: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr, flush=True)

app = FastAPI(title="HistoryBot internal RAG", docs_url=None, redoc_url=None, openapi_url=None)


class HistoryItem(BaseModel):
    role: str
    content: str
    task_state: dict | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    conversation_history: list[HistoryItem] = Field(default_factory=list)
    task_state: dict | None = None


class EcontentRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    language: str = "en"


class PdfRequest(BaseModel):
    title: str = ""
    language: str = "en"
    content: dict = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)


def _secret() -> str:
    return os.environ.get("INTERNAL_RAG_SECRET") or os.environ.get("RAG_INTERNAL_SECRET") or ""


def _authorize(x_internal_secret: str | None) -> None:
    expected = _secret()
    if not expected:
        raise HTTPException(status_code=503, detail="Internal RAG secret is not configured.")
    if not x_internal_secret or x_internal_secret != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _public_sources(result: dict) -> list[dict]:
    sources = []
    for item in result.get("sources") or []:
        sources.append(
            {
                "textbook_page_number": item.get("textbook_page_number") or item.get("printed_page_number"),
                "printed_page_number": item.get("printed_page_number") or item.get("textbook_page_number"),
                "pdf_page_number": item.get("pdf_page_number"),
                "chunk_id": item.get("chunk_id"),
                "citation_label": item.get("citation_label"),
                "authority": item.get("authority"),
                "source_type": item.get("source_type"),
                "document_name": item.get("document_name"),
                "chapter": item.get("chapter"),
                "excerpt": item.get("excerpt"),
            }
        )
    return sources


@app.get("/internal/health")
def health(x_internal_secret: str | None = Header(default=None)):
    _authorize(x_internal_secret)
    from rag.llm.client import describe_provider

    # Provider names only; never keys.
    return {"status": "ok", **describe_provider()}


@app.post("/internal/query")
def query(body: QueryRequest, x_internal_secret: str | None = Header(default=None)):
    _authorize(x_internal_secret)
    language = "kn" if body.language == "kn" else "en"
    history = []
    for item in body.conversation_history:
        row = {"role": item.role, "content": item.content}
        if item.task_state:
            row["task_state"] = item.task_state
        history.append(row)
    try:
        result = answer_question(
            body.question, language=language, history=history, task_state=body.task_state
        )
    except Exception as exc:
        _log_failure("query", exc)
        raise HTTPException(status_code=502, detail="RAG engine failed.")
    payload = {
        "answer": result.get("answer"),
        "language": result.get("language", language),
        "grounded": bool(result.get("grounded")),
        "used_supplementary": bool(result.get("used_supplementary")),
        "sources": _public_sources(result),
        "intent": result.get("intent"),
        "mode": result.get("mode"),
        "task": result.get("task"),
    }
    if result.get("depth"):
        payload["depth"] = result.get("depth")
    if result.get("timings"):
        payload["timings"] = result.get("timings")
    return payload


@app.post("/internal/econtent")
def econtent(body: EcontentRequest, x_internal_secret: str | None = Header(default=None)):
    _authorize(x_internal_secret)
    language = "kn" if body.language == "kn" else "en"
    try:
        result = generate_econtent(body.topic, language=language)
    except Exception as exc:
        _log_failure("econtent", exc)
        raise HTTPException(status_code=502, detail="E-content engine failed.")
    return {
        "title": result.get("title") or body.topic,
        "language": result.get("language", language),
        "grounded": bool(result.get("grounded")),
        "content": result.get("content"),
        "sources": [
            {
                "textbook_page_number": item.get("textbook_page_number") or item.get("printed_page_number"),
                "printed_page_number": item.get("printed_page_number") or item.get("textbook_page_number"),
                "citation_label": item.get("citation_label"),
                "authority": item.get("authority"),
                "source_type": item.get("source_type"),
                "chapter": item.get("chapter"),
                "excerpt": item.get("excerpt"),
            }
            for item in result.get("sources") or []
            if item.get("textbook_page_number") is not None or item.get("printed_page_number") is not None
        ],
        "message": None if result.get("grounded") else result.get("answer"),
    }


@app.post("/internal/econtent/pdf")
def econtent_pdf(body: PdfRequest, x_internal_secret: str | None = Header(default=None)):
    _authorize(x_internal_secret)
    try:
        pdf_bytes = render_econtent_pdf(
            {
                "title": body.title,
                "language": body.language,
                "content": body.content,
                "sources": body.sources,
            },
            images=body.images,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        _log_failure("pdf", exc)
        raise HTTPException(status_code=502, detail="PDF generation failed.")
    return Response(content=pdf_bytes, media_type="application/pdf")


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "RAG_ERROR", "message": exc.detail}})

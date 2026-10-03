"""Localhost-only FastAPI wrapper around Phase 6 answer_question."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

from rag.engine.answer import answer_question

app = FastAPI(title="HistoryBot internal RAG", docs_url=None, redoc_url=None, openapi_url=None)


class HistoryItem(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    conversation_history: list[HistoryItem] = Field(default_factory=list)


def _secret() -> str:
    return os.environ.get("INTERNAL_RAG_SECRET") or os.environ.get("RAG_INTERNAL_SECRET") or ""


def _authorize(x_internal_secret: str | None) -> None:
    expected = _secret()
    if not expected:
        raise HTTPException(status_code=503, detail="Internal RAG secret is not configured.")
    if not x_internal_secret or x_internal_secret != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


@app.get("/internal/health")
def health(x_internal_secret: str | None = Header(default=None)):
    _authorize(x_internal_secret)
    return {"status": "ok"}


@app.post("/internal/query")
def query(body: QueryRequest, x_internal_secret: str | None = Header(default=None)):
    _authorize(x_internal_secret)
    language = "kn" if body.language == "kn" else "en"
    history = [{"role": item.role, "content": item.content} for item in body.conversation_history]
    try:
        result = answer_question(body.question, language=language, history=history)
    except Exception:
        raise HTTPException(status_code=502, detail="RAG engine failed.")
    sources = []
    for item in result.get("sources") or []:
        sources.append(
            {
                "textbook_page_number": item.get("textbook_page_number"),
                "pdf_page_number": item.get("pdf_page_number"),
                "chunk_id": item.get("chunk_id"),
            }
        )
    return {
        "answer": result.get("answer"),
        "language": result.get("language", language),
        "grounded": bool(result.get("grounded")),
        "sources": sources,
    }


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "RAG_ERROR", "message": exc.detail}})

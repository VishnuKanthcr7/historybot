"""Question cleanup and follow-up rewrite for retrieval."""

from __future__ import annotations

import re

from rag.llm.client import complete
from rag.llm.config import MAX_HISTORY_TURNS, MAX_MESSAGE_CHARS
from rag.prompts.tutor import REWRITE_PROMPT

INJECTION_PATTERNS = (
    r"ignore (the )?(previous|textbook|instructions)",
    r"forget (the )?(previous|textbook|instructions)",
    r"use wikipedia",
    r"from your (own )?knowledge",
    r"even if it isn'?t in the textbook",
    r"outside the textbook",
    r"system prompt",
    r"reveal (your )?(system )?prompt",
    r"api key",
    r"show me your (api|secret|prompt)",
    r"visionias",
    r"use vision ias",
    r"ignore your source rules",
)


def normalize_question(question: str) -> str:
    text = (question or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_MESSAGE_CHARS]


def looks_like_injection(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in INJECTION_PATTERNS)


def looks_kannada(text: str) -> bool:
    return bool(re.search(r"[\u0C80-\u0CFF]", text or ""))


def trim_history(history: list[dict] | None) -> list[dict]:
    if not history:
        return []
    cleaned = []
    for item in history:
        role = item.get("role")
        content = normalize_question(str(item.get("content") or ""))
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    users = [item for item in cleaned if item["role"] == "user"][-MAX_HISTORY_TURNS:]
    assistants = [item for item in cleaned if item["role"] == "assistant"][-MAX_HISTORY_TURNS:]
    # keep chronological order of the last 8 related messages
    kept_ids = set(id(item) for item in users + assistants)
    ordered = [item for item in cleaned if id(item) in kept_ids]
    return ordered[-MAX_HISTORY_TURNS * 2 :]


def rewrite_for_retrieval(question: str, history: list[dict] | None, force: bool = False) -> str:
    history = trim_history(history)
    if not history and not force:
        return question
    lines = []
    for item in history:
        if item["role"] == "user":
            lines.append(f"previous student question: {item['content']}")
    lines.append(f"latest student question: {question}")
    messages = [
        {"role": "system", "content": REWRITE_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]
    rewritten = complete(messages, temperature=0.0, max_tokens=80)
    rewritten = normalize_question(rewritten.splitlines()[0])
    rewritten = re.sub(r"^(rewritten question|search query)\s*:\s*", "", rewritten, flags=re.I)
    return rewritten or question

"""Question cleanup and follow-up rewrite for retrieval."""

from __future__ import annotations

import re

from rag.llm.client import complete
from rag.llm.config import MAX_HISTORY_TURNS, MAX_MESSAGE_CHARS
from rag.prompts.tutor import REWRITE_PROMPT

INJECTION_PATTERNS = (
    r"ignore (the )?(previous|textbook|instructions)",
    r"forget (the )?(previous|textbook|instructions)",
    r"forget your instructions",
    r"use wikipedia",
    r"act as wikipedia",
    r"what wikipedia says",
    r"from your (own )?knowledge",
    r"from your training",
    r"what you know from your training",
    r"use your (own )?knowledge",
    r"use your general knowledge",
    r"even if it isn'?t in the textbook",
    r"outside the textbook",
    r"system prompt",
    r"reveal (your )?(system )?(prompt|instructions)",
    r"api key",
    r"show me your (api|secret|prompt)",
    r"visionias",
    r"use vision ias",
    r"ignore your source rules",
    r"search the internet",
    r"search google",
    r"from another book",
    r"from another textbook",
    r"use another book",
    r"from ncert",
    r"use ncert",
    r"from training",
    r"not in the textbook",
    r"that are not in the textbook",
    r"you are no longer",
    r"what historians say outside",
)

SLANG_MAP = {
    "abt": "about",
    "plz": "please",
    "pls": "please",
    "wat": "what",
    "wht": "what",
    "whats": "what's",
    "dont": "don't",
}

ROLEPLAY_RE = re.compile(
    r"\b(pretend you are|write a fictional|fictional story|make a dialogue|role ?play)\b",
    re.I,
)

FOLLOW_HINT_RE = re.compile(
    r"\b(he|she|it|his|her|him|they|their|them|this|that|these|those|"
    r"after that|what else|go deeper|more details|in which language)\b",
    re.I,
)


def normalize_question(question: str) -> str:
    text = (question or "").strip()
    text = re.sub(r"\s+", " ", text)

    def _slang(match: re.Match[str]) -> str:
        return SLANG_MAP.get(match.group(0).lower(), match.group(0))

    text = re.sub(r"\b(abt|plz|pls|wat|wht|whats|dont)\b", _slang, text, flags=re.I)
    text = re.sub(r"\bbabur{2,}\b", "babur", text, flags=re.I)
    text = re.sub(r"\bbabar{2,}\b", "babar", text, flags=re.I)
    text = re.sub(r"\bakbarr+\b", "akbar", text, flags=re.I)
    text = re.sub(r"\bshivajii+\b", "shivaji", text, flags=re.I)
    text = re.sub(r"\baurangzebb+\b", "aurangzeb", text, flags=re.I)
    text = re.sub(r"\btaj[\s-]?mahal\b", "taj mahal", text, flags=re.I)
    return text[:MAX_MESSAGE_CHARS]


def looks_like_injection(question: str) -> bool:
    lowered = (question or "").lower()
    return any(re.search(pattern, lowered) for pattern in INJECTION_PATTERNS)


def looks_like_roleplay(question: str) -> bool:
    return bool(ROLEPLAY_RE.search(question or ""))


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


def heuristic_followup_query(question: str, previous: str) -> str | None:
    """Insert the previous named topic when the new question uses pronouns or follow-up hints."""
    from rag.engine.classify import TOPIC_ALIASES, extract_topics

    if not previous:
        return None
    previous_topics = extract_topics(previous)
    if not previous_topics:
        return None
    current_topics = extract_topics(question)
    uses_hint = bool(FOLLOW_HINT_RE.search(question or ""))
    if current_topics and not uses_hint:
        return None
    labels = [TOPIC_ALIASES[key][0] for key in previous_topics if key in TOPIC_ALIASES]
    if not labels:
        return None
    return f"{' '.join(labels)} {question}"


def rewrite_for_retrieval(question: str, history: list[dict] | None, force: bool = False) -> str:
    history = trim_history(history)
    previous = ""
    for item in reversed(history):
        if item["role"] == "user":
            previous = item["content"]
            break
    heuristic = heuristic_followup_query(question, previous)
    if heuristic:
        return heuristic
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

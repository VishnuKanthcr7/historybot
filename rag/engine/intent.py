"""Student intent helpers. Routing only — no extra historical facts."""

from __future__ import annotations

import re

from rag.engine.classify import (
    EXAM_RE,
    TOPIC_ALIASES,
    _folded,
    extract_topics,
    last_user_question,
)

CONVERSATIONAL_LEAD = re.compile(
    r"^\s*((bro|dude|sir|pls|plz|please|hey|hi|hello)\s*[,!]?\s+)+",
    re.I,
)
CAN_YOU_LEAD = re.compile(
    r"^\s*(can you|could you|would you please|would you|please)\s+",
    re.I,
)
WANT_LEAD = re.compile(
    r"^\s*(i want to know(?: about)?|i want to learn(?: about)?|i wanna know(?: about)?|"
    r"i would like to know(?: about)?)\s+",
    re.I,
)
ABOUT_RE = re.compile(
    r"\b(tell me about|tell me everything about|i want to know about|"
    r"teach me about|learn about)\b",
    re.I,
)
BROAD_PHRASE_RE = re.compile(
    r"\b(everything about|in detail|full explanation|teach me|i want to learn|"
    r"all about|the whole|complete (explanation|overview))\b",
    re.I,
)
EASY_ENGLISH_RE = re.compile(
    r"\b(easy english|simple english|easy language|simple words|simple language|"
    r"explain simply|like i'?m a (class 9 )?student|in easy english)\b",
    re.I,
)
MORE_TASK_RE = re.compile(
    r"^(more|continue|go on|next|another one|anything else|tell me more|"
    r"give me more|more details|go deeper|more questions|more mcqs|"
    r"more questions like these|another 10|another ten|give me more questions|"
    r"next 10|next ten|give me another set|another set)\??$",
    re.I,
)
MCQ_REQUEST_RE = re.compile(
    r"\b(mcqs?|multiple choice|multiple-choice)\b",
    re.I,
)
COUNT_RE = re.compile(
    r"\b(\d+|ten|five|twenty|twelve|eight|six)\s+(?:practice\s+)?(?:mcqs?|multiple choice questions|questions)\b|"
    r"\b(?:another|next)\s+(\d+|ten|five|twenty)\b",
    re.I,
)
WORD_COUNTS = {
    "five": 5,
    "six": 6,
    "eight": 8,
    "ten": 10,
    "twelve": 12,
    "twenty": 20,
}


def strip_conversational_padding(question: str) -> str:
    text = (question or "").strip()
    text = CONVERSATIONAL_LEAD.sub("", text)
    text = CAN_YOU_LEAD.sub("", text)
    text = WANT_LEAD.sub("", text)
    return text.strip(" ,.?!") or (question or "").strip()


def wants_easy_english(question: str) -> bool:
    return bool(EASY_ENGLISH_RE.search(question or ""))


def is_more_followup(question: str) -> bool:
    return bool(MORE_TASK_RE.match(_folded(question or "")))


# A follow-up that revises the question set already on screen ("make the questions
# harder", "strictly from the textbook") without naming a new topic.
QUESTION_SET_RE = re.compile(
    r"\b(?:the|these|those)\s+(?:questions|mcqs|quiz)\b",
    re.I,
)
QUESTION_DIFFICULTY_RE = re.compile(
    r"\b(?:difficult|harder|tougher|easier|simpler|stricter|strictly|textbook)\b",
    re.I,
)


def revises_current_questions(question: str) -> bool:
    text = question or ""
    if extract_topics(text):
        return False
    return bool(QUESTION_SET_RE.search(text) and QUESTION_DIFFICULTY_RE.search(text))


def last_mcq_request(history: list[dict] | None) -> str:
    """Latest earlier request that actually asked for multiple-choice questions."""
    found = ""
    for item in history or []:
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "")
        if looks_like_mcq_request(content):
            found = content
    return found


def looks_like_mcq_request(question: str) -> bool:
    text = question or ""
    if MCQ_REQUEST_RE.search(text):
        return True
    return bool(EXAM_RE.search(text) and re.search(r"\b(quiz|test me|mcq|multiple choice)\b", text, re.I))


def looks_like_mcq_answer(answer: str) -> bool:
    text = answer or ""
    return bool(re.search(r"\nA\.\s+.+\nB\.\s+", text) and re.search(r"\bAnswer:\s*[A-D]\b", text, re.I))


def requested_item_count(question: str, default: int = 10) -> int:
    match = COUNT_RE.search(question or "")
    if not match:
        if re.search(r"\bten\b", question or "", re.I) and looks_like_mcq_request(question or ""):
            return 10
        return default
    raw = (match.group(1) or match.group(2) or "").lower()
    if raw.isdigit():
        value = int(raw)
    else:
        value = WORD_COUNTS.get(raw, default)
    return max(3, min(value, 20))


def previous_assistant(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") == "assistant":
            return str(item.get("content") or "")
    return ""


def collect_task_state(history: list[dict] | None, incoming: dict | None = None) -> dict:
    last = dict(incoming or {})
    fingerprints: list[str] = list(last.get("fingerprints") or [])
    for item in history or []:
        payload = item.get("task_state") or {}
        if not isinstance(payload, dict):
            continue
        for key in ("type", "topic", "entity", "count", "generation_index", "depth"):
            if payload.get(key) not in (None, "", []):
                last[key] = payload[key]
        fingerprints.extend(payload.get("fingerprints") or [])
        for cid in payload.get("used_chunk_ids") or payload.get("ids") or []:
            if cid:
                last.setdefault("used_chunk_ids", [])
                if cid not in last["used_chunk_ids"]:
                    last["used_chunk_ids"].append(cid)
    seen: set[str] = set()
    unique: list[str] = []
    for item in fingerprints:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    last["fingerprints"] = unique
    if "used_chunk_ids" in last:
        seen_ids: set[str] = set()
        ids: list[str] = []
        for item in last["used_chunk_ids"]:
            if item and item not in seen_ids:
                seen_ids.add(item)
                ids.append(item)
        last["used_chunk_ids"] = ids
    return last


def infer_previous_task(history: list[dict] | None, task_state: dict | None = None) -> str | None:
    collected = collect_task_state(history, task_state)
    if collected.get("type") in {"MCQ", "EXPLAIN"}:
        return collected["type"]
    previous = last_user_question(history)
    assistant = previous_assistant(history)
    if looks_like_mcq_request(previous) or looks_like_mcq_answer(assistant):
        return "MCQ"
    if extract_topics(previous) or collected.get("entity") or collected.get("topic"):
        return "EXPLAIN"
    return None


def entity_focus_query(entity: str | None, topics: set[str], question_type: str) -> str | None:
    from rag.engine.topic_map import RULER_KEYS

    rulers = [key for key in RULER_KEYS if key in topics]
    if len(rulers) >= 2:
        names = [TOPIC_ALIASES[key][0] for key in rulers if TOPIC_ALIASES.get(key)]
        if len(names) >= 2:
            return " ".join(names)
    if question_type == "BROAD_TOPIC" and "mughal" in topics and not (topics & {"shivaji", "maratha"}):
        return "Mughal Babur Humayun Akbar Shah Jahan Aurangzeb"
    if question_type == "BROAD_TOPIC" and (topics & {"maratha", "shivaji"}) and "akbar" not in topics:
        return "Maratha Shivaji Peshwa"
    if question_type == "BROAD_TOPIC" and "ahom" in topics:
        return "Ahom Dynasty Lachit Saraighat"
    if entity and entity in TOPIC_ALIASES:
        return TOPIC_ALIASES[entity][0]
    return None


def is_broad_dynasty_request(question: str, topics: set[str]) -> bool:
    dynasty_only = bool(re.search(r"\b(mughals?|marathas?|ahoms?)\b", question or "", re.I)) and not (
        topics & {"babar", "akbar", "shivaji", "shahjahan", "aurangzeb", "bajirao", "humayun", "madhav", "nizam", "sher"}
    )
    if not dynasty_only:
        return False
    return bool(BROAD_PHRASE_RE.search(question or "") or ABOUT_RE.search(question or ""))

"""Conservative question intent for retrieval. Heuristic only; no extra facts."""

from __future__ import annotations

import re

TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "babar": ("babar", "babur"),
    "humayun": ("humayun",),
    "akbar": ("akbar", "ಅಕ್ಬರ"),
    "jahangir": ("jahangir", "jehangir"),
    "shahjahan": ("shahjahan", "shah jahan", "sahajahan", "shahajahan"),
    "aurangzeb": ("aurangzeb", "aurangjeb"),
    "shivaji": ("shivaji", "ಶಿವಾಜಿ"),
    "sambhaji": ("sambhaji",),
    "peshwa": ("peshwa",),
    "bajirao": ("baji rao", "bajirao"),
    "balaji": ("balaji vishwanath",),
    "madhav": ("madhav rao",),
    "panipat": ("panipat",),
    "taj": ("taj mahal", "tajmahal", "ತಾಜ್ ಮಹಲ್", "ತಾಜ್"),
    "guerilla": ("guerilla", "guerrilla", "ಗೆರಿಲ್ಲಾ"),
    "din": ("din-e-ilahi", "din e ilahi", "dine ilahi", "din-i-ilahi", "ದೀನ್-ಇ-ಇಲಾಹಿ", "ದೀನ್"),
    "maratha": ("maratha", "ಮರಾಠ"),
    "raigad": ("raigad", "raigadh"),
    "plassey": ("plassey",),
}

STANDALONE_START = re.compile(
    r"^(what|who|where|when|why|how|tell|explain|describe|list)\b",
    re.I,
)
PRONOUN_RE = re.compile(
    r"\b(he|she|it|his|her|him|they|their|them|this|that|these|those)\b",
    re.I,
)


def extract_topics(text: str) -> set[str]:
    blob = text or ""
    lowered = blob.lower()
    found = set()
    for key, aliases in TOPIC_ALIASES.items():
        for alias in aliases:
            if alias.isascii():
                if alias in lowered:
                    found.add(key)
                    break
            elif alias in blob:
                found.add(key)
                break
    return found


def last_user_question(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def classify_intent(question: str, history: list[dict] | None) -> str:
    """Return FOLLOW_UP, NEW_TOPIC, or STANDALONE."""
    if not history:
        return "STANDALONE"
    previous = last_user_question(history)
    current_topics = extract_topics(question)
    previous_topics = extract_topics(previous)
    has_pronoun = bool(PRONOUN_RE.search(question or ""))

    if current_topics and previous_topics and current_topics.isdisjoint(previous_topics):
        return "NEW_TOPIC"
    if has_pronoun and (not current_topics or current_topics & previous_topics):
        return "FOLLOW_UP"
    if current_topics and previous_topics and current_topics <= previous_topics:
        return "FOLLOW_UP"
    if current_topics and not previous_topics:
        return "STANDALONE"
    if not current_topics and has_pronoun:
        return "FOLLOW_UP"
    if not current_topics and previous_topics:
        if STANDALONE_START.match((question or "").strip()) and not has_pronoun:
            return "NEW_TOPIC"
        if len((question or "").split()) <= 10:
            return "FOLLOW_UP"
    return "STANDALONE"

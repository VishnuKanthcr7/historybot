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
    "mughal": ("mughal", "moghul", "ಮೊಘಲ"),
    "raigad": ("raigad", "raigadh"),
    "plassey": ("plassey",),
    "ahom": ("ahom", "sukaphaa", "lachit", "saraighat", "charaideo"),
    "sher": ("sher shah", "farid khan", "sadak-e-azam"),
    "mansab": ("mansab", "mansabdari", "zat ranking"),
}

STANDALONE_START = re.compile(
    r"^(what|who|where|when|why|how|tell|explain|describe|list)\b",
    re.I,
)
PRONOUN_RE = re.compile(
    r"\b(he|she|it|his|her|him|they|their|them|this|that|these|those)\b",
    re.I,
)

GREETING_PHRASES = (
    "hi",
    "hello",
    "hey",
    "hey there",
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "namaste",
    "namaskar",
    "hi there",
    "hello there",
    "ನಮಸ್ಕಾರ",
    "ಹಾಯ್",
    "ಹಲೋ",
)
THANKS_PHRASES = (
    "thanks",
    "thank you",
    "thank you so much",
    "thanks a lot",
    "thx",
    "ty",
    "ಧನ್ಯವಾದ",
    "ಧನ್ಯವಾದಗಳು",
)
CLARIFY_PHRASES = (
    "ok",
    "okay",
    "k",
    "hmm",
    "hmmm",
    "yes",
    "no",
    "yeah",
    "yep",
    "?",
    ".",
    "...",
    "??",
)
LEADING_GREETING = re.compile(
    r"^\s*(hi|hello|hey|namaste|namaskar|ನಮಸ್ಕಾರ|ಹಾಯ್|ಹಲೋ)\s*[,!.]?\s+",
    re.I,
)


def _folded(text: str) -> str:
    return re.sub(r"[!?.،,]+$", "", (text or "").strip()).strip().lower()


def strip_leading_greeting(question: str) -> str:
    cleaned = LEADING_GREETING.sub("", question or "", count=1).strip()
    return cleaned or (question or "").strip()


def classify_casual(question: str) -> str | None:
    """Return GREETING, THANKS, CLARIFY, or None (run RAG). Never uses Chroma."""
    raw = (question or "").strip()
    if not raw:
        return "CLARIFY"
    if LEADING_GREETING.match(raw) and strip_leading_greeting(raw) != raw:
        remainder = strip_leading_greeting(raw)
        if remainder and remainder.lower() not in GREETING_PHRASES + THANKS_PHRASES + CLARIFY_PHRASES:
            return None
    folded = _folded(raw)
    if folded in GREETING_PHRASES:
        return "GREETING"
    if folded in THANKS_PHRASES:
        return "THANKS"
    if folded in CLARIFY_PHRASES:
        return "CLARIFY"
    if len(folded) <= 2 and not re.search(r"[A-Za-z\u0C80-\u0CFF]{3,}", raw):
        return "CLARIFY"
    return None


def casual_reply(kind: str, language: str) -> str:
    kn = language == "kn"
    if kind == "GREETING":
        if kn:
            return "ನಮಸ್ಕಾರ! ನಿಮ್ಮ ಇತಿಹಾಸ ಪಠ್ಯಪುಸ್ತಕದಿಂದ ಏನು ಕಲಿಯಲು ಬಯಸುತ್ತೀರಿ?"
        return "Hello! What would you like to learn from your History textbook?"
    if kind == "THANKS":
        if kn:
            return "ಸ್ವಾಗತ. ಇನ್ನೊಂದು ಪ್ರಶ್ನೆ ಕೇಳಬಹುದು."
        return "You're welcome. Ask another question from your History textbook when you're ready."
    if kn:
        return "ದಯವಿಟ್ಟು ಇತಿಹಾಸ ಪಠ್ಯಪುಸ್ತಕದ ಬಗ್ಗೆ ಪ್ರಶ್ನೆ ಕೇಳಿ."
    return "Please ask a question about the History textbook."


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


DETAILED_RE = re.compile(
    r"\b(tell me more|more detail|more details|in detail|explain fully|"
    r"detailed explanation|everything about|more information|"
    r"i want more|explain this topic in detail|give me more|"
    r"tell me about)\b",
    re.I,
)
EXPLAIN_RE = re.compile(r"\b(explain|describe)\b", re.I)
SHORT_FACT_RE = re.compile(r"^\s*(who|what|when|where)\b", re.I)
ECONTENT_RE = re.compile(
    r"\b(learning module|e-?content|make a module|create a (learning )?module)\b",
    re.I,
)
KANNADA_DETAIL_RE = re.compile(r"ವಿವರ|ಹೆಚ್ಚಿನ ಮಾಹಿತಿ")


def classify_answer_mode(question: str) -> str:
    """Return ECONTENT, DETAILED, or NORMAL. Casual is handled separately."""
    text = question or ""
    if ECONTENT_RE.search(text):
        return "ECONTENT"
    if DETAILED_RE.search(text) or KANNADA_DETAIL_RE.search(text):
        return "DETAILED"
    if EXPLAIN_RE.search(text) and not (SHORT_FACT_RE.match(text) and len(text.split()) <= 10):
        return "DETAILED"
    return "NORMAL"

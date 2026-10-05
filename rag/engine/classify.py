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
    "ashapradhan": ("ashapradhan", "ashtapradhan", "asha pradhan", "ashta pradhan", "ashapradhans"),
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
BYE_PHRASES = (
    "bye",
    "goodbye",
    "good bye",
    "see you",
    "see ya",
    "cya",
    "take care",
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
        if remainder and remainder.lower() not in GREETING_PHRASES + THANKS_PHRASES + CLARIFY_PHRASES + BYE_PHRASES:
            return None
    folded = _folded(raw)
    if folded in GREETING_PHRASES:
        return "GREETING"
    if folded in THANKS_PHRASES:
        return "THANKS"
    if folded in BYE_PHRASES:
        return "BYE"
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
    if kind == "BYE":
        if kn:
            return "ವಿದಾಯ. ಪಠ್ಯಪುಸ್ತಕದಿಂದ ಮತ್ತೆ ಕಲಿಯಲು ಬನ್ನಿ."
        return "Goodbye. Come back whenever you want to study from your History textbook."
    if kn:
        return "ದಯವಿಟ್ಟು ಇತಿಹಾಸ ಪಠ್ಯಪುಸ್ತಕದ ಬಗ್ಗೆ ಪ್ರಶ್ನೆ ಕೇಳಿ."
    return "Please ask a question about the History textbook."


def extract_topics(text: str) -> set[str]:
    blob = text or ""
    lowered = blob.lower()
    collapsed = re.sub(r"(.)\1{2,}", r"\1", lowered)
    found = set()
    for key, aliases in TOPIC_ALIASES.items():
        for alias in aliases:
            haystacks = (lowered, collapsed) if alias.isascii() else (blob,)
            for haystack in haystacks:
                if alias in haystack:
                    found.add(key)
                    break
            else:
                continue
            break
    return found


def last_user_question(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


FOLLOW_SHORT_RE = re.compile(
    r"^(tell me more|explain more|give me more( details)?|what else|continue|"
    r"go deeper|more|why|how|and then|what happened after that|what did he do after that|why is he important|why (was|is) (he|she|it) important|"
    r"more questions|more mcqs|go on|next|another one|anything else|"
    r"another 10|another ten|give me more questions|"
    r"next 10|next ten|give me another set|another set)\??$",
    re.I,
)
OFF_DOMAIN_RE = re.compile(
    r"\b(python|ronaldo|cristiano|joke|jokes|weather|prime minister|world cup|"
    r"world war|ncert|wikipedia|chatgpt|openai)\b|capital of karnataka",
    re.I,
)


def classify_intent(question: str, history: list[dict] | None) -> str:
    """Return FOLLOW_UP, NEW_TOPIC, or STANDALONE."""
    if not history:
        return "STANDALONE"
    previous = last_user_question(history)
    current_topics = extract_topics(question)
    previous_topics = extract_topics(previous)
    has_pronoun = bool(PRONOUN_RE.search(question or ""))
    folded = _folded(question or "")
    off_domain = bool(OFF_DOMAIN_RE.search(question or ""))

    if current_topics and previous_topics and current_topics.isdisjoint(previous_topics):
        return "NEW_TOPIC"
    if off_domain and not current_topics:
        return "STANDALONE"
    if has_pronoun and (not current_topics or current_topics & previous_topics):
        return "FOLLOW_UP"
    if current_topics and previous_topics and current_topics <= previous_topics:
        return "FOLLOW_UP"
    if current_topics and not previous_topics:
        return "STANDALONE"
    if not current_topics and previous_topics:
        if FOLLOW_SHORT_RE.match(folded) or has_pronoun:
            return "FOLLOW_UP"
        if STANDALONE_START.match((question or "").strip()) and not has_pronoun and len((question or "").split()) > 8:
            return "NEW_TOPIC"
        if len((question or "").split()) <= 10:
            return "FOLLOW_UP"
    return "STANDALONE"


DETAILED_RE = re.compile(
    r"\b(tell me more|more detail|more details|in detail|explain fully|"
    r"detailed explanation|everything about|more information|"
    r"i want more|explain this topic in detail|give me more|"
    r"tell me about|go deeper|what else|continue|"
    r"summarize|summary|revision|important points|quick revision|"
    r"teach me|i want to learn|full explanation|all about)\b",
    re.I,
)
EXPLAIN_RE = re.compile(r"\b(explain|describe)\b", re.I)
SHORT_FACT_RE = re.compile(r"^\s*(who|what|when|where)\b", re.I)
ECONTENT_RE = re.compile(
    r"\b(learning module|e-?content|make a module|create a (learning )?module)\b",
    re.I,
)
KANNADA_DETAIL_RE = re.compile(r"ವಿವರ|ಹೆಚ್ಚಿನ ಮಾಹಿತಿ")
DYNASTY_RE = re.compile(r"\b(mughals?|marathas?|ahoms?)\b", re.I)
EXAM_RE = re.compile(
    r"\b(quiz( me)?|test me|mcqs?|multiple choice|short questions|5-mark|"
    r"ten questions|10 questions|give( me)? (\d+ )?questions|practice questions)\b",
    re.I,
)
SUMMARY_RE = re.compile(
    r"\b(summarize|summary|revision|important points|one-page|"
    r"quick revision|what should i remember|main things|"
    r"explain simply|like i'?m a class 9|i don't understand)\b",
    re.I,
)


def classify_answer_mode(question: str) -> str:
    """Return ECONTENT, DETAILED, or NORMAL. Casual is handled separately."""
    text = question or ""
    if ECONTENT_RE.search(text):
        return "ECONTENT"
    if DETAILED_RE.search(text) or KANNADA_DETAIL_RE.search(text) or SUMMARY_RE.search(text) or EXAM_RE.search(text):
        return "DETAILED"
    if EXPLAIN_RE.search(text) and not (SHORT_FACT_RE.match(text) and len(text.split()) <= 10):
        return "DETAILED"
    return "NORMAL"


def classify_question_type(question: str, intent: str | None = None) -> str:
    """Return DIRECT, EXPLANATION, BROAD_TOPIC, FOLLOW_UP, or EXAM."""
    if intent == "FOLLOW_UP":
        return "FOLLOW_UP"
    text = question or ""
    lowered = text.lower()
    topics = extract_topics(text)
    has_admin = "administration" in lowered or "administrative" in lowered
    dynasty_only = bool(DYNASTY_RE.search(text)) and not (
        topics & {"babar", "akbar", "shivaji", "shahjahan", "aurangzeb", "bajirao", "humayun"}
    )
    if EXAM_RE.search(text):
        return "EXAM"
    if "in detail" in lowered and dynasty_only:
        return "BROAD_TOPIC"
    if re.search(
        r"\b(tell me (more |everything )?about|teach me|i want to learn about|"
        r"full explanation of|all about) the (mughals|marathas|ahoms)\b",
        lowered,
    ):
        return "BROAD_TOPIC"
    if dynasty_only and re.search(
        r"\b(everything about|full explanation|teach me|i want to learn|all about|in detail)\b",
        lowered,
    ):
        return "BROAD_TOPIC"
    if SUMMARY_RE.search(text) and dynasty_only:
        return "BROAD_TOPIC"
    if SUMMARY_RE.search(text):
        return "EXPLANATION"
    if has_admin or (EXPLAIN_RE.search(text) and ("policy" in lowered or "expansion" in lowered)):
        return "EXPLANATION"
    if EXPLAIN_RE.search(text) and dynasty_only:
        return "BROAD_TOPIC"
    if DETAILED_RE.search(text) and dynasty_only:
        return "BROAD_TOPIC"
    if re.search(r"\b(tell me about|i want to know about|teach me about)\b", lowered) and topics:
        return "EXPLANATION"
    if DETAILED_RE.search(text) or (EXPLAIN_RE.search(text) and not SHORT_FACT_RE.match(text)):
        if dynasty_only:
            return "BROAD_TOPIC"
        if EXPLAIN_RE.search(text) or "tell me more" in lowered:
            person = topics & {
                "babar",
                "akbar",
                "shivaji",
                "shahjahan",
                "aurangzeb",
                "bajirao",
                "humayun",
                "madhav",
                "sher",
            }
            return "EXPLANATION" if has_admin or EXPLAIN_RE.search(text) or person else "BROAD_TOPIC"
    if EXPLAIN_RE.search(text):
        return "EXPLANATION"
    return "DIRECT"

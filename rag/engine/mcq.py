"""Textbook-grounded Class 9 MCQs with short options and fingerprints."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass

from rag.engine.coverage import GROUP_TITLE, build_coverage_plan, filter_plan

LETTERS = "ABCD"
SKIP = (
    "do you know",
    "mughals in india",
    "seven wonders",
    "fill in the blanks",
    "exercises",
    "project work",
)
YEAR_RE = re.compile(r"\b(1[2-9]\d{2})\b")
LANG_RE = re.compile(r"\b(Persian|Turkish|Arabic|Sanskrit|Hindi|Marathi|Kannada|Urdu)\b", re.I)
BORN_RE = re.compile(r"born in ([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)")


@dataclass
class McqFact:
    question: str
    answer: str
    kind: str
    pages: list
    title: str
    group_key: str


def fingerprint(question: str, answer: str = "") -> str:
    blob = re.sub(r"[^a-z0-9]+", "", f"{question} {answer}".lower())
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def fingerprints_from_answer(answer: str) -> list[str]:
    found = []
    blocks = re.split(r"\n(?=\d+\.\s)", answer or "")
    for block in blocks:
        match = re.match(r"\d+\.\s+(.+?)(?:\nA\.|\Z)", block.strip(), re.S)
        if not match:
            continue
        stem = match.group(1).strip()
        ans = re.search(r"Answer:\s*([A-D])", block, re.I)
        opt = {}
        for letter, text in re.findall(r"^([A-D])\.\s+(.+)$", block, re.M):
            opt[letter] = text.strip()
        correct = opt.get((ans.group(1) if ans else "").upper(), "")
        found.append(fingerprint(stem, correct))
    return found


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _usable(text: str) -> bool:
    return len((text or "").split()) >= 12


def _group_text(group) -> str:
    raw = _clean(" ".join(item.get("text") or "" for item in group.chunks))
    key = (getattr(group, "key", None) or "").split(":", 1)[0]
    person_keys = {
        "babar",
        "akbar",
        "shivaji",
        "shahjahan",
        "aurangzeb",
        "bajirao",
        "humayun",
        "sambhaji",
        "sher",
        "jahangir",
        "madhav",
        "balaji",
    }
    if key not in person_keys:
        return raw
    try:
        from rag.engine.entity import _is_posthumous_bleed, _looks_corrupt_sentence, _mentions, split_entity_segments
        from rag.engine.pack import dominant_ruler
    except Exception:
        return raw
    kept: list[str] = []
    for segment in split_entity_segments(raw):
        for sent in re.split(r"(?<=[.!?])\s+", segment):
            clean = _clean(sent)
            if len(clean.split()) < 5:
                continue
            if _looks_corrupt_sentence(clean):
                continue
            if _is_posthumous_bleed(clean, key):
                continue
            # Keep entity-mentioning sentences; drop other-ruler-dominated asides.
            if _mentions(clean, key) <= 0:
                other = dominant_ruler(clean)
                if other and other != key:
                    continue
            kept.append(clean)
    return _clean(" ".join(kept)) if kept else raw


def _short(value: str, limit: int = 42) -> str:
    value = _clean(value).strip(" ,.;:")
    if len(value) > limit:
        return ""
    return value



VACUOUS_STEMS = (
    "who is the main person in the textbook account",
    "which place is mentioned in the textbook section",
    "which year is mentioned in the textbook section",
    "which language is mentioned with",
    "which language is associated with",
    "city of monuments",
    "which place is linked with",
    "which place is mentioned in connection with",
    "of this kind",
)

AWKWARD_ANSWER = {
    "fame of the marathas",
    "glory of the maratha empire",
    "this",
    "that",
    "these",
    "those",
    "king",
    "emperor",
    "ruler",
}


def _is_vacuous_question(question: str) -> bool:
    low = (question or "").lower().strip()
    return any(stem in low for stem in VACUOUS_STEMS)


def _stem_signature(question: str) -> str:
    """Collapse near-duplicate stems (same fact asked two ways)."""
    low = re.sub(r"[^a-z0-9]+", " ", (question or "").lower())
    low = re.sub(r"\b(according to the textbook|in the textbook|of this kind)\b", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if "language" in low or ("turkish" in low and "autobiography" in low):
        if "babur" in low or "babar" in low or "autobiography" in low:
            return "lang-babur-auto"
        if "akbar" in low or "translated" in low or "hindu religious" in low:
            return "lang-akbar"
        if "shivaji" in low or "administration" in low or "marathi" in low:
            return "lang-admin"
        return "language-stem"
    if "taj mahal" in low and ("memory" in low or ("built" in low and "who" in low)):
        return "taj-builder-or-memory"
    if "rohtas" in low or ("forts" in low and "construct" in low):
        return "forts-construct"
    if "how old" in low or "years old" in low:
        return "age-years"
    if "which place is linked with" in low or "city of monuments" in low:
        return "place-linked"
    if "capital" in low and ("city" in low or "mentioned" in low):
        return "capital-city"
    if "coronation" in low and "where" in low:
        return "coronation-place"
    if "centre of operations" in low or "center of operations" in low:
        return "ops-centre"
    if "father" in low and "who was" in low:
        return "who-father"
    if "mother" in low and "who was" in low:
        return "who-mother"
    return low[:72]


def _topic_allowed_group(group, topics: set[str]) -> bool:
    """Keep MCQ groups inside the asked topic family; no Sher bleed into Mughals."""
    key = (group.key or "").split(":", 1)[0]
    title = (group.title or "").lower()
    if "sher" in key or "sher" in title:
        return "sher" in topics
    # Specific ruler ask (e.g. Babur MCQs): keep that ruler's groups only.
    _RULER_TOPIC_NAMES = {
        "babar": ("babar", "babur"),
        "humayun": ("humayun",),
        "akbar": ("akbar",),
        "jahangir": ("jahangir",),
        "shahjahan": ("shahjahan", "shah jahan"),
        "aurangzeb": ("aurangzeb",),
        "shivaji": ("shivaji",),
        "sambhaji": ("sambhaji",),
        "bajirao": ("bajirao", "baji rao"),
    }
    asked_rulers = topics & set(_RULER_TOPIC_NAMES)
    if asked_rulers and not (topics & {"mughal", "maratha"}):
        blob = f"{key} {title}"
        if any(any(name in blob for name in _RULER_TOPIC_NAMES[ruler]) for ruler in asked_rulers):
            return True
        return False
    if topics & {"mughal"} and not (topics & {"maratha", "shivaji", "sambhaji", "bajirao"}):
        mughal_ok = {
            "mughal",
            "babar",
            "humayun",
            "akbar",
            "jahangir",
            "shahjahan",
            "aurangzeb",
            "taj",
            "din",
            "mansab",
            "administration",
            "general",
        }
        if key and key not in mughal_ok and key in GROUP_TITLE:
            return False
    return True


def _facts_from_group(group) -> list[McqFact]:
    title = group.title
    text = _group_text(group)
    if not _usable(text) or len(text.split()) < 12:
        return []
    pages = list(group.pages or [])
    facts: list[McqFact] = []

    def add(question: str, answer: str, kind: str) -> None:
        answer = _short(answer)
        question = _clean(question)
        if not answer or not question or len(question) > 140:
            return
        if _is_vacuous_question(question):
            return
        if kind == "person" and answer.lower() == title.lower():
            if "son of" in question.lower() or "daughter of" in question.lower():
                return
        if answer.lower() in AWKWARD_ANSWER:
            return
        if any(item.question.lower() == question.lower() for item in facts):
            return
        facts.append(
            McqFact(
                question=question,
                answer=answer,
                kind=kind,
                pages=pages,
                title=title,
                group_key=group.key,
            )
        )

    match = re.search(r"autobiography in the ([A-Za-z]+) language", text, re.I)
    if match:
        add(f"In which language did {title} write an autobiography?", match.group(1).title(), "language")
    match = LANG_RE.search(text)
    # Prefer concrete stems only (autobiography / administration); skip vague associated-with.
    if match and re.search(r"translated.*?into the ([A-Za-z]+) language|translated.*?into ([A-Za-z]+)", text, re.I):
        m2 = re.search(r"translated.*?into (?:the )?([A-Za-z]+)(?: language)?", text, re.I)
        if m2 and "akbar" in title.lower():
            add("Into which language were Hindu religious books translated under Akbar?", m2.group(1).title(), "language")
    match = BORN_RE.search(text)
    if match:
        add(f"Where was {title} born, according to the textbook?", match.group(1).strip(), "place")
    match = re.search(r"appointed as (?:the )?([A-Za-z][A-Za-z ]{1,28}?)(?: when| at| in|\.|\,)", text, re.I)
    if match:
        add(f"What office was {title} appointed to?", match.group(1).strip(), "official")
    # Prefer a concrete assumed-power age question (added later) over a vague one.
    match = re.search(r"in memory of (?:his wife )?([A-Z][A-Za-z ]{2,36}?)(?: on|\.|\,)", text)
    if match:
        add("In whose memory was the Taj Mahal built?", match.group(1).strip(), "person")
    match = re.search(r"\bbuilt (?:the )?([A-Z][A-Za-z][A-Za-z0-9 \-]{1,36}?)(?: in| on| at|\.|\,)", text)
    if match:
        work = match.group(1).strip()
        if any(token in work.lower() for token in ("fort", "mahal", "road", "mosque", "temple", "city")):
            add(f"What did {title} build, according to the textbook?", work, "monument" if any(t in work.lower() for t in ("mahal", "fort", "mosque", "temple")) else "work")
    match = re.search(r"constructed new forts at ([A-Z][A-Za-z, ]{8,48}?)(?:\.|$)", text)
    if match:
        add(f"Where did {title} construct new forts?", match.group(1).split(",")[0].strip(), "place")
        add("Who constructed new forts at Rohtas, according to the textbook?", title, "person")
    if re.search(r"built the Taj Mahal", text, re.I):
        add("Who built the Taj Mahal, according to the textbook?", title, "person")
    if re.search(r"autobiography in the Turkish", text, re.I):
        add("Who wrote an autobiography in the Turkish language?", title, "person")
    if re.search(r"imprisoned his father", text, re.I):
        add("Who imprisoned his father and seized power, according to the textbook?", title, "person")
    if re.search(r"white marble", text, re.I):
        add("The Taj Mahal is built using which material, according to the textbook?", "white marble", "material")
    if re.search(r"muhtasibs", text, re.I):
        add(f"Which officials did {title} appoint in important cities?", "muhtasibs", "official")
    if re.search(r"\bAlamgir\b", text):
        add(f"Which title did {title} earn, according to the textbook?", "Alamgir", "title")
    match = re.search(r"established the ([A-Za-z][A-Za-z ]{2,36}?)(?: in|\.|\,)", text, re.I)
    if match:
        add(f"What did {title} establish?", match.group(1).strip(), "work")
    if re.search(r"established Mughal", text, re.I):
        add(f"What did {title} establish in India, according to the textbook?", "Mughal rule", "work")
    match = re.search(r"First Battle of Panipat in (\d{4})", text, re.I)
    if match:
        add("In which year was the First Battle of Panipat fought?", match.group(1), "year")
    match = re.search(r"began around (\d{4})", text, re.I)
    if match:
        add("Around which year did construction of the Taj Mahal begin?", match.group(1), "year")
    match = re.search(r"completed around (\d{4})", text, re.I)
    if match:
        add("Around which year was the Taj Mahal completed?", match.group(1), "year")
    for year_match in YEAR_RE.finditer(text):
        start = max(0, year_match.start() - 48)
        window = text[start : year_match.end() + 24]
        if re.search(r"battle of panipat", window, re.I) and "first" in window.lower():
            add("In which year was the First Battle of Panipat fought?", year_match.group(1), "year")
        elif re.search(r"taj mahal", window, re.I) and re.search(r"began|started|construction", window, re.I):
            add("Around which year did construction of the Taj Mahal begin?", year_match.group(1), "year")
    if re.search(r"(guerrilla|guerilla) warfare", text, re.I):
        add(f"What kind of warfare is {title} associated with in the textbook?", "guerrilla warfare", "warfare")
    if re.search(r"Din-e-Ilahi|Din e Ilahi|Din-i-Ilahi", text, re.I):
        add("Which ruler is associated with Din-e-Ilahi in the textbook?", title, "person")
    match = re.search(r"After ([A-Z][A-Za-z. ]{2,32}?)[, ]+([A-Z][A-Za-z. ]{2,32}?) was appointed", text)
    if match:
        add(
            f"Who was appointed after {match.group(1).strip()}?",
            match.group(2).strip(),
            "person",
        )
    match = re.search(r"capital (?:city )?at ([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", text, re.I)
    if match:
        add(f"Which capital is mentioned in connection with {title}?", match.group(1).strip(), "place")
    match = re.search(r"banks of the river ([A-Z][A-Za-z]+)", text)
    if match:
        add("On the banks of which river was the Taj Mahal built?", match.group(1).strip(), "river")
    match = re.search(r"title ([A-Z][A-Za-z]{3,20})", text)
    if match and match.group(1).lower() not in {"the", "this", "that"}:
        add(f"Which title is mentioned for {title} in the textbook?", match.group(1).strip(), "title")
    match = re.search(r"son of ([A-Z][A-Za-z. ]{2,32}?)(?:\.|\,| who| and)", text)
    if match:
        parent = match.group(1).strip()
        if parent.lower() != title.lower() and len(parent.split()) <= 5:
            add(f"According to the textbook, {title} was the son of whom?", parent, "person")
    match = re.search(r"defeated ([A-Z][A-Za-z. ]{2,32}?)(?: in| at|\.|\,)", text)
    if match:
        foe = match.group(1).strip()
        if foe.lower() != title.lower() and len(foe) <= 42:
            add(f"Whom did {title} defeat, according to the textbook?", foe, "person")
    # Generic person-biography extractors (topic-bound, evidence-local).
    age_power = re.search(
        r"(?:When\s+)?" + re.escape(title) + r"\s+assumed power,?\s+he was only (\d{1,2}) years old",
        text,
        re.I,
    )
    if age_power:
        add(
            f"How old was {title} when he assumed power, according to the textbook?",
            f"{age_power.group(1)} years old",
            "age",
        )
    match = re.search(r"tutor and guardian ([A-Z][A-Za-z ]{2,32}?)(?: administered| came|\.|\,)", text)
    if match:
        add(f"Who was the tutor and guardian of {title}?", match.group(1).strip(), "person")
    match = re.search(r"guru (?:named |was )?([A-Z][A-Za-z ]{2,40}?)(?: who| and|,|\.)", text)
    if match:
        guru = match.group(1).strip()
        if guru.lower() != title.lower():
            add(f"Who was {title}'s guru, according to the textbook?", guru, "person")
    match = re.search(r"([A-Z][A-Za-z. ]{2,40}?) was (?:Shivaji|Baji Rao I|Akbar|Babur|[A-Z][a-z]+)['\u2019]s guru", text)
    if match:
        guru = match.group(1).strip()
        if guru.lower() != title.lower() and len(guru.split()) <= 5:
            add(f"Who was {title}'s guru, according to the textbook?", guru, "person")
    match = re.search(
        r"After the death of ([A-Z][A-Za-z. ]{2,40}?), (?:his|her) (?:eldest )?son,?\s+(?:Baji Rao I|Baji Rao|Shivaji|Akbar|Sambhaji)",
        text,
        re.I,
    )
    if match and re.search(re.escape(title.split()[0]), match.group(0), re.I):
        parent = match.group(1).strip()
        if parent.lower() != title.lower():
            add(f"Who was {title}'s father, according to the textbook?", parent, "person")
    match = re.search(r"mother,? ([A-Z][A-Za-z]{2,24})", text)
    if match and match.group(1).lower() not in {"the", "his", "her"}:
        add(f"Who was {title}'s mother, according to the textbook?", match.group(1).strip(), "person")
    match = re.search(r"father,? ([A-Z][A-Za-z]{2,24}(?:\s+[A-Z][A-Za-z]{2,24})?)", text)
    if match:
        father = match.group(1).strip()
        if father.lower() != title.lower():
            add(f"Who was {title}'s father, according to the textbook?", father, "person")
    match = re.search(r"Second Battle of Panipat(?: in |.*?in )?(\d{4})?", text, re.I)
    if match:
        if match.group(1):
            add("In which year was the Second Battle of Panipat fought?", match.group(1), "year")
        add(f"Which battle in 1556 is {title} associated with in the textbook?", "Second Battle of Panipat", "battle")
    match = re.search(r"Battle of ([A-Z][A-Za-z]+)", text)
    if match and match.group(1).lower() not in {"the", "this", "panipat"}:
        battle = f"Battle of {match.group(1).strip()}"
        add(f"Which battle is mentioned in connection with {title}?", battle, "battle")
    match = re.search(r"coronation(?: took place)?(?: in the year | in | at )[^. ]{0,40}?(\d{4})", text, re.I)
    if match:
        add(f"In which year did {title}'s coronation take place?", match.group(1), "year")
    match = re.search(r"renamed ([A-Z][A-Za-z]+)[^. ]{0,40}?as ([A-Z][A-Za-z]+)", text)
    if match:
        add(f"What did {title} rename {match.group(1)} as?", match.group(2).strip(), "place")
    match = re.search(r"built a new fort called ([A-Z][A-Za-z]+)", text, re.I)
    if match:
        add(f"Which new fort did {title} build, according to the textbook?", match.group(1).strip(), "place")
    if re.search(r"abolished the\s*['\"‘’]?\s*Jizya", text, re.I):
        add(f"Which tax on Hindus did {title} abolish?", "Jizya tax", "tax")
    if re.search(r"Mansabdari system", text, re.I):
        add(f"Which administrative system is described as unique to {title}?", "Mansabdari system", "system")
    if re.search(r"\bZabti system\b", text, re.I):
        add(f"Which revenue system did {title} bring into practice?", "Zabti system", "system")
    if re.search(r"Ryotwari system", text, re.I):
        add(f"Which revenue system is mentioned with {title}?", "Ryotwari system", "system")
    if re.search(r"policy of tolerance towards Hindus", text, re.I):
        add(f"What policy did {title} adopt towards Hindus?", "policy of tolerance", "policy")
    if re.search(r"\bPanch Mahal\b", text, re.I):
        add(f"Which monument in Fatehpur Sikri is mentioned with {title}?", "Panch Mahal", "monument")
    if re.search(r"Fatehpur Sikri", text, re.I):
        add(f"Which Mughal capital city is associated with {title}'s monuments?", "Fatehpur Sikri", "place")
    if re.search(r"\bMansabdars\b", text, re.I):
        add(f"What were supervisors of Mansabs called in {title}'s army?", "Mansabdars", "official")
    if re.search(r"\binfantry\b", text, re.I):
        add(f"Which of these army units is mentioned with {title}?", "infantry", "army_unit")
    if re.search(r"\bcavalry\b", text, re.I):
        add(f"Which of these army units is mentioned with {title}?", "cavalry", "army_unit")
    if re.search(r"elephant units", text, re.I):
        add(f"Which of these army units is mentioned with {title}?", "elephant units", "army_unit")
    if re.search(r"cannon units", text, re.I):
        add(f"Which of these army units is mentioned with {title}?", "cannon units", "army_unit")

    if re.search(r"dagh-mahali|dagh mahali", text, re.I):
        add(f"Which department stamped horses in {title}'s administration?", "dagh-mahali", "department")
    match = re.search(
        r"four ministers called ([A-Za-z, ]{8,80}?)(?: to assist|\.|$)",
        text,
        re.I,
    )
    if match:
        ministers = match.group(1).strip().rstrip(",")
        # Prefer a short distinctive minister name as the answer key.
        first = re.split(r",| and ", ministers)[0].strip()
        if first:
            add(f"Which minister title is listed among {title}'s four ministers?", first, "minister")
    match = re.search(r"born in ([A-Z][A-Za-z]+)", text)
    if match:
        add(f"Where was {title} born, according to the textbook?", match.group(1).strip(), "place")
    match = re.search(r"assembled an army of the local ([A-Z][A-Za-z]+) youths", text, re.I)
    if match:
        add(f"Which local youths did {title} train as an army?", match.group(1).strip(), "people_group")
    places = re.findall(
        r"\b(Torna|Purandar|Sinhagad|Raigad|Pratapgad|Shivneri|Amarkot|Fatehpur Sikri|Fatehpur|Chittor|Ranthambore|Kalinjar|Malwa|Gujarat|Bengal|Agra|Delhi|Panipat|Haldighat|Pune|Bhopal|Gwalior|Indore|Nagpur|Baroda|Chitradurga)\b",
        text,
    )
    # Prefer concrete place stems over vacuous "linked with" wording.
    if re.search(r"coronation.*?at ([A-Z][A-Za-z]+)", text, re.I):
        m = re.search(r"coronation.*?at ([A-Z][A-Za-z]+)", text, re.I)
        if m:
            add(f"Where did {title}'s coronation take place?", m.group(1).strip(), "place")
    if re.search(r"made ([A-Z][A-Za-z]+) as his centre of operations", text, re.I):
        m = re.search(r"made ([A-Z][A-Za-z]+) as his centre of operations", text, re.I)
        if m:
            add(f"Which place did {title} make his centre of operations?", m.group(1).strip(), "place")
    if re.search(r"Pune became his administrative centre", text, re.I):
        add(f"Which place became {title}'s administrative centre?", "Pune", "place")
    # Capitals mentioned with monuments / Mughal capitals
    if re.search(r"Fatehpur Sikri", text) and re.search(r"monument|architecture|capital", text, re.I):
        add(f"Which Mughal capital city is associated with {title}'s monuments?", "Fatehpur Sikri", "place")
    for place in places[:2]:
        if place.lower() in {title.lower(), "fatehpur"}:
            continue
        add(f"Which place is mentioned in connection with {title}?", place, "place")
    if re.search(r"Humayun was his father", text, re.I):
        add(f"Who was {title}'s father, according to the textbook?", "Humayun", "person")
    if re.search(r"Pharghana", text):
        add(f"Which kingdom was ruled by {title}'s father, according to the textbook?", "Pharghana", "place")
    if re.search(r"Raja Todarmal|Todar Mal", text, re.I):
        add(f"Who was a famous minister of finance under {title}?", "Raja Todarmal", "person")
    if re.search(r"Abdul Rahim Khan", text):
        add("Who translated Babur's autobiography into Persian?", "Abdul Rahim Khan", "person")

    if re.search(r"conquered Gujarat, Malwa", text, re.I):
        add(f"Which region did {title} conquer, according to the textbook?", "Gujarat", "place")
        add(f"Which region did {title} conquer, according to the textbook?", "Malwa", "place")
    if re.search(r"battle near Bhopal", text, re.I):
        add(f"Near which place did {title} defeat the Nizam?", "Bhopal", "place")
    if re.search(r"escaped from the prison", text, re.I) and re.search(r"\bAgra\b", text):
        add(f"From which city did {title} escape prison?", "Agra", "place")


    if re.search(r"Chatrapati|Chhatrapati", text, re.I):
        add(f"Which title is mentioned for {title} in the textbook?", "Chatrapati", "title")
    # Extra age / tax / monument / minister seeds from primary text.
    age_only = re.search(r"(?:Although he was|he was) only (\d{1,2}) years old", text, re.I)
    if age_only:
        add(
            f"How old was {title} when he became prominent, according to the textbook?",
            f"{age_only.group(1)} years old",
            "age",
        )
    if re.search(r"Chauth", text):
        add(f"Which tax or levy is mentioned with {title}?", "Chauth", "tax")
    if re.search(r"Sardeshmukhi", text):
        add(f"Which tax or levy is mentioned with {title}?", "Sardeshmukhi", "tax")
    if re.search(r"jahagir revenue system", text, re.I):
        add(f"Which revenue system did {title} abolish?", "jahagir revenue system", "system")
    for mon in re.findall(
        r"\b(Panch Mahal|Jodhabai palace|Birbal House|Kabutar Khana|Daulat Khana|Taj Mahal|Daftara Khana)\b",
        text,
    ):
        add(f"Which monument is mentioned in connection with {title}?", mon, "monument")
    for river in re.findall(r"banks of the river ([A-Z][A-Za-z]+)", text):
        add("On the banks of which river was the Taj Mahal built?", river.strip(), "river")
    if re.search(r"Marathi was the language of administration", text, re.I):
        add(f"Which language was used in {title}'s administration?", "Marathi", "language")
    if re.search(r"Hawaldar was the supervisor of the fort", text, re.I):
        add(f"Who was the supervisor of the fort in {title}'s administration?", "Hawaldar", "official")
    return facts


def _places_in(text: str) -> list[str]:
    """Return place-like tokens from a curriculum whitelist only."""
    found: list[str] = []
    for match in PLACE_RE.finditer(text or ""):
        value = match.group(1).strip()
        if value not in found:
            found.append(value)
    return found


PLACE_RE = re.compile(
    r"\b("
    r"Torna|Purandar|Sinhagad|Raigad|Pratapgad|Shivneri|Amarkot|Fatehpur Sikri|"
    r"Chittor|Ranthambore|Kalinjar|Malwa|Gujarat|Bengal|Agra|Delhi|Panipat|"
    r"Haldighat|Pune|Bhopal|Gwalior|Indore|Nagpur|Baroda|Chitradurga|"
    r"Srirangapatna|Karnataka|Maharashtra|North India|Afghanistan|Yamuna|"
    r"Narmada|Chambal|Salcet|Basin|Janjira|Rohtas|Pharghana|Jaipur|Gondwana|Uttar Pradesh"
    r")\b"
)

# Known textbook lexicon: only added to pools when present in evidence text.
LEXICON: dict[str, tuple[str, ...]] = {
    "language": ("Persian", "Turkish", "Arabic", "Sanskrit", "Hindi", "Marathi", "Kannada", "Urdu"),
    "system": (
        "Mansabdari system",
        "Zabti system",
        "Ryotwari system",
        "jahagir revenue system",
    ),
    "tax": ("Jizya tax", "Jizya", "Chauth", "Sardeshmukhi"),
    "monument": (
        "Taj Mahal",
        "Panch Mahal",
        "Jodhabai palace",
        "Birbal House",
        "Kabutar Khana",
        "Daulat Khana",
        "Daftara Khana",
        "Red Fort",
        "Jama Masjid",
    ),
    "material": ("white marble", "red sandstone"),
    "title": ("Alamgir", "Chatrapati", "Chhatrapati", "Peshwa"),
    "minister": ("Vakil", "Diwan", "Mir Bakshi", "Mir Bhakshi", "Main Sardar", "Sadr"),
    "official": ("muhtasibs", "Mansabdars", "Hawaldar", "Ashapradhans"),
    "department": ("dagh-mahali",),
    "warfare": ("guerrilla warfare", "armed warfare"),
    "policy": ("policy of tolerance",),
    "battle": (
        "First Battle of Panipat",
        "Second Battle of Panipat",
        "Battle of Haldighat",
        "Battle of Khanwa",
    ),
    "people_group": ("Mavalas",),
    "river": ("Yamuna", "Narmada", "Chambal"),
    "army_unit": ("infantry", "cavalry", "elephant units", "cannon units"),
    "place": (),  # places come from PLACE_RE only
}

# Distractor buckets: kinds in the same bucket may distract each other; never across buckets.
SEMANTIC_BUCKET = {
    "person": "person",
    "place": "place",
    "river": "river",
    "language": "language",
    "year": "year",
    "age": "age",
    "title": "title",
    "minister": "role",
    "official": "role",
    "tax": "tax",
    "system": "system",
    "monument": "monument",
    "material": "material",
    "warfare": "warfare",
    "policy": "policy",
    "battle": "battle",
    "department": "department",
    "people_group": "people_group",
    "army_unit": "army_unit",
    "work": "work",
    "term": "term",
}


def _bucket(kind: str) -> str:
    return SEMANTIC_BUCKET.get(kind or "", kind or "")

CURRICULUM_PERSON = {
    "mughal": ("Babur", "Humayun", "Akbar", "Jahangir", "Shah Jahan", "Aurangzeb", "Bairam Khan", "Mumtaz Mahal"),
    "maratha": ("Shivaji", "Sambhaji", "Balaji Vishwanath", "Baji Rao I", "Madhav Rao I", "Dadoji Kondadeo", "Nizam-ul-Mulk"),
}
CURRICULUM_TITLE = {
    "mughal": ("Alamgir",),
    "maratha": ("Chatrapati", "Peshwa"),
}
CURRICULUM_ROLE = {
    "mughal": ("Vakil", "Diwan", "Mir Bakshi", "Mansabdars", "muhtasibs"),
    "maratha": ("Hawaldar", "Ashapradhans", "Peshwa"),
}
CURRICULUM_OFFICE = CURRICULUM_ROLE  # backward alias
CURRICULUM_SYSTEM = {
    "mughal": ("Mansabdari system", "Zabti system"),
    "maratha": ("Ryotwari system", "jahagir revenue system"),
}
CURRICULUM_TAX = {
    "mughal": ("Jizya tax",),
    "maratha": ("Chauth", "Sardeshmukhi"),
}
CURRICULUM_PLACE = {
    "mughal": ("Agra", "Delhi", "Fatehpur Sikri", "Panipat", "Malwa", "Gujarat", "Bengal", "Afghanistan", "Pharghana"),
    "maratha": ("Pune", "Raigad", "Agra", "Maharashtra", "Gujarat", "Malwa", "Bhopal", "Gwalior", "Indore", "Nagpur", "Baroda"),
}
CURRICULUM_YEAR = {
    "mughal": ("1526", "1556", "1632", "1653"),
    "maratha": ("1674", "1720"),
}
CURRICULUM_LANGUAGE = {
    "mughal": ("Turkish", "Persian", "Arabic", "Hindi"),
    "maratha": ("Marathi", "Persian", "Sanskrit", "Hindi"),
}
CURRICULUM_WARFARE = {
    "maratha": ("guerrilla warfare", "armed warfare"),
}
CURRICULUM_BATTLE = {
    "mughal": ("First Battle of Panipat", "Second Battle of Panipat", "Battle of Haldighat"),
}
CURRICULUM_AGE = {
    "mughal": ("14 years old", "13 years old", "16 years old", "18 years old"),
    "maratha": ("19 years old", "16 years old", "18 years old", "21 years old"),
}


def _topic_family(topics: set[str]) -> str | None:
    if topics & {"maratha", "shivaji", "sambhaji", "bajirao", "peshwa", "madhav", "balaji"}:
        return "maratha"
    if topics & {"mughal", "babar", "humayun", "akbar", "jahangir", "shahjahan", "aurangzeb", "taj"}:
        return "mughal"
    return None


def _curriculum_distractors(kind: str, topics: set[str]) -> list[str]:
    """Same-category Class-9 curriculum terms for the topic family."""
    family = _topic_family(topics or set())
    if not family:
        return []
    bucket = _bucket(kind)
    mapping = {
        "person": CURRICULUM_PERSON,
        "title": CURRICULUM_TITLE,
        "role": CURRICULUM_ROLE,
        "office": CURRICULUM_ROLE,
        "system": CURRICULUM_SYSTEM,
        "tax": CURRICULUM_TAX,
        "place": CURRICULUM_PLACE,
        "year": CURRICULUM_YEAR,
        "language": CURRICULUM_LANGUAGE,
        "warfare": CURRICULUM_WARFARE,
        "battle": CURRICULUM_BATTLE,
        "age": CURRICULUM_AGE,
    }
    # Titles are scarce; allow same-category titles from both families.
    if bucket == "title":
        out: list[str] = []
        for fam_table in CURRICULUM_TITLE.values():
            for item in fam_table:
                if item not in out:
                    out.append(item)
        return out
    table = mapping.get(bucket, {}).get(family, ())
    return list(table)




def _classify_answer_kind(answer: str, hinted: str = "") -> str:
    """Map an answer string to a semantic MCQ category."""
    if hinted and hinted not in {"term", "work"}:
        return hinted
    low = (answer or "").lower().strip()
    if re.fullmatch(r"1[2-9]\d{2}", low):
        return "year"
    if re.search(r"\d+\s+years?\s+old", low):
        return "age"
    for kind, values in LEXICON.items():
        for value in values:
            if low == value.lower() or low == value.lower().replace(" tax", ""):
                return kind
    if "mumtaz" in low:
        return "person"
    if any(tok in low for tok in ("mahal", "fort", "mosque", "palace", "khana", "house")):
        return "monument"
    if any(tok in low for tok in ("system",)):
        return "system"
    if "warfare" in low:
        return "warfare"
    if "battle" in low:
        return "battle"
    if "tax" in low or low in {"chauth", "sardeshmukhi", "jizya"}:
        return "tax"
    if hinted:
        return hinted
    return "term"


def _scan_pool(text: str) -> dict[str, list[str]]:
    """Build same-category distractor pools from primary textbook evidence only."""
    pool: dict[str, list[str]] = defaultdict(list)

    def push(kind: str, value: str) -> None:
        value = _short(value)
        if not value:
            return
        kind = _classify_answer_kind(value, kind)
        if value not in pool[kind]:
            pool[kind].append(value)

    blob = text or ""
    for kind, values in LEXICON.items():
        for value in values:
            if re.search(rf"\b{re.escape(value)}\b", blob, re.I):
                # Normalize a few aliases
                if value.lower() == "jizya":
                    push("tax", "Jizya tax")
                elif value.lower() == "mir bhakshi":
                    push("minister", "Mir Bakshi")
                elif value.lower() == "chhatrapati":
                    push("title", "Chatrapati")
                else:
                    push(kind, value)

    for match in LANG_RE.finditer(blob):
        push("language", match.group(1).title())
    for match in YEAR_RE.finditer(blob):
        push("year", match.group(1))
    for match in re.finditer(r"(\d{1,2})\s+years?\s+old", blob, re.I):
        push("age", f"{match.group(1)} years old")
    for place in _places_in(blob):
        if place.lower() in {"yamuna", "narmada", "chambal"}:
            push("river", place)
            continue
        push("place", place)
    for title in GROUP_TITLE.values():
        if title.lower() in {
            "taj mahal",
            "din-e-ilahi",
            "guerrilla warfare",
            "mansabdari system",
            "mughal rule",
            "the marathas",
            "the ahom dynasty",
            "administration",
            "the peshwas",
        }:
            continue
        if re.search(rf"\b{re.escape(title)}\b", blob, re.I):
            push("person", title)
    # Extra people often used as answers
    for person in re.findall(
        r"\b(Umar Sheikh|Bairam Khan|Mumtaz Mahal|Dadoji Kondadeo|Nizam-ul-Mulk|"
        r"Balaji Vishwanath|Sambhaji|Tulsidas|Surdas)\b",
        blob,
    ):
        push("person", person)
    return pool


def _grounded_distractors(
    fact: McqFact, facts: list[McqFact], scanned: dict[str, list[str]], titles: list[str], topics: set[str] | None = None,
) -> list[str]:
    """Same-category distractors only; never cross-fill from other semantic types."""
    out: list[str] = []
    seen = {fact.answer.lower()}
    kind = _classify_answer_kind(fact.answer, fact.kind)

    def push(value: str) -> None:
        value = _short(value)
        if not value:
            return
        key = value.lower()
        if key in seen:
            return
        # Reject options that merely echo the stem (except person names).
        if key in fact.question.lower() and kind != "person":
            return
        # Enforce same semantic bucket only.
        cand_kind = _classify_answer_kind(value, kind)
        if _bucket(cand_kind) != _bucket(kind):
            return
        seen.add(key)
        out.append(value)

    # 1) Other textbook facts in the same semantic bucket
    for other in facts:
        other_kind = _classify_answer_kind(other.answer, other.kind)
        if _bucket(other_kind) == _bucket(kind) and other.answer.lower() != fact.answer.lower():
            push(other.answer)

    # 2) Scanned pools that share this semantic bucket
    for skim_kind, items in scanned.items():
        if _bucket(skim_kind) != _bucket(kind):
            continue
        for item in items:
            push(item)

    # 3) Person questions may use other ruler names from the allowed topic titles
    if kind == "person":
        for title in titles:
            if title.lower() in {
                "taj mahal",
                "administration",
                "mughal rule",
                "the marathas",
                "the peshwas",
                "guerrilla warfare",
                "mansabdari system",
                "din-e-ilahi",
            }:
                continue
            push(title)
        for item in scanned.get("person", []):
            push(item)

    # 4) Class-9 curriculum same-bucket terms for the topic family.
    for item in _curriculum_distractors(kind, topics or set()):
        push(item)

    # No cross-category fallback. Prefer fewer high-quality questions.
    return out


def _pad_options(correct: str, distractors: list[str]) -> list[str] | None:
    options = [correct]
    for item in distractors:
        if item.lower() not in {opt.lower() for opt in options}:
            options.append(item)
        if len(options) == 4:
            return options
    return None


def format_mcqs(items: list[dict]) -> str:
    blocks = []
    for index, item in enumerate(items, start=1):
        lines = [f"{index}. {item['question']}"]
        for letter, option in zip(LETTERS, item["options"]):
            lines.append(f"{letter}. {option}")
        lines.append(f"Answer: {item['answer_letter']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _round_robin(facts: list[McqFact]) -> list[McqFact]:
    buckets: dict[str, list[McqFact]] = defaultdict(list)
    for fact in facts:
        buckets[fact.group_key or fact.title].append(fact)
    ordered: list[McqFact] = []
    keys = list(buckets.keys())
    index = 0
    while len(ordered) < len(facts):
        key = keys[index % len(keys)]
        if buckets[key]:
            ordered.append(buckets[key].pop(0))
        index += 1
        if index > len(facts) * 8:
            break
    return ordered


def mcqs_from_pack(
    question: str,
    chunks: list[dict],
    count: int = 10,
    previous_answer: str = "",
    previous_fingerprints: list[str] | None = None,
) -> tuple[str, list[str]]:
    from rag.engine.classify import extract_topics

    topics = extract_topics(question or "")
    plan_full = build_coverage_plan(chunks)
    plan = filter_plan(question, plan_full) or plan_full
    plan = [group for group in plan if _topic_allowed_group(group, topics)]
    facts: list[McqFact] = []
    titles = []
    blob = ""
    for group in plan:
        facts.extend(_facts_from_group(group))
        titles.append(group.title)
        blob += " " + _group_text(group)
    # Broader distractor pool from family-allowed groups (still no Sher into Mughals).
    scan_blob = blob
    for group in plan_full:
        if not _topic_allowed_group(group, topics):
            continue
        scan_blob += " " + _group_text(group)
    scanned = _scan_pool(scan_blob or blob)
    if topics & {"mughal"} and "sher" not in topics:
        titles = [t for t in titles if "sher" not in t.lower()]
        scanned["person"] = [p for p in scanned.get("person", []) if "sher" not in p.lower()]
    skip = set(previous_fingerprints or [])
    skip.update(fingerprints_from_answer(previous_answer))
    used_q = set()
    used_sig = set()
    items = []
    for fact in _round_robin(facts):
        if len(items) >= count:
            break
        if _is_vacuous_question(fact.question):
            continue
        fp = fingerprint(fact.question, fact.answer)
        stem_key = re.sub(r"[^a-z0-9]+", "", fact.question.lower())
        sig = _stem_signature(fact.question)
        if fp in skip or fact.question.lower() in used_q or stem_key in used_q or sig in used_sig:
            continue
        distractors = _grounded_distractors(fact, facts, scanned, titles, topics)
        options = _pad_options(fact.answer, distractors)
        if not options:
            continue
        if len({opt.strip().lower() for opt in options if opt and opt.strip()}) < 4:
            continue
        if any(not (opt or "").strip() for opt in options):
            continue
        rotate = len(items) % 4
        ordered = options[rotate:] + options[:rotate]
        if fact.answer not in ordered:
            continue
        letter = LETTERS[ordered.index(fact.answer)]
        pages = [p for p in (fact.pages or []) if p is not None]
        items.append(
            {
                "question": fact.question,
                "options": ordered,
                "answer_letter": letter,
                "answer_text": fact.answer,
                "fingerprint": fp,
                "pages": pages,
            }
        )
        skip.add(fp)
        used_q.add(fact.question.lower())
        used_q.add(stem_key)
        used_sig.add(sig)
    fps = [item["fingerprint"] for item in items]
    if not items:
        if previous_fingerprints or previous_answer:
            return (
                "The prescribed textbook does not support additional unique practice questions "
                "of this kind without repeating earlier questions.",
                [],
            )
        return (
            "The prescribed textbook does not support enough unique practice questions "
            "of this kind from the available evidence.",
            [],
        )
    body = format_mcqs(items)
    if len(items) < count:
        body += (
            f"\n\nThe prescribed textbook supports {len(items)} unique practice questions of this kind "
            f"(requested {count}). No extra questions are added beyond the textbook."
        )
    return body, fps

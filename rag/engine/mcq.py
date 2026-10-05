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
)


def _is_vacuous_question(question: str) -> bool:
    low = (question or "").lower().strip()
    return any(stem in low for stem in VACUOUS_STEMS)


def _stem_signature(question: str) -> str:
    """Collapse near-duplicate stems (same fact asked two ways)."""
    low = re.sub(r"[^a-z0-9]+", " ", (question or "").lower())
    low = re.sub(r"\b(according to the textbook|in the textbook|of this kind)\b", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if "language" in low and ("autobiography" in low or "wrote" in low or "write" in low):
        return "lang-auto"
    if "turkish" in low and "autobiography" in low:
        return "lang-auto"
    if "taj mahal" in low and ("memory" in low or ("built" in low and "who" in low)):
        return "taj-builder-or-memory"
    if "rohtas" in low or ("forts" in low and "construct" in low):
        return "forts-construct"
    if "how old" in low or "years old" in low:
        return "age-years"
    if "which place is linked with" in low:
        return "place-linked"
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
        if answer.lower() in {"this", "that", "these", "those", "king", "emperor", "ruler"}:
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
    if match and re.search(r"autobiography|wrote|written|translated|language", text, re.I):
        add(f"Which language is mentioned with {title} in the textbook?", match.group(1).title(), "language")
    match = BORN_RE.search(text)
    if match:
        add(f"Where was {title} born, according to the textbook?", match.group(1).strip(), "place")
    match = re.search(r"appointed as (?:the )?([A-Za-z][A-Za-z ]{1,28}?)(?: when| at| in|\.|\,)", text, re.I)
    if match:
        add(f"What office was {title} appointed to?", match.group(1).strip(), "title")
    # Prefer a concrete assumed-power age question (added later) over a vague one.
    match = re.search(r"in memory of (?:his wife )?([A-Z][A-Za-z ]{2,36}?)(?: on|\.|\,)", text)
    if match:
        add("In whose memory was the Taj Mahal built?", match.group(1).strip(), "person")
    match = re.search(r"\bbuilt (?:the )?([A-Z][A-Za-z][A-Za-z0-9 \-]{1,36}?)(?: in| on| at|\.|\,)", text)
    if match:
        work = match.group(1).strip()
        if any(token in work.lower() for token in ("fort", "mahal", "road", "mosque", "temple", "city")):
            add(f"What did {title} build, according to the textbook?", work, "work")
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
        add("The Taj Mahal is built using which material, according to the textbook?", "white marble", "term")
    if re.search(r"muhtasibs", text, re.I):
        add(f"Which officials did {title} appoint in important cities?", "muhtasibs", "term")
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
        add(f"What kind of warfare is {title} associated with in the textbook?", "guerrilla warfare", "term")
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
        add("On the banks of which river was the Taj Mahal built?", match.group(1).strip(), "place")
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
        add(f"Which battle in 1556 is {title} associated with in the textbook?", "Second Battle of Panipat", "term")
    match = re.search(r"Battle of ([A-Z][A-Za-z]+)", text)
    if match and match.group(1).lower() not in {"the", "this", "panipat"}:
        battle = f"Battle of {match.group(1).strip()}"
        add(f"Which battle is mentioned in connection with {title}?", battle, "term")
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
        add(f"Which tax on Hindus did {title} abolish?", "Jizya tax", "term")
    if re.search(r"Mansabdari system", text, re.I):
        add(f"Which administrative system is described as unique to {title}?", "Mansabdari system", "term")
    if re.search(r"\bZabti system\b", text, re.I):
        add(f"Which revenue system did {title} bring into practice?", "Zabti system", "term")
    if re.search(r"Ryotwari system", text, re.I):
        add(f"Which revenue system is mentioned with {title}?", "Ryotwari system", "term")
    if re.search(r"policy of tolerance towards Hindus", text, re.I):
        add(f"What policy did {title} adopt towards Hindus?", "policy of tolerance", "term")
    if re.search(r"\bPanch Mahal\b", text, re.I):
        add(f"Which monument in Fatehpur Sikri is mentioned with {title}?", "Panch Mahal", "work")
    if re.search(r"Fatehpur Sikri", text, re.I):
        add(f"Which city of monuments is linked with {title} in the textbook?", "Fatehpur Sikri", "place")
    if re.search(r"\bMansabdars\b", text, re.I):
        add(f"What were supervisors of Mansabs called in {title}'s army?", "Mansabdars", "term")
    if re.search(r"dagh-mahali|dagh mahali", text, re.I):
        add(f"Which department stamped horses in {title}'s administration?", "dagh-mahali", "term")
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
            add(f"Which minister title is listed among {title}'s four ministers?", first, "title")
    match = re.search(r"born in ([A-Z][A-Za-z]+)", text)
    if match:
        add(f"Where was {title} born, according to the textbook?", match.group(1).strip(), "place")
    match = re.search(r"assembled an army of the local ([A-Z][A-Za-z]+) youths", text, re.I)
    if match:
        add(f"Which local youths did {title} train as an army?", match.group(1).strip(), "term")
    places = re.findall(
        r"\b(Torna|Purandar|Sinhagad|Raigad|Pratapgad|Shivneri|Amarkot|Fatehpur|Chittor|Ranthambore|Kalinjar|Malwa|Gujarat|Bengal|Agra|Delhi|Panipat|Haldighat)\b",
        text,
    )
    for place in places[:3]:
        add(f"Which place is linked with {title} in the textbook?", place, "place")
    if re.search(r"Humayun was his father", text, re.I):
        add(f"Who was {title}'s father, according to the textbook?", "Humayun", "person")
    if re.search(r"Chatrapati|Chhatrapati", text, re.I):
        add(f"Which title is mentioned for {title} in the textbook?", "Chatrapati", "title")
    return facts


def _places_in(text: str) -> list[str]:
    found: list[str] = []
    skip = {
        "india",
        "hindu",
        "muslim",
        "quran",
        "this",
        "that",
        "these",
        "their",
        "mughal",
        "maratha",
        "persian",
        "turkish",
        "english",
        "class",
        "board",
        "state",
        "king",
        "emperor",
        "after",
        "before",
        "north",
        "south",
        "east",
        "west",
    }
    for match in re.finditer(
        r"\b(?:at|in|from|near|of)\s+([A-Z][A-Za-z]{3,}(?:\s+[A-Z][A-Za-z]{3,})?)",
        text,
    ):
        value = match.group(1).strip()
        if value.lower() in skip or value in found:
            continue
        if len(value) > 32:
            continue
        found.append(value)
    return found


def _scan_pool(text: str) -> dict[str, list[str]]:
    pool: dict[str, list[str]] = defaultdict(list)

    def push(kind: str, value: str) -> None:
        value = _short(value)
        if value and value not in pool[kind]:
            pool[kind].append(value)

    for match in LANG_RE.finditer(text):
        push("language", match.group(1).title())
    for match in YEAR_RE.finditer(text):
        push("year", match.group(1))
    for match in BORN_RE.finditer(text):
        push("place", match.group(1))
    for match in re.finditer(r"capital (?:city )?at ([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", text, re.I):
        push("place", match.group(1))
    for match in re.finditer(r"banks of the river ([A-Z][A-Za-z]+)", text):
        push("place", match.group(1))
    for place in _places_in(text):
        push("place", place)
    for title in GROUP_TITLE.values():
        if re.search(rf"\b{re.escape(title)}\b", text, re.I):
            push("person", title)
    if re.search(r"white marble", text, re.I):
        push("term", "white marble")
    if re.search(r"muhtasibs", text, re.I):
        push("term", "muhtasibs")
    if re.search(r"guerrilla|guerilla", text, re.I):
        push("term", "guerrilla warfare")
    if re.search(r"\bAlamgir\b", text):
        push("title", "Alamgir")
    return pool



def _grounded_distractors(fact: McqFact, facts: list[McqFact], scanned: dict[str, list[str]], titles: list[str]) -> list[str]:
    """Prefer same-kind textbook answers; never invent filler options."""
    out: list[str] = []
    seen = {fact.answer.lower()}

    def push(value: str) -> None:
        value = _short(value)
        if not value:
            return
        key = value.lower()
        if key in seen:
            return
        # Reject options that merely echo the stem.
        if key in fact.question.lower() and fact.kind != "person":
            return
        seen.add(key)
        out.append(value)

    for other in facts:
        if other.kind == fact.kind and other.answer.lower() != fact.answer.lower():
            push(other.answer)
    for item in scanned.get(fact.kind, []):
        push(item)
    if fact.kind == "person":
        for title in titles:
            push(title)
        for item in scanned.get("person", []):
            push(item)
    # Cross-kind fallback only from scanned textbook pool of related kinds.
    if len(out) < 3:
        related = {
            "person": ("title", "place", "term"),
            "place": ("person", "title", "term"),
            "title": ("person", "term", "place"),
            "term": ("title", "work", "place", "person"),
            "work": ("term", "title", "place"),
            "year": ("place", "person", "title"),
            "language": ("place", "person", "title"),
            "age": ("place", "person", "title", "term"),
        }
        for kind in related.get(fact.kind, ()):
            for item in scanned.get(kind, []):
                push(item)
                if len(out) >= 6:
                    break
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
        distractors = _grounded_distractors(fact, facts, scanned, titles)
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

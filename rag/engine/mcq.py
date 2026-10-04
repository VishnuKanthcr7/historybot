"""Deterministic textbook-grounded MCQs from a final EvidencePack."""

from __future__ import annotations

import re

from rag.engine.coverage import build_coverage_plan, filter_plan, readable_extract
from rag.engine.validate import unsupported_named_items

LETTERS = "ABCD"


SKIP_SENTENCE = (
    "do you know",
    "mughals in india",
    "seven wonders",
    "fill in the blanks",
    "exercises",
    "project work",
)


def _sentence(group) -> str:
    extract = readable_extract(group.chunks)
    for piece in re.split(r"(?<=[.!?])\s+", extract or ""):
        cleaned = re.sub(r"\s+", " ", piece).strip(" .")
        low = cleaned.lower()
        if any(marker in low for marker in SKIP_SENTENCE):
            continue
        if cleaned.count(",") >= 4 and len(cleaned.split()) < 18:
            continue
        if 48 <= len(cleaned) <= 180 and cleaned[0].isupper():
            return cleaned
    return ""


def _stems_from_answer(previous: str) -> set[str]:
    stems = set()
    for match in re.finditer(r"^\d+\.\s+(.+)$", previous or "", re.M):
        stems.add(match.group(1).strip().lower())
    return stems


def format_mcqs(items: list[dict]) -> str:
    blocks = []
    for index, item in enumerate(items, start=1):
        options = item["options"]
        lines = [f"{index}. {item['question']}"]
        for letter, option in zip(LETTERS, options):
            lines.append(f"{letter}. {option}")
        lines.append(f"Answer: {item['answer_letter']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


STEMS = (
    "Which statement about {title} is given in the Class 9 textbook?",
    "According to the prescribed textbook, what is said about {title}?",
    "What does the Class 9 textbook say about {title}?",
)


def mcqs_from_pack(
    question: str,
    chunks: list[dict],
    count: int = 10,
    previous_answer: str = "",
) -> str:
    plan = filter_plan(question, build_coverage_plan(chunks)) or build_coverage_plan(chunks)
    facts = []
    seen = set()
    for group in plan:
        sentence = _sentence(group)
        if not sentence:
            continue
        key = sentence.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        facts.append({"title": group.title, "sentence": sentence, "pages": group.pages})
    if len(facts) < 2:
        return ""
    skip = _stems_from_answer(previous_answer)
    questions = []
    used_stems = set()
    rotate_base = 0
    while len(questions) < count:
        progressed = False
        for fact in facts:
            if len(questions) >= count:
                break
            stem_template = STEMS[(len(questions) + rotate_base) % len(STEMS)]
            stem = stem_template.format(title=fact["title"])
            if stem.lower() in skip or stem.lower() in used_stems:
                continue
            others = [item for item in facts if item["title"] != fact["title"]]
            options = [fact["sentence"]]
            for other in others:
                if other["sentence"] not in options:
                    options.append(other["sentence"])
                if len(options) == 4:
                    break
            while len(options) < 4:
                filler = f"The prescribed textbook does not give this extra detail about {fact['title']}."
                if filler not in options:
                    options.append(filler)
                else:
                    break
            if len(options) < 4:
                continue
            rotate = len(questions) % 4
            ordered = options[rotate:] + options[:rotate]
            correct = fact["sentence"]
            if correct not in ordered:
                continue
            letter = LETTERS[ordered.index(correct)]
            blob = " ".join([stem, correct])
            if unsupported_named_items(blob, chunks):
                continue
            questions.append(
                {
                    "question": stem,
                    "options": ordered[:4],
                    "answer_letter": letter,
                    "answer_text": correct,
                }
            )
            used_stems.add(stem.lower())
            progressed = True
        if not progressed:
            rotate_base += 1
            if rotate_base > len(STEMS) + 2:
                break
    if len(questions) < count:
        return ""
    return format_mcqs(questions[:count])

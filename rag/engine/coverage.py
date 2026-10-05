"""Coverage plans and section generation from a FINAL evidence pack only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.engine.classify import TOPIC_ALIASES, extract_topics
from rag.engine.pack import ahom_primary_chunk, chunk_group_key, looks_like_toc
from rag.engine.topic_map import (
    AHOM_FAMILY,
    MARATHA_FAMILY,
    MUGHAL_FAMILY,
    RULER_KEYS,
    dynasty_keys,
    looks_like_map_chunk,
)
from rag.engine.intent import wants_easy_english
from rag.engine.sanitize import sanitize_student_text
from rag.engine.validate import unsupported_named_items
from rag.llm.client import LlmError, complete
from rag.prompts.tutor import SYSTEM_PROMPT

GROUP_TITLE = {
    "babar": "Babur",
    "humayun": "Humayun",
    "akbar": "Akbar",
    "jahangir": "Jahangir",
    "shahjahan": "Shah Jahan",
    "aurangzeb": "Aurangzeb",
    "sher": "Sher Shah",
    "shivaji": "Shivaji",
    "sambhaji": "Sambhaji",
    "peshwa": "The Peshwas",
    "bajirao": "Baji Rao I",
    "balaji": "Balaji Vishwanath",
    "madhav": "Madhav Rao I",
    "nizam": "Nizam-ul-Mulk",
    "bhopal": "Battle near Bhopal",
    "taj": "Taj Mahal",
    "din": "Din-e-Ilahi",
    "guerilla": "Guerrilla warfare",
    "mansab": "Mansabdari system",
    "maratha": "The Marathas",
    "mughal": "Mughal rule",
    "ahom": "The Ahom Dynasty",
    "administration": "Administration",
}

PREFERRED_ORDER = (
    "mughal",
    "babar",
    "humayun",
    "sher",
    "akbar",
    "jahangir",
    "shahjahan",
    "aurangzeb",
    "maratha",
    "shivaji",
    "sambhaji",
    "peshwa",
    "bajirao",
    "balaji",
    "madhav",
    "nizam",
    "bhopal",
    "ahom",
    "administration",
    "general",
)

LEADIN_RE = re.compile(
    r"(?is)^(?:here(?:'s| is) (?:a rewritten explanation[^\n]*|a short section(?: on [^.\n]+)?|what (?:the )?(?:class 9 )?textbook says[^\n]*)[.!]?\s*|"
    r"according to the (?:retrieved )?evidence(?: provided)?[,:]?\s*|"
    r"based on the retrieved evidence[,:]?\s*|"
    r"the (?:retrieved )?evidence (?:says|shows|provided)[,:]?\s*|"
    r"the chunks show[,:]?\s*"
    r")"
)
META_TERMS_RE = re.compile(
    r"(?i)\b(chroma|evidence pack|vector database|retrieval|chunks?|RAG|Ollama|LLM|nomic-embed)\b"
)

MERGE_INTO = {
    "taj": "shahjahan",
    "din": "akbar",
    "mansab": "akbar",
    "guerilla": "shivaji",
    "sambhaji": "shivaji",
}


@dataclass
class CoverageGroup:
    key: str
    title: str
    pages: list[int]
    chunks: list[dict] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)

    def as_public(self) -> dict:
        return {"key": self.key, "title": self.title, "pages": self.pages, "chunk_count": len(self.chunks)}


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _usable_chunk(item: dict) -> bool:
    text = item.get("text") or ""
    if looks_like_toc(text) or looks_like_map_chunk(text):
        return False
    if _spaced_ocr(text):
        return False
    return len(text.split()) >= 20


def _spaced_ocr(text: str) -> bool:
    return bool(re.search(r"(?:\b[A-Za-z]\s){8,}", text or ""))


def _heading_key(text: str) -> str | None:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    probe = [line.strip(" :-") for line in lines[:5]]
    probe.append(" ".join(lines[:2])[:110])
    for fragment in probe:
        low = fragment.lower()
        for key in RULER_KEYS:
            title = (GROUP_TITLE.get(key) or key).lower()
            aliases = [alias for alias in TOPIC_ALIASES.get(key, (key,)) if alias.isascii()]
            if low == title or low in aliases:
                return key
            if low.startswith(title + " ") or any(low.startswith(alias) for alias in aliases):
                return key
    return None


def _group_key(item: dict) -> str:
    heading = _heading_key(item.get("text") or "")
    if heading == "aurangzeb" and not ahom_primary_chunk(item):
        return "aurangzeb"
    if heading and heading not in {"aurangzeb"}:
        return heading
    return chunk_group_key(item)


def build_coverage_plan(chunks: list[dict]) -> list[CoverageGroup]:
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in chunks:
        if not _usable_chunk(item):
            continue
        key = _group_key(item)
        key = MERGE_INTO.get(key, key)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(item)
    if "general" in buckets and len(buckets) > 1:
        order = [key for key in order if key != "general"]
    order = sorted(
        order,
        key=lambda key: (PREFERRED_ORDER.index(key) if key in PREFERRED_ORDER else 80, key),
    )
    groups = []
    for key in order:
        items = buckets.get(key) or []
        if not items:
            continue
        aliases = list(TOPIC_ALIASES.get(key, (key,)))
        title = GROUP_TITLE.get(key) or aliases[0].title()
        pages = sorted({p for item in items if (p := _page(item)) is not None})
        groups.append(
            CoverageGroup(
                key=key,
                title=title,
                pages=pages,
                chunks=items,
                markers=[alias for alias in aliases if alias.isascii()] or [key],
            )
        )
    return groups[:10]


def _rebuild_group(group: CoverageGroup, chunks: list[dict]) -> CoverageGroup:
    pages = sorted({p for item in chunks if (p := _page(item)) is not None})
    return CoverageGroup(
        key=group.key,
        title=group.title,
        pages=pages,
        chunks=chunks,
        markers=group.markers,
    )


def _bound_group(question: str, group: CoverageGroup) -> CoverageGroup:
    topics = extract_topics(question)
    family = dynasty_keys(topics)
    chunks = list(group.chunks)
    if "ahom" not in topics and family != AHOM_FAMILY:
        chunks = [item for item in chunks if not ahom_primary_chunk(item)]
        if group.key == "ahom":
            chunks = []
    if family == MUGHAL_FAMILY and "shivaji" not in topics and group.key in MARATHA_FAMILY:
        chunks = []
    return _rebuild_group(group, chunks)


def filter_plan(question: str, plan: list[CoverageGroup]) -> list[CoverageGroup]:
    topics = extract_topics(question)
    family = dynasty_keys(topics)
    bounded = [_bound_group(question, group) for group in plan]
    bounded = [group for group in bounded if group.chunks]
    person_keys = {
        "babar",
        "akbar",
        "shivaji",
        "shahjahan",
        "aurangzeb",
        "bajirao",
        "humayun",
        "madhav",
        "sher",
        "balaji",
    }
    named = topics & person_keys
    if len(named) == 1:
        key = next(iter(named))
        focused = [group for group in bounded if group.key == key]
        if focused:
            return focused
    if family == AHOM_FAMILY or "ahom" in topics:
        ahom_groups = [group for group in bounded if group.key == "ahom"]
        return ahom_groups or bounded
    if "ahom" not in topics:
        bounded = [group for group in bounded if group.key != "ahom"]
    if family == MUGHAL_FAMILY and "shivaji" not in topics:
        return [group for group in bounded if group.key not in MARATHA_FAMILY]
    if family == MARATHA_FAMILY and "akbar" not in topics:
        drop = {"babar", "humayun", "akbar", "jahangir", "shahjahan", "sher", "taj", "din", "mansab", "mughal"}
        return [group for group in bounded if group.key not in drop]
    return bounded


def group_covered(answer: str, group: CoverageGroup) -> bool:
    low = (answer or "").lower()
    if not group.markers:
        return bool((answer or "").strip())
    return any(marker.lower() in low for marker in group.markers)


def coverage_score(answer: str, plan: list[CoverageGroup]) -> dict:
    expected = [group.key for group in plan]
    generated = [group.key for group in plan if group_covered(answer, group)]
    missing = [key for key in expected if key not in generated]
    total = len(expected) or 1
    ratio = len(generated) / total
    if ratio >= 0.8:
        grade = "GOOD"
    elif ratio >= 0.5:
        grade = "PARTIAL"
    else:
        grade = "FAIL"
    return {
        "expected": expected,
        "generated": generated,
        "missing": missing,
        "grade": grade,
        "ratio": round(ratio, 2),
    }


def readable_extract(chunks: list[dict], limit: int = 8, max_words: int = 90) -> str:
    sentences = []
    seen = set()
    dangling = {"the", "of", "and", "to", "a", "an", "with", "for", "in"}
    for item in chunks:
        text = " ".join((item.get("text") or "").split())
        if looks_like_toc(text) or looks_like_map_chunk(text) or _spaced_ocr(text):
            continue
        for sent in re.split(r"(?<=[.!?])\s+", text):
            words = sent.split()
            if len(words) < 6 or len(words) > max_words:
                continue
            if words[-1].lower().strip(".,;:") in dangling:
                continue
            key = sent[:60].lower()
            if key in seen:
                continue
            seen.add(key)
            sentences.append(sent.strip())
            if len(sentences) >= limit:
                return " ".join(sentences)
    return " ".join(sentences)


def _focus_chunk_text(group: CoverageGroup, item: dict) -> str:
    text = item.get("text") or ""
    needles = [group.title] + [marker for marker in (group.markers or []) if len(marker) >= 4]
    for needle in needles:
        match = re.search(re.escape(needle), text, re.I)
        if match and match.start() > 8:
            return text[match.start() :]
    return text


def generate_section(question: str, group: CoverageGroup, strict: bool = False, full_facts: bool = False) -> str:
    chunk_limit = 8 if full_facts else 4
    blocks = []
    for item in group.chunks[:chunk_limit]:
        page = _page(item)
        text = " ".join(_focus_chunk_text(group, item).split())[:1100]
        blocks.append(f"[printed_page={page}]\n{text}")
    extra = " Use only names and dates that appear in the evidence." if strict else ""
    if full_facts:
        extra += (
            " Use every distinct textbook fact in these passages. Write 6 to 12 short sentences. "
            "Do not drop facts just to keep the answer short."
        )
        sentence_line = ""
    else:
        sentence_line = " 4 to 8 short sentences."
    if wants_easy_english(question) or re.search(
        r"easy english|simple english|explain simply|class 9 student", question or "", re.I
    ):
        extra += (
            " Use very simple Class 9 English and short sentences. "
            "Easy English is a style change only; keep the same facts."
        )
    user = (
        f"Student question: {question}\n"
        f"Write a short Class 9 tutor section titled {group.title}. "
        f"Start with a natural sentence about {group.title}. "
        f"Write only about {group.title}. "
        f"Do not begin with a neighbouring person unless that person is needed to explain {group.title}. "
        "Do not write phrases such as 'according to the evidence', 'based on the retrieved evidence', "
        "'the evidence says', 'the chunks show', or 'here is a short section'. "
        "Do not mention RAG, retrieval, Chroma, chunks, models, or page numbers. "
        f"Use ONLY the textbook passages below.{sentence_line}{extra}\n"
        "Do not mention people who are not in these passages.\n\n"
        f"Textbook passages:\n{chr(10).join(blocks)}"
    )
    extract_limit = 10 if full_facts else 3
    extract_words = 80 if full_facts else 42
    try:
        raw = complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0 if strict else 0.1,
            max_tokens=520 if full_facts else 280,
            timeout=90,
        )
    except (LlmError, TimeoutError, OSError):
        return readable_extract(group.chunks, limit=extract_limit, max_words=extract_words)
    text = (raw or "").strip()
    if unsupported_named_items(text, group.chunks):
        try:
            raw = complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user + "\nSTRICT: omit any name not in the evidence."},
                ],
                temperature=0.0,
                max_tokens=400 if full_facts else 240,
                timeout=90,
            )
            text = (raw or "").strip()
        except (LlmError, TimeoutError, OSError):
            text = ""
        if not text or unsupported_named_items(text, group.chunks):
            return readable_extract(group.chunks, limit=extract_limit, max_words=extract_words)
    packed = readable_extract(group.chunks, limit=extract_limit, max_words=extract_words)
    cleaned = _clean_student_text(text, group.title)
    if full_facts and packed and len(cleaned.split()) < max(55, int(len(packed.split()) * 0.45)):
        return packed
    return cleaned


def _clean_student_text(text: str, title: str | None = None) -> str:
    cleaned = (text or "").strip()
    for _ in range(3):
        nxt = LEADIN_RE.sub("", cleaned).strip()
        if nxt == cleaned:
            break
        cleaned = nxt
    if title:
        title_re = re.compile(rf"^{re.escape(title)}\s*\n+", re.I)
        cleaned = title_re.sub("", cleaned)
    cleaned = META_TERMS_RE.sub("", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return sanitize_student_text(cleaned.strip())


def _page_label(pages: list) -> str:
    values = sorted({int(page) for page in pages if page is not None})
    if not values:
        return ""
    if len(values) == 1:
        return f" [Page {values[0]}]"
    return f" [Pages {', '.join(str(page) for page in values)}]"


def combine_sections(question: str, sections: list[tuple[CoverageGroup, str]]) -> str:
    del question
    parts = []
    for group, body in sections:
        body = _clean_student_text(body, group.title)
        if not body:
            continue
        if not re.search(r"\[Page", body):
            body = f"{body}{_page_label(group.pages)}"
        parts.append(f"## {group.title}\n\n{body}")
    if not parts:
        return "The provided textbook does not give enough information to answer this fully."
    return "\n\n".join(parts)


def _entity_title(entity: str | None) -> str:
    if not entity:
        return "Explanation"
    return GROUP_TITLE.get(entity) or entity.replace("_", " ").title()


def combine_entity_sections(entity: str | None, sections: list[tuple[CoverageGroup, str]]) -> str:
    title = _entity_title(entity)
    parts = [f"## {title}"]
    used_pages = []
    for group, body in sections:
        body = _clean_student_text(body, group.title)
        body = sanitize_student_text(body)
        # Page-only / blank sections become empty headings — omit them.
        body_core = re.sub(r"\[Pages?\s+[0-9,\s]+\]", "", body or "", flags=re.I).strip()
        if not body_core:
            continue
        if not re.search(r"\[Page", body):
            body = f"{body}{_page_label(group.pages)}"
        parts.append(f"**{group.title}**\n\n{body}")
        used_pages.extend(group.pages or [])
    if len(parts) == 1:
        return "The provided textbook does not give enough information to answer this fully."
    return "\n\n".join(parts)



def _drop_empty_headings(text: str) -> str:
    """Remove markdown section headings that have no real body (page-only or blank)."""
    if not text:
        return text or ""
    blocks = re.split(r"\n\s*\n", text)
    kept: list[str] = []
    page_only = re.compile(r"^\[Pages?\s+[0-9,\s]+\]$", re.I)

    def _is_heading_line(s: str) -> bool:
        s = s.strip()
        return s.startswith("## ") or (s.startswith("**") and s.endswith("**"))

    def _block_has_body(block: str) -> bool:
        for ln in block.splitlines():
            s = ln.strip()
            if not s:
                continue
            if _is_heading_line(s) or page_only.match(s):
                continue
            return True
        return False

    for block in blocks:
        if not block.strip():
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_is_heading_line(ln) or page_only.match(ln) for ln in lines):
            # keep ## title temporarily; drop empty **sections**
            if lines[0].startswith("## "):
                kept.append(block)
            continue
        kept.append(block)

    final: list[str] = []
    for idx, block in enumerate(kept):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if lines and lines[0].startswith("## ") and not _block_has_body(block):
            # keep title only if a later block has body
            if any(_block_has_body(later) for later in kept[idx + 1 :]):
                final.append(block)
            continue
        if lines and _is_heading_line(lines[0]) and not _block_has_body(block):
            continue
        final.append(block)
    return "\n\n".join(final).strip()


def _filter_entity_sentences(text: str, entity: str | None) -> str:
    if not entity or not text:
        return text
    from rag.engine.entity import entity_subject_score

    parts: list[str] = []
    for block in re.split(r"(\n\s*\n)", text):
        if not block.strip() or re.fullmatch(r"\n\s*\n", block):
            parts.append(block)
            continue
        lines: list[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("Source:"):
                lines.append(line)
                continue
            if stripped.startswith("**") and stripped.endswith("**"):
                lines.append(line)
                continue
            prefix = ""
            body = line
            bullet = re.match(r"^(\s*(?:[-*]\s+|\d+\.\s+))", line)
            if bullet:
                prefix = bullet.group(1)
                body = line[len(prefix) :]
            kept: list[str] = []
            for sent in re.split(r"(?<=[.!?])\s+", body):
                sent = sent.strip()
                if not sent:
                    continue
                if re.search(r"\[Pages?\s+", sent, re.I):
                    kept.append(sent)
                    continue
                score, _reason = entity_subject_score(sent, entity)
                if score >= 3:
                    kept.append(sent)
            if kept:
                lines.append(prefix + " ".join(kept))
        parts.append("\n".join(lines))
    return "".join(parts).strip()


def generate_entity_explanation(question: str, chunks: list[dict], entity: str | None) -> dict | None:
    from rag.engine.entity import build_entity_plan, entity_readable
    from rag.engine.pack import detect_entity

    entity = entity or detect_entity(extract_topics(question))
    if not entity:
        return None
    plan = build_entity_plan(question, chunks, entity)
    if not plan:
        return None
    title = _entity_title(entity)
    draft = combine_entity_sections(entity, [(group, entity_readable([group])) for group in plan])
    extra = ""
    if wants_easy_english(question) or re.search(
        r"easy english|simple english|explain simply|class 9 student", question or "", re.I
    ):
        extra = (
            " Write in very simple Class 9 English. Short sentences. "
            "Easy English is only simpler wording; keep every fact from the draft."
        )
    user = (
        f"Student question: {question}\n"
        f"Rewrite the draft explanation of {title} in clear Class 9 English.{extra} "
        "Do not drop facts, names, places, or events that appear in the draft. "
        "Do not add names, dates, or events that are not in the draft. "
        "Do not mention RAG, retrieval, chunks, or page numbers in the prose. "
        "Keep the markdown headings.\n\n"
        f"Draft (textbook-grounded, complete):\n{draft}"
    )
    used_extractive = False
    try:
        raw = complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=900,
            timeout=90,
        )
        text = _clean_student_text((raw or "").strip(), title)
    except (LlmError, TimeoutError, OSError):
        text = ""
    if not text or unsupported_named_items(text, chunks):
        text = draft
        used_extractive = True
    score = coverage_score(text, plan)
    draft_score = coverage_score(draft, plan)
    regenerated = False
    thin = len(text.split()) < max(70, int(len(draft.split()) * 0.55))
    if score["missing"] or thin:
        missing_groups = [group for group in plan if group.key in score["missing"]] or plan
        regen_user = (
            "Rewrite the Class 9 answer so it covers the missing textbook evidence below. "
            "Keep simple English. Use ONLY this evidence plus the current answer. Do not add outside facts.\n\n"
            f"Current answer:\n{text}\n\nMissing evidence:\n{entity_readable(missing_groups)}"
        )
        try:
            extra_raw = complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": regen_user},
                ],
                temperature=0.0,
                max_tokens=700,
                timeout=90,
            )
            extra_text = _clean_student_text((extra_raw or "").strip(), title)
            if extra_text and not unsupported_named_items(extra_text, chunks):
                text = extra_text
                regenerated = True
                score = coverage_score(text, plan)
                thin = len(text.split()) < max(70, int(len(draft.split()) * 0.55))
        except (LlmError, TimeoutError, OSError):
            pass
        if score["missing"] or thin:
            text = draft
            used_extractive = True
            score = draft_score
    text = _filter_entity_sentences(text, entity)
    text = sanitize_student_text(text)
    text = _drop_empty_headings(text)
    if not re.search(r"\[Page", text):
        pages = sorted({page for group in plan if group_covered(text, group) for page in (group.pages or [])})
        if not pages:
            pages = sorted({page for group in plan for page in (group.pages or [])})
        if pages:
            text = f"{text}{_page_label(pages)}"
    return {
        "answer": text,
        "plan": [group.as_public() for group in plan],
        "coverage": score,
        "regenerated": regenerated,
        "fallback_used": used_extractive,
        "section_pages": {group.key: group.pages for group in plan if group_covered(text, group)},
    }


def generate_from_plan(question: str, chunks: list[dict], question_type: str, depth_profile=None, previous_answer: str = "") -> dict:
    from rag.engine.pack import detect_entity

    entity = detect_entity(extract_topics(question))
    if question_type == "EXPLANATION" and entity:
        entity_result = generate_entity_explanation(question, chunks, entity)
        if entity_result:
            return entity_result
    plan = filter_plan(question, build_coverage_plan(chunks))
    if question_type == "EXPLANATION" and len(plan) <= 1:
        plan = plan or [
            CoverageGroup(
                key="topic",
                title="Explanation",
                pages=sorted({p for item in chunks if (p := _page(item)) is not None}),
                chunks=chunks,
                markers=[],
            )
        ]
    rich = question_type == "EXPLANATION" and len(plan) <= 2
    if depth_profile is not None:
        rich = bool(getattr(depth_profile, "full_facts", False)) or rich
        if getattr(depth_profile, "coverage", "") == "high":
            rich = True
    sections: list[tuple[CoverageGroup, str]] = []
    used_extractive = False
    for group in plan:
        body = generate_section(question, group, full_facts=rich)
        if body == readable_extract(group.chunks, limit=8 if rich else 3):
            used_extractive = True
        sections.append((group, body))
    answer = combine_sections(question, sections)
    score = coverage_score(answer, plan)
    regenerated = False
    if score["missing"] and question_type in {"BROAD_TOPIC", "EXPLANATION"}:
        regenerated = True
        by_key = {group.key: group for group in plan}
        rebuilt = []
        for group, body in sections:
            if group.key in score["missing"]:
                extra = generate_section(question, group, strict=True, full_facts=rich)
                if not group_covered(extra, group):
                    extra = readable_extract(group.chunks) or extra
                    used_extractive = True
                rebuilt.append((group, extra))
            else:
                rebuilt.append((group, body))
        sections = rebuilt
        answer = combine_sections(question, sections)
        score = coverage_score(answer, plan)
    if score["grade"] == "FAIL":
        answer = combine_sections(
            question,
            [(group, readable_extract(group.chunks) or body) for group, body in sections],
        )
        used_extractive = True
        score = coverage_score(answer, plan)
        score["grade"] = score["grade"] if score["generated"] else "FAIL"
    if previous_answer and depth_profile is not None and getattr(depth_profile, "prefer_unused", False):
        from rag.engine.depth import filter_new_sentences

        filtered = filter_new_sentences(answer, previous_answer)
        if filtered and len(filtered.split()) >= 35:
            answer = filtered
            score = coverage_score(answer, plan)
    return {
        "answer": answer,
        "plan": [group.as_public() for group in plan],
        "coverage": score,
        "regenerated": regenerated,
        "fallback_used": used_extractive and score["grade"] != "GOOD",
        "section_pages": {group.key: group.pages for group, _body in sections if group_covered(answer, group)},
    }

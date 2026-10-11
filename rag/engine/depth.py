"""Generic answer-depth controller. Cue-based — never hardcodes people."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.engine.classify import (
    DETAILED_RE,
    ECONTENT_RE,
    EXAM_RE,
    EXPLAIN_RE,
    SHORT_FACT_RE,
    SUMMARY_RE,
    _folded,
)

# Intent depth cues (generic patterns only).
DEFINE_RE = re.compile(
    r"\b(what (is|are|was|were)|define|definition of|meaning of|who (is|was|are|were))\b",
    re.I,
)
LIST_RE = re.compile(
    r"\b(list|name (the|some|all)|what are the|enumerate|key points|important points|"
    r"main (events|points|features)|bullet|achievements?|accomplishments?|places?|chronolog\w*)\b",
    re.I,
)
COMPARE_RE = re.compile(
    r"\b(compare|difference between|differences between|vs\.?|versus|contrast|"
    r"similarit(?:y|ies)|how (?:did|does|do) .+ differ)\b",
    re.I,
)
WHY_RE = re.compile(r"^\s*why\b|\bwhy (did|was|were|is|are|do|does|did)\b", re.I)
HOW_RE = re.compile(
    r"^\s*how\b|\bhow (did|was|were|is|are|do|does|to)\b|\bin what way\b",
    re.I,
)
MORE_CUE_RE = re.compile(
    r"^(more|continue|go on|next|another one|anything else|tell me more|"
    r"give me more|more details|go deeper)\??$|"
    r"\b(tell me more|more details|go deeper|what else|continue)\b",
    re.I,
)
DETAIL_CUE_RE = re.compile(
    r"\b(in detail|detailed|everything about|full explanation|all about|"
    r"teach me|complete (explanation|overview)|explain fully)\b",
    re.I,
)
MEDIUM_CUE_RE = re.compile(
    r"\b(explain|describe|tell me about|i want to know|i want to learn|"
    r"teach me about|overview)\b",
    re.I,
)
SHORT_CUE_RE = re.compile(
    r"^\s*(who|what|when|where)\b.{0,60}$|"
    r"\b(briefly|in brief|short answer|one sentence|quickly)\b",
    re.I,
)


@dataclass(frozen=True)
class DepthProfile:
    """Controls structure and coverage aggressiveness — not invented facts."""

    depth: str  # short|medium|detail|more|exam|why|how|compare|list|define
    mode: str  # NORMAL|DETAILED|ECONTENT
    question_type_hint: str | None
    top_k: int
    full_facts: bool
    max_tokens: int
    structure: str  # direct|sections|bullets|compare|list|causal
    coverage: str  # low|medium|high
    prefer_unused: bool
    use_plan: bool
    extract_limit: int
    extract_words: int

    def as_public(self) -> dict:
        return {
            "depth": self.depth,
            "mode": self.mode,
            "structure": self.structure,
            "coverage": self.coverage,
            "top_k": self.top_k,
            "full_facts": self.full_facts,
            "prefer_unused": self.prefer_unused,
        }


def classify_depth(question: str, *, more_followup: bool = False) -> DepthProfile:
    """Map question cues to depth/structure/coverage. No person hardcoding."""
    text = (question or "").strip()
    folded = _folded(text)

    if ECONTENT_RE.search(text):
        return DepthProfile(
            depth="detail",
            mode="ECONTENT",
            question_type_hint="EXPLANATION",
            top_k=16,
            full_facts=True,
            max_tokens=1200,
            structure="sections",
            coverage="high",
            prefer_unused=False,
            use_plan=True,
            extract_limit=10,
            extract_words=90,
        )

    if more_followup or MORE_CUE_RE.match(folded) or (
        MORE_CUE_RE.search(text) and len(text.split()) <= 8
    ):
        return DepthProfile(
            depth="more",
            mode="DETAILED",
            question_type_hint="EXPLANATION",
            top_k=16,
            full_facts=True,
            max_tokens=900,
            structure="sections",
            coverage="high",
            prefer_unused=True,
            use_plan=True,
            extract_limit=10,
            extract_words=90,
        )

    if EXAM_RE.search(text):
        return DepthProfile(
            depth="exam",
            mode="DETAILED",
            question_type_hint="EXAM",
            top_k=14,
            full_facts=True,
            max_tokens=900,
            structure="list",
            coverage="high",
            prefer_unused=False,
            use_plan=False,
            extract_limit=8,
            extract_words=70,
        )

    if COMPARE_RE.search(text):
        return DepthProfile(
            depth="compare",
            mode="DETAILED",
            question_type_hint="EXPLANATION",
            top_k=16,
            full_facts=True,
            max_tokens=1100,
            structure="compare",
            coverage="high",
            prefer_unused=False,
            use_plan=True,
            extract_limit=10,
            extract_words=90,
        )

    if LIST_RE.search(text) or SUMMARY_RE.search(text):
        return DepthProfile(
            depth="list",
            mode="DETAILED",
            question_type_hint="EXPLANATION",
            top_k=12,
            full_facts=True,
            max_tokens=800,
            structure="list",
            coverage="high",
            prefer_unused=False,
            use_plan=True,
            extract_limit=8,
            extract_words=70,
        )

    if WHY_RE.search(text):
        return DepthProfile(
            depth="why",
            mode="DETAILED",
            question_type_hint="EXPLANATION",
            top_k=12,
            full_facts=True,
            max_tokens=800,
            structure="causal",
            coverage="medium",
            prefer_unused=False,
            use_plan=True,
            extract_limit=8,
            extract_words=80,
        )

    if HOW_RE.search(text) and not SHORT_FACT_RE.match(text):
        return DepthProfile(
            depth="how",
            mode="DETAILED",
            question_type_hint="EXPLANATION",
            top_k=12,
            full_facts=True,
            max_tokens=900,
            structure="sections",
            coverage="high",
            prefer_unused=False,
            use_plan=True,
            extract_limit=8,
            extract_words=85,
        )

    if DETAIL_CUE_RE.search(text) or DETAILED_RE.search(text):
        return DepthProfile(
            depth="detail",
            mode="DETAILED",
            question_type_hint=None,  # let classify_question_type decide BROAD vs EXPLANATION
            top_k=16,
            full_facts=True,
            max_tokens=1200,
            structure="sections",
            coverage="high",
            prefer_unused=False,
            use_plan=True,
            extract_limit=10,
            extract_words=90,
        )

    if DEFINE_RE.search(text) and len(text.split()) <= 14:
        return DepthProfile(
            depth="define",
            mode="NORMAL",
            question_type_hint="DIRECT",
            top_k=10,
            full_facts=False,
            max_tokens=500,
            structure="direct",
            coverage="low",
            prefer_unused=False,
            use_plan=False,
            extract_limit=4,
            extract_words=55,
        )

    if SHORT_CUE_RE.search(text) or (
        SHORT_FACT_RE.match(text) and len(text.split()) <= 10 and not EXPLAIN_RE.search(text)
    ):
        return DepthProfile(
            depth="short",
            mode="NORMAL",
            question_type_hint="DIRECT",
            top_k=8,
            full_facts=False,
            max_tokens=450,
            structure="direct",
            coverage="low",
            prefer_unused=False,
            use_plan=False,
            extract_limit=3,
            extract_words=50,
        )

    if MEDIUM_CUE_RE.search(text) or EXPLAIN_RE.search(text):
        return DepthProfile(
            depth="medium",
            mode="DETAILED",
            question_type_hint="EXPLANATION",
            top_k=14,
            full_facts=True,
            max_tokens=1000,
            structure="sections",
            coverage="high",
            prefer_unused=False,
            use_plan=True,
            extract_limit=8,
            extract_words=85,
        )

    # Default: medium-normal — enough evidence, no filler.
    return DepthProfile(
        depth="medium",
        mode="NORMAL",
        question_type_hint=None,
        top_k=10,
        full_facts=False,
        max_tokens=700,
        structure="direct",
        coverage="medium",
        prefer_unused=False,
        use_plan=False,
        extract_limit=5,
        extract_words=70,
    )



def _explicit_naming_reason(rows: list[str], aliases: list[str]) -> bool:
    """A 'hence/therefore he was called' sentence states the reason in the sentence before it."""
    from rag.engine.classify import _alias_present

    link = re.compile(r"\b(?:hence|therefore|thus)\b", re.I)
    naming = re.compile(r"\b(?:called|known as|named)\b", re.I)
    for text in rows:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        for index, sentence in enumerate(sentences):
            if not naming.search(sentence):
                continue
            previous = sentences[index - 1] if index else ""
            window = f"{previous} {sentence}".lower()
            if aliases and not any(_alias_present(window, alias) for alias in aliases):
                continue
            if link.search(sentence) or link.search(previous):
                return True
    return False


MOTIVE_CUES = (
    "because",
    "intention",
    "in order to",
    "so that",
    "reason",
    "aimed to",
    "wanted to",
    "with the intention",
    "with an intention",
    "to assist",
    "to help",
    "to stop",
    "to establish",
    "in memory of",
    "in honour of",
    "in honor of",
)



def evidence_states_motive(
    chunks: list[dict] | None,
    entity: str | None = None,
    question: str | None = None,
) -> bool:
    """True when evidence states an explicit motive for the asked entity/action.

    When a question is provided, only sentences that mention the entity and
    overlap the question's content tokens are considered (avoids treating a
    different action's purpose as the why-answer).
    """
    rows = [item.get("text") or "" for item in (chunks or []) if item.get("text")]
    if not rows:
        return False
    from rag.engine.classify import TOPIC_ALIASES
    from rag.engine.topic_map import RULER_KEYS
    from rag.engine.evidence import content_tokens

    aliases = []
    if entity:
        aliases = [a for a in TOPIC_ALIASES.get(entity, (entity,)) if isinstance(a, str) and a.isascii()]
    if _explicit_naming_reason(rows, aliases):
        return True
    blob = " ".join(rows).lower()
    q_tokens = content_tokens(question or "")
    # Drop ultra-generic tokens that appear in every Maratha passage.
    q_tokens -= {"mughal", "maratha", "kingdom", "empire", "peshwa"}

    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    candidates: list[str] = []
    for text in rows:
        for sent in _sentences(text):
            low = sent.lower()
            if aliases and not any(alias in low for alias in aliases):
                continue
            if q_tokens:
                sent_tokens = content_tokens(sent)
                if not (q_tokens & sent_tokens):
                    continue
            candidates.append(low)
    if aliases and q_tokens and not candidates:
        # Fall back to entity sentences if action overlap was too strict.
        for text in rows:
            for sent in _sentences(text):
                low = sent.lower()
                if any(alias in low for alias in aliases):
                    candidates.append(low)
    if not candidates:
        candidates = [blob]

    other_aliases = []
    for key in RULER_KEYS:
        if key == entity:
            continue
        other_aliases.extend(
            a for a in TOPIC_ALIASES.get(key, ()) if isinstance(a, str) and a.isascii() and len(a) >= 4
        )
    other_aliases.sort(key=len, reverse=True)

    for low in candidates:
        if entity and aliases:
            for alias in aliases:
                for match in re.finditer(re.escape(alias), low):
                    after = low[match.end() : match.end() + 140]
                    for other in other_aliases:
                        cut = after.find(other)
                        if cut >= 0:
                            after = after[:cut]
                            break
                    before = low[max(0, match.start() - 48) : match.start()]
                    if any(cue in after or cue in before for cue in MOTIVE_CUES):
                        return True
        elif any(cue in low for cue in MOTIVE_CUES):
            return True
    return False


def depth_prompt_extra(profile: DepthProfile, chunks: list[dict] | None = None, entity: str | None = None, question: str | None = None) -> str:
    """Extra LLM instructions by depth for the textbook part (supplementary text is labelled separately)."""
    bits = []
    if profile.depth == "short":
        bits.append(
            "Answer briefly with the direct textbook fact first. "
            "Add at most one short supporting sentence from the evidence. No filler."
        )
    elif profile.depth == "define":
        bits.append(
            "Give a clear definition from the textbook in 1–3 sentences. No invented biography."
        )
    elif profile.depth == "list":
        bits.append(
            "Use a short intro then bullet points drawn only from the evidence. "
            "Do not invent items to fill the list."
        )
    elif profile.depth == "compare":
        bits.append(
            "Write a focused comparison from the textbook passages. "
            "You may combine facts about each side. "
            "Use only points the passages give. If the textbook does not give a point "
            "for one side, say so in one short sentence instead of adding outside facts."
        )
    elif profile.depth == "why":
        bits.append(
            "Answer why or how by combining roles, duties, events, and consequences in the passages. "
            "Do not require the passages to contain the word because. "
            "Do not say the textbook lacks a reason when the passages already show the role or result. "
            "Stay on the person or event asked about."
        )
    elif profile.depth == "how":
        bits.append(
            "Explain the process or method using only steps/facts in the evidence."
        )
    elif profile.depth == "more":
        bits.append(
            "Add NEW textbook points not already covered. Prefer unused evidence. "
            "Do not repeat the previous answer verbatim. If no new evidence remains, do not stop: the system adds a labelled additional explanation."
        )
    elif profile.depth == "detail":
        bits.append(
            "Use ALL relevant primary evidence. Cover every supported section. "
            "No filler phrases. Do not invent facts outside the evidence."
        )
    elif profile.depth == "exam":
        bits.append("Write textbook-grounded practice items only. Do not invent facts.")
    else:
        bits.append(
            "Use every relevant fact from the evidence that answers the question. No filler."
        )
    if profile.structure == "sections":
        bits.append(
            "Use short markdown headings only when the evidence supports distinct sections."
        )
    return " ".join(bits)


def prefer_unused_chunks(chunks: list[dict], used_ids: list[str] | set[str] | None) -> list[dict]:
    """Reorder pack so unused chunks come first; keep used ones as fallback."""
    if not used_ids:
        return list(chunks)
    used = {str(x) for x in used_ids if x}
    fresh = [c for c in chunks if str(c.get("chunk_id") or "") not in used]
    old = [c for c in chunks if str(c.get("chunk_id") or "") in used]
    if fresh:
        return fresh + old
    return list(chunks)


def filter_new_sentences(text: str, previous_answer: str) -> str:
    """Drop sentences that already appeared in the previous assistant turn."""
    if not previous_answer or not text:
        return text
    prev_keys = set()
    for sent in re.split(r"(?<=[.!?])\s+", previous_answer):
        key = re.sub(r"[^a-z0-9]+", "", sent.lower())[:60]
        if len(key) >= 24:
            prev_keys.add(key)
    if not prev_keys:
        return text
    kept_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue
        if stripped.startswith("#") or stripped.startswith("Source:"):
            kept_lines.append(line)
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            kept_lines.append(line)
            continue
        prefix = ""
        body = line
        bullet = re.match(r"^(\s*(?:[-*]\s+|\d+\.\s+))", line)
        if bullet:
            prefix = bullet.group(1)
            body = line[len(prefix) :]
        new_sents = []
        for sent in re.split(r"(?<=[.!?])\s+", body):
            sent = sent.strip()
            if not sent:
                continue
            key = re.sub(r"[^a-z0-9]+", "", sent.lower())[:60]
            if key and key in prev_keys:
                continue
            new_sents.append(sent)
        if new_sents:
            kept_lines.append(prefix + " ".join(new_sents))
    result = "\n".join(kept_lines).strip()
    # Drop empty headings left behind.
    result = re.sub(r"(?m)^(#{1,3}\s+[^\n]+)\n+(?=#{1,3}\s|\Z)", "", result)
    return result.strip() or text

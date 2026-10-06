"""Lightweight checks on the LLM answer. One optional regeneration only."""

from __future__ import annotations

import re

from rag.engine.evidence import content_tokens
from rag.engine.normalize import looks_kannada
from rag.prompts.tutor import KANNADA_SAFE_FALLBACK, refusal_text

LEAK_MARKERS = (
    "wikipedia",
    "as an ai",
    "language model",
    "vector database",
    "embedding",
    "chroma",
    "system prompt",
    "ollama",
)

PRIMARY_HEADING = re.compile(r"^##\s*From your Class 9 textbook\s*$", re.I | re.M)
EXTRA_HEADING = re.compile(r"^##\s*Additional school-book detail\s*$", re.I | re.M)


def is_refusal(answer: str, language: str) -> bool:
    text = (answer or "").strip()
    lowered = text.lower()
    if "not available in the provided textbook" in lowered or "not available in the textbook" in lowered:
        return True
    if "kannada textbook support is currently unavailable" in lowered:
        return True
    expected = refusal_text(language)
    return expected in text or "ಲಭ್ಯವಿಲ್ಲ" in text


def is_kannada_safe_fallback(answer: str) -> bool:
    return KANNADA_SAFE_FALLBACK in (answer or "")


def extract_mentioned_pages(answer: str) -> set[int]:
    pages = set()
    for match in re.finditer(r"(?:page|pages)\s+(\d+)(?:\s*[–-]\s*(\d+))?", answer, re.I):
        start = int(match.group(1))
        pages.add(start)
        if match.group(2):
            pages.add(int(match.group(2)))
    return pages


def split_detailed_sections(answer: str) -> tuple[str, str] | None:
    text = (answer or "").strip()
    if not PRIMARY_HEADING.search(text) or not EXTRA_HEADING.search(text):
        return None
    primary = PRIMARY_HEADING.split(text, maxsplit=1)
    if len(primary) < 2:
        return None
    rest = primary[1]
    extra_split = EXTRA_HEADING.split(rest, maxsplit=1)
    if len(extra_split) < 2:
        return None
    return extra_split[0].strip(), extra_split[1].strip()


def validate_answer(
    answer: str,
    language: str,
    evidence: list[dict],
    grounded_expected: bool,
    mode: str = "NORMAL",
    primary: list[dict] | None = None,
    supplement: list[dict] | None = None,
) -> tuple[bool, str]:
    text = (answer or "").strip()
    if not text:
        return False, "empty_answer"
    lowered = text.lower()
    if any(marker in lowered for marker in LEAK_MARKERS):
        return False, "internal_or_external_leak"
    if not grounded_expected:
        return True, "ok_ungrounded"
    if is_refusal(text, language):
        return False, "model_refused_despite_evidence"
    if language == "kn":
        kn_ok, kn_reason = validate_kannada_output(text)
        if not kn_ok:
            return False, kn_reason
    allowed_pages = {
        int(item.get("textbook_page_number") or item.get("printed_page_number"))
        for item in evidence
        if item.get("textbook_page_number") is not None or item.get("printed_page_number") is not None
    }
    mentioned = extract_mentioned_pages(text)
    if mentioned and not mentioned.issubset(allowed_pages):
        return False, "invented_page_citation"
    evidence_blob = " ".join(item.get("text") or "" for item in evidence).lower()
    extra_terms = (
        "plassey",
        "gdp",
        "prime minister",
        "wikipedia",
        "visionias",
        "world war",
        "ronaldo",
        "cristiano",
        "chatgpt",
        "openai",
    )
    for term in extra_terms:
        if term in lowered and term not in evidence_blob:
            return False, f"unsupported_term:{term}"
    if "@ktbs" in lowered:
        return False, "ocr_artifact"
    if mode == "DETAILED" and supplement:
        ok, reason = validate_detailed_separation(text, primary or [], supplement)
        if not ok:
            return False, reason
    bad = unsupported_named_items(text, evidence)
    if bad:
        return False, "unsupported_claim:" + ",".join(bad[:6])
    return True, "ok"


CLAIM_SKIP = {
    "class",
    "karnataka",
    "history",
    "historybot",
    "textbook",
    "source",
    "introduction",
    "main",
    "points",
    "detailed",
    "explanation",
    "important",
    "people",
    "terms",
    "events",
    "key",
    "remember",
    "simple",
    "words",
    "board",
    "student",
    "question",
    "english",
    "section",
    "chapter",
    "primary",
    "evidence",
    "india",
    "indian",
    "social",
    "science",
    "state",
    "society",
    "after",
    "before",
    "during",
    "this",
    "that",
    "they",
    "their",
    "then",
    "from",
    "your",
    "king",
    "kings",
    "kingdom",
    "empire",
    "army",
    "north",
    "south",
    "east",
    "west",
    "however",
    "therefore",
    "although",
    "because",
    "explain",
    "according",
    "additionally",
    "furthermore",
    "definition",
    "note",
    "summary",
    "moreover",
    "besides",
    "finally",
    "firstly",
    "secondly",
    "using",
    "based",
    "under",
    "over",
    "between",
    "among",
    "through",
    "without",
    "within",
    "later",
    "early",
    "several",
    "various",
    "another",
    "other",
    "many",
    "some",
    "such",
    "most",
    "more",
    "also",
    "only",
    "even",
    "still",
    "both",
    "each",
    "these",
    "those",
    "there",
    "where",
    "which",
    "while",
    "what",
    "when",
    "who",
    "whom",
    "whose",
    "expansion",
    "administration",
    "system",
    "policy",
    "period",
    "order",
    "religion",
    "religious",
    "tolerance",
    "approach",
    "towards",
    "different",
    "religions",
    "page",
    "pages",
}


def _norm_claim(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _supported_in_evidence(phrase: str, evidence_norm: str, evidence_lower: str) -> bool:
    compact = _norm_claim(phrase)
    if len(compact) < 4:
        return True
    if compact in evidence_norm:
        return True
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", phrase.lower())
        if token not in CLAIM_SKIP and len(token) > 2
    ]
    if not tokens:
        return True
    return all(token in evidence_lower for token in tokens)


def unsupported_named_items(answer: str, evidence: list[dict]) -> list[str]:
    """Reject new people/places/years/orgs. Allows paraphrase of supported names."""
    blob = " ".join(item.get("text") or "" for item in evidence)
    evidence_lower = blob.lower()
    evidence_norm = _norm_claim(blob)
    body_lines = []
    for line in (answer or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        body_lines.append(line)
    text = "\n".join(body_lines)
    text = re.sub(r"\[Pages?\s+[0-9,\s]+\]", " ", text)
    flagged: list[str] = []

    def add(item: str) -> None:
        lowered = item.strip()
        if not lowered or lowered in flagged:
            return
        if any(marker in lowered.lower() for marker in ("textbook", "karnataka", "historybot", "class 9")):
            return
        if not _supported_in_evidence(lowered, evidence_norm, evidence_lower):
            flagged.append(lowered)

    for match in re.finditer(r"\b([A-Z][a-zA-Z']+(?:[\s-][A-Z][a-zA-Z']+){1,3})\b", text):
        add(match.group(1))
    for match in re.finditer(r"\b([A-Z][a-z]{4,})\b", text):
        add(match.group(1))
    for match in re.finditer(r"\b([A-Z]{3,})\b", text):
        add(match.group(1))
    for match in re.finditer(r"\b(1[0-9]{3}|20[0-2][0-9])\b", text):
        year = match.group(1)
        if year not in blob and year not in evidence_lower:
            add(year)
    return flagged


def validate_kannada_output(text: str) -> tuple[bool, str]:
    if not looks_kannada(text):
        return False, "kannada_script_missing"
    if _kannada_loops(text):
        return False, "kannada_repetition"
    letters = re.findall(r"[A-Za-z\u0C80-\u0CFF]", text)
    kn_letters = [ch for ch in letters if "\u0C80" <= ch <= "\u0CFF"]
    if letters and (len(kn_letters) / len(letters)) < 0.55:
        return False, "kannada_too_much_english"
    kn_tokens = re.findall(r"[\u0C80-\u0CFF]+", text)
    if len(kn_tokens) < 6:
        return False, "kannada_too_short"
    unique = set(kn_tokens)
    if len(unique) < 5:
        return False, "kannada_low_variety"
    return True, "ok"


def validate_detailed_separation(answer: str, primary: list[dict], supplement: list[dict]) -> tuple[bool, str]:
    parts = split_detailed_sections(answer)
    if not parts:
        return False, "detailed_headings_missing"
    primary_section, extra_section = parts
    if not primary_section or not extra_section:
        return False, "detailed_section_empty"
    primary_tokens = content_tokens(" ".join(item.get("text") or "" for item in primary))
    supp_tokens = content_tokens(" ".join(item.get("text") or "" for item in supplement))
    supp_unique = supp_tokens - primary_tokens
    leaked = content_tokens(primary_section) & supp_unique
    if len(leaked) >= 3:
        return False, "supplement_facts_in_primary_section"
    return True, "ok"


def _kannada_loops(text: str) -> bool:
    tokens = re.findall(r"[\u0C80-\u0CFF]+", text or "")
    if len(tokens) < 8:
        return False
    phrase = " ".join(tokens[:4])
    rest = " ".join(tokens[4:])
    if phrase and rest.count(phrase) >= 2:
        return True
    for token in set(tokens):
        if len(token) >= 4 and tokens.count(token) >= 6:
            return True
    return False


# --- Post-generation evidence support check ------------------------------------------
SUPPORT_FUNCTION = {
    "with", "from", "that", "this", "were", "have", "been", "their", "there", "which", "when",
    "what", "into", "than", "then", "they", "them", "also", "such", "only", "after", "before",
    "during", "over", "under", "about", "against", "between", "many", "much", "very", "more",
    "most", "some", "other", "each", "both", "would", "could", "should", "will", "shall", "being",
    "where", "while", "these", "those", "whom", "whose", "because", "through", "upon", "onto",
    "himself", "herself", "itself", "said", "made", "make", "including", "well",
}
SUPPORT_META = {
    "according", "evidence", "textbook", "provided", "mention", "mentions", "mentioned",
    "information", "known", "important", "prescribed", "class", "student", "answer", "details",
    "detail", "fact", "facts", "chapter", "states", "stated", "however", "although", "later",
    "describes", "described", "notes", "noted", "given", "text", "passage",
}
META_LEAD_RE = re.compile(
    r"^(?:according to (?:the )?(?:provided |given )?(?:evidence|textbook|text)|"
    r"(?:the )?(?:provided |given )?(?:evidence|textbook) (?:says|states|mentions|tells us)(?: that)?|"
    r"from the (?:evidence|textbook))\s*,?\s*",
    re.I,
)
COPULA_RE = re.compile(
    r"\b(?:was|is)\s+(?:a|an|the)\s+(?P<pred>[A-Za-z][A-Za-z\-]*(?:\s+[A-Za-z][A-Za-z\-]*){0,5}?)"
    r"(?=\s+(?:who|which|that|of|in|from|at|with|and|whose|for|to|during|under)\b|[,.;:!?]|$)",
    re.I,
)
COPULA_WHO_RE = re.compile(r"\b(?:was|is)\s+(?:a|an|the)\s+[^.;:]*?\s+who\s+", re.I)
# Evaluative characterisations the LLM likes to add ("a skilled military leader", "key areas").
EVALUATIVE = (
    "skilled", "talented", "famous", "great", "greatest", "powerful", "important", "significant", "brave",
    "effective", "unique", "notable", "prominent", "renowned", "strong", "successful", "key", "major",
    "remarkable", "legendary", "mighty", "efficient", "capable", "wise", "ambitious", "influential",
    "celebrated", "excellent", "outstanding", "visionary", "fearless", "courageous", "able",
)


def _support_stems(text: str) -> set[str]:
    words = re.findall(r"[a-z]{4,}", (text or "").lower())
    return {
        word[:6]
        for word in words
        if word not in SUPPORT_FUNCTION and word not in SUPPORT_META and word not in content_tokens_stop()
    }


def content_tokens_stop() -> set[str]:
    from rag.engine.evidence import STOPWORDS

    return STOPWORDS


def _evidence_sentences(evidence: list[dict]) -> list[str]:
    out = []
    for item in evidence or []:
        text = re.sub(r"@?KTBS\s*NOT\s+TO\s+BE\s+REPUBLISHED|@KTBS", " ", item.get("text") or "", flags=re.I)
        for sent in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
            if len(sent.split()) >= 5:
                out.append(sent.strip())
    return out


# --- Relation-direction check (generic): agent/relation/patient must not contradict the evidence -------
REL_NAME_RE = re.compile(r"\b[A-Z][\w'\u2019\-]*(?:\s+(?:of\s+|ul\s+|ud\s+)?(?:[A-Z][\w'\u2019\-]*|I{1,3}\b))*")
REL_SKIP = {"he", "she", "his", "her", "as", "when", "after", "but", "however", "although", "also", "later", "over", "due", "since"}
REL_GENERIC = {"battle", "first", "second", "third", "sultan", "king", "kingdom", "india", "dynasty", "empire"}
REL_SPECS = (  # (pattern, relation or None = the verb, left side is the agent, exclusive kind)
    (r"\b(?:was|were|is|had been)\s+(?:\w+\s+)?(defeated|conquered|captured|killed|succeeded|assisted|attacked)\s+by\b", None, False, None),
    (r"\blost\s+to\b", "defeated", False, None),
    (r"\b(defeated|conquered|captured|killed|succeeded|assisted|attacked)\b(?!\s+by)", None, True, None),
    (r"\bfather\s+of\b", "parent", True, "father"),
    (r"\bmother\s+of\b", "parent", True, "mother"),
    (r"\b(?:son|daughter)\s+of\b", "parent", False, None),
    (r"\b(?:(?:was|is|became|were)\s+(?:the|a)|[Aa]s\s+(?:the|a))\s+(?:\w+\s+)?(?:king|queen|ruler|sultan|emperor)\s+of\b", "head", True, "head"),
)
REL_POSS_RE = re.compile(r"(?<!of )\b((?i:his|her)|[A-Z][\w\-]+(?:'s|\u2019s))\s+(?:eldest\s+|elder\s+|younger\s+|second\s+)?"
                         r"(father|mother|son|daughter)\s*,?\s+(?=[A-Z])")


def _rel_names(text: str) -> list[tuple[int, int, str]]:
    out = []
    for m in REL_NAME_RE.finditer(text or ""):
        words = m.group(0).split()
        while words and (words[0].lower() in REL_SKIP or words[0].lower() in content_tokens_stop()):
            words.pop(0)
        if words:
            out.append((m.end() - len(" ".join(words)), m.end(), " ".join(words)))
    return out


def _rel_key(name: str) -> str:
    from rag.engine.entity import _person_spans

    spans = _person_spans(name)
    return spans[0][2] if spans else name.lower()


def _rel_same(a: str, b: str) -> bool:
    words = lambda s: {w for w in re.findall(r"[a-z]{4,}", s) if w not in REL_GENERIC}
    return a == b or bool(words(a) & words(b))


def relation_triples(sentence: str, current: str | None) -> list[tuple[str, str, str, str | None]]:
    """(agent, relation, patient, exclusive kind) from one sentence; pronoun subjects resolve to `current`."""
    from rag.engine.entity import _resolve_subject

    names = _rel_names(sentence)
    subj = _resolve_subject(sentence, current)[0]
    if subj == "OTHER":
        subj = _rel_key(names[0][2]) if names else None
    out = []
    for m in REL_POSS_RE.finditer(sentence):
        after = [n for n in names if n[0] >= m.end()][:1]
        owner = _rel_key(m.group(1)[:-2]) if m.group(1)[0].isupper() and m.group(1).lower() not in ("his", "her") else (subj or current)
        if not after or not owner or _rel_key(after[0][2]) == owner:
            continue
        kin = _rel_key(after[0][2])
        out.append((kin, "parent", owner, m.group(2)) if m.group(2) in ("father", "mother") else (owner, "parent", kin, None))
    for pattern, rel, left_agent, kind in REL_SPECS:
        for m in re.finditer(pattern, sentence):
            before = [n for n in names if n[1] <= m.start()]
            gap = sentence[before[-1][1] : m.start()] if before else "x"
            appositive = re.fullmatch(r"\s*,?\s*(?:(?:was|is|became)\s+)?(?:the\s+)?(?:(?!and\b|or\b)\w+\s+)?", gap)
            left = _rel_key(before[-1][2]) if appositive else (subj or current)
            window = re.split(r"[,;.]|\s+and\s+(?=[a-z])", sentence[m.end() :], maxsplit=1)[0]
            objs = {_rel_key(n[2]) for n in _rel_names(window)}
            if not objs and re.match(r"\s*(?:that|this|the same)\s+\w+", window):
                prior = [n for n in before if _rel_key(n[2]) != left]
                objs = {_rel_key(prior[-1][2])} if prior else set()
            for obj in objs if left else ():
                out.append((left, rel or m.group(1), obj, kind) if left_agent else (obj, rel or m.group(1), left, kind))
    return out


def _relation_evidence(ev_sents: list[str], focus: str | None) -> list[tuple[str, str, str, str | None]]:
    from rag.engine.entity import _resolve_subject

    out, current = [], focus
    for sent in ev_sents:
        out.extend(relation_triples(sent, current))
        subj = _resolve_subject(sent, current)[0]
        current = subj if subj and subj != "OTHER" else current
    return out


def relation_conflict(sentence: str, ev_triples: list, focus: str | None) -> str | None:
    """Reason when a relation is reversed in the evidence, or a father/mother/ruler relation names a different party."""
    for agent, rel, obj, kind in relation_triples(sentence, focus):
        same = [t for t in ev_triples if t[1] == rel]
        if any(_rel_same(agent, a) and _rel_same(obj, o) for a, _r, o, _k in same):
            continue
        if any(_rel_same(obj, a) and _rel_same(agent, o) for a, _r, o, _k in same):
            return f"reversed {rel}: {agent} -> {obj}"
        if kind and any(k == kind and _rel_same(obj, o) for _a, _r, o, k in same):
            return f"wrong agent for {kind}: {agent} -> {obj}"
        if kind == "head" and any(k == kind and _rel_same(agent, a) for a, _r, _o, k in same):
            return f"wrong object for {kind}: {agent} -> {obj}"
    return None


def enforce_evidence_support(answer: str, evidence: list[dict], title: str | None = None) -> str:
    """Rewrite or drop answer sentences whose content is not supported by the given evidence."""
    if not answer or not evidence:
        return answer
    ev_text = " ".join(item.get("text") or "" for item in evidence)
    ev_stems = _support_stems(ev_text)
    ev_nums = set(re.findall(r"\b\d+\b", ev_text))
    ev_sents = _evidence_sentences(evidence)
    used: set[str] = set()
    from rag.engine.entity import _person_spans, _resolve_subject

    focus_keys = {key for (_a, _b, key) in _person_spans(title or "")}
    focus = next(iter(focus_keys)) if len(focus_keys) == 1 else None
    ev_triples = _relation_evidence(ev_sents, focus)

    def replacement(sentence: str) -> str | None:
        stems = _support_stems(sentence)
        whole_stems = _support_stems(answer.replace(sentence, " "))
        best, best_score = None, 0
        for cand in ev_sents:
            if not cand[:1].isupper():
                continue
            score = len(stems & _support_stems(cand))
            if score > best_score:
                best, best_score = cand, score
        if not best or best_score < 2 or best in used:
            return None
        cand_stems = _support_stems(best)
        if cand_stems and len(cand_stems & whole_stems) >= 0.8 * len(cand_stems):
            return None
        used.add(best)
        if title:
            best = re.sub(r"^(?:He|She)\b", title, best)
        return best

    def fix(sentence: str) -> str | None:
        s = re.sub(r"^(?:Definition|Note|Summary|In short|Answer)\s*:\s*", "", sentence.strip(), flags=re.I)
        s = META_LEAD_RE.sub("", s)
        if not s:
            return None
        if re.search(r"\b(?:textbook|evidence)\b.*\b(?:does not|doesn't|do not|did not|no)\b", s, re.I):
            # honest limitation note: not a claim; redundant (and prompt-echoing) inside a person answer
            return None if focus else s
        s = s[0].upper() + s[1:]
        for word in EVALUATIVE:
            if re.search(rf"\b{word}\b", s, re.I) and not re.search(rf"\b{word}\b", ev_text, re.I):
                s = re.sub(rf"\s*\b{word}\b(?:\s+and\b)?", "", s, flags=re.I).strip()
                s = re.sub(r"\b([Aa])n\s+(?=[^aeiouAEIOU\W])", r"\1 ", s)
                s = re.sub(r"\b([Aa])\s+(?=[aeiouAEIOU])", r"\1n ", s)
                s = re.sub(r"\s+,", ",", s)
        if not s:
            return None
        s = s[0].upper() + s[1:]
        for _ in range(3):
            changed = False
            for match in COPULA_RE.finditer(s):
                # The whole predicate up to a relative clause / sentence end ("a poet, artist, and talented military leader").
                tail = re.split(r"\s+(?:who|which|that|whose)\s+|[;.!?]", s[match.start():], maxsplit=1)[0]
                parts = tail.split(",")
                items = [re.sub(r"^\s*(?:and|or)\s+", "", part).strip() for part in parts[1:]]
                items = [
                    item for item in items
                    if 1 <= len(item.split()) <= 4
                    and not re.match(r"(?:with|in|at|on|by|from|to|for|after|before|during|when|while|as|born|including|who|which)\b", item, re.I)
                ]
                scope = " ".join([parts[0]] + items)
                pred = [w for w in re.findall(r"[a-z]{4,}", scope.lower()) if w not in SUPPORT_FUNCTION and w not in SUPPORT_META]
                if not pred or all(w[:6] in ev_stems for w in pred):
                    continue
                who = COPULA_WHO_RE.match(s, match.start())
                if who and not _rel_names(s[who.start() : who.end()]):  # a named X owns its 'who' clause
                    s = s[: who.start()] + s[who.end():]
                    changed = True
                    break
                return replacement(s)
            if not changed:
                break
        if s.rstrip().endswith("?"):
            return s
        s = unlinked_relative(s)
        s = unsupported_cause(s)
        if not s:
            return None
        s = misattributed(s)
        if not s:
            return None
        if relation_conflict(s, ev_triples, focus):
            return None
        tokens = _support_stems(s)
        unsupported = [t for t in tokens if t not in ev_stems]
        nums = [n for n in re.findall(r"\b\d+\b", s) if n not in ev_nums]
        if nums or (len(tokens) >= 4 and len(unsupported) / len(tokens) > 0.34):
            return replacement(s)
        return s

    def unlinked_relative(s: str) -> str:
        """", which/who ..." must describe its antecedent in some single evidence sentence; else drop the clause."""
        for match in list(re.finditer(r",\s+(?:which|who)\s+([^,.;]+)", s))[::-1]:
            clause = _support_stems(match.group(1))
            ante_words = re.findall(r"[A-Za-z\-]+", s[: match.start()])[-4:]
            ante = _support_stems(" ".join(ante_words))
            if len(clause) < 2 or not ante:
                continue
            need = max(2, int(0.5 * len(clause) + 0.999))
            if any(len(clause & st) >= need and ante & st for st in (_support_stems(e) for e in ev_sents)):
                continue
            s = (s[: match.start()] + s[match.end():]).strip()
        return s

    causal = re.compile(r"\b(?:due to|as a result|because|since|thus|hence|therefore|led to|so)\b", re.I)
    prev_answer = [""]

    def unsupported_cause(s: str) -> str | None:
        """A cause-effect link in the answer must be a cause-effect link in the evidence."""
        def evidence_link(effect: str, cause: str) -> bool:
            eff = _support_stems(effect)
            cau = _support_stems(cause)
            if len(eff) < 2:
                return True
            need = max(2, int(0.5 * len(eff) + 0.999))
            for idx, sent in enumerate(ev_sents):
                if len(eff & _support_stems(sent)) < need or not causal.search(sent):
                    continue
                window = _support_stems(sent) | (_support_stems(ev_sents[idx - 1]) if idx else set())
                if len(cau & window) >= 2:
                    return True
            return False

        lead = re.match(r"^(?:this|that)\s+(?:led to|resulted in|caused)\b|^as a result\b|^because of this\b|^due to this\b", s, re.I)
        if lead and prev_answer[0] and not evidence_link(s[lead.end():], prev_answer[0]):
            return None
        for match in list(re.finditer(r",\s+(?:making|leading to|resulting in|which led to|thereby)\s+([^,.;]+)", s))[::-1]:
            if not evidence_link(match.group(1), s[: match.start()]):
                s = (s[: match.start()] + s[match.end():]).strip()
        return s

    def misattributed(s: str) -> str | None:
        """Drop a copular claim about the focus whose evidence sentence is about someone else."""
        if not focus:
            return s
        subject, _how, _off = _resolve_subject(s, focus)
        if subject != focus:
            return s
        for match in list(COPULA_RE.finditer(s)):
            end = re.search(r"[,.;:!?]|\s+and\s+", s[match.end():])
            stop = match.end() + (end.start() if end else len(s) - match.end())
            pred_stems = _support_stems(s[match.start():stop])
            if len(pred_stems) < 2:
                continue
            need = max(2, int(0.6 * len(pred_stems) + 0.999))
            hits = [e for e in ev_sents if len(pred_stems & _support_stems(e)) >= need]
            if not hits:
                continue
            if any(_resolve_subject(e, focus)[0] == focus for e in hits):
                continue
            conj = re.search(r"\s+and\s+$", s[: match.start()])
            if conj:
                return (s[: conj.start()] + s[stop:]).strip()
            return replacement(s)
        return s

    def disambiguate(sentences: list[str]) -> list[str]:
        out = []
        prev = ""
        for sent in sentences:
            if title and focus:
                lead = re.match(
                    r"^((?:However|But|Also|Later|Then|Thus|Hence|Additionally|Moreover|Furthermore|In addition|Finally),?\s+)?"
                    r"(He|She|(?<=,\s)he|(?<=,\s)she)\b",
                    sent,
                )
                if lead:
                    prev = "Someone Else."  # prefer the person's name over a sentence-leading pronoun
                # Another named person/place in the previous sentence makes "he" ambiguous.
                title_words = set(title.split())
                others = {key for (_a, _b, key) in _person_spans(prev)} - {focus}
                names = [w for w in re.findall(r"(?<=\s)[A-Z][a-z]+", prev) if w not in title_words]
                if lead and (others or names):
                    start = lead.start(2)
                    sent = sent[:start] + title + sent[lead.end(2):]
                    sent = sent[0].upper() + sent[1:]
            out.append(sent)
            prev = sent
        return out

    out_lines = []
    last_sentence = [""]
    for line in answer.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "Source", "[Page")):
            out_lines.append(line)
            continue
        bullet = re.match(r"^(\s*(?:[-*\u2022]|\d+[.)])\s+)", line)
        prefix = bullet.group(1) if bullet else ""
        body = line[len(prefix):]
        kept = []
        if focus and (
            re.fullmatch(r"[^.!]*\?", body.strip())
            or re.fullmatch(r"(?:who|what|when|where|why|how)\b[^.!?]{0,60}", body.strip(), re.I)
        ):
            continue  # a bare question echo is not part of the answer
        for sent in re.split(r"(?<=[.!?][\"'\u201d\u2019])\s+|(?<=[.!?])\s+(?=[A-Z\"'(\u201c\u2018])", body.strip()):
            if not sent.strip():
                continue
            fixed = fix(sent)
            if fixed and len(fixed.split()) >= 3:
                kept.append(fixed)
                prev_answer[0] = fixed
        if kept:
            kept = disambiguate([last_sentence[0]] + kept)[1:]
            last_sentence[0] = kept[-1]
            out_lines.append(prefix + " ".join(kept))
    result = "\n".join(out_lines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result or answer

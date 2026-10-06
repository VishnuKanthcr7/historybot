"""Generic fact index over primary textbook chunks.

The index records only relations and attributes a sentence states.
It does not replace chunks, and it does not infer a relationship
from two names merely appearing together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.engine.evidence import looks_like_exercise_chunk

NOT_STATED = "The prescribed textbook does not state that."
CITE_LABEL = "Class 9 Karnataka State Board 2026–27 textbook"

# Linguistic frames and predicate families. Not people, and not full questions.
_BROAD_RE = re.compile(
    r"\b(explain|tell me about|tell me more|tell me everything|describe|in detail|"
    r"everything about|teach me|summarize|summary|mcqs?|multiple choice|quiz|"
    r"revision|important points|go deeper|what else|what about|i want to know about|"
    r"i want to learn|learning module|e-?content)\b",
    re.I,
)
_YESNO_RE = re.compile(
    r"^(?P<aux>did|do|does|was|were|is|are|had|has)\s+(?P<body>.+?)\??$",
    re.I,
)
_PRONOUN_RE = re.compile(r"\b(he|she|him|his|her)\b", re.I)

_FUNCTION = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "from", "by", "with",
    "and", "or", "as", "after", "before", "when", "while", "his", "her", "their",
    "this", "that", "these", "those", "who", "what", "where", "when", "why", "how",
    "did", "was", "were", "is", "are", "do", "does", "had", "has", "been", "be",
    "into", "over", "under", "between", "against", "towards", "toward", "about",
    "there", "then", "later", "also", "only", "but", "due", "since", "although",
    "though", "because", "during", "upon", "within", "without", "near", "across",
    "he", "she", "they", "it", "its", "him", "them", "not", "no", "nor", "yet",
    "if", "so", "such", "than", "too", "very", "just", "own", "other", "another",
    "first", "second", "third", "new", "old", "many", "some", "any", "all",
    "which", "whose", "whom", "into", "per", "via",
}
_NAME_STOP = _FUNCTION | {
    "after", "when", "although", "later", "during", "over", "from", "into",
    "king", "kings", "battle", "army", "rule", "power", "death", "father",
    "mother", "son", "daughter", "years", "year", "thus", "hence", "with",
    "do", "you", "know", "this", "revenue", "system", "society", "literature",
    "province", "district", "village", "religious", "hindu", "administration",
    "chapter", "exercises", "activities", "project", "answer", "write",
    "golden", "age", "north", "south", "east", "west", "india", "indian",
}
_TYPE_WORDS = {
    "ruler", "king", "queen", "emperor", "sultan", "member", "minister",
    "system", "office", "monument", "group", "dynasty", "warrior", "poet",
}
_COLLECTIVE_RE = re.compile(r"^the\s+[a-z]+s$", re.I)

_PARTICLE = r"rao|ul|ud|bin|ibn|de|van|da|di|al|e"
_NAME_RE = re.compile(
    rf"\b([A-Z][A-Za-z''\-]*(?:-[A-Za-z][A-Za-z''\-]+)+"
    rf"|[A-Z][A-Za-z''\-]{{2,}}(?:\s+(?:[A-Z][A-Za-z''\-]+|{_PARTICLE}|I{{1,4}}|IV|VI{{0,3}}|IX|XI{{0,3}})){{1,5}}"
    rf"|[A-Z][A-Za-z''\-]{{3,}})\b"
)
_GROUP_RE = re.compile(r"\b(the\s+[A-Z][a-z]+s)\b")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NOISE_RE = re.compile(r"@?KTBS\s*NOT\s+TO\s+BE\s+REPUBLISHED|@KTBS", re.I)
_NEG_RE = re.compile(r"\b(did not|do not|does not|was not|were not|is not|never|not a|not the)\b", re.I)


@dataclass(frozen=True)
class Span:
    text: str
    norm: str
    category: str = "unspecified"


@dataclass
class Fact:
    fact_id: str
    statement_id: str
    kind: str
    predicate: str
    predicate_surface: str
    roles: dict[str, Span]
    polarity: str
    sentence: str
    span: str
    chunk_id: str
    printed_page: int | None
    source_id: str
    list_id: str | None = None
    order_key: str | None = None
    citation_label: str = ""
    document_name: str = ""
    pdf_page_number: int | None = None
    source_type: str = "primary_textbook"


@dataclass
class FactQuery:
    act: str
    predicate: str
    binds: dict[str, str]
    open_role: str | None
    polarity: str = "asserted"
    surface: str = ""


@dataclass
class FactIndex:
    facts: list[Fact] = field(default_factory=list)

    def norms(self) -> set[str]:
        found = set()
        for fact in self.facts:
            for span in fact.roles.values():
                if span.norm and len(span.norm) >= 3:
                    found.add(span.norm)
        return found


_CACHE: FactIndex | None = None


def norm_text(text: str) -> str:
    value = (text or "").lower().replace("'", "").replace("'", "")
    value = value.replace("-", " ")
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _page(item: dict) -> int | None:
    value = item.get("printed_page_number") or item.get("textbook_page_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _prepare(text: str) -> str:
    cleaned = _NOISE_RE.sub(" ", text or "")
    cleaned = cleaned.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\ufffd", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _span(text: str, category: str = "unspecified") -> Span | None:
    surface = re.sub(r"\s+", " ", (text or "")).strip(" ,;:.")
    if not surface:
        return None
    folded = norm_text(surface)
    if not folded or folded in _FUNCTION:
        return None
    if category == "unspecified" and _COLLECTIVE_RE.match(folded):
        category = "group"
    return Span(surface, folded, category)


def _same(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    left_tokens = {token for token in left.split() if token not in _FUNCTION and len(token) >= 3}
    right_tokens = {token for token in right.split() if token not in _FUNCTION and len(token) >= 3}
    if not left_tokens or not right_tokens:
        return False
    short, long = (left_tokens, right_tokens) if len(left_tokens) <= len(right_tokens) else (right_tokens, left_tokens)
    return short <= long and any(len(token) >= 4 for token in short)


def _specific(value: str) -> bool:
    return bool(value) and not _COLLECTIVE_RE.match(value)


def _names(text: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []
    for match in _NAME_RE.finditer(text or ""):
        surface = match.group(0).strip()
        if surface.lower() in _NAME_STOP:
            continue
        if any(start < match.end() and match.start() < end for start, end in taken):
            continue
        found.append((match.start(), match.end(), surface))
        taken.append((match.start(), match.end()))
    for match in _GROUP_RE.finditer(text or ""):
        if any(start < match.end() and match.start() < end for start, end in taken):
            continue
        found.append((match.start(), match.end(), match.group(1)))
        taken.append((match.start(), match.end()))
    found.sort()
    return found


def _polarity(text: str) -> str:
    return "negated" if _NEG_RE.search(text or "") else "asserted"


def _last_name(text: str) -> str | None:
    names = _names(text)
    return names[-1][2] if names else None


def _first_subject(sentence: str, previous: str | None) -> str | None:
    """Name the main clause is about. A leading After/When name is not the subject."""
    match = re.match(
        r"(?:when|after|although|though|since|because|with|due to)\b[^,]{0,120},\s*",
        sentence,
        re.I,
    )
    appos = re.search(
        r",\s*([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})\s*,\s+was\b",
        sentence,
    )
    if appos:
        return appos.group(1)
    body = sentence[match.end() :] if match else sentence
    body = re.sub(r"^(?:but|and|later|then|thus|hence|also)\b,?\s*", "", body, flags=re.I)
    if re.match(r"^(?:he|she|his|her)\b", body, re.I):
        head = sentence[: match.end()] if match else ""
        head_names = _names(head)
        return head_names[-1][2] if head_names else previous
    names = _names(body)
    if names:
        return names[0][2]
    return previous


class _Builder:
    def __init__(self, chunk: dict):
        self.chunk = chunk
        self.prepared = _prepare(chunk.get("text") or "")
        self.page = _page(chunk)
        self.source_id = str(chunk.get("source_id") or "")
        self.chunk_id = str(chunk.get("chunk_id") or "")
        self.label = str(chunk.get("citation_label") or CITE_LABEL)
        self.document = str(chunk.get("document_name") or "")
        self.pdf_page = chunk.get("pdf_page_number")
        self.source_type = str(chunk.get("source_type") or "primary_textbook")
        self.facts: list[Fact] = []
        self._n = 0
        self.current: str | None = None
        self.pending_father: str | None = None
        self.pending_sentence: str | None = None
        self.previous_sentence: str = ""

    def add(
        self,
        kind: str,
        predicate: str,
        surface: str,
        roles: dict[str, Span | None],
        sentence: str,
        span: str,
        polarity: str | None = None,
        list_id: str | None = None,
        order_key: str | None = None,
    ) -> None:
        kept = {key: value for key, value in roles.items() if value is not None}
        if not kept or not sentence:
            return
        blob = self.prepared
        probe = re.sub(r"\s+", " ", span or sentence).strip()
        if probe and probe.lower() not in blob.lower() and sentence.lower() not in blob.lower():
            return
        self._n += 1
        self.facts.append(
            Fact(
                fact_id=f"{self.chunk_id}:{self._n}",
                statement_id=f"{self.chunk_id}:{norm_text(sentence)[:80]}",
                kind=kind,
                predicate=predicate,
                predicate_surface=surface,
                roles=kept,
                polarity=polarity or _polarity(sentence),
                sentence=sentence,
                span=probe or sentence,
                chunk_id=self.chunk_id,
                printed_page=self.page,
                source_id=self.source_id,
                list_id=list_id,
                order_key=order_key,
                citation_label=self.label,
                document_name=self.document,
                pdf_page_number=self.pdf_page if isinstance(self.pdf_page, int) else None,
                source_type=self.source_type,
            )
        )

    def person(self, text: str | None) -> Span | None:
        if not text or text.lower() in {"he", "she", "him", "his", "her"}:
            text = self.current
        return _span(text or "", "person")

    def extract(self) -> list[Fact]:
        if not self.prepared or looks_like_exercise_chunk(self.chunk):
            return []
        sentences = [part.strip() for part in _SENT_SPLIT.split(self.prepared) if len(part.split()) >= 3]
        for sentence in sentences:
            if re.search(r"_{3,}", sentence):
                continue
            subject = _first_subject(sentence, self.current)
            self._sentence(sentence, subject)
            if subject and subject.lower() not in {"he", "she"}:
                self.current = subject
            self.previous_sentence = sentence
        return self.facts

    def _sentence(self, sentence: str, subject: str | None) -> None:
        self._kinship(sentence, subject)
        self._appointment(sentence, subject)
        self._succession(sentence, subject)
        self._conflict(sentence, subject)
        self._motion(sentence, subject)
        self._assist(sentence, subject)
        self._creation(sentence, subject)
        self._age(sentence, subject)
        self._birth(sentence, subject)
        self._quantity(sentence, subject)
        self._definition(sentence)
        self._list(sentence, subject)
        self._chronology(sentence, subject)
        self._identity(sentence, subject)
        self._generic_verb(sentence, subject)

    def _kinship(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"(?:his|her)\s+(?:eldest\s+|elder\s+|younger\s+|second\s+|first\s+)?(father|mother|son|daughter),\s*"
            r"([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4})",
            sentence,
        )
        if match:
            kin, name = match.group(1).lower(), match.group(2)
            owner = subject
            death = re.search(r"death of ([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4})", sentence)
            if death:
                owner = death.group(1)
            if kin in {"father", "mother"}:
                self._emit_kin(name, owner, kin, sentence)
            else:
                self._emit_kin(owner, name, kin, sentence)
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+(?:[A-Z][A-Za-z''\-]+|rao)){0,3})\s+was the (father|mother) of\s+"
            r"([A-Z][A-Za-z''\-]+(?:\s+(?:[A-Z][A-Za-z''\-]+|rao)){0,3})",
            sentence,
            re.I,
        )
        if match:
            self._emit_kin(match.group(1), match.group(3), match.group(2).lower(), sentence)
        match = re.search(
            r"was the (?:eldest\s+|elder\s+|younger\s+|second\s+)?(son|daughter) of "
            r"([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})",
            sentence,
        )
        if match and subject:
            self._emit_kin(match.group(2), subject, match.group(1), sentence)
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})\s+was (?:his|her) (father|mother)\b",
            sentence,
        )
        previous = self.current
        if match and previous and norm_text(match.group(1)) != norm_text(previous):
            joined = sentence
            candidate = f"{self.previous_sentence} {sentence}" if self.previous_sentence and previous not in sentence else sentence
            if candidate.lower() in self.prepared.lower():
                joined = candidate
            self._emit_kin(match.group(1), previous, match.group(2), joined)
        intro = re.search(
            r"(?i:(?:^|\s)(?:his\s+|her\s+)?father,\s*)([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})",
            sentence,
        )
        death = re.search(r"death of (?:his|her) father,\s*([A-Z][A-Za-z''\-]+)", sentence, re.I)
        if death and self.pending_father and norm_text(self.pending_father) != norm_text(death.group(1)):
            joined = sentence
            if self.pending_sentence and self.pending_father not in sentence:
                candidate = f"{self.pending_sentence} {sentence}"
                if candidate.lower() in self.prepared.lower():
                    joined = candidate
            self._emit_kin(self.pending_father, death.group(1), "father", joined)
            self.pending_father = None
            self.pending_sentence = None
        if intro and not (death and norm_text(intro.group(1)) == norm_text(death.group(1))):
            self.pending_father = intro.group(1)
            self.pending_sentence = sentence

    def _emit_kin(self, parent: str | None, child: str | None, kin: str, sentence: str) -> None:
        parent_span = self.person(parent)
        child_span = self.person(child)
        kin_span = _span(kin, "unspecified")
        if not parent_span or not child_span or parent_span.norm == child_span.norm:
            return
        stored = {"son": "father", "daughter": "mother"}.get(kin, kin)
        kin_span = _span(stored, "unspecified")
        self.add(
            "relationship",
            "parent",
            kin,
            {"parent": parent_span, "child": child_span, "kin": kin_span},
            sentence,
            sentence,
        )

    def _appointment(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,4}|[Hh]e|[Ss]he)\s*,?\s+was\s+(appointed|nominated)\s+as\s+(?:the\s+)?([A-Za-z][^.,;]{1,40})",
            sentence,
        )
        if match:
            self.add(
                "relationship",
                "appointed_as",
                match.group(2),
                {
                    "patient": self.person(match.group(1)),
                    "office": _span(match.group(3), "office"),
                },
                sentence,
                match.group(0),
            )
            death = re.search(r"death of\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})", sentence)
            if death and norm_text(death.group(1)) != norm_text(match.group(1)):
                self.add(
                    "chronology",
                    "after",
                    "after the death of",
                    {"earlier": self.person(death.group(1)), "later": self.person(match.group(1))},
                    sentence,
                    sentence,
                    order_key="after",
                )
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3}|[Hh]e|[Ss]he)\s+appointed\s+"
            r"(?:his\s+|her\s+)?(?:son\s+|daughter\s+)?([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,4})\s+as\s+(?:the\s+)?([^.,;]{2,40})",
            sentence,
        )
        if match:
            self.add(
                "relationship",
                "appointed_as",
                "appointed",
                {
                    "agent": self.person(match.group(1)),
                    "patient": self.person(match.group(2)),
                    "office": _span(match.group(3), "office"),
                },
                sentence,
                match.group(0),
            )

    def _succession(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})\s+succeeded\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3}|him|her)\b",
            sentence,
        )
        if match:
            earlier = self.current if match.group(2).lower() in {"him", "her"} else match.group(2)
            self.add(
                "relationship",
                "succeeded",
                "succeeded",
                {"later": self.person(match.group(1)), "earlier": self.person(earlier)},
                sentence,
                match.group(0),
            )
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})\b[^.]{0,80}\bbecame the successor\b",
            sentence,
        )
        death = re.search(r"death of ([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})", sentence)
        if match and death:
            self.add(
                "chronology",
                "succeeded",
                "successor",
                {"later": self.person(match.group(1)), "earlier": self.person(death.group(1))},
                sentence,
                sentence,
                order_key="after",
            )

    def _conflict(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4}|[Hh]e|[Ss]he)\s+defeated\s+"
            r"(the\s+[A-Z][a-z]+s?|[A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})",
            sentence,
        )
        if match:
            self.add(
                "event",
                "defeated",
                "defeated",
                {"agent": self.person(match.group(1)), "patient": self.person(match.group(2))},
                sentence,
                match.group(0),
            )
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4}|[Hh]e|[Ss]he)\s+was defeated by\s+"
            r"(the\s+[A-Z][a-z]+s?|[A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})",
            sentence,
            re.I,
        )
        if match:
            self.add(
                "event",
                "defeated",
                "was defeated by",
                {"patient": self.person(match.group(1)), "agent": self.person(match.group(2))},
                sentence,
                match.group(0),
            )
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4}|[Hh]e|[Ss]he)\s+lost to\s+"
            r"(the\s+[A-Z][a-z]+s?|[A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,3})"
            r"(?:\s+in\s+a\s+battle\s+near\s+([A-Z][A-Za-z''\-]+))?",
            sentence,
        )
        if match:
            place = match.group(3)
            if not place:
                near = re.search(r"\bnear\s+([A-Z][A-Za-z''\-]+)", sentence, re.I)
                place = near.group(1) if near else None
            self.add(
                "event",
                "lost_to",
                "lost to",
                {
                    "patient": self.person(match.group(1)),
                    "agent": self.person(match.group(2)),
                    "location": _span(place, "place") if place else None,
                },
                sentence,
                match.group(0),
            )

    def _motion(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"(tried to march|marched|march(?:ed)?)\s+towards\s+([A-Z][A-Za-z''\-]+)",
            sentence,
            re.I,
        )
        if match and subject:
            self.add(
                "event",
                "moved_toward",
                match.group(1),
                {"agent": self.person(subject), "destination": _span(match.group(2), "place")},
                sentence,
                match.group(0),
            )

    def _assist(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"(?:assisting|assisted|assist)\s+(the\s+[A-Z][a-z]+s?|[A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})",
            sentence,
        )
        if match:
            self.add(
                "relationship",
                "assisted",
                "assisted",
                {"agent": self.person(subject), "patient": self.person(match.group(1))},
                sentence,
                match.group(0),
            )

    def _creation(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"\b(built|constructed|established|founded)\s+(?:the\s+|a\s+|an\s+)?([^.,;]{2,60})",
            sentence,
            re.I,
        )
        if match and subject:
            self.add(
                "relationship",
                "built" if match.group(1).lower() in {"built", "constructed"} else "established",
                match.group(1).lower(),
                {"agent": self.person(subject), "object": _span(match.group(2), "monument")},
                sentence,
                match.group(0),
            )
        match = re.search(r"\babolished\s+([A-Z][A-Za-z''\-]+)", sentence)
        if match and subject:
            self.add(
                "event",
                "abolished",
                "abolished",
                {"agent": self.person(subject), "object": _span(match.group(1), "term")},
                sentence,
                match.group(0),
            )
        match = re.search(r"\bwrote\s+([^.,;]{2,60})", sentence, re.I)
        if match and subject:
            self.add(
                "event",
                "wrote",
                "wrote",
                {"agent": self.person(subject), "object": _span(match.group(1), "term")},
                sentence,
                match.group(0),
            )

    def _age(self, sentence: str, subject: str | None) -> None:
        match = re.search(r"at the age of\s+(\d+)\s*(years?)?", sentence, re.I)
        if not match:
            match = re.search(r"\b(?:was\s+only\s+)?(\d+)\s+years?\s+old\b", sentence, re.I)
        if not match:
            return
        who = subject
        named = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})\b[^.]{0,40}(?:assumed power|ascend|throne|came to power)",
            sentence,
        )
        if named:
            who = named.group(1)
        value = _span(match.group(1), "number")
        self.add(
            "attribute",
            "age",
            "age",
            {"subject": self.person(who), "value": value},
            sentence,
            match.group(0),
        )

    def _birth(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})\s+was born\s+(?:in|at)\s+([A-Z][^.,;]{1,40})",
            sentence,
        )
        if not match:
            match = re.search(r",\s*([A-Z][A-Za-z''\-]+),\s+was born\s+(?:in|at)\s+([A-Z][^.,;]{1,40})", sentence)
        if match:
            self.add(
                "attribute",
                "birthplace",
                "born",
                {"subject": self.person(match.group(1)), "value": _span(match.group(2), "place")},
                sentence,
                match.group(0),
            )

    def _quantity(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"(\d+\s+(?:lakh|lakhs|crore|crores)(?:\s+rupees)?)",
            sentence,
            re.I,
        )
        if not match:
            return
        who = _last_name(sentence) or subject
        came = re.search(r"came to\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})", sentence)
        if came:
            who = came.group(1)
        context = "compensation" if re.search(r"compensation", sentence, re.I) else "amount"
        self.add(
            "quantity",
            "quantity",
            context,
            {
                "subject": self.person(who),
                "value_text": _span(match.group(1), "number"),
                "context": _span(context, "unspecified"),
            },
            sentence,
            match.group(0),
        )

    def _definition(self, sentence: str) -> None:
        match = re.match(r"([A-Z][\w''\-]+(?:[-\s][\w''\-]+){0,3})\s*:\s+(.{8,})", sentence)
        if match and match.group(1).lower() not in _NAME_STOP:
            self.add(
                "definition",
                "definition",
                "called",
                {"term": _span(match.group(1), "term"), "definition": _span(sentence, "unspecified")},
                sentence,
                sentence,
            )
        for match in re.finditer(
            r"(?:called|named|known as)\s+[\"']?([A-Z][\w''\-]+(?:[-\s][A-Za-z][\w''\-]+){0,4})",
            sentence,
        ):
            self.add(
                "definition",
                "definition",
                "called",
                {"term": _span(match.group(1), "term"), "definition": _span(sentence, "unspecified")},
                sentence,
                match.group(0),
            )
        match = re.search(r"\b(The\s+[A-Z][A-Za-z\-]+\s+system)\s+was\s+(.{8,})", sentence)
        if match:
            self.add(
                "definition",
                "definition",
                "was",
                {"term": _span(match.group(1), "system"), "definition": _span(match.group(2), "unspecified")},
                sentence,
                match.group(0),
            )
        match = re.search(r"(.{8,80}?)\s+is called\s+([A-Za-z][\w\s\-]{2,40})", sentence, re.I)
        if match:
            self.add(
                "definition",
                "definition",
                "is called",
                {"term": _span(match.group(2), "term"), "definition": _span(match.group(1), "unspecified")},
                sentence,
                match.group(0),
            )

    def _list(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"([A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})'s\s+(ministers|members|taxes|territories)\s+were\s+(.+)",
            sentence,
            re.I,
        )
        if match:
            self._emit_list(match.group(1), match.group(2), match.group(3), sentence)
            return
        match = re.search(
            r"(ministers|members|departments)\s+(?:called|known as|named)\s+(.+)",
            sentence,
            re.I,
        )
        if match:
            owner = self.current if re.search(r"\bassist\s+(?:him|her)\b", sentence, re.I) else subject
            self._emit_list(owner, match.group(1), match.group(2), sentence)

    def _emit_list(self, owner: str | None, context: str, raw: str, sentence: str) -> None:
        parts = re.split(r",|\band\b", raw)
        members = []
        for part in parts:
            part = re.sub(r"\b(to|in|of|the|a)\b.*", "", part, flags=re.I).strip(" .")
            span = _span(part, "person")
            if span and len(span.norm) >= 2 and span.norm not in _FUNCTION:
                members.append(span)
        if len(members) < 2:
            return
        list_id = f"{self.chunk_id}:{norm_text(context)}:{norm_text(owner or '')}"
        self.add(
            "list",
            "list",
            context,
            {"owner": self.person(owner), "context": _span(context, "unspecified")},
            sentence,
            raw,
            list_id=list_id,
        )
        for index, member in enumerate(members, start=1):
            self.add(
                "list",
                "member_of",
                context,
                {"member": member, "owner": self.person(owner), "context": _span(context, "unspecified")},
                sentence,
                member.text,
                list_id=list_id,
                order_key=str(index),
            )

    def _chronology(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"after the death of\s+([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,4})",
            sentence,
            re.I,
        )
        if match and subject and norm_text(subject) != norm_text(match.group(1)):
            self.add(
                "chronology",
                "after",
                "after the death of",
                {"earlier": self.person(match.group(1)), "later": self.person(subject)},
                sentence,
                match.group(0),
                order_key="after",
            )
        if re.match(r"later\b", sentence, re.I) and subject and self.current and norm_text(subject) != norm_text(self.current):
            self.add(
                "chronology",
                "after",
                "later",
                {"earlier": self.person(self.current), "later": self.person(subject)},
                sentence,
                sentence,
                order_key="later",
            )

    def _identity(self, sentence: str, subject: str | None) -> None:
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})\s+was\s+(?:a|an|the)\s+((?:(?!appointed|defeated|born|only\s+\d)[^.]{3,80}))",
            sentence,
        )
        if not match:
            return
        complement = match.group(2).strip()
        if re.match(r"(?:eldest\s+|elder\s+)?(?:son|daughter|father|mother)\b", complement, re.I):
            return
        category = "unspecified"
        tokens = set(norm_text(complement).split())
        if tokens & _TYPE_WORDS:
            category = next(iter(tokens & _TYPE_WORDS))
        self.add(
            "identity",
            "identity",
            "was",
            {"subject": self.person(match.group(1)), "complement": _span(complement, category)},
            sentence,
            match.group(0),
        )
        if re.search(r"\bruler of\b|\bking of\b|\bemperor of\b", complement, re.I):
            place = re.search(r"(?:ruler|king|emperor) of\s+(.+)", complement, re.I)
            self.add(
                "relationship",
                "ruler_of",
                "ruler of",
                {"agent": self.person(match.group(1)), "place": _span(place.group(1), "place") if place else None},
                sentence,
                match.group(0),
            )

    def _generic_verb(self, sentence: str, subject: str | None) -> None:
        """A content verb between two names. Copulas and bare 'and' create nothing."""
        if re.search(
            r"\b(father|mother|son|daughter|appointed|nominated|defeated|lost|march|assisted|built|born|succeeded)\b",
            sentence,
            re.I,
        ):
            return
        match = re.search(
            r"\b([A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})\s+"
            r"(attacked|conquered|helped|joined|founded|captured|imprisoned)\s+"
            r"(the\s+[A-Z][a-z]+s?|[A-Z][A-Za-z''\-]+(?:\s+[A-Za-z''\-]+){0,3})",
            sentence,
        )
        if not match:
            return
        self.add(
            "relationship",
            match.group(2).lower(),
            match.group(2).lower(),
            {"agent": self.person(match.group(1)), "patient": self.person(match.group(3))},
            sentence,
            match.group(0),
        )


def index_chunks(chunks: list[dict]) -> FactIndex:
    facts: list[Fact] = []
    seen = set()
    for chunk in chunks:
        if (chunk.get("source_type") or "primary_textbook") not in {"primary_textbook", ""}:
            continue
        for fact in _Builder(chunk).extract():
            key = (
                fact.predicate,
                fact.polarity,
                tuple(sorted((role, span.norm) for role, span in fact.roles.items())),
                fact.printed_page,
                fact.list_id,
                fact.order_key,
            )
            if key in seen:
                continue
            seen.add(key)
            facts.append(fact)
    return FactIndex(facts)


def corpus_index() -> FactIndex:
    global _CACHE
    if _CACHE is None:
        from rag.engine.topic_map import load_primary_chunks

        _CACHE = index_chunks(list(load_primary_chunks()))
    return _CACHE


def _previous_user(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def _expand_pronouns(question: str, history: list[dict] | None) -> str:
    if not _PRONOUN_RE.search(question or ""):
        return question
    if _names(question):
        return question
    previous = _previous_user(history)
    names = [name for _a, _b, name in _names(previous)]
    if len(names) != 1:
        return question
    name = names[0]
    text = re.sub(r"\b(his|her)\b", f"{name}'s", question, count=1, flags=re.I)
    text = re.sub(r"\b(he|she|him)\b", name, text, count=1, flags=re.I)
    return text


def _clean_slot(text: str) -> str:
    value = (text or "").strip(" ?.,;:")
    value = re.sub(
        r"\b(receive|received|assume power|assumed power|happen|happened|the battle|battle|do|does|did)\b",
        " ",
        value,
        flags=re.I,
    )
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" ?.,;:")


def compile_question(question: str, history: list[dict] | None = None) -> FactQuery | None:
    raw = _expand_pronouns((question or "").strip(), history)
    if not raw or _BROAD_RE.search(raw):
        return None
    if re.search(r"\b(and also|and what|and tell|and his exact|and world)\b", raw, re.I):
        return None
    text = raw.strip().rstrip("?")
    folded = re.sub(r"\s+", " ", text)

    match = re.search(
        r"\b(?:who|whom)\s+(?:was|is|were|are)\s+(?:the\s+)?(father|mother|parent|son|daughter)\s+of\s+(.+)$",
        folded,
        re.I,
    )
    if match:
        kin = match.group(1).lower()
        entity = _clean_slot(match.group(2))
        if kin in {"son", "daughter"}:
            return FactQuery("wh", "parent", {"parent": norm_text(entity), "kin": "father" if kin == "son" else "mother"}, "child", surface=kin)
        return FactQuery("wh", "parent", {"child": norm_text(entity), "kin": "father" if kin == "parent" else kin}, "parent", surface=kin)
    match = re.search(
        r"\b(?:who|whom)\s+(?:was|is)\s+(.+?)'s\s+(father|mother|parent|son|daughter)\b",
        folded,
        re.I,
    )
    if match:
        kin = match.group(2).lower()
        entity = _clean_slot(match.group(1))
        if kin in {"son", "daughter"}:
            return FactQuery("wh", "parent", {"parent": norm_text(entity)}, "child", surface=kin)
        return FactQuery("wh", "parent", {"child": norm_text(entity), "kin": "father" if kin == "parent" else kin}, "parent", surface=kin)
    match = re.search(r"\bwhose\s+(son|daughter|father|mother)\s+(?:was|is|were)\s+(.+)$", folded, re.I)
    if match:
        kin = match.group(1).lower()
        entity = _clean_slot(match.group(2))
        if kin in {"son", "daughter"}:
            return FactQuery("wh", "parent", {"child": norm_text(entity)}, "parent", surface=kin)
        return FactQuery("wh", "parent", {"parent": norm_text(entity)}, "child", surface=kin)

    if re.search(r"\b(at what age|how old|what age)\b", folded, re.I):
        who = re.search(r"\b(?:did|was|is)\s+(.+?)\s+(?:assume|ascend|come|became|become|appoint)", folded, re.I)
        if not who:
            who = re.search(r"\b(?:did|was)\s+(.+)$", folded, re.I)
        if who:
            return FactQuery("wh", "age", {"subject": norm_text(_clean_slot(who.group(1)))}, "value", surface="age")

    if re.search(r"\bborn\b|\bbirthplace\b|\bbirth place\b", folded, re.I):
        who = re.search(r"\b(?:was|is|did)\s+(.+?)\s+born\b", folded, re.I)
        if who:
            return FactQuery("wh", "birthplace", {"subject": norm_text(_clean_slot(who.group(1)))}, "value", surface="born")

    if re.search(r"\b(how much|how many|what amount|compensation)\b", folded, re.I):
        who = re.search(r"\bdid\s+(.+?)\s+(?:receive|get|obtain)\b", folded, re.I)
        if not who:
            who = re.search(r"\bcompensation\s+did\s+(.+)$", folded, re.I)
        if who:
            binds = {"subject": norm_text(_clean_slot(who.group(1)))}
            if re.search(r"compensation", folded, re.I):
                binds["context"] = "compensation"
            return FactQuery("wh", "quantity", binds, "value_text", surface="quantity")

    match = re.search(r"\bwhere did\s+(.+?)\s+(lose|fall|fight)\b", folded, re.I)
    if match:
        return FactQuery("wh", "lost_to", {"patient": norm_text(_clean_slot(match.group(1)))}, "location", surface="lose")
    match = re.search(r"\bwhat was the outcome\s+(?:near|at|of|in)\s+(.+)$", folded, re.I)
    if match:
        return FactQuery("wh", "lost_to", {"location": norm_text(_clean_slot(match.group(1)))}, "patient", surface="outcome")
    match = re.search(r"\bwho (?:tried to |wanted to )?(?:march|marched|move|moved)\s+towards\s+(.+)$", folded, re.I)
    if match:
        return FactQuery("wh", "moved_toward", {"destination": norm_text(_clean_slot(match.group(1)))}, "agent", surface="march")
    match = re.search(r"\bwho tried to march towards\s+(.+)$", folded, re.I)
    if match:
        return FactQuery("wh", "moved_toward", {"destination": norm_text(_clean_slot(match.group(1)))}, "agent", surface="march")

    match = re.search(r"\bwho built\s+(.+)$", folded, re.I)
    if match:
        return FactQuery("wh", "built", {"object": norm_text(_clean_slot(match.group(1)))}, "agent", surface="built")
    match = re.search(r"\bwhich tax did\s+(.+?)\s+abolish", folded, re.I)
    if match:
        return FactQuery("wh", "abolished", {"agent": norm_text(_clean_slot(match.group(1)))}, "object", surface="abolish")
    match = re.search(r"\bwho was appointed\s+(?:as\s+)?(?:the\s+)?(.+?)(?:\s+after\b|$)", folded, re.I)
    if match:
        binds = {"office": norm_text(_clean_slot(match.group(1)))}
        death = re.search(r"after (?:the death of\s+)?(.+)$", folded, re.I)
        if death:
            binds["earlier"] = norm_text(_clean_slot(death.group(1)))
        return FactQuery("wh", "appointed_as", binds, "patient", surface="appointed")
    match = re.search(r"\bafter whose death was\s+(.+?)\s+appointed", folded, re.I)
    if match:
        return FactQuery("wh", "after", {"later": norm_text(_clean_slot(match.group(1)))}, "earlier", surface="after")
    match = re.search(r"\bwho came\s+(after|before)\s+(.+)$", folded, re.I)
    if match:
        if match.group(1).lower() == "after":
            return FactQuery("wh", "after", {"earlier": norm_text(_clean_slot(match.group(2)))}, "later", surface="after")
        return FactQuery("wh", "after", {"later": norm_text(_clean_slot(match.group(2)))}, "earlier", surface="before")
    match = re.search(r"\bwhich\s+(ministers|members|taxes)\b.*\b(?:assist|assisted|of|under)\s+(.+)$", folded, re.I)
    if match:
        return FactQuery(
            "wh",
            "member_of",
            {"owner": norm_text(_clean_slot(match.group(2))), "context": norm_text(match.group(1))},
            "member",
            surface="list",
        )
    match = re.search(r"\bwhat did\s+(.+?)\s+(write|built|build|abolish|conquer)\b", folded, re.I)
    if match:
        verb = match.group(2).lower()
        predicate = {"write": "wrote", "built": "built", "build": "built", "abolish": "abolished", "conquer": "conquered"}[verb]
        return FactQuery("wh", predicate, {"agent": norm_text(_clean_slot(match.group(1)))}, "object", surface=verb)

    if re.match(r"\bwhat\s+(?:is|was|were|are)\b", folded, re.I) and not re.search(
        r"\b(outcome|capital of|your|python|joke)\b", folded, re.I
    ):
        term = re.sub(r"^(?:what)\s+(?:is|was|were|are)\s+(?:the\s+|a\s+|an\s+)?", "", folded, flags=re.I)
        term = _clean_slot(term)
        if term and len(norm_text(term)) >= 4 and not re.match(r"^(?:who|he|she)$", term, re.I):
            return FactQuery("wh", "definition", {"term": norm_text(term)}, "definition", surface="definition")

    if re.match(r"\bwho\s+(?:was|is|were|are)\b", folded, re.I):
        return None

    yes = _YESNO_RE.match(folded)
    if not yes:
        return None
    return _compile_yesno(yes.group("aux").lower(), yes.group("body"))


def _compile_yesno(aux: str, body: str) -> FactQuery | None:
    body = body.strip()
    polarity = "negated" if _NEG_RE.search(body) else "asserted"
    match = re.search(
        r"^(.+?)\s+(appoint|appointed)\s+(.+)$",
        body,
        re.I,
    )
    if match:
        return FactQuery(
            "yesno",
            "appointed_as",
            {"agent": norm_text(_clean_slot(match.group(1))), "patient": norm_text(_clean_slot(match.group(3)))},
            None,
            polarity,
            "appointed",
        )
    match = re.search(r"^(.+?)\s+(?:a|an|the)\s+(.+)$", body, re.I)
    if match and aux in {"was", "were", "is", "are"}:
        return FactQuery(
            "yesno",
            "identity",
            {"subject": norm_text(_clean_slot(match.group(1))), "complement": norm_text(_clean_slot(match.group(2)))},
            None,
            polarity,
            "identity",
        )
    match = re.search(
        r"^(.+?)\s+(lose|lost|defeat|defeated)\b(.*)$",
        body,
        re.I,
    )
    if match:
        verb = match.group(2).lower()
        tail = match.group(3) or ""
        place = re.search(r"\b(?:near|at|in)\s+([A-Za-z][\w\-]+)", tail, re.I)
        by = re.search(r"\bby\s+(.+)$", tail, re.I)
        if verb in {"lose", "lost"}:
            binds = {"patient": norm_text(_clean_slot(match.group(1)))}
            if place:
                binds["location"] = norm_text(place.group(1))
            return FactQuery("yesno", "lost_to", binds, None, polarity, "lost")
        binds = {"agent": norm_text(_clean_slot(match.group(1)))}
        patient = re.search(r"^(?:\s+the)?\s*([A-Za-z][\w''\-]+(?:\s+[A-Za-z][\w''\-]+){0,3})", tail)
        if by:
            binds = {
                "patient": norm_text(_clean_slot(match.group(1))),
                "agent": norm_text(_clean_slot(by.group(1))),
            }
        elif patient:
            binds["patient"] = norm_text(_clean_slot(patient.group(1)))
        if place:
            binds["location"] = norm_text(place.group(1))
        return FactQuery("yesno", "defeated", binds, None, polarity, "defeated")
    return None


_PREDICATE_FAMILY = {
    "lost_to": {"lost_to", "defeated"},
    "defeated": {"defeated", "lost_to"},
    "after": {"after", "succeeded"},
    "succeeded": {"succeeded", "after"},
    "appointed_as": {"appointed_as"},
    "parent": {"parent"},
    "age": {"age"},
    "birthplace": {"birthplace"},
    "quantity": {"quantity"},
    "definition": {"definition"},
    "moved_toward": {"moved_toward"},
    "built": {"built"},
    "member_of": {"member_of", "list"},
    "abolished": {"abolished"},
    "wrote": {"wrote"},
    "identity": {"identity"},
    "assisted": {"assisted"},
}

_HARD = {
    "parent",
    "age",
    "birthplace",
    "appointed_as",
    "lost_to",
    "defeated",
    "moved_toward",
    "quantity",
    "member_of",
    "after",
    "succeeded",
    "built",
    "abolished",
    "assisted",
    "identity",
}


def _family(predicate: str) -> set[str]:
    return _PREDICATE_FAMILY.get(predicate, {predicate})


def _role_ok(fact: Fact, role: str, wanted: str) -> bool:
    if role == "kin":
        kin = fact.roles.get("kin")
        if not kin:
            return True
        if wanted in {"father", "parent"}:
            return kin.norm in {"father", "parent"}
        if wanted in {"mother"}:
            return kin.norm == "mother"
        return _same(kin.norm, wanted)
    span = fact.roles.get(role)
    if span is None:
        return False
    return _same(span.norm, wanted)


def _supports(fact: Fact, query: FactQuery) -> bool:
    if fact.predicate not in _family(query.predicate) or fact.polarity != query.polarity:
        return False
    if query.predicate == "definition":
        term = fact.roles.get("term")
        wanted = query.binds.get("term", "")
        return bool(term and wanted and (wanted in term.norm or term.norm in wanted or _same(term.norm, wanted)))
    if query.predicate == "member_of":
        if fact.predicate != "member_of":
            return False
    for role, wanted in query.binds.items():
        if role == "earlier" and query.predicate == "appointed_as":
            continue
        if not _role_ok(fact, role, wanted):
            return False
    if query.open_role and query.open_role not in fact.roles and query.predicate != "definition":
        if not (query.open_role == "value_text" and "value" in fact.roles):
            return False
    return True


def _conflicts(fact: Fact, query: FactQuery) -> bool:
    if query.act != "yesno" or fact.polarity == "negated":
        return False
    if fact.predicate not in _family(query.predicate):
        return False
    if query.predicate == "identity":
        subject = query.binds.get("subject", "")
        if not _role_ok(fact, "subject", subject):
            return False
        complement = fact.roles.get("complement")
        if not complement:
            return False
        asked = set(query.binds.get("complement", "").split()) - _FUNCTION
        stored = set(complement.norm.split()) - _FUNCTION
        asked_types = asked & _TYPE_WORDS
        stored_types = stored & _TYPE_WORDS
        if asked and asked <= stored:
            return False
        return bool(asked_types and stored_types and asked_types != stored_types)
    if query.predicate in {"lost_to", "defeated"}:
        place = query.binds.get("location")
        if place and not _role_ok(fact, "location", place):
            return False
        for role in ("patient", "agent"):
            wanted = query.binds.get(role)
            if not wanted:
                continue
            span = fact.roles.get(role)
            if not span:
                continue
            if _same(span.norm, wanted):
                continue
            if _specific(span.norm) and _specific(wanted):
                return True
        return False
    if query.predicate == "appointed_as":
        patient = query.binds.get("patient")
        agent = query.binds.get("agent")
        if patient and not _role_ok(fact, "patient", patient):
            return False
        stored_agent = fact.roles.get("agent")
        if agent and stored_agent and _specific(stored_agent.norm) and not _same(stored_agent.norm, agent):
            return True
        return False
    return False


def lookup(index: FactIndex, query: FactQuery) -> tuple[str, list[Fact]]:
    if any(re.fullmatch(r"(?:he|she|him|his|her|they|them)", value or "") for value in query.binds.values()):
        return "fallback", []
    supported = [fact for fact in index.facts if _supports(fact, query)]
    earlier = query.binds.get("earlier")
    if earlier and query.predicate == "appointed_as":
        supported = [
            fact
            for fact in supported
            if earlier in norm_text(fact.sentence)
            and not _same((fact.roles.get("patient") or Span("", "", "")).norm, earlier)
        ]
    if query.predicate == "definition" and supported:
        term = query.binds.get("term", "")
        pages = {fact.printed_page for fact in supported}
        extra = [
            fact
            for fact in index.facts
            if fact.printed_page in pages and term and term in norm_text(fact.sentence)
        ]
        supported = extra + supported
    if supported:
        return "supported", supported
    conflicts = [fact for fact in index.facts if _conflicts(fact, query)]
    if conflicts:
        return "contradicted", conflicts
    if query.act == "yesno" or query.predicate in _HARD:
        return "not_stated", []
    return "fallback", []


def _content_tokens(text: str) -> set[str]:
    return {token for token in norm_text(text).split() if len(token) >= 4}


def _sentences(facts: list[Fact], limit: int = 3) -> list[str]:
    out = []
    seen = set()
    for fact in facts:
        text = re.sub(r"\s+", " ", fact.sentence).strip()
        key = norm_text(text)
        if not text or key in seen:
            continue
        tokens = _content_tokens(text)
        if len(tokens) >= 8 and any(
            tokens <= _content_tokens(previous) or _content_tokens(previous) <= tokens for previous in out
        ):
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _pages(facts: list[Fact]) -> list[int]:
    pages = []
    for fact in facts:
        if fact.printed_page is not None and fact.printed_page not in pages:
            pages.append(fact.printed_page)
    return pages


def _sources(facts: list[Fact]) -> list[dict]:
    rows = []
    seen = set()
    for fact in facts:
        if fact.printed_page is None or fact.printed_page in seen:
            continue
        seen.add(fact.printed_page)
        rows.append(
            {
                "textbook_page_number": fact.printed_page,
                "printed_page_number": fact.printed_page,
                "pdf_page_number": fact.pdf_page_number,
                "chunk_id": fact.chunk_id,
                "source_type": fact.source_type or "primary_textbook",
                "authority": "primary",
                "citation_label": fact.citation_label or CITE_LABEL,
                "document_name": fact.document_name,
            }
        )
    rows.sort(key=lambda item: int(item["printed_page_number"]))
    return rows


def _citation(facts: list[Fact]) -> str:
    pages = _pages(facts)
    label = next((fact.citation_label for fact in facts if fact.citation_label), CITE_LABEL)
    if not pages:
        return f"Source: {label}"
    if len(pages) == 1:
        return f"Source: {label}, page {pages[0]}"
    return f"Source: {label}, pages " + ", ".join(str(page) for page in pages)


def render_answer(status: str, facts: list[Fact]) -> str:
    lines = _sentences(facts)
    if status == "supported":
        body = " ".join(lines)
    elif status == "contradicted":
        correction = " ".join(lines)
        body = NOT_STATED if not correction else f"{NOT_STATED} The textbook states: {correction}"
    else:
        body = NOT_STATED
        return body
    cite = _citation(facts)
    return f"{body}\n\n{cite}" if cite else body


def try_fact_answer(question: str, history: list[dict] | None = None, index: FactIndex | None = None) -> dict | None:
    """Answer a compiled fact question, or return None so the evidence pack can run."""
    query = compile_question(question, history)
    if query is None:
        return None
    fact_index = index if index is not None else corpus_index()
    status, facts = lookup(fact_index, query)
    if status == "fallback":
        return None
    answer = render_answer(status, facts)
    sources = _sources(facts) if status != "not_stated" else []
    return {
        "answer": answer,
        "language": "en",
        "grounded": status != "not_stated",
        "sources": sources,
        "retrieval_query": question,
        "retrieved": [],
        "selected_chunk_ids": [fact.chunk_id for fact in facts if fact.chunk_id],
        "validation_reason": f"fact_{status}",
        "intent": "STANDALONE",
        "mode": "NORMAL",
        "question_type": "DIRECT",
        "resolved_topic": None,
        "used_supplementary": False,
        "regeneration_count": 0,
        "unsupported_claims": [],
        "fallback_used": False,
        "fact_status": status,
        "fact_predicate": query.predicate,
    }

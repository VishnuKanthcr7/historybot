"""Phase 9B greeting/casual gate checks. No Chroma calls for greetings."""

from rag.engine.classify import classify_casual
from rag.engine.answer import answer_question


def main() -> None:
    cases = [
        ("hi", "GREETING"),
        ("hello", "GREETING"),
        ("hey", "GREETING"),
        ("good morning", "GREETING"),
        ("thanks", "THANKS"),
        ("thank you", "THANKS"),
        ("?", "CLARIFY"),
        ("ok", "CLARIFY"),
        ("Hi, who was Babar?", None),
    ]
    for text, expected in cases:
        got = classify_casual(text)
        print(("OK" if got == expected else "FAIL"), repr(text), got, "expected", expected)

    for text in ("hi", "hello", "thanks", "?"):
        result = answer_question(text, language="en")
        has_hits = bool(result.get("retrieved"))
        print(
            "ANS",
            repr(text),
            result.get("intent"),
            result.get("answer")[:80],
            "retrieved",
            has_hits,
            "sources",
            result.get("sources"),
        )


if __name__ == "__main__":
    main()

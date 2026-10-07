"""Evidence-boundary checks for broad, how, why, and comparison answers.

These tests do not call the language model and do not expect a fixed paragraph.
They check that selected textbook evidence keeps the right person and the right event.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.coverage import causal_chain_kept
from rag.engine.depth import evidence_states_motive
from rag.engine.coverage import combine_entity_sections
from rag.engine.entity import (
    _mentions,
    _resolve_subject,
    build_entity_plan,
    entity_focus_evidence,
    entity_readable,
)
from rag.engine.topic_map import RULER_KEYS, load_primary_chunks

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {detail}")


def blob(chunks: list[dict]) -> str:
    return " ".join(item.get("text") or "" for item in chunks).lower()


def main() -> None:
    check("regnal-ii-not-base", _mentions("Tarabai made Shivaji II the king.", "shivaji") == 0)
    check("regnal-i-still-matches", _mentions("Baji Rao I was appointed as Peshwa.", "bajirao") > 0)
    check(
        "causal-requires-previous-event",
        not causal_chain_kept(
            "Nizam-ul-Mulk lost near Bhopal. Due to this, Baji Rao received compensation.",
            "Nizam-ul-Mulk marched towards Delhi. As a result, Baji Rao received compensation.",
        ),
    )
    check(
        "causal-keeps-stated-cause",
        causal_chain_kept(
            "Nizam-ul-Mulk lost near Bhopal. Due to this, Baji Rao received compensation.",
            "Nizam-ul-Mulk lost near Bhopal. Due to this, Baji Rao received compensation.",
        ),
    )
    motive_chunks = [
        {
            "text": "Shah Jahan built the Taj Mahal in memory of his wife Mumtaz.",
        }
    ]
    check(
        "why-explicit-memory",
        evidence_states_motive(motive_chunks, "shahjahan", "Why did Shah Jahan build the Taj Mahal?"),
    )
    check(
        "why-adjacent-event-is-not-a-motive",
        not evidence_states_motive(
            [{"text": "Shah Jahan built a fort. Trade increased during his reign."}],
            "shahjahan",
            "Why did Shah Jahan build the Taj Mahal?",
        ),
    )

    chunks = load_primary_chunks()
    baji = entity_focus_evidence(chunks, "bajirao")
    baji_text = blob(baji)
    check("baji-detail-has-evidence", "peshwa" in baji_text and "baji rao" in baji_text)
    if "compensation" in baji_text or "lakh" in baji_text:
        for item in baji:
            text = (item.get("text") or "").lower()
            if "compensation" not in text and "lakh" not in text:
                continue
            comp = text.find("compensation")
            if comp < 0:
                comp = text.find("lakh")
            check(
                "bhopal-before-compensation",
                "bhopal" in text[:comp],
                text[: comp + 40],
            )
            break
        else:
            check("bhopal-before-compensation", False, "compensation sentence missing from a single chunk")
    else:
        check("bhopal-before-compensation", False, "no compensation evidence")
    plan_text = " ".join(
        chunk.get("text") or ""
        for group in build_entity_plan("Explain Baji Rao I in detail.", baji, "bajirao")
        for chunk in group.chunks
    ).lower()
    comp_at = plan_text.find("compensation")
    if comp_at < 0:
        comp_at = plan_text.find("lakh")
    check(
        "plan-keeps-bhopal-with-compensation",
        comp_at > 0 and "bhopal" in plan_text[max(0, comp_at - 400) : comp_at],
        plan_text[max(0, comp_at - 180) : comp_at + 40],
    )
    baji_plan = build_entity_plan("Explain Baji Rao I in detail.", baji, "bajirao")
    readable = combine_entity_sections("bajirao", [(group, entity_readable([group])) for group in baji_plan]).lower()
    due = readable.find("due to this")
    check("draft-keeps-bhopal-cause", due > 0 and "bhopal" in readable[max(0, due - 350) : due], readable[max(0, due - 160) : due + 20])

    shivaji = entity_focus_evidence(chunks, "shivaji")
    shivaji_text = blob(shivaji)
    check("shivaji-not-shivaji-ii", "shivaji ii" not in shivaji_text)
    check("shivaji-not-tarabai", "tarabai" not in shivaji_text)
    admin = build_entity_plan("How did Shivaji administer his kingdom?", shivaji, "shivaji")
    admin = [group for group in admin if str(group.key).endswith(":administration")]
    admin_text = " ".join(chunk.get("text") or "" for group in admin for chunk in group.chunks).lower()
    check("shivaji-admin-present", "ryotwari" in admin_text and "justice" in admin_text)
    check("shivaji-admin-no-later-ruler", "shivaji ii" not in admin_text and "tarabai" not in admin_text and "rajaram" not in admin_text)

    akbar = blob(entity_focus_evidence(chunks, "akbar"))
    check("akbar-evidence-excludes-shivaji", "shivaji" not in akbar)
    check("shivaji-evidence-excludes-akbar", "akbar" not in shivaji_text)

    extra = 0
    for key in RULER_KEYS:
        if key in {"shivaji", "bajirao", "akbar"}:
            continue
        focused = entity_focus_evidence(chunks, key)
        if not focused:
            continue
        leaked = False
        for item in focused:
            for sentence in (item.get("text") or "").split(". "):
                subject, _how, _off = _resolve_subject(sentence, key)
                if subject in RULER_KEYS and subject != key:
                    leaked = True
        check(f"subject-boundary-{key}", not leaked)
        extra += 1
        if extra >= 5:
            break
    check("extra-rulers-checked", extra >= 5, f"only {extra}")

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

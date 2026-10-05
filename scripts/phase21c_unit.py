"""Phase 21C unit checks: intent, fingerprints, MCQ shape. No Express, no llama3."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.engine.intent import (
    collect_task_state,
    infer_previous_task,
    is_more_followup,
    requested_item_count,
)
from rag.engine.mcq import fingerprint, fingerprints_from_answer, mcqs_from_pack
from rag.engine.pack import build_evidence_pack
from rag.vectorstore.retrieve import retrieve_primary

PHRASES = (
    "more",
    "more questions",
    "give me more",
    "another 10",
    "continue",
    "more mcqs",
    "next 10",
    "give me another set",
)


def stems(answer: str) -> list[str]:
    return [match.group(1).strip().lower() for match in re.finditer(r"^\d+\.\s+(.+)$", answer or "", re.M)]


def option_lens(answer: str) -> list[int]:
    return [len(match.group(1).strip()) for match in re.finditer(r"^[A-D]\.\s+(.+)$", answer or "", re.M)]


def main() -> int:
    failed = []
    for phrase in PHRASES:
        if not is_more_followup(phrase):
            failed.append(f"more-phrase:{phrase}")
    if requested_item_count("give me 10 mcqs about the mughals") != 10:
        failed.append("count-10")
    if requested_item_count("another 10") != 10:
        failed.append("count-another-10")
    if requested_item_count("give me 20 mcqs about akbar") != 20:
        failed.append("count-20")

    truncated = {
        "type": "MCQ",
        "topic": "mughal",
        "fingerprints": ["aaaa", "bbbb"],
        "count": 10,
    }
    history = [
        {"role": "user", "content": "give me 10 mcqs about the mughals"},
        {"role": "assistant", "content": "1. Incomplete because of truncation", "task_state": truncated},
    ]
    if infer_previous_task(history, truncated) != "MCQ":
        failed.append("infer-mcq-from-task-state")
    collected = collect_task_state(history, truncated)
    if "aaaa" not in collected.get("fingerprints", []):
        failed.append("collect-fingerprints")

    hits = retrieve_primary("Mughal Babur Humayun Akbar Shah Jahan Aurangzeb", top_k=16, language="en")
    pack = build_evidence_pack(
        "give me 10 mcqs about the mughals",
        "Mughal Babur Humayun Akbar Shah Jahan Aurangzeb",
        "BROAD_TOPIC",
        raw_hits=hits,
    )
    first, fps = mcqs_from_pack("give me 10 mcqs about the mughals", pack.chunks, count=10)
    if not first:
        failed.append("mcq-empty")
    else:
        n = len(re.findall(r"^\d+\.\s+", first, re.M))
        if n < 5:
            failed.append(f"mcq-too-few:{n}")
        if len(set(stems(first))) != len(stems(first)):
            failed.append("mcq-duplicate-stems")
        if any(length > 80 for length in option_lens(first)):
            failed.append("mcq-long-options")
        if len(set(fps)) != len(fps):
            failed.append("mcq-duplicate-fingerprints")
        second, fps2 = mcqs_from_pack(
            "give me 10 mcqs about the mughals",
            pack.chunks,
            count=10,
            previous_fingerprints=fps,
            previous_answer=first[:2000],
        )
        overlap = set(stems(first)) & set(stems(second))
        if overlap:
            failed.append(f"more-overlap:{sorted(overlap)[:3]}")
        if set(fps) & set(fps2):
            failed.append("more-fingerprint-overlap")
        parsed = fingerprints_from_answer(first)
        if parsed and parsed != fps[: len(parsed)] and set(parsed) != set(fps):
            # Allow order-equal fingerprints reconstructed from text.
            if set(parsed) != set(fps):
                failed.append("fingerprint-roundtrip")

    dummy = fingerprint("In which language did Babur write an autobiography?", "Turkish")
    skipped, _ = mcqs_from_pack(
        "give me 10 mcqs about the mughals",
        pack.chunks,
        count=10,
        previous_fingerprints=[dummy],
    )
    if "In which language did Babur write an autobiography?" in first:
        if "In which language did Babur write an autobiography?" in skipped:
            failed.append("skip-specific-fingerprint")

    print("FAIL" if failed else "PASS", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Small deterministic sample derived from the fact index.

One direct question per predicate. This is not the corpus-wide coverage result.
Run scripts/fact_corpus_harness.py for that.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from rag.engine.facts import corpus_index
from fact_corpus_harness import evaluate_case, generate_cases


def main() -> int:
    index = corpus_index()
    chosen = {}
    for case in generate_cases(index):
        if case.category != "A" or case.expect != "supported":
            continue
        chosen.setdefault(case.predicate, case)
    print("representative sample only; not corpus-wide coverage")
    failed = 0
    for predicate in sorted(chosen):
        result = evaluate_case(chosen[predicate], index)
        print(
            result.verdict,
            predicate,
            result.question,
            result.failure or result.status,
        )
        if result.verdict != "PASS":
            failed += 1
            print(" ", (result.actual or "").replace("\n", " | ")[:240])
    print(f"representative {len(chosen) - failed}/{len(chosen)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

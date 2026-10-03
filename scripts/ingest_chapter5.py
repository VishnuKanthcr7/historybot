"""Ingest Chapter 5 (PDF pages 3–16) from the Class 9 Social Science Part 2 textbook."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.ingestion.pipeline import run_ingest


def main() -> int:
    summary = run_ingest()
    print(json.dumps({k: v for k, v in summary.items() if k != "char_count_per_page"}, ensure_ascii=False, indent=2))
    print("char_count_per_page:")
    for row in summary["char_count_per_page"]:
        print(
            f"  pdf={row['pdf_page_number']} textbook={row['textbook_page_number']} chars={row['char_count']}"
        )
    ok = summary["validation"]["all_passed"]
    print("VALIDATION", "PASS" if ok else "FAIL")
    if not ok:
        print("failed_checks:", summary["validation"]["failed"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

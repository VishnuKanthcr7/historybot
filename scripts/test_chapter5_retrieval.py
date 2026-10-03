"""Vector retrieval test only. Does not call an LLM."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.vectorstore.config import CHAT_TOP_K
from rag.vectorstore.retrieve import retrieve

QUESTIONS = [
    "Who established the Moghul rule in India?",
    "What was Din-e-Ilahi?",
    "What were the main features of Shivaji's administration?",
    "What is guerilla warfare according to the textbook?",
    "Who built the Taj Mahal?",
]


def main() -> int:
    report = []
    for question in QUESTIONS:
        hits = retrieve(question, top_k=CHAT_TOP_K)
        report.append(
            {
                "question": question,
                "top_k": CHAT_TOP_K,
                "hits": hits,
                "top_textbook_pages": [hit["textbook_page_number"] for hit in hits],
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

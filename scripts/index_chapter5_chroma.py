"""Index Phase 4 Chapter 5 chunks into persistent ChromaDB."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.vectorstore.chroma_store import get_client, inspect_collection
from rag.vectorstore.config import COLLECTION_NAME, EXPECTED_CHUNK_COUNT
from rag.vectorstore.index import index_chunks


def main() -> int:
    existing = inspect_collection()
    print("existing_collection:", json.dumps(existing, ensure_ascii=False, default=str))
    result = index_chunks()
    print("index_result:", json.dumps({k: v for k, v in result.items() if k != "ids"}, indent=2))

    client = get_client()
    first_count = inspect_collection(client)["count"]
    del client
    reopened = get_client()
    second = inspect_collection(reopened)
    print("persistence_reopen_count:", second["count"])
    print("persistence_ok:", first_count == second["count"] == EXPECTED_CHUNK_COUNT)
    print("collection:", COLLECTION_NAME)
    return 0 if first_count == EXPECTED_CHUNK_COUNT else 1


if __name__ == "__main__":
    raise SystemExit(main())

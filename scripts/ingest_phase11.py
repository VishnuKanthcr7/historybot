"""Extract Phase 11 pages/chunks and index historybot_class9_ss_v2. Leaves historybot_class9_ss untouched."""

from __future__ import annotations

import json

from rag.ingestion.v2 import run_phase11_extract
from rag.vectorstore.chroma_store import inspect_collection
from rag.vectorstore.config import COLLECTION_NAME
from rag.vectorstore.index_v2 import index_phase11


def main() -> None:
    before = inspect_collection(name=COLLECTION_NAME)
    print("OLD_BEFORE", json.dumps({"name": COLLECTION_NAME, "count": None if not before else before["count"]}))
    extracted = run_phase11_extract()
    print("EXTRACT", json.dumps({k: extracted[k] for k in extracted if k != "chunks"}, ensure_ascii=False, indent=2))
    indexed = index_phase11(extracted["chunks"])
    print("INDEX", json.dumps(indexed, ensure_ascii=False, indent=2))
    after = inspect_collection(name=COLLECTION_NAME)
    print("OLD_AFTER", json.dumps({"name": COLLECTION_NAME, "count": None if not after else after["count"]}))
    if before and after and before["count"] != after["count"]:
        raise SystemExit("Old collection count changed.")


if __name__ == "__main__":
    main()

"""Start the internal RAG HTTP service on 127.0.0.1 only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

import uvicorn


def main() -> None:
    secret = os.environ.get("INTERNAL_RAG_SECRET") or os.environ.get("RAG_INTERNAL_SECRET")
    if not secret:
        raise SystemExit("INTERNAL_RAG_SECRET is required")
    uvicorn.run(
        "rag.internal_api:app",
        host="127.0.0.1",
        port=int(os.environ.get("RAG_INTERNAL_PORT", "8000")),
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()

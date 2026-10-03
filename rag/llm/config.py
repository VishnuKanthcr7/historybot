"""Runtime settings for the grounded answer engine. No secrets hardcoded."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except ImportError:
    pass

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip() or "ollama"
OLLAMA_BASE_URL = (
    os.environ.get("OLLAMA_BASE_URL")
    or os.environ.get("OLLAMA_HOST")
    or "http://127.0.0.1:11434"
).rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL") or os.environ.get("LLM_MODEL") or "llama3"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", OLLAMA_MODEL)

RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "5"))
# Starting cosine-distance cutoff from Phase 5 tests (not a proven accuracy guarantee).
# Guerilla-warfare hits were ~0.50; stronger Babar/Taj hits were ~0.15–0.31.
RAG_DISTANCE_THRESHOLD = float(os.environ.get("RAG_DISTANCE_THRESHOLD", "0.55"))
RAG_STRONG_DISTANCE = float(os.environ.get("RAG_STRONG_DISTANCE", "0.32"))
RAG_MIN_TOKEN_OVERLAP = int(os.environ.get("RAG_MIN_TOKEN_OVERLAP", "1"))
MAX_HISTORY_TURNS = 4
MAX_MESSAGE_CHARS = 2000
MAX_REGENERATIONS = 1

REFUSAL_EN = "This topic is not available in the textbook."
REFUSAL_KN = "ಈ ವಿಷಯ ನೀಡಲಾದ ಪಠ್ಯಪುಸ್ತಕದಲ್ಲಿ ಲಭ್ಯವಿಲ್ಲ."

"""Runtime settings for the grounded answer engine. No secrets hardcoded."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except ImportError:
    pass

# Provider selection (see rag/llm/client.py resolve_provider and docs/llm-provider.md):
# 1. HISTORYBOT_LLM_PROVIDER, when set, wins. It is the explicit dev/test switch
#    (the regression harnesses set it to "ollama" with OpenAI blocked).
# 2. Otherwise production behaviour: OpenAI when OPENAI_API_KEY is configured.
# 3. Otherwise LLM_PROVIDER (default "ollama").
# LLM_PROVIDER alone does not override a configured OpenAI key; that keeps the
# live site on OpenAI with the current .env.
LLM_PROVIDER = (os.environ.get("LLM_PROVIDER", "ollama").strip() or "ollama").lower()
HISTORYBOT_LLM_PROVIDER = os.environ.get("HISTORYBOT_LLM_PROVIDER", "").strip().lower()
# No cross-provider fallback unless set explicitly: "none" (default), "ollama", or "openai".
LLM_FALLBACK_PROVIDER = (os.environ.get("LLM_FALLBACK_PROVIDER", "none").strip() or "none").lower()
SUPPORTED_PROVIDERS = ("ollama", "openai")
OLLAMA_BASE_URL = (
    os.environ.get("OLLAMA_BASE_URL")
    or os.environ.get("OLLAMA_HOST")
    or "http://127.0.0.1:11434"
).rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL") or os.environ.get("LLM_MODEL") or "llama3"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", OLLAMA_MODEL)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "").strip() or "gpt-6.1-sol"
OPENAI_BASE_URL = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com").rstrip("/")
_REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low").strip().lower() or "low"
if OPENAI_REASONING_EFFORT not in _REASONING_EFFORTS:
    OPENAI_REASONING_EFFORT = "low"

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

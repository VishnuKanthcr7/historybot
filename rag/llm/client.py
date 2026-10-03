"""LLM client abstraction. Phase 6 uses local Ollama llama3 only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import LLM_PROVIDER, OLLAMA_BASE_URL, OLLAMA_MODEL


class LlmError(RuntimeError):
    pass


def complete(messages: list[dict], temperature: float = 0.1, max_tokens: int = 500) -> str:
    provider = LLM_PROVIDER.lower()
    if provider != "ollama":
        raise LlmError(
            f"LLM_PROVIDER={provider} is not enabled in Phase 6. Use ollama locally."
        )
    return _ollama_chat(messages, temperature=temperature, max_tokens=max_tokens)


def _ollama_chat(messages: list[dict], temperature: float, max_tokens: int) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise LlmError(f"Ollama chat failed: {exc}") from exc
    message = (body.get("message") or {}).get("content")
    if not message or not str(message).strip():
        raise LlmError("Ollama returned an empty message")
    return str(message).strip()

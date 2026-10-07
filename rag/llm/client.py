"""LLM client. OpenAI Responses API is primary when a key is configured; Ollama is the fallback."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from .config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_REASONING_EFFORT,
)

last_provider = ""
last_error = ""


class LlmError(RuntimeError):
    pass


def complete(messages: list[dict], temperature: float = 0.1, max_tokens: int = 500, timeout: int = 180) -> str:
    global last_provider, last_error
    if OPENAI_API_KEY:
        try:
            text = _openai_responses(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            last_provider = "openai"
            last_error = ""
            print(f"llm_provider=openai model={OPENAI_MODEL}", file=sys.stderr)
            return text
        except LlmError as exc:
            last_error = _redact(str(exc))
            print("llm_provider=ollama fallback=openai_failed", file=sys.stderr)
    elif LLM_PROVIDER.lower() != "ollama":
        raise LlmError(
            f"LLM_PROVIDER={LLM_PROVIDER} is not enabled. Use ollama locally in this phase."
        )
    text = _ollama_chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    last_provider = "ollama"
    return text


def _openai_responses(messages: list[dict], temperature: float, max_tokens: int, timeout: int) -> str:
    instructions, conversation = _split_messages(messages)
    budget = _output_budget(max_tokens)
    body = _response_body(instructions, conversation, temperature, budget, include_temperature=True)
    try:
        payload = _post_responses(body, timeout)
    except LlmError as exc:
        if "temperature" not in str(exc).lower():
            raise
        body = _response_body(instructions, conversation, temperature, budget, include_temperature=False)
        payload = _post_responses(body, timeout)
    text = _output_text(payload)
    if text:
        return text
    if _incomplete_for_length(payload):
        retry = _response_body(
            instructions,
            conversation,
            temperature,
            min(16000, budget * 2),
            include_temperature="temperature" in body,
        )
        payload = _post_responses(retry, timeout)
        text = _output_text(payload)
    if not text:
        raise LlmError("OpenAI returned an empty message")
    return text


def _response_body(
    instructions: str,
    conversation: list[dict],
    temperature: float,
    budget: int,
    include_temperature: bool,
) -> dict:
    body: dict = {
        "model": OPENAI_MODEL,
        "input": conversation,
        "max_output_tokens": budget,
        "reasoning": {"effort": OPENAI_REASONING_EFFORT},
        "store": False,
    }
    if instructions:
        body["instructions"] = instructions
    if include_temperature:
        body["temperature"] = temperature
    return body


def _post_responses(body: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        f"{OPENAI_BASE_URL}/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise LlmError("OpenAI request timed out") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LlmError(_public_error(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise LlmError("OpenAI request failed") from exc
    except OSError as exc:
        raise LlmError("OpenAI request failed") from exc


def _split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    instructions: list[str] = []
    conversation: list[dict] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        if role in {"system", "developer"}:
            if content.strip():
                instructions.append(content.strip())
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        conversation.append({"role": role, "content": content})
    if not conversation:
        conversation.append({"role": "user", "content": "Continue."})
    return "\n\n".join(instructions), conversation


def _output_budget(max_tokens: int) -> int:
    asked = max(16, int(max_tokens))
    return min(8000, max(asked + 1024, asked * 4))


def _output_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in {"output_text", "text"}:
                continue
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _incomplete_for_length(payload: dict) -> bool:
    details = payload.get("incomplete_details") or {}
    return payload.get("status") == "incomplete" and details.get("reason") == "max_output_tokens"


def _public_error(status: int, detail: str) -> str:
    message = ""
    try:
        parsed = json.loads(detail)
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or "")
    except json.JSONDecodeError:
        message = ""
    if not message:
        message = "request rejected"
    return f"OpenAI HTTP {status}: {_redact(message)[:300]}"


def _redact(text: str) -> str:
    if OPENAI_API_KEY:
        text = text.replace(OPENAI_API_KEY, "[redacted]")
    return text


def _ollama_chat(messages: list[dict], temperature: float = 0.1, max_tokens: int = 500, timeout: int = 180) -> str:
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(
            {
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LlmError("Ollama request failed") from exc
    message = payload.get("message") if isinstance(payload, dict) else None
    text = str((message or {}).get("content") or "").strip()
    if not text:
        raise LlmError("Ollama returned an empty message")
    return text

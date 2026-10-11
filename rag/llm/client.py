"""LLM client.

Which provider answers (resolve_provider):
1. HISTORYBOT_LLM_PROVIDER ("ollama" or "openai"), when set. Dev/test override.
2. Otherwise "openai" when OPENAI_API_KEY is configured (production behaviour).
3. Otherwise LLM_PROVIDER (default "ollama").
There is no automatic cross-provider fallback. A second provider is tried only when
LLM_FALLBACK_PROVIDER names it explicitly (default "none"). Errors never include keys.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from .config import (
    HISTORYBOT_LLM_PROVIDER,
    LLM_FALLBACK_PROVIDER,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_REASONING_EFFORT,
    SUPPORTED_PROVIDERS,
)

last_provider = ""
last_error = ""


class LlmError(RuntimeError):
    pass


def resolve_provider() -> tuple[str, str]:
    """(provider, reason). Names only, never keys."""
    override = (HISTORYBOT_LLM_PROVIDER or "").strip().lower()
    if override:
        if override not in SUPPORTED_PROVIDERS:
            raise LlmError(
                f"HISTORYBOT_LLM_PROVIDER={override} is not supported. Use one of: {', '.join(SUPPORTED_PROVIDERS)}."
            )
        return override, "HISTORYBOT_LLM_PROVIDER override"
    if OPENAI_API_KEY:
        return "openai", "OPENAI_API_KEY is configured"
    primary = (LLM_PROVIDER or "ollama").strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        raise LlmError(f"LLM_PROVIDER={primary} is not supported. Use one of: {', '.join(SUPPORTED_PROVIDERS)}.")
    return primary, "LLM_PROVIDER (no OpenAI key configured)"


def provider_plan() -> list[str]:
    """Providers to try, in order. Raises LlmError for a bad setting. Never includes a key."""
    primary, _reason = resolve_provider()
    plan = [primary]
    fallback = (LLM_FALLBACK_PROVIDER or "none").strip().lower()
    if fallback not in ("", "none", "off", "false", "0"):
        if fallback not in SUPPORTED_PROVIDERS:
            raise LlmError(f"LLM_FALLBACK_PROVIDER={fallback} is not supported. Use none, ollama, or openai.")
        if fallback != primary:
            plan.append(fallback)
    return plan


def describe_provider() -> dict:
    """Safe description for health checks and startup logs."""
    try:
        primary, reason = resolve_provider()
        plan = provider_plan()
    except LlmError as exc:
        return {"llm_provider": "invalid", "reason": str(exc), "fallback": "none"}
    return {
        "llm_provider": primary,
        "model": _model_for(primary),
        "reason": reason,
        "fallback": plan[1] if len(plan) > 1 else "none",
    }


def _model_for(provider: str) -> str:
    return OPENAI_MODEL if provider == "openai" else OLLAMA_MODEL


def _call(provider: str, messages: list[dict], temperature: float, max_tokens: int, timeout: int) -> str:
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise LlmError("LLM provider openai is selected but OPENAI_API_KEY is not set.")
        return _openai_responses(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    return _ollama_chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)


def complete(messages: list[dict], temperature: float = 0.1, max_tokens: int = 500, timeout: int = 180) -> str:
    global last_provider, last_error
    plan = provider_plan()
    errors: list[str] = []
    for index, provider in enumerate(plan):
        try:
            text = _call(provider, messages, temperature, max_tokens, timeout)
        except LlmError as exc:
            message = _redact(str(exc))
            errors.append(f"{provider}: {message}")
            last_error = message
            if index + 1 < len(plan):
                print(f"llm_provider={provider} failed; trying configured fallback={plan[index + 1]}", file=sys.stderr)
            continue
        last_provider = provider
        last_error = ""
        print(f"llm_provider={provider} model={_model_for(provider)}", file=sys.stderr)
        return text
    raise LlmError("LLM unavailable (" + "; ".join(errors) + ")")


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
    except urllib.error.HTTPError as exc:
        raise LlmError(f"Ollama HTTP {exc.code} for model {OLLAMA_MODEL}") from exc
    except TimeoutError as exc:
        raise LlmError("Ollama request timed out") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise LlmError(f"Ollama is not reachable at {OLLAMA_BASE_URL}") from exc
    message = payload.get("message") if isinstance(payload, dict) else None
    text = str((message or {}).get("content") or "").strip()
    if not text:
        raise LlmError("Ollama returned an empty message")
    return text

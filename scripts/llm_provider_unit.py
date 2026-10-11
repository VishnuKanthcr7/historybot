"""Unit tests for LLM provider selection. No network: urllib is mocked.

Proves:
1. The current .env combination (LLM_PROVIDER=ollama + an OpenAI key) resolves to OpenAI,
   with no Ollama fallback (production keeps answering via OpenAI).
2. Test mode (HISTORYBOT_LLM_PROVIDER=ollama) resolves to Ollama with zero OpenAI calls,
   even when an OpenAI key is present.
3. No silent fallback in either direction; a second provider only with LLM_FALLBACK_PROVIDER.
Run: python scripts/llm_provider_unit.py
"""
from __future__ import annotations

import importlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DUMMY_KEY = "sk-unit-test-not-a-real-key"
KEYS = ("LLM_PROVIDER", "HISTORYBOT_LLM_PROVIDER", "LLM_FALLBACK_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OLLAMA_BASE_URL")
calls: list[str] = []
fail_hosts: set[str] = set()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(request, timeout=None):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    calls.append(url)
    host = "openai" if "/v1/responses" in url else "ollama"
    if host in fail_hosts:
        raise urllib.error.URLError("unit-test: down")
    if host == "openai":
        return _Resp(json.dumps({"output_text": "openai-answer"}).encode())
    return _Resp(json.dumps({"message": {"content": "ollama-answer"}}).encode())


def load(env: dict[str, str]):
    # Every relevant variable is set explicitly, so the project .env (loaded with
    # override=False) cannot change the case under test.
    for key in KEYS:
        os.environ[key] = env.get(key, "")
    os.environ["OPENAI_BASE_URL"] = "https://api.openai.example"
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
    import rag.llm.config as config
    import rag.llm.client as client

    importlib.reload(config)
    client = importlib.reload(client)
    urllib.request.urlopen = fake_urlopen
    calls.clear()
    fail_hosts.clear()
    return client


def run_case(name, env, fail=(), expect_text=None, expect_error=False, expect_hosts=(), expect_provider=None):
    client = load(env)
    fail_hosts.update(fail)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    text, error = None, ""
    info = client.describe_provider()
    try:
        text = client.complete(msgs)
    except client.LlmError as exc:
        error = str(exc)
    hosts = ["openai" if "/v1/responses" in url else "ollama" for url in calls]
    reasons = []
    if expect_error and not error:
        reasons.append("expected error")
    if not expect_error and error:
        reasons.append(f"unexpected error: {error}")
    if expect_text is not None and text != expect_text:
        reasons.append(f"text={text!r}")
    if tuple(hosts) != tuple(expect_hosts):
        reasons.append(f"hosts={hosts}")
    if expect_provider and info.get("llm_provider") != expect_provider:
        reasons.append(f"resolved={info.get('llm_provider')}")
    if DUMMY_KEY in error or DUMMY_KEY in json.dumps(info):
        reasons.append("key leaked")
    ok = not reasons
    print(f"{'PASS' if ok else 'FAIL'} {name} resolved={info.get('llm_provider')} hosts={hosts} {'; '.join(reasons)}")
    return ok


K = DUMMY_KEY
CASES = [
    # (1) current .env combination -> OpenAI, no Ollama fallback
    ("prod .env (LLM_PROVIDER=ollama + key) -> openai", {"LLM_PROVIDER": "ollama", "OPENAI_API_KEY": K}, (), "openai-answer", False, ("openai",), "openai"),
    ("prod .env, OpenAI down -> clear error, NO ollama", {"LLM_PROVIDER": "ollama", "OPENAI_API_KEY": K}, ("openai",), None, True, ("openai",), "openai"),
    # (2) test mode -> Ollama, zero OpenAI calls, even with a key present
    ("test mode override + key -> only ollama", {"HISTORYBOT_LLM_PROVIDER": "ollama", "LLM_PROVIDER": "ollama", "OPENAI_API_KEY": K}, (), "ollama-answer", False, ("ollama",), "ollama"),
    ("test mode, Ollama down -> error, NO openai", {"HISTORYBOT_LLM_PROVIDER": "ollama", "OPENAI_API_KEY": K}, ("ollama",), None, True, ("ollama",), "ollama"),
    ("test mode, no key -> only ollama", {"HISTORYBOT_LLM_PROVIDER": "ollama"}, (), "ollama-answer", False, ("ollama",), "ollama"),
    ("override is case-insensitive", {"HISTORYBOT_LLM_PROVIDER": "OLLAMA", "OPENAI_API_KEY": K}, (), "ollama-answer", False, ("ollama",), "ollama"),
    # no key at all -> LLM_PROVIDER decides
    ("no key, LLM_PROVIDER=ollama -> ollama", {"LLM_PROVIDER": "ollama"}, (), "ollama-answer", False, ("ollama",), "ollama"),
    ("no key, LLM_PROVIDER=openai -> clear error, no calls", {"LLM_PROVIDER": "openai"}, (), None, True, (), None),
    ("override openai without key -> clear error, no calls", {"HISTORYBOT_LLM_PROVIDER": "openai"}, (), None, True, (), None),
    # (3) fallback only when explicit
    ("explicit fallback=ollama: openai down -> ollama", {"OPENAI_API_KEY": K, "LLM_FALLBACK_PROVIDER": "ollama"}, ("openai",), "ollama-answer", False, ("openai", "ollama"), "openai"),
    ("explicit fallback=openai: ollama down -> openai", {"HISTORYBOT_LLM_PROVIDER": "ollama", "OPENAI_API_KEY": K, "LLM_FALLBACK_PROVIDER": "openai"}, ("ollama",), "openai-answer", False, ("ollama", "openai"), "ollama"),
    ("fallback=none explicit -> error, single provider", {"OPENAI_API_KEY": K, "LLM_FALLBACK_PROVIDER": "none"}, ("openai",), None, True, ("openai",), "openai"),
    ("unknown override -> error, no calls", {"HISTORYBOT_LLM_PROVIDER": "gemini", "OPENAI_API_KEY": K}, (), None, True, (), None),
    ("unknown LLM_PROVIDER without key -> error, no calls", {"LLM_PROVIDER": "gemini"}, (), None, True, (), None),
    ("bad fallback -> error, no calls", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": "claude"}, (), None, True, (), None),
]


def depth_followup_openai_down() -> bool:
    """A 'tell me more' follow-up in production mode with OpenAI down: clear error, no Ollama call."""
    client = load({"LLM_PROVIDER": "ollama", "OPENAI_API_KEY": DUMMY_KEY})
    fail_hosts.add("openai")
    import rag.engine.answer as answer

    answer = importlib.reload(answer)  # bind the reloaded client.complete
    chunk = {"chunk_id": "m1", "printed_page_number": 7, "textbook_page_number": 7, "authority": "primary",
             "text": "Akbar had established many hierarchies in his army. These were called Mansabs and its supervisors were called Mansabdars."}
    answer.retrieve_primary = lambda *a, **k: [dict(chunk)]
    answer.topic_supported_by_primary = lambda q: None
    history = [{"role": "user", "content": "Explain the Mansabdari system."},
               {"role": "assistant", "content": "The Mansabdari system organised the army into ranks called Mansabs."}]
    error = ""
    try:
        answer.answer_question("Can you tell me more about this, I mean the Mansabdari system?", "en", history, None)
    except client.LlmError as exc:
        error = str(exc)
    hosts = ["openai" if "/v1/responses" in url else "ollama" for url in calls]
    ok = bool(error) and hosts and all(h == "openai" for h in hosts) and DUMMY_KEY not in error
    print(f"{'PASS' if ok else 'FAIL'} depth follow-up, OpenAI down -> clear error, NO ollama hosts={hosts} error={error[:80]!r}")
    importlib.reload(answer)
    return bool(ok)


def main() -> int:
    original = urllib.request.urlopen
    saved = {key: os.environ.get(key) for key in KEYS}
    try:
        results = [run_case(*case) for case in CASES]
        results.append(depth_followup_openai_down())
    finally:
        urllib.request.urlopen = original
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    passed = sum(results)
    print(f"llm_provider_unit {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

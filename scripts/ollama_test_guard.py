"""Dev/test guard: forces Ollama, blocks and counts any OpenAI attempt. Never for production.

Usage:
  python scripts/ollama_test_guard.py run <script.py> [args...]
  python scripts/ollama_test_guard.py serve <port>
Set HISTORYBOT_GUARD_STATE to write the counters as JSON.
"""
import atexit
import json
import os
import runpy
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["OPENAI_API_KEY"] = ""          # present but empty: dotenv(override=False) keeps it empty
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["HISTORYBOT_LLM_PROVIDER"] = "ollama"   # explicit dev/test override
os.environ["LLM_FALLBACK_PROVIDER"] = "none"
sys.path.insert(0, str(ROOT))
STATE = Path(os.environ.get("HISTORYBOT_GUARD_STATE") or os.environ.get("STAGE3_GUARD_STATE") or (ROOT / "tmp" / "final-dev" / "guard-state.json"))
STATS = {"openai_attempts": 0, "openai_http": 0, "ollama_calls": 0, "last_provider": ""}

_real_urlopen = urllib.request.urlopen


def _guarded_urlopen(req, *args, **kwargs):
    url = getattr(req, "full_url", None) or str(req)
    if "openai.com" in url or "/v1/responses" in url:
        STATS["openai_http"] += 1
        _save()
        raise RuntimeError("OpenAI blocked by test guard")
    return _real_urlopen(req, *args, **kwargs)


urllib.request.urlopen = _guarded_urlopen

import rag.llm.config as cfg  # noqa: E402
import rag.llm.client as client  # noqa: E402

assert cfg.OPENAI_API_KEY == "" and client.OPENAI_API_KEY == "", "OpenAI key present in test process"
assert cfg.LLM_PROVIDER.lower() == "ollama"
assert client.resolve_provider()[0] == "ollama" and client.provider_plan() == ["ollama"], "provider must resolve to ollama only"


def _blocked(*args, **kwargs):
    STATS["openai_attempts"] += 1
    _save()
    raise client.LlmError("OpenAI blocked by test guard")


client._openai_responses = _blocked
client._post_responses = _blocked
_real_ollama = client._ollama_chat


def _counted(*args, **kwargs):
    STATS["ollama_calls"] += 1
    text = _real_ollama(*args, **kwargs)
    STATS["last_provider"] = "ollama"
    _save()
    return text


client._ollama_chat = _counted


def _save():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    data = dict(STATS, provider=client.resolve_provider()[0], model=cfg.OLLAMA_MODEL,
                openai_key_set=bool(client.OPENAI_API_KEY), target=sys.argv[1:3])
    STATE.write_text(json.dumps(data), encoding="utf-8")


def _report():
    _save()
    print(
        f"TEST_GUARD provider={client.resolve_provider()[0]} model={cfg.OLLAMA_MODEL} "
        f"openai_key_set={bool(client.OPENAI_API_KEY)} openai_attempts={STATS['openai_attempts']} "
        f"openai_http={STATS['openai_http']} ollama_calls={STATS['ollama_calls']}",
        file=sys.stderr,
        flush=True,
    )


atexit.register(_report)

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "serve":
        import uvicorn
        from rag.internal_api import app

        _save()
        uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
    else:
        script = str(Path(sys.argv[2]).resolve())
        sys.argv = [script] + sys.argv[3:]
        runpy.run_path(script, run_name="__main__")

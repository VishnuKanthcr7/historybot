# LLM provider selection

HistoryBot's RAG service (`rag/llm/client.py`) picks one LLM provider per process.

## Resolution order

1. `HISTORYBOT_LLM_PROVIDER` (`ollama` or `openai`). This is the explicit **dev/test override**.
   Test harnesses (`scripts/ollama_test_guard.py`, `scripts/final_answer_quality_regression.py`)
   set it to `ollama`, empty `OPENAI_API_KEY` and block OpenAI at the network level.
   Do not set it in production.
2. Otherwise, **production behaviour**: `openai` when `OPENAI_API_KEY` is configured.
3. Otherwise `LLM_PROVIDER` (default `ollama`).

`LLM_PROVIDER` alone does **not** override a configured OpenAI key. With the current `.env`
(`LLM_PROVIDER=ollama` plus an OpenAI key) the service resolves to **OpenAI**. To make the file
self-explanatory you may set `LLM_PROVIDER=openai`; behaviour is the same.

## Fallback

There is no automatic cross-provider fallback. If the selected provider fails, the request fails
with a clear error (`LLM unavailable (openai: ...)`), and keys never appear in errors or logs.
To allow a second provider, set it explicitly:

```
LLM_FALLBACK_PROVIDER=ollama   # OpenAI first, Ollama only if OpenAI fails
LLM_FALLBACK_PROVIDER=none     # default
```

Note: the code that ran before this change fell back to Ollama silently when OpenAI failed.
Set `LLM_FALLBACK_PROVIDER=ollama` if you want to keep that behaviour on purpose.

## Checking which provider is active (no paid call)

- At startup `scripts/rag_internal_server.py` prints
  `HistoryBot RAG llm_provider=<name> model=<model> reason=<why> fallback=<name>` to stderr.
- `GET /internal/health` (internal secret required) returns the same fields.
- Each completion logs `llm_provider=<name> model=<model>` to stderr.

## Tests

`python scripts/llm_provider_unit.py` (mocked HTTP, no network) proves:
the current `.env` combination resolves to OpenAI with no Ollama fallback; test mode resolves to
Ollama with zero OpenAI calls even when a key exists; and no fallback happens unless
`LLM_FALLBACK_PROVIDER` is set.

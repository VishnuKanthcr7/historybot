# Testing HistoryBot without paid AI calls

Production answers come from OpenAI (see `llm-provider.md`). **Every AI test must run in Ollama-only
test mode** so no paid call can happen. Do not run the old `scripts/phase*_regression.py` scripts
directly with the normal `.env`: with an OpenAI key configured they would call OpenAI. Wrap them:

    python scripts\ollama_test_guard.py run scripts\<script>.py [args]

The guard empties `OPENAI_API_KEY`, sets `HISTORYBOT_LLM_PROVIDER=ollama` and
`LLM_FALLBACK_PROVIDER=none`, blocks OpenAI URLs at the network layer, asserts the provider plan is
`["ollama"]`, and prints `TEST_GUARD ... openai_attempts=0 openai_http=0 ollama_calls=N` at exit.

## No-AI tests (safe any time)

| Command | What it checks |
|---|---|
| `python scripts\final_unit_tests.py` | sanitizer, PDF markup, refusal guard, rare-term rescue, bullet shortening, e-content labels/pronouns |
| `python scripts\llm_provider_unit.py` | provider selection with mocked HTTP (production => OpenAI, test mode => Ollama, no silent fallback) |
| `python scripts\ollama_test_guard.py run scripts\fact_layer_unit.py` | fact layer |
| `python scripts\ollama_test_guard.py run scripts\phase21c_unit.py` | request/route units |

## Test instances (never the live :3000 / :8000)

    python scripts\ollama_test_guard.py serve 8100                    # RAG, Ollama only
    set PORT=3100 & set RAG_INTERNAL_URL=http://127.0.0.1:8100 & node backend\src\server.js

Then, with `HISTORYBOT_TEST_API=http://127.0.0.1:3100/api/v1`:

| Command | What it checks |
|---|---|
| `node backend\scripts\privacy-test.mjs` | cross-account access, token expiry/logout, input errors (400/413/404), no secrets in responses (no AI calls) |
| `node backend\scripts\auth-media-test.mjs` | sign-in rules, admin separation, image matching (incl. future assets) and protected image delivery |
| `node backend\scripts\ai-usage-test.mjs run` | persistent daily AI limit (use AI_DAILY_LIMIT=2 and a dead RAG URL; see the script header) |
| `HISTORYBOT_TEST_RAG=http://127.0.0.1:8100 node backend\scripts\smoke-test.mjs` | authenticated end-to-end chat; refuses to ask anything unless the RAG reports provider=ollama |
| `RAG_DOWN=1 node backend\scripts\smoke-test.mjs` (backend pointed at a dead RAG) | clear 502 RAG_UNAVAILABLE |

All of these create their own accounts and delete only those rows.

## Answer-quality regression (Ollama, ~15 min)

    python scripts\final_answer_quality_regression.py [--only id1,id2] [--out file.json]

33 textbook questions (terms, follow-ups, typos, tables, exam answers, off-topic). The script sets
test mode itself and fails if the provider plan is not `["ollama"]`.
Sentence-length checks depend on the local model; llama3 is occasionally above the 24-word
average on long exam answers.

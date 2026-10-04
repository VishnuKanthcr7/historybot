# Phase 13 — Production LLM and embedding provider evaluation

**Date:** 2026-10-04  
**Base commit:** `256d3fe12a746cf67fdcf6cebde303b8058a6d3d` (`phase-12-production-readiness-audit`)  
**Scope:** Evaluation only. No deploy, no purchase, no `.env` changes, no API keys, no Ollama replacement, no Chroma rebuild, no schema change.

**Live API tests:** none. Quality, Kannada, latency, and prices below are **architecture estimates** from current HistoryBot code plus **publicly known provider shapes**. Anything that needs a key is marked **NEEDS LIVE VALIDATION**. Pricing is **Must verify before purchase.**

---

## 1. Current architecture

Inspected in `rag/llm/client.py`, `rag/llm/config.py`, `rag/vectorstore/embeddings.py`, `rag/vectorstore/retrieve.py`, `rag/engine/answer.py`, `rag/engine/econtent.py`, `rag/engine/normalize.py`, `rag/engine/validate.py`, `rag/prompts/tutor.py`, `rag/prompts/econtent.py`, `rag/pdf/render.py`.

```
Student question
  → normalize (max 2000 chars)
  → casual?  (no LLM)
  → mode: NORMAL | DETAILED | ECONTENT
  → optional rewrite LLM  (follow-up pronouns or Kannada → English search)
  → embed query with nomic-embed-text  (768-d)
  → Chroma historybot_class9_ss_v2
       primary  top_k=5 (e-content retrieve 8+, keep 5)
       detailed/e-content also supplementary  top_k=5 or 8, keep 3
  → evidence filter (distance 0.55 / strong 0.32 / token overlap)
  → LLM complete(system + user evidence)   Ollama llama3 only
  → validate; at most one stricter retry
  → citations attached in Python (not by the model)
  → e-content: 8–9 JSON section LLM calls, then ReportLab PDF (no LLM)
```

| Piece | Current code |
|---|---|
| LLM abstraction | `complete(messages, temperature, max_tokens, timeout)` |
| Provider gate | `LLM_PROVIDER` must be `ollama` or it **raises**. `LLM_BASE_URL` / `LLM_API_KEY` exist and are **unused**. |
| Ollama client | `POST {OLLAMA_BASE_URL}/api/chat`, `stream: false`, `options.temperature`, `options.num_predict` |
| Chat model | `llama3` (`OLLAMA_MODEL` / `LLM_MODEL`) |
| Embedding client | `POST {OLLAMA_HOST}/api/embeddings`, model **must** be `nomic-embed-text` |
| Embedding dim | **768** (inspected on v2) |
| Chroma | Active `historybot_class9_ss_v2` (**161** docs). Legacy `historybot_class9_ss` (67) unused. Cosine space. Query vectors supplied by the app, not Chroma’s default embedder. |
| Evidence limits | Chat: keep **3** primary chunks (`select_evidence` `max_keep=3`). Detailed: + **3** supplementary. E-content: keep 5 primary + 3 supp; each section packs 2–4 chunks, text **truncated to 900 chars**. |
| Prompt construction | Fixed `SYSTEM_PROMPT` + user block with labelled PRIMARY/SUPPLEMENTARY evidence. DETAILED requires two markdown headings. |
| Answer validation | Leak markers, refusal detection, DETAILED heading split, Kannada fallback. One regeneration (`MAX_REGENERATIONS = 1`). |
| Follow-up rewrite | Separate LLM call, `max_tokens=80`, previous **user** questions only. History is **not** sent as multi-turn chat to the answer model. |
| Detailed flow | Extra supplementary retrieve; `max_tokens=700`; on validation fail, retry then fall back to NORMAL primary-only. |
| E-content flow | Up to **9** `SECTION_SPECS` calls (`max_tokens` 180–500, timeout 75s). English skips `simple_kannada`. PDF is ReportLab only. |
| PDF flow | **No LLM.** |

Do not change this stack in this phase.

---

## 2. Requirements

### LLM

- HTTPS API; **prefer OpenAI-compatible** `/v1/chat/completions` so `complete()` can grow a second branch without rewriting the engine.
- Context window: **at least ~8k tokens** practical; **32k+ comfortable** (see §4). Do not shrink evidence to fit a tiny window.
- Strong instruction following (ground to evidence, JSON for e-content, exact DETAILED headings, exact refusal sentences).
- Strong simple English for Class 9.
- Usable Kannada **generation** if bilingual launch happens later. That is **not** the same as Kannada RAG.
- Latency: chat should not rely on the current **180s** Ollama timeout; target **a few seconds** typical.
- Predictable, low cost relative to an **₹18,000** project (monthly AI should stay a small fraction of that fee).
- Structured prompts / JSON object output for e-content.
- Long textbook evidence in the user message (several chunks).
- Suitable for **anonymous public students** (no end-user OAuth).
- Provider-side rate limits plus app-side caps.
- **No self-hosted GPU requirement.**

### Embeddings

- HTTPS API **or** a small local VPS model.
- Deterministic enough that the same query retrieves the same neighbourhood.
- Semantic retrieval for short history questions.
- Stable named model (no silent replacement).
- Dimension: **768 today**. A different dimension is allowed only with a **controlled Chroma rebuild** (not now).
- Low cost; avoid locking retrieval to a single expensive vendor.

---

## 3. Test workload

Same questions as the source-aware eval set. **Not executed against any paid API in this phase.**

| # | Type | Question | What the provider must do |
|---|---|---|---|
| 1–8 | NORMAL | Babar, Akbar, Shivaji, Baji Rao I, Din-e-Ilahi, Taj Mahal, after Third Panipat, guerilla warfare | Short grounded English; first-sentence fact; no extra-corpus biography |
| 9–10 | FOLLOW-UP | Who was Babar? / What did he do after that? | Rewrite pronouns; retrieve Babar, not a new entity |
| 11–14 | DETAILED | More about Shivaji; Shivaji administration; Mughal administration; mansabdari | Two headings; PRIMARY vs NCERT/extra; mansabdari may be limited on primary |
| 15–17 | E-CONTENT | Shivaji / Marathas / Mughals | Many JSON sections; no Wikipedia |
| 18–20 | UNSUPPORTED | GDP; Plassey; current PM | Refusal after weak evidence — often **no successful grounded generation** |
| 21–22 | INJECTION | Wikipedia; VisionIAS | Treat as question; refuse if primary evidence insufficient |

Success is **grounding**, not fluency. A cheaper model that invents pages fails this product.

---

## 4. Context analysis

**Measured on this machine (read-only):** 161 v2 documents; chunk length min 235 / median 614 / p90 762 / max 1018 / mean **611 characters**. `SYSTEM_PROMPT` **2066** chars. `REWRITE_PROMPT` **459**. `ECONTENT_SYSTEM` **634**. Nine e-content specs, sum of `max_tokens` **3140**.

Assumption used below: **~4 English characters ≈ 1 token**. Labelled as an assumption.

| Workload | Chunks in prompt | Approx input tokens | `max_tokens` output cap | Extra LLM calls |
|---|---|---|---|---|
| Rewrite (follow-up / Kannada) | 0 evidence | ~150–400 | 80 | 1 |
| NORMAL | 3 × ~611 chars | **~1,100–1,600** | 450 | +1 if validation fails |
| DETAILED | 3 primary + 3 supp | **~1,800–2,600** | 700 | retry; may fall back to NORMAL |
| E-content (English, 8 sections) | 2–4 chunks × 900-char cap per section | **~7,000–11,000** total across calls | 280–500 each; ~2,500–3,000 if all succeed | up to 8 retries |
| PDF | — | 0 | 0 | 0 |

**Maximum single prompt** today is DETAILED or one fat e-content section: still **well under 8k tokens**. A **4k** window is tight if chunks grow; **8k is the practical minimum**; **32k+** is plenty and avoids future chapter growth forcing prompt cuts.

Do **not** drop supplementary evidence to fit a small model. Grounding quality outranks provider convenience.

All Groq Llama 3.x, Gemini Flash, and typical OpenRouter chat models advertise **8k–128k+** context. **None of the categories below fail on context size** for the current 161-chunk corpus. **NEEDS LIVE VALIDATION** for actual tokenizer counts.

---

## 5. Provider comparison

No accounts, no keys, no paid calls.

| Provider | Candidate model (example, not purchased) | LLM API | Context | English | Kannada gen. | Cost | Latency | OpenAI-compatible | Production suitability |
|---|---|---|---|---|---|---|---|---|---|
| **A. Groq-class** | Llama 3.3 70B instruct **or** Llama 3.1 8B if budget-capped | Hosted chat | GOOD (typically 8k–128k class) | GOOD (70B) / FAIR (8B; local `llama3` already showed grounding retries) | UNKNOWN | GOOD (historically low; **Must verify before purchase**) | GOOD (known for fast tokens) | GOOD | GOOD for English-first if caps exist |
| **B. Gemini-class** | Gemini Flash / Flash-Lite class | Google AI HTTP; optional OpenAI-compat shim **NEEDS LIVE VALIDATION** | GOOD (large advertised windows) | GOOD | FAIR (often stronger on Indic scripts than small Llamas; **not proven here**) | GOOD | GOOD | FAIR | GOOD if adapter is confirmed |
| **C. OpenRouter-style** | Same models as A/B via one key | OpenAI-style router | GOOD | GOOD/FAIR (depends on routed model) | UNKNOWN | FAIR (upstream + markup; **Must verify**) | FAIR | GOOD | FAIR (easy failover; extra hop, extra policy) |
| **D. Other known OpenAI-compat** (Together / Fireworks / DeepSeek-class) | Llama 70B or cheap chat SKUs | HTTPS chat completions | GOOD | GOOD/FAIR | UNKNOWN | GOOD/FAIR | GOOD/FAIR | GOOD | FAIR until a SKU is live-tested |
| **Local Ollama (current)** | `llama3` | localhost, not public HTTPS | FAIR | FAIR | POOR/UNKNOWN | GOOD (electricity only) | POOR on CPU VPS | POOR (custom `/api/chat`) | POOR as public production chat |
| **Self-hosted llama3 on cheap VPS** | same | local | FAIR | FAIR | POOR | POOR (RAM/time) | POOR without GPU | POOR | POOR |

**Kannada column is generation only.** Textbook-Kannada RAG stays **BLOCKED** (Nudi).

---

## 6. Cost assumptions

**Must verify before purchase.** These are **not invoices**.

**Mix (assumption):** of student questions: **75% NORMAL**, **15% DETAILED**, **5% E-CONTENT**, **5% refuse** after retrieve (embed only or tiny unused call). **20%** of chats also run a **rewrite**. **15%** of grounded chats run a **validation retry**. PDF = **0 LLM tokens**. Actual billed output assumed **below** `max_tokens` (NORMAL ~200, DETAILED ~400, e-content ~220/section × 8).

**Approx LLM tokens per average question** (blend): **~2,400 input + ~350 output**.  
**Embeddings:** 1–2 short queries (~50 tokens each). Local nomic ⇒ **$0**. Hosted embed ⇒ small extra.

**Illustrative unit prices used only for arithmetic** (public ballpark, often outdated):

| SKU class | Input / 1M tokens | Output / 1M tokens |
|---|---|---|
| Groq-class Llama 8B | $0.05 | $0.08 |
| Groq-class Llama 70B | $0.59 | $0.79 |
| Gemini Flash-class | $0.10 | $0.40 |
| OpenRouter | ~underlying + **unknown markup** | same |

School holidays vs exam season will swing real spend. **Do not assume a free forever tier.**

---

## 7. Small usage estimate — Scenario A

**100 questions/day × 30 ≈ 3,000 / month**

| | Input tok/mo | Output tok/mo |
|---|---|---|
| Blend | ~7.2M | ~1.05M |

| SKU class | Est. LLM $/month | Embed (keep nomic local) |
|---|---|---|
| Llama 8B-class | **~$0.4** | $0 |
| Llama 70B-class | **~$5** | $0 |
| Gemini Flash-class | **~$1.1** | $0 |

Order of magnitude: **well under ₹500/month** if prices still resemble the table. **Must verify before purchase.**

---

## 8. Medium usage estimate — Scenario B

**500 questions/day × 30 ≈ 15,000 / month**

| | Input | Output |
|---|---|---|
| Blend | ~36M | ~5.3M |

| SKU class | Est. LLM $/month |
|---|---|
| Llama 8B-class | **~$2** |
| Llama 70B-class | **~$25** |
| Gemini Flash-class | **~$6** |

**₹18,000 project implication:** 70B-class at medium traffic can become a **recurring** cost larger than a single month of “AI budget” if the whole fee must also cover VPS. Flash-class or 8B-class stay small **if** e-content stays ~5% of traffic. Uncapped e-content (8 LLM calls each) is the spike.

---

## 9. Large usage estimate — Scenario C

**2,000 questions/day × 30 ≈ 60,000 / month**

| | Input | Output |
|---|---|---|
| Blend | ~144M | ~21M |

| SKU class | Est. LLM $/month |
|---|---|
| Llama 8B-class | **~$9** |
| Llama 70B-class | **~$100** |
| Gemini Flash-class | **~$23** |

At this scale, **daily global budgets** are mandatory. 70B-class without caps can exceed the spirit of an ₹18,000 build. Prefer Flash-class **or** 70B with a hard rupee/day stop.

OpenRouter: add unknown percent; treat as **≥** the chosen upstream.

Hosted embeddings (if used): often on the order of **$0.01–0.10 / 1M tokens**. Query volume is tiny vs chat. Rebuild of 161 chunks is negligible money; **compatibility** is the issue, not cost.

---

## 10. Kannada analysis

| Layer | Status |
|---|---|
| **A. Kannada generation** | Prompt already asks for 2–4 Kannada-script sentences. Local `llama3` was **uneven**. Gemini-class is the better **candidate** for Indic script; Groq Llama is **UNKNOWN**. **NEEDS LIVE VALIDATION.** No provider “solves Kannada.” |
| **B. Kannada textbook RAG** | **BLOCKED** until Unicode Kannada chunks exist. Rewrite-to-English retrieval still uses **English** primary `source_type`. Switching LLM does **not** ingest Nudi PDFs. |

Do not market bilingual production on the back of a hosted model alone.

---

## 11. Embedding comparison

Current index: **nomic-embed-text, 768-d, 161 vectors, cosine**.

| | Option A — Keep nomic on VPS | Option B — Hosted embedding API | Option C — Other local small model |
|---|---|---|---|
| Typical model | Same `nomic-embed-text` (Ollama embed-only or equivalent runtime) | OpenAI/Gemini/Voyage-class, etc. | e.g. MiniLM / E5-small / other nomic build |
| Cost | Electricity; **$0 API** | Per query + ingest; usually low at this scale | $0 API |
| RAM | Extra **~1–2 GB** order of magnitude (not a vendor SKU) | None for embed model | Similar or smaller |
| CPU | Fine for 161-doc queries | Network RTT | Fine |
| Latency | Local ms–tens of ms after warm | HTTPS RTT from India **NEEDS LIVE VALIDATION** | Local |
| Privacy | Query text stays on VPS | Query text leaves the VPS | Stays on VPS |
| Reproducibility | GOOD if model file pinned | FAIR (vendor can change) | GOOD if pinned |
| Chroma compatibility | **Same 768-d space — no rebuild** | **Rebuild required** unless the API is **literally** the same nomic 768 model |
| Rebuild now? | **No** | **No in this phase**; later, controlled re-embed | **Yes later** if dim or space differs |

**Recommendation:** **Option A** for production v1. LLM may move to HTTPS; **query and document vectors stay nomic**. Option B only if local Ollama-embed is operationally painful **and** a 768 nomic-compatible API is confirmed.

---

## 12. Ollama analysis

| | Development | Production (public VPS) |
|---|---|---|
| `llama3` chat | **Suitable** (current Phase 6–11C path) | **Not suitable** on a low-cost Linux VPS: multi-GB weights, high RAM, slow CPU, no GPU assumed. RTX 2050 is a **local Windows** possibility, not a hosting plan. |
| `nomic-embed-text` | **Suitable** | **Practical** as **embed-only** if RAM budget includes ~1–2 GB extra and Ollama (or a smaller embed runtime) is firewalled on 127.0.0.1 |
| Disk | Several GB for llama3 + hundreds of MB for nomic | If chat stays external: **nomic-only** disk is modest |
| GPU | Optional locally | Do not require |

**Verified conclusion:** **Ollama chat = development. External HTTPS LLM = production.** Ollama (or equivalent) **may** remain on the VPS **only for embeddings**.

---

## 13. Primary recommendation (architecture only — do not implement)

**Primary production LLM: Groq-class hosted Llama 3.3 70B instruct (OpenAI-compatible HTTPS), with a documented fallback SKU of Gemini Flash-class if Groq 70B list price after verification exceeds the rupee cap.**

Why this ordering:

1. **Cost:** 70B-class is cheap at **pilot** scale; **must** combine with §18 caps so medium/large traffic cannot surprise-bill. Flash-class is the cheaper safety valve.  
2. **Reliability / latency:** Groq-class is known for high tokens/s; good for classroom wait time. **NEEDS LIVE VALIDATION** from India.  
3. **English:** 70B follows DETAILED headings and JSON better than local `llama3` 8B-class — that matters more than shaving ₹100/month.  
4. **Kannada potential:** weaker than Gemini-class; acceptable because Kannada RAG is **blocked** anyway.  
5. **Context:** far above current prompts.  
6. **API compatibility:** Groq-class `/v1/chat/completions` matches the intended `LLM_BASE_URL` adapter.  
7. **Rate limits:** provider limits exist; app must add daily budgets.  
8. **Privacy:** HTTPS; data-use policy **Must verify before purchase** (training / retention).  
9. **Deploy:** one env key + base URL; no GPU.  
10. **₹18,000:** keep **Option A embeddings** ($0) + **hard daily LLM stop**; prefer Flash-class if verified 70B medium-month estimate is still ~$25.

**Do not implement. Do not buy credits in this phase.**

---

## 14. Backup recommendation (architecture only)

**Backup: Gemini Flash-class** (Google AI HTTPS, OpenAI-compat layer **NEEDS LIVE VALIDATION**).

Use if Groq-class is unavailable, throttled, or list price after verification is too high. Stronger **Kannada generation candidate**. Slightly more adapter work if the OpenAI shim is incomplete.

**OpenRouter-style** is a **meta-backup** (one key, many upstreams), not the first choice: extra hop, extra data policy, markup. Fine as an emergency router later.

---

## 15. Migration risks

### Ollama chat → external LLM (keep nomic embeddings)

| Area | Effect |
|---|---|
| Code | Extend `rag/llm/client.py` `complete()` with an OpenAI-compat branch; map `max_tokens` → `max_tokens`; send `Authorization: Bearer`. **Do not do this in Phase 13.** |
| Chroma | **No rebuild** if embeddings stay `nomic-embed-text` 768-d |
| MySQL | **No schema change** |
| Downtime | Minutes to restart Python RAG with new env; or blue/green process |
| Testing | Re-run Phase 11/11B/11C question set; injection; e-content JSON parse; DETAILED headings; latency from India |

### Ollama embeddings → other embeddings

| Area | Effect |
|---|---|
| Code | New `embed_text` backend; relax “Phase 5 only nomic” guard |
| Chroma | **Controlled rebuild / re-embed of all 161 (and future) chunks into a new collection** (e.g. `historybot_class9_ss_v3`). Do not mix dimensions in v2. Distance thresholds **must be re-tuned** |
| MySQL | None |
| Downtime | Retrieval quality gap until the new collection is active and eval passes |
| Testing | Full retrieval probes + grounded eval; never switch embed model in place on v2 |

**Rule:** LLM switch **should not** require Chroma rebuild. Embedding switch **will** generally require re-embedding.

---

## 16. Security / privacy

| Topic | Notes |
|---|---|
| API key | Server env only (`LLM_API_KEY`). Never frontend, never git. Rotate if leaked. |
| Student text | Questions and textbook **chunks** go to the LLM provider. Anonymous UUID is not the main leak; **free-text PII in questions** is. |
| Data retention / training | **Must verify before purchase** on Groq, Google, OpenRouter, and any D vendor. Do not claim “no training” without their current terms. |
| HTTPS | Required for production LLM and any hosted embed API. |
| Region | Endpoints may be outside India; latency and data-transfer policy **Must verify**. |
| Abuse | Anonymous sessions can burn tokens via e-content loops. Provider keys with **spend caps** are as important as Express rate limits. |
| Logging | Do not log full prompts + keys. Provider dashboards may store prompts — **Must verify**. |
| Legal | This file is not legal advice. |

---

## 17. Future production environment variables

Conceptual only. **Do not put real secrets in git or in the current `.env` in this phase.**

```
# --- LLM (production) ---
LLM_PROVIDER=openai_compat          # future value; today only ollama works
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=                          # e.g. groq-class or gemini-class model id after purchase
LLM_API_KEY=                        # secret; never commit
LLM_TIMEOUT_S=60
LLM_MAX_OUTPUT_TOKENS_NORMAL=450
LLM_MAX_OUTPUT_TOKENS_DETAILED=700

# --- Embeddings (keep local nomic unless a later phase decides otherwise) ---
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
OLLAMA_HOST=http://127.0.0.1:11434   # embed-only on VPS; not public
# EMBEDDING_BASE_URL=                # only if Option B
# EMBEDDING_API_KEY=

CHROMA_PATH=data/chroma
CHROMA_COLLECTION=historybot_class9_ss_v2

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=historybot
MYSQL_USER=                         # dedicated non-root
MYSQL_PASSWORD=

INTERNAL_RAG_SECRET=
RAG_INTERNAL_URL=http://127.0.0.1:8000
RAG_INTERNAL_PORT=8000

DAILY_LLM_BUDGET=                   # implement later; rupee or token cap
RATE_LIMIT_WINDOW_MS=60000
RATE_LIMIT_MAX_REQUESTS=30
```

Local development should keep `LLM_PROVIDER=ollama` and `OLLAMA_MODEL=llama3` until a later implementation phase.

---

## 18. Rate-limit and cost-control recommendations (do not implement yet)

| Control | Suggested starting point |
|---|---|
| Express IP limit | Keep **30 / 60s**; add `trust proxy` when behind HTTPS |
| Per session / day | **40** chat completions (NORMAL+DETAILED) |
| E-content | **3 modules / session / day**; **20 / site / day** |
| PDF | **10 / session / day** (CPU, not LLM) |
| Global daily token or rupee cap | Hard stop returning `RAG_UNAVAILABLE` when hit; wire unused `DAILY_LLM_BUDGET` |
| Output caps | Keep code caps: rewrite **80**, NORMAL **450**, DETAILED **700**, e-content **per SECTION_SPECS** (do not raise) |
| Provider dashboard | Enable **max monthly spend** at the vendor |
| Caching | Optional exact-question cache for refusals and identical NORMAL answers **within a session only**; do not cache across students if that stores PII longer |
| Abuse | Treat e-content as expensive (≈8× a chat). Do not expose Python `/internal` publicly |

---

## 19. Final decision

| Decision | Choice |
|---|---|
| Production chat LLM | **Groq-class Llama 70B instruct** as primary architecture target |
| Backup chat LLM | **Gemini Flash-class** |
| Production embeddings | **Keep nomic-embed-text (768-d) locally** |
| Ollama `llama3` | **Development only** |
| Ollama nomic | **Allowed on VPS for embeddings only** |
| Chroma rebuild for LLM switch | **Not required** |
| Chroma rebuild for embed switch | **Required** (controlled, later) |
| Live tests this phase | **None** — **NEEDS LIVE VALIDATION** before any purchase |
| Implementation | **Not in this phase** |
| Hosting purchase | **Not in this phase** |

**Stop.** Do not start Phase 14 here.

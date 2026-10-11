"""Final answer-quality regression. Runs the engine in-process on Ollama with OpenAI blocked.

Checks:
- citations are within the retrieved pages
- no "Additional historical context"
- the exact refusal sentence only for genuinely missing / off-topic questions
- no refusal when the asked term is in the retrieved evidence
- sentence length (simple English heuristic) and format requests
Writes tmp/final-dev/final-answer-quality.json.

Usage: python scripts/final_answer_quality_regression.py [--quick] [--only ID,ID] [--out name.json]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# --- OpenAI block: set before anything from rag is imported -----------------
os.environ["OPENAI_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["HISTORYBOT_LLM_PROVIDER"] = "ollama"  # explicit dev/test override
os.environ["LLM_FALLBACK_PROVIDER"] = "none"

import urllib.request  # noqa: E402

_real_urlopen = urllib.request.urlopen
GUARD = {"openai_attempts": 0, "ollama_calls": 0}


def _guarded_urlopen(request, *args, **kwargs):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    if "openai" in url.lower() or "/v1/responses" in url:
        GUARD["openai_attempts"] += 1
        raise RuntimeError("OpenAI is blocked in this regression")
    return _real_urlopen(request, *args, **kwargs)


urllib.request.urlopen = _guarded_urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rag.llm.client as client  # noqa: E402
import rag.llm.config as llm_config  # noqa: E402

assert not llm_config.OPENAI_API_KEY and not client.OPENAI_API_KEY, "OpenAI key must be empty"
assert client.provider_plan() == ["ollama"], "provider must resolve to ollama only"
_real_ollama = client._ollama_chat


def _count_ollama(*args, **kwargs):
    GUARD["ollama_calls"] += 1
    return _real_ollama(*args, **kwargs)


def _blocked_openai(*args, **kwargs):
    GUARD["openai_attempts"] += 1
    raise client.LlmError("OpenAI is blocked in this regression")


client._ollama_chat = _count_ollama
client._openai_responses = _blocked_openai

from rag.engine.answer import answer_question  # noqa: E402
from rag.engine.topic_map import load_primary_chunks  # noqa: E402
from rag.prompts.tutor import NOT_IN_TEXTBOOK  # noqa: E402

OUT_DIR = ROOT / "tmp" / "final-dev"
OUT = OUT_DIR / "final-answer-quality.json"
CORPUS = " ".join((c.get("text") or "") for c in load_primary_chunks()).lower()


def in_corpus(term: str) -> bool:
    return re.search(rf"\b{re.escape(term.lower())}", CORPUS) is not None


TERMS = ["zabti", "mansabdari", "jagir", "iqta", "dagh", "patta", "chauth", "sardeshmukhi",
         "ryotwari", "jizya", "din-e-ilahi", "navaratnas", "subhas", "guerrilla"]
MISSING = [
    ("missing-plassey", "Who won the Battle of Plassey?", "plassey"),
    ("missing-kalinga", "What did Emperor Ashoka do after the Kalinga war?", "kalinga"),
    ("missing-jallianwala", "What happened at Jallianwala Bagh in 1919?", "jallianwala"),
    ("missing-quitindia", "What was the Quit India Movement?", "quit india"),
]

# id, question, prior question (for follow-ups), kind, extra checks
CASES = [
    ("akbar-direct", "Who was Akbar?", None, "answer", {"need": ["akbar"]}),
    ("akbar-again", "Explain again more simply.", "Who was Akbar?", "answer", {"need": ["akbar"], "max_avg": 18, "differs_from_prior": True}),
    ("akbar-still", "I still don't understand.", "Who was Akbar?", "answer", {"need": ["akbar"], "max_avg": 18, "differs_from_prior": True}),
    ("akbar-simpler", "Explain Akbar in simpler words.", None, "answer", {"need": ["akbar"], "max_avg": 18}),
    ("akbar-five", "Give five bullet points about Akbar.", None, "answer", {"bullets": 5}),
    ("akbar-aurangzeb-table", "Compare Akbar and Aurangzeb in an easy table.", None, "answer", {"table": True}),
    ("mansabdari-exam", "Write an exam answer on the Mansabdari system.", None, "answer", {"numbered": True}),
    ("shivaji-short", "Tell me about Shivaji in a shorter way.", None, "answer", {"max_words": 170, "who_did_what": True}),
    ("shivaji-direct", "Who was Shivaji?", None, "answer", {"who_did_what": True}),
    ("typo-akbr", "who was akbr", None, "answer", {"need": ["akbar"]}),
    ("typo-shershah", "tell me about shershah", None, "answer", {"need": ["sher shah"]}),
    ("typo-mansabdar", "what is mansabdar system", None, "answer", {"need": ["mansab"]}),
    ("ambiguous-king", "Who was the king?", None, "any", {}),
    ("multi-panipat", "What happened in the first and second battles of Panipat?", None, "answer", {"need": ["panipat"]}),
    ("multi-akbar-shivaji", "Who were Akbar and Shivaji?", None, "answer", {"need": ["akbar", "shivaji"]}),
    # "Tell me more" follow-ups must go deeper, not restate the previous answer.
    ("mansabdari-more", "Can you tell me more about this, I mean the Mansabdari system?", "Explain the Mansabdari system.", "answer", {"need": ["mansab"], "deeper_than_prior": True}),
    ("mansabdari-more-typo", "can you more on this i mean mansabadri system", "Explain the Mansabdari system.", "answer", {"need": ["mansab"], "deeper_than_prior": True}),
    ("akbar-more", "Tell me more about him.", "Who was Akbar?", "answer", {"need": ["akbar"], "deeper_than_prior": True}),
    ("shivaji-more", "Can you explain this in more detail?", "Who was Shivaji?", "answer", {"need": ["shivaji"], "deeper_than_prior": True, "who_did_what": True}),
    ("offtopic-python", "How do I write a for loop in Python?", None, "refuse", {}),
    ("offtopic-cricket", "Who won the cricket world cup?", None, "refuse", {}),
    ("offtopic-musk", "Who is Elon Musk?", None, "refuse", {}),
    ("followup-example", "Give an example.", "Explain the Mansabdari system.", "answer", {"need": ["mansab"], "deeper_than_prior": True}),
]
QUICK = {"akbar-again", "akbar-aurangzeb-table", "shivaji-short", "typo-akbr", "offtopic-python", "mansabdari-more",
         "offtopic-musk", "followup-example"}


def pages(sources):
    return sorted({int(s["printed_page_number"]) for s in sources or [] if str(s.get("printed_page_number") or "").isdigit()})


def body(answer: str) -> str:
    return re.sub(r"\n*Source:.*$", "", answer or "", flags=re.S).strip()


def avg_sentence_words(answer: str) -> float:
    lines = [ln for ln in body(answer).splitlines() if ln.strip() and not ln.strip().startswith("|")]
    text = re.sub(r"[#*>`]+", " ", "\n".join(lines))
    parts = [p for p in re.split(r"[.!?]+|\n+", text) if len(p.split()) >= 2]
    return round(sum(len(p.split()) for p in parts) / len(parts), 1) if parts else 0.0


def run_one(question, history):
    t0 = time.time()
    result = answer_question(question, "en", history)
    return result, round(time.time() - t0, 1)


def check_answer(case_id, question, kind, extra, result, prior_answer=None, key_term=None):
    answer = result.get("answer") or ""
    reasons = []
    src = pages(result.get("sources"))
    retrieved = sorted({int(h["printed_page_number"]) for h in result.get("retrieved") or []
                        if str(h.get("printed_page_number") or "").isdigit()})
    refused = NOT_IN_TEXTBOOK in answer
    supplement = ""
    if "**additional historical explanation**" in answer.lower():
        supplement = re.split(r"\*\*Additional historical explanation\*\*", answer, flags=re.I)[-1]
        supplement = re.split(r"\*\*Quick revision\*\*|\n\s*Source:", supplement, flags=re.I)[0]
    if re.search(r"\bpage\s*\d+", supplement, re.I):
        reasons.append("page-cited-in-supplement")
    if "additional historical context" in answer.lower():
        reasons.append("legacy-additional-context-label")
    if src and retrieved and not set(src) <= set(retrieved):
        reasons.append(f"citation-outside-retrieved:{sorted(set(src) - set(retrieved))}")
    if kind == "answer":
        if refused:
            reasons.append("refused-supported-topic")
        if not src:
            reasons.append("no-citation")
    if kind == "supplement":
        # In-scope history that the textbook does not cover: a labelled supplementary answer,
        # never a refusal, and never a textbook page citation.
        if refused:
            reasons.append("refused-in-scope-history")
        if not supplement.strip():
            reasons.append("no-supplement-section")
        if src:
            reasons.append(f"textbook-citation-on-non-textbook-topic:{src}")
    if kind == "refuse" and not refused:
        reasons.append("missing-exact-refusal")
    if kind == "refuse" and src:
        reasons.append("refusal-with-citation")
    if key_term:
        evidence_text = " ".join((h.get("text") or "") for h in result.get("retrieved") or []).lower()
        if key_term.lower() in evidence_text and refused:
            reasons.append("refused-although-term-in-evidence")
    lowered = body(answer).lower()
    for need in extra.get("need", []):
        if need not in lowered:
            reasons.append(f"missing:{need}")
    avg = avg_sentence_words(answer)
    if kind == "answer" and avg > extra.get("max_avg", 24):
        reasons.append(f"long-sentences:{avg}")
    words = len(body(answer).split())
    if extra.get("max_words") and words > extra["max_words"]:
        reasons.append(f"too-long:{words}")
    if extra.get("bullets"):
        n = len([ln for ln in body(answer).splitlines() if re.match(r"^\s*(?:[-*\u2022]|\d+[.)])\s+", ln)])
        if n != extra["bullets"]:
            reasons.append(f"bullets:{n}")
    if extra.get("table"):
        rows = [ln for ln in body(answer).splitlines() if ln.strip().startswith("|")]
        if len(rows) < 3:
            reasons.append("no-table")
        if any(re.search(r"\|\s*\.\s*$", ln) for ln in rows):
            reasons.append("stray-period-after-table-row")
    if extra.get("numbered"):
        if len([ln for ln in body(answer).splitlines() if re.match(r"^\s*\d+[.)]\s+", ln)]) < 2:
            reasons.append("no-numbered-points")
    if re.search(r"\*\*\s*\.|:\*\*\.|^#+ .*\.$", body(answer), re.M):
        reasons.append("stray-period-after-heading")
    if extra.get("differs_from_prior") and prior_answer:
        a = set(re.findall(r"[a-z]+", body(prior_answer).lower()))
        b = re.findall(r"[a-z]+", lowered)
        same = sum(1 for w in b if w in a) / max(len(b), 1)
        prior_sents = {s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", body(prior_answer)) if len(s.split()) > 5}
        repeated = sum(1 for s in re.split(r"(?<=[.!?])\s+", lowered) if s.strip() in prior_sents)
        if repeated >= 3:
            reasons.append(f"repeats-prior-sentences:{repeated}")
        if avg >= avg_sentence_words(prior_answer) + 1:
            reasons.append("not-simpler-than-prior")
    depth_metrics = {}
    if extra.get("deeper_than_prior") and prior_answer:
        from rag.engine.answer import _repeat_overlap, _sentence_jaccard

        overlap = _repeat_overlap(answer, prior_answer)
        prior_words = set(re.findall(r"[a-z]{4,}", body(prior_answer).lower()))
        new_words = {w for w in re.findall(r"[a-z]{4,}", lowered) if w not in prior_words}
        honest = False  # supplement policy: no 'textbook does not give more' note is allowed
        depth_metrics = {
            "overlap_vs_prior": overlap,
            "sentence_jaccard_vs_prior": _sentence_jaccard(answer, prior_answer),
            "new_words": len(new_words),
            "words": words,
            "prior_words": len(body(prior_answer).split()),
            "honest_exhausted": honest,
        }
        if "does not give more details" in lowered:
            reasons.append("exhausted-note-printed")
        if overlap >= 0.5:
            reasons.append(f"restates-prior:{overlap}")
        if len(new_words) < 15:
            reasons.append(f"few-new-words:{len(new_words)}")
    if extra.get("who_did_what"):
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", body(answer)):
            # The defect is the passive "He was captured by the Sultan" (it was his father, Shahaji).
            # Shivaji actively capturing forts from the Sultan is correct and not flagged.
            if re.search(r"\b(?:was|were|got|being)\s+captured\b|\bcaptured\s+by\b", sentence, re.I) and re.search(r"\bsultan\b", sentence, re.I):
                if not re.search(r"shahaji|father", sentence, re.I):
                    reasons.append("capture-attributed-to-wrong-person")
    return {
        "id": case_id,
        "question": question,
        "verdict": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "answer": answer,
        "cited_pages": src,
        "retrieved_pages": retrieved,
        "avg_sentence_words": avg,
        "word_count": words,
        "validation_reason": result.get("validation_reason"),
        "not_found_kind": result.get("not_found_kind"),
        "refusal_guard": result.get("refusal_guard"),
        "depth": depth_metrics or None,
        "depth_request": result.get("depth_request"),
        "prior_answer": prior_answer if depth_metrics else None,
    }


def main() -> int:
    args = sys.argv[1:]
    quick = "--quick" in args
    only = set()
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    global OUT
    if "--out" in args:
        OUT = OUT_DIR / args[args.index("--out") + 1]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    skipped = []

    def want(case_id):
        if only:
            return case_id in only
        return not quick or case_id in QUICK or case_id in {"term-zabti", "missing-plassey"}

    for term in TERMS:
        cid = f"term-{term}"
        if not want(cid):
            continue
        if not in_corpus(term):
            skipped.append({"id": cid, "reason": "term not in textbook corpus"})
            continue
        result, secs = run_one(f"What is {term}?", [])
        row = check_answer(cid, f"What is {term}?", "answer", {"need": [term.split("-")[0]]}, result, key_term=term)
        row["seconds"] = secs
        rows.append(row)
        print(f"{row['verdict']} {cid} {secs}s pages={row['cited_pages']} {row['reasons']}", flush=True)
    for cid, question, needle in MISSING:
        if not want(cid):
            continue
        if in_corpus(needle):
            skipped.append({"id": cid, "reason": "topic is in the textbook corpus"})
            continue
        result, secs = run_one(question, [])
        row = check_answer(cid, question, "supplement", {}, result)
        row["seconds"] = secs
        rows.append(row)
        print(f"{row['verdict']} {cid} {secs}s {row['reasons']}", flush=True)
    prior_cache = {}
    for cid, question, prior, kind, extra in CASES:
        if not want(cid):
            continue
        history = []
        prior_answer = None
        if prior:
            if prior not in prior_cache:
                prior_cache[prior] = answer_question(prior, "en", [])
            prior_answer = prior_cache[prior]["answer"]
            history = [{"role": "user", "content": prior}, {"role": "assistant", "content": prior_answer}]
        result, secs = run_one(question, history)
        row = check_answer(cid, question, kind, extra, result, prior_answer=prior_answer)
        row["seconds"] = secs
        rows.append(row)
        print(f"{row['verdict']} {cid} {secs}s pages={row['cited_pages']} avg={row['avg_sentence_words']} {row['reasons']}", flush=True)

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    summary = {
        "pass": passed,
        "fail": len(rows) - passed,
        "total": len(rows),
        "skipped": skipped,
        "provider": client.last_provider or "ollama",
        "openai_attempts": GUARD["openai_attempts"],
        "ollama_calls": GUARD["ollama_calls"],
    }
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"final_answer_quality PASS={passed} FAIL={len(rows) - passed} TOTAL={len(rows)} skipped={len(skipped)} "
          f"openai_attempts={GUARD['openai_attempts']} ollama_calls={GUARD['ollama_calls']} -> {OUT}")
    if GUARD["openai_attempts"]:
        return 2
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

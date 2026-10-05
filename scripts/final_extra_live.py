"""Extra live/follow-up/module checks after Ahom/Ashapradhan fixes."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from rag.engine.answer import answer_question
from rag.engine.topic_map import load_primary_chunks

load_primary_chunks.cache_clear()

OUT = Path(os.environ.get("TEMP") or ".") / "historybot-final-qa"
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:3000/api/v1"
rows = []


def refuse(text: str) -> bool:
    low = (text or "").lower()
    return any(
        m in low
        for m in (
            "not available in the provided textbook",
            "not available in the textbook",
            "i can help with topics covered",
        )
    )


def ask(q, hist=None):
    t0 = time.time()
    result = answer_question(q, language="en", history=hist or [])
    return result, round(time.time() - t0, 1)


def rec(topic, pattern, q, ok, citation="", grounded=None, notes="", seconds=None):
    rows.append(
        {
            "topic": topic,
            "pattern": pattern,
            "question": q,
            "result": "PASS" if ok else "FAIL",
            "citation": citation,
            "grounded": grounded,
            "notes": notes,
            "seconds": seconds,
            "layer_ran": "live_fix",
        }
    )
    print(("PASS" if ok else "FAIL"), pattern, topic, notes)


def http(method, path, body=None, timeout=900):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"Accept": "application/json", **({"Content-Type": "application/json"} if data else {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main():
    follow = [
        ("Baji Rao I", "Who was Baji Rao?", "Tell me more."),
        ("Akbar", "Who was Akbar?", "What did he do after that?"),
        ("Shivaji", "Who was Shivaji?", "Tell me more about his administration."),
        ("Babur", "Who was Babur?", "Why is he important?"),
    ]
    for topic, q1, q2 in follow:
        r1, t1 = ask(q1)
        hist = [{"role": "user", "content": q1}, {"role": "assistant", "content": r1.get("answer") or ""}]
        r2, t2 = ask(q2, hist)
        pages = sorted(
            {
                s.get("printed_page_number")
                for s in (r2.get("sources") or r1.get("sources") or [])
                if s.get("printed_page_number")
            }
        )
        ok = bool(r1.get("grounded")) and bool(r2.get("grounded")) and not refuse(r2.get("answer") or "")
        ans = ((r1.get("answer") or "") + " " + (r2.get("answer") or "")).lower()
        if topic == "Baji Rao I" and "third battle of panipat" in ans and "bhopal" not in ans:
            ok = False
        rec(topic, "followup", f"{q1} -> {q2}", ok, ",".join(map(str, pages)), r2.get("grounded"), f"t={t1}+{t2}", t1 + t2)

    for q, topic in [
        ("Who were the Ahoms?", "Ahom"),
        ("Tell me about the Ahom dynasty.", "Ahom"),
        ("What is Ashapradhan?", "Admin-Ashtapradhan"),
        ("Explain Ashtapradhan.", "Admin-Ashtapradhan"),
        ("Give 5 MCQs on Ahom.", "Ahom"),
    ]:
        r, t = ask(q)
        pages = sorted({s.get("printed_page_number") for s in (r.get("sources") or []) if s.get("printed_page_number")})
        ok = bool(r.get("grounded")) and not refuse(r.get("answer") or "")
        preview = (r.get("answer") or "")[:80].replace("\n", " ")
        rec(topic, "fixed_retest", q, ok, ",".join(map(str, pages)), r.get("grounded"), f"t={t}; {preview}", t)

    for topic, q, bads, need in [
        ("Baji Rao I", "Who was Baji Rao?", ["1761"], "baji"),
        ("Shivaji", "Who was Shivaji?", [], "shivaji"),
        ("Akbar", "Who was Akbar?", [], "akbar"),
    ]:
        r, t = ask(q)
        ans = (r.get("answer") or "").lower()
        ok = bool(r.get("grounded")) and need in ans
        for bad in bads:
            if bad in ans:
                ok = False
        pages = sorted({s.get("printed_page_number") for s in (r.get("sources") or []) if s.get("printed_page_number")})
        rec(topic, "boundary", q, ok, ",".join(map(str, pages)), r.get("grounded"), f"t={t}", t)

    for q in ["Who was Napoleon?", "Explain World War II.", "Who is Cristiano Ronaldo?", "Explain quantum entanglement."]:
        r, t = ask(q)
        ok = refuse(r.get("answer") or "") or r.get("grounded") is False
        rec("Unsupported", "unsupported_retest", q, ok, "", False, f"t={t}", t)

    session = http("POST", "/sessions", {})
    sid = session["session_id"]
    for topic in ["Baji Rao", "Akbar", "Shivaji", "Babur", "Mughals", "Marathas", "Ahom"]:
        t0 = time.time()
        try:
            ec = http("POST", "/econtent", {"session_id": sid, "topic": topic, "language": "en"}, timeout=900)
            ok = bool(ec.get("grounded"))
            notes = f"title={ec.get('title')};t={round(time.time() - t0, 1)}"
            eid = ec.get("id") or ec.get("econtent_id")
            if ok and eid and topic in ("Baji Rao", "Akbar", "Ahom"):
                req = urllib.request.Request(
                    f"{API}/econtent/{eid}/pdf",
                    data=json.dumps({"session_id": sid}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json", "Accept": "application/pdf"},
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    pdf = resp.read()
                pdf_ok = pdf[:4] == b"%PDF" and len(pdf) > 1000
                (OUT / f"sample-{topic.replace(' ', '').lower()}.pdf").write_bytes(pdf)
                rec("PDF", f"pdf_{topic.replace(' ', '_')}", topic, pdf_ok, "", True, f"bytes={len(pdf)}")
            rec("Module", "econtent", topic, ok, "", ec.get("grounded"), notes, round(time.time() - t0, 1))
        except Exception as exc:  # noqa: BLE001
            rec("Module", "econtent", topic, False, "", False, str(exc))

    t0 = time.time()
    rk = answer_question("Who was Akbar?", language="kn")
    tk = round(time.time() - t0, 1)
    ans = rk.get("answer") or ""
    ok = bool(rk.get("grounded")) and not refuse(ans)
    rec("Akbar", "kannada_safe", "Who was Akbar? (kn)", ok, "", rk.get("grounded"), f"t={tk};len={len(ans)}", tk)

    (OUT / "EXTRA_LIVE.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    passed = sum(1 for r in rows if r["result"] == "PASS")
    print("EXTRA", passed, "/", len(rows))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

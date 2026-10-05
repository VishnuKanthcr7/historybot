"""Phase 21C Express conversation-path integration.

Hits the public API the browser uses:
POST /api/v1/sessions
POST /api/v1/conversations
POST /api/v1/conversations/:id/messages
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

BASE = os.environ.get("HISTORYBOT_API_BASE") or f"http://127.0.0.1:{os.environ.get('PORT') or os.environ.get('APP_PORT') or '3000'}/api/v1"
OUT = ROOT / "tmp" / "phase21c-integration.json"


def stems(answer: str) -> list[str]:
    return [match.group(1).strip().lower() for match in re.finditer(r"^\d+\.\s+(.+)$", answer or "", re.M)]


def req(method: str, path: str, body: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            return response.status, payload
    except urllib.error.HTTPError as err:
        payload = json.loads(err.read().decode("utf-8") or "{}")
        return err.code, payload
    except Exception as err:
        return 0, {"error": str(err)}


def send(session_id: str, conversation_id: str, message: str) -> tuple[int, dict, float]:
    start = time.perf_counter()
    status, payload = req(
        "POST",
        f"/conversations/{conversation_id}/messages",
        {"session_id": session_id, "message": message, "language": "en"},
        timeout=180,
    )
    return status, payload, time.perf_counter() - start


def content_of(payload: dict) -> str:
    return str((payload.get("message") or {}).get("content") or "")


def main() -> int:
    rows = []
    health_status, health = req("GET", "/health")
    if health_status != 200:
        report = {
            "verdict": "FAIL",
            "reason": f"Express not reachable at {BASE}/health status={health_status} {health}",
            "cases": [],
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("FAIL Express not reachable", health_status, health)
        return 1

    session_status, session = req("POST", "/sessions", {})
    session_id = session.get("session_id")
    if session_status not in {200, 201} or not session_id:
        print("FAIL create session", session_status, session)
        return 1
    conv_status, conv = req("POST", "/conversations", {"session_id": session_id, "title": "phase21c"})
    conversation_id = conv.get("conversation_id")
    if conv_status not in {200, 201} or not conversation_id:
        print("FAIL create conversation", conv_status, conv)
        return 1

    s1, p1, t1 = send(session_id, conversation_id, "give me 10 mcqs about the mughals")
    a1 = content_of(p1)
    n1 = len(re.findall(r"^\d+\.\s+", a1, re.M))
    ok1 = s1 == 201 and n1 >= 5 and "answer:" in a1.lower()
    rows.append({"id": "express-mcq", "ok": ok1, "status": s1, "count": n1, "t": round(t1, 1), "preview": a1[:400]})

    s2, p2, t2 = send(session_id, conversation_id, "more")
    a2 = content_of(p2)
    n2 = len(re.findall(r"^\d+\.\s+", a2, re.M))
    overlap = set(stems(a1)) & set(stems(a2))
    topic_ok = any(name in (a1 + a2).lower() for name in ("mughal", "babur", "akbar", "sher", "taj", "aurangzeb"))
    ok2 = s2 == 201 and n2 >= 1 and not overlap and topic_ok
    rows.append(
        {
            "id": "express-more",
            "ok": ok2,
            "status": s2,
            "count": n2,
            "overlap": sorted(overlap)[:5],
            "t": round(t2, 1),
            "preview": a2[:400],
        }
    )

    conv2_status, conv2 = req("POST", "/conversations", {"session_id": session_id, "title": "bajirao"})
    cid2 = conv2.get("conversation_id")
    s3, p3, t3 = send(session_id, cid2, "tell me about bajirao in easy english")
    a3 = content_of(p3)
    ok3 = s3 == 201 and "baji" in a3.lower() and len(a3.split()) >= 40
    rows.append({"id": "express-bajirao", "ok": ok3, "status": s3, "words": len(a3.split()), "t": round(t3, 1), "preview": a3[:500]})

    s4, p4, t4 = send(session_id, cid2, "more")
    a4 = content_of(p4)
    ok4 = s4 == 201 and "baji" in a4.lower() and "ahom" not in a4.lower() and "## madhav" not in a4.lower()
    rows.append({"id": "express-bajirao-more", "ok": ok4, "status": s4, "t": round(t4, 1), "preview": a4[:400]})

    passed = sum(1 for row in rows if row["ok"])
    verdict = "PASS" if passed == len(rows) else ("PARTIAL" if passed else "FAIL")
    report = {
        "verdict": verdict,
        "passed": passed,
        "total": len(rows),
        "session_id": session_id,
        "conversation_id": conversation_id,
        "cases": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(verdict, passed, "/", len(rows))
    for row in rows:
        print(("PASS" if row["ok"] else "FAIL"), row["id"], row)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

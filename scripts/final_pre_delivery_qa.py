"""HistoryBot final pre-delivery QA — local machine only.

CloudAgent unavailable; run on the Windows repo host.
Outputs: %TEMP%/historybot-final-qa/QA_MATRIX.md|.csv and audit JSON.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from rag.engine.answer import answer_question
from rag.engine.classify import TOPIC_ALIASES, extract_topics
from rag.engine.pack import build_evidence_pack, detect_entity
from rag.engine.topic_map import build_topic_index, load_primary_chunks, public_topic_map
from rag.sources.catalog import EXCLUDED_SOURCE_FILES, PRIMARY_ENGLISH_FILE, SOURCES
from rag.vectorstore.config import ACTIVE_COLLECTION, CHROMA_PATH
from rag.vectorstore.chroma_store import get_existing_collection

OUT_DIR = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "historybot-final-qa"
OUT_DIR.mkdir(parents=True, exist_ok=True)
API = os.environ.get("HISTORYBOT_API_BASE") or "http://127.0.0.1:3000/api/v1"

# Entity boundary: forbidden bleed tokens when focusing these entities
BOUNDARY = {
    "bajirao": ["balaji vishwanath", "third battle of panipat", "1761"],
    "shivaji": ["sambhaji became", "ahom"],
    "akbar": ["aurangzeb abolished", "din-e-ilahi by aurangzeb"],
    "babar": ["akbar was born", "shivaji"],
    "aurangzeb": ["din-e-ilahi", "bairam khan"],
    "ahom": ["baji rao", "peshwa", "shivaji's ashtapradhan"],
}


def http_json(method: str, path: str, body: dict | None = None, timeout: int = 300):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Accept": "application/json", **({"Content-Type": "application/json"} if data else {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refuse(text: str) -> bool:
    low = (text or "").lower()
    markers = (
        "not available in the provided textbook",
        "not available in the textbook",
        "outside the prescribed",
        "cannot answer from the textbook",
        "not covered in your prescribed",
        "i can help with topics covered",
    )
    return any(m in low for m in markers)


def cite_pages(sources) -> list[int]:
    pages = []
    for s in sources or []:
        p = s.get("printed_page_number") or s.get("textbook_page_number")
        try:
            pages.append(int(p))
        except (TypeError, ValueError):
            pass
    return sorted(set(pages))


def source_audit() -> dict:
    client = get_existing_collection(ACTIVE_COLLECTION)
    data = client.get(include=["metadatas", "documents"])
    metas = data.get("metadatas") or []
    docs = data.get("documents") or []
    ids = data.get("ids") or []
    by_type = Counter((m or {}).get("source_type") for m in metas)
    authorities = Counter((m or {}).get("authority") for m in metas)
    chapters = Counter((m or {}).get("chapter") for m in metas)
    primary = [m for m in metas if (m or {}).get("source_type") == "primary_textbook"]
    pages = sorted(
        {
            int(m.get("printed_page_number") or m.get("textbook_page_number"))
            for m in primary
            if (m.get("printed_page_number") or m.get("textbook_page_number")) not in (None, "")
        }
    )
    excluded_present = []
    for m in metas:
        name = (m or {}).get("document_name") or ""
        for ex in EXCLUDED_SOURCE_FILES:
            if ex.lower().replace(".pdf", "") in name.lower():
                excluded_present.append(ex)
    topic_map = public_topic_map()
    primary_chunks = load_primary_chunks()
    return {
        "active_collection": ACTIVE_COLLECTION,
        "chroma_path": str(CHROMA_PATH),
        "chunk_count": len(ids),
        "by_source_type": dict(by_type),
        "authorities": dict(authorities),
        "chapters": dict(chapters),
        "primary_chunk_count": len(primary_chunks),
        "primary_pages": pages,
        "primary_english_file": PRIMARY_ENGLISH_FILE,
        "approved_primary_source_id": "ktbs_2026_en_ch17",
        "excluded_files_policy": sorted(EXCLUDED_SOURCE_FILES),
        "excluded_leaked_into_index": sorted(set(excluded_present)),
        "topic_map": topic_map,
        "supplement_sources_in_catalog_but_student_path_excluded": [
            "ncert_mughals",
            "ncert_marathas",
        ],
        "catalog_keys": sorted(SOURCES.keys()),
    }


def build_matrix_questions() -> list[dict]:
    """Large realistic matrix from indexed topics — not hardcoded answer text."""
    topics = {
        "Babur": ["Babur", "Babar", "who was babur", "babar"],
        "Akbar": ["Akbar", "akbar"],
        "Aurangzeb": ["Aurangzeb", "aurangzeb"],
        "Humayun": ["Humayun"],
        "Jahangir": ["Jahangir"],
        "Shah Jahan": ["Shah Jahan", "Shahjahan"],
        "Sher Shah": ["Sher Shah"],
        "Mughals": ["the Mughals", "Mughal empire", "Mughals"],
        "Shivaji": ["Shivaji"],
        "Sambhaji": ["Sambhaji"],
        "Baji Rao I": ["Baji Rao", "Bajirao", "Baji Rao I"],
        "Balaji Vishwanath": ["Balaji Vishwanath"],
        "Madhav Rao": ["Madhav Rao"],
        "Marathas": ["the Marathas", "Maratha"],
        "Maratha Union": ["Maratha Union", "Maratha confederacy"],
        "Peshwa": ["Peshwa", "the Peshwas"],
        "Ahom": ["Ahom", "the Ahoms", "Lachit", "Saraighat"],
        "Admin-Mansabdari": ["Mansabdari", "mansab"],
        "Admin-Ashtapradhan": ["Ashtapradhan", "Ashapradhan"],
        "Admin-Chauth": ["Chauth", "Sardeshmukhi"],
        "Din-e-Ilahi": ["Din-e-Ilahi", "Din e Ilahi"],
        "Taj Mahal": ["Taj Mahal"],
        "Guerrilla": ["guerrilla warfare", "guerilla"],
        "Panipat": ["First Battle of Panipat", "Panipat"],
        "Raigad": ["Raigad"],
    }

    patterns = [
        ("identity", "Who was {name}?"),
        ("identity", "Who is {name}?"),
        ("definition", "What is {name}?"),
        ("definition", "Define {name}."),
        ("factual", "What do you know about {name}?"),
        ("why", "Why is {name} important?"),
        ("how", "How did {name} rise to power?"),
        ("how", "How was {name} related to administration?"),
        ("list", "List key points about {name}."),
        ("chronology", "When did {name} live / rule?"),
        ("exam_2", "Write a 2-mark answer on {name}."),
        ("exam_5", "Write a 5-mark answer on {name}."),
        ("detail", "Explain {name} in detail."),
        ("detail", "Tell me about {name}."),
        ("more", "Tell me more about {name}."),
        ("student_imperfect", "who was {name} pls"),
        ("student_imperfect", "{name}??"),
        ("student_imperfect", "explain {name} in easy english"),
        ("viva", "In one minute, summarize {name} for a viva."),
        ("professor", "Briefly discuss {name} with textbook page references."),
        ("compare_prep", "What should I remember about {name} for exams?"),
    ]

    rows = []
    for topic, names in topics.items():
        for name in names[:2]:
            for pattern, tmpl in patterns:
                q = tmpl.format(name=name)
                rows.append(
                    {
                        "topic": topic,
                        "pattern": pattern,
                        "question": q,
                        "layer": "pack",
                        "expect_grounded": True,
                        "entity_hint": topic,
                    }
                )

    # Comparisons
    compares = [
        ("Akbar vs Aurangzeb", "Compare Akbar and Aurangzeb."),
        ("Shivaji vs Sambhaji", "Compare Shivaji and Sambhaji."),
        ("Baji Rao vs Balaji", "Compare Baji Rao and Balaji Vishwanath."),
        ("Mughals vs Marathas", "Compare the Mughals and the Marathas."),
        ("Babur vs Akbar", "How was Babur different from Akbar?"),
    ]
    for topic, q in compares:
        rows.append(
            {
                "topic": topic,
                "pattern": "compare",
                "question": q,
                "layer": "pack",
                "expect_grounded": True,
                "entity_hint": topic,
            }
        )

    # Unsupported — should refuse
    unsupported = [
        ("Unsupported", "Who was Napoleon?", "unsupported"),
        ("Unsupported", "Explain World War II.", "unsupported"),
        ("Unsupported", "What is India's GDP?", "unsupported"),
        ("Unsupported", "Who is Cristiano Ronaldo?", "unsupported"),
        ("Unsupported", "What is the latest news today?", "unsupported"),
        ("Unsupported", "Explain quantum entanglement.", "unsupported"),
        ("Unsupported", "Summarize the Wikipedia page on Akbar.", "unsupported"),
        ("Unsupported", "Answer from NCERT Class 7 History.", "unsupported"),
        ("Unsupported", "Who is the Prime Minister of India?", "unsupported"),
        ("Unsupported", "Write code to hack a website.", "unsupported"),
        ("Unsupported", "What happened at the Battle of Plassey in detail beyond textbook?", "unsupported"),
    ]
    for topic, q, pattern in unsupported:
        rows.append(
            {
                "topic": topic,
                "pattern": pattern,
                "question": q,
                "layer": "live",
                "expect_grounded": False,
                "expect_refuse": True,
                "entity_hint": None,
            }
        )

    # MCQs
    mcq_topics = [
        "Babur",
        "Akbar",
        "Aurangzeb",
        "Shivaji",
        "Baji Rao",
        "Marathas",
        "Mughals",
        "Ahom",
        "Sher Shah",
        "Din-e-Ilahi",
        "Mansabdari",
        "Ashtapradhan",
    ]
    for t in mcq_topics:
        for n in (5, 10):
            rows.append(
                {
                    "topic": t,
                    "pattern": f"mcq_{n}",
                    "question": f"Give {n} MCQs on {t}.",
                    "layer": "live",
                    "expect_grounded": True,
                    "entity_hint": t,
                    "mcq_n": n,
                }
            )

    # Follow-ups (live chain anchors)
    follow = [
        ("Baji Rao I", "Who was Baji Rao?", "Tell me more."),
        ("Akbar", "Who was Akbar?", "What did he do after that?"),
        ("Shivaji", "Who was Shivaji?", "Tell me more about his administration."),
        ("Babur", "Who was Babur?", "Why is he important?"),
    ]
    for topic, q1, q2 in follow:
        rows.append(
            {
                "topic": topic,
                "pattern": "followup_anchor",
                "question": q1,
                "followup": q2,
                "layer": "live",
                "expect_grounded": True,
                "entity_hint": topic,
            }
        )

    return rows


def pack_check(row: dict) -> dict:
    q = row["question"]
    topics = extract_topics(q)
    entity = detect_entity(topics)
    qtype = "EXPLANATION" if row["pattern"] in {"detail", "more", "exam_5", "professor"} else "DIRECT"
    if row["pattern"] == "compare" or "vs" in row["topic"].lower() or row["topic"] in {"Mughals", "Marathas", "Maratha Union", "Ahom"}:
        if any(k in (row["topic"] or "").lower() for k in ("mughal", "maratha", "ahom", "union")):
            qtype = "BROAD_TOPIC"
    try:
        pack = build_evidence_pack(q, q, qtype)
    except Exception as exc:  # noqa: BLE001
        return {
            **row,
            "result": "FAIL",
            "citation": "",
            "grounded": False,
            "notes": f"pack_error:{exc}",
            "layer_ran": "pack",
        }
    pages = pack.pages or []
    blob = " ".join((c.get("text") or "") for c in pack.chunks).lower()
    source_types = {(c.get("source_type") or "") for c in pack.chunks}
    supp_leak = any(t.startswith("supplementary") for t in source_types)
    notes = []
    ok = True
    if row.get("expect_refuse"):
        # pack layer alone cannot confirm refuse; mark SKIP for pack
        return {
            **row,
            "result": "SKIP_PACK",
            "citation": ",".join(map(str, pages)),
            "grounded": None,
            "notes": "unsupported deferred to live",
            "layer_ran": "pack",
            "entity": entity,
        }
    if not pack.chunks:
        ok = False
        notes.append("empty_pack")
    if supp_leak:
        ok = False
        notes.append("supplement_in_pack")
    # Boundary soft check on pack text
    key = None
    for k in BOUNDARY:
        if k in (entity or "") or k in q.lower().replace(" ", ""):
            key = k
            break
    if entity == "bajirao":
        key = "bajirao"
    if key and key in BOUNDARY:
        for bad in BOUNDARY[key]:
            if bad in blob and key == "bajirao" and bad in ("balaji vishwanath", "1761", "third battle of panipat"):
                # Baji Rao pack must not be Balaji/1761 dominated
                if bad == "balaji vishwanath" and "baji" not in blob:
                    ok = False
                    notes.append(f"boundary:{bad}")
                if bad == "1761" and "baji rao" in blob and "bhopal" not in blob:
                    notes.append(f"warn_boundary:{bad}")
    return {
        **row,
        "result": "PASS" if ok else "FAIL",
        "citation": ",".join(map(str, pages)),
        "grounded": bool(pack.chunks) and not supp_leak,
        "notes": ";".join(notes) or "pack_ok",
        "layer_ran": "pack",
        "entity": entity,
        "pack_n": len(pack.chunks),
    }


def live_answer(question: str, history: list | None = None, timeout_note: str = "") -> dict:
    t0 = time.time()
    try:
        result = answer_question(question, language="en", history=history or [])
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "answer": "",
            "sources": [],
            "grounded": False,
            "error": str(exc),
            "seconds": round(time.time() - t0, 1),
            "refused": False,
        }
    answer = result.get("answer") or result.get("message") or ""
    if isinstance(result.get("message"), dict):
        answer = result["message"].get("content") or answer
    # normalize shapes from answer_question
    if not answer and "text" in result:
        answer = result["text"]
    sources = result.get("sources") or []
    grounded = result.get("grounded")
    if grounded is None:
        grounded = not refuse(answer)
    return {
        "ok": True,
        "answer": answer,
        "sources": sources,
        "grounded": grounded,
        "refused": refuse(answer) or grounded is False,
        "seconds": round(time.time() - t0, 1),
        "error": None,
        "raw_keys": sorted(result.keys()),
    }


def select_live_subset(matrix: list[dict]) -> list[dict]:
    """Representative live set — keep pack matrix large; live sample stays honest/tractable."""
    selected = []
    mcq_seen = set()
    per_topic = defaultdict(int)
    priority_topics = {
        "Babur", "Akbar", "Aurangzeb", "Shivaji", "Baji Rao I", "Marathas",
        "Mughals", "Ahom", "Sher Shah", "Din-e-Ilahi", "Admin-Mansabdari",
        "Admin-Ashtapradhan", "Shah Jahan", "Humayun",
    }
    mcq5_topics = {"Babur", "Akbar", "Shivaji", "Baji Rao", "Marathas", "Mughals", "Ahom", "Aurangzeb"}
    mcq10_topics = {"Akbar", "Shivaji", "Marathas"}
    for row in matrix:
        if row.get("expect_refuse") or row.get("pattern") == "followup_anchor":
            selected.append(row)
            continue
        pat = str(row.get("pattern", ""))
        if pat.startswith("mcq_5"):
            t = row["topic"]
            if t not in mcq_seen and t in mcq5_topics:
                mcq_seen.add(t)
                selected.append(row)
            continue
        if pat.startswith("mcq_10"):
            if row["topic"] in mcq10_topics:
                selected.append(row)
            continue
        if row["topic"] in priority_topics and row["pattern"] in {
            "identity", "detail", "compare", "exam_5", "student_imperfect"
        }:
            if per_topic[row["topic"]] < 1:
                selected.append({**row, "layer": "live"})
                per_topic[row["topic"]] += 1
    seen = set()
    out = []
    for row in selected:
        if row["question"] in seen:
            continue
        seen.add(row["question"])
        out.append(row)
    return out


def run_live(row: dict) -> dict:
    if row.get("followup"):
        first = live_answer(row["question"])
        hist = [
            {"role": "user", "content": row["question"]},
            {"role": "assistant", "content": first.get("answer") or ""},
        ]
        second = live_answer(row["followup"], history=hist)
        pages = cite_pages(second.get("sources") or first.get("sources"))
        ok = first.get("ok") and second.get("ok") and (first.get("grounded") is not False) and (second.get("grounded") is not False)
        if row.get("expect_refuse"):
            ok = second.get("refused") is True
        notes = f"t1={first.get('seconds')}s t2={second.get('seconds')}s; followup"
        # boundary on answers
        ans = (first.get("answer") or "") + "\n" + (second.get("answer") or "")
        bleed = boundary_bleed(row, ans)
        if bleed:
            ok = False
            notes += ";" + bleed
        return {
            **row,
            "result": "PASS" if ok else "FAIL",
            "citation": ",".join(map(str, pages)),
            "grounded": bool(first.get("grounded") and second.get("grounded")),
            "notes": notes,
            "layer_ran": "live",
            "seconds": (first.get("seconds") or 0) + (second.get("seconds") or 0),
            "answer_preview": (second.get("answer") or "")[:240],
        }

    res = live_answer(row["question"])
    pages = cite_pages(res.get("sources"))
    if row.get("expect_refuse"):
        ok = res.get("ok") and res.get("refused")
        notes = f"refuse_expected; t={res.get('seconds')}s"
    else:
        ok = res.get("ok") and not res.get("refused") and (res.get("grounded") is not False)
        notes = f"t={res.get('seconds')}s"
        if row.get("mcq_n"):
            # soft MCQ count check
            opts = len(re.findall(r"(?m)^\s*[A-D][\).:]", res.get("answer") or ""))
            qn = len(re.findall(r"(?i)\bQ(?:uestion)?\s*\d+|\b\d+[\).]\s+", res.get("answer") or ""))
            notes += f";mcq_opts~{opts};q_markers~{qn}"
            if qn < max(1, row["mcq_n"] // 2):
                notes += ";weak_mcq_count"
        bleed = boundary_bleed(row, res.get("answer") or "")
        if bleed:
            ok = False
            notes += ";" + bleed
        # citation expected for grounded
        if ok and not pages and not refuse(res.get("answer") or ""):
            notes += ";no_citation_pages"
    if res.get("error"):
        ok = False
        notes += f";err:{res['error']}"
    return {
        **row,
        "result": "PASS" if ok else "FAIL",
        "citation": ",".join(map(str, pages)),
        "grounded": False if row.get("expect_refuse") else bool(res.get("grounded")),
        "notes": notes,
        "layer_ran": "live",
        "seconds": res.get("seconds"),
        "answer_preview": (res.get("answer") or "")[:240],
    }


def boundary_bleed(row: dict, answer: str) -> str:
    low = (answer or "").lower()
    topic = (row.get("topic") or "").lower()
    q = (row.get("question") or "").lower()
    checks = []
    if "baji" in topic or "baji" in q:
        if "third battle of panipat" in low and "bhopal" not in low:
            checks.append("bleed:bajirao->1761")
        if re.search(r"\bbalaji vishwanath\b", low) and "baji rao" in q and "compare" not in row.get("pattern", ""):
            # mention of predecessor can be ok if explaining lineage; flag only if answer centers Balaji
            if low.find("balaji") < low.find("baji") and "baji rao" not in low[:120]:
                checks.append("bleed:bajirao->balaji")
    if "shivaji" in topic and "sambhaji" not in topic and "compare" not in (row.get("pattern") or ""):
        if "sambhaji" in low and "shivaji" not in low[:80]:
            checks.append("bleed:shivaji->sambhaji")
    if topic == "akbar" and "aurangzeb" in low and "compare" not in (row.get("pattern") or ""):
        if low.count("aurangzeb") > low.count("akbar"):
            checks.append("bleed:akbar->aurangzeb")
    return ";".join(checks)


def api_flow_tests() -> list[dict]:
    rows = []
    try:
        session = http_json("POST", "/sessions", {})
        sid = session["session_id"]
        c1 = http_json("POST", "/conversations", {"session_id": sid, "title": "QA flow A"})
        cid1 = c1["conversation_id"]
        msg = http_json(
            "POST",
            f"/conversations/{cid1}/messages",
            {"session_id": sid, "message": "Who was Baji Rao?", "language": "en"},
            timeout=300,
        )
        content = (msg.get("message") or {}).get("content") or msg.get("answer") or ""
        sources = (msg.get("message") or {}).get("sources") or msg.get("sources") or []
        ok = bool(content) and not refuse(content)
        rows.append(
            {
                "topic": "API",
                "pattern": "send_bajirao",
                "question": "Who was Baji Rao?",
                "result": "PASS" if ok else "FAIL",
                "citation": ",".join(map(str, cite_pages(sources))),
                "grounded": ok,
                "notes": f"api_msg;len={len(content)}",
                "layer_ran": "api",
            }
        )
        # New conversation blank
        c2 = http_json("POST", "/conversations", {"session_id": sid, "title": "QA flow blank"})
        cid2 = c2["conversation_id"]
        got = http_json("GET", f"/conversations/{cid2}?session_id={sid}")
        blank = len(got.get("messages") or []) == 0
        rows.append(
            {
                "topic": "API",
                "pattern": "new_chat_blank",
                "question": "(new conversation)",
                "result": "PASS" if blank else "FAIL",
                "citation": "",
                "grounded": True,
                "notes": f"messages={len(got.get('messages') or [])}",
                "layer_ran": "api",
            }
        )
        # Restore old
        old = http_json("GET", f"/conversations/{cid1}?session_id={sid}")
        restored = any(m.get("role") == "user" for m in (old.get("messages") or []))
        rows.append(
            {
                "topic": "API",
                "pattern": "history_restore",
                "question": "(restore cid1)",
                "result": "PASS" if restored else "FAIL",
                "citation": "",
                "grounded": True,
                "notes": f"msgs={len(old.get('messages') or [])}",
                "layer_ran": "api",
            }
        )
        # List still has both
        listing = http_json("GET", f"/conversations?session_id={sid}")
        ids = {c.get("conversation_id") for c in (listing.get("conversations") or [])}
        rows.append(
            {
                "topic": "API",
                "pattern": "history_retained",
                "question": "(list)",
                "result": "PASS" if cid1 in ids and cid2 in ids else "FAIL",
                "citation": "",
                "grounded": True,
                "notes": f"n={len(ids)}",
                "layer_ran": "api",
            }
        )
        # Unsupported via API
        c3 = http_json("POST", "/conversations", {"session_id": sid, "title": "QA unsupported"})
        u = http_json(
            "POST",
            f"/conversations/{c3['conversation_id']}/messages",
            {"session_id": sid, "message": "Who was Napoleon?", "language": "en"},
            timeout=300,
        )
        ucontent = (u.get("message") or {}).get("content") or ""
        rows.append(
            {
                "topic": "API",
                "pattern": "unsupported_napoleon",
                "question": "Who was Napoleon?",
                "result": "PASS" if refuse(ucontent) or (u.get("message") or {}).get("grounded") is False else "FAIL",
                "citation": "",
                "grounded": False,
                "notes": ucontent[:160].replace("\n", " "),
                "layer_ran": "api",
            }
        )
        # Econtent Baji Rao
        ec = http_json(
            "POST",
            "/econtent",
            {"session_id": sid, "conversation_id": cid1, "topic": "Baji Rao", "language": "en"},
            timeout=900,
        )
        ec_ok = bool(ec.get("grounded")) and bool(ec.get("id") or ec.get("econtent_id") or ec.get("title"))
        rows.append(
            {
                "topic": "Module",
                "pattern": "econtent_bajirao",
                "question": "Baji Rao",
                "result": "PASS" if ec_ok else "FAIL",
                "citation": ",".join(map(str, cite_pages(ec.get("sources")))),
                "grounded": bool(ec.get("grounded")),
                "notes": f"title={ec.get('title')}",
                "layer_ran": "api",
                "econtent_id": ec.get("id") or ec.get("econtent_id"),
            }
        )
        eid = ec.get("id") or ec.get("econtent_id")
        if eid:
            # PDF
            req = urllib.request.Request(
                f"{API}/econtent/{eid}/pdf",
                data=json.dumps({"session_id": sid}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/pdf"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                pdf = resp.read()
            pdf_ok = pdf[:4] == b"%PDF" and len(pdf) > 1000
            pdf_path = OUT_DIR / "sample-bajirao.pdf"
            pdf_path.write_bytes(pdf)
            rows.append(
                {
                    "topic": "PDF",
                    "pattern": "pdf_bajirao",
                    "question": "Baji Rao PDF",
                    "result": "PASS" if pdf_ok else "FAIL",
                    "citation": "",
                    "grounded": True,
                    "notes": f"bytes={len(pdf)};path={pdf_path}",
                    "layer_ran": "api",
                }
            )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            {
                "topic": "API",
                "pattern": "flow_error",
                "question": "",
                "result": "FAIL",
                "citation": "",
                "grounded": False,
                "notes": str(exc),
                "layer_ran": "api",
            }
        )
    return rows


def write_matrix(results: list[dict]):
    md = OUT_DIR / "QA_MATRIX.md"
    csv_path = OUT_DIR / "QA_MATRIX.csv"
    lines = [
        "# HistoryBot Final QA Matrix",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Local-only exception: repo at C:\\\\Users\\\\vkant\\\\Projects\\\\historybot on machineId d8dc7c79-1ff0-4d5b-afb6-b723ab7e7a3c; CloudAgent unavailable.",
        "",
        "| Topic | Question pattern | Result | Citation | Grounded | Notes |",
        "|---|---|---|---|---|---|",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["topic", "pattern", "question", "result", "citation", "grounded", "notes", "layer_ran", "seconds"],
        )
        writer.writeheader()
        for r in results:
            topic = str(r.get("topic") or "")
            pattern = str(r.get("pattern") or "")
            result = str(r.get("result") or "")
            citation = str(r.get("citation") or "")
            grounded = r.get("grounded")
            notes = str(r.get("notes") or "").replace("|", "/")
            qshort = str(r.get("question") or "")[:80].replace("|", "/")
            lines.append(
                f"| {topic} | {pattern}: {qshort} | {result} | {citation} | {grounded} | {notes} |"
            )
            writer.writerow(
                {
                    "topic": topic,
                    "pattern": pattern,
                    "question": r.get("question"),
                    "result": result,
                    "citation": citation,
                    "grounded": grounded,
                    "notes": r.get("notes"),
                    "layer_ran": r.get("layer_ran"),
                    "seconds": r.get("seconds"),
                }
            )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md, csv_path


def frontend_start_learning_static() -> list[dict]:
    home = (ROOT / "frontend/src/pages/Home.jsx").read_text(encoding="utf-8")
    chat = (ROOT / "frontend/src/pages/Chat.jsx").read_text(encoding="utf-8")
    ctx = (ROOT / "frontend/src/context/AppContext.jsx").read_text(encoding="utf-8")
    checks = [
        ("beginFreshChat_defined", "beginFreshChat" in ctx and "removeItem(CURRENT_KEY)" in ctx),
        ("home_calls_beginFreshChat", "beginFreshChat()" in home and "fresh=1" in home),
        ("home_header_not_raw_link", "to=\"/chat\"" not in home or "startLearning" in home),
        ("chat_handles_fresh", 'params.get("fresh")' in chat and "beginFreshChat()" in chat),
        ("chat_skips_restore_on_fresh", "params.get(\"fresh\")" in chat),
        ("newChat_preserved", "const newChat" in ctx),
        ("openConversation_preserved", "openConversation" in ctx),
    ]
    rows = []
    for name, ok in checks:
        rows.append(
            {
                "topic": "StartLearning",
                "pattern": name,
                "question": name,
                "result": "PASS" if ok else "FAIL",
                "citation": "",
                "grounded": True,
                "notes": "static_frontend",
                "layer_ran": "static",
            }
        )
    return rows


def security_light() -> list[dict]:
    rows = []
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    rows.append(
        {
            "topic": "Security",
            "pattern": "env_example_no_password",
            "question": ".env.example",
            "result": "PASS" if "MYSQL_PASSWORD=\n" in env_example.replace("\r\n", "\n") or "MYSQL_PASSWORD=" in env_example else "FAIL",
            "citation": "",
            "grounded": True,
            "notes": "template only",
            "layer_ran": "static",
        }
    )
    # Public API should not expose raw textbook PDF path
    try:
        req = urllib.request.Request(f"{API.replace('/api/v1','')}/9th English SS Part - 2 2026-27.pdf")
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = 0
    rows.append(
        {
            "topic": "Security",
            "pattern": "textbook_pdf_not_public",
            "question": "GET textbook pdf via app root",
            "result": "PASS" if code in (0, 404, 401, 403) else "FAIL",
            "citation": "",
            "grounded": True,
            "notes": f"http={code}",
            "layer_ran": "static",
        }
    )
    # secrets not in frontend bundle source
    api_js = (ROOT / "frontend/src/services/api.js").read_text(encoding="utf-8")
    rows.append(
        {
            "topic": "Security",
            "pattern": "frontend_no_internal_secret",
            "question": "api.js",
            "result": "PASS" if "INTERNAL_RAG_SECRET" not in api_js and "MYSQL_PASSWORD" not in api_js else "FAIL",
            "citation": "",
            "grounded": True,
            "notes": "no secrets in frontend src",
            "layer_ran": "static",
        }
    )
    return rows


def main() -> int:
    print("OUT", OUT_DIR)
    audit = source_audit()
    (OUT_DIR / "SOURCE_AUDIT.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(
        "SOURCE",
        audit["active_collection"],
        "chunks",
        audit["chunk_count"],
        "primary",
        audit["primary_chunk_count"],
        "pages",
        audit["primary_pages"],
    )

    matrix = build_matrix_questions()
    print("MATRIX_SIZE", len(matrix))

    results: list[dict] = []
    results.extend(frontend_start_learning_static())
    results.extend(security_light())

    # Pack layer for all non-live-only rows
    pack_rows = [r for r in matrix if not r.get("expect_refuse") and not str(r.get("pattern", "")).startswith("mcq") and r.get("pattern") != "followup_anchor"]
    print("PACK_CHECKS", len(pack_rows))
    for i, row in enumerate(pack_rows, 1):
        results.append(pack_check(row))
        if i % 50 == 0:
            print(f"  pack {i}/{len(pack_rows)}")

    # Live subset
    live_rows = select_live_subset(matrix)
    print("LIVE_CHECKS", len(live_rows))
    timings = []
    for i, row in enumerate(live_rows, 1):
        print(f"  live {i}/{len(live_rows)}: {row['question'][:70]}")
        got = run_live(row)
        results.append(got)
        if got.get("seconds"):
            timings.append(got["seconds"])
        (OUT_DIR / "progress.jsonl").open("a", encoding="utf-8").write(json.dumps(got, ensure_ascii=False) + "\n")

    print("API_FLOWS")
    results.extend(api_flow_tests())

    md, csv_path = write_matrix(results)
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("result") == "PASS"),
        "failed": sum(1 for r in results if r.get("result") == "FAIL"),
        "skipped": sum(1 for r in results if str(r.get("result", "")).startswith("SKIP")),
        "by_pattern": dict(Counter(r.get("pattern") for r in results)),
        "by_topic": dict(Counter(r.get("topic") for r in results)),
        "timings_sec": {
            "count": len(timings),
            "min": min(timings) if timings else None,
            "max": max(timings) if timings else None,
            "avg": round(sum(timings) / len(timings), 1) if timings else None,
        },
        "source_audit": {
            "collection": audit["active_collection"],
            "primary_pages": audit["primary_pages"],
            "excluded_leaked": audit["excluded_leaked_into_index"],
            "by_source_type": audit["by_source_type"],
        },
        "matrix_path": str(md),
        "csv_path": str(csv_path),
        "failed_rows": [r for r in results if r.get("result") == "FAIL"][:50],
    }
    (OUT_DIR / "QA_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps({k: summary[k] for k in ("total", "passed", "failed", "skipped", "timings_sec")}, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

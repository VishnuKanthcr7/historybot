"""Deterministic unit tests for the final dev run (no LLM, no network).

Covers: stray full stops (sanitize), key-term evidence trimming and refusal guard helpers,
and the PDF markdown flow. Run: python scripts/final_unit_tests.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["OPENAI_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["HISTORYBOT_LLM_PROVIDER"] = "ollama"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.engine.sanitize import is_structural_line, sanitize_student_text  # noqa: E402
from rag.engine import answer as ans  # noqa: E402
from rag.prompts.tutor import NOT_IN_TEXTBOOK  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}{' - ' + str(detail) if detail and not ok else ''}")


# --- Part 3C: no full stop after headings, tables, list items, citations -----
sample = """Akbar was a Mughal king

**Important points:**

* Akbar was born in Amarkot
\u2022 He abolished the Jizya tax
1. He divided the kingdom into Subhas
## Administration

| | Akbar | Aurangzeb |
| --- | --- | --- |
| Born | Amarkot | Not given in the textbook |

Source: Class 9 Karnataka State Board 2026-27 textbook, pages 5, 6"""
out = sanitize_student_text(sample)
lines = out.splitlines()
check("prose line still ends with a full stop", "Akbar was a Mughal king." in out, out)
check("bold heading keeps no full stop", "**Important points:**" in lines, out)
check("markdown heading keeps no full stop", "## Administration" in lines, out)
check("table rows unchanged", "| Born | Amarkot | Not given in the textbook |" in lines and "| --- | --- | --- |" in lines, out)
check("bullet items get no added full stop", "* Akbar was born in Amarkot" in lines and "1. He divided the kingdom into Subhas" in lines, out)
check("bullet marker \u2022 kept", "\u2022 He abolished the Jizya tax" in lines, out)
check("citation line unchanged", lines[-1].startswith("Source: Class 9") and not lines[-1].endswith(".."), out)
check("no '**.' anywhere", "**." not in out and "|." not in out, out)
for line in ["## Heading", "**Bold**", "| a | b |", "|---|---|", "Source: x", "Textbook pages 12, 13", "Important points:"]:
    check(f"structural: {line}", is_structural_line(line))
for line in ["Akbar was a king.", "He ruled for many years"]:
    check(f"not structural: {line}", not is_structural_line(line))

# --- Part 3A: key term trimming and detection -------------------------------
long_text = ("Akbar organised the army well. " * 22) + "He brought the Zabti system into practice. Land was measured with bamboo sticks."
trimmed = ans._trim_passage(long_text, focus=frozenset({"zabti"}))
check("trim keeps a term that sits past the cut", "zabti" in trimmed.lower(), trimmed[-120:])
check("trim stays bounded", len(trimmed) <= 900, len(trimmed))
check("trim without focus is unchanged behaviour", "zabti" not in ans._trim_passage(long_text).lower())
check("key terms drop generic words", ans._key_terms("What is zabti?") == frozenset({"zabti"}), ans._key_terms("What is zabti?"))
check("key terms for a battle keep the name", "plassey" in ans._key_terms("Who won the Battle of Plassey?"))
terms, matched = ans._evidence_has_key_terms("What is mansabdar system?", [{"text": "The Mansabdari system ranked officers."}])
check("prefix match: mansabdar -> mansabdari", len(matched) == 1, terms)
terms, matched = ans._evidence_has_key_terms("Who won the Battle of Plassey?", [{"text": "The battle of Panipat was fought in 1526."}])
check("missing topic has no matching evidence", not matched, terms)

# --- refusal detector --------------------------------------------------------
check("exact refusal detected", ans._is_not_found(NOT_IN_TEXTBOOK))
check("short refusal with lead-in detected", ans._is_not_found("Zabti is not in the passages. " + NOT_IN_TEXTBOOK))
table = "Here is a table:\n\n| | A | B |\n|---|---|---|\n| x | y | z |\n\nNote: The textbook does not provide B's birthplace."
check("table with a partial note is not a refusal", not ans._is_not_found(table))
check("normal answer is not a refusal", not ans._is_not_found("Akbar was a king. He ruled well."))

# --- Part 3B: who did what --------------------------------------------------
ev = [{"text": "Shivaji built a new fort called Pratapgad. Since Shivaji fought against Vijayapura Sultans, "
               "his father, Shahaji, was captured by the Sultan. On the assurance that he would not launch "
               "further attacks against the sultanate, Shahaji was released. Shivaji was born in Shivneri."}]
wrong = "\u2022 He was captured by the Sultan, but was released later."
fixed, n = ans._fix_swapped_subjects(wrong, ev)
check("swapped subject is restored from the passage", n == 1 and fixed.startswith("\u2022 His father, Shahaji, was captured"), fixed)
fixed, n = ans._fix_swapped_subjects("Shivaji was captured by the Sultan.", ev)
check("named wrong subject is restored", n == 1 and fixed.startswith("His father, Shahaji, was captured"), fixed)
for good in ["His father, Shahaji, was captured by the Sultan.", "Shivaji was born in Shivneri.", "Shahaji was released."]:
    out_line, n = ans._fix_swapped_subjects(good, ev)
    check(f"correct line unchanged: {good[:30]}", n == 0 and out_line == good, out_line)

# --- Part 4: misspelt textbook names, short terms, unsupported sentences --------
check("spelling: akbr -> Akbar", "Akbar" in ans._correct_textbook_spelling("who was akbr"), ans._correct_textbook_spelling("who was akbr"))
check("spelling: shershah -> Sher Shah", "Sher Shah" in ans._correct_textbook_spelling("tell me about shershah"))
py_q = "How do I write a for loop in Python?"
check("spelling: ordinary words unchanged", ans._correct_textbook_spelling(py_q) == py_q, ans._correct_textbook_spelling(py_q))
check("domain: short textbook term 'dagh' is in domain", not ans._current_question_outside_domain("What is dagh?"))
check("domain: python stays outside", ans._current_question_outside_domain("How do I write a for loop in Python?"))
support = [{"text": "Akbar abolished the Jizya tax on Hindus. He brought the Zabti system into practice."}]
kept, dropped = ans._drop_unsupported_sentences(
    "Akbar abolished the Jizya tax on Hindus.\nThe Quit India Movement was started by Mahatma Gandhi in August 1942.", support
)
check("unsupported sentence dropped, supported kept", dropped == 1 and "Jizya" in kept and "Quit India" not in kept, kept)
kept, dropped = ans._drop_unsupported_sentences("| a | b |\n**Heading**\nThe textbook does not give his birthplace.", support)
check("tables, headings and textbook notes are kept", dropped == 0, kept)

# --- PDF markdown flow ---------------------------------------------------------
try:
    from rag.pdf import render

    class _Styles(dict):
        pass

    styles = _Styles(HBH="H", HBSub="S", HBBody="B")
    seen = []

    class _P:
        def __init__(self, text, style):
            seen.append((style, text))

    render.Paragraph = _P
    render._flow_markdown("## Shivaji\n\n**What did they do?**\n\nShivaji built **Pratapgad** fort.\nHe was brave.", styles)
    check("PDF: ## heading becomes a heading", ("H", "Shivaji") in seen, seen)
    check("PDF: bold-only line becomes a subheading", ("S", "What did they do?") in seen, seen)
    body = [text for style, text in seen if style == "B"]
    check("PDF: no literal ** in body", body and all("**" not in text for text in body), body)
    check("PDF: no full stop after subheading", not any(text.endswith("?**.") or text == "What did they do?." for _, text in seen), seen)
except ImportError as exc:
    check("PDF renderer importable", False, exc)

# Rare-term lexical rescue and long-bullet shortening (generic, no fixed answers).
import rag.engine.topic_map as _tm
_orig_loader = _tm.load_primary_chunks
_fake_corpus = (
    {"chunk_id": "c1", "page": 7, "text": "A separate department stamped the horses, known as 'dagh-mahali'."},
    {"chunk_id": "c2", "page": 7, "text": "Akbar organised the army into mansabs."},
)
_tm.load_primary_chunks = lambda: _fake_corpus
try:
    rescued, n_added = ans._lexical_rescue("What is dagh?", [_fake_corpus[1]])
    check("lexical rescue adds the chunk naming a rare term", n_added == 1 and rescued[0]["chunk_id"] == "c1", rescued)
    same, n_none = ans._lexical_rescue("What is dagh?", list(_fake_corpus))
    check("lexical rescue does nothing when already retrieved", n_none == 0 and len(same) == 2)
    _, n_missing = ans._lexical_rescue("What is zzqword?", [_fake_corpus[1]])
    check("lexical rescue adds nothing for an absent term", n_missing == 0)
finally:
    _tm.load_primary_chunks = _orig_loader
long_bullets = (
    "- Short fact about a ruler here.\n"
    "- He adopted a policy of tolerance towards Hindus, permitting his wives to worship their gods in the palace and abolishing a tax on Hindus.\n"
    "Source: Class 9 textbook, page 5"
)
short_out, n_short = ans._shorten_long_bullets(long_bullets)
check("long bullet cut at clause break", n_short == 1 and "- He adopted a policy of tolerance towards Hindus." in short_out.split("\n"), short_out)
check("short bullet and source line untouched", short_out.split("\n")[0] == "- Short fact about a ruler here." and short_out.split("\n")[2].startswith("Source:"), short_out)
check("non-bullet prose never shortened", ans._shorten_long_bullets("x " * 40)[1] == 0)

check("renumber closes a gap left by a dropped item",
      ans._renumber_lists("Intro.\n\n1. A.\n3. B.\n4. C.\n\nEnd.") == "Intro.\n\n1. A.\n2. B.\n3. C.\n\nEnd.")
check("renumber restarts after a paragraph", ans._renumber_lists("1. A\n2. B\nText\n5. C") == "1. A\n2. B\nText\n1. C")
check("exam answers count as point lists", ans._wants_bullets("Write an exam answer on the Mansabdari system."))

check("refusal guard keeps short off-textbook terms (GDP)", "gdp" in ans._guard_terms("What is the GDP of India?"), ans._guard_terms("What is the GDP of India?"))
_, gdp_hits = ans._evidence_has_key_terms("What is the GDP of India?", [{"text": "North India had many rivers."}], ans._guard_terms("What is the GDP of India?"))
check("GDP question finds no passage naming every guard term", not gdp_hits)
check("guard terms skip common short words", not (ans._guard_terms("Who was Akbar and how did he rule?") & {"who", "was", "how", "did"}))

from rag.engine.sanitize import sanitize_structured as _ss
_doc = _ss({"important_people": [{"name": "Shivaji", "note": "Shivaji built forts", "pages": [13]}],
            "important_terms": [{"term": "Ashtapradhan", "meaning": "Eight ministers", "pages": [14]}],
            "mcqs": [{"question": "Who was Shivaji's guru?", "options": ["Dadoji Kondadeo", "Jaisingh"], "answer": "Dadoji Kondadeo", "pages": [13]}],
            "text": "His father was captured by the Sultan. [Page 13]"})
check("people name gets no added full stop", _doc["important_people"][0]["name"] == "Shivaji", _doc["important_people"][0])
check("term label gets no added full stop", _doc["important_terms"][0]["term"] == "Ashtapradhan", _doc["important_terms"][0])
check("MCQ answer stays equal to an option", _doc["mcqs"][0]["answer"] in _doc["mcqs"][0]["options"], _doc["mcqs"][0])
check("note prose still ends with a full stop", _doc["important_people"][0]["note"].endswith("."), _doc["important_people"][0]["note"])
check("no full stop after a [Page N] citation", _doc["text"].endswith("[Page 13]"), _doc["text"])
from rag.engine import econtent as _ec
_prior = "In addition to defeating the kingdoms, Aurangzeb had determined to vanquish the Maratha kingdom completely."
check("econtent keeps 'he' rather than guessing the module subject",
      "Shivaji appointed" not in (_ec._clarify_pronoun_sentence("To achieve this, he appointed Shaista Khan and Jaisingh.", _prior, ["Shivaji"], "Shivaji") or ""))
check("econtent still names the subject when the previous sentence is about them",
      (_ec._clarify_pronoun_sentence("Towards this end, he assembled an army.", "In his childhood, Shivaji dreamt of a kingdom.", [], "Shivaji") or "").startswith("Towards this end, Shivaji"))

check("module title gets no added full stop", _ec._sanitize_content({"title": "Class 9 History: Shivaji"}).get("title") == "Class 9 History: Shivaji", _ec._sanitize_content({"title": "Class 9 History: Shivaji"}))
_src = ["In addition, Aurangzeb had determined to vanquish the Maratha kingdom completely. To achieve this, he appointed Shaista Khan and Jaisingh."]
check("list row keeps 'he' when the textbook sentence before is about someone else",
      "Shivaji" not in _ec._clarify_list_item("To achieve this, he appointed Shaista Khan and Jaisingh.", ["Shivaji"], "Shivaji", _src))

check("list row with unknown context keeps a mid-sentence 'he'",
      _ec._clarify_list_item("To achieve this, he appointed Shaista Khan and Jaisingh.", ["Shivaji"], "Shivaji", []) == "To achieve this, he appointed Shaista Khan and Jaisingh.")

_rep, _n_rep = ans._drop_repeated_sentences("The king appointed generals and ministers and framed laws for the kingdom.\n\nExplanation: According to the textbook, the king appointed generals and ministers and framed laws for the kingdom.\n\nSource: Class 9 textbook, page 10")
check("restated sentence is dropped once", _n_rep == 1 and _rep.count("appointed generals") == 1 and _rep.endswith("page 10"), _rep)
check("a longer sentence that adds facts is kept", ans._drop_repeated_sentences("Akbar was born in Amarkot in Sindh. Akbar was born in Amarkot in Sindh and became king at thirteen after Humayun died.")[1] == 0)
check("spelling: kalinga is not turned into a textbook name", "kalinjar" not in ans._correct_textbook_spelling("What did Emperor Ashoka do after the Kalinga war?").lower(), ans._correct_textbook_spelling("What did Emperor Ashoka do after the Kalinga war?"))

_prev = "Akbar was a famous Mughal king who was born in Amarkot. His father was Humayun who ruled before him. Akbar abolished the Jizya tax on Hindus in his empire."
check("re-explain detector counts restated sentences", ans._repeated_prior_sentences(_prev + " Source: x", _prev) == 3)
check("re-explain detector ignores new wording", ans._repeated_prior_sentences("Akbar was a great king. He was kind to all people of his land.", _prev) == 0)

# --- Answer depth: "tell me more" follow-ups (mocked LLM and retrieval) -------
_FIRST_Q = "Explain the Mansabdari system."
_FIRST_A = (
    "The **Mansabdari system** was a unique feature of Akbar's administration. It organised his army into ranks called **Mansabs**.\n\n"
    "- **Akbar** established Mansabs, meaning different ranks or levels in the army.\n"
    "- **Mansabdars** were the supervisors of these ranks.\n"
    "- **The Mughal king** had the duty of appointing Mansabdars.\n"
    "- **The Mughal army** included infantry (foot soldiers), cavalry (horse soldiers), elephant units and cannon units.\n"
    "- **The dagh-mahali** was a separate department for stamping horses.\n\n"
    "Source: Class 9 Karnataka State Board 2026-27 textbook, pages 7, 10"
)
_HIST = [
    {"role": "user", "content": _FIRST_Q},
    {"role": "assistant", "content": _FIRST_A, "task_state": {"type": "EXPLAIN", "used_chunk_ids": ["m1", "m2"]}},
]


def _chunk(cid, page, text):
    return {"chunk_id": cid, "printed_page_number": page, "textbook_page_number": page, "text": text,
            "authority": "primary", "source_type": "primary_textbook"}


_CHUNKS = [
    _chunk("m1", 7, "The Mansabdari system was a unique feature of his administration. Akbar was the supreme head of his empire, the commander-in-chief of his army, head of the executive and judiciary. There were four ministers called Vakil, Diwan, Mir Bhakshi and Main Sardar to assist him in the administration."),
    _chunk("m2", 7, "Akbar had established many hierarchies in his army. These were called Mansabs and its supervisors were called Mansabdars. There were infantry, cavalry, elephant units and cannon units in the Mughal army. There was a separate department to stamp the horses known as dagh-mahali."),
    _chunk("m3", 10, "The Mughal kings had the authority to appoint or dismiss military generals and ministers. The appointment of mansabdars, giving jagirs and framing laws were the duties of the king. The provincial administration was taken care of by the governor, Diwan, Bakhshi and Faujdar."),
    _chunk("m4", 7, "For administrative convenience, Akbar had divided his kingdom into the Central government, provincial government and parganas. By the end of Akbar's reign there were 15 subahs. Each subha had a Sipah Salar, a diwan and a bakhshi. The Mansabdari system was a unique feature of his administration."),
] + [
    _chunk(f"x{i}", 20 + i, f"The Mughal administration had officers number {i} who kept records of the army, the land and the revenue of every district in the kingdom of Akbar, and the Mansabdars reported to them.")
    for i in range(8)
]
_NEW_ANSWER = (
    "The Mansabdari system was a unique feature of Akbar's administration.\n\n"
    "## How it fitted into the government\n"
    "Akbar was the supreme head of his empire and the commander-in-chief of his army. "
    "Four ministers called Vakil, Diwan, Mir Bhakshi and Main Sardar assisted him in the administration.\n\n"
    "## Who appointed the Mansabdars\n"
    "The appointment of mansabdars, giving jagirs and framing laws were the duties of the king.\n\n"
    "## Summary\nThe Mansabdari system linked the army ranks to the king's administration."
)
_calls = []
_replies = []


def _fake_complete(messages, **kw):
    _calls.append({"messages": messages, "kw": kw})
    return _replies.pop(0) if _replies else _NEW_ANSWER


def _fake_retrieve(query, top_k=8, language="en"):
    return [dict(item) for item in _CHUNKS][:top_k]


_saved = (ans.complete, ans.retrieve_primary, ans.topic_supported_by_primary)
ans.complete, ans.retrieve_primary, ans.topic_supported_by_primary = _fake_complete, _fake_retrieve, (lambda q: None)
try:
    for q in [
        "can you more on this i mean mansabadri system",
        "Can you tell me more about this, I mean the Mansabdari system?",
        "tell me more",
        "Elaborate on the Mansabdari system",
        "Explain the Mansabdari system in detail",
        "Can you go deeper into this?",
        "Could you say more about it?",
    ]:
        check(f"depth request detected: {q!r}", ans._depth_request(q, q, _HIST) is not None)
    for q in [
        "Explain the Mansabdari system.",
        "Who was Akbar?",
        "Explain it again more simply",
        "Give me more questions",
        "Which ruler had more power, Akbar or Babur?",
        "Tell me more briefly",
    ]:
        check(f"not a depth request: {q!r}", ans._depth_request(q, q, _HIST) is None, ans._depth_request(q, q, _HIST))

    _d = ans._depth_request("can you more on this i mean mansabadri system", "can you more on this i mean mansabadri system", _HIST)
    check("topic resolved from a typo'd message", _d and _d["topic"].lower() == "mansabdari system" and _d["followup"], _d)
    _d = ans._depth_request("tell me more", "tell me more", _HIST)
    check("topic resolved from history for a bare 'tell me more'", _d and "mansabdari system" in _d["topic"].lower() and _d["followup"], _d)
    check("follow-up carries the previous answer (without the Source line)", _d and "dagh-mahali" in _d["previous_answer"] and "Source:" not in _d["previous_answer"])
    check("follow-up carries the chunks the previous answer used", _d and _d["used_ids"] == {"m1", "m2"}, _d)
    _d = ans._depth_request("Tell me more about the Zabti system", "Tell me more about the Zabti system", _HIST)
    check("a new topic is a detail request, not an expansion of the old answer",
          _d and _d["topic"].lower() == "zabti system" and not _d["followup"] and not _d["previous_answer"], _d)

    # Baseline prompt (ordinary question) vs depth prompt on the same retrieval.
    _calls.clear()
    ans.answer_question("What were the duties of the Mughal king?", "en", [], None)
    _base_prompt = _calls[0]["messages"][-1]["content"] if _calls else ""
    _calls.clear()
    _res = ans.answer_question("can you more on this i mean mansabadri system", "en", _HIST, None)
    _prompt = _calls[0]["messages"][-1]["content"] if _calls else ""
    _blocks = _prompt.count("[TEXTBOOK; printed_page=")
    check("depth follow-up goes to the model (no deterministic/fact-layer answer)", len(_calls) >= 1 and _res.get("validation_reason") == "reasoned_history", _res.get("validation_reason"))
    check("depth prompt includes the previous answer", "Previous answer:" in _prompt and "separate department for stamping horses" in _prompt)
    check("depth prompt asks to expand, not repeat", "deeper explanation of: Mansabdari system" in _prompt and "Do NOT repeat its bullet points" in _prompt)
    check("depth prompt sends more evidence than the old limit (6 passages)", _blocks > 6 and _blocks > _base_prompt.count("[TEXTBOOK; printed_page="), (_blocks, _base_prompt.count("[TEXTBOOK; printed_page=")))
    check("depth prompt evidence is larger than an ordinary prompt", len(_prompt) > len(_base_prompt) + 1500, (len(_prompt), len(_base_prompt)))
    check("depth request gets a larger token budget", _calls and _calls[0]["kw"].get("max_tokens", 0) >= 1400, _calls and _calls[0]["kw"])
    check("ordinary questions keep the old prompt (no depth block)", "deeper explanation of" not in _base_prompt and "Previous answer:" not in _base_prompt)
    check("expanded answer is not cut back by post-processing", "## Who Appointed the Mansabdars" in _res["answer"] and "Four ministers" in _res["answer"], _res["answer"])
    check("citations preserved on a depth answer", "Source: Class 9 Karnataka State Board" in _res["answer"] and "page" in _res["answer"].split("Source:")[-1], _res["answer"][-160:])
    check("no repetition retry when the answer is new", _res.get("depth_request", {}).get("retry") is False and len(_calls) == 1, _res.get("depth_request"))
    check("task state records a 'more' depth", (_res.get("task") or {}).get("depth") == "more", _res.get("task"))

    # Repetition guard: the model repeats the previous answer once, then gives new details.
    _calls.clear()
    _replies[:] = [_FIRST_A.split("\n\nSource:")[0], _NEW_ANSWER]
    _res = ans.answer_question("Can you tell me more about this, I mean the Mansabdari system?", "en", _HIST, None)
    check("repetition guard retries once with a 'new details' instruction",
          len(_calls) == 2 and "mostly repeated the previous answer" in _calls[1]["messages"][-1]["content"], len(_calls))
    check("retry answer replaces the repeat", "## Who Appointed the Mansabdars" in _res["answer"] and (_res.get("depth_request") or {}).get("retry") is True, _res.get("depth_request"))
    check("overlap of the repeated first draft is measured high", ((_res.get("depth_request") or {}).get("overlap_first") or 0) >= 0.5, _res.get("depth_request"))

    # Evidence exhausted: both drafts repeat -> honest note, still cited.
    _calls.clear()
    _replies[:] = [_FIRST_A.split("\n\nSource:")[0], _FIRST_A.split("\n\nSource:")[0]]
    _res = ans.answer_question("tell me more", "en", _HIST, None)
    check("repeated depth answer is measured but no 'textbook does not give more' note is printed (supplement policy)",
          "does not give more details" not in _res["answer"] and (_res.get("depth_request") or {}).get("exhausted") is True, _res["answer"][:160])
    check("exhausted answer keeps its citation", "Source: Class 9 Karnataka State Board" in _res["answer"])
    check("at most one repetition retry", len(_calls) == 2, len(_calls))

    _other = _chunk("s1", 14, "Army: The Maratha army had infantry, cavalry, elephant units and cannon units. There were important forts in Raigad and Sinhagad.")
    _same_page = _chunk("p7", 7, "Revenue system: This was one of the remarkable achievements of Akbar's administration.")
    _pool = ans._depth_pool("Mansabdari system", _CHUNKS[:4] + [_other, _same_page])
    check("depth evidence keeps topic passages and same-page context", {"m1", "m2", "m3", "m4", "p7"} <= {c["chunk_id"] for c in _pool}, [c["chunk_id"] for c in _pool])
    check("depth evidence drops another ruler's passage that only shares words", "s1" not in {c["chunk_id"] for c in _pool})
    _calls.clear()
    _res = ans.answer_question("Can you explain this in more detail?", "en", _HIST, None)
    check("bare 'explain this in more detail' after a textbook answer is not refused as off-domain",
          _res.get("validation_reason") == "reasoned_history" and (_res.get("depth_request") or {}).get("topic", "").lower() == "mansabdari system", (_res.get("validation_reason"), _res.get("depth_request")))
    _off_hist = [{"role": "user", "content": "How do I write a for loop in Python?"},
                 {"role": "assistant", "content": NOT_IN_TEXTBOOK}]
    _calls.clear()
    _res = ans.answer_question("Can you explain this in more detail?", "en", _off_hist, None)
    check("bare depth request after an off-topic question stays outside the textbook", NOT_IN_TEXTBOOK in _res["answer"] and not _calls, _res["answer"][:120])
    _calls.clear()
    _res = ans.answer_question("Can you tell me more about Python loops?", "en", _HIST, None)
    check("depth request about an off-topic subject is still refused", NOT_IN_TEXTBOOK in _res["answer"] and not _calls, _res["answer"][:120])
    _calls.clear()
    _replies[:] = [_FIRST_A.split("\n\nSource:")[0], _FIRST_A.split("\n\nSource:")[0] + "\n\n" + _NEW_ANSWER]
    _res = ans.answer_question("tell me more", "en", _HIST, None)
    check("a partly repeated answer that adds new sections is not labelled exhausted",
          not _res["answer"].startswith("The textbook does not give more details") and "Four ministers" in _res["answer"], (_res.get("depth_request"), _res["answer"][:120]))
    check("overlap helper: identical answers = 1.0", ans._repeat_overlap(_FIRST_A, _FIRST_A) == 1.0)
    check("overlap helper: new answer is low", ans._repeat_overlap(_NEW_ANSWER, _FIRST_A) < 0.5, ans._repeat_overlap(_NEW_ANSWER, _FIRST_A))

    # ---- Supplement policy (textbook first, labelled supplementary explanation) ----
    _LABELLED = (
        "**From your textbook**\n"
        "The Mansabdari system was a unique feature of Akbar's administration. "
        "Akbar had established many hierarchies in his army called Mansabs, and their supervisors were called Mansabdars.\n\n"
        "**Additional historical explanation**\n"
        "Each mansabdar held a rank that showed how many soldiers he had to keep. "
        "He was often paid through land revenue. See page 12 for more.\n\n"
        "**Quick revision**\n- Mansab means rank."
    )
    _tb, _sup, _rev, _lab = ans._split_sections(_LABELLED)
    check("section split: textbook / supplement / revision", _lab and "Mansabs" in _tb and "soldiers" in _sup and "rank" in _rev, (_tb[:40], _sup[:40], _rev))
    check("supplement never keeps a page reference", "page 12" not in ans._clean_supplement(_sup))
    _calls.clear()
    _replies[:] = [_LABELLED]
    _res = ans.answer_question("Explain the Mansabdari system.", "en", [], None)
    _body = _res["answer"].split("Source:")[0]
    check("answer carries both labels in order", _body.find("**From your textbook**") < _body.find("**Additional historical explanation**") and _body.find("**From your textbook**") >= 0, _body[:200])
    check("citations come only from the textbook part", "Source:" in _res["answer"] and "page 12" not in _res["answer"], _res["answer"][-160:])
    check("used_supplementary flag set", _res.get("used_supplementary") is True)
    # Unsupported sentence written under the textbook label is moved, not dropped or cited.
    _calls.clear()
    _replies[:] = ["**From your textbook**\nAkbar had established many hierarchies in his army called Mansabs. "
                   "The rank holders were later called the steel frame of the empire by modern historians writing in Britain."]
    _res = ans.answer_question("What was a mansab?", "en", [], None)
    _parts = _res["answer"].split("**Additional historical explanation**")
    check("unsupported textbook-labelled sentence is moved to the supplementary part",
          len(_parts) == 2 and "steel frame" in _parts[1] and "steel frame" not in _parts[0], _res["answer"][:300])
    # In-scope history the textbook does not cover: supplementary answer, no citation, no refusal.
    ans.topic_supported_by_primary = lambda q: False
    _calls.clear()
    _replies[:] = ["The Battle of Plassey was fought between the British East India Company and the Nawab of Bengal, Siraj-ud-Daulah. The Company won, and this helped it gain control of Bengal."]
    _res = ans.answer_question("What was the Battle of Plassey?", "en", [], None)
    check("non-textbook history is supplemented, not refused",
          NOT_IN_TEXTBOOK not in _res["answer"] and "**Additional historical explanation**" in _res["answer"] and len(_calls) == 1, _res["answer"][:200])
    check("supplement-only answer has no textbook citation", not _res.get("sources") and "Source:" not in _res["answer"] and "From your textbook" not in _res["answer"])
    check("supplement-only prompt says no passage matched", "none match this question" in _calls[0]["messages"][-1]["content"])
    ans.topic_supported_by_primary = lambda q: None
    _calls.clear()
    _res = ans.answer_question("Who is Elon Musk?", "en", [], None)
    check("off-topic question still refused before any model call", NOT_IN_TEXTBOOK in _res["answer"] and not _calls, _res["answer"][:120])
    _calls.clear()
    _res = ans.answer_question("Who won the IPL cricket final?", "en", [], None)
    check("cricket still refused before any model call", not _calls and NOT_IN_TEXTBOOK in _res["answer"], _res["answer"][:120])
    _calls.clear()
    _res = ans.answer_question("What is the GDP of India?", "en", [], None)
    check("GDP / current economic data refused before any model call", not _calls and NOT_IN_TEXTBOOK in _res["answer"], _res["answer"][:120])
    _calls.clear()
    _res = ans.answer_question("What is the inflation rate in India now?", "en", [], None)
    check("inflation rate refused before any model call", not _calls and NOT_IN_TEXTBOOK in _res["answer"], _res["answer"][:120])
    check("headings are title-cased", ans._title_case_headings("## how it worked\n## why it was important\n## Akbar's rule\ntext ## keep")
          == "## How It Worked\n## Why It Was Important\n## Akbar's Rule\ntext ## keep")
    _composed = ans._compose_sections("Intro.", "## background and key dates\nText.", "")
    check("composed answer has title-case headings", "## Background and Key Dates" in _composed, _composed[:120])
    from rag.prompts.tutor import FINAL_ANSWER_PROMPT as _FAP
    check("prompt: person answers use the structured outline", "Who was X?" in _FAP and "Achievements and Importance" in _FAP and "Title Case" in _FAP)
    check("prompt: 'briefly' stays short", "Briefly" in _FAP and "2 to 5 sentences with no headings" in _FAP)
    check("history vocabulary passes the domain gate", not ans._current_question_outside_domain("What was the Battle of Plassey?")
          and not ans._current_question_outside_domain("Explain the Kalinga war of Ashoka"))
    check("named non-textbook topic is detected (no textbook citation)",
          ans._names_term_outside_textbook("What did Emperor Ashoka do after the Kalinga war?")
          and ans._names_term_outside_textbook("What was the Quit India Movement?"))
    check("textbook terms and typos are not treated as outside",
          not ans._names_term_outside_textbook("What is the Mansabdari system?")
          and not ans._names_term_outside_textbook("who was akbr")
          and not ans._names_term_outside_textbook("Explain this in simpler words please"))
    # Continuation follow-ups use the previous answer and add new information.
    for _q in ("Give an example", "What happened next?", "What was the role of nobles?"):
        _calls.clear()
        _replies[:] = ["**From your textbook**\nThe appointment of mansabdars, giving jagirs and framing laws were the duties of the king.\n\n**Additional historical explanation**\nFor example, a noble with a rank of 5000 commanded a large cavalry force."]
        _res = ans.answer_question(_q, "en", _HIST, None)
        _prompt = _calls[0]["messages"][-1]["content"] if _calls else ""
        check(f"follow-up '{_q}' is answered with the earlier answer as context",
              len(_calls) >= 1 and NOT_IN_TEXTBOOK not in _res["answer"] and "Your previous answer" in _prompt and "dagh-mahali" in _prompt,
              (_res.get("validation_reason"), _res["answer"][:100]))
    # The repetition guard never shortens a long, useful answer.
    _facts = [
        "Point one: every officer received a numbered rank from the emperor.", "Point two: the rank decided his salary and status at court.",
        "Point three: many officers were paid through the income of assigned lands.", "Point four: these lands were moved often so nobody grew too strong.",
        "Point five: horses were branded so that officers could not cheat at inspections.", "Point six: Rajput chiefs also joined and served as officers.",
        "Point seven: promotion depended on loyalty and good service in battles.", "Point eight: the system tied distant provinces to the capital.",
        "Point nine: later rulers struggled when the land income became too small.", "Point ten: that shortage weakened the army in the eighteenth century.",
        "Point eleven: historians see it as a clever way to control powerful nobles.", "Point twelve: students should remember rank, salary, horses and loyalty.",
    ]
    _long = _NEW_ANSWER + "\n\n**Additional historical explanation**\n" + "\n".join(f"- {f}" for f in _facts)
    _calls.clear()
    _replies[:] = [_long]
    _res = ans.answer_question("Explain the Mansabdari system in detail", "en", [], None)
    check("long answers are not cut by the repetition guard", _res["answer"].count("Point ") >= 12, _res["answer"].count("Point "))
finally:
    ans.complete, ans.retrieve_primary, ans.topic_supported_by_primary = _saved

passed = sum(results)
print(f"final_unit_tests {passed}/{len(results)} PASS")
raise SystemExit(0 if passed == len(results) else 1)

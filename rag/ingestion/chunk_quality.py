"""Mark unreliable supplementary chunks. Does not invent missing PDF text."""

from __future__ import annotations

import re

# Empty slots left by CID-font extraction (the missing word itself is gone).
_MISSING_SLOT = re.compile(
    r"\b(as|called|the|a|an|of|had)\s+[.]|\benrolled as\s+[.]|\bknown as\s+[.]|"
    r"\bthe higher the\s+,|\bholds a\s+,|\bwho holds a\s+,",
    re.I,
)
_CROP = re.compile(r"\bwas an the\b|\bR uling\b|\beffectively in the Who\b|\bIn 1526 he and Agra\b", re.I)
_TRUNC_START = re.compile(
    r"^(were the successors|ries,|f the total|quare seal|h century|to increase productivity)\b",
    re.I,
)
_BLANK_EXERCISE = re.compile(r"_{5,}|\(b\) If determined a rank", re.I)


def assess_chunk(chunk: dict) -> dict:
    text = (chunk.get("text") or "").strip()
    source_type = chunk.get("source_type") or ""
    if source_type != "supplementary_mughal":
        return {"excluded": False, "reason": "ok"}
    reasons = []
    if _CROP.search(text):
        reasons.append("cropped_or_missing_words")
    if _MISSING_SLOT.search(text):
        reasons.append("cid_missing_terms")
    if _TRUNC_START.search(text):
        reasons.append("truncated_start")
    if _BLANK_EXERCISE.search(text):
        reasons.append("exercise_blanks_unclear")
    if re.search(r"\bof were only\b|\bpeasantry and in this economic world\b", text, re.I):
        reasons.append("broken_sentence")
    if text.lower().startswith("of many social and cultural units"):
        reasons.append("truncated_exercise_page")
    if re.search(r"It deals with$", text.strip()):
        reasons.append("truncated_end")
    if len(text) < 200:
        reasons.append("too_short")
    if reasons:
        return {"excluded": True, "reason": ",".join(reasons)}
    return {"excluded": False, "reason": "ok"}


def is_retrieval_excluded(chunk: dict) -> bool:
    meta_flag = chunk.get("retrieval_excluded")
    if meta_flag in (True, "true", "True", 1, "1"):
        return True
    return bool(assess_chunk(chunk)["excluded"])

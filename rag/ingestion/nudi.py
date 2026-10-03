"""Nudi → Unicode Kannada conversion interface.

This module does not invent a glyph mapping. It only uses an already-installed
converter if one exists, then validates that output is real Kannada Unicode.
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess

from rag.engine.normalize import looks_kannada

# Typical Nudi ASCII leftovers that must not appear in converted RAG text.
_NUDI_LEFTOVER = re.compile(r"[À-ÿ].*[À-ÿ]")


def converter_status() -> dict:
    module_name = os.environ.get("NUDI_PYTHON_MODULE", "").strip()
    command = os.environ.get("NUDI_CONVERTER_CMD", "").strip()
    discovered = []
    for name in ("nudi2unicode", "nudi_unicode", "baraha", "kn_nudi"):
        try:
            importlib.import_module(name)
            discovered.append(name)
        except Exception:
            continue
    return {
        "available": bool(module_name or command or discovered),
        "env_module": module_name or None,
        "env_command": command or None,
        "discovered_modules": discovered,
        "note": (
            "No verified Nudi converter is installed in this environment. "
            "Kannada primary ingestion is pending. The original PDF is unchanged."
            if not (module_name or command or discovered)
            else "A converter setting or module was found and will be validated before ingest."
        ),
    }


def looks_like_raw_nudi(text: str) -> bool:
    if looks_kannada(text):
        return False
    return bool(_NUDI_LEFTOVER.search(text or ""))


def convert_nudi_to_unicode(text: str) -> str:
    """Convert Nudi ASCII to Unicode Kannada if a verified converter is configured."""
    status = converter_status()
    if not status["available"]:
        raise RuntimeError(status["note"])
    converted = _run_converter(text, status)
    if not looks_kannada(converted) or looks_like_raw_nudi(converted):
        raise RuntimeError(
            "Nudi conversion output is not valid Unicode Kannada and will not be ingested."
        )
    if "ಕನ್ನಡ" not in converted and not re.search(r"[\u0C80-\u0CFF]{3,}", converted):
        raise RuntimeError("Nudi conversion did not produce Kannada script.")
    return converted


def _run_converter(text: str, status: dict) -> str:
    module_name = status.get("env_module") or (status.get("discovered_modules") or [None])[0]
    if module_name:
        module = importlib.import_module(module_name)
        for attr in ("convert", "nudi_to_unicode", "to_unicode"):
            fn = getattr(module, attr, None)
            if callable(fn):
                return str(fn(text))
        raise RuntimeError(f"Module {module_name} has no convert/nudi_to_unicode/to_unicode function.")
    command = status.get("env_command")
    if command:
        completed = subprocess.run(
            command,
            input=text,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
            shell=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Nudi converter command failed: {completed.stderr[:200]}")
        return completed.stdout
    raise RuntimeError("No Nudi converter could be executed.")

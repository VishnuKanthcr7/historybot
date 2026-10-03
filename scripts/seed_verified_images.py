"""Deprecated wrapper. Prefer: node backend/scripts/seed-verified-images.mjs"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    script = ROOT / "backend" / "scripts" / "seed-verified-images.mjs"
    return subprocess.call(["node", str(script)], cwd=str(ROOT / "backend"))


if __name__ == "__main__":
    raise SystemExit(main())

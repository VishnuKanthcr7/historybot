"""Apply Phase 11B quality flags to historybot_class9_ss_v2 only."""

from __future__ import annotations

import json

from rag.vectorstore.phase11b_patch import patch_v2_quality


def main() -> None:
    result = patch_v2_quality()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

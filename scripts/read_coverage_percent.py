from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(round(float(payload["totals"]["percent_covered"]), 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

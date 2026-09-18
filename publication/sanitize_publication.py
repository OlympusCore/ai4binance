"""Compatibility entry point for the local-only public showcase sanitizer."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        Path(__file__).resolve().parents[1] / "scripts" / "sanitize_publication.py",
        run_name="__main__",
    )

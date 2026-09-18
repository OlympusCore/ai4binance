"""Infrastructure helpers for opportunity artifact loading."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast


def load_optional_json_mapping(path: Path) -> Mapping[str, object] | None:
    """Return a decoded JSON mapping or None when the artifact is unavailable."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    return cast(Mapping[str, object], payload)


__all__ = ("load_optional_json_mapping",)

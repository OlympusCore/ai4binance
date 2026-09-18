"""Deterministic EIEF identifiers."""

from __future__ import annotations

from ai4binance.external_intel.core.validation import hash_material


def eief_id(prefix: str, *parts: str, length: int = 24) -> str:
    if not prefix.strip().isalnum():
        raise ValueError("EIEF id prefix must be alphanumeric")
    if not parts or any(not part.strip() for part in parts):
        raise ValueError("EIEF id material is required")
    digest = hash_material(prefix, *parts)[:length]
    return f"{prefix.lower()}_{digest}"

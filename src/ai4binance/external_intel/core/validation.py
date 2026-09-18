"""Small validation helpers for EIEF immutable contracts."""

from __future__ import annotations

import re
from datetime import datetime
from hashlib import sha256

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def require_text(name: str, value: str, *, maximum: int = 2_000) -> None:
    if not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty and bounded")


def require_optional_text(
    name: str, value: str | None, *, maximum: int = 2_000
) -> None:
    if value is not None and len(value) > maximum:
        raise ValueError(f"{name} must be bounded")


def require_unique_text(
    name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool = True,
    maximum_items: int = 100,
    maximum_text: int = 2_000,
) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{name} cannot be empty")
    if len(values) > maximum_items or len(set(values)) != len(values):
        raise ValueError(f"{name} must be bounded and unique")
    if any(not value.strip() or len(value) > maximum_text for value in values):
        raise ValueError(f"{name} contains invalid text")


def require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def require_unit_interval(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within zero and one")


def require_sha256(name: str, value: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def hash_material(*parts: str) -> str:
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()

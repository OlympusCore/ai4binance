"""Exact promotion subject contract and canonical identity validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CODE_REVISION_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class ExactPromotionIdentity(Protocol):
    """Read-only dependency contract for readiness orchestration."""

    @property
    def symbol(self) -> str: ...

    @property
    def market_type(self) -> str | None: ...

    @property
    def code_revision(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class PromotionEvidenceQuery:
    """Exact strategy and evidence identity required for promotion resolution."""

    strategy_id: str
    strategy_version: str
    strategy_sha256: str
    symbol: str
    market_type: str
    timeframe: str
    parameter_set_sha256: str
    dataset_sha256: str
    code_revision: str
    as_of: datetime

    def __post_init__(self) -> None:
        _normalize_exact_identity(self)
        _require_aware(self.as_of, "promotion query as_of")

    @property
    def subject_key(self) -> tuple[str, ...]:
        return (
            self.strategy_id,
            self.strategy_version,
            self.strategy_sha256,
            self.symbol,
            self.market_type,
            self.timeframe,
            self.parameter_set_sha256,
            self.dataset_sha256,
            self.code_revision,
        )


def _normalize_exact_identity(
    value: ExactPromotionIdentity,
) -> None:
    text_fields = ("strategy_id", "strategy_version", "timeframe")
    for field_name in text_fields:
        raw_value = getattr(value, field_name)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"promotion {field_name} is required")
        object.__setattr__(value, field_name, raw_value.strip())
    symbol = value.symbol.strip().upper()
    if not symbol.isascii() or not symbol.isalnum():
        raise ValueError("promotion symbol identity is invalid")
    object.__setattr__(value, "symbol", symbol)
    market_type = value.market_type
    if not isinstance(market_type, str):
        raise ValueError("promotion market type is required")
    normalized_market = market_type.strip().upper()
    if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
        raise ValueError("promotion market type is invalid")
    object.__setattr__(value, "market_type", normalized_market)
    for field_name in (
        "strategy_sha256",
        "parameter_set_sha256",
        "dataset_sha256",
    ):
        raw_value = getattr(value, field_name)
        if not isinstance(raw_value, str) or not _SHA256_PATTERN.fullmatch(raw_value):
            raise ValueError(f"promotion {field_name} is invalid")
    code_revision = value.code_revision
    if not isinstance(code_revision, str) or not _CODE_REVISION_PATTERN.fullmatch(
        code_revision
    ):
        raise ValueError("promotion code revision is invalid")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")

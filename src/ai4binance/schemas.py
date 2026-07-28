"""Immutable shared snapshot, specialist-agent and analysis-state schemas."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import ClassVar, cast

from ai4binance.domain import Signal, TradeCandidate


class AgentStatus(StrEnum):
    """Standard specialist-agent completion states."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


USABLE_AGENT_STATUSES = frozenset({AgentStatus.SUCCESS, AgentStatus.PARTIAL})


def is_usable_agent_result(result: "AgentResult") -> bool:
    """Return whether an agent result may contribute non-authoritative evidence."""
    return result.applicable and result.status in USABLE_AGENT_STATUSES


class DataQuality(StrEnum):
    """Shared market-data quality states."""

    DATA_VALID = "DATA_VALID"
    DATA_DEGRADED = "DATA_DEGRADED"
    DATA_INVALID = "DATA_INVALID"


class PromotionStatus(StrEnum):
    """Governed lifecycle states for analysis methods and strategies."""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    EXPERIMENTAL = "EXPERIMENTAL"
    STAGED_CANDIDATE = "STAGED_CANDIDATE"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    REJECTED = "REJECTED"


class OOSValidationStatus(StrEnum):
    """Out-of-sample evidence state used for hard-gate governance."""

    UNVALIDATED = "UNVALIDATED"
    INSUFFICIENT = "INSUFFICIENT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _freeze_value(value: object) -> object:
    """Recursively freeze common container values for a decision cycle."""
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        frozen = {str(key): _freeze_value(item) for key, item in mapping.items()}
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Return a recursively immutable defensive copy of a mapping."""
    return cast(Mapping[str, object], _freeze_value(value))


def _require_aware_timestamp(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OHLCVCandle:
    """Immutable market candle with basic integrity checks."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        """Reject impossible OHLC relationships and negative values."""
        _require_aware_timestamp("timestamp", self.timestamp)
        if min(self.open, self.high, self.low, self.close, self.volume) < Decimal("0"):
            raise ValueError("OHLCV values cannot be negative")
        if self.low > self.high:
            raise ValueError("candle low cannot exceed high")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("invalid OHLC relationship")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Deeply immutable shared market snapshot used by every agent in a cycle."""

    snapshot_id: str
    created_at: datetime
    exchange: str
    market_type: str
    symbol: str
    timeframes: tuple[str, ...]
    ohlcv_by_timeframe: Mapping[str, Sequence[OHLCVCandle]]
    latest_price: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    spread: Decimal | None
    order_book_summary: Mapping[str, object] = field(default_factory=dict)
    exchange_filters: Mapping[str, object] = field(default_factory=dict)
    server_time: datetime | None = None
    data_freshness: Mapping[str, object] = field(default_factory=dict)
    data_quality: DataQuality = DataQuality.DATA_INVALID
    wallet_summary: Mapping[str, object] = field(default_factory=dict)
    inventory_summary: Mapping[str, object] = field(default_factory=dict)
    open_orders: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    market_metadata: Mapping[str, object] = field(default_factory=dict)
    news_snapshot: Mapping[str, object] = field(default_factory=dict)
    sentiment_snapshot: Mapping[str, object] = field(default_factory=dict)
    derivatives_snapshot: Mapping[str, object] = field(default_factory=dict)
    onchain_snapshot: Mapping[str, object] = field(default_factory=dict)

    _MAPPING_FIELDS: ClassVar[tuple[str, ...]] = (
        "ohlcv_by_timeframe",
        "order_book_summary",
        "exchange_filters",
        "data_freshness",
        "wallet_summary",
        "inventory_summary",
        "market_metadata",
        "news_snapshot",
        "sentiment_snapshot",
        "derivatives_snapshot",
        "onchain_snapshot",
    )

    def __post_init__(self) -> None:
        """Normalize identity and defensively freeze nested snapshot values."""
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id cannot be empty")
        _require_aware_timestamp("created_at", self.created_at)
        if self.server_time is not None:
            _require_aware_timestamp("server_time", self.server_time)
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be empty")
        object.__setattr__(self, "symbol", normalized_symbol)
        if not self.timeframes or any(not item.strip() for item in self.timeframes):
            raise ValueError("timeframes must contain non-empty values")
        for field_name in ("latest_price", "bid", "ask", "spread"):
            value = getattr(self, field_name)
            if value is not None and value < Decimal("0"):
                raise ValueError(f"{field_name} cannot be negative")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        for field_name in self._MAPPING_FIELDS:
            frozen_value = _freeze_mapping(getattr(self, field_name))
            object.__setattr__(self, field_name, frozen_value)
        frozen_orders = tuple(_freeze_mapping(order) for order in self.open_orders)
        object.__setattr__(self, "open_orders", frozen_orders)


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Standardized specialist output with no order-execution authority."""

    agent_name: str
    agent_version: str
    snapshot_id: str
    timestamp: datetime
    symbol: str
    timeframes: tuple[str, ...]
    status: AgentStatus
    data_quality: DataQuality
    applicable: bool
    directional_vote: float
    score: float
    confidence: float
    evidence: tuple[str, ...] = field(default_factory=tuple)
    counter_evidence: tuple[str, ...] = field(default_factory=tuple)
    invalidation: str | None = None
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    detected_setups: tuple[str, ...] = field(default_factory=tuple)
    regime_compatibility: str = "UNKNOWN"
    false_positive_risk: tuple[str, ...] = field(default_factory=tuple)
    hard_gate_eligible: bool = False
    oos_validation_status: OOSValidationStatus = OOSValidationStatus.UNVALIDATED
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH_ONLY
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    calculation_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate ranges and freeze calculation metadata."""
        for field_name in ("agent_name", "agent_version", "snapshot_id", "symbol"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        normalized_symbol = self.symbol.strip().upper()
        _require_aware_timestamp("timestamp", self.timestamp)
        if not self.timeframes:
            raise ValueError("timeframes cannot be empty")
        if not self.reason_codes or any(not item.strip() for item in self.reason_codes):
            raise ValueError("reason_codes must contain deterministic values")
        valid_vote = isfinite(self.directional_vote) and (
            -1.0 <= self.directional_vote <= 1.0
        )
        if not valid_vote:
            raise ValueError("directional_vote must be finite and between -1 and 1")
        if not isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise ValueError("score must be finite and between 0 and 100")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")
        if self.hard_gate_eligible and self.promotion_status not in {
            PromotionStatus.PAPER_APPROVED,
            PromotionStatus.LIVE_ELIGIBLE,
        }:
            raise ValueError("unvalidated agents cannot be hard-gate eligible")
        if (
            self.hard_gate_eligible
            and self.oos_validation_status is not OOSValidationStatus.APPROVED
        ):
            raise ValueError("hard-gate eligibility requires approved OOS evidence")
        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(
            self,
            "calculation_metadata",
            _freeze_mapping(self.calculation_metadata),
        )


@dataclass(frozen=True, slots=True)
class AnalysisState:
    """Snapshot-consistent immutable state passed through the orchestrator."""

    snapshot_id: str
    symbol: str
    timestamp: datetime
    market_snapshot: MarketSnapshot
    agent_results: Mapping[str, AgentResult] = field(default_factory=dict)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    candidate_setups: tuple[TradeCandidate, ...] = field(default_factory=tuple)
    final_decision: Signal | None = None

    def __post_init__(self) -> None:
        """Block mixed-snapshot or mixed-symbol analysis state."""
        _require_aware_timestamp("timestamp", self.timestamp)
        normalized_symbol = self.symbol.strip().upper()
        if self.snapshot_id != self.market_snapshot.snapshot_id:
            raise ValueError("analysis state and market snapshot IDs must match")
        if normalized_symbol != self.market_snapshot.symbol:
            raise ValueError("analysis state and market snapshot symbols must match")
        for result in self.agent_results.values():
            if result.snapshot_id != self.snapshot_id:
                raise ValueError(
                    "every agent result must reference the shared snapshot"
                )
            if result.symbol.strip().upper() != normalized_symbol:
                raise ValueError("every agent result must reference the shared symbol")
        for candidate in self.candidate_setups:
            if candidate.snapshot_id != self.snapshot_id:
                raise ValueError("every candidate must reference the shared snapshot")
            if candidate.symbol != normalized_symbol:
                raise ValueError("every candidate must reference the shared symbol")
        if self.final_decision is not None:
            if self.final_decision.snapshot_id != self.snapshot_id:
                raise ValueError("final decision must reference the shared snapshot")
            if self.final_decision.symbol != normalized_symbol:
                raise ValueError("final decision must reference the shared symbol")
        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "agent_results", _freeze_mapping(self.agent_results))

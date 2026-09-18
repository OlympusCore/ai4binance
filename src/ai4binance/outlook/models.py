"""Immutable contracts for the research-only Market Outlook engine."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from ai4binance.domain import PriceZone, SetupTier


class BiasDirection(StrEnum):
    """Directional context without order authority."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class OutlookStatus(StrEnum):
    """Completeness state for one synthesized outlook."""

    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class KeyLevelKind(StrEnum):
    """Supported structural level types."""

    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"


@dataclass(frozen=True, slots=True)
class TimeframeBias:
    """One deterministic timeframe bias derived from existing agent evidence."""

    timeframe: str
    direction: BiasDirection
    score: float
    confidence: float
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("bias timeframe cannot be empty")
        if not isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise ValueError("bias score must be finite and between 0 and 100")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("bias confidence must be finite and between 0 and 1")
        if not self.reason_codes:
            raise ValueError("bias reason_codes cannot be empty")


@dataclass(frozen=True, slots=True)
class SetupRadarItem:
    """Research setup visible on the radar without execution permission."""

    setup_name: str
    timeframe: str
    direction: BiasDirection
    setup_tier: SetupTier
    score: float
    confidence: float
    status: str
    promotion_status: str
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in ("setup_name", "timeframe", "status", "promotion_status"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if not isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise ValueError("setup score must be finite and between 0 and 100")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("setup confidence must be finite and between 0 and 1")


@dataclass(frozen=True, slots=True)
class HighImpactEvent:
    """Sourced high-impact event supplied by the immutable snapshot."""

    event_id: str
    title: str
    scheduled_at: datetime
    impact: str
    source: str

    def __post_init__(self) -> None:
        for field_name in ("event_id", "title", "impact", "source"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None:
            raise ValueError("high-impact event timestamp must be timezone-aware")
        if self.impact not in {"HIGH", "CRITICAL"}:
            raise ValueError("outlook events must be HIGH or CRITICAL impact")


@dataclass(frozen=True, slots=True)
class KeyLevel:
    """ATR-buffered structural zone instead of false point precision."""

    timeframe: str
    kind: KeyLevelKind
    zone: PriceZone
    source: str = "ROLLING_SUPPORT_RESISTANCE"

    def __post_init__(self) -> None:
        if not self.timeframe.strip() or not self.source.strip():
            raise ValueError("key level timeframe and source cannot be empty")


@dataclass(frozen=True, slots=True)
class TpoCompositeContext:
    """Secondary auction-context proxy with explicit implementation limits."""

    status: str
    source_timeframe: str | None = None
    point_of_control_proxy: Decimal | None = None
    evidence: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.status.strip():
            raise ValueError("TPO/composite status cannot be empty")
        if self.point_of_control_proxy is not None and self.point_of_control_proxy < 0:
            raise ValueError("point-of-control proxy cannot be negative")
        if self.status != "AVAILABLE" and not self.blockers:
            raise ValueError("limited TPO/composite context requires blockers")


@dataclass(frozen=True, slots=True)
class MarketOutlook:
    """Complete research outlook with no signal or order authority."""

    snapshot_id: str
    symbol: str
    timestamp: datetime
    status: OutlookStatus
    timeframe_biases: tuple[TimeframeBias, ...]
    market_regime: str
    pro_trend_direction: BiasDirection
    timeframe_conflict: bool
    macro_cycle_view: str
    volatility_state: str
    setups_on_radar: tuple[SetupRadarItem, ...]
    high_impact_data: tuple[HighImpactEvent, ...]
    key_levels: tuple[KeyLevel, ...]
    tpo_composites: TpoCompositeContext
    no_trade_rationale: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.symbol.strip():
            raise ValueError("outlook identity cannot be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("outlook timestamp must be timezone-aware")
        if not self.market_regime.strip() or not self.macro_cycle_view.strip():
            raise ValueError("outlook context fields cannot be empty")
        if not self.volatility_state.strip() or not self.no_trade_rationale.strip():
            raise ValueError("outlook risk fields cannot be empty")
        if self.execution_allowed:
            raise ValueError("Market Outlook cannot grant execution authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("Market Outlook must remain live blocked")
        if self.status is OutlookStatus.READY and self.blockers:
            raise ValueError("READY outlook cannot contain blockers")

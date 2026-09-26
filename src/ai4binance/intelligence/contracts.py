"""Immutable evidence contracts for deterministic Trading Intelligence."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

ZERO = Decimal("0")


class StructureState(StrEnum):
    """Hierarchical market-structure states without order authority."""

    BULLISH = "STRUCTURE_BULLISH"
    BEARISH = "STRUCTURE_BEARISH"
    RANGE = "STRUCTURE_RANGE"
    TRANSITION = "STRUCTURE_TRANSITION"
    UNCERTAIN = "STRUCTURE_UNCERTAIN"


class SwingKind(StrEnum):
    """Confirmed swing geometry kind."""

    HIGH = "HIGH"
    LOW = "LOW"


class ScenarioDirection(StrEnum):
    """Research direction that never implies execution permission."""

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class ScenarioType(StrEnum):
    """Bounded scenario families admitted to deterministic synthesis."""

    LONG_CONTINUATION = "LONG_CONTINUATION"
    LONG_REVERSAL = "LONG_REVERSAL"
    SHORT_CONTINUATION = "SHORT_CONTINUATION"
    SHORT_REVERSAL = "SHORT_REVERSAL"
    RANGE_MEAN_REVERSION = "RANGE_MEAN_REVERSION"
    BREAKOUT_PENDING = "BREAKOUT_PENDING"
    NO_VALID_SETUP = "NO_VALID_SETUP"


class ScenarioState(StrEnum):
    """Scenario lifecycle before risk and validation."""

    FORMING = "FORMING"
    CONFIRMED = "CONFIRMED"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"
    NO_VALID_SETUP = "NO_VALID_SETUP"


class CalibrationState(StrEnum):
    """Availability of subject-specific OOS probability calibration."""

    NOT_CALIBRATED = "PROBABILITY_NOT_CALIBRATED"
    CALIBRATED = "OOS_CALIBRATED"


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_nonblank(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blank values")


def _require_confidence(name: str, value: float) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and between zero and one")


@dataclass(frozen=True, slots=True)
class ConfirmedSwing:
    """A pivot visible only after its right-side confirmation bars close."""

    timeframe: str
    kind: SwingKind
    candle_index: int
    occurred_at: datetime
    available_at: datetime
    price: Decimal
    label: str
    atr_significance: Decimal

    def __post_init__(self) -> None:
        if not self.timeframe.strip() or not self.label.strip():
            raise ValueError("confirmed swing identity cannot be empty")
        if self.candle_index < 0:
            raise ValueError("confirmed swing index cannot be negative")
        _require_aware("confirmed swing occurred_at", self.occurred_at)
        _require_aware("confirmed swing available_at", self.available_at)
        if self.available_at < self.occurred_at:
            raise ValueError("confirmed swing cannot be available before occurrence")
        if self.price <= ZERO or self.atr_significance < ZERO:
            raise ValueError("confirmed swing price/significance is invalid")


@dataclass(frozen=True, slots=True)
class StructureEvent:
    """A deterministic BOS or CHoCH observation."""

    event_type: str
    direction: ScenarioDirection
    level: Decimal
    occurred_at: datetime
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.event_type.strip() or not self.evidence_ref.strip():
            raise ValueError("structure event identity cannot be empty")
        if self.level <= ZERO:
            raise ValueError("structure event level must be positive")
        _require_aware("structure event occurred_at", self.occurred_at)


@dataclass(frozen=True, slots=True)
class TimeframeStructureEvidence:
    """One timeframe's structure, invalidation, and provenance."""

    timeframe: str
    state: StructureState
    method: str
    range_low: Decimal
    range_high: Decimal
    invalidation_level: Decimal | None
    confidence: float
    swings: tuple[ConfirmedSwing, ...] = field(default_factory=tuple)
    events: tuple[StructureEvent, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.timeframe.strip() or not self.method.strip():
            raise ValueError("timeframe structure identity cannot be empty")
        if self.range_low <= ZERO or self.range_high < self.range_low:
            raise ValueError("timeframe structure range is invalid")
        if self.invalidation_level is not None and self.invalidation_level <= ZERO:
            raise ValueError("structure invalidation must be positive")
        _require_confidence("structure confidence", self.confidence)
        _require_nonblank("structure reason codes", self.reason_codes)
        _require_nonblank("structure warnings", self.warnings)


@dataclass(frozen=True, slots=True)
class StructuralLevelEvidence:
    """Shared structural zone consumed by downstream hypotheses."""

    level_id: str
    level_type: str
    price_low: Decimal
    price_high: Decimal
    source_timeframe: str
    touch_count: int
    break_count: int
    freshness: str
    role_flip: bool
    confidence: float
    evidence_ref: str
    rejection_strength: float = 0.0
    volume_context: str = "NOT_MEASURED"
    age_bars: int = 0

    def __post_init__(self) -> None:
        required = (
            self.level_id,
            self.level_type,
            self.source_timeframe,
            self.freshness,
            self.evidence_ref,
        )
        if any(not value.strip() for value in required):
            raise ValueError("structural level identity cannot be empty")
        if self.price_low <= ZERO or self.price_high < self.price_low:
            raise ValueError("structural level price zone is invalid")
        if self.touch_count < 0 or self.break_count < 0:
            raise ValueError("structural level counts cannot be negative")
        if self.age_bars < 0:
            raise ValueError("structural level age cannot be negative")
        _require_confidence("structural level confidence", self.confidence)
        _require_confidence(
            "structural level rejection strength",
            self.rejection_strength,
        )
        if not self.volume_context.strip():
            raise ValueError("structural level volume context cannot be empty")


@dataclass(frozen=True, slots=True)
class TrendGeometryEvidence:
    """Dynamic trend-zone evidence projected from the existing trend owner."""

    source_timeframe: str
    slope: Decimal
    channel_width: Decimal
    state: str
    touch_quality: str
    evidence_ref: str
    confidence: float
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        required = (
            self.source_timeframe,
            self.state,
            self.touch_quality,
            self.evidence_ref,
        )
        if any(not value.strip() for value in required):
            raise ValueError("trend geometry identity cannot be empty")
        if self.channel_width < ZERO:
            raise ValueError("trend channel width cannot be negative")
        _require_confidence("trend geometry confidence", self.confidence)
        _require_nonblank("trend geometry blockers", self.blockers)


@dataclass(frozen=True, slots=True)
class PatternHypothesisEvidence:
    """Normalized pattern evidence; a hypothesis is never an entry."""

    hypothesis_id: str
    family: str
    direction: ScenarioDirection
    lifecycle_state: str
    confidence: float
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...] = field(default_factory=tuple)
    invalidation: str | None = None
    primary_direction_signal: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        required = (self.hypothesis_id, self.family, self.lifecycle_state)
        if any(not value.strip() for value in required):
            raise ValueError("pattern hypothesis identity cannot be empty")
        _require_confidence("pattern hypothesis confidence", self.confidence)
        _require_nonblank("pattern evidence_for", self.evidence_for)
        _require_nonblank("pattern evidence_against", self.evidence_against)
        if self.primary_direction_signal or self.execution_allowed:
            raise ValueError("pattern hypotheses cannot own direction or execution")


@dataclass(frozen=True, slots=True)
class DerivativesContextEvidence:
    """Freshness-bound Futures context separate from OHLCV evidence."""

    status: str
    source_count: int
    as_of: datetime | None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.status.strip() or self.source_count < 0:
            raise ValueError("derivatives context identity is invalid")
        if self.as_of is not None:
            _require_aware("derivatives context as_of", self.as_of)
        _require_nonblank("derivatives evidence refs", self.evidence_refs)
        _require_nonblank("derivatives blockers", self.blockers)
        if self.execution_allowed:
            raise ValueError("derivatives context cannot authorize execution")


@dataclass(frozen=True, slots=True)
class ConfidenceComponent:
    """Named confidence component used by weakest-critical-layer reduction."""

    name: str
    value: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("confidence component name cannot be empty")
        _require_confidence("confidence component", self.value)


@dataclass(frozen=True, slots=True)
class ScenarioHypothesis:
    """Snapshot-bound scenario before candidate planning and risk."""

    scenario_id: str
    snapshot_id: str
    scenario_type: ScenarioType
    direction: ScenarioDirection
    state: ScenarioState
    structure_state: StructureState
    regime: str
    invalidation_level: Decimal | None
    confidence: float
    confidence_components: tuple[ConfidenceComponent, ...]
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    calibration_state: CalibrationState = CalibrationState.NOT_CALIBRATED
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.snapshot_id.strip():
            raise ValueError("scenario identity cannot be empty")
        if not self.regime.strip():
            raise ValueError("scenario regime cannot be empty")
        if self.invalidation_level is not None and self.invalidation_level <= ZERO:
            raise ValueError("scenario invalidation must be positive")
        _require_confidence("scenario confidence", self.confidence)
        if not self.confidence_components:
            raise ValueError("scenario confidence components cannot be empty")
        if self.confidence != min(
            component.value for component in self.confidence_components
        ):
            raise ValueError("scenario confidence must equal the weakest component")
        _require_nonblank("scenario evidence_for", self.evidence_for)
        _require_nonblank("scenario evidence_against", self.evidence_against)
        _require_nonblank("scenario blockers", self.blockers)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("scenario hypotheses must remain live blocked")


@dataclass(frozen=True, slots=True)
class TradingIntelligenceState:
    """One deterministic evidence chain shared by candidates, risk, and validation."""

    snapshot_id: str
    symbol: str
    timestamp: datetime
    structures: tuple[TimeframeStructureEvidence, ...]
    levels: tuple[StructuralLevelEvidence, ...]
    trend_geometry: tuple[TrendGeometryEvidence, ...]
    pattern_hypotheses: tuple[PatternHypothesisEvidence, ...]
    derivatives_context: DerivativesContextEvidence
    scenarios: tuple[ScenarioHypothesis, ...]
    selected_scenario_id: str | None
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.symbol.strip():
            raise ValueError("trading intelligence identity cannot be empty")
        _require_aware("trading intelligence timestamp", self.timestamp)
        _require_nonblank("trading intelligence blockers", self.blockers)
        _require_nonblank("trading intelligence warnings", self.warnings)
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("trading intelligence scenario IDs must be unique")
        if (
            self.selected_scenario_id is not None
            and self.selected_scenario_id not in scenario_ids
        ):
            raise ValueError("selected scenario must exist in the scenario set")
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("trading intelligence must remain research-only")

    @property
    def selected_scenario(self) -> ScenarioHypothesis | None:
        """Return the selected scenario without creating a second index."""
        return next(
            (
                item
                for item in self.scenarios
                if item.scenario_id == self.selected_scenario_id
            ),
            None,
        )

    @property
    def primary_confidence(self) -> float:
        """Return selected confidence or zero when selection is blocked."""
        selected = self.selected_scenario
        return selected.confidence if selected is not None else 0.0

    @property
    def runner_up_confidence(self) -> float:
        """Return the strongest non-selected scenario confidence."""
        return max(
            (
                item.confidence
                for item in self.scenarios
                if item.scenario_id != self.selected_scenario_id
            ),
            default=0.0,
        )

    @property
    def scenario_separation(self) -> float:
        """Expose confidence separation without hiding hard blockers."""
        return max(0.0, self.primary_confidence - self.runner_up_confidence)

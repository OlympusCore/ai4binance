"""Immutable evidence contracts for deterministic Trading Intelligence."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from ai4binance.intelligence.event_context import EventContextEvidence
from ai4binance.intelligence.method_lineage import MethodLineage

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


class PatternLifecycleState(StrEnum):
    """Normalized research lifecycle for every pattern family."""

    FORMING = "FORMING"
    POTENTIAL = "POTENTIAL"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    ALTERNATIVE_UNRESOLVED = "ALTERNATIVE_UNRESOLVED"


class TrendGeometryState(StrEnum):
    """Lifecycle of one deterministic dynamic trend zone."""

    VALID = "TRENDLINE_VALID"
    WEAKENING = "TRENDLINE_WEAKENING"
    BREAK = "TRENDLINE_BREAK"
    FALSE_BREAK = "TRENDLINE_FALSE_BREAK"
    RETEST = "TRENDLINE_RETEST"
    SIDEWAYS = "TRENDLINE_SIDEWAYS"


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
        if (
            not self.price.is_finite()
            or not self.atr_significance.is_finite()
            or self.price <= ZERO
            or self.atr_significance < ZERO
        ):
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
        if not self.level.is_finite() or self.level <= ZERO:
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
        if (
            not self.range_low.is_finite()
            or not self.range_high.is_finite()
            or self.range_low <= ZERO
            or self.range_high < self.range_low
        ):
            raise ValueError("timeframe structure range is invalid")
        if self.invalidation_level is not None and (
            not self.invalidation_level.is_finite() or self.invalidation_level <= ZERO
        ):
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
    anchor_points: tuple[tuple[datetime, Decimal], ...] = field(default_factory=tuple)
    intercept: Decimal = ZERO
    touch_count: int = 0
    atr_normalized_error: Decimal = ZERO
    age_bars: int = 0
    break_state: str = "UNBROKEN"
    retest_state: str = "NOT_RETESTED"
    compression_state: str = "NOT_MEASURED"
    acceleration_state: str = "NOT_MEASURED"
    blockers: tuple[str, ...] = field(default_factory=tuple)
    geometry_id: str = ""
    method: str = "ENDPOINT_CHANNEL_FALLBACK"
    atr_normalized_slope: Decimal = ZERO

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
        if self.touch_count < 0 or self.age_bars < 0:
            raise ValueError("trend geometry counts cannot be negative")
        if self.atr_normalized_error < ZERO:
            raise ValueError("trend geometry error cannot be negative")
        for timestamp, price in self.anchor_points:
            _require_aware("trend anchor timestamp", timestamp)
            if price <= ZERO:
                raise ValueError("trend anchor price must be positive")
        if any(
            not value.strip()
            for value in (
                self.break_state,
                self.retest_state,
                self.compression_state,
                self.acceleration_state,
            )
        ):
            raise ValueError("trend geometry lifecycle cannot be empty")
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
    source_timeframe: str = "UNKNOWN"
    geometry_quality: float = 0.0
    completion_quality: float = 0.0
    attributes: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    primary_direction_signal: bool = False
    execution_allowed: bool = False
    observation_id: str = ""
    method_lineage: MethodLineage | None = None

    def __post_init__(self) -> None:
        required = (self.hypothesis_id, self.family, self.lifecycle_state)
        if any(not value.strip() for value in required):
            raise ValueError("pattern hypothesis identity cannot be empty")
        _require_confidence("pattern hypothesis confidence", self.confidence)
        _require_confidence("pattern geometry quality", self.geometry_quality)
        _require_confidence("pattern completion quality", self.completion_quality)
        if not self.source_timeframe.strip():
            raise ValueError("pattern source timeframe cannot be empty")
        if any(not key.strip() or not value.strip() for key, value in self.attributes):
            raise ValueError("pattern attributes cannot contain blank values")
        _require_nonblank("pattern evidence_for", self.evidence_for)
        _require_nonblank("pattern evidence_against", self.evidence_against)
        if self.primary_direction_signal or self.execution_allowed:
            raise ValueError("pattern hypotheses cannot own direction or execution")
        if self.method_lineage is not None and not isinstance(
            self.method_lineage, MethodLineage
        ):
            raise ValueError("pattern method lineage must be typed")


@dataclass(frozen=True, slots=True)
class DerivativesContextEvidence:
    """Freshness-bound Futures context separate from OHLCV evidence."""

    status: str
    source_count: int
    as_of: datetime | None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    age_seconds: int | None = None
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    basis: Decimal | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    mark_index_divergence: Decimal | None = None
    taker_buy_sell_ratio: Decimal | None = None
    crowding_state: str = "UNKNOWN"
    confidence: float = 0.0
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.status.strip() or self.source_count < 0:
            raise ValueError("derivatives context identity is invalid")
        if self.as_of is not None:
            _require_aware("derivatives context as_of", self.as_of)
        if self.age_seconds is not None and self.age_seconds < 0:
            raise ValueError("derivatives context age cannot be negative")
        self._validate_metrics()
        _require_confidence("derivatives context confidence", self.confidence)
        if not self.crowding_state.strip():
            raise ValueError("derivatives crowding state cannot be empty")
        _require_nonblank("derivatives evidence refs", self.evidence_refs)
        _require_nonblank("derivatives blockers", self.blockers)
        if self.execution_allowed:
            raise ValueError("derivatives context cannot authorize execution")

    def _validate_metrics(self) -> None:
        """Reject non-finite or impossible typed derivatives metrics."""
        for field_name in (
            "funding_rate",
            "open_interest",
            "basis",
            "mark_price",
            "index_price",
            "mark_index_divergence",
            "taker_buy_sell_ratio",
        ):
            value = getattr(self, field_name)
            if value is not None and not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
        for field_name in (
            "open_interest",
            "mark_price",
            "index_price",
            "taker_buy_sell_ratio",
        ):
            value = getattr(self, field_name)
            if value is not None and value < ZERO:
                raise ValueError(f"{field_name} cannot be negative")
        if self.mark_index_divergence is not None and self.mark_index_divergence < ZERO:
            raise ValueError("mark/index divergence cannot be negative")


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
class DirectionalConsensusEvidence:
    """Dependency-filtered agreement, never a claim of measured independence."""

    supporting_refs: tuple[str, ...] = ()
    opposing_refs: tuple[str, ...] = ()
    neutral_refs: tuple[str, ...] = ()
    dependency_groups: tuple[tuple[str, ...], ...] = ()
    evidence_families: tuple[str, ...] = ()
    direction: ScenarioDirection = ScenarioDirection.NEUTRAL
    calibration_state: CalibrationState = CalibrationState.NOT_CALIBRATED
    independent_confirmation_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.direction, ScenarioDirection):
            raise ValueError("directional consensus requires a typed direction")
        if (
            self.calibration_state is not CalibrationState.NOT_CALIBRATED
            or isinstance(self.independent_confirmation_count, bool)
            or not isinstance(self.independent_confirmation_count, int)
            or self.independent_confirmation_count != 0
        ):
            raise ValueError(
                "directional agreement cannot claim unmeasured independence"
            )
        for refs in (self.supporting_refs, self.opposing_refs, self.neutral_refs):
            _require_nonblank("directional evidence", refs)
            if len(set(refs)) != len(refs):
                raise ValueError("directional evidence references must be unique")
        classifications = self.supporting_refs + self.opposing_refs + self.neutral_refs
        if len(set(classifications)) != len(classifications):
            raise ValueError("directional evidence classifications must be disjoint")
        members = tuple(ref for group in self.dependency_groups for ref in group)
        _require_nonblank("dependency group members", members)
        _require_nonblank("evidence families", self.evidence_families)
        if len(set(members)) != len(members) or any(
            not group for group in self.dependency_groups
        ):
            raise ValueError("dependency groups must be nonempty and disjoint")
        if not set(
            self.supporting_refs + self.opposing_refs + self.neutral_refs
        ) <= set(members):
            raise ValueError("directional evidence must retain its dependency group")
        if any(
            len(set(group) & set(self.supporting_refs)) > 1
            for group in self.dependency_groups
        ):
            raise ValueError("dependent evidence cannot add directional confirmations")


@dataclass(frozen=True, slots=True)
class EvidenceOverlap:
    """Exact observed intersection, with no invented tolerance or probability."""

    evidence_refs: tuple[str, ...]
    price_low: Decimal | None = None
    price_high: Decimal | None = None
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_nonblank("overlap evidence", self.evidence_refs)
        if len(set(self.evidence_refs)) < 2 or len(set(self.evidence_refs)) != len(
            self.evidence_refs
        ):
            raise ValueError("overlap requires distinct evidence references")
        if self.occurred_at is not None:
            _require_aware("overlap timestamp", self.occurred_at)
            if self.price_low is not None or self.price_high is not None:
                raise ValueError("time overlap cannot claim a price intersection")
        elif (
            self.price_low is None
            or self.price_high is None
            or not self.price_low.is_finite()
            or not self.price_high.is_finite()
            or not ZERO < self.price_low <= self.price_high
        ):
            raise ValueError("price overlap requires a finite positive intersection")


@dataclass(frozen=True, slots=True)
class ConfluenceEvidence:
    """Observable alignment separate from directional consensus and confidence."""

    available_refs: tuple[str, ...] = ()
    overlaps: tuple[EvidenceOverlap, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    independence_status: str = "NOT_MEASURED"

    def __post_init__(self) -> None:
        _require_nonblank("confluence evidence", self.available_refs)
        _require_nonblank("confluence counter evidence", self.counter_evidence)
        if len(set(self.available_refs)) != len(self.available_refs):
            raise ValueError("confluence evidence references must be unique")
        if self.independence_status != "NOT_MEASURED":
            raise ValueError(
                "geometric overlap cannot establish statistical independence"
            )
        if any(
            not set(row.evidence_refs) <= set(self.available_refs)
            for row in self.overlaps
        ):
            raise ValueError("overlap must reference available dimension evidence")

    @property
    def status(self) -> str:
        """Missing observations are not measured absence or confirmed confluence."""
        if not self.available_refs:
            return "DATA_UNAVAILABLE"
        if len(self.available_refs) < 2:
            return "INSUFFICIENT_EVIDENCE"
        return "OBSERVED_OVERLAP" if self.overlaps else "NO_OBSERVED_OVERLAP"


@dataclass(frozen=True, slots=True)
class MultiMethodEvidence:
    """Five explicit snapshot-bound dimensions without a combined authority score."""

    snapshot_id: str
    directional_consensus: DirectionalConsensusEvidence = field(
        default_factory=DirectionalConsensusEvidence
    )
    location_confluence: ConfluenceEvidence = field(default_factory=ConfluenceEvidence)
    timing_confluence: ConfluenceEvidence = field(default_factory=ConfluenceEvidence)
    invalidation_confluence: ConfluenceEvidence = field(
        default_factory=ConfluenceEvidence
    )
    target_confluence: ConfluenceEvidence = field(default_factory=ConfluenceEvidence)

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("multi-method evidence requires snapshot identity")
        if not isinstance(
            self.directional_consensus, DirectionalConsensusEvidence
        ) or any(
            not isinstance(row, ConfluenceEvidence)
            for row in (
                self.location_confluence,
                self.timing_confluence,
                self.invalidation_confluence,
                self.target_confluence,
            )
        ):
            raise ValueError(
                "multi-method dimensions must use typed evidence contracts"
            )


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
        if self.invalidation_level is not None and (
            not self.invalidation_level.is_finite() or self.invalidation_level <= ZERO
        ):
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
    estimated_round_trip_cost_ratio: Decimal | None = None
    cost_blockers: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    market_type: str = "SPOT"
    event_context: tuple[EventContextEvidence, ...] = ()
    method_diversity_count: int = 0
    dependency_group_count: int = 0
    evidence_conflicts: tuple[str, ...] = ()
    transaction_cost_ratio: Decimal | None = None
    funding_periods: int | None = None
    multi_method_evidence: MultiMethodEvidence | None = None

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.symbol.strip():
            raise ValueError("trading intelligence identity cannot be empty")
        _require_aware("trading intelligence timestamp", self.timestamp)
        if self.market_type not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError("trading intelligence market type is invalid")
        _require_nonblank("trading intelligence blockers", self.blockers)
        _require_nonblank("trading intelligence warnings", self.warnings)
        _require_nonblank("trading intelligence cost blockers", self.cost_blockers)
        if self.estimated_round_trip_cost_ratio is not None and (
            not self.estimated_round_trip_cost_ratio.is_finite()
            or self.estimated_round_trip_cost_ratio < ZERO
        ):
            raise ValueError("trading intelligence cost ratio is invalid")
        self._validate_evidence_binding()
        self._validate_context_contract()

    def _validate_context_contract(self) -> None:
        """Preserve context identity, cost horizons and veto authority."""
        if any(row.snapshot_id != self.snapshot_id for row in self.event_context):
            raise ValueError("event context must belong to the canonical snapshot")
        if any(
            code not in self.blockers
            for context in self.event_context
            for code in context.blockers
        ):
            raise ValueError("event context vetoes must propagate to shared state")
        if any(
            (row.symbol, row.market_type) != (self.symbol, self.market_type)
            or row.available_at > self.timestamp
            for context in self.event_context
            for row in context.observations
        ):
            raise ValueError(
                "event observations must match shared-state identity and time"
            )
        if self.method_diversity_count < 0 or self.dependency_group_count < 0:
            raise ValueError("evidence counts cannot be negative")
        if self.transaction_cost_ratio is not None and (
            not self.transaction_cost_ratio.is_finite()
            or self.transaction_cost_ratio < ZERO
        ):
            raise ValueError("transaction cost ratio must be finite and nonnegative")
        if self.funding_periods is not None and (
            isinstance(self.funding_periods, bool)
            or not isinstance(self.funding_periods, int)
            or self.funding_periods < 0
        ):
            raise ValueError("funding horizon must be a nonnegative period count")
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("trading intelligence must remain research-only")

    def _validate_evidence_binding(self) -> None:
        """Reject cross-cycle evidence and contradictory scenario selection."""
        if self.multi_method_evidence is not None:
            if self.multi_method_evidence.snapshot_id != self.snapshot_id:
                raise ValueError(
                    "multi-method evidence must match the canonical snapshot"
                )
            if any(
                row.occurred_at is not None and row.occurred_at > self.timestamp
                for row in self.multi_method_evidence.timing_confluence.overlaps
            ):
                raise ValueError("timing confluence cannot use future evidence")
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        if any(item.snapshot_id != self.snapshot_id for item in self.scenarios):
            raise ValueError("scenario snapshot identity must match shared state")
        if any(
            swing.available_at > self.timestamp
            for structure in self.structures
            for swing in structure.swings
        ) or any(
            event.occurred_at > self.timestamp
            for structure in self.structures
            for event in structure.events
        ):
            raise ValueError("structure evidence cannot be available after snapshot")
        if self.selected_scenario_id is not None and self.blockers:
            raise ValueError("blocked intelligence cannot select a scenario")
        if self.selected_scenario is not None and self.selected_scenario.state not in {
            ScenarioState.FORMING,
            ScenarioState.CONFIRMED,
        }:
            raise ValueError("selected scenario must be forming or confirmed")
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("trading intelligence scenario IDs must be unique")
        if (
            self.selected_scenario_id is not None
            and self.selected_scenario_id not in scenario_ids
        ):
            raise ValueError("selected scenario must exist in the scenario set")

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

"""Canonical opportunity radar snapshot builder.

The radar consumes immutable candle snapshots and produces research-only
opportunity evidence. It never grants paper, live, or order authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from ai4binance.domain import Action, SetupTier
from ai4binance.domain.opportunity_observation import (
    OpportunityBias,
    OpportunityLifecycleState,
    VWAPOpportunity,
    VWAPOpportunityConfig,
    estimate_measurable_trade_plan,
)
from ai4binance.indicators import atr, relative_volume, session_vwap
from ai4binance.opportunity_intelligence import (
    PRIMARY_OPPORTUNITY_TIMEFRAMES,
    TIMEFRAME_DURATIONS,
    CandlestickPattern,
    MultiTimeframeAlignmentState,
    MultiTimeframeDiagnostic,
    analyze_candlestick,
    build_multi_timeframe_diagnostic,
    detect_chart_pattern,
)
from ai4binance.opportunity_policy import classify_opportunity_grade
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.strategies.rules import setup_pattern_type

ZERO = Decimal("0")
REQUIRED_DEEP_SCAN_TIMEFRAMES = PRIMARY_OPPORTUNITY_TIMEFRAMES
PRIMARY_SETUP_TIMEFRAME = "15m"


class VWAPOpportunityEvaluator:
    """Observe reclaim/rejection candidates with explicit confirmation gates."""

    def __init__(self, config: VWAPOpportunityConfig | None = None) -> None:
        self._config = config or VWAPOpportunityConfig()

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        timeframe: str,
        session_start: datetime,
        structure_aligned: bool,
        htf_aligned: bool,
        inventory_available: bool = False,
    ) -> VWAPOpportunity:
        """Evaluate closed candles; fail closed when evidence is incomplete."""
        if session_start.tzinfo is None or session_start.utcoffset() is None:
            raise ValueError("session_start must be timezone-aware")
        candles = tuple(
            candle
            for candle in snapshot.ohlcv_by_timeframe.get(timeframe, ())
            if candle.timestamp >= session_start
        )
        minimum = max(self._config.atr_period + 1, self._config.volume_window + 1)
        if len(candles) < minimum:
            return self._blocked(
                snapshot, timeframe, session_start, "INSUFFICIENT_SESSION_DATA"
            )

        latest = candles[-1]
        previous = candles[-2]
        current_vwap = session_vwap(candles, session_start)
        previous_vwap = session_vwap(candles[:-1], session_start)
        current_atr = atr(candles, self._config.atr_period)
        current_rvol = relative_volume(candles, self._config.volume_window)
        atr_distance = (
            abs(latest.close - current_vwap) / current_atr
            if current_atr > ZERO
            else Decimal("Infinity")
        )
        bullish = previous.close <= previous_vwap and latest.close > current_vwap
        bearish = previous.close >= previous_vwap and latest.close < current_vwap
        bias = (
            OpportunityBias.BULLISH
            if bullish
            else OpportunityBias.BEARISH
            if bearish
            else OpportunityBias.NEUTRAL
        )
        crossings = self._crossing_count(candles, session_start)

        blockers: list[str] = []
        if snapshot.data_quality is not DataQuality.DATA_VALID:
            blockers.append("DATA_NOT_VALID")
        if bias is OpportunityBias.NEUTRAL:
            blockers.append("VWAP_TRIGGER_MISSING")
        if current_rvol < self._config.min_relative_volume:
            blockers.append("VOLUME_CONFIRMATION_MISSING")
        if atr_distance > self._config.max_atr_distance:
            blockers.append("VWAP_OVEREXTENDED")
        if crossings > self._config.max_crossings:
            blockers.append("VWAP_CHOP_DETECTED")
        if not structure_aligned:
            blockers.append("STRUCTURE_CONFIRMATION_REQUIRED")
        if not htf_aligned:
            blockers.append("HTF_CONFIRMATION_REQUIRED")
        if bias is OpportunityBias.BEARISH and not inventory_available:
            blockers.append("SPOT_INVENTORY_REQUIRED_FOR_SELL")

        evidence = (
            f"VWAP={current_vwap}",
            f"RELATIVE_VOLUME={current_rvol}",
            f"ATR_DISTANCE={atr_distance}",
            f"VWAP_CROSSINGS={crossings}",
        )
        action = Action.NO_TRADE
        tier = SetupTier.NO_TRADE
        if not blockers:
            action = Action.BUY if bullish else Action.SELL
            tier = SetupTier.B
        return VWAPOpportunity(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            observed_at=latest.timestamp,
            session_start=session_start,
            setup_name="session_vwap_reclaim" if bullish else "session_vwap_rejection",
            bias=bias,
            action=action,
            setup_tier=tier,
            price=latest.close,
            vwap=current_vwap,
            atr=current_atr,
            relative_volume=current_rvol,
            atr_distance=atr_distance,
            crossing_count=crossings,
            evidence=evidence,
            blockers=tuple(blockers),
            lifecycle_state=_vwap_lifecycle_state(tuple(blockers)),
        )

    def _crossing_count(
        self, candles: tuple[OHLCVCandle, ...], session_start: datetime
    ) -> int:
        start_index = max(1, len(candles) - self._config.crossing_lookback)
        sides: list[bool] = []
        for index in range(start_index, len(candles)):
            value = session_vwap(candles[: index + 1], session_start)
            sides.append(candles[index].close >= value)
        return sum(left != right for left, right in pairwise(sides))

    @staticmethod
    def _blocked(
        snapshot: MarketSnapshot,
        timeframe: str,
        session_start: datetime,
        blocker: str,
    ) -> VWAPOpportunity:
        return VWAPOpportunity(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            observed_at=snapshot.created_at,
            session_start=session_start,
            setup_name="session_vwap_observation",
            bias=OpportunityBias.NEUTRAL,
            action=Action.NO_TRADE,
            setup_tier=SetupTier.NO_TRADE,
            price=snapshot.latest_price,
            vwap=None,
            atr=None,
            relative_volume=None,
            atr_distance=None,
            crossing_count=0,
            blockers=(blocker,),
        )


@dataclass(frozen=True, slots=True)
class OpportunityRadarCandidate:
    """YKB-compatible research candidate derived from canonical candles."""

    opportunity_id: str
    symbol: str
    market: str
    timeframe: str
    setup_name: str
    direction: str
    status: str
    promotion_status: str
    score: Decimal
    grade: str
    confidence: Decimal
    target_risk_reward: Decimal
    observed_at: datetime
    source_snapshot_id: str
    supporting_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    confirmation_requirements: tuple[str, ...]
    promotion_requirements: tuple[str, ...]
    execution_blockers: tuple[str, ...]
    next_evidence_action: str
    why_now: tuple[str, ...] = field(default_factory=tuple)
    entry: str = "PENDING_VALIDATED_LEVEL"
    stop_loss: str = "PENDING_VALIDATED_LEVEL"
    tp1: str = "PENDING_VALIDATED_LEVEL"
    tp2: str = "PENDING_VALIDATED_LEVEL"
    tp3: str = "PENDING_VALIDATED_LEVEL"
    blockers: tuple[str, ...] = field(default_factory=tuple)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    pattern_type: str | None = None
    score_components: tuple[tuple[str, Decimal], ...] = field(default_factory=tuple)
    multi_timeframe_diagnostic: MultiTimeframeDiagnostic | None = None

    def __post_init__(self) -> None:
        for value in (
            self.opportunity_id,
            self.symbol,
            self.market,
            self.timeframe,
            self.setup_name,
            self.direction,
            self.status,
            self.promotion_status,
            self.grade,
            self.next_evidence_action,
            self.source_snapshot_id,
        ):
            if not value.strip():
                raise ValueError("opportunity radar candidate identity is required")
        if not Decimal("0") <= self.score <= Decimal("100"):
            raise ValueError("opportunity radar score must be 0..100")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("opportunity radar confidence must be 0..1")
        if self.target_risk_reward <= ZERO:
            raise ValueError("opportunity radar target risk/reward must be positive")
        for values in (
            self.supporting_evidence,
            self.counter_evidence,
            self.confirmation_requirements,
            self.promotion_requirements,
            self.execution_blockers,
            self.why_now,
            self.blockers,
        ):
            if len(set(values)) != len(values) or any(
                not item.strip() for item in values
            ):
                raise ValueError("opportunity radar evidence lists must be unique")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity radar candidate cannot authorize execution")
        if self.pattern_type is not None and not self.pattern_type.strip():
            raise ValueError("opportunity radar pattern_type cannot be blank")
        score_component_names = tuple(name for name, _value in self.score_components)
        if (
            len(set(score_component_names)) != len(score_component_names)
            or any(not name.strip() for name in score_component_names)
            or any(
                not ZERO <= value <= Decimal("100")
                for _, value in self.score_components
            )
        ):
            raise ValueError("opportunity radar score components are invalid")

    def to_inbox_item(self) -> dict[str, object]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "setup_name": self.setup_name,
            "pattern_type": self.pattern_type or setup_pattern_type(self.setup_name),
            "timeframe": self.timeframe,
            "direction": self.direction,
            "source": "opportunity_radar_snapshot",
            "status": self.status,
            "promotion_status": self.promotion_status,
            "score": float(self.score),
            "grade": self.grade,
            "confidence": float(self.confidence),
            "target_risk_reward": str(self.target_risk_reward),
            "blockers": self.blockers,
            "why_now": self.why_now,
            "supporting_evidence": self.supporting_evidence,
            "counter_evidence": self.counter_evidence,
            "confirmation_requirements": self.confirmation_requirements,
            "promotion_requirements": self.promotion_requirements,
            "execution_blockers": self.execution_blockers,
            "next_evidence_action": self.next_evidence_action,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
            "score_components": {
                name: str(value) for name, value in self.score_components
            },
            "multi_timeframe_diagnostic": (
                self.multi_timeframe_diagnostic.to_payload()
                if self.multi_timeframe_diagnostic is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class OpportunityRadarSnapshot:
    radar_id: str
    cycle_id: str
    observed_at: datetime
    source_snapshot_ids: tuple[str, ...]
    universe_version: str
    policy_version: str
    candidates: tuple[OpportunityRadarCandidate, ...]
    blockers: tuple[str, ...]
    status: str = "RUNNING_WITH_BLOCKERS"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.radar_id.strip() or not self.cycle_id.strip():
            raise ValueError("opportunity radar snapshot identity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("opportunity radar timestamp must be timezone-aware")
        if not self.source_snapshot_ids:
            raise ValueError("opportunity radar snapshot requires source snapshots")
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("opportunity radar status is invalid")
        if len(set(self.blockers)) != len(self.blockers) or any(
            not blocker.strip() for blocker in self.blockers
        ):
            raise ValueError("opportunity radar blockers must be unique")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity radar snapshot cannot authorize execution")

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def to_payload(self) -> dict[str, object]:
        return {
            "radar_id": self.radar_id,
            "cycle_id": self.cycle_id,
            "observed_at": self.observed_at.isoformat(),
            "source_snapshot_ids": self.source_snapshot_ids,
            "universe_version": self.universe_version,
            "policy_version": self.policy_version,
            "candidate_count": self.candidate_count,
            "candidate_states": tuple(
                candidate.to_inbox_item() for candidate in self.candidates
            ),
            "blockers": self.blockers,
            "status": self.status,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_opportunity_radar_snapshot(
    snapshots: Iterable[MarketSnapshot],
    *,
    cycle_id: str,
    observed_at: datetime | None = None,
    market: str = "SPOT",
    timeframe: str | None = None,
) -> OpportunityRadarSnapshot:
    """Build a deterministic radar snapshot from canonical candle snapshots."""
    source_snapshots = tuple(snapshots)
    if timeframe is not None and timeframe not in TIMEFRAME_DURATIONS:
        raise ValueError("opportunity radar timeframe is unsupported")
    if not source_snapshots:
        raise ValueError("opportunity radar requires at least one market snapshot")
    observed = observed_at or max(snapshot.created_at for snapshot in source_snapshots)
    candidates = tuple(
        _candidate_from_snapshot(
            snapshot,
            market=market,
            decision_time=observed,
            timeframe=timeframe or PRIMARY_SETUP_TIMEFRAME,
            explicit_timeframe=timeframe is not None,
        )
        for snapshot in source_snapshots
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *(
                    blocker
                    for candidate in candidates
                    for blocker in candidate.blockers
                ),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    return OpportunityRadarSnapshot(
        radar_id=f"opportunity-radar:{cycle_id}",
        cycle_id=cycle_id,
        observed_at=observed,
        source_snapshot_ids=tuple(
            snapshot.snapshot_id for snapshot in source_snapshots
        ),
        universe_version="canonical-market-snapshot:v1",
        policy_version="opportunity-radar-policy:v1",
        candidates=candidates,
        blockers=blockers,
        status="READY"
        if any(candidate.score > ZERO for candidate in candidates)
        else "RUNNING_WITH_BLOCKERS",
    )


def _candidate_from_snapshot(
    snapshot: MarketSnapshot,
    *,
    market: str,
    decision_time: datetime,
    timeframe: str = PRIMARY_SETUP_TIMEFRAME,
    explicit_timeframe: bool = False,
) -> OpportunityRadarCandidate:
    diagnostic = build_multi_timeframe_diagnostic(
        snapshot,
        decision_time=decision_time,
    )
    duration = TIMEFRAME_DURATIONS[timeframe]
    primary = tuple(
        candle
        for candle in snapshot.ohlcv_by_timeframe.get(timeframe, ())
        if candle.timestamp + duration <= decision_time
    )
    primary_blockers: tuple[str, ...] = ()
    if not primary:
        primary_blockers = (f"MISSING_CLOSED_TIMEFRAME:{timeframe}",)
    elif decision_time - (primary[-1].timestamp + duration) > duration * 2:
        primary_blockers = (f"STALE_TIMEFRAME:{timeframe}",)
    if any(a.timestamp >= b.timestamp for a, b in pairwise(primary)):
        primary_blockers += (f"TIMEFRAME_SEQUENCE_INVALID:{timeframe}",)
    canonical_blockers = tuple(
        dict.fromkeys(
            (
                *_canonical_snapshot_blockers(snapshot, diagnostic),
                *primary_blockers,
            )
        )
    )
    if canonical_blockers:
        return _blocked_candidate(
            snapshot,
            market=market,
            blockers=canonical_blockers,
            timeframe=timeframe if explicit_timeframe else "UNSPECIFIED",
        )
    closed = {
        reference.timeframe: tuple(
            candle
            for candle in snapshot.ohlcv_by_timeframe[reference.timeframe]
            if candle.timestamp <= reference.open_time
        )
        for reference in diagnostic.candle_references
    }
    structure_aligned = _trend_aligned(closed["1h"])
    htf_aligned = _trend_aligned(closed["4h"]) and diagnostic.alignment_status not in {
        MultiTimeframeAlignmentState.CONFLICTING,
        MultiTimeframeAlignmentState.INSUFFICIENT_DATA,
    }
    opportunity = VWAPOpportunityEvaluator().evaluate(
        replace(
            snapshot,
            ohlcv_by_timeframe={**snapshot.ohlcv_by_timeframe, timeframe: primary},
        ),
        timeframe=timeframe,
        session_start=primary[0].timestamp,
        structure_aligned=structure_aligned,
        htf_aligned=htf_aligned,
    )
    candlestick = analyze_candlestick(primary)
    pattern = detect_chart_pattern(
        primary,
        timeframe=timeframe,
        snapshot_id=snapshot.snapshot_id,
        decision_time=decision_time,
    )
    extension_blockers = (
        ("EXTENDED_CANDLE_WAIT_FOR_RETEST",)
        if CandlestickPattern.EXTENDED in candlestick.patterns
        else ()
    )
    confirmation = tuple(dict.fromkeys((*opportunity.blockers, *extension_blockers)))
    direction = _direction(opportunity)
    setup_detected = (
        opportunity.action in {Action.BUY, Action.SELL} and not confirmation
    )
    promotion = (
        "VALIDATION_GATE_REQUIRED",
        "OOS_NOT_COMPLETE",
        "PAPER_VALIDATION_PENDING",
    )
    execution = ("RISK_APPROVAL_MISSING", "LIVE_ORDER_BLOCKED")
    score = Decimal("72") if setup_detected else ZERO
    confidence = Decimal("0.64") if setup_detected else Decimal("0")
    trade_plan = _trade_plan(opportunity) if setup_detected else {}
    return OpportunityRadarCandidate(
        opportunity_id=(
            f"opportunity:{snapshot.snapshot_id}:"
            f"{timeframe + ':' if explicit_timeframe else ''}"
            f"{opportunity.setup_name}:{direction}"
        ),
        symbol=snapshot.symbol,
        market=market,
        timeframe=opportunity.timeframe,
        setup_name=opportunity.setup_name,
        direction=direction,
        status="WATCHLIST" if setup_detected else "CONFIRMATION_PENDING",
        promotion_status="RESEARCH_ONLY",
        score=score,
        grade=classify_opportunity_grade(score),
        confidence=confidence,
        target_risk_reward=Decimal("2"),
        observed_at=opportunity.observed_at,
        source_snapshot_id=snapshot.snapshot_id,
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    f"snapshot:{snapshot.snapshot_id}",
                    *opportunity.evidence,
                    "CANONICAL_TIMEFRAMES=15m,1h,4h",
                    f"MTF_ALIGNMENT={diagnostic.alignment_status.value}",
                    *candlestick.reason_codes,
                    *(
                        (f"CHART_PATTERN={pattern.pattern_type}:{pattern.state.value}",)
                        if pattern is not None
                        else ()
                    ),
                )
            )
        ),
        counter_evidence=tuple(dict.fromkeys((*confirmation, *promotion, *execution))),
        confirmation_requirements=confirmation,
        promotion_requirements=promotion,
        execution_blockers=execution,
        next_evidence_action=(
            "RUN_VALIDATION_QUEUE"
            if setup_detected
            else "WAIT_FOR_CONFIRMATION_AND_REFRESH_RADAR"
        ),
        why_now=(
            "VWAP_RECLAIM_REJECTION_DETECTED",
            "HTF_STRUCTURE_ALIGNED",
        )
        if setup_detected
        else (),
        entry=trade_plan.get("entry", "PENDING_VALIDATED_LEVEL"),
        stop_loss=trade_plan.get("stop_loss", "PENDING_VALIDATED_LEVEL"),
        tp1=trade_plan.get("tp1", "PENDING_VALIDATED_LEVEL"),
        tp2=trade_plan.get("tp2", "PENDING_VALIDATED_LEVEL"),
        tp3=trade_plan.get("tp3", "PENDING_VALIDATED_LEVEL"),
        blockers=tuple(dict.fromkeys((*confirmation, *promotion, *execution))),
        pattern_type=setup_pattern_type(opportunity.setup_name),
        score_components=(
            ("structure_quality", Decimal("70") if structure_aligned else ZERO),
            ("price_action_quality", Decimal("72") if setup_detected else ZERO),
            (
                "candlestick_quality",
                Decimal("65") if candlestick.patterns else Decimal("25"),
            ),
            (
                "chart_pattern_quality",
                Decimal("55") if pattern is not None else ZERO,
            ),
            (
                "multi_tf_alignment",
                Decimal("80")
                if diagnostic.alignment_status is MultiTimeframeAlignmentState.ALIGNED
                else Decimal("55"),
            ),
            (
                "volume_confirmation",
                min(Decimal("100"), opportunity.relative_volume * Decimal("50"))
                if opportunity.relative_volume is not None
                else ZERO,
            ),
        ),
        multi_timeframe_diagnostic=diagnostic,
    )


def _canonical_snapshot_blockers(
    snapshot: MarketSnapshot,
    diagnostic: MultiTimeframeDiagnostic,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if snapshot.data_quality is not DataQuality.DATA_VALID:
        blockers.append("CANONICAL_SNAPSHOT_DATA_NOT_VALID")
    missing = tuple(
        timeframe
        for timeframe in REQUIRED_DEEP_SCAN_TIMEFRAMES
        if not snapshot.ohlcv_by_timeframe.get(timeframe)
    )
    if missing:
        blockers.append("CANONICAL_MTF_SNAPSHOT_INCOMPLETE:" + ",".join(missing))
    blockers.extend(diagnostic.blockers)
    if snapshot.latest_price is None or snapshot.latest_price <= ZERO:
        blockers.append("CANONICAL_LATEST_PRICE_UNAVAILABLE")
    return tuple(blockers)


def _blocked_candidate(
    snapshot: MarketSnapshot,
    *,
    market: str,
    blockers: tuple[str, ...],
    timeframe: str = "UNSPECIFIED",
) -> OpportunityRadarCandidate:
    execution = ("LIVE_ORDER_BLOCKED",)
    return OpportunityRadarCandidate(
        opportunity_id=(
            f"opportunity:{snapshot.snapshot_id}:"
            f"{timeframe + ':' if timeframe != 'UNSPECIFIED' else ''}SETUP_UNAVAILABLE"
        ),
        symbol=snapshot.symbol,
        market=market,
        timeframe=timeframe,
        setup_name="SETUP_UNAVAILABLE",
        direction="WATCH_ONLY",
        status="WATCHLIST",
        promotion_status="RESEARCH_ONLY",
        score=ZERO,
        grade="D",
        confidence=ZERO,
        target_risk_reward=Decimal("2"),
        observed_at=snapshot.created_at,
        source_snapshot_id=snapshot.snapshot_id,
        supporting_evidence=(f"snapshot:{snapshot.snapshot_id}",),
        counter_evidence=tuple(dict.fromkeys((*blockers, *execution))),
        confirmation_requirements=blockers,
        promotion_requirements=("VALIDATION_GATE_REQUIRED",),
        execution_blockers=execution,
        next_evidence_action="REFRESH_CANONICAL_MARKET_SNAPSHOT",
        blockers=tuple(
            dict.fromkeys((*blockers, "VALIDATION_GATE_REQUIRED", *execution))
        ),
        pattern_type=setup_pattern_type("SETUP_UNAVAILABLE"),
    )


def _trend_aligned(candles: Sequence[OHLCVCandle]) -> bool:
    if len(candles) < 2:
        return False
    return candles[-1].close >= candles[0].close


def _direction(opportunity: VWAPOpportunity) -> str:
    if opportunity.bias is OpportunityBias.BULLISH:
        return "BULLISH"
    if opportunity.bias is OpportunityBias.BEARISH:
        return "BEARISH"
    return "WATCH_ONLY"


def _trade_plan(opportunity: VWAPOpportunity) -> Mapping[str, str]:
    if opportunity.price is None or opportunity.atr is None or opportunity.atr <= ZERO:
        return {}
    return estimate_measurable_trade_plan(
        entry=opportunity.price,
        risk=opportunity.atr,
        direction="BULLISH" if opportunity.action is Action.BUY else "BEARISH",
    )


def _price_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _vwap_lifecycle_state(
    blockers: tuple[str, ...],
) -> OpportunityLifecycleState:
    if not blockers:
        return OpportunityLifecycleState.WATCH_ONLY
    if any(
        blocker
        in {
            "VWAP_TRIGGER_MISSING",
            "VOLUME_CONFIRMATION_MISSING",
            "STRUCTURE_CONFIRMATION_REQUIRED",
            "HTF_CONFIRMATION_REQUIRED",
        }
        for blocker in blockers
    ):
        return OpportunityLifecycleState.CONFIRMATION_PENDING
    return OpportunityLifecycleState.WATCH_ONLY

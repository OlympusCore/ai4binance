"""Fail-closed, research-only opportunity observations.

This module does not generate production signals and has no execution authority.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import cast

from ai4binance.domain import Action, SetupTier
from ai4binance.indicators import atr, relative_volume, session_vwap
from ai4binance.schemas import (
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
    PromotionStatus,
)
from ai4binance.validation.summary import ValidationSummary, ValidationSummaryReader

ZERO = Decimal("0")


class OpportunityBias(StrEnum):
    """Directional observation, not an executable signal."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True, slots=True)
class VWAPOpportunityConfig:
    """Conservative thresholds for the unvalidated VWAP experiment."""

    atr_period: int = 14
    volume_window: int = 20
    min_relative_volume: Decimal = Decimal("1.2")
    max_atr_distance: Decimal = Decimal("1.5")
    crossing_lookback: int = 8
    max_crossings: int = 3

    def __post_init__(self) -> None:
        if self.atr_period < 1 or self.volume_window < 1:
            raise ValueError("indicator periods must be positive")
        if self.min_relative_volume <= ZERO or self.max_atr_distance <= ZERO:
            raise ValueError("VWAP thresholds must be positive")
        if self.crossing_lookback < 2 or self.max_crossings < 0:
            raise ValueError("crossing thresholds are invalid")


@dataclass(frozen=True, slots=True)
class VWAPOpportunity:
    """Auditable output that remains RESEARCH_ONLY by construction."""

    snapshot_id: str
    symbol: str
    timeframe: str
    observed_at: datetime
    session_start: datetime
    setup_name: str
    bias: OpportunityBias
    action: Action
    setup_tier: SetupTier
    price: Decimal | None
    vwap: Decimal | None
    atr: Decimal | None
    relative_volume: Decimal | None
    atr_distance: Decimal | None
    crossing_count: int
    evidence: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH_ONLY
    execution_allowed: bool = False


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
class OpportunityInboxItem:
    """Visible opportunity or validation item that remains review-only."""

    market: str
    symbol: str
    setup_name: str
    timeframe: str
    direction: str
    source: str
    status: str
    promotion_status: str
    score: float
    confidence: float
    blockers: tuple[str, ...]
    target_risk_reward: Decimal = Decimal("2")
    stretch_risk_reward: Decimal = Decimal("3")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for name in (
            "market",
            "symbol",
            "setup_name",
            "timeframe",
            "direction",
            "source",
            "status",
            "promotion_status",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.target_risk_reward <= ZERO:
            raise ValueError("target risk/reward must be positive")
        if self.stretch_risk_reward < self.target_risk_reward:
            raise ValueError("stretch risk/reward cannot be below target")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity inbox item cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class OpportunityInbox:
    """Bounded user-facing view of Spot/Futures opportunity evidence."""

    symbol: str
    items: tuple[OpportunityInboxItem, ...]
    validation_summary: ValidationSummary
    blockers: tuple[str, ...]
    generation_status: str = "DEGRADED"
    research_blockers: tuple[str, ...] = field(default_factory=tuple)
    execution_blockers: tuple[str, ...] = field(default_factory=tuple)
    next_safe_actions: tuple[str, ...] = field(default_factory=tuple)
    research_loop_allowed: bool = True
    opportunity_generation_allowed: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("opportunity inbox symbol is required")
        if self.generation_status not in {"ACTIVE", "DEGRADED"}:
            raise ValueError("opportunity generation status is invalid")
        if not self.research_loop_allowed or not self.opportunity_generation_allowed:
            raise ValueError("opportunity inbox must keep research generation enabled")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity inbox cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class OpportunityInboxBuilder:
    """Merge market radar and validation summaries without weakening gates."""

    validation_reader: ValidationSummaryReader
    market_outlook_path: Path
    max_items: int = 20

    def __post_init__(self) -> None:
        if self.max_items < 1:
            raise ValueError("opportunity inbox max_items must be positive")

    def build(self, symbol: str) -> OpportunityInbox:
        normalized = symbol.strip().upper()
        validation = self.validation_reader.summarize(normalized)
        research_blockers: list[str] = []
        execution_blockers: list[str] = list(validation.blockers)
        items: list[OpportunityInboxItem] = []
        market_state = self._market_state()
        if market_state is None:
            research_blockers.append("MARKET_OUTLOOK_UNAVAILABLE")
        else:
            items.extend(self._market_items(normalized, market_state))
            execution_blockers.extend(
                str(item) for item in _object_tuple(market_state.get("blockers"))
            )
        items.extend(self._validation_items(validation))
        if not items:
            research_blockers.append("NO_VISIBLE_OPPORTUNITY_EVIDENCE")
        if not any(_is_ready_execution_candidate(item) for item in items):
            execution_blockers.append("NO_READY_CANDIDATE")
        blockers = tuple(dict.fromkeys((*research_blockers, *execution_blockers)))
        return OpportunityInbox(
            normalized,
            tuple(items[: self.max_items]),
            validation,
            blockers,
            generation_status="ACTIVE" if items else "DEGRADED",
            research_blockers=tuple(dict.fromkeys(research_blockers)),
            execution_blockers=tuple(dict.fromkeys(execution_blockers)),
            next_safe_actions=_next_safe_actions(blockers),
        )

    def _market_state(self) -> Mapping[str, object] | None:
        try:
            payload = json.loads(self.market_outlook_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        return cast(Mapping[str, object], payload)

    @staticmethod
    def _market_items(
        symbol: str,
        state: Mapping[str, object],
    ) -> tuple[OpportunityInboxItem, ...]:
        setups = _object_tuple(state.get("setups_on_radar"))
        blockers = tuple(str(item) for item in _object_tuple(state.get("blockers")))
        direction = str(state.get("pro_trend_direction", "UNKNOWN"))
        status = str(state.get("status", "PARTIAL"))
        if not setups:
            return ()
        return tuple(
            _market_item(symbol, setup, blockers, direction, status) for setup in setups
        )

    @staticmethod
    def _validation_items(
        validation: ValidationSummary,
    ) -> tuple[OpportunityInboxItem, ...]:
        ordered = sorted(
            validation.runs,
            key=lambda run: (
                run.promotion_status != "STAGED_CANDIDATE",
                len(run.blockers),
                run.timeframe,
                run.playbook,
            ),
        )
        return tuple(
            OpportunityInboxItem(
                market="SPOT",
                symbol=validation.symbol,
                setup_name=run.playbook,
                timeframe=run.timeframe,
                direction="UNKNOWN",
                source="validation_summary",
                status="WATCHLIST",
                promotion_status=run.promotion_status,
                score=_metric(run.metrics, "net_return"),
                confidence=max(
                    0.0, 1.0 - _metric(run.metrics, "bootstrap_probability_of_loss")
                ),
                blockers=tuple(dict.fromkeys((*run.blockers, "EXECUTION_NOT_ALLOWED"))),
            )
            for run in ordered
        )


def _metric(metrics: tuple[tuple[str, float], ...], name: str) -> float:
    return next((value for key, value in metrics if key == name), 0.0)


def _is_ready_execution_candidate(item: OpportunityInboxItem) -> bool:
    return (
        item.status == "READY"
        and item.promotion_status == "STAGED_CANDIDATE"
        and not item.blockers
        and item.score >= 60.0
        and item.confidence >= 0.5
    )


def _next_safe_actions(blockers: tuple[str, ...]) -> tuple[str, ...]:
    actions: list[str] = []
    for blocker in blockers:
        action = _safe_action_for_blocker(blocker)
        if action:
            actions.append(action)
    if not actions:
        actions.append("KEEP_RESEARCH_RADAR_RUNNING")
    return tuple(dict.fromkeys(actions))


def _safe_action_for_blocker(blocker: str) -> str:
    if blocker in {
        "MARKET_OUTLOOK_UNAVAILABLE",
        "NO_VISIBLE_OPPORTUNITY_EVIDENCE",
    }:
        return "RUN_ANALYZE_PUBLIC"
    if blocker in {
        "VALIDATION_ARTIFACTS_UNAVAILABLE",
        "VALIDATION_RUN_CARDS_UNAVAILABLE",
        "VALIDATION_GATE_REQUIRED",
        "BACKTEST_APPROVAL_MISSING",
        "WALK_FORWARD_APPROVAL_MISSING",
        "OOS_APPROVAL_MISSING",
        "LOW_OOS_TRADE_COUNT",
        "WEAK_OOS_FOLD_CONSISTENCY",
        "COST_STRESS_RETURN_NOT_POSITIVE",
        "BOOTSTRAP_LOSS_PROBABILITY_HIGH",
    }:
        return "RUN_VALIDATION_QUEUE"
    if blocker == "NO_READY_CANDIDATE":
        return "KEEP_WATCHLIST_AND_WAIT_FOR_READY_SETUP"
    if "ORDER_BOOK" in blocker or "DEPTH" in blocker:
        return "REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE"
    if "WHALE" in blocker:
        return "RUN_WHALE_FUSION_RESEARCH"
    if "EXTERNAL" in blocker or "SOCIAL" in blocker or "NEWS" in blocker:
        return "COLLECT_SOURCED_EXTERNAL_EVIDENCE"
    if blocker == "DEPENDENCY_NOT_READY:derivatives":
        return "REFRESH_DERIVATIVES_RESEARCH"
    if blocker == "TRADE_CANDIDATE_AND_RISK_PLAN_MISSING":
        return "BUILD_CANDIDATE_RISK_PLAN"
    if "RISK_APPROVAL" in blocker:
        return "PREPARE_RISK_REVIEW"
    if blocker == "HIGH_IMPACT_DATA_UNAVAILABLE":
        return "COLLECT_HIGH_IMPACT_EVENT_CONTEXT"
    if blocker == "MACRO_CYCLE_EVIDENCE_UNAVAILABLE":
        return "REFRESH_MACRO_CYCLE_CONTEXT"
    if blocker in {
        "TPO_AUCTION_PROFILE_NOT_IMPLEMENTED",
        "COMPOSITE_BALANCE_AREAS_NOT_IMPLEMENTED",
    }:
        return "STAGE_MARKET_PROFILE_RESEARCH"
    return "REVIEW_BLOCKER:" + blocker


def _market_item(
    symbol: str,
    setup: object,
    state_blockers: tuple[str, ...],
    fallback_direction: str,
    fallback_status: str,
) -> OpportunityInboxItem:
    if isinstance(setup, Mapping):
        setup_blockers = tuple(
            str(item) for item in _object_tuple(setup.get("blockers"))
        )
        return OpportunityInboxItem(
            market="SPOT",
            symbol=symbol,
            setup_name=str(setup.get("setup_name", "UNKNOWN_SETUP")),
            timeframe=str(setup.get("timeframe", "MULTI_TF")),
            direction=str(setup.get("direction", fallback_direction)),
            source="market_outlook",
            status=str(setup.get("status", fallback_status)),
            promotion_status=str(setup.get("promotion_status", "RESEARCH_ONLY")),
            score=float(setup.get("score", 0.0)),
            confidence=float(setup.get("confidence", 0.0)),
            blockers=tuple(
                dict.fromkeys(
                    (*state_blockers, *setup_blockers, "VALIDATION_GATE_REQUIRED")
                )
            ),
        )
    return OpportunityInboxItem(
        market="SPOT",
        symbol=symbol,
        setup_name=str(setup),
        timeframe="MULTI_TF",
        direction=fallback_direction,
        source="market_outlook",
        status=fallback_status,
        promotion_status="RESEARCH_ONLY",
        score=0.0,
        confidence=0.0,
        blockers=tuple(dict.fromkeys((*state_blockers, "VALIDATION_GATE_REQUIRED"))),
    )


def _object_tuple(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()

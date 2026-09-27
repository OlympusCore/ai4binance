"""Canonical research-only trade-plan and risk/reward binding."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from hashlib import sha256
from itertools import pairwise
from typing import cast

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.domain import Action, CandidateStatus, PriceZone, TradeCandidate
from ai4binance.domain.research.virtual_runtime_attribution import TradeDecisionEvidence
from ai4binance.indicators import atr
from ai4binance.intelligence.contracts import (
    ScenarioDirection,
    ScenarioHypothesis,
    ScenarioState,
    SwingKind,
    TradingIntelligenceState,
)
from ai4binance.intelligence.method_registry import current_method_registry
from ai4binance.reporting import to_primitive
from ai4binance.schemas import MarketSnapshot

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RiskRewardEngine:
    """Calculate explicit gross, structural, and cost-aware research metrics."""

    def net(
        self, candidate: TradeCandidate, cost_ratio: Decimal | None
    ) -> Decimal | None:
        """Return cost-aware R/R or no value when required evidence is absent."""
        if cost_ratio is None:
            return None
        entry = candidate.entry_price
        risk = (
            max(
                abs(entry - candidate.invalidation_level),
                abs(entry - candidate.stop_loss),
            )
            + entry * cost_ratio
        )
        net_reward = abs(candidate.take_profit_levels[0] - entry) - entry * cost_ratio
        if risk <= ZERO or net_reward <= ZERO:
            return None
        return cast(Decimal, net_reward / risk)

    def target_ladder(
        self,
        candidate: TradeCandidate,
        cost_ratio: Decimal,
        signed_funding_ratio: Decimal = ZERO,
    ) -> tuple[tuple[Decimal, Decimal], ...]:
        """Conditional per-unit payoff and net R/R, never expected PnL.

        Transaction costs use the existing entry-notional estimate. Funding
        receipts may affect payoff but cannot reduce the stressed risk denominator.
        """
        if (
            not cost_ratio.is_finite()
            or cost_ratio < ZERO
            or not signed_funding_ratio.is_finite()
        ):
            raise ValueError(
                "plan costs must be finite with nonnegative transaction costs"
            )
        entry = candidate.entry_price
        sign = Decimal(1) if candidate.action is Action.BUY else Decimal(-1)
        risk = max(
            abs(entry - candidate.stop_loss), abs(entry - candidate.invalidation_level)
        )
        risk += entry * (cost_ratio + abs(signed_funding_ratio))
        costs = entry * (cost_ratio + signed_funding_ratio)
        return tuple(
            ((target - entry) * sign - costs, ((target - entry) * sign - costs) / risk)
            for target in candidate.take_profit_levels
        )

    def conditional_partial_exit(
        self,
        candidate: TradeCandidate,
        *,
        fractions: tuple[Decimal, ...],
        reached_targets: int,
        cost_ratio: Decimal,
        signed_funding_ratio: Decimal = ZERO,
    ) -> Decimal:
        """Payoff if a target prefix fills and the remainder hits the initial stop."""
        if (
            len(fractions) != len(candidate.take_profit_levels)
            or any(not weight.is_finite() or weight <= ZERO for weight in fractions)
            or sum(fractions) != Decimal(1)
            or isinstance(reached_targets, bool)
            or not isinstance(reached_targets, int)
            or not 0 <= reached_targets <= len(fractions)
        ):
            raise ValueError(
                "partial exits require positive weights summing to one "
                "and a valid prefix"
            )
        ladder = self.target_ladder(candidate, cost_ratio, signed_funding_ratio)
        sign = Decimal(1) if candidate.action is Action.BUY else Decimal(-1)
        stopped = (
            candidate.stop_loss - candidate.entry_price
        ) * sign - candidate.entry_price * (cost_ratio + signed_funding_ratio)
        return sum(
            (
                weight * (ladder[index][0] if index < reached_targets else stopped)
                for index, weight in enumerate(fractions)
            ),
            ZERO,
        )

    def structural(
        self,
        candidate: TradeCandidate,
        scenario: ScenarioHypothesis,
    ) -> Decimal | None:
        """Return structural R/R only when scenario invalidation has valid geometry."""
        invalidation = scenario.invalidation_level
        valid = invalidation is not None and (
            ZERO < invalidation < candidate.entry_zone.lower
            if candidate.action is Action.BUY
            else invalidation > candidate.entry_zone.upper
        )
        if not valid or invalidation is None:
            return None
        return cast(
            Decimal,
            abs(candidate.take_profit_levels[0] - candidate.entry_price)
            / abs(candidate.entry_price - invalidation),
        )


@dataclass(frozen=True, slots=True)
class TradePlanEngine:
    """Bind a strategy proposal to one selected scenario in deterministic order."""

    risk_reward_engine: RiskRewardEngine = RiskRewardEngine()

    def propose(
        self, snapshot: MarketSnapshot, state: TradingIntelligenceState
    ) -> tuple[TradeCandidate, ...]:
        """Create structural Futures proposals without an indicator candidate seed.

        ATR describes volatility only. Entry, invalidation and targets must be
        observable prices; missing geometry never falls back to ATR multiples.
        """
        scenario = state.selected_scenario
        if (
            snapshot.market_type != "USD_M_FUTURES"
            or (state.snapshot_id, state.symbol, state.timestamp, state.market_type)
            != (
                snapshot.snapshot_id,
                snapshot.symbol,
                snapshot.created_at,
                snapshot.market_type,
            )
            or state.blockers
            or scenario is None
            or scenario.state is not ScenarioState.CONFIRMED
            or scenario.blockers
            or scenario.invalidation_level is None
            or scenario.direction is ScenarioDirection.NEUTRAL
        ):
            return ()
        structures = {item.timeframe: item for item in state.structures}
        if any(
            timeframe not in structures
            or structures[timeframe].method != "CONFIRMED_SWING_GRAPH"
            or any(
                sum(s.kind is kind for s in structures[timeframe].swings) < 2
                for kind in SwingKind
            )
            for timeframe in ("4h", "1h")
        ):
            return ()
        long = scenario.direction is ScenarioDirection.LONG
        method = "CONFIRMED_PIVOT_SUPPORT" if long else "CONFIRMED_PIVOT_RESISTANCE"
        if not any(
            line.source_timeframe == "4h"
            and line.method == method
            and not line.blockers
            and line.break_state in {"UNBROKEN", "FALSE_BREAK"}
            and (line.slope > ZERO if long else line.slope < ZERO)
            for line in state.trend_geometry
        ):
            return ()
        timeframes = tuple(
            timeframe
            for timeframe in ("15m", "5m")
            if f"ENTRY_TRIGGER_TIMEFRAME:{timeframe}" in scenario.evidence_for
        )
        proposals: list[TradeCandidate] = []
        for timeframe in timeframes:
            rows = tuple(
                candle
                for candle in snapshot.ohlcv_by_timeframe.get(timeframe, ())
                if candle.timestamp + timeframe_duration(timeframe)
                <= snapshot.created_at
            )
            if (
                len(rows) < 15
                or any(
                    b.timestamp - a.timestamp != timeframe_duration(timeframe)
                    for a, b in pairwise(rows)
                )
                or snapshot.created_at
                - (rows[-1].timestamp + timeframe_duration(timeframe))
                >= timeframe_duration(timeframe)
            ):
                continue
            entry, stop = rows[-1].close, scenario.invalidation_level
            long = scenario.direction is ScenarioDirection.LONG
            targets = self._targets(state, entry, long)
            if not targets or not (
                ZERO < stop < entry if long else stop > entry > ZERO
            ):
                continue
            volatility = atr(rows, 14)
            if volatility <= ZERO:
                continue
            digest = sha256(
                f"{scenario.scenario_id}|{timeframe}|structural-v3".encode()
            ).hexdigest()[:20]
            candidate = TradeCandidate(
                candidate_id=f"candidate:{digest}",
                snapshot_id=snapshot.snapshot_id,
                timestamp=snapshot.created_at,
                symbol=snapshot.symbol,
                timeframe=timeframe,
                action=Action.BUY if long else Action.SELL,
                setup_name="trend_continuation",
                status=CandidateStatus.READY_FOR_RISK,
                entry_zone=PriceZone(entry, entry),
                invalidation_level=stop,
                stop_loss=stop,
                take_profit_levels=tuple(targets),
                trailing_stop=stop,
                atr=volatility,
                risk_reward=abs(next(iter(targets)) - entry) / abs(entry - stop),
                score=scenario.confidence * 100,
                confidence=scenario.confidence,
                market_type=snapshot.market_type,
                evidence=(
                    *scenario.evidence_for,
                    "STRUCTURAL_ENTRY_V3",
                    "ATR_VOLATILITY_ONLY",
                ),
                target_sources=tuple(targets.values()),
            )
            candidate = self.structural_candidate(candidate, scenario, state, snapshot)
            candidate = self.bind(candidate, scenario, state)
            evidence = TradeDecisionEvidence(
                status="RECORDED_AT_DECISION",
                as_of=snapshot.created_at,
                direction_method="CONFIRMED_SWING_GRAPH_AND_4H_TREND_GEOMETRY",
                entry_method="CONFIRMED_SCENARIO_CLOSED_CANDLE_TRIGGER",
                factors_json=json.dumps(
                    to_primitive(
                        {
                            "state": state,
                            **self._plan_factors(candidate),
                            "entry_candles": rows[-50:],
                            "entry": candidate.entry_price,
                            "initial_stop": candidate.stop_loss,
                            "targets": candidate.take_profit_levels,
                            "target_sources": candidate.target_sources,
                            "direction": "LONG" if long else "SHORT",
                            "timeframe": timeframe,
                            "entry_trigger": candidate.entry_trigger,
                            "entry_state": candidate.entry_state,
                            "entry_expiry": candidate.entry_expiry,
                            "gross_rr": candidate.risk_reward,
                            "net_rr": candidate.net_risk_reward,
                            "expected_r": candidate.expected_r,
                            "probability_calibration_state": (
                                candidate.probability_calibration_state
                            ),
                            "atr_role": "VOLATILITY_ONLY",
                            "ema_role": "NOT_USED",
                            "leverage_authority": "DOWNSTREAM_DETERMINISTIC_RISK_GATE",
                        }
                    ),
                    sort_keys=True,
                ),
            )
            proposals.append(replace(candidate, decision_evidence=evidence))
        return tuple(proposals)

    @staticmethod
    def _targets(
        state: TradingIntelligenceState, entry: Decimal, long: bool
    ) -> dict[Decimal, str]:
        targets: dict[Decimal, str] = {}
        for level in state.levels:
            if level.level_type not in {"SUPPORT", "RESISTANCE"}:
                continue
            effective_type = (
                ("RESISTANCE" if level.level_type == "SUPPORT" else "SUPPORT")
                if level.role_flip
                else level.level_type
            )
            if level.freshness not in {"FRESH", "AGING"} or effective_type != (
                "RESISTANCE" if long else "SUPPORT"
            ):
                continue
            price = level.price_low if long else level.price_high
            if price > entry if long else ZERO < price < entry:
                targets.setdefault(price, level.level_id)
        return {
            price: targets[price] for price in sorted(targets, reverse=not long)[:3]
        }

    def structural_candidate(
        self,
        candidate: TradeCandidate,
        scenario: ScenarioHypothesis,
        state: TradingIntelligenceState,
        snapshot: MarketSnapshot,
    ) -> TradeCandidate:
        """Derive Futures targets from observed zones before risk evaluation.

        Keep the existing invalidation boundary: rounding may tighten the stop,
        never extend risk beyond the scenario. Missing geometry is a veto.
        """
        raw = snapshot.exchange_filters.get("PRICE_FILTER", {})
        try:
            tick = (
                Decimal(str(raw.get("tickSize"))) if isinstance(raw, Mapping) else ZERO
            )
        except InvalidOperation:
            tick = ZERO
        if not tick.is_finite() or tick <= ZERO:
            return self._unavailable(candidate, "STRUCTURAL_PLAN_TICK_SIZE_UNAVAILABLE")
        invalidation = scenario.invalidation_level
        if invalidation is None:
            return self._unavailable(
                candidate, "STRUCTURAL_PLAN_INVALIDATION_UNAVAILABLE"
            )
        long = candidate.action is Action.BUY
        entry_rounding = ROUND_CEILING if long else ROUND_FLOOR
        target_rounding = ROUND_FLOOR if long else ROUND_CEILING
        entry = (candidate.entry_price / tick).to_integral_value(
            rounding=entry_rounding
        ) * tick
        stop = (invalidation / tick).to_integral_value(rounding=entry_rounding) * tick
        if not (ZERO < stop < entry if long else stop > entry > ZERO):
            return self._unavailable(candidate, "STRUCTURAL_PLAN_STOP_GEOMETRY_INVALID")
        targets: dict[Decimal, str] = {}
        for edge, source in self._targets(state, entry, long).items():
            price = (edge / tick).to_integral_value(rounding=target_rounding) * tick
            if price > entry if long else ZERO < price < entry:
                targets.setdefault(price, source)
        ordered = tuple(sorted(targets, reverse=not long))[:3]
        if not ordered:
            return self._unavailable(candidate, "STRUCTURAL_PLAN_TARGET_UNAVAILABLE")
        return replace(
            candidate,
            entry_zone=PriceZone(entry, entry),
            stop_loss=stop,
            invalidation_level=stop,
            trailing_stop=stop,
            take_profit_levels=ordered,
            risk_reward=abs(ordered[0] - entry) / abs(entry - stop),
            target_sources=tuple(targets[target] for target in ordered),
            evidence=tuple(dict.fromkeys((*candidate.evidence, "STRUCTURAL_PLAN_V2"))),
        )

    @staticmethod
    def _unavailable(candidate: TradeCandidate, blocker: str) -> TradeCandidate:
        return replace(
            candidate,
            status=CandidateStatus.RESEARCH_ONLY,
            blockers=tuple(dict.fromkeys((*candidate.blockers, blocker))),
        )

    def bind(
        self,
        candidate: TradeCandidate,
        scenario: ScenarioHypothesis,
        state: TradingIntelligenceState,
    ) -> TradeCandidate:
        """Apply scenario, invalidation, entry, target, and R/R constraints.

        This remains a research-plan projection: it cannot set execution authority,
        synthesize OOS calibration, or alter strategy-owned price geometry.
        """
        status, blockers = self._scenario_readiness(candidate, scenario, state)

        net_risk_reward = self.risk_reward_engine.net(
            candidate, state.estimated_round_trip_cost_ratio
        )
        if net_risk_reward is None:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.extend((*state.cost_blockers, "NET_RISK_REWARD_UNAVAILABLE"))
        structural_risk_reward = self.risk_reward_engine.structural(candidate, scenario)
        if structural_risk_reward is None:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.append("SCENARIO_INVALIDATION_UNAVAILABLE_OR_INVALID")
        if scenario.blockers and scenario.state is ScenarioState.CONFIRMED:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.extend(scenario.blockers)
        if scenario.state is ScenarioState.CONFIRMED and scenario.confidence <= 0:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.append("SCENARIO_CONFIDENCE_UNAVAILABLE")
        expiry = self.entry_expiry(candidate.timestamp, candidate.timeframe)
        if expiry is None:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.append("ENTRY_EXPIRY_UNAVAILABLE")
        unique_blockers = tuple(dict.fromkeys(blockers))
        candidate = self._economics(candidate, scenario, state)
        decision_evidence = candidate.decision_evidence
        if decision_evidence.status == "NOT_RECORDED":
            decision_evidence = TradeDecisionEvidence(
                status="RECORDED_AT_DECISION",
                as_of=state.timestamp,
                direction_method="CANONICAL_SCENARIO",
                entry_method="SCENARIO_BINDING",
                factors_json=json.dumps(
                    to_primitive(
                        {
                            "state": state,
                            **self._plan_factors(candidate),
                        }
                    ),
                    sort_keys=True,
                ),
            )
        return replace(
            candidate,
            status=status,
            scenario_id=scenario.scenario_id,
            decision_evidence=decision_evidence,
            scenario_type=scenario.scenario_type.value,
            scenario_state=scenario.state.value,
            scenario_invalidation=(
                str(scenario.invalidation_level)
                if scenario.invalidation_level is not None
                else None
            ),
            structural_risk_reward=structural_risk_reward,
            net_risk_reward=net_risk_reward,
            estimated_round_trip_cost_ratio=state.estimated_round_trip_cost_ratio,
            expected_r=None,
            probability_calibration_state=scenario.calibration_state.value,
            entry_trigger=self.entry_trigger(scenario),
            entry_state=(
                "ENTRY_VALID"
                if status is CandidateStatus.READY_FOR_RISK and not unique_blockers
                else "ENTRY_NOT_READY"
            ),
            entry_expiry=expiry,
            target_sources=candidate.target_sources,
            evidence=tuple(
                dict.fromkeys(
                    (
                        *candidate.evidence,
                        f"SCENARIO_ID:{scenario.scenario_id}",
                        f"SCENARIO_TYPE:{scenario.scenario_type.value}",
                    )
                )
            ),
            blockers=unique_blockers,
        )

    @staticmethod
    def _scenario_readiness(
        candidate: TradeCandidate,
        scenario: ScenarioHypothesis,
        state: TradingIntelligenceState,
    ) -> tuple[CandidateStatus, list[str]]:
        """Preserve mandatory readiness vetoes before calculating economics."""
        status = candidate.status
        blockers = list(candidate.blockers)
        if state.blockers:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.extend(state.blockers)
        if (
            scenario.state is ScenarioState.CONFIRMED
            and f"ENTRY_TRIGGER_TIMEFRAME:{candidate.timeframe}"
            not in scenario.evidence_for
        ):
            status = CandidateStatus.RESEARCH_ONLY
            blockers.append("ENTRY_TRIGGER_TIMEFRAME_MISMATCH")
        if scenario.state is ScenarioState.FORMING:
            if status is CandidateStatus.READY_FOR_RISK:
                status = CandidateStatus.WAIT_FOR_RETEST
            blockers.append("SCENARIO_CONFIRMATION_PENDING")
        elif scenario.state is not ScenarioState.CONFIRMED:
            status = CandidateStatus.RESEARCH_ONLY
            blockers.extend(("SCENARIO_NOT_CONFIRMED", *scenario.blockers))

        return status, blockers

    @staticmethod
    def _plan_factors(candidate: TradeCandidate) -> dict[str, object]:
        return {
            "method_registry": current_method_registry().snapshot_payload(),
            "target_net_risk_rewards": candidate.target_net_risk_rewards,
            "target_conditional_pnl_per_unit": (
                candidate.target_conditional_pnl_per_unit
            ),
            "signed_funding_cost_ratio": candidate.signed_funding_cost_ratio,
            "stop_alternatives": candidate.stop_alternatives,
        }

    def _economics(
        self,
        candidate: TradeCandidate,
        scenario: ScenarioHypothesis,
        state: TradingIntelligenceState,
    ) -> TradeCandidate:
        funding = ZERO
        if state.market_type == "USD_M_FUTURES":
            if (
                state.funding_periods is None
                or state.derivatives_context.funding_rate is None
            ):
                return candidate
            sign = Decimal(1) if candidate.action is Action.BUY else Decimal(-1)
            funding = (
                state.derivatives_context.funding_rate * state.funding_periods * sign
            )
        if state.transaction_cost_ratio is None:
            return candidate
        ladder = self.risk_reward_engine.target_ladder(
            candidate, state.transaction_cost_ratio, funding
        )
        alternatives = tuple(
            (f"STRUCTURE:{row.timeframe}", row.invalidation_level)
            for row in state.structures
            if row.invalidation_level is not None
            and (
                ZERO < row.invalidation_level < candidate.entry_price
                if candidate.action is Action.BUY
                else row.invalidation_level > candidate.entry_price
            )
        )
        return replace(
            candidate,
            target_net_risk_rewards=tuple(row[1] for row in ladder),
            target_conditional_pnl_per_unit=tuple(row[0] for row in ladder),
            signed_funding_cost_ratio=funding,
            stop_alternatives=(
                (f"SELECTED_SCENARIO:{scenario.scenario_id}", candidate.stop_loss),
                *alternatives,
            ),
        )

    @staticmethod
    def entry_trigger(scenario: ScenarioHypothesis) -> str:
        return next(
            (
                item
                for item in scenario.evidence_for
                if any(
                    marker in item
                    for marker in ("ENGULFING", "BREAKOUT", "RETEST", "TRIGGER")
                )
            ),
            "SCENARIO_CONFIRMATION",
        )

    @staticmethod
    def entry_expiry(timestamp: datetime, timeframe: str) -> datetime | None:
        unit, raw_value = timeframe[-1:].lower(), timeframe[:-1]
        if not raw_value.isdigit() or len(raw_value) > 6:
            return None
        value = int(raw_value)
        if value < 1:
            return None
        scale = {"m": 60, "h": 3600, "d": 86400}.get(unit)
        try:
            return timestamp + timedelta(seconds=value * scale) if scale else None
        except OverflowError:
            return None

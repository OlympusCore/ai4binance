"""Canonical research-only trade-plan and risk/reward binding."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from ai4binance.domain import Action, CandidateStatus, TradeCandidate
from ai4binance.intelligence.contracts import (
    ScenarioHypothesis,
    ScenarioState,
    TradingIntelligenceState,
)

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
        status = candidate.status
        blockers = list(candidate.blockers)
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
        return replace(
            candidate,
            status=status,
            scenario_id=scenario.scenario_id,
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

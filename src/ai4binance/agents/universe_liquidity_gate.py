"""Deterministic Spot universe and liquidity eligibility gate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ai4binance.agents.registry import AgentDefinition, AgentStage
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OOSValidationStatus,
)


@dataclass(frozen=True, slots=True)
class UniverseLiquidityGate:
    """Apply deterministic Spot listing, filter, and spread eligibility checks."""

    definition: AgentDefinition
    maximum_spread_ratio: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        if (
            self.definition.name != "universe_liquidity"
            or self.definition.stage is not AgentStage.ELIGIBILITY
        ):
            raise ValueError(
                "universe liquidity gate requires the universe_liquidity definition"
            )
        if not Decimal("0") < self.maximum_spread_ratio < Decimal("1"):
            raise ValueError("maximum_spread_ratio must be between 0 and 1")

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Return the dependency-checked, fail-closed eligibility result."""
        blocked_dependencies = tuple(
            dependency
            for dependency in self.definition.dependencies
            if dependency not in prior_results
            or prior_results[dependency].status
            not in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}
        )
        if blocked_dependencies:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=tuple(
                    f"DEPENDENCY_NOT_READY:{dependency}"
                    for dependency in blocked_dependencies
                ),
                reason_codes=("AGENT_DEPENDENCY_BLOCKED",),
            )
        try:
            return self.evaluate_snapshot(snapshot)
        except Exception as error:
            return self._result(
                snapshot,
                status=AgentStatus.FAILED,
                data_quality=DataQuality.DATA_INVALID,
                applicable=False,
                blockers=("AGENT_INTERNAL_ERROR",),
                reason_codes=("AGENT_FAILED_CLOSED",),
                calculation_metadata={"error_type": type(error).__name__},
            )

    def evaluate_snapshot(self, snapshot: MarketSnapshot) -> AgentResult:
        """Evaluate a snapshot after data-quality readiness is established."""
        blockers: list[str] = []
        if snapshot.market_metadata.get("trading_status") != "TRADING":
            blockers.append("SYMBOL_NOT_CONFIRMED_TRADING")
        if not snapshot.exchange_filters:
            blockers.append("EXCHANGE_FILTERS_MISSING")
        if snapshot.latest_price is None or snapshot.latest_price <= Decimal("0"):
            blockers.append("LATEST_PRICE_MISSING")
        if snapshot.bid is None or snapshot.ask is None or snapshot.spread is None:
            blockers.append("BID_ASK_SPREAD_MISSING")
        elif snapshot.latest_price is not None and snapshot.latest_price > Decimal("0"):
            spread_ratio = snapshot.spread / snapshot.latest_price
            if spread_ratio > self.maximum_spread_ratio:
                blockers.append("SPREAD_EXCEEDS_LIMIT")

        unique_blockers = tuple(dict.fromkeys(blockers))
        return self._result(
            snapshot,
            status=AgentStatus.BLOCKED if unique_blockers else AgentStatus.SUCCESS,
            data_quality=(
                DataQuality.DATA_INVALID if unique_blockers else DataQuality.DATA_VALID
            ),
            applicable=True,
            score=0.0 if unique_blockers else 100.0,
            confidence=1.0,
            blockers=unique_blockers,
            reason_codes=(
                "UNIVERSE_LIQUIDITY_BLOCKED"
                if unique_blockers
                else "UNIVERSE_LIQUIDITY_VALID",
            ),
            calculation_metadata={
                "maximum_spread_ratio": str(self.maximum_spread_ratio)
            },
        )

    def _result(
        self,
        snapshot: MarketSnapshot,
        *,
        status: AgentStatus,
        data_quality: DataQuality,
        applicable: bool,
        directional_vote: float = 0.0,
        score: float = 0.0,
        confidence: float = 0.0,
        blockers: tuple[str, ...] = (),
        reason_codes: tuple[str, ...],
        calculation_metadata: Mapping[str, object] | None = None,
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.definition.name,
            agent_version=self.definition.version,
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframes=snapshot.timeframes,
            status=status,
            data_quality=data_quality,
            applicable=applicable,
            directional_vote=directional_vote,
            score=score,
            confidence=confidence,
            blockers=blockers,
            false_positive_risk=self.definition.false_positive_risk,
            hard_gate_eligible=False,
            oos_validation_status=OOSValidationStatus.UNVALIDATED,
            promotion_status=self.definition.promotion_status,
            reason_codes=reason_codes,
            calculation_metadata=calculation_metadata or {},
        )

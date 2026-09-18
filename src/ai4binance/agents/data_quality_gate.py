"""Deterministic snapshot quality gate with no decision or execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise

from ai4binance.agents.registry import AgentDefinition, AgentStage
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OOSValidationStatus,
)


@dataclass(frozen=True, slots=True)
class DataQualityGate:
    """Validate canonical snapshot candles before analytical execution begins."""

    definition: AgentDefinition
    minimum_candles: int = 2

    def __post_init__(self) -> None:
        if (
            self.definition.name != "data_quality"
            or self.definition.stage is not AgentStage.ELIGIBILITY
        ):
            raise ValueError("data quality gate requires the data_quality definition")
        if self.minimum_candles < 2:
            raise ValueError("minimum_candles must be at least 2")

    def evaluate(self, snapshot: MarketSnapshot) -> AgentResult:
        """Return the immutable, fail-closed quality result for one snapshot."""
        try:
            return self._evaluate(snapshot)
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

    def _evaluate(self, snapshot: MarketSnapshot) -> AgentResult:
        blockers: list[str] = []
        warnings: list[str] = []
        candle_counts: dict[str, int] = {}

        if snapshot.data_quality is DataQuality.DATA_INVALID:
            blockers.append("SNAPSHOT_DATA_QUALITY_INVALID")

        for timeframe in snapshot.timeframes:
            candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
            candle_counts[timeframe] = len(candles)
            if len(candles) < self.minimum_candles:
                blockers.append(f"INSUFFICIENT_CANDLES:{timeframe}")
                continue
            timestamps = tuple(candle.timestamp for candle in candles)
            if len(set(timestamps)) != len(timestamps):
                blockers.append(f"DUPLICATE_CANDLES:{timeframe}")
            if any(current >= following for current, following in pairwise(timestamps)):
                blockers.append(f"OUT_OF_ORDER_CANDLES:{timeframe}")
            if any(timestamp > snapshot.created_at for timestamp in timestamps):
                blockers.append(f"FUTURE_CANDLE:{timeframe}")
            if any(candle.volume == Decimal("0") for candle in candles):
                warnings.append(f"ZERO_VOLUME:{timeframe}")
            freshness = snapshot.data_freshness.get(timeframe)
            if isinstance(freshness, Mapping) and freshness.get("stale") is True:
                blockers.append(f"STALE_CANDLES:{timeframe}")

        unique_blockers = tuple(dict.fromkeys(blockers))
        unique_warnings = tuple(dict.fromkeys(warnings))
        if unique_blockers:
            status = AgentStatus.BLOCKED
            quality = DataQuality.DATA_INVALID
            score = 0.0
        elif unique_warnings:
            status = AgentStatus.PARTIAL
            quality = DataQuality.DATA_DEGRADED
            score = 60.0
        else:
            status = AgentStatus.SUCCESS
            quality = DataQuality.DATA_VALID
            score = 100.0
        return self._result(
            snapshot,
            status=status,
            data_quality=quality,
            applicable=True,
            score=score,
            confidence=1.0,
            blockers=unique_blockers,
            warnings=unique_warnings,
            reason_codes=(
                (
                    "DATA_INVALID"
                    if unique_blockers
                    else "DATA_DEGRADED"
                    if unique_warnings
                    else "DATA_VALID"
                ),
            ),
            calculation_metadata={"candle_counts": candle_counts},
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
        warnings: tuple[str, ...] = (),
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
            warnings=warnings,
            false_positive_risk=self.definition.false_positive_risk,
            hard_gate_eligible=False,
            oos_validation_status=OOSValidationStatus.UNVALIDATED,
            promotion_status=self.definition.promotion_status,
            reason_codes=reason_codes,
            calculation_metadata=calculation_metadata or {},
        )

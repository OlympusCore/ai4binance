"""Implemented eligibility agents and safe research-only specialists."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from math import fsum

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.registry import AgentRegistry, AgentStage
from ai4binance.domain import TradeCandidate
from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import FilterValue, SymbolInfo
from ai4binance.risk import RiskContext, RiskEngine
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    is_usable_agent_result,
)


@dataclass(frozen=True, slots=True)
class ResearchOnlyAgent(BaseAgent):
    """Installed specialist that cannot claim evidence before implementation."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        return self.result(
            snapshot,
            status=AgentStatus.INSUFFICIENT_DATA,
            data_quality=snapshot.data_quality,
            applicable=False,
            blockers=("SPECIALIST_IMPLEMENTATION_NOT_VALIDATED",),
            warnings=("RESEARCH_ONLY_AGENT",),
            reason_codes=("RESEARCH_ONLY_NO_SIGNAL",),
            calculation_metadata={
                "required_data": self.definition.required_data,
                "oos_requirements": self.definition.oos_requirements,
            },
        )


@dataclass(frozen=True, slots=True)
class DataQualityAgent(BaseAgent):
    """Validate candle continuity, freshness and minimum history."""

    minimum_candles: int = 2

    def __post_init__(self) -> None:
        if self.minimum_candles < 2:
            raise ValueError("minimum_candles must be at least 2")

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
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
        return self.result(
            snapshot,
            status=status,
            data_quality=quality,
            applicable=True,
            score=score,
            confidence=1.0,
            blockers=unique_blockers,
            warnings=unique_warnings,
            reason_codes=(
                "DATA_INVALID"
                if unique_blockers
                else "DATA_DEGRADED"
                if unique_warnings
                else "DATA_VALID",
            ),
            calculation_metadata={"candle_counts": candle_counts},
        )


@dataclass(frozen=True, slots=True)
class UniverseLiquidityAgent(BaseAgent):
    """Apply deterministic Spot listing, filter and spread eligibility checks."""

    maximum_spread_ratio: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        if not Decimal("0") < self.maximum_spread_ratio < Decimal("1"):
            raise ValueError("maximum_spread_ratio must be between 0 and 1")

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
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
        return self.result(
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


@dataclass(frozen=True, slots=True)
class ConfluenceAgent(BaseAgent):
    """Combine only one strongest result from each independent evidence cluster."""

    registry: AgentRegistry

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        cluster_results: dict[str, AgentResult] = {}
        rejected_correlated: list[str] = []
        for name, result in prior_results.items():
            definition = self.registry.by_name.get(name)
            if definition is None or definition.stage is not AgentStage.ANALYSIS:
                continue
            if not is_usable_agent_result(result):
                continue
            current = cluster_results.get(definition.evidence_cluster)
            if current is None or (
                result.confidence,
                result.score,
                result.agent_name,
            ) > (
                current.confidence,
                current.score,
                current.agent_name,
            ):
                if current is not None:
                    rejected_correlated.append(current.agent_name)
                cluster_results[definition.evidence_cluster] = result
            else:
                rejected_correlated.append(result.agent_name)

        selected = tuple(cluster_results[name] for name in sorted(cluster_results))
        if not selected:
            return self.result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("NO_VALIDATED_SPECIALIST_EVIDENCE",),
                reason_codes=("CONFLUENCE_BLOCKED",),
            )
        weights = tuple(max(result.confidence, 0.01) for result in selected)
        weight_total = fsum(weights)
        score = (
            fsum(
                result.score * weight
                for result, weight in zip(selected, weights, strict=True)
            )
            / weight_total
        )
        vote = (
            fsum(
                result.directional_vote * weight
                for result, weight in zip(selected, weights, strict=True)
            )
            / weight_total
        )
        confidence = fsum(result.confidence for result in selected) / len(selected)
        aligned_weight = fsum(
            weight
            for result, weight in zip(selected, weights, strict=True)
            if vote == 0 or result.directional_vote * vote >= 0
        )
        directional_agreement = aligned_weight / weight_total
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=round(score, 6),
            confidence=round(confidence, 6),
            evidence=tuple(result.agent_name for result in selected),
            warnings=(
                ("OOS_VALIDATION_INCOMPLETE", "DIRECTIONAL_CONFLICT")
                if directional_agreement < 0.67
                else ("OOS_VALIDATION_INCOMPLETE",)
            ),
            reason_codes=("INDEPENDENT_CONFLUENCE_CALCULATED",),
            calculation_metadata={
                "independent_confluence_count": len(selected),
                "evidence_clusters": tuple(sorted(cluster_results)),
                "selected_agents": tuple(result.agent_name for result in selected),
                "rejected_correlated_agents": tuple(sorted(rejected_correlated)),
                "directional_agreement": round(directional_agreement, 6),
            },
        )


@dataclass(frozen=True, slots=True)
class RiskAgent(BaseAgent):
    """Evaluate strategy candidates with deterministic capital controls."""

    candidates: tuple[TradeCandidate, ...] = ()
    risk_engine: RiskEngine = field(default_factory=RiskEngine)

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        if not self.candidates:
            return self.result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",),
                reason_codes=("RISK_REJECTED_NO_PLAN",),
            )
        try:
            filters = SymbolFilters.from_symbol_info(self._symbol_info(snapshot))
        except ExchangePayloadError:
            return self.result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("EXCHANGE_FILTERS_INVALID",),
                reason_codes=("RISK_REJECTED_INVALID_FILTERS",),
            )
        context = RiskContext(
            equity_usdt=self._optional_decimal(
                snapshot.wallet_summary.get("equity_usdt")
            ),
            current_exposure_usdt=self._optional_decimal(
                snapshot.inventory_summary.get("exposure_usdt")
            )
            or Decimal("0"),
            inventory_quantity=self._optional_decimal(
                snapshot.inventory_summary.get("quantity")
            ),
            daily_loss_usdt=self._optional_decimal(
                snapshot.wallet_summary.get("daily_loss_usdt")
            )
            or Decimal("0"),
            estimated_slippage_ratio=self._optional_decimal(
                snapshot.market_metadata.get("estimated_slippage_ratio")
            )
            or Decimal("0"),
            consecutive_losses=self._optional_integer(
                snapshot.market_metadata.get("consecutive_losses")
            ),
            cooldown_active=snapshot.market_metadata.get("cooldown_active") is True,
        )
        assessments = self.risk_engine.evaluate_many(
            self.candidates,
            snapshot,
            context,
            filters,
            limit=5,
        )
        assessment = min(
            assessments,
            key=lambda item: (
                not item.approved,
                len(item.blockers),
                item.candidate_id,
            ),
        )
        return self.result(
            snapshot,
            status=(
                AgentStatus.SUCCESS if assessment.approved else AgentStatus.BLOCKED
            ),
            data_quality=snapshot.data_quality,
            applicable=True,
            score=100.0 if assessment.approved else 0.0,
            confidence=1.0,
            blockers=assessment.blockers,
            reason_codes=("RISK_APPROVED" if assessment.approved else "RISK_REJECTED",),
            calculation_metadata={
                "candidate_id": assessment.candidate_id,
                "approved": assessment.approved,
                "size_usdt": str(assessment.size_usdt),
                "quantity": str(assessment.quantity),
                "risk_amount_usdt": str(assessment.risk_amount_usdt),
                "evaluated_candidate_count": len(assessments),
                "unevaluated_candidate_count": max(
                    0, len(self.candidates) - len(assessments)
                ),
                "assessments": tuple(
                    {
                        "candidate_id": item.candidate_id,
                        "approved": item.approved,
                        "blockers": item.blockers,
                    }
                    for item in assessments
                ),
            },
        )

    @staticmethod
    def _optional_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() and parsed >= Decimal("0") else None

    @staticmethod
    def _optional_integer(value: object) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @staticmethod
    def _symbol_info(snapshot: MarketSnapshot) -> SymbolInfo:
        filters: dict[str, Mapping[str, FilterValue]] = {}
        for name, raw_values in snapshot.exchange_filters.items():
            if not isinstance(raw_values, Mapping):
                raise ExchangePayloadError("snapshot exchange filter is invalid")
            parsed: dict[str, FilterValue] = {}
            for key, value in raw_values.items():
                if value is not None and not isinstance(value, (str, int, float, bool)):
                    raise ExchangePayloadError("snapshot filter value is invalid")
                parsed[str(key)] = value
            filters[name] = parsed
        base_asset = snapshot.market_metadata.get("base_asset", "UNKNOWN_BASE")
        quote_asset = snapshot.market_metadata.get("quote_asset", "UNKNOWN_QUOTE")
        status = snapshot.market_metadata.get("trading_status", "UNKNOWN")
        return SymbolInfo(
            snapshot.symbol,
            str(status),
            str(base_asset),
            str(quote_asset),
            filters,
        )

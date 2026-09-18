"""Implemented eligibility agents and safe research-only specialists."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.data_quality_gate import DataQualityGate
from ai4binance.agents.evidence_fusion import EvidenceFusionEngine
from ai4binance.agents.registry import AgentRegistry
from ai4binance.agents.risk_gate import RiskGate
from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate
from ai4binance.domain import TradeCandidate
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.risk import RiskEngine
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    MarketSnapshot,
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
    """Compatibility facade for the canonical `DataQualityGate`."""

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
        return DataQualityGate(
            self.definition,
            minimum_candles=self.minimum_candles,
        ).evaluate(snapshot)


@dataclass(frozen=True, slots=True)
class UniverseLiquidityAgent(BaseAgent):
    """Compatibility facade for the canonical `UniverseLiquidityGate`."""

    maximum_spread_ratio: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        UniverseLiquidityGate(
            self.definition,
            maximum_spread_ratio=self.maximum_spread_ratio,
        )

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        return UniverseLiquidityGate(
            self.definition,
            maximum_spread_ratio=self.maximum_spread_ratio,
        ).evaluate_snapshot(snapshot)


@dataclass(frozen=True, slots=True)
class ConfluenceAgent(BaseAgent):
    """Compatibility facade for the canonical `EvidenceFusionEngine`."""

    registry: AgentRegistry

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        return EvidenceFusionEngine(self.definition, self.registry).fuse(
            snapshot,
            prior_results,
        )


@dataclass(frozen=True, slots=True)
class RiskAgent(BaseAgent):
    """Compatibility facade for the canonical `RiskGate`."""

    candidates: tuple[TradeCandidate, ...] = ()
    risk_engine: RiskEngine = field(default_factory=RiskEngine)
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        return RiskGate(
            self.definition,
            candidates=self.candidates,
            risk_engine=self.risk_engine,
            execution_surface=self.execution_surface,
        ).evaluate_candidates(snapshot)

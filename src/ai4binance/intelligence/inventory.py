"""Machine-checkable P0--P14 Trading Intelligence ownership inventory."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from ai4binance.intelligence.method_registry import current_method_registry


@dataclass(frozen=True, slots=True)
class AnalysisMethodCoverage:
    """Reviewed family scope, not a claim of exhaustive technical-analysis coverage."""

    family: str
    module: str
    owner: str
    implemented: tuple[str, ...]
    missing: tuple[str, ...]
    decision_role: str
    limitations: str
    tests: tuple[str, ...]
    sources: tuple[str, ...]
    performance_status: str = "METHOD_LEVEL_OOS_NOT_VERIFIED"

    @property
    def coverage_status(self) -> str:
        return "PARTIAL" if self.missing else "IMPLEMENTED_WITHIN_REVIEWED_SCOPE"


def _coverage_projection() -> tuple[AnalysisMethodCoverage, ...]:
    """Keep the legacy family interface as a projection of the one registry."""
    registry = current_method_registry()
    sources = {source.source_id: source.locator for source in registry.sources}
    return tuple(
        AnalysisMethodCoverage(
            family=row.family,
            module=row.module,
            owner=row.owner,
            implemented=row.implemented,
            missing=row.missing,
            decision_role=row.decision_role,
            limitations=row.limitations,
            tests=row.tests,
            sources=tuple(sources[key] for key in row.source_ids),
        )
        for row in registry.coverage
    )


ANALYSIS_METHODS = _coverage_projection()
REQUIRED_ANALYSIS_FAMILIES = frozenset(row.family for row in ANALYSIS_METHODS)


@dataclass(frozen=True, slots=True)
class TradingIntelligencePhase:
    """One ordered delivery phase and its runtime owner."""

    phase: str
    capability: str
    module: str
    symbol: str
    consumer: str

    def validate_owner(self) -> None:
        """Fail closed when the canonical implementation owner disappears."""
        if not hasattr(import_module(self.module), self.symbol):
            raise ValueError(f"Trading Intelligence owner is unavailable: {self.phase}")
        consumer_module, consumer_symbol = CONSUMER_OWNERS[self.phase]
        if not hasattr(import_module(consumer_module), consumer_symbol):
            raise ValueError(
                f"Trading Intelligence consumer is unavailable: {self.phase}"
            )


PHASES: tuple[TradingIntelligencePhase, ...] = (
    TradingIntelligencePhase(
        "P0",
        "Source/consumer/contract inventory",
        "ai4binance.intelligence.inventory",
        "TradingIntelligenceInventory",
        "quality and architecture checks",
    ),
    TradingIntelligencePhase(
        "P1",
        "Canonical MarketSnapshot and data quality",
        "ai4binance.schemas",
        "MarketSnapshot",
        "EnterpriseOrchestrator",
    ),
    TradingIntelligencePhase(
        "P2",
        "Canonical MTF market structure",
        "ai4binance.intelligence.structure",
        "MarketStructureEngine",
        "TradingIntelligenceEngine",
    ),
    TradingIntelligencePhase(
        "P3",
        "Structural levels and trend geometry",
        "ai4binance.intelligence.levels",
        "StructuralLevelMapEngine",
        "TradingIntelligenceEngine",
    ),
    TradingIntelligencePhase(
        "P4",
        "Classical patterns and price action",
        "ai4binance.intelligence.patterns",
        "PatternHypothesisFabric",
        "ScenarioEngine",
    ),
    TradingIntelligencePhase(
        "P5",
        "Fibonacci and harmonic confluence",
        "ai4binance.intelligence.patterns",
        "FibonacciConfluenceEngine",
        "PatternHypothesisFabric",
    ),
    TradingIntelligencePhase(
        "P6",
        "Elliott multi-hypothesis",
        "ai4binance.intelligence.patterns",
        "ElliottWaveHypothesisEngine",
        "PatternHypothesisFabric",
    ),
    TradingIntelligencePhase(
        "P7",
        "Futures derivatives context",
        "ai4binance.intelligence.derivatives",
        "FuturesContextEngine",
        "ScenarioEngine",
    ),
    TradingIntelligencePhase(
        "P8",
        "Scenario synthesis",
        "ai4binance.intelligence.trading",
        "ScenarioEngine",
        "EnterpriseOrchestrator",
    ),
    TradingIntelligencePhase(
        "P9",
        "Trade plan binding",
        "ai4binance.intelligence.plan",
        "TradePlanEngine",
        "ScenarioEngine",
    ),
    TradingIntelligencePhase(
        "P10",
        "Risk/reward calculation",
        "ai4binance.intelligence.plan",
        "RiskRewardEngine",
        "TradePlanEngine",
    ),
    TradingIntelligencePhase(
        "P11",
        "Futures leverage governance",
        "ai4binance.research.virtual_runtime_risk",
        "FuturesLeverageGovernor",
        "VirtualPortfolioRiskGovernor",
    ),
    TradingIntelligencePhase(
        "P12",
        "Walk-forward and OOS calibration",
        "ai4binance.validation.walk_forward",
        "WalkForwardValidator",
        "FuturesOosEvidenceReader",
    ),
    TradingIntelligencePhase(
        "P13",
        "Virtual Market acceptance",
        "ai4binance.research.virtual_runtime",
        "VirtualMarketRuntime",
        "application research",
    ),
    TradingIntelligencePhase(
        "P14",
        "Attribution and controlled learning evidence",
        "ai4binance.application.learning_loop",
        "ControlledLearningLoop",
        "application research",
    ),
)


CONSUMER_OWNERS: dict[str, tuple[str, str]] = {
    "P0": ("ai4binance.intelligence.inventory", "TradingIntelligenceInventory"),
    "P1": ("ai4binance.agents.orchestrator", "EnterpriseOrchestrator"),
    "P2": ("ai4binance.intelligence.trading", "ScenarioEngine"),
    "P3": ("ai4binance.intelligence.trading", "ScenarioEngine"),
    "P4": ("ai4binance.intelligence.trading", "ScenarioEngine"),
    "P5": ("ai4binance.intelligence.patterns", "PatternHypothesisFabric"),
    "P6": ("ai4binance.intelligence.patterns", "PatternHypothesisFabric"),
    "P7": ("ai4binance.intelligence.trading", "ScenarioEngine"),
    "P8": ("ai4binance.agents.orchestrator", "EnterpriseOrchestrator"),
    "P9": ("ai4binance.intelligence.trading", "ScenarioEngine"),
    "P10": ("ai4binance.intelligence.plan", "TradePlanEngine"),
    "P11": (
        "ai4binance.research.virtual_runtime_risk",
        "VirtualPortfolioRiskGovernor",
    ),
    "P12": ("ai4binance.validation.futures_oos", "FuturesOosEvidenceReader"),
    "P13": ("ai4binance.application.research", "ResearchApplicationService"),
    "P14": ("ai4binance.application.research", "ResearchApplicationService"),
}


@dataclass(frozen=True, slots=True)
class TradingIntelligenceInventory:
    """Validate the ordered phase chain and its concrete canonical owners."""

    phases: tuple[TradingIntelligencePhase, ...] = PHASES
    methods: tuple[AnalysisMethodCoverage, ...] = ANALYSIS_METHODS

    def validate(self) -> None:
        expected = tuple(f"P{index}" for index in range(15))
        if tuple(item.phase for item in self.phases) != expected:
            raise ValueError("Trading Intelligence phases must be complete and ordered")
        for phase in self.phases:
            phase.validate_owner()
        families = tuple(item.family for item in self.methods)
        if (
            len(set(families)) != len(families)
            or set(families) != REQUIRED_ANALYSIS_FAMILIES
        ):
            raise ValueError(
                "analysis method family inventory is incomplete or duplicated"
            )
        for method in self.methods:
            if not hasattr(import_module(method.module), method.owner):
                raise ValueError(
                    f"analysis method owner is unavailable: {method.family}"
                )
            if set(method.implemented) & set(method.missing):
                raise ValueError(
                    f"analysis method coverage is contradictory: {method.family}"
                )

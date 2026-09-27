"""Machine-checkable P0--P14 Trading Intelligence ownership inventory."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from ai4binance.intelligence.method_registry import (
    TradingMethodRegistry,
    current_method_registry,
)


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


def render_reference_manual(registry: TradingMethodRegistry | None = None) -> str:
    """Generate a deterministic projection of the canonical registry."""
    registry = registry or current_method_registry()
    lines = [
        "---",
        "title: Trading Intelligence Reference Manual",
        "source_of_truth: false",
        "content_role: GENERATED_PROJECTION",
        f"registry_version: {registry.version}",
        f"registry_sha256: {registry.snapshot_payload()['sha256']}",
        "promotion_status: RESEARCH_ONLY",
        "live_eligibility_status: LIVE_ORDER_BLOCKED",
        "---",
        "",
        "# Trading Intelligence Reference Manual",
        "",
        "Generated from docs/registries/registry_trading_intelligence.yaml. "
        "Do not edit this projection.",
        "",
        "Catalog membership is not implementation, source agreement is not OOS "
        "evidence, and confidence is not probability.",
        "",
        "News and sentiment are optional advisory context unless an explicit setup "
        "policy requires them. Critical event review vetoes scenario selection.",
        "",
        "Dependency groups retain shared-input and opposing evidence. "
        "Statistical independence is NOT_MEASURED.",
        "",
        "Target payoffs are conditional, with signed funding and explicit holding "
        "periods. Partial exits require explicit weights; leverage and sizing "
        "remain downstream risk decisions.",
        "",
    ]
    sources = {row.source_id: row for row in registry.sources}
    rules = {row.rule_id: row for row in registry.rules}
    for scope in registry.scope:
        lines.extend(
            (
                f"## {scope.family}",
                "",
                f"Scope status: {scope.status}. {scope.notes}",
                "",
            )
        )
        for key in scope.method_ids:
            method = registry.method(key)
            lines.extend(
                (
                    f"### {method.canonical_name}",
                    "",
                    f"Method: {method.method_id}@{method.version}; "
                    f"rules: {method.rule_set_version}.",
                    f"Implementation: {method.implementation_status}; "
                    f"OOS: {method.oos_status}.",
                    f"Owner: {method.module or 'NOT_IMPLEMENTED'} / "
                    f"{method.owner or 'NOT_IMPLEMENTED'}.",
                    f"Inputs: {', '.join(method.input_requirements)}.",
                    f"Limits: {method.limitations}",
                    "",
                )
            )
            for rule_id in method.rule_ids:
                rule = rules[rule_id]
                lines.extend(
                    (
                        f"- {rule.rule_id}@{rule.version}: {rule.statement}",
                        f"  Applicability: {rule.applicability}",
                        f"  Tolerances: {rule.tolerance_policy}",
                        f"  Ambiguity: {rule.ambiguity}",
                    )
                )
            lines.extend(
                (
                    "",
                    "Sources: "
                    + "; ".join(sources[key].locator for key in method.source_ids),
                    "",
                )
            )
    lines.extend(("## Dated source comparisons", ""))
    for review in registry.source_reviews:
        lines.extend(
            (
                f"- [{review.source_id}]({sources[review.source_id].locator}) "
                f"({review.reviewed_at.date()}): {review.finding} "
                f"{review.implementation_consequence}",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def write_reference_manual(directory: Path) -> Path:
    """Write a generated manual and pinned registry below repository runtime only."""
    from ai4binance.storage import write_json_object_verified

    runtime = Path(__file__).resolve().parents[3] / "runtime"
    target = directory.resolve()
    if not target.is_relative_to(runtime.resolve()):
        raise ValueError("generated reference artifacts must remain below runtime")
    target.mkdir(parents=True, exist_ok=True)
    registry = current_method_registry()
    manual = target / "reference_manual.md"
    content = render_reference_manual(registry)
    manual.write_text(content, encoding="utf-8")
    if manual.read_text(encoding="utf-8") != content:
        raise OSError("reference manual destination verification failed")
    write_json_object_verified(
        target / "method_registry_snapshot.json",
        registry.snapshot_payload(),
        blocker="METHOD_REGISTRY_SNAPSHOT_WRITE_FAILED",
        subject_id=f"trading-methods:{registry.version}",
        indent=2,
    )
    return manual


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate the trading reference projection."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    print(write_reference_manual(parser.parse_args().output_dir))

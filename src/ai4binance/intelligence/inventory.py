"""Machine-checkable P0--P14 Trading Intelligence ownership inventory."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from ai4binance.intelligence.method_registry import (
    MethodDefinition,
    MethodRuleStages,
    ReferenceChapter,
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
                    f"Validation: {method.validation_status}; "
                    f"governance: {method.governance_status}.",
                    f"Owner: {method.module or 'NOT_IMPLEMENTED'} / "
                    f"{method.owner or 'NOT_IMPLEMENTED'}.",
                    f"Lifecycle scope: {method.lifecycle_scope}; "
                    f"markets: {', '.join(method.markets)}.",
                    f"Inputs: {', '.join(method.input_requirements)}.",
                    f"Limits: {method.limitations}",
                    "",
                )
            )
            aliases = tuple(
                f"{alias.alias} ({alias.context})"
                for alias in registry.aliases
                if alias.method_id == method.method_id
            )
            lines.extend((f"Aliases: {'; '.join(aliases) or 'None registered'}.", ""))
            lines.extend(_method_reference_lines(method))
            lines.extend(_method_stage_lines(method))
            for rule_id in method.rule_ids:
                rule = rules[rule_id]
                lines.extend(
                    (
                        f"- {rule.rule_id}@{rule.version} [{rule.rule_type}]: "
                        f"{rule.statement}",
                        f"  Applicability: {rule.applicability}",
                        f"  Tolerances: {rule.tolerance_policy}",
                        f"  Ambiguity: {rule.ambiguity}",
                        f"  Sources: {', '.join(rule.source_ids)}; "
                        f"tests: {', '.join(rule.test_refs) or 'NOT_VERIFIED'}.",
                    )
                )
                if rule.semantics is not None:
                    lines.extend(
                        f"  {key.replace('_', ' ').title()}: {value}"
                        for key, value in rule.semantics.model_dump().items()
                    )
            lines.extend(
                (
                    "",
                    "Sources: "
                    + "; ".join(
                        f"[{key}]({sources[key].locator})" for key in method.source_ids
                    ),
                    "",
                )
            )
    lines.extend(_registry_reference_lines(registry))
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


def _method_reference_lines(method: MethodDefinition) -> list[str]:
    reference = method.reference
    if reference is None:
        return [
            "Detailed reference definition: NOT_VERIFIED. "
            "The registered implementation limits above remain authoritative "
            "for this catalog entry.",
            "",
        ]
    lines = [
        f"Definition: {reference.definition}",
        f"Purpose: {reference.purpose}",
        f"Origin / school: {reference.origin_or_school}",
        f"Standardization: {reference.standardization_status}",
        f"Market context: {'; '.join(reference.market_context)}",
        f"Direction semantics: {reference.direction_semantics}",
        f"Timeframe semantics: {reference.timeframe_semantics}",
        f"Known failure modes: {'; '.join(reference.known_failure_modes)}",
        f"Ambiguity: {reference.ambiguity_notes}",
        "",
    ]
    chapter = reference.chapter
    if reference.standardization_status == "NOT_VERIFIED":
        lines.append(
            "Detailed reference definition: NOT_VERIFIED. The description records "
            "research scope; it is not an admitted methodology specification."
        )
    for field in ReferenceChapter.model_fields:
        value = getattr(chapter, field) if chapter is not None else None
        lines.append(f"{field.replace('_', ' ').title()}: {value or 'NOT_VERIFIED'}")
    lines.extend(
        ("", "Missing reference fields: " + ", ".join(reference_gaps(method)), "")
    )
    return lines


def reference_gaps(method: MethodDefinition) -> tuple[str, ...]:
    """Expose descriptive completeness separately from implementation and OOS."""
    if method.reference is None:
        return ("reference",)
    chapter = method.reference.chapter
    missing = [
        key
        for key in ReferenceChapter.model_fields
        if chapter is None
        or getattr(chapter, key) is None
        or getattr(chapter, key).startswith("NOT_VERIFIED")
    ]
    if method.rule_stages is None or not any(method.rule_stages.model_dump().values()):
        missing.append("rule_stages")
    if method.reference.standardization_status == "NOT_VERIFIED":
        missing.append("standardization_status")
    if not method.source_ids:
        missing.append("source_ids")
    return tuple(missing)


def _method_stage_lines(method: MethodDefinition) -> list[str]:
    stages = method.rule_stages
    lines = ["Rule stages (references, not executable policy):"]
    for key in MethodRuleStages.model_fields:
        refs = getattr(stages, key) if stages is not None else ()
        lines.append(f"- {key.title()}: {', '.join(refs) or 'NOT_VERIFIED'}")
    return [*lines, ""]


def reference_acceptance_projection(
    registry: TradingMethodRegistry | None = None,
) -> dict[str, object]:
    """Project master sections 11--14 and D6 without granting acceptance authority."""
    registry = registry or current_method_registry()
    rules = {row.rule_id: row for row in registry.rules}
    methods = [
        {
            "method_id": method.method_id,
            "master_requirements": ["11", "12", "13", "14", "D6"],
            "implementation_status": method.implementation_status,
            "owner": method.module,
            "symbol": method.owner,
            "source_ids": list(method.source_ids),
            "test_refs": sorted(
                {ref for key in method.rule_ids for ref in rules[key].test_refs}
            ),
            "missing_reference_fields": list(reference_gaps(method)),
            "validation_status": method.validation_status,
            "oos_status": method.oos_status,
            "implementation_limits": method.limitations,
        }
        for method in registry.methods
    ]
    return {
        "source_of_truth": False,
        "registry_version": registry.version,
        "registry_sha256": registry.snapshot_payload()["sha256"],
        "status": "PARTIALLY_VERIFIED",
        "methods": methods,
        "scope": (
            "Descriptive reference coverage only; "
            "not the complete master acceptance decision."
        ),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _registry_reference_lines(registry: TradingMethodRegistry) -> list[str]:
    lines = ["## Method interactions", ""]
    for edge in registry.interactions:
        lines.append(
            f"- {edge.left} / {edge.right}: {edge.relationship}; "
            f"statistical independence: {edge.independence_status}."
        )
    lines.extend(("", "## Implementation coverage and research gaps", ""))
    for coverage in registry.coverage:
        lines.extend(
            (
                f"- {coverage.family}: {coverage.decision_role}",
                f"  Implemented scope: {'; '.join(coverage.implemented)}.",
                f"  Missing scope: {'; '.join(coverage.missing) or 'None registered'}.",
                f"  Limits: {coverage.limitations}",
            )
        )
    lines.extend(("", "## Source provenance", ""))
    for source in registry.sources:
        lines.extend(
            (
                f"### {source.source_id}",
                "",
                f"Reference: [{source.source_id}]({source.locator})",
                f"Verification: {source.verification}; "
                f"revision: {source.revision or 'NOT_VERIFIED'}; "
                f"content SHA-256: {source.content_sha256 or 'NOT_ARCHIVED'}.",
                f"Limits: {source.notes}",
            )
        )
        bibliography = source.bibliography
        if bibliography is not None:
            lines.extend(
                (
                    f"Title: {bibliography.title}",
                    f"Organization: {bibliography.organization}; "
                    f"author: {bibliography.author or 'NOT_VERIFIED'}.",
                    f"Source family: {bibliography.source_family}; "
                    f"classification: {bibliography.primary_or_secondary}.",
                    "Publication date: "
                    f"{bibliography.publication_date or 'NOT_VERIFIED'}; "
                    f"version: {bibliography.source_version or 'NOT_VERIFIED'}.",
                    f"Accessed: {bibliography.accessed_at.isoformat()}",
                    f"Licensing: {bibliography.licensing_notes}",
                    f"Source conflicts: {bibliography.conflict_notes}",
                )
            )
        lines.append("")
    return lines


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
    write_json_object_verified(
        target / "reference_acceptance.json",
        reference_acceptance_projection(registry),
        blocker="REFERENCE_ACCEPTANCE_WRITE_FAILED",
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

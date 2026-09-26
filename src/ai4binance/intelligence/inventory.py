"""Machine-checkable P0--P14 Trading Intelligence ownership inventory."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


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


_CME = "https://www.cmegroup.com/education/courses/technical-analysis/"
_REVERSALS = _CME + "technical-patterns-reversals"
_CONTINUATION = _CME + "trend-and-continuation-patterns"
_LEVELS = _CME + "support-and-resistance"
_FIBONACCI = _CME + "fibonacci-retracements-and-extensions"
_HARMONICS = "https://harmonictrader.com/harmonic-patterns/"
_ELLIOTT = "https://www.elliottwave.com/waveopedia/"

# This registry describes observed code. Missing variants are backlog items,
# never aliases for implemented detectors or permission to generate a trade.
ANALYSIS_METHODS: tuple[AnalysisMethodCoverage, ...] = (
    AnalysisMethodCoverage(
        "pattern_lifecycle",
        "ai4binance.opportunity_intelligence",
        "OpportunityLifecycleLedger",
        ("forming", "potential", "confirmed", "failed", "invalidated", "expired"),
        (),
        "STATE_AND_CONFIRMATION_GATE",
        "Lifecycle implementation does not establish per-pattern profitability.",
        ("tests/test_opportunity_intelligence.py",),
        (_REVERSALS, _CONTINUATION),
    ),
    AnalysisMethodCoverage(
        "trend_geometry",
        "ai4binance.intelligence.trend",
        "TrendGeometryEngine",
        (
            "confirmed_pivot_lines",
            "projected_channels",
            "break_retest",
            "compression",
            "acceleration",
        ),
        ("robust_regression_channel",),
        "STRUCTURAL_CONTEXT_AND_ENTRY_QUALIFICATION",
        "Fallback endpoint geometry is not a confirmed-pivot entry qualification.",
        ("tests/test_trading_intelligence.py", "tests/test_structural_entries.py"),
        (_LEVELS,),
    ),
    AnalysisMethodCoverage(
        "market_structure",
        "ai4binance.intelligence.structure",
        "MarketStructureEngine",
        (
            "confirmed_swings",
            "higher_high_lower_low_sequence",
            "break_of_structure",
            "change_of_character",
        ),
        (),
        "DIRECTION_AND_INVALIDATION",
        "Pivot confirmation requires right-hand closed bars; "
        "observation time differs from pivot time.",
        ("tests/test_trading_intelligence.py", "tests/test_structural_entries.py"),
        (_LEVELS,),
    ),
    AnalysisMethodCoverage(
        "chart_patterns",
        "ai4binance.opportunity_intelligence",
        "detect_chart_pattern",
        (
            "double_top",
            "double_bottom",
            "head_and_shoulders",
            "inverse_head_and_shoulders",
            "rising_wedge",
            "falling_wedge",
            "converging_triangle",
        ),
        (
            "ascending_triangle",
            "descending_triangle",
            "rectangle",
            "flag",
            "pennant",
            "triple_top",
            "triple_bottom",
        ),
        "LIFECYCLE_BOUND_PATTERN_HYPOTHESIS",
        "Generic convergence does not implement every named continuation variant.",
        ("tests/test_opportunity_intelligence.py", "tests/test_structural_entries.py"),
        (_REVERSALS, _CONTINUATION),
    ),
    AnalysisMethodCoverage(
        "trendline_flowing",
        "ai4binance.intelligence.trend",
        "TrendGeometryEngine",
        ("closed_bar_trendline_projection", "trendline_break_retest"),
        (),
        "DYNAMIC_TRENDLINE_CONTEXT",
        "User terminology maps to existing dynamic trendline projection, "
        "not a separate standardized detector.",
        ("tests/test_structural_entries.py",),
        (_LEVELS,),
    ),
    AnalysisMethodCoverage(
        "elliott_waves",
        "ai4binance.intelligence.patterns",
        "ElliottWaveHypothesisEngine",
        (
            "six_pivot_impulse_candidate",
            "wave_two_origin_rule",
            "wave_three_length_rule",
            "wave_four_overlap_rule",
        ),
        (
            "multi_degree_alternative_counts",
            "zigzag",
            "flat",
            "corrective_triangle",
            "diagonal",
            "double_three",
            "triple_three",
        ),
        "UNRESOLVED_ALTERNATIVE_CONTEXT_ONLY",
        "One observed count; wave degree and correction remain unresolved. "
        "No standalone entry authority.",
        ("tests/test_trading_intelligence.py", "tests/test_advanced_agents.py"),
        (_ELLIOTT + "impulse/", _ELLIOTT + "corrective-waves/"),
    ),
    AnalysisMethodCoverage(
        "fibonacci",
        "ai4binance.intelligence.patterns",
        "FibonacciConfluenceEngine",
        (
            "retracement_0.382",
            "retracement_0.5",
            "retracement_0.618",
            "extension_1.272",
            "extension_1.618",
        ),
        ("retracement_0.236", "retracement_0.786", "multi_anchor_cluster_validation"),
        "CONTEXT_ONLY",
        "Confirmed swing anchors; 0.5 is a conventional midpoint. "
        "Confluence does not authorize an entry.",
        ("tests/test_trading_intelligence.py", "tests/test_advanced_agents.py"),
        (_FIBONACCI,),
    ),
    AnalysisMethodCoverage(
        "harmonic_patterns",
        "ai4binance.intelligence.patterns",
        "HarmonicPatternEngine",
        ("gartley", "bat"),
        (
            "ab_cd",
            "alternate_ab_cd",
            "alternate_bat",
            "butterfly",
            "crab",
            "deep_crab",
            "shark",
            "five_zero",
        ),
        "POTENTIAL_REVERSAL_ZONE_CONTEXT",
        "Last five confirmed alternating pivots only; "
        "ratio match is not a confirmed reversal trigger.",
        ("tests/test_trading_intelligence.py", "tests/test_advanced_agents.py"),
        (_HARMONICS,),
    ),
    AnalysisMethodCoverage(
        "support_resistance",
        "ai4binance.intelligence.levels",
        "StructuralLevelMapEngine",
        ("swing_zones", "zone_age", "role_flip", "opposing_level_targets"),
        (),
        "STRUCTURAL_STOP_AND_TARGET_SOURCES",
        "Price zones are estimated from the available closed-bar structure.",
        ("tests/test_trading_intelligence.py", "tests/test_structural_entries.py"),
        (_LEVELS,),
    ),
    AnalysisMethodCoverage(
        "formations",
        "ai4binance.opportunity_intelligence",
        "analyze_candlestick",
        (
            "rejection",
            "strong_continuation",
            "inside_bar",
            "outside_bar",
            "bullish_engulfing",
            "bearish_engulfing",
            "indecision",
            "range_expansion",
            "range_contraction",
            "extended",
        ),
        (),
        "CANDLE_GEOMETRY_CONFIRMATION",
        "Umbrella alias also references chart_patterns; no duplicate detector "
        "or exhaustive candlestick catalog claim.",
        ("tests/test_opportunity_intelligence.py",),
        (_REVERSALS,),
    ),
    AnalysisMethodCoverage(
        "chart_analysis",
        "ai4binance.intelligence.trading",
        "ScenarioEngine",
        (
            "multi_timeframe_scenario_synthesis",
            "evidence_lineage",
            "structural_trade_plan",
        ),
        (),
        "DETERMINISTIC_SCENARIO_SYNTHESIS",
        "Risk, validation and governance retain veto authority. "
        "Price/OI backtests are a separate component.",
        ("tests/test_trading_intelligence.py", "tests/test_structural_entries.py"),
        (_LEVELS, _CONTINUATION),
    ),
)

REQUIRED_ANALYSIS_FAMILIES = frozenset(
    {
        "pattern_lifecycle",
        "trend_geometry",
        "market_structure",
        "chart_patterns",
        "trendline_flowing",
        "elliott_waves",
        "fibonacci",
        "harmonic_patterns",
        "support_resistance",
        "formations",
        "chart_analysis",
    }
)


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

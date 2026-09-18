"""Default governed catalog for platform definitions and analytical capabilities."""

from ai4binance.agents.registry import (
    AgentDefinition,
    AgentRegistry,
    AgentStage,
    CapabilityActivationPolicy,
    CapabilityBundleDefinition,
    CapabilityBundleRegistry,
    CapabilityDefinition,
    CapabilityExecutionClass,
    CapabilityRegistry,
)

ALL_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
ALL_REGIMES = ("ALL",)
DEFAULT_OOS = ("walk_forward", "multi_regime_oos", "false_positive_review")


def _definition(
    name: str,
    family: str,
    stage: AgentStage,
    *,
    dependencies: tuple[str, ...] = (),
    required_data: tuple[str, ...] = ("ohlcv",),
    timeframes: tuple[str, ...] = ALL_TIMEFRAMES,
    cluster: str = "diagnostic",
    false_positive_risk: tuple[str, ...] = ("unvalidated_method",),
    expensive: bool = False,
) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        family=family,
        version="0.1.0",
        stage=stage,
        required_data=required_data,
        supported_timeframes=timeframes,
        compatible_regimes=ALL_REGIMES,
        false_positive_risk=false_positive_risk,
        oos_requirements=DEFAULT_OOS,
        dependencies=dependencies,
        evidence_cluster=cluster,
        expensive=expensive,
    )


ELIGIBILITY_DEPENDENCIES = ("data_quality", "universe_liquidity")

"""Logical analytical capabilities represented by legacy-compatible definitions."""

ANALYSIS_DEFINITIONS: tuple[AgentDefinition, ...] = (
    _definition(
        "multi_timeframe",
        "market_intelligence",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="mtf",
    ),
    _definition(
        "market_regime",
        "market_intelligence",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="regime",
    ),
    _definition(
        "market_structure",
        "structure",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="structure",
        false_positive_risk=("provisional_swing", "chop"),
    ),
    _definition(
        "support_resistance",
        "location",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="location",
        false_positive_risk=("overfit_levels",),
    ),
    _definition(
        "trend",
        "trend",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="trend",
        false_positive_risk=("chop", "late_reversal"),
    ),
    _definition(
        "trend_events",
        "trend",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="trend",
        false_positive_risk=("lag", "chop", "unconfirmed_transition"),
    ),
    _definition(
        "trend_channel",
        "trend",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="trend",
        false_positive_risk=("forced_anchors",),
    ),
    _definition(
        "price_action",
        "trigger",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        timeframes=("15m", "1h"),
        cluster="trigger",
        false_positive_risk=("single_candle_noise",),
    ),
    _definition(
        "candlestick",
        "trigger",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "support_resistance"),
        timeframes=("15m", "1h"),
        cluster="trigger",
        false_positive_risk=("context_free_pattern",),
    ),
    _definition(
        "chart_pattern",
        "pattern",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "market_structure"),
        cluster="pattern",
        false_positive_risk=("curve_fit", "subjective_geometry"),
        expensive=True,
    ),
    _definition(
        "fibonacci",
        "location",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "market_structure"),
        timeframes=("4h", "1d"),
        cluster="location",
        false_positive_risk=("forced_anchors",),
    ),
    _definition(
        "harmonic_pattern",
        "pattern",
        AgentStage.ANALYSIS,
        dependencies=(
            "data_quality",
            "universe_liquidity",
            "market_structure",
            "fibonacci",
        ),
        cluster="pattern",
        false_positive_risk=("ratio_curve_fit",),
        expensive=True,
    ),
    _definition(
        "elliott_wave",
        "pattern",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "market_structure"),
        cluster="pattern",
        false_positive_risk=("subjective_count",),
        expensive=True,
    ),
    _definition(
        "momentum",
        "momentum",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="momentum",
        false_positive_risk=("premature_reversal",),
    ),
    _definition(
        "divergence",
        "momentum",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "momentum"),
        cluster="momentum",
        false_positive_risk=("invalid_pivots",),
    ),
    _definition(
        "moving_average",
        "trend",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="trend",
        false_positive_risk=("lag", "correlated_evidence"),
    ),
    _definition(
        "ichimoku",
        "trend",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="trend",
        false_positive_risk=("lag", "parameter_sensitivity"),
    ),
    _definition(
        "volatility",
        "volatility",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="volatility",
        false_positive_risk=("breakout_block", "noise"),
    ),
    _definition(
        "volume",
        "participation",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="participation",
        false_positive_risk=("illiquid_spike",),
    ),
    _definition(
        "volume_profile",
        "location",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "volume"),
        cluster="location",
        false_positive_risk=("bin_sensitivity",),
    ),
    _definition(
        "order_flow",
        "liquidity",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("order_book",),
        timeframes=("15m",),
        cluster="liquidity",
        false_positive_risk=("transient_depth",),
    ),
    _definition(
        "liquidity_analysis",
        "liquidity",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("order_book", "ohlcv"),
        cluster="liquidity",
        false_positive_risk=("spoofing",),
    ),
    _definition(
        "smc",
        "structure",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "market_structure"),
        cluster="structure",
        false_positive_risk=("subjective_labeling",),
    ),
    _definition(
        "wyckoff",
        "cycle",
        AgentStage.ANALYSIS,
        dependencies=(
            "data_quality",
            "universe_liquidity",
            "market_structure",
            "volume",
        ),
        cluster="cycle",
        false_positive_risk=("subjective_phase",),
    ),
    _definition(
        "breakout_retest",
        "trigger",
        AgentStage.ANALYSIS,
        dependencies=(
            "data_quality",
            "universe_liquidity",
            "support_resistance",
            "volume",
        ),
        cluster="trigger",
        false_positive_risk=("false_breakout",),
    ),
    _definition(
        "mean_reversion",
        "strategy",
        AgentStage.ANALYSIS,
        dependencies=(
            "data_quality",
            "universe_liquidity",
            "market_regime",
            "volatility",
        ),
        cluster="strategy",
        false_positive_risk=("trend_continuation",),
    ),
    _definition(
        "statistics",
        "quantitative",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        cluster="statistics",
        false_positive_risk=("data_snooping",),
    ),
    _definition(
        "correlation",
        "intermarket",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("ohlcv", "benchmark_data"),
        cluster="market_intelligence",
        false_positive_risk=("unstable_correlation",),
    ),
    _definition(
        "sentiment",
        "market_intelligence",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("sentiment_snapshot",),
        cluster="market_intelligence",
        false_positive_risk=("source_bias",),
    ),
    _definition(
        "news",
        "market_intelligence",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("news_snapshot",),
        cluster="market_intelligence",
        false_positive_risk=("stale_news", "source_quality"),
    ),
    _definition(
        "derivatives",
        "supplementary",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("derivatives_snapshot",),
        cluster="market_intelligence",
        false_positive_risk=("spot_mismatch",),
    ),
    _definition(
        "long_short",
        "supplementary",
        AgentStage.ANALYSIS,
        dependencies=("data_quality", "universe_liquidity", "derivatives"),
        required_data=("derivatives_snapshot",),
        cluster="market_intelligence",
        false_positive_risk=("crowding_noise",),
    ),
    _definition(
        "whale",
        "supplementary",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("onchain_snapshot",),
        cluster="market_intelligence",
        false_positive_risk=("address_attribution",),
    ),
    _definition(
        "onchain",
        "supplementary",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("onchain_snapshot",),
        cluster="market_intelligence",
        false_positive_risk=("chain_exchange_mismatch",),
    ),
)


PLATFORM_DEFINITIONS: tuple[AgentDefinition, ...] = (
    _definition(
        "data_acquisition",
        "data",
        AgentStage.ACQUISITION,
        required_data=("exchange_adapter",),
        cluster="data",
    ),
    _definition(
        "data_quality",
        "data",
        AgentStage.ELIGIBILITY,
        required_data=("market_snapshot",),
        cluster="data_quality",
    ),
    _definition(
        "universe_liquidity",
        "eligibility",
        AgentStage.ELIGIBILITY,
        dependencies=("data_quality",),
        required_data=("ticker", "exchange_filters"),
        cluster="liquidity",
    ),
    *ANALYSIS_DEFINITIONS,
    _definition(
        "memory_advisory",
        "memory",
        AgentStage.ANALYSIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("compiled_cycle_context", "memory_advisory_evidence"),
        cluster="historical_memory",
        false_positive_risk=("historical_bias", "stale_memory"),
    ),
    _definition(
        "confluence",
        "synthesis",
        AgentStage.SYNTHESIS,
        dependencies=ELIGIBILITY_DEPENDENCIES,
        required_data=("agent_results",),
        cluster="confluence",
    ),
    _definition(
        "risk",
        "risk",
        AgentStage.RISK,
        dependencies=("confluence",),
        required_data=("trade_candidate",),
        cluster="risk",
    ),
    _definition(
        "trailing_stop",
        "risk",
        AgentStage.RISK,
        dependencies=("risk",),
        required_data=("position", "atr"),
        cluster="risk",
    ),
    _definition(
        "wallet_inventory",
        "portfolio",
        AgentStage.RISK,
        dependencies=("data_quality",),
        required_data=("authorized_wallet",),
        cluster="risk",
    ),
    _definition(
        "validation",
        "validation",
        AgentStage.VALIDATION,
        dependencies=("confluence", "risk"),
        required_data=("agent_results", "risk_result"),
        cluster="validation",
    ),
    _definition(
        "execution",
        "execution",
        AgentStage.EXECUTION,
        dependencies=("validation", "risk", "wallet_inventory"),
        required_data=("validated_order", "live_gates"),
        cluster="execution",
    ),
    _definition(
        "backtest",
        "research",
        AgentStage.RESEARCH,
        required_data=("historical_ohlcv",),
        cluster="validation",
    ),
    _definition(
        "walk_forward",
        "research",
        AgentStage.RESEARCH,
        dependencies=("backtest",),
        required_data=("backtest_results",),
        cluster="validation",
    ),
    _definition(
        "optimization",
        "research",
        AgentStage.RESEARCH,
        dependencies=("walk_forward",),
        required_data=("versioned_parameters",),
        cluster="validation",
    ),
    _definition(
        "learning",
        "learning",
        AgentStage.LEARNING,
        dependencies=("validation",),
        required_data=("lifecycle_records",),
        cluster="learning",
    ),
    _definition(
        "qaqc_agent",
        "governance",
        AgentStage.LEARNING,
        dependencies=("validation", "learning"),
        required_data=(
            "quality_gate_report",
            "validation_artifacts",
            "run_cards",
            "blocker_dashboard",
        ),
        cluster="governance",
        false_positive_risk=("process_theater", "cosmetic_cleanup"),
    ),
)

ORCHESTRATED_SPECIALIST_NAMES = tuple(item.name for item in ANALYSIS_DEFINITIONS)


def _capability_definition(definition: AgentDefinition) -> CapabilityDefinition:
    """Project one analytical catalog item into its runtime-neutral contract."""
    return CapabilityDefinition(
        capability_id=definition.name,
        version=definition.version,
        family=definition.family,
        dependencies=definition.dependencies,
        required_data=definition.required_data,
        timeframes=definition.supported_timeframes,
        compatible_regimes=definition.compatible_regimes,
        cluster=definition.evidence_cluster,
        expensive=definition.expensive,
        runtime_eligible=True,
        execution_class=CapabilityExecutionClass.DETERMINISTIC_THREAD_POOL,
        activation_policy=CapabilityActivationPolicy.ALWAYS_SCHEDULED,
        promotion_status=definition.promotion_status,
    )


CAPABILITY_DEFINITIONS: tuple[CapabilityDefinition, ...] = tuple(
    _capability_definition(definition) for definition in ANALYSIS_DEFINITIONS
)

CAPABILITY_BUNDLE_DEFINITIONS: tuple[CapabilityBundleDefinition, ...] = (
    CapabilityBundleDefinition(
        "market_state",
        (
            "multi_timeframe",
            "market_regime",
            "trend",
            "trend_events",
            "trend_channel",
            "moving_average",
            "ichimoku",
            "volatility",
        ),
    ),
    CapabilityBundleDefinition(
        "structure_location",
        (
            "market_structure",
            "support_resistance",
            "fibonacci",
            "smc",
            "volume_profile",
        ),
    ),
    CapabilityBundleDefinition(
        "momentum_participation",
        ("momentum", "divergence", "volume", "statistics"),
    ),
    CapabilityBundleDefinition(
        "liquidity_flow",
        ("order_flow", "liquidity_analysis", "price_action", "candlestick"),
    ),
    CapabilityBundleDefinition(
        "cross_market_derivatives",
        ("correlation", "derivatives", "long_short"),
    ),
    CapabilityBundleDefinition(
        "setup_event",
        (
            "chart_pattern",
            "harmonic_pattern",
            "elliott_wave",
            "wyckoff",
            "breakout_retest",
            "mean_reversion",
            "sentiment",
            "news",
            "whale",
            "onchain",
        ),
    ),
)

EXTERNAL_CAPABILITY_DEPENDENCY_IDS = tuple(
    dependency
    for definition in CAPABILITY_DEFINITIONS
    for dependency in definition.dependencies
    if dependency not in {item.capability_id for item in CAPABILITY_DEFINITIONS}
)


def build_default_registry() -> AgentRegistry:
    """Return the complete immutable Custom Instructions agent catalog."""
    return AgentRegistry(PLATFORM_DEFINITIONS)


def build_default_capability_registry() -> CapabilityRegistry:
    """Return the immutable contract registry for analytical capabilities."""
    return CapabilityRegistry(
        CAPABILITY_DEFINITIONS,
        external_dependency_ids=tuple(
            dict.fromkeys(EXTERNAL_CAPABILITY_DEPENDENCY_IDS)
        ),
    )


def build_default_capability_bundle_registry() -> CapabilityBundleRegistry:
    """Return the exact six-bundle runtime-planning projection."""
    return CapabilityBundleRegistry(
        CAPABILITY_BUNDLE_DEFINITIONS,
        build_default_capability_registry(),
    )

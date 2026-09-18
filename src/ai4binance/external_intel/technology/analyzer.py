"""Rule-first technology classification with no model dependency."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.external_intel.core.enums import TechnologyRecommendation
from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.models import (
    RetrievedDocument,
    TechnologyCandidate,
)


@dataclass(frozen=True, slots=True)
class _TechnologyRule:
    area: str
    keywords: tuple[str, ...]
    components: tuple[str, ...]
    required_validation: tuple[str, ...] = ()
    implementation_risk: float = 0.5
    license_risk: float = 0.5
    security_risk: float = 0.2


_COMMON_REQUIRED_VALIDATION = (
    "SANDBOX_IMPLEMENTATION",
    "UNIT_TESTS",
    "BACKTEST_WHEN_TRADING_RELEVANT",
    "WALK_FORWARD_WHEN_TRADING_RELEVANT",
    "OOS_VALIDATION_WHEN_TRADING_RELEVANT",
)


_RULES = (
    _TechnologyRule(
        "application-security",
        (
            "security",
            "vulnerability",
            "cve",
            "hardening",
            "supply chain",
            "prompt injection",
            "sbom",
            "secrets",
            "zero trust",
        ),
        ("SecurityAssurance", "ExternalIntelligence", "ValidationPipeline"),
        (
            "THREAT_MODEL",
            "STATIC_SECURITY_REVIEW",
            "SECRET_LEAK_REVIEW",
        ),
        security_risk=0.4,
    ),
    _TechnologyRule(
        "agent-architecture",
        (
            "agent",
            "agent architecture",
            "multi-agent",
            "orchestration",
            "rag",
            "retrieval",
            "context engineering",
            "guardrail",
            "handoff",
            "tool use",
        ),
        ("AgentOrchestrator", "RAGLayer", "AdvisoryLLM"),
        (
            "TYPED_STATE_CONTRACT",
            "LEAST_PRIVILEGE_TOOL_REVIEW",
            "DETERMINISTIC_MERGE_ORDER",
            "HUMAN_APPROVAL_GATE_REVIEW",
        ),
        implementation_risk=0.6,
    ),
    _TechnologyRule(
        "backtest-validation",
        (
            "backtest",
            "walk-forward",
            "out-of-sample",
            "oos",
            "benchmark",
            "simulation",
            "time series split",
            "lookahead",
            "slippage",
        ),
        ("BacktestEngine", "ValidationPipeline", "AutoMLGovernance"),
        (
            "LEAKAGE_REVIEW",
            "TRANSACTION_COST_MODEL",
            "REGIME_SPLIT_REVIEW",
        ),
    ),
    _TechnologyRule(
        "market-microstructure",
        (
            "order flow",
            "microstructure",
            "execution",
            "execution method",
            "liquidity",
            "spread",
            "order book",
            "slippage",
        ),
        ("MarketStructureAgent", "RiskEngine", "BacktestEngine"),
        (
            "LIQUIDITY_MODEL_REVIEW",
            "FILL_ASSUMPTION_REVIEW",
            "NO_LIVE_EXECUTION_AUTHORITY",
        ),
        implementation_risk=0.6,
    ),
    _TechnologyRule(
        "data-engineering",
        (
            "data source",
            "new data",
            "dataset",
            "streaming",
            "event-driven",
            "data quality",
            "schema",
            "lineage",
            "provenance",
            "freshness",
        ),
        ("DataQualityAgent", "EventBus", "EvidenceFabric"),
        (
            "SOURCE_PROVENANCE_REVIEW",
            "FRESHNESS_CONTRACT",
            "SCHEMA_VALIDATION",
        ),
    ),
    _TechnologyRule(
        "protocol-exchange-api",
        (
            "protocol",
            "api",
            "websocket",
            "sbe",
            "fix",
            "endpoint",
            "market data stream",
            "binance api",
            "mcp",
        ),
        ("ExchangeGateway", "ExternalIntelligence", "EventBus"),
        (
            "OFFICIAL_DOCUMENTATION_REVIEW",
            "RATE_LIMIT_REVIEW",
            "IDEMPOTENCY_REVIEW",
            "AUTHORIZATION_BOUNDARY_REVIEW",
        ),
        implementation_risk=0.6,
        security_risk=0.35,
    ),
    _TechnologyRule(
        "model-method-optimization",
        (
            "model",
            "llm",
            "embedding",
            "fine-tuning",
            "optimizer",
            "optimization",
            "bayesian",
            "automl",
            "hyperparameter",
            "reinforcement learning",
        ),
        ("AdvisoryLLM", "AutoMLGovernance", "ValidationPipeline"),
        (
            "MODEL_CARD_REVIEW",
            "DETERMINISM_OR_SEED_REVIEW",
            "MULTIPLE_TESTING_REVIEW",
            "PERFORMANCE_BASELINE_REVIEW",
        ),
        implementation_risk=0.6,
    ),
    _TechnologyRule(
        "strategy-signal-research",
        (
            "strategy",
            "indicator",
            "pattern",
            "alpha",
            "signal",
            "factor",
            "regime",
            "momentum",
            "mean reversion",
            "breakout",
        ),
        ("StrategyResearch", "FeatureEngineering", "ValidationPipeline"),
        (
            "HYPOTHESIS_REGISTER",
            "LEAKAGE_REVIEW",
            "OOS_VALIDATION_REQUIRED",
            "NO_TRADE_SIGNAL_AUTHORITY",
        ),
        implementation_risk=0.7,
    ),
    _TechnologyRule(
        "risk-control",
        (
            "risk control",
            "risk management",
            "position sizing",
            "drawdown",
            "exposure",
            "kill switch",
            "circuit breaker",
            "liquidity risk",
            "correlation",
        ),
        ("RiskEngine", "DecisionGovernanceEngine", "ValidationPipeline"),
        (
            "FAIL_CLOSED_STATE_TESTS",
            "LIMIT_INVARIANT_TESTS",
            "HUMAN_APPROVAL_GATE_REVIEW",
        ),
        implementation_risk=0.4,
        security_risk=0.25,
    ),
    _TechnologyRule(
        "blockchain-feature",
        (
            "blockchain",
            "on-chain",
            "onchain",
            "wallet",
            "mempool",
            "bridge",
            "staking",
            "smart contract",
            "tokenomics",
        ),
        ("OnChainIntelligence", "ExternalIntelligence", "RiskEngine"),
        (
            "SOURCE_PROVENANCE_REVIEW",
            "WALLET_PRIVACY_BOUNDARY_REVIEW",
            "CHAIN_REORG_OR_FINALITY_REVIEW",
        ),
        implementation_risk=0.7,
        security_risk=0.45,
    ),
    _TechnologyRule(
        "ontology-knowledge-graph",
        (
            "ontology",
            "knowledge graph",
            "graph rag",
            "semantic",
            "entity resolution",
            "evidence graph",
            "relationship extraction",
        ),
        ("Ontology", "EvidenceFabric", "RAGLayer"),
        (
            "SOURCE_OF_TRUTH_REVIEW",
            "ENTITY_RELATIONSHIP_CONTRACT_REVIEW",
            "PROVENANCE_GRAPH_REVIEW",
        ),
    ),
    _TechnologyRule(
        "workflow-orchestrator-pipeline",
        (
            "workflow",
            "orchestrator",
            "pipeline",
            "durable execution",
            "scheduler",
            "state machine",
            "dag",
            "loop",
            "autonomous",
        ),
        ("WorkflowRuntime", "EventBus", "ContinuousAssurance"),
        (
            "BOUNDED_CONCURRENCY_REVIEW",
            "RETRY_BUDGET_REVIEW",
            "DEGRADED_STATE_REVIEW",
            "AUDIT_TRACE_REVIEW",
        ),
        implementation_risk=0.6,
    ),
)


def analyze_technology(
    document: RetrievedDocument,
    *,
    evidence_id: str,
    source_reliability: float,
) -> TechnologyCandidate | None:
    text = " ".join(
        (document.title, document.text_excerpt, *document.headings)
    ).casefold()
    matches = tuple(
        (rule, sum(keyword in text for keyword in rule.keywords)) for rule in _RULES
    )
    rule, hit_count = max(matches, key=lambda item: (item[1], item[0].area))
    if hit_count == 0:
        return None
    relevance = min(1.0, 0.35 + hit_count * 0.13)
    confidence = min(source_reliability, 0.4 + hit_count * 0.1)
    recommendation = (
        TechnologyRecommendation.RESEARCH_CANDIDATE
        if confidence >= 0.7 and hit_count >= 2
        else TechnologyRecommendation.WATCH
    )
    return TechnologyCandidate(
        candidate_id=eief_id("webtech", document.document_id, rule.area),
        technology_area=rule.area,
        title=document.title,
        recommendation=recommendation,
        evidence_ids=(evidence_id,),
        relevance_to_ai4binance=relevance,
        architecture_fit=relevance,
        implementation_risk=rule.implementation_risk,
        license_risk=rule.license_risk,
        security_risk=rule.security_risk,
        confidence=confidence,
        affected_components=rule.components,
        required_validation=tuple(
            dict.fromkeys((*rule.required_validation, *_COMMON_REQUIRED_VALIDATION))
        ),
        blockers=(
            "HUMAN_REVIEW_REQUIRED",
            "NO_INSTALL_AUTHORITY",
            "NO_TRADE_SIGNAL_AUTHORITY",
            "LIVE_ORDER_BLOCKED",
        ),
    )

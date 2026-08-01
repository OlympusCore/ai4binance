"""Default MultiOps registry for AI4BINANCE control-plane checks."""

from __future__ import annotations

from ai4binance.multiops.contracts import (
    MultiOpsRegistry,
    OpsCapability,
    OpsDomain,
    OpsDomainDefinition,
)

DEFAULT_MULTI_OPS_DOMAINS: tuple[OpsDomainDefinition, ...] = (
    OpsDomainDefinition(
        OpsDomain.AIOPS,
        "AIOps",
        "Observe system health, incidents, alert correlation, and safe runbooks.",
        (
            OpsCapability.HEALTH,
            OpsCapability.INCIDENT,
            OpsCapability.ALERT_CORRELATION,
            OpsCapability.SAFE_RUNBOOKS,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.MLOPS,
        "MLOps",
        "Govern datasets, features, models, drift, and promotion evidence.",
        (
            OpsCapability.DATASET_REGISTRY,
            OpsCapability.FEATURE_REGISTRY,
            OpsCapability.MODEL_REGISTRY,
            OpsCapability.DRIFT,
            OpsCapability.PROMOTION,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.LLMOPS,
        "LLMOps",
        "Control prompt registries, model routing, evals, grounding, and budgets.",
        (
            OpsCapability.PROMPT_REGISTRY,
            OpsCapability.MODEL_ROUTING,
            OpsCapability.EVAL,
            OpsCapability.GROUNDING,
            OpsCapability.TOKEN_LATENCY,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.RAGOPS,
        "RAGOps",
        "Track corpus versions, chunking, embeddings, retrieval, and lineage.",
        (
            OpsCapability.CORPUS_VERSION,
            OpsCapability.CHUNKING,
            OpsCapability.EMBEDDING,
            OpsCapability.RETRIEVAL_QUALITY,
            OpsCapability.SOURCE_LINEAGE,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.AGENTOPS,
        "AgentOps",
        "Govern agent registry, role drift, loop budget, tools, and retirement.",
        (
            OpsCapability.AGENT_REGISTRY,
            OpsCapability.ROLE_DRIFT,
            OpsCapability.LOOP_BUDGET,
            OpsCapability.TOOL_AUTHORIZATION,
            OpsCapability.AGENT_RETIREMENT,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.DATAOPS,
        "DataOps",
        "Review freshness, reconciliation, quality, and dataset lineage.",
        (
            OpsCapability.FRESHNESS,
            OpsCapability.RECONCILIATION,
            OpsCapability.QUALITY,
            OpsCapability.DATASET_LINEAGE,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.DEVSECOPS,
        "DevSecOps",
        "Coordinate CI, tests, secret scanning, and release gates.",
        (
            OpsCapability.CI,
            OpsCapability.TESTS,
            OpsCapability.SECRET_SCANNING,
            OpsCapability.RELEASE_GATES,
        ),
    ),
    OpsDomainDefinition(
        OpsDomain.TRADEOPS,
        "TradeOps",
        "Inspect paper lifecycle, order intent, execution blockers, and closures.",
        (
            OpsCapability.PAPER_LIFECYCLE,
            OpsCapability.ORDER_INTENT,
            OpsCapability.EXECUTION_BLOCKERS,
            OpsCapability.CLOSURE_REVIEW,
        ),
    ),
)


def build_default_multiops_registry() -> MultiOpsRegistry:
    return MultiOpsRegistry(DEFAULT_MULTI_OPS_DOMAINS)

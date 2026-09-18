"""Deterministic research-topic intake for bounded external radar findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ResearchAction(StrEnum):
    """The only advisory next-step classes available to a radar finding."""

    IGNORE = "IGNORE"
    WATCH = "WATCH"
    RESEARCH = "RESEARCH"
    PROTOTYPE = "PROTOTYPE"
    VALIDATE = "VALIDATE"
    ADOPT_CANDIDATE = "ADOPT_CANDIDATE"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class ResearchTopic:
    topic_id: str
    title: str
    question: str
    query: str
    keywords: tuple[str, ...]
    validation_requirement: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchAssessment:
    """Research-only, JSON-serializable evaluation for one external finding."""

    finding_id: str
    topic_id: str
    research_question: str
    evidence_strength: float
    source_authority: float
    novelty_score: float
    system_relevance: float
    canonical_compatibility: float
    expected_benefit: float
    implementation_cost: float
    security_risk: float
    trading_risk: float
    determinism_impact: float
    performance_impact: float
    validation_requirement: tuple[str, ...]
    recommended_action: ResearchAction
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.finding_id or not self.topic_id or not self.research_question:
            raise ValueError("research assessment identity is required")
        for name, value in (
            ("evidence strength", self.evidence_strength),
            ("source authority", self.source_authority),
            ("novelty score", self.novelty_score),
            ("system relevance", self.system_relevance),
            ("canonical compatibility", self.canonical_compatibility),
            ("expected benefit", self.expected_benefit),
            ("implementation cost", self.implementation_cost),
            ("security risk", self.security_risk),
            ("trading risk", self.trading_risk),
            ("determinism impact", self.determinism_impact),
            ("performance impact", self.performance_impact),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within zero and one")
        if not self.validation_requirement or len(
            set(self.validation_requirement)
        ) != len(self.validation_requirement):
            raise ValueError("research assessment validation requirements are invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("research assessment cannot grant authority")


_BASE_VALIDATION = (
    "SOURCE_PROVENANCE_REVIEW",
    "SANDBOX_IMPLEMENTATION",
    "UNIT_TESTS",
    "SECURITY_REVIEW",
)

RESEARCH_TOPICS = (
    ResearchTopic(
        "NEW_ALGORITHM",
        "New Algorithm",
        (
            "Does the finding introduce a new deterministic algorithm or analytical "
            "method?"
        ),
        "new algorithm deterministic analytics",
        ("algorithm", "strategy"),
        ("HYPOTHESIS_REGISTER", "LEAKAGE_REVIEW", "OOS_VALIDATION_REQUIRED"),
    ),
    ResearchTopic(
        "NEW_PROTOCOL",
        "New Protocol",
        "Does the finding introduce a protocol, API, or interoperability capability?",
        "new protocol API interoperability",
        ("protocol", "api", "websocket", "fix"),
        ("OFFICIAL_DOCUMENTATION_REVIEW", "AUTHORIZATION_BOUNDARY_REVIEW"),
    ),
    ResearchTopic(
        "NEW_MODEL",
        "New Model",
        "Does the finding introduce a model with reproducible, governed evaluation?",
        "new model reproducible machine learning",
        ("model", "llm", "embedding", "forecast"),
        ("MODEL_CARD_REVIEW", "DETERMINISM_OR_SEED_REVIEW"),
    ),
    ResearchTopic(
        "NEW_AGENT_ARCHITECTURE",
        "New Agent Architecture",
        (
            "Does the finding introduce an agent architecture with typed state and "
            "least privilege?"
        ),
        "new agent architecture typed state",
        ("agent", "orchestration", "handoff", "tool use"),
        (
            "TYPED_STATE_CONTRACT",
            "LEAST_PRIVILEGE_TOOL_REVIEW",
            "DETERMINISTIC_MERGE_ORDER",
        ),
    ),
    ResearchTopic(
        "NEW_INDICATOR",
        "New Indicator",
        (
            "Does the finding introduce an indicator with oracle parity and OOS "
            "validation?"
        ),
        "new technical indicator deterministic",
        ("indicator", "oscillator", "signal", "factor"),
        ("ORACLE_PARITY_REVIEW", "OOS_VALIDATION_REQUIRED"),
    ),
    ResearchTopic(
        "NEW_EXECUTION_METHOD",
        "New Execution Method",
        (
            "Does the finding introduce an execution method while preserving manual "
            "and paper-only boundaries?"
        ),
        "new execution method slippage liquidity",
        ("execution", "fill", "slippage", "liquidity"),
        ("FILL_ASSUMPTION_REVIEW", "NO_LIVE_EXECUTION_AUTHORITY"),
    ),
    ResearchTopic(
        "NEW_RISK_CONTROL_METHOD",
        "New Risk-Control Method",
        "Does the finding strengthen a fail-closed risk control or veto?",
        "new risk control fail closed",
        ("risk", "drawdown", "exposure", "kill switch"),
        ("FAIL_CLOSED_STATE_TESTS", "LIMIT_INVARIANT_TESTS"),
    ),
    ResearchTopic(
        "NEW_DATA_SOURCE",
        "New Data Source",
        "Does the finding introduce a provenance-bound data source or stream?",
        "new data source provenance freshness",
        ("data source", "dataset", "stream", "provenance"),
        ("FRESHNESS_CONTRACT", "SCHEMA_VALIDATION"),
    ),
    ResearchTopic(
        "NEW_OPTIMIZATION_METHOD",
        "New Optimization Method",
        (
            "Does the finding introduce an optimization method without leakage or "
            "uncontrolled multiple testing?"
        ),
        "new optimization method time series",
        ("optimization", "optimizer", "bayesian", "hyperparameter"),
        ("MULTIPLE_TESTING_REVIEW", "PERFORMANCE_BASELINE_REVIEW"),
    ),
    ResearchTopic(
        "NEW_BACKTESTING_METHOD",
        "New Backtesting Method",
        (
            "Does the finding improve backtesting, simulation realism, or "
            "walk-forward validation?"
        ),
        "new backtesting method walk forward",
        ("backtest", "walk-forward", "out-of-sample", "simulation"),
        ("TIME_SERIES_SPLIT_REVIEW", "FEES_SLIPPAGE_FILL_REVIEW"),
    ),
    ResearchTopic(
        "NEW_SECURITY_MECHANISM",
        "New Security Mechanism",
        (
            "Does the finding reduce supply-chain, secret, prompt-injection, or "
            "vulnerability risk?"
        ),
        "new security mechanism supply chain",
        ("security", "vulnerability", "supply chain", "prompt injection"),
        ("THREAT_MODEL", "STATIC_SECURITY_REVIEW", "SECRET_LEAK_REVIEW"),
    ),
    ResearchTopic(
        "NEW_BLOCKCHAIN_FEATURE",
        "New Blockchain Feature",
        (
            "Does the finding introduce blockchain intelligence with finality and "
            "privacy controls?"
        ),
        "new blockchain feature onchain",
        ("blockchain", "on-chain", "mempool", "smart contract"),
        ("CHAIN_REORG_OR_FINALITY_REVIEW", "WALLET_PRIVACY_BOUNDARY_REVIEW"),
    ),
    ResearchTopic(
        "NEW_MULTI_AGENT_PIPELINE",
        "New Multi-Agent Pipeline for Complex Analytics",
        "Does the finding introduce a bounded multi-agent analytics pipeline?",
        "new multi agent pipeline complex analytics",
        ("multi-agent", "pipeline", "workflow", "dag"),
        ("BOUNDED_CONCURRENCY_REVIEW", "AUDIT_TRACE_REVIEW"),
    ),
    ResearchTopic(
        "NEW_METHODOLOGY",
        "New Methodology",
        (
            "Does the finding introduce a reproducible methodology with explicit "
            "validation?"
        ),
        "new methodology reproducible validation",
        ("methodology", "framework", "evaluation", "benchmark"),
        ("REPRODUCIBILITY_REVIEW", "VALIDATION_PLAN_REQUIRED"),
    ),
)


def research_topics_payload() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "topic_id": topic.topic_id,
            "title": topic.title,
            "question": topic.question,
            "query": topic.query,
            "validation_requirement": topic.validation_requirement,
        }
        for topic in RESEARCH_TOPICS
    )


def assess_finding(
    *,
    finding_id: str,
    text: str,
    evidence_strength: float,
    source_authority: float,
    novelty_score: float,
    system_relevance: float,
    canonical_compatibility: float,
    expected_benefit: float,
    implementation_cost: float,
    security_risk: float,
    trading_risk: float,
    local_validation_started: bool = False,
    local_validation_completed: bool = False,
) -> ResearchAssessment:
    """Classify one bounded finding without making an execution or adoption decision."""

    topic = _topic_for_text(text)
    determinism_impact = round(
        min(canonical_compatibility, 1.0 - implementation_cost), 4
    )
    performance_impact = round(expected_benefit * (1.0 - implementation_cost), 4)
    validation_requirement = tuple(
        dict.fromkeys((*_BASE_VALIDATION, *topic.validation_requirement))
    )
    action = _recommended_action(
        evidence_strength=evidence_strength,
        source_authority=source_authority,
        system_relevance=system_relevance,
        canonical_compatibility=canonical_compatibility,
        expected_benefit=expected_benefit,
        implementation_cost=implementation_cost,
        security_risk=security_risk,
        trading_risk=trading_risk,
        local_validation_started=local_validation_started,
        local_validation_completed=local_validation_completed,
    )
    return ResearchAssessment(
        finding_id=finding_id,
        topic_id=topic.topic_id,
        research_question=topic.question,
        evidence_strength=round(evidence_strength, 4),
        source_authority=round(source_authority, 4),
        novelty_score=round(novelty_score, 4),
        system_relevance=round(system_relevance, 4),
        canonical_compatibility=round(canonical_compatibility, 4),
        expected_benefit=round(expected_benefit, 4),
        implementation_cost=round(implementation_cost, 4),
        security_risk=round(security_risk, 4),
        trading_risk=round(trading_risk, 4),
        determinism_impact=determinism_impact,
        performance_impact=performance_impact,
        validation_requirement=validation_requirement,
        recommended_action=action,
    )


def _topic_for_text(text: str) -> ResearchTopic:
    normalized = text.casefold()
    matches = tuple(
        (topic, sum(keyword in normalized for keyword in topic.keywords))
        for topic in RESEARCH_TOPICS
    )
    topic, match_count = sorted(matches, key=lambda item: (-item[1], item[0].topic_id))[
        0
    ]
    if match_count:
        return topic
    return next(
        topic for topic in RESEARCH_TOPICS if topic.topic_id == "NEW_METHODOLOGY"
    )


def _recommended_action(
    *,
    evidence_strength: float,
    source_authority: float,
    system_relevance: float,
    canonical_compatibility: float,
    expected_benefit: float,
    implementation_cost: float,
    security_risk: float,
    trading_risk: float,
    local_validation_started: bool,
    local_validation_completed: bool,
) -> ResearchAction:
    if security_risk >= 0.8 or trading_risk >= 0.8 or canonical_compatibility < 0.25:
        return ResearchAction.REJECT
    if system_relevance < 0.2 or expected_benefit < 0.2:
        return ResearchAction.IGNORE
    if evidence_strength < 0.5 or source_authority < 0.5:
        return ResearchAction.WATCH
    if local_validation_completed and canonical_compatibility >= 0.9:
        return ResearchAction.ADOPT_CANDIDATE
    if local_validation_started:
        return ResearchAction.VALIDATE
    if (
        evidence_strength >= 0.8
        and canonical_compatibility >= 0.75
        and expected_benefit >= 0.7
        and implementation_cost <= 0.45
    ):
        return ResearchAction.PROTOTYPE
    return ResearchAction.RESEARCH

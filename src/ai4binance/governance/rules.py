"""Centralized DGE rule metadata.

This module is intentionally small in the first DGE slice: it gives every
enforced rule an auditable identity, severity, evidence maturity, promotion
state, and version without changing the broader trading runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ai4binance.governance.dge_models import (
    DgeRuleSeverity,
    EvidenceStatus,
    RulePromotionStatus,
)


@dataclass(frozen=True, slots=True)
class GovernanceRule:
    """Versioned rule metadata used by the Decision Governance Engine."""

    rule_id: str
    name: str
    description: str
    category: str
    severity: DgeRuleSeverity
    enabled: bool = True
    parameters: Mapping[str, str] = MappingProxyType({})
    evidence_status: EvidenceStatus = EvidenceStatus.PROMOTED
    promotion_status: RulePromotionStatus = RulePromotionStatus.PROMOTED
    allowed_regimes: tuple[str, ...] = ("ANY",)
    market_types: tuple[str, ...] = ("SPOT",)
    strategy_types: tuple[str, ...] = ("ANY",)
    created_at: str = "2026-08-08T00:00:00Z"
    updated_at: str = "2026-08-08T00:00:00Z"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        required = (
            self.rule_id,
            self.name,
            self.description,
            self.category,
            self.created_at,
            self.updated_at,
            self.version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("DGE governance rule identity is required")
        _require_unique_nonblank("DGE allowed regimes", self.allowed_regimes)
        _require_unique_nonblank("DGE market types", self.market_types)
        _require_unique_nonblank("DGE strategy types", self.strategy_types)


def default_governance_rule_catalog() -> tuple[GovernanceRule, ...]:
    """Return the first centralized DGE rule registry."""

    return (
        GovernanceRule(
            "DGE_SNAPSHOT_INTEGRITY",
            "Snapshot Integrity",
            "Governance input snapshot must be complete and immutable.",
            "system_safety",
            DgeRuleSeverity.CRITICAL,
        ),
        GovernanceRule(
            "DGE_DATA_QUALITY_GATE",
            "Data Quality Gate",
            "Fresh, synchronized market data is required before trading.",
            "data_quality",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_REQUIRED_TIMEFRAMES_PRESENT",
            "Required Timeframes Present",
            "Required multi-timeframe evidence must be present.",
            "data_quality",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_LIQUIDITY_APPROVED",
            "Liquidity Approved",
            "Spread, depth, and slippage evidence must be acceptable.",
            "liquidity",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_WALLET_POSITION_CONTEXT_VERIFIED",
            "Wallet Position Context Verified",
            "Wallet and inventory evidence must be known for current feasibility.",
            "portfolio",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_NO_COIN_DEPENDENCY_BIAS",
            "No Coin Dependency Bias",
            "Inventory attachment must not force a trade decision.",
            "portfolio",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_NO_EXTERNAL_CAPITAL_REQUIRED",
            "No External Capital Required",
            "Recovery candidates cannot require new external capital.",
            "portfolio",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_REGIME_COMPATIBLE",
            "Regime Compatible",
            "Strategy candidate must be compatible with the current regime.",
            "regime",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_MTF_ALIGNED",
            "Multi-Timeframe Aligned",
            "Higher timeframe conflict downgrades or rejects candidates.",
            "mtf",
            DgeRuleSeverity.SOFT,
        ),
        GovernanceRule(
            "DGE_NEGATIVE_EVIDENCE_CLEAR",
            "Negative Evidence Clear",
            "Rejection evidence is evaluated before positive evidence.",
            "negative_evidence",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_STRUCTURE_VALID",
            "Structure and Invalidation Valid",
            "Entry, stop, invalidation, and target logic must be structural.",
            "structure",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_OOS_APPROVED",
            "Out-of-Sample Evidence Approved",
            "Execution-impacting claims require OOS evidence.",
            "validation",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_RISK_APPROVED",
            "Risk Approved",
            "Risk manager approval is required before paper eligibility.",
            "risk",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_VALIDATION_APPROVED",
            "Validation Approved",
            "Independent validation approval is required before paper eligibility.",
            "validation",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_EXECUTION_FEASIBLE_FOR_PAPER_ONLY",
            "Execution Feasible for Paper Only",
            "Exchange and order constraints must be known before paper eligibility.",
            "execution",
            DgeRuleSeverity.SOFT,
        ),
        GovernanceRule(
            "DGE_HUMAN_REVIEW_RECORDED",
            "Human Review Recorded",
            "Manual review remains required for controlled operation.",
            "human_review",
            DgeRuleSeverity.SOFT,
        ),
        GovernanceRule(
            "DGE_SCORE_THRESHOLD",
            "Score Threshold",
            "Candidate signal quality must satisfy the configured minimum.",
            "setup_quality",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_CONFIDENCE_THRESHOLD",
            "Confidence Threshold",
            "Candidate confidence must satisfy the configured minimum.",
            "setup_quality",
            DgeRuleSeverity.HARD,
        ),
        GovernanceRule(
            "DGE_RISK_REWARD_THRESHOLD",
            "Risk Reward Threshold",
            "Risk/reward must satisfy the configured minimum.",
            "risk",
            DgeRuleSeverity.HARD,
        ),
    )


def governance_rule_index(
    rules: tuple[GovernanceRule, ...],
) -> dict[str, GovernanceRule]:
    """Index rules by id and fail fast on duplicates."""

    indexed: dict[str, GovernanceRule] = {}
    for rule in rules:
        if rule.rule_id in indexed:
            raise ValueError(f"duplicate DGE rule id: {rule.rule_id}")
        indexed[rule.rule_id] = rule
    return indexed


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai4binance.enterprise.committees import (
    CommitteeDecision,
    CommitteeId,
    CommitteeOutcome,
    CommitteeRegistry,
    CommitteeTemplate,
    build_default_committee_registry,
)
from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def test_default_committee_registry_covers_templates_not_persistent_agents() -> None:
    registry = build_default_committee_registry()
    investment = registry.get(CommitteeId.INVESTMENT_RISK)

    assert len(registry.templates) == len(CommitteeId)
    assert investment.persistent_agent is False
    assert CommitteeOutcome.LIVE_ORDER_BLOCKED in investment.allowed_outcomes
    assert all(
        item.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for item in registry.templates
    )


def test_committee_decision_is_validated_against_template_outcomes() -> None:
    registry = build_default_committee_registry()
    decision = CommitteeDecision(
        identity(),
        CommitteeId.TECHNOLOGY_CHANGE_ADVISORY,
        "decision-1",
        "proposal-1",
        CommitteeOutcome.TEST_APPROVED,
        ("artifact:test-report",),
    )

    assert registry.validate_decision(decision) is decision
    with pytest.raises(ValueError, match="outside template"):
        registry.validate_decision(
            replace(decision, outcome=CommitteeOutcome.PAPER_SOAK_APPROVED)
        )


def test_committee_templates_and_decisions_remain_fail_closed() -> None:
    template = build_default_committee_registry().get(
        CommitteeId.MODEL_PARAMETER_PROMOTION
    )
    decision = CommitteeDecision(
        identity(),
        CommitteeId.MODEL_PARAMETER_PROMOTION,
        "decision-1",
        "candidate-1",
        CommitteeOutcome.READY_FOR_USER_APPROVAL,
        ("artifact:oos-report",),
    )

    with pytest.raises(ValueError, match="not an agent"):
        replace(template, persistent_agent=True)
    with pytest.raises(ValueError, match="authorize"):
        replace(template, execution_allowed=True)
    with pytest.raises(ValueError, match="user approval"):
        replace(decision, user_approval_required=False)
    with pytest.raises(ValueError, match="promote"):
        replace(decision, promotion_status="PAPER_APPROVED")


def test_committee_registry_rejects_missing_or_duplicate_templates() -> None:
    registry = build_default_committee_registry()
    template = registry.templates[0]

    with pytest.raises(ValueError, match="cover every"):
        CommitteeRegistry(registry.templates[:-1])
    with pytest.raises(ValueError, match="unique"):
        CommitteeRegistry((template, template, *registry.templates[2:]))
    with pytest.raises(ValueError, match="at least two"):
        CommitteeTemplate(
            CommitteeId.EXECUTIVE_MANAGEMENT,
            (DepartmentId.EXECUTIVE_OFFICE,),
            (CommitteeOutcome.RESEARCH_ONLY,),
        )

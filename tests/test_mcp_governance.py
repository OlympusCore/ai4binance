"""Read-only Governance MCP contract tests."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from ai4binance.mcp.evidence import FreshnessStatus
from ai4binance.mcp.governance import GovernanceMcpGateway

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)


def gateway() -> GovernanceMcpGateway:
    return GovernanceMcpGateway(clock=lambda: NOW)


def test_governance_mcp_reads_policy_and_authority_without_execution() -> None:
    policy = gateway().get_policy()
    authority = gateway().get_authority()
    policy_data = policy.data
    authority_data = authority.data
    assert isinstance(policy_data["execution_sensitive_tools"], (list, tuple))
    assert isinstance(authority_data["initial_posture"], Mapping)

    assert policy.freshness_status is FreshnessStatus.FRESH
    assert "order.live.submit" in policy_data["execution_sensitive_tools"]
    assert authority_data["initial_posture"]["MCP_X_EXECUTION_SENSITIVE"] == "BLOCKED"
    assert policy.execution_allowed is False
    assert authority.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_governance_mcp_checks_actions_contracts_and_blockers() -> None:
    service = gateway()
    action = service.check_action()
    contract = service.check_contract()
    blockers = service.get_blockers()

    assert action.data["order.live.submit"] == "MCP_X_EXECUTION_SENSITIVE"
    assert action.blockers == ("MCP_X_BLOCKED",)
    assert contract.data["blockers_cannot_be_compensated"] is True
    assert contract.data["execution_allowed"] is False
    assert "LIVE_ORDER_BLOCKED" in blockers.blockers


def test_governance_mcp_rejects_naive_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GovernanceMcpGateway(clock=lambda: datetime(2026, 8, 20)).get_policy()

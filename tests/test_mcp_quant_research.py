from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai4binance.mcp import (
    FreshnessStatus,
    QuantResearchGateway,
    WolframMcpRegistration,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def test_quant_research_capabilities_are_cold_path_and_research_only() -> None:
    report = QuantResearchGateway(clock=lambda: NOW).get_capabilities()

    assert report.freshness_status is FreshnessStatus.FRESH
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.data["cold_path_only"] is True
    assert report.data["providers"] == {
        "internal_deterministic": "AVAILABLE",
        "wolfram": "UNAVAILABLE",
    }


def test_wolfram_status_fails_closed_without_external_registration() -> None:
    report = QuantResearchGateway(clock=lambda: NOW).wolfram_status()

    assert report.blockers == (
        "WOLFRAM_MCP_INVOCATION_BLOCKED",
        "WOLFRAM_MCP_DISABLED",
        "WOLFRAM_MCP_ENDPOINT_MISSING",
        "WOLFRAM_MCP_CREDENTIAL_MISSING",
    )
    assert report.data["endpoint_configured"] is False
    assert report.data["credential_configured"] is False
    assert "credential" not in report.source_artifact.lower()


def test_formula_verification_uses_internal_check_and_wolfram_gate() -> None:
    report = QuantResearchGateway(clock=lambda: NOW).verify_formula()

    assert report.data["internal_verification"] == "VERIFIED"
    assert report.data["wolfram_verification"] == "UNAVAILABLE"
    assert "WOLFRAM_MCP_INVOCATION_BLOCKED" in report.blockers
    assert report.execution_allowed is False


def test_registered_wolfram_provider_still_requires_executed_verification() -> None:
    gateway = QuantResearchGateway(
        wolfram_registration=WolframMcpRegistration(
            enabled=True,
            endpoint_ref="local-wolfram-mcp",
            credential_configured=True,
            invocation_allowed=True,
        ),
        clock=lambda: NOW,
    )

    status = gateway.wolfram_status()
    verification = gateway.verify_formula()

    assert status.blockers == ()
    assert status.data["invocation_allowed"] is True
    assert verification.data["wolfram_verification"] == "REGISTERED_NOT_EXECUTED"
    assert verification.blockers == ("WOLFRAM_VERIFICATION_NOT_EXECUTED",)


def test_statistics_assessment_is_deterministic_and_non_trading() -> None:
    report = QuantResearchGateway(clock=lambda: NOW).assess_statistics()

    assert report.data["sample_id"] == "embedded_reference_returns_v1"
    assert report.data["n"] == 5
    assert report.data["multiple_testing_control_required"] is True
    assert report.data["tradability_inferred"] is False
    assert report.blockers == ()


def test_wolfram_registration_requires_complete_authority_for_invocation() -> None:
    with pytest.raises(ValueError, match="complete registration"):
        WolframMcpRegistration(invocation_allowed=True)


def test_quant_gateway_rejects_naive_clock() -> None:
    gateway = QuantResearchGateway(clock=lambda: datetime(2026, 8, 20, 12, 0))

    with pytest.raises(ValueError, match="timezone-aware"):
        gateway.get_capabilities()

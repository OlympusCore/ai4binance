from typing import Any, cast

import pytest

from ai4binance.governance.execution_authority import (
    BINANCE_MARKET_MANUAL_PROFILE,
    VIRTUAL_MARKET_AUTO_PROFILE,
    ExecutionAuthorityProfile,
    ExecutionAutomationMode,
    ExecutionSurface,
    authority_profile_for_surface,
)


def test_binance_market_surface_requires_human_and_blocks_autonomy() -> None:
    profile = authority_profile_for_surface(ExecutionSurface.BINANCE_MARKET)

    assert profile is BINANCE_MARKET_MANUAL_PROFILE
    assert profile.surface is ExecutionSurface.BINANCE_MARKET
    assert profile.requires_manual_confirmation is True
    assert profile.autonomous_execution_allowed is False
    assert profile.virtual_simulation_allowed is False
    assert profile.auto_simulation_allowed is False
    assert profile.binance_order_allowed is False
    assert profile.live_order_allowed is False
    assert profile.bounded_simulation_only is False
    assert profile.live_execution_allowed is False
    assert profile.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_virtual_market_surface_allows_bounded_autonomous_simulation_only() -> None:
    profile = authority_profile_for_surface(ExecutionSurface.VIRTUAL_MARKET)

    assert profile is VIRTUAL_MARKET_AUTO_PROFILE
    assert profile.surface is ExecutionSurface.VIRTUAL_MARKET
    assert profile.requires_manual_confirmation is False
    assert profile.autonomous_execution_allowed is True
    assert profile.virtual_simulation_allowed is True
    assert profile.auto_simulation_allowed is True
    assert profile.binance_order_allowed is False
    assert profile.live_order_allowed is False
    assert profile.bounded_simulation_only is True
    assert profile.live_execution_allowed is False
    assert profile.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_execution_authority_profiles_reject_invalid_shapes_and_surfaces() -> None:
    base_kwargs = {
        "execution_surface": ExecutionSurface.BINANCE_MARKET,
        "automation_mode": ExecutionAutomationMode.HUMAN_HAND_MANUAL_ONLY,
        "simulated_execution_allowed": False,
        "paper_execution_allowed": True,
        "auto_execution_allowed": False,
        "autonomous_learning_allowed": False,
        "bounded_self_improvement_allowed": False,
        "simulated_spot_allowed": False,
        "simulated_futures_allowed": False,
        "requires_manual_confirmation": True,
    }
    named_kwargs = {**base_kwargs, "authority_profile_id": "manual"}
    profile_factory = cast(Any, ExecutionAuthorityProfile)

    with pytest.raises(ValueError, match="identity is required"):
        profile_factory(authority_profile_id=" ", **base_kwargs)
    with pytest.raises(ValueError, match="cannot authorize live use"):
        profile_factory(
            authority_profile_id="manual",
            execution_allowed=True,
            **base_kwargs,
        )
    with pytest.raises(ValueError, match="must remain research only"):
        profile_factory(promotion_status="LIVE_APPROVED", **named_kwargs)
    with pytest.raises(ValueError, match="must remain live blocked"):
        profile_factory(live_eligibility_status="READY", **named_kwargs)
    with pytest.raises(ValueError, match="must be unique"):
        profile_factory(reason_codes=("DUP", "DUP"), **named_kwargs)
    with pytest.raises(ValueError, match="cannot contain blanks"):
        profile_factory(reason_codes=("OK", " "), **named_kwargs)
    with pytest.raises(ValueError, match="paper execution compatibility flag"):
        profile_factory(
            authority_profile_id="virtual",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            simulated_execution_allowed=True,
            paper_execution_allowed=False,
            auto_execution_allowed=True,
            autonomous_learning_allowed=True,
            bounded_self_improvement_allowed=True,
            simulated_spot_allowed=True,
            simulated_futures_allowed=True,
            requires_manual_confirmation=False,
        )
    with pytest.raises(ValueError, match="simulated execution allowance"):
        profile_factory(
            authority_profile_id="virtual",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            simulated_execution_allowed=False,
            paper_execution_allowed=True,
            auto_execution_allowed=True,
            autonomous_learning_allowed=True,
            bounded_self_improvement_allowed=True,
            simulated_spot_allowed=True,
            simulated_futures_allowed=True,
            requires_manual_confirmation=False,
        )
    with pytest.raises(ValueError, match="autonomous learning allowance"):
        profile_factory(
            authority_profile_id="virtual",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            simulated_execution_allowed=True,
            paper_execution_allowed=True,
            auto_execution_allowed=True,
            autonomous_learning_allowed=False,
            bounded_self_improvement_allowed=True,
            simulated_spot_allowed=True,
            simulated_futures_allowed=True,
            requires_manual_confirmation=False,
        )
    with pytest.raises(ValueError, match="simulated execution allowance"):
        profile_factory(
            authority_profile_id="virtual",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            simulated_execution_allowed=False,
            paper_execution_allowed=True,
            auto_execution_allowed=True,
            autonomous_learning_allowed=True,
            bounded_self_improvement_allowed=True,
            simulated_spot_allowed=True,
            simulated_futures_allowed=True,
            requires_manual_confirmation=False,
        )
    with pytest.raises(ValueError, match="manual confirmation"):
        profile_factory(**dict(named_kwargs, requires_manual_confirmation=False))
    with pytest.raises(ValueError, match="bounded autonomous simulation requires"):
        profile_factory(
            authority_profile_id="virtual",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            simulated_execution_allowed=True,
            paper_execution_allowed=True,
            auto_execution_allowed=False,
            autonomous_learning_allowed=True,
            bounded_self_improvement_allowed=True,
            simulated_spot_allowed=True,
            simulated_futures_allowed=True,
            requires_manual_confirmation=False,
        )
    with pytest.raises(ValueError, match="unsupported execution surface"):
        authority_profile_for_surface(cast(Any, "UNKNOWN"))

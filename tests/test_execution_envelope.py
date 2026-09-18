from dataclasses import replace
from typing import Any, cast

import pytest

from ai4binance.governance.execution_authority import (
    ExecutionAutomationMode,
    ExecutionSurface,
)
from ai4binance.governance.execution_envelope import (
    ExecutionEnvelope,
    execution_envelope_for_surface,
)


def test_execution_envelope_for_governed_surfaces_is_fail_closed() -> None:
    binance_envelope = execution_envelope_for_surface(ExecutionSurface.BINANCE_MARKET)
    virtual_envelope = execution_envelope_for_surface(ExecutionSurface.VIRTUAL_MARKET)

    assert binance_envelope.authority_profile_id == "BINANCE_MANUAL_ONLY_V1"
    assert binance_envelope.execution_surface is ExecutionSurface.BINANCE_MARKET
    assert (
        binance_envelope.automation_mode
        is ExecutionAutomationMode.HUMAN_HAND_MANUAL_ONLY
    )
    assert binance_envelope.manual_confirmation_required is True
    assert binance_envelope.virtual_simulation_allowed is False
    assert binance_envelope.auto_simulation_allowed is False
    assert binance_envelope.paper_execution_allowed is True
    assert binance_envelope.external_order_allowed is False
    assert binance_envelope.live_order_allowed is False
    assert binance_envelope.external_order_blocked is True
    assert binance_envelope.bounded_simulation_only is False

    assert virtual_envelope.authority_profile_id == "VIRTUAL_AUTONOMOUS_SIMULATION_V1"
    assert virtual_envelope.execution_surface is ExecutionSurface.VIRTUAL_MARKET
    assert (
        virtual_envelope.automation_mode
        is ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION
    )
    assert virtual_envelope.manual_confirmation_required is False
    assert virtual_envelope.virtual_simulation_allowed is True
    assert virtual_envelope.auto_simulation_allowed is True
    assert virtual_envelope.paper_execution_allowed is True
    assert virtual_envelope.external_order_allowed is False
    assert virtual_envelope.live_order_allowed is False
    assert virtual_envelope.external_order_blocked is True
    assert virtual_envelope.bounded_simulation_only is True


def test_execution_envelope_rejects_contradictory_authority_inputs() -> None:
    envelope_factory = cast(Any, ExecutionEnvelope)

    with pytest.raises(ValueError, match="cannot authorize external orders"):
        envelope_factory(
            authority_profile_id="bad-external",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            manual_confirmation_required=False,
            virtual_simulation_allowed=True,
            auto_simulation_allowed=True,
            paper_execution_allowed=True,
            external_order_allowed=True,
            live_order_allowed=False,
            bounded_simulation_only=True,
        )

    with pytest.raises(ValueError, match="cannot authorize external orders"):
        envelope_factory(
            authority_profile_id="bad-live",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            manual_confirmation_required=False,
            virtual_simulation_allowed=True,
            auto_simulation_allowed=True,
            paper_execution_allowed=True,
            external_order_allowed=False,
            live_order_allowed=True,
            bounded_simulation_only=True,
        )

    with pytest.raises(ValueError, match="must remain manual and non-autonomous"):
        envelope_factory(
            authority_profile_id="bad-manual",
            execution_surface=ExecutionSurface.BINANCE_MARKET,
            automation_mode=ExecutionAutomationMode.HUMAN_HAND_MANUAL_ONLY,
            manual_confirmation_required=False,
            virtual_simulation_allowed=False,
            auto_simulation_allowed=False,
            paper_execution_allowed=True,
            external_order_allowed=False,
            live_order_allowed=False,
            bounded_simulation_only=False,
        )

    with pytest.raises(ValueError, match="must remain autonomous and unconfirmed"):
        envelope_factory(
            authority_profile_id="bad-virtual",
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            manual_confirmation_required=True,
            virtual_simulation_allowed=True,
            auto_simulation_allowed=True,
            paper_execution_allowed=True,
            external_order_allowed=False,
            live_order_allowed=False,
            bounded_simulation_only=True,
        )


def test_execution_envelope_rejects_identity_reason_and_simulation_drift() -> None:
    envelope = execution_envelope_for_surface(ExecutionSurface.BINANCE_MARKET)

    with pytest.raises(ValueError, match="identity is required"):
        replace(envelope, authority_profile_id="")
    with pytest.raises(ValueError, match="reason codes must be unique"):
        replace(envelope, reason_codes=("DUPLICATE", "DUPLICATE"))
    with pytest.raises(ValueError, match="reason codes cannot contain blanks"):
        replace(envelope, reason_codes=("",))
    with pytest.raises(ValueError, match="requires paper execution compatibility"):
        replace(
            envelope,
            virtual_simulation_allowed=True,
            paper_execution_allowed=False,
        )
    with pytest.raises(ValueError, match="requires virtual simulation allowance"):
        replace(envelope, auto_simulation_allowed=True)
    with pytest.raises(ValueError, match="must match the execution surface"):
        replace(envelope, bounded_simulation_only=True)

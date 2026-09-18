"""Canonical execution envelope derived from governed authority profiles."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.governance.execution_authority import (
    ExecutionAuthorityProfile,
    ExecutionAutomationMode,
    ExecutionSurface,
    authority_profile_for_surface,
)


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


@dataclass(frozen=True, slots=True)
class ExecutionEnvelope:
    """Typed execution summary used by application and execution layers."""

    authority_profile_id: str
    execution_surface: ExecutionSurface
    automation_mode: ExecutionAutomationMode
    manual_confirmation_required: bool
    virtual_simulation_allowed: bool
    auto_simulation_allowed: bool
    paper_execution_allowed: bool
    external_order_allowed: bool
    live_order_allowed: bool
    bounded_simulation_only: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.authority_profile_id.strip():
            raise ValueError("execution envelope identity is required")
        _require_unique_nonblank("execution envelope reason codes", self.reason_codes)
        if self.external_order_allowed or self.live_order_allowed:
            raise ValueError("execution envelope cannot authorize external orders")
        if self.virtual_simulation_allowed and not self.paper_execution_allowed:
            raise ValueError(
                "virtual execution envelope requires paper execution compatibility"
            )
        if self.auto_simulation_allowed and not self.virtual_simulation_allowed:
            raise ValueError("auto simulation requires virtual simulation allowance")
        if self.bounded_simulation_only != (
            self.execution_surface is ExecutionSurface.VIRTUAL_MARKET
        ):
            raise ValueError("bounded simulation flag must match the execution surface")
        if self.execution_surface is ExecutionSurface.BINANCE_MARKET and (
            not self.manual_confirmation_required or self.auto_simulation_allowed
        ):
            raise ValueError(
                "Binance execution envelope must remain manual and non-autonomous"
            )
        if self.execution_surface is ExecutionSurface.VIRTUAL_MARKET and (
            self.manual_confirmation_required or not self.auto_simulation_allowed
        ):
            raise ValueError(
                "virtual execution envelope must remain autonomous and unconfirmed"
            )

    @property
    def external_order_blocked(self) -> bool:
        """Return whether the envelope blocks all external order authority."""

        return not self.external_order_allowed


def execution_envelope_for_profile(
    profile: ExecutionAuthorityProfile,
) -> ExecutionEnvelope:
    """Derive the canonical envelope from one governed authority profile."""

    return ExecutionEnvelope(
        authority_profile_id=profile.authority_profile_id,
        execution_surface=profile.execution_surface,
        automation_mode=profile.automation_mode,
        manual_confirmation_required=profile.requires_manual_confirmation,
        virtual_simulation_allowed=profile.virtual_simulation_allowed,
        auto_simulation_allowed=profile.auto_simulation_allowed,
        paper_execution_allowed=profile.paper_execution_allowed,
        external_order_allowed=profile.external_order_allowed,
        live_order_allowed=profile.live_order_allowed,
        bounded_simulation_only=profile.bounded_simulation_only,
        reason_codes=profile.reason_codes,
    )


def execution_envelope_for_surface(
    execution_surface: ExecutionSurface,
) -> ExecutionEnvelope:
    """Return the canonical execution envelope for a governed surface."""

    return execution_envelope_for_profile(
        authority_profile_for_surface(execution_surface)
    )

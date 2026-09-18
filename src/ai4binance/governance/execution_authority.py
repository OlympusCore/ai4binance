"""Canonical execution-surface authority profiles for simulation and live boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionSurface(StrEnum):
    """Canonical execution surfaces with distinct authority envelopes."""

    BINANCE_MARKET = "BINANCE_MARKET"
    VIRTUAL_MARKET = "VIRTUAL_MARKET"


class ExecutionAutomationMode(StrEnum):
    """Deterministic automation modes allowed per execution surface."""

    HUMAN_HAND_MANUAL_ONLY = "HUMAN_HAND_MANUAL_ONLY"
    BOUNDED_AUTONOMOUS_SIMULATION = "BOUNDED_AUTONOMOUS_SIMULATION"
    BOUNDED_AUTO_PAPER_ALGO = "BOUNDED_AUTO_PAPER_ALGO"


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


@dataclass(frozen=True, slots=True)
class ExecutionAuthorityProfile:
    """Governed authority envelope for one execution surface."""

    authority_profile_id: str
    execution_surface: ExecutionSurface
    automation_mode: ExecutionAutomationMode
    simulated_execution_allowed: bool
    paper_execution_allowed: bool
    auto_execution_allowed: bool
    autonomous_learning_allowed: bool
    bounded_self_improvement_allowed: bool
    simulated_spot_allowed: bool
    simulated_futures_allowed: bool
    requires_manual_confirmation: bool
    reason_codes: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def autonomous_execution_allowed(self) -> bool:
        """Return the canonical autonomous-execution contract field."""

        return self.auto_execution_allowed

    @property
    def surface(self) -> ExecutionSurface:
        """Return the canonical execution surface with a concise accessor."""

        return self.execution_surface

    @property
    def virtual_simulation_allowed(self) -> bool:
        """Return whether the surface may run autonomous virtual simulation."""

        return self.simulated_execution_allowed

    @property
    def auto_simulation_allowed(self) -> bool:
        """Return whether the surface may autonomously submit virtual actions."""

        return self.auto_execution_allowed

    @property
    def external_order_allowed(self) -> bool:
        """Return whether the surface can submit an exchange order."""

        return self.execution_allowed

    @property
    def binance_order_allowed(self) -> bool:
        """Return whether Binance-market order placement is allowed."""

        return self.execution_allowed

    @property
    def live_order_allowed(self) -> bool:
        """Return whether live-order authority is enabled."""

        return self.live_execution_allowed

    @property
    def bounded_simulation_only(self) -> bool:
        """Return whether the surface is limited to bounded simulation only."""

        return self.execution_surface is ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        if not self.authority_profile_id.strip():
            raise ValueError("execution authority profile identity is required")
        if self.execution_allowed or self.live_execution_allowed:
            raise ValueError("execution authority profile cannot authorize live use")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("execution authority profile must remain research only")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("execution authority profile must remain live blocked")
        _require_unique_nonblank("execution authority reason codes", self.reason_codes)
        if self.simulated_execution_allowed and not self.paper_execution_allowed:
            raise ValueError(
                "simulated execution requires the paper execution compatibility flag"
            )
        if self.auto_execution_allowed and not self.simulated_execution_allowed:
            raise ValueError("auto simulation requires simulated execution allowance")
        if (
            self.bounded_self_improvement_allowed
            and not self.autonomous_learning_allowed
        ):
            raise ValueError(
                "bounded self-improvement requires autonomous learning allowance"
            )
        if (
            self.simulated_spot_allowed or self.simulated_futures_allowed
        ) and not self.simulated_execution_allowed:
            raise ValueError(
                "simulated market coverage requires simulated execution allowance"
            )
        if self.automation_mode is ExecutionAutomationMode.HUMAN_HAND_MANUAL_ONLY and (
            self.auto_execution_allowed
            or self.simulated_execution_allowed
            or self.autonomous_learning_allowed
            or self.bounded_self_improvement_allowed
            or self.simulated_spot_allowed
            or self.simulated_futures_allowed
            or not self.requires_manual_confirmation
        ):
            raise ValueError(
                "human-hand manual execution requires manual confirmation "
                "and no autonomous simulation"
            )
        if self.automation_mode in {
            ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            ExecutionAutomationMode.BOUNDED_AUTO_PAPER_ALGO,
        } and (
            not self.simulated_execution_allowed
            or not self.auto_execution_allowed
            or not self.autonomous_learning_allowed
            or not self.bounded_self_improvement_allowed
            or not self.simulated_spot_allowed
            or not self.simulated_futures_allowed
            or self.requires_manual_confirmation
        ):
            raise ValueError(
                "bounded autonomous simulation requires governed simulated "
                "execution, learning, and self-improvement without manual confirmation"
            )


BINANCE_MARKET_MANUAL_PROFILE = ExecutionAuthorityProfile(
    authority_profile_id="BINANCE_MANUAL_ONLY_V1",
    execution_surface=ExecutionSurface.BINANCE_MARKET,
    automation_mode=ExecutionAutomationMode.HUMAN_HAND_MANUAL_ONLY,
    simulated_execution_allowed=False,
    paper_execution_allowed=True,
    auto_execution_allowed=False,
    autonomous_learning_allowed=False,
    bounded_self_improvement_allowed=False,
    simulated_spot_allowed=False,
    simulated_futures_allowed=False,
    requires_manual_confirmation=True,
    reason_codes=(
        "BINANCE_MARKET",
        "HUMAN_HAND_MANUAL_ONLY",
        "AUTO_SIMULATION_DISABLED",
        "LIVE_ORDER_BLOCKED",
    ),
)

VIRTUAL_MARKET_AUTO_PROFILE = ExecutionAuthorityProfile(
    authority_profile_id="VIRTUAL_AUTONOMOUS_SIMULATION_V1",
    execution_surface=ExecutionSurface.VIRTUAL_MARKET,
    automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
    simulated_execution_allowed=True,
    paper_execution_allowed=True,
    auto_execution_allowed=True,
    autonomous_learning_allowed=True,
    bounded_self_improvement_allowed=True,
    simulated_spot_allowed=True,
    simulated_futures_allowed=True,
    requires_manual_confirmation=False,
    reason_codes=(
        "VIRTUAL_MARKET",
        "BOUNDED_AUTONOMOUS_SIMULATION",
        "EXTERNAL_ORDER_BLOCKED",
        "LIVE_ORDER_BLOCKED",
    ),
)


def authority_profile_for_surface(
    execution_surface: ExecutionSurface,
) -> ExecutionAuthorityProfile:
    """Return the canonical authority profile for the given surface."""

    if execution_surface is ExecutionSurface.BINANCE_MARKET:
        return BINANCE_MARKET_MANUAL_PROFILE
    if execution_surface is ExecutionSurface.VIRTUAL_MARKET:
        return VIRTUAL_MARKET_AUTO_PROFILE
    raise ValueError(f"unsupported execution surface: {execution_surface}")

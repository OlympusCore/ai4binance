"""Eligibility gating for bounded virtual simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from typing import Protocol, cast

_blocker_reduction_module = import_module("ai4binance.governance.blocker_reduction")
VirtualBlockerReduction = _blocker_reduction_module.VirtualBlockerReduction
reduce_virtual_blockers = _blocker_reduction_module.reduce_virtual_blockers

_execution_envelope_module = import_module("ai4binance.governance.execution_envelope")
execution_envelope_for_surface = (
    _execution_envelope_module.execution_envelope_for_surface
)


class _VirtualBlockerReductionLike(Protocol):
    @property
    def root_cause_codes(self) -> tuple[str, ...]: ...


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _is_virtual_market_surface(execution_surface: object) -> bool:
    return getattr(execution_surface, "value", execution_surface) == "VIRTUAL_MARKET"


class VirtualSimulationStatus(StrEnum):
    """Deterministic eligibility outcome for the virtual execution surface."""

    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class VirtualSimulationEligibility:
    """Explicit separation between virtual simulation and external order authority."""

    status: VirtualSimulationStatus
    execution_surface: object
    requires_manual_confirmation: bool
    virtual_simulation_allowed: bool
    auto_simulation_allowed: bool
    binance_order_allowed: bool
    live_order_allowed: bool
    reason_codes: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    blocker_reduction: object | None = None
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def eligible(self) -> bool:
        return self.status is VirtualSimulationStatus.ELIGIBLE

    def __post_init__(self) -> None:
        _require_unique_nonblank("virtual simulation reason codes", self.reason_codes)
        _require_unique_nonblank("virtual simulation blockers", self.blockers)
        if self.blockers:
            blocker_reduction = cast(
                _VirtualBlockerReductionLike | None, self.blocker_reduction
            )
            if blocker_reduction is None:
                raise ValueError(
                    "blocked virtual simulation requires root-cause reduction"
                )
            if blocker_reduction.root_cause_codes != self.blockers:
                raise ValueError(
                    "blocked virtual simulation root-cause reduction is inconsistent"
                )
        elif self.blocker_reduction is not None:
            raise ValueError(
                "eligible virtual simulation cannot carry root-cause reduction"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("virtual simulation eligibility must remain live blocked")
        if self.binance_order_allowed or self.live_order_allowed:
            raise ValueError("virtual simulation eligibility cannot authorize orders")
        if self.eligible:
            if not _is_virtual_market_surface(self.execution_surface):
                raise ValueError(
                    "eligible virtual simulation must target VIRTUAL_MARKET"
                )
            if not self.virtual_simulation_allowed or not self.auto_simulation_allowed:
                raise ValueError(
                    "eligible virtual simulation requires autonomous "
                    "simulation authority"
                )
            if self.requires_manual_confirmation:
                raise ValueError(
                    "eligible virtual simulation cannot require manual confirmation"
                )
            if self.blockers:
                raise ValueError("eligible virtual simulation cannot contain blockers")
        else:
            if not self.blockers:
                raise ValueError("blocked virtual simulation requires blockers")


def evaluate_virtual_simulation_eligibility(
    *,
    execution_surface: object,
    analysis_blockers: tuple[str, ...] = (),
    candidate_blockers: tuple[str, ...] = (),
    risk_blockers: tuple[str, ...] = (),
    validation_blockers: tuple[str, ...] = (),
    dge_blockers: tuple[str, ...] = (),
    portfolio_blockers: tuple[str, ...] = (),
    feasibility_blockers: tuple[str, ...] = (),
) -> VirtualSimulationEligibility:
    """Evaluate whether bounded virtual simulation may proceed."""

    authority_envelope = execution_envelope_for_surface(execution_surface)
    authority_blockers: list[str] = []
    if not _is_virtual_market_surface(execution_surface):
        authority_blockers.append("EXECUTION_SURFACE_NOT_VIRTUAL_MARKET")
    if not authority_envelope.virtual_simulation_allowed:
        authority_blockers.append("VIRTUAL_SIMULATION_NOT_ALLOWED")
    if not authority_envelope.auto_simulation_allowed:
        authority_blockers.append("AUTO_SIMULATION_NOT_ALLOWED")
    if authority_envelope.external_order_allowed:
        authority_blockers.append("BINANCE_ORDER_AUTHORITY_LEAK")
    if authority_envelope.live_order_allowed:
        authority_blockers.append("LIVE_ORDER_AUTHORITY_LEAK")
    blocker_reduction = reduce_virtual_blockers(
        analysis_blockers=analysis_blockers,
        candidate_blockers=candidate_blockers,
        risk_blockers=risk_blockers,
        validation_blockers=validation_blockers,
        dge_blockers=dge_blockers,
        portfolio_blockers=portfolio_blockers,
        feasibility_blockers=feasibility_blockers,
        authority_blockers=tuple(authority_blockers),
    )
    blockers = list(blocker_reduction.root_cause_codes)
    unique_blockers = tuple(dict.fromkeys(blockers))
    status = (
        VirtualSimulationStatus.BLOCKED
        if unique_blockers
        else VirtualSimulationStatus.ELIGIBLE
    )
    reason_codes = (
        authority_envelope.reason_codes
        if status is VirtualSimulationStatus.ELIGIBLE
        else tuple(dict.fromkeys((*authority_envelope.reason_codes, *unique_blockers)))
    )
    return VirtualSimulationEligibility(
        status=status,
        execution_surface=execution_surface,
        requires_manual_confirmation=authority_envelope.manual_confirmation_required,
        virtual_simulation_allowed=(
            authority_envelope.virtual_simulation_allowed
            and status is VirtualSimulationStatus.ELIGIBLE
        ),
        auto_simulation_allowed=(
            authority_envelope.auto_simulation_allowed
            and status is VirtualSimulationStatus.ELIGIBLE
        ),
        binance_order_allowed=False,
        live_order_allowed=False,
        reason_codes=reason_codes,
        blockers=unique_blockers,
        blocker_reduction=(blocker_reduction if unique_blockers else None),
    )

"""Canonical virtual-market runtime application service."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Protocol

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
    VirtualSimulationStatus,
    evaluate_virtual_simulation_eligibility,
)

_research_virtual_runtime = import_module("ai4binance.research.virtual_runtime")

_ELIGIBILITY_EXPORTS = {
    "VirtualSimulationEligibility",
    "VirtualSimulationStatus",
    "evaluate_virtual_simulation_eligibility",
}

_RESEARCH_EXPORTS = set(_research_virtual_runtime.__all__)

__all__ = (
    "VirtualSimulationEligibility",
    "VirtualSimulationStatus",
    "evaluate_virtual_simulation_eligibility",
    "VirtualMarketCycleResult",
    "evaluate_virtual_market_runtime",
    "run_virtual_market_cycle",
    *_research_virtual_runtime.__all__,
)


class _StatusValue(Protocol):
    value: str


@dataclass(frozen=True, slots=True)
class VirtualMarketCycleResult:
    """Bounded virtual-market result bundle with explicit live-blocked status."""

    request: object
    decision: object
    eligibility: object
    blockers: tuple[str, ...]
    trade_intent: object | None
    portfolio_before: object
    portfolio_after: object
    audit_refs: tuple[str, ...]
    halt_review: object | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("virtual market cycle result cannot grant execution")
        if getattr(self.decision, "eligibility", None) is not self.eligibility:
            raise ValueError(
                "virtual market cycle result must use the decision eligibility"
            )
        if tuple(getattr(self.eligibility, "blockers", ())) != self.blockers:
            raise ValueError("virtual market cycle result blockers are inconsistent")
        if getattr(self.decision, "trade_intent", None) is not self.trade_intent:
            raise ValueError("virtual market cycle result trade intent is inconsistent")
        if (
            getattr(self.decision, "portfolio_before", None)
            is not self.portfolio_before
        ):
            raise ValueError(
                "virtual market cycle result portfolio_before is inconsistent"
            )
        if getattr(self.decision, "portfolio_after", None) is not self.portfolio_after:
            raise ValueError(
                "virtual market cycle result portfolio_after is inconsistent"
            )
        if tuple(getattr(self.decision, "audit_refs", ())) != self.audit_refs:
            raise ValueError("virtual market cycle result audit refs are inconsistent")
        if getattr(self.decision, "halt_review", None) is not self.halt_review:
            raise ValueError("virtual market cycle result halt review is inconsistent")

    @property
    def decision_status(self) -> _StatusValue:
        return self.decision.status

    @property
    def halted(self) -> bool:
        return bool(self.decision.halted)

    def to_payload(self) -> dict[str, object]:
        """Return a secret-safe payload for logs, CLI output, or audit sinks."""

        return {
            "request": self.request,
            "decision_status": getattr(
                self.decision_status, "value", self.decision_status
            ),
            "eligibility": self.eligibility,
            "blockers": self.blockers,
            "trade_intent": self.trade_intent,
            "portfolio_before": self.portfolio_before,
            "portfolio_after": self.portfolio_after,
            "audit_refs": self.audit_refs,
            "halt_review": self.halt_review,
            "execution_allowed": self.execution_allowed,
            "live_eligibility_status": self.live_eligibility_status,
        }


def __getattr__(name: str) -> object:
    if name in _ELIGIBILITY_EXPORTS:
        return globals()[name]
    if name == "evaluate_virtual_market_runtime":
        return evaluate_virtual_market_runtime
    if name in _RESEARCH_EXPORTS:
        value = getattr(_research_virtual_runtime, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)


def evaluate_virtual_market_runtime(
    request: object,
    *,
    runtime: object | None = None,
) -> object:
    """Evaluate one virtual-market request through the canonical runtime bridge."""

    virtual_market_runtime = (
        runtime
        if runtime is not None
        else _research_virtual_runtime.VirtualMarketRuntime()
    )
    return virtual_market_runtime.evaluate(request)


def run_virtual_market_cycle(
    request: object,
    *,
    runtime: object | None = None,
) -> VirtualMarketCycleResult:
    """Evaluate one bounded virtual-market cycle and return a result bundle."""

    virtual_market_runtime = (
        runtime
        if runtime is not None
        else _research_virtual_runtime.VirtualMarketRuntime()
    )
    decision = virtual_market_runtime.evaluate(request)
    return VirtualMarketCycleResult(
        request=request,
        decision=decision,
        eligibility=decision.eligibility,
        blockers=tuple(decision.eligibility.blockers),
        trade_intent=decision.trade_intent,
        portfolio_before=decision.portfolio_before,
        portfolio_after=decision.portfolio_after,
        audit_refs=decision.audit_refs,
        halt_review=decision.halt_review,
    )

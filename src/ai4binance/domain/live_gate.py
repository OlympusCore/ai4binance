"""Fail-closed execution safety policies."""

from dataclasses import fields

from ai4binance.domain import ExecutionStatus, LiveGateInput, LiveGateResult

LIVE_GATE_REQUIREMENTS: tuple[str, ...] = tuple(
    field_info.name for field_info in fields(LiveGateInput)
)


def evaluate_live_gate(gate_input: LiveGateInput) -> LiveGateResult:
    """Return every unmet live prerequisite without side effects."""
    blockers = tuple(
        requirement
        for requirement in LIVE_GATE_REQUIREMENTS
        if not getattr(gate_input, requirement)
    )
    status = (
        ExecutionStatus.LIVE_ORDER_BLOCKED
        if blockers
        else ExecutionStatus.EXECUTION_ALLOWED
    )
    return LiveGateResult(status=status, blockers=blockers)

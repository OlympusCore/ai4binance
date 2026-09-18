from __future__ import annotations

import pytest

from ai4binance.governance import (
    ToolCallSignature,
    ToolLoopAction,
    ToolLoopDecision,
    ToolLoopGuard,
    ToolLoopGuardConfig,
    ToolSideEffect,
)


def test_tool_loop_guard_warns_and_blocks_repeated_failures() -> None:
    guard = ToolLoopGuard(
        ToolLoopGuardConfig(
            exact_failure_warn_after=2,
            exact_failure_block_after=3,
        )
    )

    assert not guard.before_call(
        tool_name="quality-triage",
        arguments={"symbol": "HOTUSDT"},
        side_effect=ToolSideEffect.READ_LOCAL,
    ).blocked
    assert (
        guard.after_call(
            tool_name="quality-triage",
            arguments={"symbol": "HOTUSDT"},
            side_effect=ToolSideEffect.READ_LOCAL,
            result={"error": "boom"},
            failed=True,
        ).action
        is ToolLoopAction.ALLOW
    )
    assert (
        guard.after_call(
            tool_name="quality-triage",
            arguments={"symbol": "HOTUSDT"},
            side_effect=ToolSideEffect.READ_LOCAL,
            result={"error": "boom"},
            failed=True,
        ).action
        is ToolLoopAction.WARN
    )
    guard.after_call(
        tool_name="quality-triage",
        arguments={"symbol": "HOTUSDT"},
        side_effect=ToolSideEffect.READ_LOCAL,
        result={"error": "boom"},
        failed=True,
    )

    blocked = guard.before_call(
        tool_name="quality-triage",
        arguments={"symbol": "HOTUSDT"},
        side_effect=ToolSideEffect.READ_LOCAL,
    )

    assert blocked.blocked
    assert blocked.code == "REPEATED_EXACT_FAILURE_BLOCKED"


def test_tool_loop_guard_blocks_idempotent_no_progress() -> None:
    guard = ToolLoopGuard(
        ToolLoopGuardConfig(
            no_progress_warn_after=2,
            no_progress_block_after=3,
        )
    )
    args = {"source": "runtime/artifacts/quality/triage/state.json"}

    for _ in range(3):
        guard.after_call(
            tool_name="quality-triage",
            arguments=args,
            side_effect=ToolSideEffect.READ_LOCAL,
            result={"status": "same"},
            failed=False,
        )

    blocked = guard.before_call(
        tool_name="quality-triage",
        arguments=args,
        side_effect=ToolSideEffect.READ_LOCAL,
    )

    assert blocked.action is ToolLoopAction.BLOCK
    assert blocked.result_hash is not None
    assert blocked.code == "IDEMPOTENT_NO_PROGRESS_BLOCKED"


def test_tool_loop_guard_contracts_reject_invalid_config() -> None:
    with pytest.raises(ValueError, match="thresholds"):
        ToolLoopGuardConfig(exact_failure_warn_after=0)
    with pytest.raises(ValueError, match="tool name"):
        ToolCallSignature("", "a" * 64)
    with pytest.raises(ValueError, match="args hash"):
        ToolCallSignature("tool", "bad")
    with pytest.raises(ValueError, match="count"):
        ToolLoopDecision(count=-1)
    with pytest.raises(ValueError, match="result hash"):
        ToolLoopDecision(result_hash="bad")


def test_tool_loop_guard_ignores_non_idempotent_success() -> None:
    guard = ToolLoopGuard()
    decision = guard.after_call(
        tool_name="writer",
        arguments={"target": "state"},
        side_effect=ToolSideEffect.WRITE_LOCAL,
        result={"status": "same"},
        failed=False,
    )

    assert decision.action is ToolLoopAction.ALLOW
    assert not guard.before_call(
        tool_name="writer",
        arguments={"target": "state"},
        side_effect=ToolSideEffect.WRITE_LOCAL,
    ).blocked

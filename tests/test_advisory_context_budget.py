from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.application.context.budget import (
    BoundedContextAssembler,
    ContextAssembly,
    ContextBudgetExceededError,
    ContextFragment,
    TokenBudget,
    TokenBudgetGuard,
    TokenUsage,
)


def test_bounded_context_truncates_and_drops_restricted_sources() -> None:
    guard = TokenBudgetGuard(TokenBudget(max_fragment=16, max_context=256))
    assembly = BoundedContextAssembler(guard).assemble(
        system="system",
        current_input="input",
        fragments=(
            ContextFragment("large", "alpha " * 60, priority=2),
            ContextFragment("restricted", "secret-ish", classification="RESTRICTED"),
            ContextFragment(
                "expired",
                "old",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            ContextFragment("small", "usable", priority=1),
        ),
    )

    assert assembly.execution_allowed is False
    assert assembly.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "large" in assembly.truncated_sources
    assert assembly.dropped_sources == ("expired", "restricted")
    assert assembly.kept_sources == ("large", "small")
    assert "[CONTEXT_TRUNCATED]" in assembly.rendered_context


def test_bounded_context_blocks_when_window_cannot_fit() -> None:
    guard = TokenBudgetGuard(
        TokenBudget(
            context_window=8,
            max_current_input=2,
            output_reserve=7,
        )
    )
    with pytest.raises(ContextBudgetExceededError, match=r"INPUT|CONTEXT_WINDOW"):
        BoundedContextAssembler(guard).assemble(
            system="system",
            current_input="this input cannot fit",
            fragments=(),
        )


def test_context_budget_contract_edges() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TokenBudget(max_context=-1)
    with pytest.raises(ValueError, match="reserve"):
        TokenBudget(context_window=8, output_reserve=9)
    with pytest.raises(ValueError, match="negative"):
        TokenUsage(0, -1, 0, 0, 0, 0)
    with pytest.raises(ValueError, match="source and content"):
        ContextFragment("", "content")
    with pytest.raises(ValueError, match="expiry"):
        ContextFragment("source", "content", expires_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="cannot authorize"):
        ContextAssembly(
            "",
            TokenUsage(0, 0, 0, 0, 0, 0),
            (),
            (),
            (),
            execution_allowed=True,
        )


def test_bounded_context_drops_low_priority_until_budget_fits() -> None:
    guard = TokenBudgetGuard(TokenBudget(max_fragment=32, max_context=130))
    assembly = BoundedContextAssembler(guard).assemble(
        system="s",
        current_input="i",
        fragments=(
            ContextFragment("keep", "alpha " * 5, priority=10),
            ContextFragment("drop", "beta " * 20, priority=1),
        ),
    )

    assert assembly.kept_sources == ("keep",)
    assert assembly.dropped_sources == ("drop",)

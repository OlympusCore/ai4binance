"""Boundary coverage for the deterministic universe-liquidity gate."""

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

import pytest

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.data_quality_gate import DataQualityGate
from ai4binance.agents.registry import AgentDefinition, AgentStage
from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate
from ai4binance.schemas import AgentStatus
from tests.test_agents import snapshot


def definition() -> AgentDefinition:
    """Return the canonical definition used by the production gate."""
    return build_default_registry().get("universe_liquidity")


@pytest.mark.parametrize(
    ("invalid_definition", "message"),
    [
        (lambda: replace(definition(), name="risk"), "universe_liquidity definition"),
        (
            lambda: replace(definition(), stage=AgentStage.RISK),
            "universe_liquidity definition",
        ),
    ],
)
def test_universe_liquidity_gate_rejects_noncanonical_definitions(
    invalid_definition: Callable[[], AgentDefinition], message: str
) -> None:
    """Only the eligibility-stage universe definition may own this gate."""
    with pytest.raises(ValueError, match=message):
        UniverseLiquidityGate(invalid_definition())


@pytest.mark.parametrize("maximum_spread_ratio", [Decimal("0"), Decimal("1")])
def test_universe_liquidity_gate_rejects_invalid_spread_limits(
    maximum_spread_ratio: Decimal,
) -> None:
    """The deterministic spread threshold must stay inside its safe range."""
    with pytest.raises(ValueError, match="maximum_spread_ratio"):
        UniverseLiquidityGate(definition(), maximum_spread_ratio=maximum_spread_ratio)


def test_universe_liquidity_gate_fails_closed_on_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected evaluation failures become a deterministic blocked result."""
    gate = UniverseLiquidityGate(definition())

    def raise_internal_error(
        self: UniverseLiquidityGate, market_snapshot: object
    ) -> None:
        raise RuntimeError("simulated evaluation fault")

    monkeypatch.setattr(
        UniverseLiquidityGate, "evaluate_snapshot", raise_internal_error
    )
    data_quality = DataQualityGate(
        build_default_registry().get("data_quality")
    ).evaluate(snapshot())
    result = gate.evaluate(
        snapshot(),
        {"data_quality": data_quality},
    )

    assert result.status is AgentStatus.FAILED
    assert result.blockers == ("AGENT_INTERNAL_ERROR",)
    assert result.calculation_metadata == {"error_type": "RuntimeError"}


def test_universe_liquidity_gate_covers_missing_price_and_quote_paths() -> None:
    """Missing market primitives retain distinct eligibility blockers."""
    gate = UniverseLiquidityGate(definition())
    result = gate.evaluate_snapshot(
        replace(snapshot(), latest_price=None, bid=None, ask=None, spread=None)
    )

    assert result.status is AgentStatus.BLOCKED
    assert result.blockers == ("LATEST_PRICE_MISSING", "BID_ASK_SPREAD_MISSING")

    price_missing = gate.evaluate_snapshot(replace(snapshot(), latest_price=None))
    assert price_missing.blockers == ("LATEST_PRICE_MISSING",)

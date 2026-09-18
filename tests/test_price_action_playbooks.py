"""Deterministic research-only price-action playbook tests."""

from dataclasses import replace
from decimal import Decimal

import pytest

from ai4binance.domain import Action, CandidateStatus, ValidationStatus
from ai4binance.schemas import AgentStatus
from ai4binance.strategies.price_action import PriceActionPlaybookEngine
from tests.test_strategy_risk import evidence, snapshot


@pytest.mark.parametrize(
    ("setup", "direction", "action"),
    [
        ("pullback_continuation", 0.8, Action.BUY),
        ("breakout_retest", 0.8, Action.BUY),
        ("support_reclaim", 0.8, Action.BUY),
        ("resistance_rejection", -0.8, Action.SELL),
        ("failed_breakout_reversal", -0.8, Action.SELL),
    ],
)
def test_supported_playbooks_generate_research_candidates(
    setup: str,
    direction: float,
    action: Action,
) -> None:
    results = evidence(direction)
    results["price_action"] = replace(
        results["price_action"],
        detected_setups=(setup,),
    )

    candidate = PriceActionPlaybookEngine().generate(
        snapshot(inventory=action is Action.SELL),
        results,
    )[0]

    assert candidate.setup_name == setup
    assert candidate.action is action
    assert candidate.status is CandidateStatus.READY_FOR_RISK
    assert candidate.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert candidate.risk_reward == 2
    assert candidate.evidence[0] == f"PLAYBOOK_{setup.upper()}"


def test_sell_playbook_blocks_when_spot_inventory_is_unknown() -> None:
    results = evidence(-0.8)
    results["price_action"] = replace(
        results["price_action"],
        detected_setups=("resistance_rejection",),
    )

    candidate = PriceActionPlaybookEngine().generate(snapshot(), results)[0]

    assert candidate.status is CandidateStatus.RESEARCH_ONLY
    assert candidate.inventory_action == "REDUCE_EXISTING_SPOT_INVENTORY"
    assert candidate.blockers == ("INVENTORY_UNKNOWN_FOR_SPOT_SELL",)


def test_sell_playbook_uses_no_inventory_action_for_futures_market() -> None:
    results = evidence(-0.8)
    results["price_action"] = replace(
        results["price_action"],
        detected_setups=("resistance_rejection",),
    )

    candidate = PriceActionPlaybookEngine().generate(
        snapshot(market_type="USD_M_FUTURES"),
        results,
    )[0]

    assert candidate.status is CandidateStatus.READY_FOR_RISK
    assert candidate.inventory_action == "NONE"
    assert candidate.blockers == ()


def test_playbooks_reject_missing_setup_and_countertrend_continuation() -> None:
    assert PriceActionPlaybookEngine().generate(snapshot(), evidence(0.8)) == ()
    results = evidence(0.8)
    results["price_action"] = replace(
        results["price_action"],
        directional_vote=-0.8,
        detected_setups=("breakout_retest",),
    )

    assert PriceActionPlaybookEngine().generate(snapshot(), results) == ()


def test_strategy_engine_includes_detected_playbook_after_core_candidate() -> None:
    from ai4binance.strategies.engine import StrategyEngine

    results = evidence(0.8)
    results["price_action"] = replace(
        results["price_action"],
        detected_setups=("support_reclaim",),
    )

    candidates = StrategyEngine().generate(snapshot(), results)

    assert [item.setup_name for item in candidates] == [
        "support_reclaim",
        "trend_continuation",
    ]


def test_price_action_accepts_partial_confluence_and_canonical_setup() -> None:
    results = evidence(0.8)
    results["confluence"] = replace(
        results["confluence"],
        status=AgentStatus.PARTIAL,
    )
    results["breakout_retest"] = replace(
        results["price_action"],
        agent_name="breakout_retest",
        status=AgentStatus.PARTIAL,
        detected_setups=("BULLISH_BREAKOUT_RETEST",),
    )
    results["price_action"] = replace(
        results["price_action"],
        status=AgentStatus.NOT_APPLICABLE,
        applicable=False,
    )

    candidates = PriceActionPlaybookEngine().generate(snapshot(), results)

    assert [item.setup_name for item in candidates] == ["breakout_retest"]


def test_price_action_rejects_incomplete_or_unusable_preconditions() -> None:
    engine = PriceActionPlaybookEngine()
    results = evidence(0.8)
    assert engine.generate(replace(snapshot(), latest_price=None), results) == ()
    assert engine.generate(snapshot(), {"trend": results["trend"]}) == ()
    results["trend"] = replace(results["trend"], status=AgentStatus.FAILED)
    assert engine.generate(snapshot(), results) == ()
    results = evidence(0.8)
    results["price_action"] = replace(
        results["price_action"], detected_setups=("unsupported",)
    )
    assert engine.generate(snapshot(), results) == ()
    short_snapshot = replace(
        snapshot(),
        ohlcv_by_timeframe={"1h": snapshot().ohlcv_by_timeframe["1h"][:14]},
    )
    assert engine.generate(short_snapshot, results) == ()
    results = evidence(0.8)
    results["price_action"] = replace(
        results["price_action"],
        directional_vote=0.1,
        detected_setups=("support_reclaim",),
    )
    assert engine.generate(snapshot(), results) == ()


@pytest.mark.parametrize(
    ("setup", "direction", "price", "confluence_direction"),
    [
        ("support_reclaim", -0.8, "100", -0.8),
        ("resistance_rejection", 0.8, "100", 0.8),
        ("resistance_rejection", -0.8, "1", -0.8),
        ("support_reclaim", 0.8, "100", -0.8),
    ],
)
def test_price_action_rejects_invalid_setup_direction_and_conflicts(
    setup: str, direction: float, price: str, confluence_direction: float
) -> None:
    results = evidence(direction)
    results["price_action"] = replace(results["price_action"], detected_setups=(setup,))
    results["confluence"] = replace(
        results["confluence"], directional_vote=confluence_direction
    )

    assert (
        PriceActionPlaybookEngine().generate(
            replace(snapshot(), latest_price=Decimal(price)), results
        )
        == ()
    )


def test_price_action_uses_first_timeframe_and_rejects_bad_short_target() -> None:
    results = evidence(0.8)
    results["price_action"] = replace(
        results["price_action"],
        detected_setups=("support_reclaim",),
    )
    source = snapshot()
    no_one_hour = replace(
        source,
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": source.ohlcv_by_timeframe["1h"]},
    )

    candidate = PriceActionPlaybookEngine().generate(no_one_hour, results)[0]

    assert candidate.timeframe == "15m"

    short_results = evidence(-0.8)
    short_results["price_action"] = replace(
        short_results["price_action"],
        detected_setups=("failed_breakout_reversal",),
    )
    assert (
        PriceActionPlaybookEngine(target_multiplier=Decimal("100")).generate(
            replace(snapshot(inventory=True), latest_price=Decimal("100")),
            short_results,
        )
        == ()
    )

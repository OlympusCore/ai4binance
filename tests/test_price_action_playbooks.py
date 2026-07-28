"""Deterministic research-only price-action playbook tests."""

from dataclasses import replace

import pytest
from test_strategy_risk import evidence, snapshot

from ai4binance.domain import Action, CandidateStatus, ValidationStatus
from ai4binance.schemas import AgentStatus
from ai4binance.strategies.price_action import PriceActionPlaybookEngine


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
        "trend_continuation",
        "support_reclaim",
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

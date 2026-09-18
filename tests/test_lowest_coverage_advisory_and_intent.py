"""Fail-closed coverage for bounded advisory and virtual trade contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.agents.evaluation import AdvisoryFixtureProvider
from ai4binance.domain import Action
from ai4binance.local_agent.advisory_harness import (
    LocalAdvisoryFixtureHarness,
    LocalAdvisoryFixtureHarnessReport,
)
from ai4binance.research.virtual_runtime_trade_intent import VirtualTradeIntent

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def test_advisory_harness_contract_rejects_invalid_batch_and_report_states() -> None:
    with pytest.raises(ValueError, match="maximum is invalid"):
        LocalAdvisoryFixtureHarness(maximum_fixtures=0)
    with pytest.raises(ValueError, match="timestamp must be timezone-aware"):
        LocalAdvisoryFixtureHarness().run(
            (),
            cast(AdvisoryFixtureProvider, object()),
            started_at=datetime(2026, 9, 15),
        )

    run = SimpleNamespace(fixture_id="fixture-1", blockers=())
    values: dict[str, object] = {
        "fixture_runs": (run,),
        "status": "PASS",
        "blockers": (),
    }
    for overrides, message in (
        ({"fixture_runs": ()}, "requires runs"),
        ({"fixture_runs": (run, run)}, "must be unique"),
        ({"status": "BLOCKED"}, "status is invalid"),
        ({"execution_allowed": True}, "cannot promote or execute"),
    ):
        attempt = dict(values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            LocalAdvisoryFixtureHarnessReport(**attempt)  # type: ignore[arg-type]


def test_virtual_trade_intent_rejects_nonfillable_or_unsafe_contracts() -> None:
    values: dict[str, object] = {
        "snapshot_id": "snapshot-1",
        "decision_id": "decision-1",
        "candidate_id": "candidate-1",
        "symbol": "BTCUSDT",
        "market": "spot",
        "action": Action.BUY,
        "quantity": Decimal("1"),
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("90"),
        "take_profit_levels": (Decimal("110"),),
        "reason_codes": ("RULE_MATCH",),
    }
    for overrides, message in (
        ({"symbol": " "}, "identity is required"),
        ({"reason_codes": ("DUPLICATE", "DUPLICATE")}, "must be unique"),
        ({"blockers": (" ",)}, "cannot contain blanks"),
        ({"action": Action.HOLD}, "must be BUY or SELL"),
        ({"market": "margin"}, "must be SPOT or USD_M_FUTURES"),
        ({"market": "USD_M_FUTURES"}, "requires explicit direction"),
        ({"quantity": Decimal("0")}, "requires positive geometry"),
    ):
        attempt = dict(values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            VirtualTradeIntent(**attempt)  # type: ignore[arg-type]

    intent = VirtualTradeIntent(**values)  # type: ignore[arg-type]
    assert intent.market == "SPOT"

"""Deterministic persistence tests for independent virtual wallets."""

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.application import VirtualPortfolioState
from ai4binance.virtual_wallet_journal import (
    VirtualWalletJournal,
    VirtualWalletJournalError,
)

NOW = datetime(2026, 9, 12, 13, 0, tzinfo=UTC)


def _journal(tmp_path: Path) -> VirtualWalletJournal:
    return VirtualWalletJournal(
        ledger_path=tmp_path / "runtime" / "logs" / "virtual-wallet.jsonl",
        state_path=tmp_path / "runtime" / "state" / "virtual-wallets.json",
        report_root=tmp_path,
    )


def test_virtual_wallet_journal_initializes_independent_wallets_and_report(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)

    portfolios = journal.initialize(NOW)

    assert portfolios.spot.portfolio_id == "virtual-wallet:spot"
    assert portfolios.spot.market == "SPOT"
    assert portfolios.spot.equity_usdt == Decimal("1000")
    assert portfolios.futures.portfolio_id == "virtual-wallet:futures"
    assert portfolios.futures.market == "USD_M_FUTURES"
    assert portfolios.futures.equity_usdt == Decimal("1000")
    state = json.loads(journal.state_path.read_text(encoding="utf-8"))
    assert state["movement_count"] == 2
    assert state["balance_change_count"] == 0
    assert state["execution_allowed"] is False
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    report = (
        tmp_path / "runtime" / "reports" / "virtual_wallets" / "latest.md"
    ).read_text(encoding="utf-8")
    assert "Virtual_Spot_Wallet" in report
    assert "Virtual_Futures_Wallet" in report
    assert "2026-09-12T13:00:00+00:00" in report


def test_daily_loss_tuning_trigger_requires_three_losses_in_same_utc_day() -> None:
    from ai4binance import virtual_wallet_journal as module

    def movement(index: int, *, pnl: str, exit_at: datetime) -> dict[str, object]:
        return {
            "movement_id": f"movement:{index}",
            "market": "SPOT",
            "closed_trade": {
                "trade_id": f"trade:{index}",
                "exit_time": exit_at.isoformat(),
                "net_pnl_usdt": pnl,
            },
            "managed_position": {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy_id": "trend_continuation",
                "strategy_version": "1",
                "strategy_config_hash": "a" * 64,
                "entry_price": "100",
                "initial_quantity": "1",
            },
        }

    prior = movement(0, pnl="-2", exit_at=NOW - timedelta(days=1))
    first = movement(1, pnl="-1", exit_at=NOW - timedelta(hours=2))
    win = movement(2, pnl="3", exit_at=NOW - timedelta(hours=1))
    second = movement(3, pnl="-2", exit_at=NOW - timedelta(minutes=30))
    before = module._daily_loss_tuning_trigger((prior, first, win, second), NOW)
    assert before["status"] == "NOT_TRIGGERED"
    assert before["loss_count_today"] == 2

    third = movement(4, pnl="-3", exit_at=NOW)
    triggered = module._daily_loss_tuning_trigger(
        (prior, first, win, second, third), NOW
    )
    repeated = module._daily_loss_tuning_trigger(
        (
            prior,
            first,
            win,
            second,
            third,
            movement(5, pnl="-4", exit_at=NOW),
        ),
        NOW,
    )

    assert triggered["status"] == "TRIGGERED"
    assert triggered["loss_threshold"] == 3
    assert triggered["loss_count_today"] == 3
    assert len(cast(list[object], triggered["losses"])) == 3
    assert len(cast(list[object], triggered["subjects"])) == 1
    assert repeated["trigger_id"] == triggered["trigger_id"]
    assert repeated["execution_allowed"] is False
    assert repeated["promotion_status"] == "RESEARCH_ONLY"
    assert repeated["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_virtual_wallet_journal_records_every_change_once_with_timestamp(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    portfolios = journal.initialize(NOW)
    after = replace(
        portfolios.spot,
        cash_usdt=Decimal("899"),
        equity_usdt=Decimal("999"),
        inventory_quantity=Decimal("100"),
        inventory_cost_basis_usdt=Decimal("100"),
        fees_paid_usdt=Decimal("1"),
    )
    decision = SimpleNamespace(
        status=SimpleNamespace(value="ORDER_READY"),
        trade_intent=SimpleNamespace(action=SimpleNamespace(value="BUY")),
        portfolio_before=portfolios.spot,
        portfolio_after=after,
    )

    first = journal.record_cycle(
        snapshot_id="snapshot:1",
        observed_at=NOW,
        decision=decision,
    )
    repeated = journal.record_cycle(
        snapshot_id="snapshot:1",
        observed_at=NOW,
        decision=decision,
    )

    assert first["movement_count"] == 3
    assert repeated["movement_count"] == 3
    assert repeated["balance_change_count"] == 1
    wallets = cast(Mapping[str, Mapping[str, object]], repeated["wallets"])
    spot = wallets["Virtual_Spot_Wallet"]
    assert spot["cash_usdt"] == "899"
    assert spot["equity_usdt"] == "999"
    lines = journal.ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    movement = json.loads(lines[-1])["payload"]["movement"]
    assert movement["timestamp"] == "2026-09-12T13:00:00+00:00"
    assert movement["equity_delta_usdt"] == "-1"
    assert movement["cash_delta_usdt"] == "-101"
    assert movement["trade_action"] == "BUY"
    report = (
        tmp_path / "runtime" / "reports" / "virtual_wallets" / "latest.md"
    ).read_text(encoding="utf-8")
    assert "VIRTUAL_SIMULATION_MOVEMENT" in report
    assert "| 2026-09-12T13:00:00+00:00 | Virtual_Spot_Wallet" in report


def test_virtual_wallet_dashboard_reports_period_changes_and_bounded_detail(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    portfolios = journal.initialize(NOW - timedelta(days=40))
    after_old = replace(
        portfolios.spot,
        cash_usdt=Decimal("900"),
        equity_usdt=Decimal("900"),
        realized_pnl_usdt=Decimal("-100"),
    )
    journal.record_cycle(
        snapshot_id="old-change",
        observed_at=NOW - timedelta(days=8),
        decision=SimpleNamespace(
            status=SimpleNamespace(value="CLOSED"),
            trade_intent=None,
            portfolio_before=portfolios.spot,
            portfolio_after=after_old,
        ),
    )
    after_recent = replace(
        after_old,
        cash_usdt=Decimal("990"),
        equity_usdt=Decimal("990"),
        realized_pnl_usdt=Decimal("-10"),
    )
    journal.record_cycle(
        snapshot_id="recent-change",
        observed_at=NOW - timedelta(hours=12),
        decision=SimpleNamespace(
            status=SimpleNamespace(value="CLOSED"),
            trade_intent=None,
            portfolio_before=after_old,
            portfolio_after=after_recent,
        ),
    )

    result = journal.dashboard_snapshot(NOW)

    spot = cast(
        Mapping[str, object],
        cast(Mapping[str, object], result["wallets"])["Virtual_Spot_Wallet"],
    )
    assert spot["inception_at"] == (NOW - timedelta(days=40)).isoformat()
    changes = cast(Mapping[str, Mapping[str, object]], spot["period_changes"])
    assert changes["daily"]["percent_change"] == "10.0"
    assert changes["weekly"]["percent_change"] == "10.0"
    assert changes["monthly"]["percent_change"] == "-1.00"
    assert all(item["coverage"] == "FULL_PERIOD" for item in changes.values())
    movements = cast(list[Mapping[str, object]], result["movements"])
    assert movements[0]["movement_id"] == "virtual-wallet:SPOT:recent-change"
    assert movements[0]["equity_after_usdt"] == "990"
    assert "before" not in movements[0]
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert result["trade_records"] == []


def test_dashboard_snapshot_exposes_only_complete_virtual_trade_records(
    tmp_path: Path,
) -> None:
    from ai4binance import virtual_wallet_journal as module

    journal = _journal(tmp_path)
    _open_bound_position(journal)

    result = journal.dashboard_snapshot(NOW)

    records = cast(list[Mapping[str, object]], result["trade_records"])
    assert len(records) == 1
    assert records[0]["symbol"] == "HOTUSDT"
    assert Decimal(str(records[0]["entry"])) == Decimal("100")
    assert Decimal(str(records[0]["stop_loss"])) == Decimal("95")
    take_profit_levels = cast(list[object], records[0]["take_profit_levels"])
    assert [Decimal(str(item)) for item in take_profit_levels] == [Decimal("110")]
    assert (
        module._trade_record_dashboard_row(
            {
                "timestamp": NOW.isoformat(),
                "market": "SPOT",
                "managed_position": {
                    "position_id": "incomplete",
                    "symbol": "HOTUSDT",
                    "market": "SPOT",
                    "opened_at": NOW.isoformat(),
                    "entry_price": "100",
                    "stop_loss": "95",
                    "take_profit_levels": [],
                    "position_side": "LONG",
                    "status": "OPEN",
                    "timeframe": "1h",
                    "initial_quantity": "1",
                    "remaining_quantity": "1",
                },
            }
        )
        is None
    )


def test_virtual_wallet_snapshot_supplies_risk_capital_before_evaluation(
    tmp_path: Path,
) -> None:
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.risk_gate import RiskGate
    from tests.test_strategy_risk import approved_candidate, snapshot

    journal = _journal(tmp_path)
    original = snapshot()
    prepared = journal.analysis_snapshot(original)
    gate = RiskGate(
        build_default_registry().get("risk"), candidates=(approved_candidate(),)
    )
    before = gate.evaluate_candidates(original)
    after = gate.evaluate_candidates(prepared)
    assert before.blockers == ("EQUITY_UNKNOWN",)
    assert after.calculation_metadata["approved"] is True
    assert not after.blockers
    assert not original.wallet_summary
    assert prepared.wallet_summary["source"] == "VIRTUAL_PORTFOLIO"
    assert prepared.wallet_summary["open_position_count"] == 0
    assert journal.analysis_snapshot(original).wallet_summary == prepared.wallet_summary
    with pytest.raises(VirtualWalletJournalError, match="PRIVATE_CONTEXT_REJECTED"):
        journal.analysis_snapshot(
            replace(original, wallet_summary={"equity_usdt": "9000"})
        )


def test_virtual_wallet_existing_inventory_is_not_assigned_to_scanned_symbol(
    tmp_path: Path,
) -> None:
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.risk_gate import RiskGate
    from tests.test_strategy_risk import approved_candidate, snapshot

    journal = _journal(tmp_path)
    original = snapshot()
    before = journal.initialize(original.created_at).spot
    after = replace(before, cash_usdt=Decimal("900"), inventory_quantity=Decimal("1"))
    journal.record_cycle(
        snapshot_id="inventory",
        observed_at=original.created_at,
        decision=SimpleNamespace(
            portfolio_before=before,
            portfolio_after=after,
            status=SimpleNamespace(value="ORDER_READY"),
            trade_intent=None,
        ),
    )
    prepared = journal.analysis_snapshot(original)
    result = RiskGate(
        build_default_registry().get("risk"), candidates=(approved_candidate(),)
    ).evaluate_candidates(prepared)
    assert not prepared.inventory_summary
    assert result.blockers == ("VIRTUAL_POSITION_IDENTITY_UNAVAILABLE",)
    assert journal.initialize(original.created_at).spot == after


def test_virtual_wallet_journal_rejects_state_drift(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    portfolios = journal.initialize(NOW)
    drifted = replace(portfolios.spot, cash_usdt=Decimal("999"))
    decision = SimpleNamespace(
        status=SimpleNamespace(value="ORDER_READY"),
        trade_intent=None,
        portfolio_before=drifted,
        portfolio_after=replace(drifted, equity_usdt=Decimal("999")),
    )

    with pytest.raises(VirtualWalletJournalError, match="VIRTUAL_WALLET_STATE_DRIFT"):
        journal.record_cycle(
            snapshot_id="snapshot:drift",
            observed_at=NOW,
            decision=decision,
        )


def test_virtual_wallet_journal_detects_tampering_and_missing_ledger(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    journal.initialize(NOW)
    rows = journal.ledger_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[-1])
    payload["payload"]["movement"]["equity_delta_usdt"] = "9999"
    rows[-1] = json.dumps(payload, sort_keys=True)
    journal.ledger_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(VirtualWalletJournalError):
        journal.initialize(NOW)

    clean = _journal(tmp_path / "missing")
    clean.initialize(NOW)
    clean.ledger_path.unlink()
    with pytest.raises(
        VirtualWalletJournalError,
        match="VIRTUAL_WALLET_LEDGER_MISSING_FOR_EXISTING_STATE",
    ):
        clean.initialize(NOW)


def test_virtual_portfolio_state_payload_round_trip_preserves_decimals() -> None:
    original = VirtualPortfolioState(
        portfolio_id="virtual-wallet:futures",
        market="USD_M_FUTURES",
        cash_usdt=Decimal("950.125"),
        equity_usdt=Decimal("999.875"),
        realized_pnl_usdt=Decimal("2.25"),
        unrealized_pnl_usdt=Decimal("-0.125"),
        fees_paid_usdt=Decimal("0.75"),
        funding_cost_usdt=Decimal("-0.25"),
    )

    restored = VirtualPortfolioState.from_payload(original.to_payload())

    assert restored == original


def _open_bound_position(journal: VirtualWalletJournal) -> None:
    from ai4binance.domain import Action
    from ai4binance.research.virtual_runtime import VirtualMarketRuntime
    from tests.test_virtual_runtime import approved_virtual_runtime_request

    request = approved_virtual_runtime_request(
        snapshot_id="entry",
        decision_id="decision",
        candidate_id="candidate",
        symbol="HOTUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        timeframe="1h",
        portfolio=journal.initialize(NOW).spot,
    )
    decision = VirtualMarketRuntime().evaluate(request)
    assert decision.status.value == "ORDER_READY"
    journal.record_cycle(
        snapshot_id="entry", observed_at=NOW, decision=decision, request=request
    )


def test_managed_wallet_restores_symbol_processes_closed_candles_once_and_closes(
    tmp_path: Path,
) -> None:
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.risk_gate import RiskGate
    from ai4binance.schemas import OHLCVCandle
    from tests.test_strategy_risk import approved_candidate, snapshot

    journal = _journal(tmp_path)
    _open_bound_position(journal)
    restarted = _journal(tmp_path)
    assert restarted.open_position_symbols() == ("HOTUSDT",)
    candle = OHLCVCandle(
        NOW,
        Decimal("100"),
        Decimal("102"),
        Decimal("99"),
        Decimal("101"),
        Decimal("1000"),
    )
    original = replace(
        snapshot(),
        created_at=NOW + timedelta(minutes=30),
        ohlcv_by_timeframe={"1h": (candle,)},
    )
    before = journal.ledger_path.read_bytes()
    prepared = restarted.analysis_snapshot(original)
    assert journal.ledger_path.read_bytes() == before
    assert Decimal(str(prepared.inventory_summary["quantity"])) == Decimal("1")
    risk = RiskGate(
        build_default_registry().get("risk"), candidates=(approved_candidate(),)
    )
    assert risk.evaluate_candidates(prepared).blockers == (
        "VIRTUAL_MANAGED_POSITION_ALREADY_OPEN",
    )
    other = restarted.analysis_snapshot(replace(original, symbol="BTCUSDT"))
    assert other.inventory_summary["quantity"] == "0"
    closed = replace(original, created_at=NOW + timedelta(hours=1))
    restarted.analysis_snapshot(closed)
    after = journal.ledger_path.read_bytes()
    assert after != before
    _journal(tmp_path).analysis_snapshot(closed)
    assert journal.ledger_path.read_bytes() == after
    stop = replace(
        candle,
        timestamp=NOW + timedelta(hours=1),
        low=Decimal("94"),
        close=Decimal("95"),
    )
    prepared = _journal(tmp_path).analysis_snapshot(
        replace(
            original,
            created_at=NOW + timedelta(hours=2),
            ohlcv_by_timeframe={"1h": (candle, stop)},
        )
    )
    assert prepared.inventory_summary["quantity"] == "0"
    assert prepared.wallet_summary["open_position_count"] == 0
    assert not _journal(tmp_path).open_position_symbols()
    last = json.loads(journal.ledger_path.read_text().splitlines()[-1])["payload"][
        "movement"
    ]
    assert last["closed_trade"] is not None
    assert last["execution_allowed"] is False
    assert last["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_managed_wallet_rejects_missing_candle_history_without_mutation(
    tmp_path: Path,
) -> None:
    from ai4binance.schemas import OHLCVCandle
    from tests.test_strategy_risk import snapshot

    journal = _journal(tmp_path)
    _open_bound_position(journal)
    before = journal.ledger_path.read_bytes()
    candle = OHLCVCandle(
        NOW + timedelta(hours=2),
        Decimal("100"),
        Decimal("102"),
        Decimal("94"),
        Decimal("95"),
        Decimal("1000"),
    )
    with pytest.raises(VirtualWalletJournalError, match="CANDLE_GAP"):
        journal.analysis_snapshot(
            replace(
                snapshot(),
                created_at=NOW + timedelta(hours=3),
                ohlcv_by_timeframe={"1h": (candle,)},
            )
        )
    assert journal.ledger_path.read_bytes() == before


def test_virtual_wallet_validation_rejects_authority_and_balance_drift(
    tmp_path: Path,
) -> None:
    from ai4binance import virtual_wallet_journal as module

    journal = _journal(tmp_path)
    journal.initialize(NOW)
    payload = json.loads(
        journal.ledger_path.read_text(encoding="utf-8").splitlines()[0]
    )["payload"]["movement"]
    for key, value, message in [
        ("market", "INVALID", "MARKET_INVALID"),
        ("execution_allowed", True, "EXECUTION_AUTHORITY_DRIFT"),
        ("promotion_status", "LIVE", "PROMOTION_AUTHORITY_DRIFT"),
        ("live_eligibility_status", "READY", "LIVE_AUTHORITY_DRIFT"),
        ("after", None, "AFTER_STATE_INVALID"),
        ("equity_delta_usdt", "999", "EQUITY_DELTA_DRIFT"),
        ("cash_delta_usdt", "999", "CASH_DELTA_DRIFT"),
    ]:
        invalid = dict(payload)
        invalid[key] = value
        with pytest.raises(ValueError, match=message):
            module._validated_movement(invalid)
    invalid = dict(payload)
    invalid["before"] = "bad"
    with pytest.raises(ValueError, match="BEFORE_STATE_INVALID"):
        module._validated_movement(invalid)
    with pytest.raises(ValueError, match="non-empty text"):
        module._required_text({}, "missing")
    with pytest.raises(ValueError, match="decimal"):
        module._required_decimal({"value": "bad"}, "value")
    with pytest.raises(ValueError, match="finite"):
        module._required_decimal({"value": "NaN"}, "value")
    with pytest.raises(ValueError, match="TIMESTAMP_INVALID"):
        module._utc_timestamp(datetime(2026, 1, 1))


def test_virtual_wallet_portfolio_builder_and_period_helpers(tmp_path: Path) -> None:
    from ai4binance import virtual_wallet_journal as module

    journal = _journal(tmp_path)
    journal.initialize(NOW)
    with pytest.raises(VirtualWalletJournalError, match="TIMESTAMP_INVALID"):
        journal.portfolio_builder(object(), SimpleNamespace(market_type="SPOT"))
    assert (
        journal.portfolio_builder(
            SimpleNamespace(created_at=NOW), SimpleNamespace(market_type="SPOT")
        ).market
        == "SPOT"
    )
    assert (
        journal.portfolio_builder(
            SimpleNamespace(created_at=NOW),
            SimpleNamespace(market_type="USD_M_FUTURES"),
        ).market
        == "USD_M_FUTURES"
    )
    with pytest.raises(VirtualWalletJournalError, match="MARKET_INVALID"):
        journal.portfolio_builder(
            SimpleNamespace(created_at=NOW), SimpleNamespace(market_type="BAD")
        )
    movement = journal._read_movements()[0]
    current = journal.initialize(NOW).spot
    assert (
        module._period_change((movement,), current, NOW - timedelta(days=1))["coverage"]
        == "SINCE_INCEPTION"
    )


def test_virtual_wallet_record_and_dashboard_fail_closed_paths(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    portfolios = journal.initialize(NOW)
    with pytest.raises(VirtualWalletJournalError, match="DECISION_STATE_INVALID"):
        journal.record_cycle(
            snapshot_id="bad", observed_at=NOW, decision=SimpleNamespace()
        )
    with pytest.raises(VirtualWalletJournalError, match="DECISION_IDENTITY_DRIFT"):
        journal.record_cycle(
            snapshot_id="bad",
            observed_at=NOW,
            decision=SimpleNamespace(
                portfolio_before=portfolios.spot,
                portfolio_after=portfolios.futures,
            ),
        )
    partial = _journal(tmp_path / "partial")
    with pytest.raises(VirtualWalletJournalError, match="PORTFOLIOS_INCOMPLETE"):
        partial.dashboard_snapshot(NOW)


def test_virtual_wallet_reader_rejects_corrupt_event_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(tmp_path)
    journal.ledger_path.parent.mkdir(parents=True)
    monkeypatch.setattr(type(journal._store), "verify_chain", lambda _self: None)
    cases = [
        ("[]\n", "EVENT_INVALID"),
        ('{"event_type":"BAD"}\n', "EVENT_TYPE_INVALID"),
        (
            '{"event_type":"VIRTUAL_WALLET_INITIALIZED","payload":null}\n',
            "EVENT_PAYLOAD_INVALID",
        ),
        (
            '{"event_type":"VIRTUAL_WALLET_INITIALIZED","payload":{"movement":null}}\n',
            "MOVEMENT_INVALID",
        ),
    ]
    for content, code in cases:
        journal.ledger_path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=code):
            journal._read_movements()


def test_virtual_wallet_reader_cross_event_invariants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance import virtual_wallet_journal as module

    journal = _journal(tmp_path)
    journal.initialize(NOW)
    base = json.loads(journal.ledger_path.read_text(encoding="utf-8").splitlines()[0])[
        "payload"
    ]["movement"]
    monkeypatch.setattr(type(journal._store), "verify_chain", lambda _self: None)
    monkeypatch.setattr(module, "_validated_movement", lambda payload: dict(payload))

    def write(movements: list[dict[str, object]]) -> None:
        journal.ledger_path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "event_type": "VIRTUAL_WALLET_INITIALIZED",
                        "timestamp": item.get("event_timestamp", item["timestamp"]),
                        "payload": {"movement": item},
                    }
                )
                for item in movements
            )
            + "\n",
            encoding="utf-8",
        )

    timestamp_drift = dict(base)
    write(
        [
            timestamp_drift
            | {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "event_timestamp": base["timestamp"],
            }
        ]
    )
    with pytest.raises(ValueError, match="EVENT_TIMESTAMP_DRIFT"):
        journal._read_movements()
    movement_type = dict(base)
    movement_type["movement_type"] = "VIRTUAL_SIMULATION_MOVEMENT"
    write([movement_type])
    with pytest.raises(ValueError, match="MOVEMENT_TYPE_DRIFT"):
        journal._read_movements()
    duplicate = dict(base)
    write([duplicate, duplicate])
    with pytest.raises(ValueError, match="MOVEMENT_DUPLICATE"):
        journal._read_movements()
    genesis = dict(base)
    genesis["movement_id"] = "second"
    write([base, genesis])
    with pytest.raises(ValueError, match="GENESIS_DUPLICATE"):
        journal._read_movements()
    with pytest.raises(ValueError, match="POSITION_PAYLOAD_INVALID"):
        module.VirtualWalletJournal._latest_positions(
            ({"market": "SPOT", "managed_position": "invalid"},)
        )


def test_virtual_wallet_managed_position_rejections(tmp_path: Path) -> None:
    from ai4binance.schemas import DataQuality
    from tests.test_strategy_risk import snapshot

    journal = _journal(tmp_path)
    _open_bound_position(journal)
    original = snapshot()
    with pytest.raises(VirtualWalletJournalError, match="DATA_INVALID"):
        journal.manage_positions(
            replace(original, data_quality=DataQuality.DATA_INVALID)
        )
    with pytest.raises(VirtualWalletJournalError, match="CANDLES_MISSING"):
        journal.manage_positions(replace(original, ohlcv_by_timeframe={}))
    candles = original.ohlcv_by_timeframe["1h"]
    gapped = replace(candles[1], timestamp=candles[1].timestamp + timedelta(hours=1))
    with pytest.raises(VirtualWalletJournalError, match="CANDLE_GAP"):
        journal.manage_positions(
            replace(original, ohlcv_by_timeframe={"1h": (candles[0], gapped)})
        )
    movement = next(
        item for item in journal._read_movements() if item.get("managed_position")
    )
    identity = dict(movement)
    identity["market"] = "USD_M_FUTURES"
    with pytest.raises(ValueError, match="POSITION_IDENTITY_DRIFT"):
        journal._latest_positions((identity,))
    quantity = dict(movement)
    after = dict(cast(Mapping[str, object], quantity["after"]))
    after["inventory_quantity"] = "999"
    quantity["after"] = after
    with pytest.raises(ValueError, match="POSITION_QUANTITY_DRIFT"):
        journal._latest_positions((quantity,))


def test_virtual_wallet_futures_context_and_empty_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_strategy_risk import snapshot

    journal = _journal(tmp_path)
    _open_bound_position(journal)
    _position, cursor = journal._latest_positions(journal._read_movements())["SPOT"]
    monkeypatch.setattr(
        type(journal),
        "_latest_positions",
        staticmethod(
            lambda _movements: {
                "SPOT": (
                    SimpleNamespace(market="USD_M_FUTURES", symbol="HOTUSDT"),
                    cursor,
                )
            }
        ),
    )
    with pytest.raises(VirtualWalletJournalError, match="FUTURES_LIFECYCLE_CONTEXT"):
        journal.manage_positions(snapshot())
    empty = _journal(tmp_path / "empty")
    empty.ledger_path.parent.mkdir(parents=True)
    empty.ledger_path.write_text("", encoding="utf-8")
    assert empty._read_movements() == ()

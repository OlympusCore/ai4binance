"""Coverage tests for file-backed accounting reconciliation edge cases."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.accounting import reconciliation
from ai4binance.accounting.records import BinanceAccountLedger, ProductType

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def test_reconciliation_helpers_cover_invalid_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malformed = tmp_path / "events.jsonl"
    malformed.write_text(
        '\nnot-json\n[]\n{"payload": {"order_id": "a", "status": "NEW"}}\n',
        encoding="utf-8",
    )
    assert reconciliation._read_events(malformed) == (
        {"payload": {"order_id": "a", "status": "NEW"}},
    )
    assert reconciliation._latest_by_id(
        malformed, id_field="order_id", value_field="status"
    ) == {"a": "NEW"}
    assert (
        reconciliation._latest_position_amounts(malformed, value_field="position_amt")
        == {}
    )
    assert (
        reconciliation._latest_source_at(
            ({"payload": "bad"}, {"payload": {"envelope": "bad"}}),
            ProductType.SPOT,
            "REST",
        )
        is None
    )
    assert reconciliation._parse_time(None) is None
    assert reconciliation._parse_time("bad-date") is None
    assert reconciliation._parse_time("2026-09-16T12:00:00") is None
    assert reconciliation._optional_decimal(None) is None
    assert reconciliation._optional_decimal("NaN") is None
    assert reconciliation._difference("same", "same") == ()
    assert reconciliation._difference("2.5", "1") == Decimal("1.5")

    original = Path.read_text

    def raises_os_error(self: Path, *, encoding: str) -> str:
        if self == malformed:
            raise OSError("unreadable")
        return original(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", raises_os_error)
    assert reconciliation._read_events(malformed) == ()


def test_reconciler_records_stale_streams_mismatches_and_duplicates(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct")
    raw = ledger.root / "shared" / "raw_api_events.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        json.dumps(
            {
                "timestamp": "2026-09-16T11:58:00+00:00",
                "payload": {
                    "received_at": "2026-09-16T11:58:00+00:00",
                    "envelope": {"product_type": "SPOT", "source_type": "REST"},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for relative, rows in {
        "spot/orders.jsonl": [{"payload": {"order_id": "one", "status": "NEW"}}],
        "spot/order_events.jsonl": [
            {"payload": {"order_id": "one", "order_status": "FILLED"}}
        ],
        "futures_usdm/orders.jsonl": [
            {"payload": {"order_id": "two", "status": "NEW"}}
        ],
        "futures_usdm/order_events.jsonl": [
            {"payload": {"order_id": "two", "order_status": "NEW"}}
        ],
        "futures_usdm/positions_current.jsonl": [
            {
                "payload": {
                    "symbol": "BTCUSDT",
                    "position_side": "LONG",
                    "position_amt": "1",
                }
            }
        ],
        "futures_usdm/position_events.jsonl": [
            {
                "payload": {
                    "symbol": "BTCUSDT",
                    "position_side": "LONG",
                    "new_position_amt": "2",
                }
            }
        ],
    }.items():
        path = ledger.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )
    reconciler = reconciliation.AccountingFileReconciler(ledger, freshness_seconds=30)
    first = reconciler.reconcile_latest(
        snapshot_id="s", sync_run_id="r", observed_at=NOW
    )
    second = reconciler.reconcile_latest(
        snapshot_id="s", sync_run_id="r", observed_at=NOW
    )
    assert first.status == "DEGRADED"
    assert first.accepted_count > 0
    assert second.duplicate_count == first.accepted_count
    assert any("MISMATCH" in blocker for blocker in first.blockers)
    assert any("MISSING_OR_STALE" in blocker for blocker in first.blockers)
    with pytest.raises(ValueError, match="timezone-aware"):
        reconciler.reconcile_latest(
            snapshot_id="s2", sync_run_id="r2", observed_at=datetime(2026, 9, 16, 12, 0)
        )


def test_compare_entity_reports_difference() -> None:
    record = reconciliation._compare_entity(
        ProductType.SPOT, "ORDER", "one", "NEW", "FILLED", NOW
    )
    assert record.severity == "WARNING"
    assert record.difference == ("NEW", "FILLED")

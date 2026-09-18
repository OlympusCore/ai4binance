from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.data.aggtrades import (
    AggregateTrade,
    build_aggregate_trade_revision,
    reconcile_candle_trades,
)
from ai4binance.schemas import OHLCVCandle


def _trade(identifier: int, price: str, quantity: str, second: int) -> AggregateTrade:
    return AggregateTrade(
        aggregate_trade_id=identifier,
        price=Decimal(price),
        quantity=Decimal(quantity),
        first_trade_id=identifier,
        last_trade_id=identifier,
        timestamp=datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC),
        buyer_is_maker=identifier % 2 == 0,
    )


def test_aggregate_trade_revision_is_deterministic_and_fail_closed() -> None:
    trades = (_trade(10, "1", "2", 0), _trade(11, "1.2", "3", 1))
    first = build_aggregate_trade_revision(
        symbol="HOTUSDT",
        dataset_revision_id="dataset:abc",
        trades=trades,
        source_sha256=("a" * 64,),
    )
    second = build_aggregate_trade_revision(
        symbol="HOTUSDT",
        dataset_revision_id="dataset:abc",
        trades=trades,
        source_sha256=("a" * 64,),
    )

    assert first == second
    assert first.trade_count == 2
    assert first.aggressive_buy_ratio == pytest.approx(0.6)
    assert first.execution_allowed is False


def test_aggregate_trade_revision_reports_id_gaps() -> None:
    report = build_aggregate_trade_revision(
        symbol="HOTUSDT",
        dataset_revision_id="dataset:abc",
        trades=(_trade(10, "1", "1", 0), _trade(12, "1", "1", 1)),
        source_sha256=("b" * 64,),
    )

    assert report.aggregate_id_gap_count == 1
    assert report.blockers == ("AGGREGATE_TRADE_ID_GAPS_PRESENT",)


def test_candle_trade_reconciliation_passes_exact_public_evidence() -> None:
    candle = OHLCVCandle(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("1.2"),
        low=Decimal("0.9"),
        close=Decimal("1.1"),
        volume=Decimal("10"),
    )
    trades = (
        _trade(1, "1", "2", 0),
        _trade(2, "1.2", "3", 1),
        _trade(3, "0.9", "4", 2),
        _trade(4, "1.1", "1", 3),
    )

    report = reconcile_candle_trades(candle, trades, duration=timedelta(minutes=15))

    assert report.status == "PASSED"
    assert report.blockers == ()
    assert report.execution_allowed is False


def test_candle_trade_reconciliation_blocks_missing_and_drifted_evidence() -> None:
    candle = OHLCVCandle(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("1.2"),
        low=Decimal("0.9"),
        close=Decimal("1.1"),
        volume=Decimal("10"),
    )
    missing = reconcile_candle_trades(candle, (), duration=timedelta(minutes=15))
    drifted = reconcile_candle_trades(
        candle, (_trade(1, "1", "1", 0),), duration=timedelta(minutes=15)
    )

    assert missing.blockers == ("AGGREGATE_TRADES_MISSING",)
    assert set(drifted.blockers) == {
        "CANDLE_TRADE_OHLC_MISMATCH",
        "CANDLE_TRADE_VOLUME_MISMATCH",
    }


def test_aggregate_trade_contracts_reject_invalid_identity_and_ordering() -> None:
    with pytest.raises(ValueError, match="identifiers"):
        _trade(-1, "1", "1", 0)
    with pytest.raises(ValueError, match="positive"):
        AggregateTrade(1, Decimal("0"), Decimal("1"), 1, 1, datetime.now(UTC), True)
    first, second = _trade(2, "1", "1", 1), _trade(1, "1", "1", 2)
    with pytest.raises(ValueError, match="ID ordered"):
        build_aggregate_trade_revision(
            symbol="HOTUSDT",
            dataset_revision_id="dataset:x",
            trades=(first, second),
            source_sha256=("a" * 64,),
        )
    with pytest.raises(ValueError, match="timestamps"):
        build_aggregate_trade_revision(
            symbol="HOTUSDT",
            dataset_revision_id="dataset:x",
            trades=(_trade(1, "1", "1", 2), _trade(2, "1", "1", 1)),
            source_sha256=("a" * 64,),
        )


def test_reconciliation_rejects_out_of_window_trade_and_invalid_duration() -> None:
    candle = OHLCVCandle(
        datetime(2026, 1, 1, tzinfo=UTC),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
    )
    outside = replace(
        _trade(1, "1", "1", 0), timestamp=datetime(2026, 1, 2, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="outside"):
        reconcile_candle_trades(candle, (outside,), duration=timedelta(minutes=15))
    with pytest.raises(ValueError, match="duration"):
        reconcile_candle_trades(candle, (), duration=timedelta(0))


@pytest.mark.parametrize(
    ("symbol", "dataset_revision", "checksums", "match"),
    [
        ("bad-symbol", "dataset:x", ("a" * 64,), "symbol"),
        ("HOTUSDT", "wrong:x", ("a" * 64,), "dataset revision"),
        ("HOTUSDT", "dataset:x", (), "required"),
        ("HOTUSDT", "dataset:x", ("short",), "checksum"),
    ],
)
def test_aggregate_revision_rejects_invalid_provenance(
    symbol: str,
    dataset_revision: str,
    checksums: tuple[str, ...],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_aggregate_trade_revision(
            symbol=symbol,
            dataset_revision_id=dataset_revision,
            trades=(_trade(1, "1", "1", 0),),
            source_sha256=checksums,
        )

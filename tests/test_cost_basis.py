"""Read-only trade history and fee-aware Spot cost basis tests."""

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from test_private_security import RecordingTransport, factory

from ai4binance.exchange.private import BinancePrivateAccountReader
from ai4binance.portfolio.cost_basis import CostBasisService


def trade(
    trade_id: int,
    *,
    buyer: bool,
    qty: str,
    quote: str,
    fee: str = "0",
    fee_asset: str = "USDT",
) -> dict[str, object]:
    return {
        "id": trade_id,
        "price": str(Decimal(quote) / Decimal(qty)),
        "qty": qty,
        "quoteQty": quote,
        "commission": fee,
        "commissionAsset": fee_asset,
        "isBuyer": buyer,
        "time": trade_id,
    }


class History:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object:
        assert symbol == "HOTUSDT"
        assert from_id is None
        assert limit == 1_000
        return self.rows


def test_private_reader_adds_signed_read_only_trade_history() -> None:
    transport = RecordingTransport()
    reader = BinancePrivateAccountReader(factory(), transport)
    assert reader.trades("hotusdt", from_id=7, limit=10) == {"ok": True}
    request = transport.requests[0]
    parsed = urlparse(request.full_url)
    query = parse_qs(parsed.query)
    assert request.method == "GET"
    assert parsed.path == "/api/v3/myTrades"
    assert query["symbol"] == ["HOTUSDT"]
    assert query["fromId"] == ["7"]


def test_weighted_average_cost_realized_pnl_and_quote_fees() -> None:
    rows = [
        trade(1, buyer=True, qty="10", quote="10", fee="0.1"),
        trade(2, buyer=True, qty="10", quote="30", fee="0.3"),
        trade(3, buyer=False, qty="5", quote="15", fee="0.15"),
    ]
    report = CostBasisService(History(rows)).evaluate("HOTUSDT", Decimal("15"))
    assert report.quantity == Decimal("15")
    assert report.average_cost_quote == Decimal("2.02")
    assert report.realized_pnl_quote == Decimal("4.75")
    assert report.quote_fees == Decimal("0.55")
    assert report.blockers == ()
    assert report.execution_allowed is False


def test_base_fee_changes_inventory_and_external_fee_is_blocked() -> None:
    rows = [
        trade(1, buyer=True, qty="10", quote="10", fee="1", fee_asset="HOT"),
        trade(2, buyer=True, qty="1", quote="1", fee="0.1", fee_asset="BNB"),
    ]
    report = CostBasisService(History(rows)).evaluate("HOTUSDT", Decimal("10"))
    assert report.quantity == Decimal("10")
    assert report.average_cost_quote == Decimal("1.1")
    assert report.blockers == ("TRADE_FEE_CONVERSION_UNAVAILABLE",)


def test_missing_history_and_wallet_mismatch_fail_closed() -> None:
    report = CostBasisService(History([])).evaluate("HOTUSDT", Decimal("10"))
    assert report.average_cost_quote is None
    assert report.blockers == (
        "WALLET_TRADE_HISTORY_QUANTITY_MISMATCH",
        "TRADE_HISTORY_UNAVAILABLE",
    )


def test_history_rejects_invalid_limit_and_malformed_rows() -> None:
    with pytest.raises(ValueError, match="limit"):
        BinancePrivateAccountReader(factory(), RecordingTransport()).trades(
            "HOTUSDT", limit=0
        )
    with pytest.raises(ValueError, match="price"):
        CostBasisService(History([{"id": 1}])).evaluate("HOTUSDT", Decimal("0"))

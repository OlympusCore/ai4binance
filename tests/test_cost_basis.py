"""Read-only trade history and fee-aware Spot cost basis tests."""

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from ai4binance.exchange.private import BinancePrivateAccountReader
from ai4binance.portfolio.cost_basis import (
    CostBasisReport,
    CostBasisService,
    SpotTradeFill,
)
from tests.test_private_security import RecordingTransport, factory


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
        assert from_id == 0
        assert limit == 1_000
        return self.rows


class PagedHistory:
    def __init__(self) -> None:
        self.calls: list[tuple[int | None, int]] = []

    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object:
        assert symbol == "HOTUSDT"
        assert from_id is not None
        self.calls.append((from_id, limit))
        pages = {
            0: [
                trade(0, buyer=True, qty="1", quote="1"),
                trade(1, buyer=True, qty="1", quote="2"),
            ],
            2: [trade(2, buyer=True, qty="1", quote="3")],
        }
        return pages.get(from_id, [])


class StalledHistory:
    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object:
        assert symbol == "HOTUSDT"
        return [
            trade(0, buyer=True, qty="1", quote="1"),
            trade(1, buyer=True, qty="1", quote="1"),
        ]


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


def test_cost_basis_reads_complete_history_from_oldest_trade_id() -> None:
    history = PagedHistory()

    report = CostBasisService(history).evaluate(
        "HOTUSDT",
        Decimal("3"),
        limit=2,
    )

    assert history.calls == [(0, 2), (2, 2)]
    assert report.trade_count == 3
    assert report.quantity == Decimal("3")
    assert report.average_cost_quote == Decimal("2")
    assert report.blockers == ()
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_cost_basis_pagination_failures_remain_blocked() -> None:
    stalled = CostBasisService(StalledHistory()).evaluate(
        "HOTUSDT",
        Decimal("2"),
        limit=2,
    )
    truncated = CostBasisService(
        PagedHistory(),
        maximum_history_pages=1,
    ).evaluate("HOTUSDT", Decimal("2"), limit=2)

    assert stalled.blockers == ("TRADE_HISTORY_PAGINATION_STALLED",)
    assert truncated.blockers == ("TRADE_HISTORY_PAGE_LIMIT_REACHED",)
    assert stalled.execution_allowed is False
    assert truncated.execution_allowed is False


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


def test_cost_basis_duplicate_oversell_and_invalid_net_acquired_fail_closed() -> None:
    rows = [
        trade(1, buyer=True, qty="1", quote="1", fee="1", fee_asset="HOT"),
        trade(2, buyer=True, qty="2", quote="4"),
        trade(2, buyer=True, qty="2", quote="4"),
        trade(3, buyer=False, qty="3", quote="9"),
    ]

    report = CostBasisService(History(rows)).evaluate("HOTUSDT", Decimal("0"))

    assert report.quantity == Decimal("0")
    assert report.average_cost_quote is None
    assert report.blockers == (
        "INVALID_NET_ACQUIRED_QUANTITY",
        "DUPLICATE_TRADE_ID",
        "SELL_EXCEEDS_RECONSTRUCTED_INVENTORY",
    )


def test_cost_basis_rejects_invalid_contracts_and_payload_shapes() -> None:
    with pytest.raises(ValueError, match="Spot trade fill is invalid"):
        SpotTradeFill(
            trade_id=-1,
            symbol="HOTUSDT",
            price=Decimal("1"),
            quantity=Decimal("1"),
            quote_quantity=Decimal("1"),
            commission=Decimal("0"),
            commission_asset="USDT",
            is_buyer=True,
            time_ms=0,
        )
    with pytest.raises(ValueError, match="cost basis report is invalid"):
        CostBasisReport(
            symbol="",
            base_asset="HOT",
            quote_asset="USDT",
            quantity=Decimal("0"),
            average_cost_quote=None,
            realized_pnl_quote=Decimal("0"),
            quote_fees=Decimal("0"),
            trade_count=0,
            blockers=(),
        )
    with pytest.raises(ValueError, match="average cost is invalid"):
        CostBasisReport(
            symbol="HOTUSDT",
            base_asset="HOT",
            quote_asset="USDT",
            quantity=Decimal("1"),
            average_cost_quote=Decimal("-1"),
            realized_pnl_quote=Decimal("0"),
            quote_fees=Decimal("0"),
            trade_count=0,
            blockers=(),
        )
    with pytest.raises(ValueError, match="wallet quantity"):
        CostBasisService(History([])).evaluate("HOTUSDT", Decimal("-1"))
    with pytest.raises(ValueError, match="maximum history pages"):
        CostBasisService(History([]), maximum_history_pages=0)
    with pytest.raises(ValueError, match="trade history limit"):
        CostBasisService(History([])).evaluate("HOTUSDT", Decimal("0"), limit=0)
    with pytest.raises(ValueError, match="trade history must be an array"):
        CostBasisService(_ScalarHistory()).evaluate("HOTUSDT", Decimal("0"))
    with pytest.raises(ValueError, match="trade history rows must be objects"):
        CostBasisService(_MixedHistory()).evaluate("HOTUSDT", Decimal("1"))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"id": True}, "id must be an integer"),
        (
            {**trade(1, buyer=True, qty="1", quote="1"), "id": "bad"},
            "id must be an integer",
        ),
        (
            {**trade(1, buyer=True, qty="1", quote="1"), "id": "-1"},
            "id cannot be negative",
        ),
        (
            {**trade(1, buyer=True, qty="1", quote="1"), "price": "bad"},
            "price must be decimal-compatible",
        ),
        (
            {**trade(1, buyer=True, qty="1", quote="1"), "qty": "-1"},
            "qty must be finite and non-negative",
        ),
        (
            {**trade(1, buyer=True, qty="1", quote="1"), "commissionAsset": ""},
            "commissionAsset must be text",
        ),
        (
            {**trade(1, buyer=True, qty="1", quote="1"), "isBuyer": "true"},
            "isBuyer must be boolean",
        ),
    ],
)
def test_cost_basis_rejects_malformed_trade_fields(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CostBasisService(History([payload])).evaluate("HOTUSDT", Decimal("1"))


@pytest.mark.parametrize(
    ("symbol", "message"),
    [
        ("HOT/USDT", "symbol must be ASCII alphanumeric"),
        ("USDT", "symbol quote asset is unsupported"),
        ("HOTTRY", "symbol quote asset is unsupported"),
    ],
)
def test_cost_basis_rejects_unsupported_or_malformed_symbols(
    symbol: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CostBasisService(History([])).evaluate(symbol, Decimal("0"))


class _ScalarHistory:
    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object:
        del symbol, from_id, limit
        return {"id": 1}


class _MixedHistory:
    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object:
        del symbol, from_id, limit
        return [trade(1, buyer=True, qty="1", quote="1"), 1]

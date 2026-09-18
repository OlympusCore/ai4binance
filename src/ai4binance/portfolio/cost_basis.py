"""Fee-aware weighted-average Spot cost basis from bounded complete history."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

ZERO = Decimal("0")
MATCH_TOLERANCE = Decimal("0.00000001")
DEFAULT_MAXIMUM_HISTORY_PAGES = 10


class SpotTradeHistoryReader(Protocol):
    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class SpotTradeFill:
    trade_id: int
    symbol: str
    price: Decimal
    quantity: Decimal
    quote_quantity: Decimal
    commission: Decimal
    commission_asset: str
    is_buyer: bool
    time_ms: int

    def __post_init__(self) -> None:
        if (
            self.trade_id < 0
            or not self.symbol
            or min(
                self.price,
                self.quantity,
                self.quote_quantity,
                self.commission,
            )
            < ZERO
            or self.price == ZERO
            or self.quantity == ZERO
            or not self.commission_asset
            or self.time_ms < 0
        ):
            raise ValueError("Spot trade fill is invalid")


@dataclass(frozen=True, slots=True)
class CostBasisReport:
    symbol: str
    base_asset: str
    quote_asset: str
    quantity: Decimal
    average_cost_quote: Decimal | None
    realized_pnl_quote: Decimal
    quote_fees: Decimal
    trade_count: int
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        values = (self.quantity, self.realized_pnl_quote, self.quote_fees)
        if (
            not self.symbol
            or not self.base_asset
            or not self.quote_asset
            or self.quantity < ZERO
            or any(not value.is_finite() for value in values)
            or self.trade_count < 0
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("cost basis report is invalid")
        if self.average_cost_quote is not None and (
            not self.average_cost_quote.is_finite() or self.average_cost_quote < ZERO
        ):
            raise ValueError("average cost is invalid")


@dataclass(frozen=True, slots=True)
class CostBasisService:
    reader: SpotTradeHistoryReader
    maximum_history_pages: int = DEFAULT_MAXIMUM_HISTORY_PAGES

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_history_pages, bool)
            or not 1 <= self.maximum_history_pages <= 100
        ):
            raise ValueError("maximum history pages must be between 1 and 100")

    def evaluate(
        self,
        symbol: str,
        wallet_quantity: Decimal,
        *,
        limit: int = 1_000,
    ) -> CostBasisReport:
        normalized = _symbol(symbol)
        base, quote = _assets(normalized)
        if not wallet_quantity.is_finite() or wallet_quantity < ZERO:
            raise ValueError("wallet quantity must be finite and non-negative")
        if isinstance(limit, bool) or not 1 <= limit <= 1_000:
            raise ValueError("trade history limit must be between 1 and 1000")
        fills, history_blockers = self._load_trade_history(normalized, limit)
        ordered = sorted(fills, key=lambda item: (item.time_ms, item.trade_id))
        quantity = ZERO
        cost = ZERO
        realized = ZERO
        quote_fees = ZERO
        blockers = list(history_blockers)
        seen: set[int] = set()
        for fill in ordered:
            if fill.trade_id in seen:
                blockers.append("DUPLICATE_TRADE_ID")
                continue
            seen.add(fill.trade_id)
            fee_base = fill.commission if fill.commission_asset == base else ZERO
            fee_quote = fill.commission if fill.commission_asset == quote else ZERO
            if fill.commission > ZERO and fill.commission_asset not in {base, quote}:
                blockers.append("TRADE_FEE_CONVERSION_UNAVAILABLE")
            quote_fees += fee_quote
            if fill.is_buyer:
                acquired = fill.quantity - fee_base
                if acquired <= ZERO:
                    blockers.append("INVALID_NET_ACQUIRED_QUANTITY")
                    continue
                quantity += acquired
                cost += fill.quote_quantity + fee_quote
                continue
            disposed = fill.quantity + fee_base
            if disposed > quantity:
                blockers.append("SELL_EXCEEDS_RECONSTRUCTED_INVENTORY")
                disposed = quantity
            if disposed <= ZERO:
                continue
            average = cost / quantity if quantity > ZERO else ZERO
            proceeds = fill.quote_quantity - fee_quote
            realized += proceeds - (average * disposed)
            quantity -= disposed
            cost -= average * disposed
        if abs(quantity - wallet_quantity) > MATCH_TOLERANCE:
            blockers.append("WALLET_TRADE_HISTORY_QUANTITY_MISMATCH")
        average_cost = cost / quantity if quantity > ZERO else None
        if not ordered:
            blockers.append("TRADE_HISTORY_UNAVAILABLE")
        return CostBasisReport(
            symbol=normalized,
            base_asset=base,
            quote_asset=quote,
            quantity=quantity,
            average_cost_quote=average_cost,
            realized_pnl_quote=realized,
            quote_fees=quote_fees,
            trade_count=len(ordered),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def _load_trade_history(
        self,
        symbol: str,
        limit: int,
    ) -> tuple[tuple[SpotTradeFill, ...], tuple[str, ...]]:
        fills: list[SpotTradeFill] = []
        from_id = 0
        for _ in range(self.maximum_history_pages):
            payload = self.reader.trades(symbol, from_id=from_id, limit=limit)
            if not isinstance(payload, (list, tuple)):
                raise ValueError("trade history must be an array")
            if len(payload) > limit:
                raise ValueError("trade history page exceeds requested limit")
            page = tuple(
                _fill(cast(Mapping[str, object], row), symbol)
                for row in cast(Sequence[object], payload)
                if isinstance(row, Mapping)
            )
            if len(page) != len(payload):
                raise ValueError("trade history rows must be objects")
            if any(fill.trade_id < from_id for fill in page):
                return tuple(fills), ("TRADE_HISTORY_PAGINATION_STALLED",)
            fills.extend(page)
            if len(page) < limit:
                return tuple(fills), ()
            next_from_id = max(fill.trade_id for fill in page) + 1
            if next_from_id <= from_id:
                return tuple(fills), ("TRADE_HISTORY_PAGINATION_STALLED",)
            from_id = next_from_id
        return tuple(fills), ("TRADE_HISTORY_PAGE_LIMIT_REACHED",)


def _fill(payload: Mapping[str, object], symbol: str) -> SpotTradeFill:
    return SpotTradeFill(
        trade_id=_integer(payload.get("id"), "id"),
        symbol=symbol,
        price=_decimal(payload.get("price"), "price"),
        quantity=_decimal(payload.get("qty"), "qty"),
        quote_quantity=_decimal(payload.get("quoteQty"), "quoteQty"),
        commission=_decimal(payload.get("commission", "0"), "commission"),
        commission_asset=_text(payload.get("commissionAsset"), "commissionAsset"),
        is_buyer=_boolean(payload.get("isBuyer"), "isBuyer"),
        time_ms=_integer(payload.get("time"), "time"),
    )


def _assets(symbol: str) -> tuple[str, str]:
    for quote in ("USDT", "FDUSD", "USDC", "BTC", "ETH", "BNB"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    raise ValueError("symbol quote asset is unsupported")


def _symbol(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or not normalized.isascii() or not normalized.isalnum():
        raise ValueError("symbol must be ASCII alphanumeric")
    return normalized


def _decimal(value: object, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be decimal-compatible") from None
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError(f"{name} must be finite and non-negative")
    return parsed


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if parsed < 0:
        raise ValueError(f"{name} cannot be negative")
    return parsed


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be text")
    return value.strip().upper()


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value

"""Strict read-only USD-M account normalization for advisory context only."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

from ai4binance.portfolio.orders import AccountOpenOrder, normalize_open_order


class FuturesAccountReader(Protocol):
    def account(self) -> object: ...

    def positions(self, symbol: str | None = None) -> object: ...

    def open_orders(self, symbol: str | None = None) -> object: ...


@dataclass(frozen=True, slots=True)
class FuturesPosition:
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    unrealized_pnl: Decimal
    mark_price: Decimal | None = None
    liquidation_price: Decimal | None = None
    leverage: int | None = None
    margin_type: str | None = None
    notional: Decimal | None = None
    isolated_margin: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("futures position symbol is required")
        non_negative = (
            self.entry_price,
            *(
                value
                for value in (self.mark_price, self.liquidation_price)
                if value is not None
            ),
            *(value for value in (self.isolated_margin,) if value is not None),
        )
        if any(not value.is_finite() or value < 0 for value in non_negative):
            raise ValueError("futures position prices and margin must be non-negative")
        signed = (self.quantity, self.unrealized_pnl, self.notional)
        if any(value is not None and not value.is_finite() for value in signed):
            raise ValueError("futures position values must be finite")
        if self.leverage is not None and self.leverage < 1:
            raise ValueError("futures position leverage must be positive")
        if self.margin_type is not None and not self.margin_type.strip():
            raise ValueError("futures position margin type cannot be empty")


@dataclass(frozen=True, slots=True)
class FuturesAccountSnapshot:
    captured_at: datetime
    symbol: str
    can_trade: bool
    total_wallet_balance: Decimal
    available_balance: Decimal
    positions: tuple[FuturesPosition, ...]
    open_orders: tuple[AccountOpenOrder, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("futures account timestamp must be timezone-aware")
        if not self.symbol.strip():
            raise ValueError("futures account identity is invalid")
        if min(self.total_wallet_balance, self.available_balance) < 0:
            raise ValueError("futures balances cannot be negative")
        if any(order.market != "USD_M_FUTURES" for order in self.open_orders):
            raise ValueError("Futures account contains a non-Futures order")

    @property
    def open_order_count(self) -> int:
        return len(self.open_orders)


@dataclass(frozen=True, slots=True)
class FuturesAccountSnapshotService:
    reader: FuturesAccountReader

    def capture(
        self,
        symbol: str,
        captured_at: datetime,
        *,
        account_wide: bool = False,
    ) -> FuturesAccountSnapshot:
        normalized = self._symbol(symbol)
        account = self._mapping(self.reader.account(), "futuresAccount")
        # The production signed reader intentionally accepts only plain symbols.
        # Delivery contracts contain an underscore, so fetch read-only account-wide
        # data and apply the requested-symbol filter locally.
        requested_symbol = None if account_wide or "_" in normalized else normalized
        positions = tuple(
            self._position(self._mapping(item, "position"))
            for item in self._sequence(
                self.reader.positions(requested_symbol), "positions"
            )
        )
        order_payloads = self._sequence(
            self.reader.open_orders(requested_symbol), "openOrders"
        )
        normalized_orders = tuple(
            normalize_open_order(
                self._mapping(item, "openOrder"), market="USD_M_FUTURES"
            )
            for item in order_payloads
        )
        return FuturesAccountSnapshot(
            captured_at=captured_at,
            symbol=normalized,
            can_trade=self._boolean(account.get("canTrade"), "canTrade"),
            total_wallet_balance=self._decimal(
                account.get("totalWalletBalance"), "totalWalletBalance"
            ),
            available_balance=self._decimal(
                account.get("availableBalance"), "availableBalance"
            ),
            positions=(
                positions
                if account_wide
                else tuple(item for item in positions if item.symbol == normalized)
            ),
            open_orders=(
                normalized_orders
                if account_wide
                else tuple(
                    item for item in normalized_orders if item.symbol == normalized
                )
            ),
        )

    @classmethod
    def _position(cls, payload: Mapping[str, object]) -> FuturesPosition:
        return FuturesPosition(
            symbol=cls._symbol(cls._text(payload.get("symbol"), "symbol")),
            quantity=cls._signed_decimal(payload.get("positionAmt"), "positionAmt"),
            entry_price=cls._decimal(payload.get("entryPrice"), "entryPrice"),
            unrealized_pnl=cls._signed_decimal(
                payload.get("unRealizedProfit"), "unRealizedProfit"
            ),
            mark_price=cls._optional_decimal(payload.get("markPrice"), "markPrice"),
            liquidation_price=cls._optional_decimal(
                payload.get("liquidationPrice"), "liquidationPrice"
            ),
            leverage=cls._optional_integer(payload.get("leverage"), "leverage"),
            margin_type=cls._optional_text(payload.get("marginType")),
            notional=cls._optional_signed_decimal(payload.get("notional"), "notional"),
            isolated_margin=cls._optional_decimal(
                payload.get("isolatedMargin"), "isolatedMargin"
            ),
        )

    @staticmethod
    def _mapping(value: object, name: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be an object")
        return cast(Mapping[str, object], value)

    @staticmethod
    def _sequence(value: object, name: str) -> Sequence[object]:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{name} must be an array")
        return cast(Sequence[object], value)

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be text")
        return value.strip()

    @staticmethod
    def _boolean(value: object, name: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be boolean")
        return value

    @classmethod
    def _decimal(cls, value: object, name: str) -> Decimal:
        parsed = cls._signed_decimal(value, name)
        if parsed < 0:
            raise ValueError(f"{name} must be non-negative")
        return parsed

    @staticmethod
    def _signed_decimal(value: object, name: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{name} must be decimal-compatible") from None
        if not parsed.is_finite():
            raise ValueError(f"{name} must be finite")
        return parsed

    @classmethod
    def _optional_decimal(cls, value: object, name: str) -> Decimal | None:
        if value is None or value == "":
            return None
        parsed = cls._signed_decimal(value, name)
        if parsed < 0:
            raise ValueError(f"{name} must be non-negative")
        return parsed

    @classmethod
    def _optional_signed_decimal(cls, value: object, name: str) -> Decimal | None:
        if value is None or value == "":
            return None
        return cls._signed_decimal(value, name)

    @staticmethod
    def _optional_integer(value: object, name: str) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError(f"{name} must be integer-compatible")
        try:
            parsed = int(str(value))
        except ValueError:
            raise ValueError(f"{name} must be integer-compatible") from None
        if str(parsed) != str(value).strip() or parsed < 1:
            raise ValueError(f"{name} must be a positive integer")
        return parsed

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("marginType must be text")
        return value.strip().upper()

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        parts = normalized.split("_")
        if not normalized or any(not part or not part.isalnum() for part in parts):
            raise ValueError("symbol must be alphanumeric with optional underscores")
        return normalized

"""Strict read-only wallet normalization with no order methods."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

from ai4binance.portfolio.orders import AccountOpenOrder, normalize_open_order


class PrivateAccountReader(Protocol):
    """Injectable signed-GET boundary; deliberately exposes no order operation."""

    def account(self) -> object: ...

    def open_orders(self, symbol: str | None = None) -> object: ...


@dataclass(frozen=True, slots=True)
class SpotBalance:
    asset: str
    free: Decimal
    locked: Decimal

    def __post_init__(self) -> None:
        if not self.asset.strip() or min(self.free, self.locked) < 0:
            raise ValueError("Spot balance is invalid")


@dataclass(frozen=True, slots=True)
class WalletSnapshot:
    captured_at: datetime
    account_status: str
    can_trade: bool
    balances: tuple[SpotBalance, ...]
    symbol: str
    open_orders: tuple[AccountOpenOrder, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("wallet timestamp must be timezone-aware")
        if not self.account_status.strip() or not self.symbol.strip():
            raise ValueError("wallet identity is required")
        if any(order.market != "SPOT" for order in self.open_orders):
            raise ValueError("Spot wallet contains a non-Spot order")

    @property
    def open_order_count(self) -> int:
        return len(self.open_orders)

    def balance(self, asset: str) -> SpotBalance | None:
        normalized = asset.strip().upper()
        return next((item for item in self.balances if item.asset == normalized), None)


@dataclass(frozen=True, slots=True)
class WalletSnapshotService:
    reader: PrivateAccountReader

    def capture(
        self,
        symbol: str,
        captured_at: datetime,
        *,
        account_wide: bool = False,
    ) -> WalletSnapshot:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        account = self._mapping(self.reader.account(), "account")
        balances_payload = self._sequence(account.get("balances"), "balances")
        balances = tuple(
            self._balance(self._mapping(item, "balance")) for item in balances_payload
        )
        if len({item.asset for item in balances}) != len(balances):
            raise ValueError("wallet balances must contain unique assets")
        order_payloads = self._sequence(
            self.reader.open_orders(None if account_wide else normalized_symbol),
            "openOrders",
        )
        orders = tuple(
            normalize_open_order(self._mapping(item, "openOrder"), market="SPOT")
            for item in order_payloads
        )
        return WalletSnapshot(
            captured_at=captured_at,
            account_status=self._text(account.get("accountType"), "accountType"),
            can_trade=self._boolean(account.get("canTrade"), "canTrade"),
            balances=balances,
            symbol=normalized_symbol,
            open_orders=orders,
        )

    @classmethod
    def _balance(cls, payload: Mapping[str, object]) -> SpotBalance:
        return SpotBalance(
            asset=cls._text(payload.get("asset"), "asset").upper(),
            free=cls._decimal(payload.get("free"), "free"),
            locked=cls._decimal(payload.get("locked"), "locked"),
        )

    @staticmethod
    def _mapping(value: object, field_name: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{field_name} must be an object")
        return cast(Mapping[str, object], value)

    @staticmethod
    def _sequence(value: object, field_name: str) -> Sequence[object]:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{field_name} must be an array")
        return cast(Sequence[object], value)

    @staticmethod
    def _text(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be text")
        return value.strip()

    @staticmethod
    def _boolean(value: object, field_name: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} must be boolean")
        return value

    @staticmethod
    def _decimal(value: object, field_name: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{field_name} must be decimal-compatible") from None
        if not parsed.is_finite() or parsed < 0:
            raise ValueError(f"{field_name} must be finite and non-negative")
        return parsed

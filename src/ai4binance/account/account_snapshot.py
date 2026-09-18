"""Unify REST wallet state and reconciliation evidence into one snapshot."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ai4binance.accounting import FileReconciliationSummary
from ai4binance.portfolio import FuturesAccountSnapshot, WalletSnapshot

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class SpotAssetSnapshot:
    asset: str
    free_qty: Decimal
    locked_qty: Decimal
    market_price: Decimal | None
    market_value_usdt: Decimal | None
    free_market_value_usdt: Decimal | None
    locked_market_value_usdt: Decimal | None
    data_as_of: datetime
    blockers: tuple[str, ...] = ()

    @property
    def total_qty(self) -> Decimal:
        return self.free_qty + self.locked_qty

    def __post_init__(self) -> None:
        if (
            not self.asset.strip()
            or self.data_as_of.tzinfo is None
            or self.data_as_of.utcoffset() is None
        ):
            raise ValueError("spot asset snapshot identity is invalid")
        values = (
            self.free_qty,
            self.locked_qty,
            *(value for value in (self.market_price,) if value is not None),
            *(value for value in (self.market_value_usdt,) if value is not None),
            *(value for value in (self.free_market_value_usdt,) if value is not None),
            *(value for value in (self.locked_market_value_usdt,) if value is not None),
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("spot asset snapshot values must be non-negative")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("spot asset blockers cannot be empty")


@dataclass(frozen=True, slots=True)
class FuturesCapitalSnapshot:
    wallet_balance: Decimal
    available_balance: Decimal
    margin_ratio: Decimal | None
    available_margin_ratio: Decimal | None
    position_count: int
    data_as_of: datetime
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.data_as_of.tzinfo is None or self.data_as_of.utcoffset() is None:
            raise ValueError("futures capital timestamp must be timezone-aware")
        values = (
            self.wallet_balance,
            self.available_balance,
            *(value for value in (self.margin_ratio,) if value is not None),
            *(value for value in (self.available_margin_ratio,) if value is not None),
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("futures capital values must be non-negative")
        if self.position_count < 0:
            raise ValueError("futures position count cannot be negative")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("futures capital blockers cannot be empty")


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    snapshot_id: str
    data_as_of: datetime
    spot_assets: tuple[SpotAssetSnapshot, ...]
    futures: FuturesCapitalSnapshot | None
    reconciliation_status: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def spot_value_usdt(self) -> Decimal:
        return sum(
            (
                asset.market_value_usdt
                for asset in self.spot_assets
                if asset.market_value_usdt is not None
            ),
            ZERO,
        )

    @property
    def futures_equity_usdt(self) -> Decimal:
        return self.futures.wallet_balance if self.futures is not None else ZERO

    @property
    def total_value_usdt(self) -> Decimal:
        return self.spot_value_usdt + self.futures_equity_usdt

    @property
    def spot_ratio(self) -> Decimal:
        if self.total_value_usdt <= ZERO:
            return ZERO
        return self.spot_value_usdt / self.total_value_usdt

    @property
    def futures_ratio(self) -> Decimal:
        if self.total_value_usdt <= ZERO:
            return ZERO
        return self.futures_equity_usdt / self.total_value_usdt

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("account snapshot identity is required")
        if self.data_as_of.tzinfo is None or self.data_as_of.utcoffset() is None:
            raise ValueError("account snapshot timestamp must be timezone-aware")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("account snapshot blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("account snapshot cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class AccountSnapshotBuilder:
    quote_assets: tuple[str, ...] = ("USDT", "USDC")

    def build(
        self,
        *,
        snapshot_id: str,
        data_as_of: datetime,
        spot_wallet: WalletSnapshot | None,
        futures_account: FuturesAccountSnapshot | None,
        prices_usdt: Mapping[str, Decimal],
        reconciliation: FileReconciliationSummary | None = None,
    ) -> AccountSnapshot:
        blockers: list[str] = []
        if spot_wallet is None:
            blockers.append("SPOT_WALLET_UNAVAILABLE")
            spot_assets: tuple[SpotAssetSnapshot, ...] = ()
        else:
            spot_assets = tuple(
                self._spot_asset(
                    balance.asset,
                    balance.free,
                    balance.locked,
                    prices_usdt,
                    data_as_of,
                )
                for balance in spot_wallet.balances
                if balance.free + balance.locked > ZERO
            )
            blockers.extend(
                blocker for asset in spot_assets for blocker in asset.blockers
            )
        futures = (
            None
            if futures_account is None
            else self._futures(futures_account, data_as_of)
        )
        if futures_account is None:
            blockers.append("FUTURES_ACCOUNT_UNAVAILABLE")
        if futures is not None:
            blockers.extend(futures.blockers)
        reconciliation_status = "UNKNOWN"
        if reconciliation is None:
            blockers.append("RECONCILIATION_REQUIRED")
        else:
            reconciliation_status = reconciliation.status
            blockers.extend(reconciliation.blockers)
        return AccountSnapshot(
            snapshot_id,
            data_as_of,
            spot_assets,
            futures,
            reconciliation_status,
            tuple(dict.fromkeys(blockers)),
        )

    def _spot_asset(
        self,
        asset: str,
        free_qty: Decimal,
        locked_qty: Decimal,
        prices_usdt: Mapping[str, Decimal],
        data_as_of: datetime,
    ) -> SpotAssetSnapshot:
        normalized = asset.strip().upper()
        blockers: list[str] = []
        price = ONE if normalized in self.quote_assets else prices_usdt.get(normalized)
        if price is None:
            blockers.append("VALUATION_PRICE_UNAVAILABLE")
        total = free_qty + locked_qty
        return SpotAssetSnapshot(
            normalized,
            free_qty,
            locked_qty,
            price,
            None if price is None else total * price,
            None if price is None else free_qty * price,
            None if price is None else locked_qty * price,
            data_as_of,
            tuple(blockers),
        )

    @staticmethod
    def _futures(
        account: FuturesAccountSnapshot,
        data_as_of: datetime,
    ) -> FuturesCapitalSnapshot:
        blockers: list[str] = []
        ratio = (
            account.available_balance / account.total_wallet_balance
            if account.total_wallet_balance > ZERO
            else None
        )
        if ratio is None:
            blockers.append("FUTURES_WALLET_EQUITY_UNAVAILABLE")
        return FuturesCapitalSnapshot(
            account.total_wallet_balance,
            account.available_balance,
            None,
            ratio,
            len(
                tuple(
                    position
                    for position in account.positions
                    if position.quantity != ZERO
                )
            ),
            data_as_of,
            tuple(blockers),
        )

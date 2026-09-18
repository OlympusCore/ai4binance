"""Coin-agnostic wallet and position context for opportunity governance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.portfolio.asset_policy import AssetPolicy
from ai4binance.portfolio.futures import FuturesAccountSnapshot
from ai4binance.portfolio.wallet import WalletSnapshot

ZERO = Decimal("0")
QUOTE_ASSETS = frozenset({"USDT", "USDC", "FDUSD", "BUSD"})


class PositionMarket(StrEnum):
    SPOT = "SPOT"
    USD_M_FUTURES = "USD_M_FUTURES"


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class CapitalSourceStatus(StrEnum):
    AVAILABLE_CASH = "AVAILABLE_CASH"
    REVIEWABLE_POSITION = "REVIEWABLE_POSITION"
    PROTECTED_REVIEW_REQUIRED = "PROTECTED_REVIEW_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PositionContextRecord:
    """Read-only position fact; a position is context, never a thesis."""

    asset: str
    market: PositionMarket
    side: PositionSide
    quantity: Decimal
    available_quantity: Decimal
    locked_quantity: Decimal = ZERO
    symbol: str | None = None
    notional_usdt: Decimal | None = None
    capital_source_status: CapitalSourceStatus = CapitalSourceStatus.UNAVAILABLE
    blockers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("position context asset is required")
        if self.quantity < ZERO or self.available_quantity < ZERO:
            raise ValueError("position context quantities cannot be negative")
        if self.locked_quantity < ZERO:
            raise ValueError("position context locked quantity cannot be negative")
        if self.notional_usdt is not None and (
            not self.notional_usdt.is_finite() or self.notional_usdt < ZERO
        ):
            raise ValueError("position context notional must be non-negative")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("position context cannot authorize execution")
        _require_unique_nonblank("position blockers", self.blockers)
        _require_unique_nonblank("position evidence refs", self.evidence_refs)


@dataclass(frozen=True, slots=True)
class PositionContextReport:
    """Coin-agnostic source-of-capital view used by DGE and reports."""

    records: tuple[PositionContextRecord, ...]
    blockers: tuple[str, ...]
    largest_asset: str | None = None
    concentration_ratio: Decimal | None = None
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_unique_nonblank("position context blockers", self.blockers)
        if self.concentration_ratio is not None and not (
            ZERO <= self.concentration_ratio <= Decimal("1")
        ):
            raise ValueError(
                "position concentration ratio must be between zero and one"
            )
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("position context report cannot promote or execute")


@dataclass(frozen=True, slots=True)
class PositionContextBuilder:
    """Build a wallet/position context without binding the system to one coin."""

    policy: AssetPolicy = field(default_factory=AssetPolicy)
    quote_asset: str = "USDT"

    def __post_init__(self) -> None:
        normalized_quote = self.quote_asset.strip().upper()
        if not normalized_quote or not normalized_quote.isalnum():
            raise ValueError("quote asset must be alphanumeric")
        object.__setattr__(self, "quote_asset", normalized_quote)

    def build(
        self,
        *,
        spot_wallet: WalletSnapshot | None,
        futures_account: FuturesAccountSnapshot | None = None,
        prices_usdt: Mapping[str, Decimal] | None = None,
    ) -> PositionContextReport:
        blockers: list[str] = []
        records: list[PositionContextRecord] = []
        if spot_wallet is None:
            blockers.append("SPOT_WALLET_CONTEXT_UNAVAILABLE")
        else:
            records.extend(self._spot_records(spot_wallet, prices_usdt))
        if futures_account is not None:
            records.extend(self._futures_records(futures_account))
        if not records:
            blockers.append("POSITION_CONTEXT_EMPTY")
        blockers.extend(blocker for record in records for blocker in record.blockers)
        largest_asset, concentration = _largest_known_exposure(records)
        if concentration is not None and concentration >= Decimal("0.80"):
            blockers.append("POSITION_CONCENTRATION_REVIEW_REQUIRED")
        return PositionContextReport(
            records=tuple(records),
            blockers=tuple(dict.fromkeys(blockers)),
            largest_asset=largest_asset,
            concentration_ratio=concentration,
        )

    def _spot_records(
        self,
        wallet: WalletSnapshot,
        prices_usdt: Mapping[str, Decimal] | None,
    ) -> tuple[PositionContextRecord, ...]:
        records: list[PositionContextRecord] = []
        for balance in wallet.balances:
            asset = balance.asset.strip().upper()
            quantity = balance.free + balance.locked
            if quantity <= ZERO:
                continue
            price = _price_for(asset, prices_usdt)
            quote_like = (
                asset in QUOTE_ASSETS or asset in self.policy.preferred_quote_assets
            )
            notional = (
                quantity
                if quote_like
                else price * quantity
                if price is not None
                else None
            )
            blockers: list[str] = ["POSITION_IS_CONTEXT_NOT_THESIS"]
            status = CapitalSourceStatus.UNAVAILABLE
            if balance.locked > ZERO:
                blockers.append("LOCKED_BALANCE_PRESENT")
            if quote_like and balance.free > ZERO:
                status = CapitalSourceStatus.AVAILABLE_CASH
            elif self.policy.is_protected(asset):
                status = CapitalSourceStatus.PROTECTED_REVIEW_REQUIRED
                blockers.extend(
                    (
                        "COIN_ATTACHMENT_BIAS_BLOCKED",
                        "PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE",
                    )
                )
            elif notional is None:
                blockers.append("POSITION_USDT_VALUATION_UNAVAILABLE")
            elif balance.free > ZERO:
                status = CapitalSourceStatus.REVIEWABLE_POSITION
                blockers.append("MANUAL_CAPITAL_RELEASE_REVIEW_REQUIRED")
            records.append(
                PositionContextRecord(
                    asset=asset,
                    market=PositionMarket.SPOT,
                    side=PositionSide.LONG,
                    quantity=quantity,
                    available_quantity=balance.free,
                    locked_quantity=balance.locked,
                    symbol=f"{asset}{self.quote_asset}" if not quote_like else asset,
                    notional_usdt=notional,
                    capital_source_status=status,
                    blockers=tuple(dict.fromkeys(blockers)),
                    evidence_refs=("spot_wallet",),
                )
            )
        return tuple(records)

    @staticmethod
    def _futures_records(
        account: FuturesAccountSnapshot,
    ) -> tuple[PositionContextRecord, ...]:
        records: list[PositionContextRecord] = []
        for position in account.positions:
            if position.quantity == ZERO:
                continue
            quantity = abs(position.quantity)
            notional = (
                abs(position.notional)
                if position.notional is not None
                else quantity * position.mark_price
                if position.mark_price is not None
                else None
            )
            blockers = [
                "POSITION_IS_CONTEXT_NOT_THESIS",
                "FUTURES_POSITION_REQUIRES_SEPARATE_RISK_MODEL",
                "FUTURES_OPPORTUNITY_NOT_SPOT_RECOVERY_TOOL",
            ]
            if position.mark_price is None:
                blockers.append("MARK_PRICE_UNAVAILABLE")
            if position.liquidation_price is None or position.liquidation_price <= ZERO:
                blockers.append("LIQUIDATION_PRICE_UNAVAILABLE")
            if position.leverage is None:
                blockers.append("LEVERAGE_UNAVAILABLE")
            records.append(
                PositionContextRecord(
                    asset=_asset_from_symbol(position.symbol),
                    market=PositionMarket.USD_M_FUTURES,
                    side=PositionSide.LONG
                    if position.quantity > ZERO
                    else PositionSide.SHORT,
                    quantity=quantity,
                    available_quantity=ZERO,
                    symbol=position.symbol,
                    notional_usdt=notional,
                    capital_source_status=CapitalSourceStatus.UNAVAILABLE,
                    blockers=tuple(dict.fromkeys(blockers)),
                    evidence_refs=("futures_account",),
                )
            )
        return tuple(records)


def _price_for(asset: str, prices_usdt: Mapping[str, Decimal] | None) -> Decimal | None:
    if prices_usdt is None:
        return None
    value = prices_usdt.get(asset)
    if value is None:
        return None
    if not value.is_finite() or value < ZERO:
        raise ValueError("position context prices must be finite and non-negative")
    return value


def _asset_from_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return normalized.removesuffix("USDT") or normalized


def _largest_known_exposure(
    records: tuple[PositionContextRecord, ...] | list[PositionContextRecord],
) -> tuple[str | None, Decimal | None]:
    exposures: dict[str, Decimal] = {}
    for record in records:
        if record.notional_usdt is None:
            continue
        exposures[record.asset] = (
            exposures.get(record.asset, ZERO) + record.notional_usdt
        )
    total = sum(exposures.values(), ZERO)
    if total <= ZERO or not exposures:
        return None, None
    largest_asset, largest_value = max(exposures.items(), key=lambda item: item[1])
    return largest_asset, largest_value / total


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

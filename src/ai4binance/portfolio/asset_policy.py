"""Deterministic asset policy and Spot balance classification."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.portfolio.wallet import SpotBalance

ZERO = Decimal("0")


class AssetClassification(StrEnum):
    CASH_EQUIVALENT = "CASH_EQUIVALENT"
    ACTIVE_POSITION = "ACTIVE_POSITION"
    PROTECTED_POSITION = "PROTECTED_POSITION"
    LOCKED = "LOCKED"
    FEE_RESERVE = "FEE_RESERVE"
    DUST = "DUST"
    ILLIQUID = "ILLIQUID"
    CONVERTIBLE = "CONVERTIBLE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class AssetPolicy:
    """User-owned asset policy; defaults keep assets reviewable, not protected."""

    protected_assets: tuple[str, ...] = ()
    fee_reserve_assets: tuple[str, ...] = ("BNB",)
    preferred_quote_assets: tuple[str, ...] = ("USDT", "USDC")
    dust_value_threshold_usdt: Decimal = Decimal("5")
    automatic_conversion_enabled: bool = False
    automatic_wallet_transfer_enabled: bool = False
    automatic_position_reduction_enabled: bool = False

    def __post_init__(self) -> None:
        protected = self._normalize_assets(self.protected_assets, "protected_assets")
        fee_reserves = self._normalize_assets(
            self.fee_reserve_assets, "fee_reserve_assets"
        )
        quotes = self._normalize_assets(
            self.preferred_quote_assets, "preferred_quote_assets"
        )
        if not quotes:
            raise ValueError("preferred_quote_assets must not be empty")
        if (
            not self.dust_value_threshold_usdt.is_finite()
            or self.dust_value_threshold_usdt < ZERO
        ):
            raise ValueError(
                "dust_value_threshold_usdt must be finite and non-negative"
            )
        object.__setattr__(self, "protected_assets", protected)
        object.__setattr__(self, "fee_reserve_assets", fee_reserves)
        object.__setattr__(self, "preferred_quote_assets", quotes)

    def is_protected(self, asset: str) -> bool:
        return self._normalize_asset(asset) in self.protected_assets

    def is_quote_asset(self, asset: str) -> bool:
        return self._normalize_asset(asset) in self.preferred_quote_assets

    @classmethod
    def _normalize_assets(cls, assets: tuple[str, ...], name: str) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(cls._normalize_asset(item) for item in assets))
        if any(not item for item in normalized):
            raise ValueError(f"{name} cannot contain empty assets")
        return normalized

    @staticmethod
    def _normalize_asset(asset: str) -> str:
        normalized = asset.strip().upper()
        if not normalized or not normalized.isalnum():
            raise ValueError("asset must be alphanumeric")
        return normalized


@dataclass(frozen=True, slots=True)
class AssetClassificationRecord:
    asset: str
    classification: AssetClassification
    classification_reason: str
    free: Decimal
    locked: Decimal
    estimated_value_usdt: Decimal | None = None
    available_for_new_spot_notional: Decimal = ZERO
    funding_eligible: bool = False

    def __post_init__(self) -> None:
        if not self.asset.strip() or not self.classification_reason.strip():
            raise ValueError("asset classification identity is required")
        if min(self.free, self.locked, self.available_for_new_spot_notional) < ZERO:
            raise ValueError("asset classification values cannot be negative")
        if self.estimated_value_usdt is not None and (
            not self.estimated_value_usdt.is_finite()
            or self.estimated_value_usdt < ZERO
        ):
            raise ValueError("estimated_value_usdt must be finite and non-negative")
        if (
            self.classification is AssetClassification.PROTECTED_POSITION
            and self.funding_eligible
        ):
            raise ValueError("protected assets cannot be funding eligible")


@dataclass(frozen=True, slots=True)
class AssetClassifier:
    policy: AssetPolicy = field(default_factory=AssetPolicy)

    def classify_spot_balance(
        self,
        balance: SpotBalance,
        *,
        prices_usdt: Mapping[str, Decimal] | None = None,
    ) -> AssetClassificationRecord:
        asset = balance.asset.strip().upper()
        total_quantity = balance.free + balance.locked
        price = self._price_for(asset, prices_usdt)
        value_usdt = (
            price * total_quantity
            if price is not None and asset not in self.policy.preferred_quote_assets
            else total_quantity
            if asset in self.policy.preferred_quote_assets
            else None
        )
        if asset in self.policy.protected_assets:
            return self._record(
                balance,
                AssetClassification.PROTECTED_POSITION,
                "PROTECTED_ASSET_POLICY",
                value_usdt,
            )
        if asset in self.policy.fee_reserve_assets:
            return self._record(
                balance,
                AssetClassification.FEE_RESERVE,
                "FEE_RESERVE_POLICY",
                value_usdt,
            )
        if asset in self.policy.preferred_quote_assets:
            reason = (
                "PREFERRED_QUOTE_ASSET_WITH_LOCKED_BALANCE"
                if balance.locked > ZERO
                else "PREFERRED_QUOTE_ASSET"
            )
            return self._record(
                balance,
                AssetClassification.CASH_EQUIVALENT,
                reason,
                value_usdt,
                available_for_new_spot_notional=balance.free,
                funding_eligible=True,
            )
        if balance.free <= ZERO and balance.locked > ZERO:
            return self._record(
                balance,
                AssetClassification.LOCKED,
                "LOCKED_BY_OPEN_ORDER",
                value_usdt,
            )
        if value_usdt is None:
            return self._record(
                balance,
                AssetClassification.UNSUPPORTED,
                "USDT_PRICE_UNAVAILABLE",
                value_usdt,
            )
        if value_usdt < self.policy.dust_value_threshold_usdt:
            return self._record(
                balance,
                AssetClassification.DUST,
                "BELOW_DUST_VALUE_THRESHOLD",
                value_usdt,
            )
        return self._record(
            balance,
            AssetClassification.CONVERTIBLE,
            "MANUAL_CONVERSION_REQUIRED",
            value_usdt,
            funding_eligible=self.policy.automatic_conversion_enabled,
        )

    def classify_spot_balances(
        self,
        balances: tuple[SpotBalance, ...],
        *,
        prices_usdt: Mapping[str, Decimal] | None = None,
    ) -> tuple[AssetClassificationRecord, ...]:
        return tuple(
            self.classify_spot_balance(balance, prices_usdt=prices_usdt)
            for balance in balances
        )

    @staticmethod
    def _price_for(
        asset: str, prices_usdt: Mapping[str, Decimal] | None
    ) -> Decimal | None:
        if prices_usdt is None:
            return None
        value = prices_usdt.get(asset)
        if value is None:
            return None
        if not value.is_finite() or value < ZERO:
            raise ValueError("asset prices must be finite and non-negative")
        return value

    @staticmethod
    def _record(
        balance: SpotBalance,
        classification: AssetClassification,
        reason: str,
        estimated_value_usdt: Decimal | None,
        *,
        available_for_new_spot_notional: Decimal = ZERO,
        funding_eligible: bool = False,
    ) -> AssetClassificationRecord:
        return AssetClassificationRecord(
            balance.asset.strip().upper(),
            classification,
            reason,
            balance.free,
            balance.locked,
            estimated_value_usdt,
            available_for_new_spot_notional,
            funding_eligible,
        )

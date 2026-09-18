"""Deterministic derivatives and open-interest feature engine."""

from dataclasses import dataclass
from decimal import Decimal

from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesFeatures,
    DerivativesMetric,
    PriceOiRegime,
)

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class DerivativesFeatureEngine:
    short_lookback: int = 1
    medium_lookback: int = 4

    def __post_init__(self) -> None:
        if self.short_lookback < 1 or self.medium_lookback <= self.short_lookback:
            raise ValueError("feature lookbacks must be positive and ordered")

    def compute(
        self,
        dataset: DerivativesDataset,
        prices: tuple[Decimal, ...],
    ) -> DerivativesFeatures:
        oi = dataset.values(DerivativesMetric.OPEN_INTEREST)
        blockers: list[str] = []
        if len(oi) <= self.medium_lookback or len(prices) != len(oi):
            blockers.append("OI_OR_PRICE_HISTORY_INSUFFICIENT")
        oi_short = self._change(oi, self.short_lookback)
        oi_medium = self._change(oi, self.medium_lookback)
        price_change = self._change(prices, self.medium_lookback)
        regime = self.regime(price_change, oi_medium)
        if not oi:
            blockers.append("OPEN_INTEREST_MISSING")
        funding = dataset.values(DerivativesMetric.FUNDING_RATE)
        basis = dataset.values(DerivativesMetric.BASIS_RATE)
        taker = dataset.values(DerivativesMetric.TAKER_BUY_SELL_RATIO)
        top = dataset.values(DerivativesMetric.TOP_POSITION_RATIO)
        global_ratio = dataset.values(DerivativesMetric.GLOBAL_ACCOUNT_RATIO)
        mark = dataset.values(DerivativesMetric.MARK_PRICE)
        index = dataset.values(DerivativesMetric.INDEX_PRICE)
        return DerivativesFeatures(
            symbol=dataset.symbol,
            as_of=dataset.as_of,
            oi_change_short=oi_short,
            oi_change_medium=oi_medium,
            oi_zscore=self._zscore(oi),
            oi_percentile=self._percentile(oi),
            price_oi_regime=regime,
            funding_percentile=self._percentile(funding),
            basis_zscore=self._zscore(basis),
            taker_imbalance=self._taker_imbalance(taker),
            top_vs_global_divergence=self._difference(top, global_ratio),
            mark_index_deviation=self._relative_difference(mark, index),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _change(values: tuple[Decimal, ...], lookback: int) -> Decimal | None:
        if len(values) <= lookback or values[-lookback - 1] == ZERO:
            return None
        return (values[-1] / values[-lookback - 1]) - ONE

    @staticmethod
    def _zscore(values: tuple[Decimal, ...]) -> Decimal | None:
        if len(values) < 2:
            return None
        mean = sum(values, ZERO) / Decimal(len(values))
        variance = sum(((value - mean) ** 2 for value in values), ZERO) / Decimal(
            len(values)
        )
        if variance == ZERO:
            return ZERO
        return (values[-1] - mean) / variance.sqrt()

    @staticmethod
    def _percentile(values: tuple[Decimal, ...]) -> Decimal | None:
        if not values:
            return None
        less_or_equal = sum(value <= values[-1] for value in values)
        return Decimal(less_or_equal) / Decimal(len(values))

    @staticmethod
    def regime(
        price_change: Decimal | None,
        oi_change: Decimal | None,
    ) -> PriceOiRegime:
        """Classify a Price/OI change pair without requiring full features."""
        if (
            price_change is None
            or oi_change is None
            or ZERO in {price_change, oi_change}
        ):
            return PriceOiRegime.FLAT_OR_MIXED
        if price_change > ZERO and oi_change > ZERO:
            return PriceOiRegime.NEW_LONG_PARTICIPATION
        if price_change > ZERO and oi_change < ZERO:
            return PriceOiRegime.SHORT_COVERING
        if price_change < ZERO and oi_change > ZERO:
            return PriceOiRegime.NEW_SHORT_PRESSURE
        return PriceOiRegime.DELEVERAGING

    @staticmethod
    def _taker_imbalance(values: tuple[Decimal, ...]) -> Decimal | None:
        if not values:
            return None
        ratio = values[-1]
        if ratio < ZERO:
            return None
        return (ratio - ONE) / (ratio + ONE) if ratio + ONE != ZERO else None

    @staticmethod
    def _difference(
        left: tuple[Decimal, ...], right: tuple[Decimal, ...]
    ) -> Decimal | None:
        return left[-1] - right[-1] if left and right else None

    @staticmethod
    def _relative_difference(
        left: tuple[Decimal, ...], right: tuple[Decimal, ...]
    ) -> Decimal | None:
        if not left or not right or right[-1] == ZERO:
            return None
        return (left[-1] - right[-1]) / right[-1]

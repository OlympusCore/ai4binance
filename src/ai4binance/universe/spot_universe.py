"""Dynamic Binance Spot universe prefilter."""

from dataclasses import dataclass, field

from ai4binance.universe.filters import (
    UniverseFilterPolicy,
    UniverseFilterResult,
    UniverseMarket,
    UniverseSymbol,
)


@dataclass(frozen=True, slots=True)
class SpotUniverseBuilder:
    policy: UniverseFilterPolicy = field(default_factory=UniverseFilterPolicy)

    def filter(
        self, symbols: tuple[UniverseSymbol, ...]
    ) -> tuple[UniverseFilterResult, ...]:
        return tuple(self._filter_one(symbol) for symbol in symbols)

    def accepted(
        self, symbols: tuple[UniverseSymbol, ...]
    ) -> tuple[UniverseSymbol, ...]:
        return tuple(
            result.symbol for result in self.filter(symbols) if result.accepted
        )

    def _filter_one(self, symbol: UniverseSymbol) -> UniverseFilterResult:
        blockers: list[str] = []
        if symbol.market is not UniverseMarket.SPOT:
            blockers.append("MARKET_NOT_SPOT")
        if symbol.status != "TRADING":
            blockers.append("SYMBOL_NOT_TRADING")
        if symbol.quote_asset not in self.policy.quote_assets:
            blockers.append("QUOTE_ASSET_NOT_ALLOWED")
        if symbol.quote_volume_24h_usdt < self.policy.minimum_24h_quote_volume_usdt:
            blockers.append("INSUFFICIENT_24H_VOLUME")
        if symbol.spread_bps > self.policy.maximum_spread_bps:
            blockers.append("SPREAD_EXCEEDS_LIMIT")
        if symbol.depth_0_5_pct_usdt < self.policy.minimum_depth_0_5_pct_usdt:
            blockers.append("INSUFFICIENT_ORDER_BOOK_DEPTH")
        if not symbol.data_quality_ok:
            blockers.append("DATA_INCOMPLETE")
        return UniverseFilterResult(
            symbol, not blockers, tuple(dict.fromkeys(blockers))
        )

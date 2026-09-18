"""Dynamic USD-M Futures universe prefilter kept separate from Spot."""

from dataclasses import dataclass, field

from ai4binance.universe.filters import (
    UniverseFilterPolicy,
    UniverseFilterResult,
    UniverseMarket,
    UniverseSymbol,
)


@dataclass(frozen=True, slots=True)
class FuturesUniverseBuilder:
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
        if symbol.market is not UniverseMarket.USD_M_FUTURES:
            blockers.append("MARKET_NOT_USD_M_FUTURES")
        if symbol.status != "TRADING":
            blockers.append("SYMBOL_NOT_TRADING")
        if symbol.contract_type != "PERPETUAL":
            blockers.append("CONTRACT_NOT_PERPETUAL")
        if symbol.margin_asset not in self.policy.futures_margin_assets:
            blockers.append("MARGIN_ASSET_NOT_ALLOWED")
        if symbol.quote_volume_24h_usdt < self.policy.minimum_24h_quote_volume_usdt:
            blockers.append("INSUFFICIENT_24H_VOLUME")
        if symbol.spread_bps > self.policy.maximum_spread_bps:
            blockers.append("SPREAD_EXCEEDS_LIMIT")
        if symbol.depth_0_5_pct_usdt < self.policy.minimum_depth_0_5_pct_usdt:
            blockers.append("INSUFFICIENT_ORDER_BOOK_DEPTH")
        if (
            symbol.open_interest_usdt is None
            or symbol.open_interest_usdt < self.policy.minimum_open_interest_usdt
        ):
            blockers.append("OPEN_INTEREST_INSUFFICIENT")
        if (
            symbol.funding_rate is None
            or abs(symbol.funding_rate) > self.policy.maximum_abs_funding_rate
        ):
            blockers.append("FUNDING_RATE_OUT_OF_POLICY")
        if not symbol.data_quality_ok:
            blockers.append("DATA_INCOMPLETE")
        return UniverseFilterResult(
            symbol, not blockers, tuple(dict.fromkeys(blockers))
        )

"""Coordinate Spot and Futures universe prefilters for bounded scans."""

from dataclasses import dataclass, field

from ai4binance.universe import (
    FuturesUniverseBuilder,
    SpotUniverseBuilder,
    UniverseFilterResult,
    UniverseMarket,
    UniverseSymbol,
)


@dataclass(frozen=True, slots=True)
class MultiSymbolScanReport:
    market: UniverseMarket | str
    results: tuple[UniverseFilterResult, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def accepted_symbols(self) -> tuple[str, ...]:
        return tuple(result.symbol.symbol for result in self.results if result.accepted)

    @property
    def rejected_symbols(self) -> tuple[str, ...]:
        return tuple(
            result.symbol.symbol for result in self.results if not result.accepted
        )

    def __post_init__(self) -> None:
        if any(not item.strip() for item in self.blockers):
            raise ValueError("scan report blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("scan report cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ScannerOrchestrator:
    spot_builder: SpotUniverseBuilder = field(default_factory=SpotUniverseBuilder)
    futures_builder: FuturesUniverseBuilder = field(
        default_factory=FuturesUniverseBuilder
    )

    def scan_spot(self, symbols: tuple[UniverseSymbol, ...]) -> MultiSymbolScanReport:
        if not symbols:
            return MultiSymbolScanReport(
                UniverseMarket.SPOT,
                (),
                ("SCANNER_INPUT_UNAVAILABLE",),
            )
        results = self.spot_builder.filter(symbols)
        return self._report(UniverseMarket.SPOT, results)

    def scan_futures(
        self, symbols: tuple[UniverseSymbol, ...]
    ) -> MultiSymbolScanReport:
        if not symbols:
            return MultiSymbolScanReport(
                UniverseMarket.USD_M_FUTURES,
                (),
                ("SCANNER_INPUT_UNAVAILABLE",),
            )
        results = self.futures_builder.filter(symbols)
        return self._report(UniverseMarket.USD_M_FUTURES, results)

    def scan_all(
        self,
        *,
        spot_symbols: tuple[UniverseSymbol, ...],
        futures_symbols: tuple[UniverseSymbol, ...],
    ) -> MultiSymbolScanReport:
        spot = self.scan_spot(spot_symbols)
        futures = self.scan_futures(futures_symbols)
        return MultiSymbolScanReport(
            "ALL",
            (*spot.results, *futures.results),
            tuple(dict.fromkeys((*spot.blockers, *futures.blockers))),
        )

    @staticmethod
    def _report(
        market: UniverseMarket,
        results: tuple[UniverseFilterResult, ...],
    ) -> MultiSymbolScanReport:
        blockers = tuple(
            dict.fromkeys(blocker for result in results for blocker in result.blockers)
        )
        return MultiSymbolScanReport(market, results, blockers)

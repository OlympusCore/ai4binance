"""External integration adapters for read-only AI4Binance boundaries."""

from ai4binance.integrations.research_market_universe import (
    ReadOnlyCoinGeckoJsonTransport,
    ResearchMarketUniverseProvider,
)

__all__ = ("ReadOnlyCoinGeckoJsonTransport", "ResearchMarketUniverseProvider")

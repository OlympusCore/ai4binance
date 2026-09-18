"""Compatibility facade for the local opportunity-monitoring contract."""

from ai4binance.compatibility.opportunity_monitor import (
    MARKET_TIMEFRAMES as MARKET_TIMEFRAMES,
)
from ai4binance.compatibility.opportunity_monitor import SAFE_STATE as SAFE_STATE
from ai4binance.compatibility.opportunity_monitor import (
    FuturesBuilder as FuturesBuilder,
)
from ai4binance.compatibility.opportunity_monitor import (
    _outcome as _outcome,
)
from ai4binance.compatibility.opportunity_monitor import (
    inspect_market_data as inspect_market_data,
)
from ai4binance.compatibility.opportunity_monitor import (
    market_symbols as market_symbols,
)
from ai4binance.compatibility.opportunity_monitor import (
    monitor_directory as monitor_directory,
)
from ai4binance.compatibility.opportunity_monitor import (
    read_monitor as read_monitor,
)
from ai4binance.compatibility.opportunity_monitor import (
    refresh_monitor as refresh_monitor,
)
from ai4binance.compatibility.opportunity_monitor import (
    universe_monitor_summary as universe_monitor_summary,
)
from ai4binance.domain.opportunity_observation import (
    diagnose_opportunity_generation as diagnose_opportunity_generation,
)
from ai4binance.domain.opportunity_observation import (
    has_complete_measurable_opportunity as has_complete_measurable_opportunity,
)
from ai4binance.domain.opportunity_observation import (
    has_complete_measurable_trade_plan as has_complete_measurable_trade_plan,
)

__all__ = (
    "MARKET_TIMEFRAMES",
    "SAFE_STATE",
    "FuturesBuilder",
    "diagnose_opportunity_generation",
    "has_complete_measurable_opportunity",
    "has_complete_measurable_trade_plan",
    "inspect_market_data",
    "market_symbols",
    "monitor_directory",
    "read_monitor",
    "refresh_monitor",
    "universe_monitor_summary",
)

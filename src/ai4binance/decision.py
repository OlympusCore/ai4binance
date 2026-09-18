"""Safe deterministic decision factories."""

from datetime import datetime

from ai4binance.domain import DEFAULT_SIGNAL_TIMESTAMP, Signal


def build_no_trade_signal(
    *,
    symbol: str,
    timeframes: tuple[str, ...],
    market_type: str = "Spot",
    timestamp: datetime = DEFAULT_SIGNAL_TIMESTAMP,
    snapshot_id: str = "no-snapshot",
    blocker: str = "ANALYSIS_NOT_AVAILABLE",
) -> Signal:
    """Build the complete fail-closed decision used before validated analysis."""
    return Signal(
        symbol=symbol,
        timeframes=timeframes,
        timestamp=timestamp,
        snapshot_id=snapshot_id,
        market_type=market_type,
        blockers=(blocker,),
        reason_codes=("DEFAULT_NO_TRADE", blocker),
        reason_summary="NO_TRADE: validated market analysis is not available.",
    )

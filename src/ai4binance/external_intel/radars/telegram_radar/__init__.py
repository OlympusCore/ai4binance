"""Telegram Radar fail-closed MVP connector."""

from ai4binance.external_intel.core.enums import MissionName, RadarName, SourceType
from ai4binance.external_intel.radars.unavailable import UnavailableRadarConnector


def build_connector() -> UnavailableRadarConnector:
    return UnavailableRadarConnector(
        RadarName.TELEGRAM_RADAR,
        SourceType.TELEGRAM_MESSAGE,
        MissionName.BINANCE_OPPORTUNITY_NEWS,
        "telegram",
    )


__all__ = ["build_connector"]

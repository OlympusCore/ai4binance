"""Reddit Radar fail-closed MVP connector."""

from ai4binance.external_intel.core.enums import MissionName, RadarName, SourceType
from ai4binance.external_intel.radars.unavailable import UnavailableRadarConnector


def build_connector() -> UnavailableRadarConnector:
    return UnavailableRadarConnector(
        RadarName.REDDIT_RADAR,
        SourceType.REDDIT_POST,
        MissionName.BINANCE_OPPORTUNITY_NEWS,
        "reddit",
    )


__all__ = ["build_connector"]

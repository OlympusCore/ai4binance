"""X Radar fail-closed MVP connector."""

from ai4binance.external_intel.core.enums import MissionName, RadarName, SourceType
from ai4binance.external_intel.radars.unavailable import UnavailableRadarConnector


def build_connector() -> UnavailableRadarConnector:
    return UnavailableRadarConnector(
        RadarName.X_RADAR,
        SourceType.X_POST,
        MissionName.BINANCE_OPPORTUNITY_NEWS,
        "x",
    )


__all__ = ["build_connector"]

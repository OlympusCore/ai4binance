"""Regulatory Radar fail-closed MVP connector."""

from ai4binance.external_intel.core.enums import MissionName, RadarName, SourceType
from ai4binance.external_intel.radars.unavailable import UnavailableRadarConnector


def build_connector() -> UnavailableRadarConnector:
    return UnavailableRadarConnector(
        RadarName.REGULATORY_RADAR,
        SourceType.REGULATORY_NOTICE,
        MissionName.REGULATORY_RISK,
        "regulatory",
    )


__all__ = ["build_connector"]

"""Security Radar fail-closed MVP connector."""

from ai4binance.external_intel.core.enums import MissionName, RadarName, SourceType
from ai4binance.external_intel.radars.unavailable import UnavailableRadarConnector


def build_connector() -> UnavailableRadarConnector:
    return UnavailableRadarConnector(
        RadarName.SECURITY_RADAR,
        SourceType.SECURITY_ADVISORY,
        MissionName.SECURITY_RISK,
        "security",
    )


__all__ = ["build_connector"]

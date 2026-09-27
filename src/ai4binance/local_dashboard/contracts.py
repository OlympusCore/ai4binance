"""Versioned wire validation for the existing dashboard projection."""

from functools import cache
from pathlib import Path

from ai4binance.schema_validation import OfflineSchemaRegistry

SNAPSHOT_VERSION = "DashboardSnapshot/v1"
SNAPSHOT_SCHEMA = (
    "https://ai4binance.local/schemas/interface/dashboard_snapshot.schema.json"
)


@cache
def _registry() -> OfflineSchemaRegistry:
    return OfflineSchemaRegistry.from_directory(
        Path(__file__).resolve().parents[3] / "schemas/interface"
    )


def validate_snapshot(payload: object) -> None:
    """Reject malformed projection output before it reaches a browser."""
    _registry().validate(SNAPSHOT_SCHEMA, payload)

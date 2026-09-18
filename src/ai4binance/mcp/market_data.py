"""Read-only canonical market data MCP evidence contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai4binance.mcp.evidence import EvidenceEnvelope, EvidenceGateway, EvidenceSource

MARKET_SNAPSHOT_SOURCE = EvidenceSource(
    artifact_type="market_snapshot",
    relative_path=Path("market/snapshot.json"),
    timestamp_field="timestamp",
    max_age=timedelta(minutes=5),
    required_fields=(
        "snapshot_id",
        "symbol",
        "timestamp",
        "status",
        "blockers",
        "execution_allowed",
        "live_eligibility_status",
    ),
)

MARKET_DATA_QUALITY_SOURCE = EvidenceSource(
    artifact_type="market_data_quality",
    relative_path=Path("market/data-quality.json"),
    timestamp_field="timestamp",
    max_age=timedelta(minutes=15),
    required_fields=(
        "check_id",
        "timestamp",
        "status",
        "blockers",
        "execution_allowed",
        "live_eligibility_status",
    ),
)

MARKET_PROVENANCE_SOURCE = EvidenceSource(
    artifact_type="market_provenance",
    relative_path=Path("market/provenance.json"),
    timestamp_field="timestamp",
    max_age=timedelta(hours=24),
    required_fields=(
        "provenance_id",
        "timestamp",
        "sources",
        "blockers",
        "execution_allowed",
        "live_eligibility_status",
    ),
)


@dataclass(slots=True)
class MarketDataGateway:
    """Expose canonical market evidence without direct exchange access."""

    artifact_root: Path
    max_artifact_bytes: int = 1_000_000
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    _evidence: EvidenceGateway = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_evidence",
            EvidenceGateway(
                self.artifact_root,
                max_artifact_bytes=self.max_artifact_bytes,
                clock=self.clock,
            ),
        )

    def get_snapshot(self) -> EvidenceEnvelope:
        """Return the latest canonical validated market snapshot artifact."""
        return self._evidence.read(MARKET_SNAPSHOT_SOURCE)

    def get_data_quality(self) -> EvidenceEnvelope:
        """Return the latest market data quality artifact."""
        return self._evidence.read(MARKET_DATA_QUALITY_SOURCE)

    def get_provenance(self) -> EvidenceEnvelope:
        """Return the latest market provenance artifact."""
        return self._evidence.read(MARKET_PROVENANCE_SOURCE)

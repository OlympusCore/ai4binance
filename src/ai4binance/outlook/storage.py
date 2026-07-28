"""Atomic persistence for the latest research-only Market Outlook artifact."""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.outlook.models import MarketOutlook
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified


@dataclass(frozen=True, slots=True)
class MarketOutlookArtifactStore:
    """Publish one bounded state file for read-only evidence consumers."""

    state_path: Path

    def save(self, outlook: MarketOutlook) -> None:
        """Atomically replace latest state without granting execution authority."""
        if outlook.execution_allowed or outlook.live_eligibility_status != (
            "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("unsafe Market Outlook cannot be persisted")
        write_json_object_verified(
            self.state_path,
            cast(dict[str, object], to_primitive(outlook)),
            blocker="MARKET_OUTLOOK_DESTINATION_VERIFY_FAILED",
            subject_id=outlook.snapshot_id,
            indent=2,
        )

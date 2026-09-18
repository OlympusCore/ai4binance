"""CLI-side persistence helpers for opportunity radar artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.opportunity_intelligence import (
    OpportunityEventType,
    OpportunityLifecycleEvent,
    opportunity_event_id,
)
from ai4binance.opportunity_ledger import OpportunityLedgerWriter
from ai4binance.opportunity_radar import OpportunityRadarSnapshot
from ai4binance.reporting import to_primitive


def write_opportunity_radar_snapshot(
    snapshot: OpportunityRadarSnapshot,
    path: Path,
    *,
    lifecycle_ledger_path: Path | None = None,
) -> Path:
    """Persist radar state and idempotent lifecycle evidence at the CLI boundary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            to_primitive(snapshot.to_payload()), ensure_ascii=True, sort_keys=True
        ),
        encoding="utf-8",
    )
    ledger = OpportunityLedgerWriter(
        lifecycle_ledger_path or path.with_name("lifecycle.jsonl")
    )
    for candidate in snapshot.candidates:
        forming = candidate.score > 0
        event_type = (
            OpportunityEventType.OPPORTUNITY_FORMING
            if forming
            else OpportunityEventType.OPPORTUNITY_OBSERVED
        )
        state = (
            OpportunityLifecycleState.SETUP_FORMING
            if forming
            else OpportunityLifecycleState.WATCH_ONLY
        )
        event_id = opportunity_event_id(
            candidate.opportunity_id,
            event_type,
            candidate.observed_at,
            candidate.source_snapshot_id,
        )
        ledger.append(
            OpportunityLifecycleEvent(
                event_id=event_id,
                event_type=event_type,
                opportunity_id=candidate.opportunity_id,
                lifecycle_state=state,
                event_time=candidate.observed_at,
                cycle_id=snapshot.cycle_id,
                snapshot_id=candidate.source_snapshot_id,
                reason_codes=(
                    "RESEARCH_ONLY_OBSERVATION",
                    *candidate.confirmation_requirements,
                ),
                evidence_refs=candidate.supporting_evidence,
            )
        )
    return path

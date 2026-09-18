"""Fail-closed startup replay diagnostics for durable event journals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ai4binance.config import Settings
from ai4binance.events import (
    DiskEventJournal,
    DomainEvent,
    EventJournalCorruptionError,
    JournaledEventRuntime,
)
from ai4binance.execution.live_order_lifecycle import (
    LiveOrderLifecycleStateMachine,
)


@dataclass(frozen=True, slots=True)
class StartupReplayJournalSnapshot:
    """Replay evidence for one durable journal path."""

    journal_path: str
    journal_exists: bool
    journal_size_bytes: int
    event_count: int
    replayed_event_count: int
    replay_from_sequence: int
    checkpoint_sequence: int | None
    checkpoint_event_hash: str | None
    lifecycle_stage: str | None
    blockers: tuple[str, ...]


def startup_replay_payload(settings: Settings) -> dict[str, object]:
    """Open the live-order replay journal on startup without granting authority."""
    journal_path = _startup_replay_path(settings)
    journal = DiskEventJournal(journal_path)
    journal_exists = journal_path.exists()
    journal_size_bytes = journal_path.stat().st_size if journal_exists else 0
    try:
        recovery = journal.recover()
        replay_runtime = JournaledEventRuntime.open(journal)
        replayed_events = replay_runtime.snapshot()
        lifecycle_stage = _lifecycle_stage(replayed_events)
    except (EventJournalCorruptionError, ValueError) as error:
        blocker = _blocker_name(error)
        return {
            "command": "startup-replay",
            "status": "DEGRADED",
            "blockers": (blocker,),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "replay": asdict(
                StartupReplayJournalSnapshot(
                    journal_path=str(journal_path),
                    journal_exists=journal_exists,
                    journal_size_bytes=journal_size_bytes,
                    event_count=0,
                    replayed_event_count=0,
                    replay_from_sequence=1,
                    checkpoint_sequence=None,
                    checkpoint_event_hash=None,
                    lifecycle_stage=None,
                    blockers=(blocker,),
                )
            ),
        }
    checkpoint = recovery.checkpoint
    replay_snapshot = StartupReplayJournalSnapshot(
        journal_path=str(journal_path),
        journal_exists=journal_exists,
        journal_size_bytes=journal_size_bytes,
        event_count=len(recovery.events),
        replayed_event_count=len(replayed_events),
        replay_from_sequence=recovery.replay_from_sequence,
        checkpoint_sequence=checkpoint.sequence if checkpoint is not None else None,
        checkpoint_event_hash=(
            checkpoint.event_hash if checkpoint is not None else None
        ),
        lifecycle_stage=lifecycle_stage,
        blockers=(),
    )
    return {
        "command": "startup-replay",
        "status": "READY",
        "blockers": (),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "replay": asdict(replay_snapshot),
    }


def _startup_replay_path(settings: Settings) -> Path:
    return settings.audit_directory / "live-order-lifecycle.jsonl"


def _lifecycle_stage(events: tuple[DomainEvent, ...]) -> str | None:
    if not events:
        return None
    record = LiveOrderLifecycleStateMachine.replay(events)
    return record.stage.value


def _blocker_name(error: Exception) -> str:
    if isinstance(error, EventJournalCorruptionError):
        return "STARTUP_REPLAY_JOURNAL_INVALID"
    return "STARTUP_REPLAY_UNAVAILABLE"

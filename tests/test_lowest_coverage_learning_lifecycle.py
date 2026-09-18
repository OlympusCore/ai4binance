"""Fail-closed storage and decoding coverage for governed lesson lifecycle."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.learning import lifecycle
from ai4binance.learning.governance import GovernedLesson, LessonStatus
from ai4binance.learning.lifecycle import (
    GovernedLessonLifecycleStore,
    GovernedLessonLifecycleWorker,
    LessonTransitionRequest,
)
from ai4binance.learning.models import LearningSummary


def test_lesson_store_handles_absent_and_invalid_payloads(tmp_path: Path) -> None:
    """Missing storage is empty; malformed persistence remains rejected."""
    store = GovernedLessonLifecycleStore(
        tmp_path / "lessons.json",
        tmp_path / "audit.jsonl",
    )
    assert store.load() == ()

    store.lessons_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="payload is invalid"):
        store.load()


def test_lesson_store_rejects_invalid_save_preconditions(tmp_path: Path) -> None:
    """Lifecycle persistence requires aware time and unique lesson IDs."""
    store = GovernedLessonLifecycleStore(
        tmp_path / "lessons.json",
        tmp_path / "audit.jsonl",
    )
    lesson = GovernedLesson(
        lesson_id="lesson-1",
        code="LESSON",
        rationale="Evidence-backed observation.",
        evidence_count=1,
        source_artifact_ids=("artifact-1",),
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        store.save((), at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="must be unique"):
        store.save((lesson, lesson), at=datetime(2026, 1, 1, tzinfo=UTC))


def test_lesson_decoder_and_scalar_validators_fail_closed() -> None:
    """Untrusted persisted lesson fields require their exact declared types."""
    with pytest.raises(ValueError, match="record is invalid"):
        lifecycle._lesson_from_mapping({})
    with pytest.raises(ValueError, match="record is invalid"):
        lifecycle._lesson_from_mapping(None)
    with pytest.raises(ValueError, match="field"):
        lifecycle._text({}, "field")
    with pytest.raises(ValueError, match="items"):
        lifecycle._texts({"items": ("not", "a", "list")}, "items")
    with pytest.raises(ValueError, match="count"):
        lifecycle._integer({"count": True}, "count")
    with pytest.raises(ValueError, match="timestamp"):
        lifecycle._timestamp({"timestamp": "2026-01-01T00:00:00"}, "timestamp")


def test_lesson_decoder_reconstructs_typed_lesson() -> None:
    """A valid persisted record retains research-only lesson state."""
    observed = datetime(2026, 1, 1, tzinfo=UTC)
    lesson = lifecycle._lesson_from_mapping(
        {
            "lesson_id": "lesson-1",
            "code": "LESSON",
            "rationale": "Evidence-backed observation.",
            "evidence_count": 1,
            "source_artifact_ids": ["artifact-1"],
            "observed_at": observed.isoformat(),
            "expires_at": (observed + timedelta(days=1)).isoformat(),
            "status": LessonStatus.OBSERVED.value,
            "validation_artifact_ids": [],
            "blockers": [],
        }
    )
    assert lesson.status is LessonStatus.OBSERVED
    assert lesson.execution_allowed is False


def test_lesson_decoder_wraps_invalid_enum_value() -> None:
    """Stored status values are decoded through the governed enum."""
    observed = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="record is invalid"):
        lifecycle._lesson_from_mapping(
            {
                "lesson_id": "lesson-1",
                "code": "LESSON",
                "rationale": "Evidence-backed observation.",
                "evidence_count": 1,
                "source_artifact_ids": ["artifact-1"],
                "observed_at": observed.isoformat(),
                "expires_at": (observed + timedelta(days=1)).isoformat(),
                "status": "UNSAFE",
                "validation_artifact_ids": [],
                "blockers": [],
            }
        )


def test_lifecycle_worker_rejects_invalid_inputs_without_persisting(
    tmp_path: Path,
) -> None:
    """Worker validation rejects unsafe lifecycle requests before persistence."""
    store = GovernedLessonLifecycleStore(
        tmp_path / "lessons.json",
        tmp_path / "audit.jsonl",
    )
    summary = LearningSummary(
        summary_id="learning:empty",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        lessons=(),
        experiments=(),
    )
    with pytest.raises(ValueError, match="expiry window"):
        GovernedLessonLifecycleWorker(store, expiry_window=timedelta(0))

    worker = GovernedLessonLifecycleWorker(store)
    with pytest.raises(ValueError, match="timezone-aware"):
        worker.reconcile(summary, at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="unknown lesson"):
        worker.reconcile(
            summary,
            at=datetime(2026, 1, 1, tzinfo=UTC),
            transitions=(LessonTransitionRequest("unknown", LessonStatus.REJECTED),),
        )

    assert worker.reconcile(summary, at=datetime(2026, 1, 1, tzinfo=UTC)) == ()
    assert not store.lessons_path.exists()

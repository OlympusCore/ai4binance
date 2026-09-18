"""Idempotent controlled-learning application boundary."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol


class LessonStatusLike(Protocol):
    value: str


class GovernedLessonLike(Protocol):
    status: LessonStatusLike
    execution_allowed: bool


class LearningSummaryLike(Protocol):
    summary_id: str
    risk_change_allowed: bool


class LearningEngine(Protocol):
    def analyze(self, **artifacts: object) -> LearningSummaryLike: ...


class LearningStoreLike(Protocol):
    summary_path: Path

    def save(self, summary: LearningSummaryLike) -> None: ...


class ClosedPositionLedger(Protocol):
    def closed_positions(self) -> tuple[object, ...]: ...


@dataclass(frozen=True, slots=True)
class LearningLoopResult:
    summary: Any
    saved: bool
    governed_lessons: tuple[GovernedLessonLike, ...] = ()
    lessons_saved: bool = False
    execution_allowed: bool = False


@dataclass(frozen=True, slots=True)
class ControlledLearningLoop:
    store: Any
    engine: Any
    lifecycle_worker: Any | None = None

    def run(self, **artifacts: object) -> LearningLoopResult:
        raw_transitions = artifacts.pop("lesson_transitions", ())
        if not isinstance(raw_transitions, tuple):
            raise ValueError("lesson transitions must be an immutable tuple")
        summary = self.engine.analyze(**artifacts)
        governed_lessons: tuple[GovernedLessonLike, ...] = ()
        lessons_saved = False
        if self.lifecycle_worker is not None:
            at = artifacts.get("created_at", getattr(summary, "created_at", None))
            if not isinstance(at, datetime):
                raise ValueError("learning lifecycle requires a datetime timestamp")
            before = self.lifecycle_worker.store.load()
            governed_lessons = self.lifecycle_worker.reconcile(
                summary,
                at=at,
                transitions=raw_transitions,
            )
            lessons_saved = governed_lessons != before
        if self.store.summary_path.exists():
            current = json.loads(self.store.summary_path.read_text(encoding="utf-8"))
            # Content identity does not establish freshness after a new analysis.
            previous_at_raw = current.get("created_at")
            previous_at = (
                datetime.fromisoformat(previous_at_raw)
                if isinstance(previous_at_raw, str)
                else None
            )
            analyzed_at = getattr(summary, "created_at", None)
            refresh_due = previous_at is None or (
                isinstance(analyzed_at, datetime)
                and analyzed_at - previous_at >= timedelta(days=1)
            )
            if current.get("summary_id") == summary.summary_id and not refresh_due:
                return LearningLoopResult(
                    summary,
                    saved=False,
                    governed_lessons=governed_lessons,
                    lessons_saved=lessons_saved,
                )
        self.store.save(summary)
        return LearningLoopResult(
            summary,
            saved=True,
            governed_lessons=governed_lessons,
            lessons_saved=lessons_saved,
        )


class LearningEvidenceProvider(Protocol):
    def load(self, snapshot: object) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class PaperLedgerLearningEvidenceProvider:
    ledger: ClosedPositionLedger

    def load(self, snapshot: object) -> dict[str, object]:
        del snapshot
        return {"paper_positions": self.ledger.closed_positions()}

"""Idempotent controlled-learning application boundary."""

import json
from dataclasses import dataclass, field

from ai4binance.learning.engine import ControlledLearningEngine
from ai4binance.learning.models import LearningSummary
from ai4binance.learning.storage import LearningStore


@dataclass(frozen=True, slots=True)
class LearningLoopResult:
    summary: LearningSummary
    saved: bool
    execution_allowed: bool = False


@dataclass(frozen=True, slots=True)
class ControlledLearningLoop:
    store: LearningStore
    engine: ControlledLearningEngine = field(default_factory=ControlledLearningEngine)

    def run(self, **artifacts: object) -> LearningLoopResult:
        summary = self.engine.analyze(**artifacts)  # type: ignore[arg-type]
        if self.store.summary_path.exists():
            current = json.loads(self.store.summary_path.read_text(encoding="utf-8"))
            if current.get("summary_id") == summary.summary_id:
                return LearningLoopResult(summary, saved=False)
        self.store.save(summary)
        return LearningLoopResult(summary, saved=True)

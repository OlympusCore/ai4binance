"""Evidence-counting learning engine that only proposes validation work."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from ai4binance.backtest.models import BacktestResult
from ai4binance.execution.lifecycle import LifecyclePosition
from ai4binance.learning.models import (
    ExperimentRecommendation,
    LearningSummary,
    LessonCandidate,
)
from ai4binance.tuning.models import TuningReport
from ai4binance.validation.models import WalkForwardReport


@dataclass(frozen=True, slots=True)
class ControlledLearningEngine:
    """Aggregate validated artifacts without modifying production state."""

    def analyze(
        self,
        *,
        created_at: datetime,
        backtests: tuple[BacktestResult, ...] = (),
        walk_forward_reports: tuple[WalkForwardReport, ...] = (),
        tuning_reports: tuple[TuningReport, ...] = (),
        paper_positions: tuple[LifecyclePosition, ...] = (),
    ) -> LearningSummary:
        counts: dict[str, int] = {}
        for result in backtests:
            self._add(counts, "REJECTED_SIGNALS", len(result.rejected_signals))
            self._add(counts, "LOW_TRADE_COUNT", int(result.metrics.trade_count < 5))
        for walk_forward_report in walk_forward_reports:
            for blocker in walk_forward_report.blockers:
                self._add(counts, f"OOS_{blocker}", 1)
        for tuning_report in tuning_reports:
            for blocker in tuning_report.blockers:
                self._add(counts, f"TUNING_{blocker}", 1)
        for position in paper_positions:
            if position.closure_review is not None:
                self._add(counts, position.closure_review.lesson_candidate, 1)
        lessons = tuple(
            LessonCandidate(code, count, self._rationale(code))
            for code, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if count > 0
        )
        experiments = tuple(
            ExperimentRecommendation(
                rank=index,
                experiment_id=f"experiment:{lesson.code.lower()}",
                objective=f"Validate mitigation for {lesson.code}",
                required_validation=("backtest", "walk_forward", "multi_regime_oos"),
            )
            for index, lesson in enumerate(lessons, start=1)
        )
        payload = "|".join(f"{item.code}:{item.evidence_count}" for item in lessons)
        digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
        return LearningSummary(
            summary_id=f"learning:{digest}",
            created_at=created_at,
            lessons=lessons,
            experiments=experiments,
        )

    @staticmethod
    def _add(counts: dict[str, int], code: str, amount: int) -> None:
        counts[code] = counts.get(code, 0) + amount

    @staticmethod
    def _rationale(code: str) -> str:
        return f"Observed recurring evidence for {code}; validation is required."

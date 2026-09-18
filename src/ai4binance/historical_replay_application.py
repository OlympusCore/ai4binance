"""Application orchestration boundary for deterministic historical replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai4binance.application.learning_loop import ControlledLearningLoop
from ai4binance.historical_replay_evaluation import (
    HistoricalDgeCounterfactualOutcome,
    HistoricalReplayPublication,
    HistoricalReplaySystemEvaluation,
    HistoricalReplaySystemEvaluator,
)
from ai4binance.historical_replay_state import HistoricalReplayStateStore
from ai4binance.research.backtesting.robustness import BacktestRobustnessReport
from ai4binance.research.historical_replay import HistoricalMarketReplayRequest
from ai4binance.research.historical_replay_materialization import (
    HistoricalExecutionContextProvider,
    HistoricalReplayDatasetSeries,
    HistoricalReplaySnapshotMaterializer,
)
from ai4binance.research.virtual_market import VirtualMarket
from ai4binance.research_runtime import (
    HistoricalMarketReplayRunner,
    HistoricalReplayRunResult,
    HistoricalReplaySnapshot,
)
from ai4binance.validation.models import WalkForwardReport


@dataclass(frozen=True, slots=True)
class HistoricalReplayApplicationResult:
    """Outputs from one bounded application-owned replay chain."""

    snapshots: tuple[HistoricalReplaySnapshot, ...]
    replay: HistoricalReplayRunResult
    evaluation: HistoricalReplaySystemEvaluation
    publication: HistoricalReplayPublication
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.snapshots:
            raise ValueError("historical replay application requires snapshots")
        if self.evaluation.replay_result is not self.replay:
            raise ValueError("historical replay application result identity drift")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay application cannot authorize trading")


@dataclass(frozen=True, slots=True)
class HistoricalReplayApplicationService:
    """Chain canonical materialization, replay, evaluation, and persistence."""

    materializer: HistoricalReplaySnapshotMaterializer
    runner: HistoricalMarketReplayRunner
    evaluator: HistoricalReplaySystemEvaluator

    def execute(
        self,
        request: HistoricalMarketReplayRequest,
        datasets: Sequence[HistoricalReplayDatasetSeries],
        execution_context_provider: HistoricalExecutionContextProvider,
        *,
        root: Path,
        stamp: str,
        walk_forward_reports: Mapping[VirtualMarket | str, WalkForwardReport]
        | None = None,
        robustness_reports: Mapping[VirtualMarket | str, BacktestRobustnessReport]
        | None = None,
        dge_counterfactuals: Sequence[HistoricalDgeCounterfactualOutcome] = (),
        reproducibility_reference_sha256: str | None = None,
        learning_loop: ControlledLearningLoop | None = None,
        state_store: HistoricalReplayStateStore | None = None,
    ) -> HistoricalReplayApplicationResult:
        """Execute one deterministic historical replay workflow."""

        snapshots = self.materializer.materialize(
            request,
            datasets,
            execution_context_provider,
        )
        replay = self.runner.run(request, snapshots)
        evaluation = self.evaluator.evaluate(
            replay,
            walk_forward_reports=walk_forward_reports,
            robustness_reports=robustness_reports,
            dge_counterfactuals=dge_counterfactuals,
            reproducibility_reference_sha256=reproducibility_reference_sha256,
            learning_loop=learning_loop,
        )
        publication = self.evaluator.persist_and_publish(
            evaluation,
            root=root,
            stamp=stamp,
            state_store=state_store,
        )
        return HistoricalReplayApplicationResult(
            snapshots=snapshots,
            replay=replay,
            evaluation=evaluation,
            publication=publication,
        )


__all__ = (
    "HistoricalReplayApplicationResult",
    "HistoricalReplayApplicationService",
)

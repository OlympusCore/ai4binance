"""Transition-safe persistence boundary for historical replay evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ai4binance.historical_replay_state import HistoricalReplayStateStore
from ai4binance.ops.user_reports import user_report_paths, write_user_report_files
from ai4binance.research.virtual_runtime import VirtualMarketRuntime


@dataclass(frozen=True, slots=True)
class HistoricalReplayEvidencePublisher:
    """Persist one evaluated replay without owning evaluation policy."""

    runtime: VirtualMarketRuntime

    def publish(
        self,
        evaluation: object,
        *,
        root: Path,
        stamp: str,
        state_store: HistoricalReplayStateStore | None = None,
        render_evaluation: Callable[[Any], str],
        publication_factory: Callable[..., object],
    ) -> object:
        """Persist wallet state and publish exact market/system evidence."""

        typed_evaluation = cast(Any, evaluation)
        if not stamp.strip():
            raise ValueError("historical replay publication stamp is required")
        resolved_store = state_store or HistoricalReplayStateStore.for_run(
            root,
            typed_evaluation.replay_result.request.run_id,
        )
        observed_at = max(
            cycle.replay_snapshot.created_at
            for cycle in typed_evaluation.replay_result.cycles
        )
        persisted = resolved_store.persist(
            typed_evaluation.replay_result,
            persisted_at=observed_at,
        )
        market_paths = tuple(
            (
                item.market,
                self.runtime.publish_evidence_surface(
                    item.adapter,
                    root=root,
                    stamp=stamp,
                ),
            )
            for item in typed_evaluation.markets
        )
        system_paths = (
            self.runtime.publish_system_acceptance_report(
                typed_evaluation.system_acceptance,
                root=root,
                stamp=stamp,
            )
            if typed_evaluation.system_acceptance is not None
            else None
        )
        evaluation_paths = user_report_paths(
            root,
            "historical_replay",
            stamp,
            file_stem="historical_replay_system_evaluation",
            latest_stem="historical_replay_system_evaluation_latest",
        )
        write_user_report_files(
            evaluation_paths,
            typed_evaluation.to_payload(),
            render_evaluation(typed_evaluation),
        )
        return publication_factory(
            state_path=resolved_store.path,
            state_persisted=persisted,
            market_report_paths=market_paths,
            system_acceptance_paths=system_paths,
            system_evaluation_paths=evaluation_paths,
        )


__all__ = ("HistoricalReplayEvidencePublisher",)

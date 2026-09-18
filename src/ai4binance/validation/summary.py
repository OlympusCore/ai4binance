"""Bounded summaries for persisted validation/backtest evidence."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.research.backtesting.layout import load_backtest_layout_manifest


@dataclass(frozen=True, slots=True)
class ValidationRunSummary:
    """One run-card summary with no execution authority."""

    symbol: str
    timeframe: str
    playbook: str
    run_id: str
    promotion_status: str
    metrics: tuple[tuple[str, float], ...]
    blockers: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    created_at: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.symbol,
                self.timeframe,
                self.playbook,
                self.run_id,
                self.promotion_status,
            )
        ):
            raise ValueError("validation run summary identity is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("validation summary cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """Human-readable validation index over existing run-card artifacts."""

    symbol: str
    artifact_directory: str
    run_count: int
    staged_candidate_count: int
    research_only_count: int
    top_blockers: tuple[tuple[str, int], ...]
    runs: tuple[ValidationRunSummary, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.artifact_directory.strip():
            raise ValueError("validation summary identity is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("validation summary cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ValidationSummaryReader:
    """Read small run-card files instead of massive backtest JSONL artifacts."""

    artifact_directory: Path
    max_runs: int = 200
    max_blockers: int = 12

    def __post_init__(self) -> None:
        if self.max_runs < 1 or self.max_blockers < 1:
            raise ValueError("validation summary bounds must be positive")

    def summarize(self, symbol: str) -> ValidationSummary:
        normalized = symbol.strip().upper()
        blockers: list[str] = []
        runs: list[ValidationRunSummary] = []
        symbol_root = self.artifact_directory / normalized
        if not symbol_root.exists():
            blockers.append("VALIDATION_ARTIFACTS_UNAVAILABLE")
        else:
            for path in sorted(symbol_root.glob("*/*.run-card.json"))[: self.max_runs]:
                try:
                    runs.append(_run_summary(path))
                except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                    blockers.append(f"RUN_CARD_UNREADABLE:{path.as_posix()}")

        blocker_counts = Counter(blocker for run in runs for blocker in run.blockers)
        if not runs and not blockers:
            blockers.append("VALIDATION_RUN_CARDS_UNAVAILABLE")
        staged = sum(1 for run in runs if run.promotion_status == "STAGED_CANDIDATE")
        research = sum(1 for run in runs if run.promotion_status == "RESEARCH_ONLY")
        return ValidationSummary(
            symbol=normalized,
            artifact_directory=self.artifact_directory.as_posix(),
            run_count=len(runs),
            staged_candidate_count=staged,
            research_only_count=research,
            top_blockers=tuple(blocker_counts.most_common(self.max_blockers)),
            runs=tuple(runs),
            blockers=tuple(dict.fromkeys(blockers)),
        )


def _run_summary(path: Path) -> ValidationRunSummary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("run card must be an object")
    run_card = cast(Mapping[str, object], payload)
    artifact_paths = tuple(
        str(item[0])
        for item in _sequence(run_card.get("artifact_sha256"))
        if isinstance(item, Sequence) and not isinstance(item, str) and item
    )
    metrics = tuple(
        (str(item[0]), float(item[1]))
        for item in _sequence(run_card.get("metrics"))
        if isinstance(item, Sequence) and not isinstance(item, str) and len(item) >= 2
    )
    return ValidationRunSummary(
        symbol=str(run_card["symbol"]).strip().upper(),
        timeframe=str(run_card["timeframe"]).strip(),
        playbook=_playbook(run_card),
        run_id=str(run_card["run_id"]).strip(),
        promotion_status=str(run_card["promotion_status"]).strip(),
        metrics=metrics,
        blockers=tuple(str(item) for item in _sequence(run_card.get("blockers"))),
        artifact_paths=tuple(
            load_backtest_layout_manifest().canonicalize_uri(item)
            for item in artifact_paths
        ),
        created_at=str(run_card["created_at"]),
    )


def _playbook(run_card: Mapping[str, object]) -> str:
    hypothesis = str(run_card.get("hypothesis_id", "")).strip()
    parts = hypothesis.split(":")
    if len(parts) >= 3 and parts[1]:
        return parts[1]
    strategy = run_card.get("strategy_sha256")
    if isinstance(strategy, str) and strategy.strip():
        return "UNKNOWN_PLAYBOOK"
    raise ValueError("run card playbook is unavailable")


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()

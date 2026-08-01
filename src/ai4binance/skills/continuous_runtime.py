"""Runtime wrapper for the continuous skill discovery loop."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.config import Settings
from ai4binance.ops.runtime import SingleInstanceLease
from ai4binance.reporting import to_primitive
from ai4binance.skills.continuous_discovery import ContinuousLearningCycleReport
from ai4binance.skills.discovery_pipeline import (
    ContinuousSkillDiscoveryEngine,
    DocumentationFetcher,
    GitHubDocumentationFetcher,
    StaticCandidateScout,
    StaticDocumentationFetcher,
    source_file_candidates,
    source_file_documents,
)
from ai4binance.skills.github_discovery import (
    DEFAULT_DISCOVERY_QUERIES,
    CandidateScout,
    GitHubSearchScout,
)


@dataclass(frozen=True, slots=True)
class SkillDiscoveryRuntime:
    engine: ContinuousSkillDiscoveryEngine
    queries: tuple[str, ...] = DEFAULT_DISCOVERY_QUERIES
    max_candidates: int = 10
    min_score: float = 0.85

    def run_once(
        self,
        *,
        now: datetime | None = None,
    ) -> ContinuousLearningCycleReport:
        return self.engine.run_once(
            queries=self.queries,
            max_candidates=self.max_candidates,
            min_score=self.min_score,
            now=now,
        )


@dataclass(frozen=True, slots=True)
class SkillDiscoverySupervisor:
    runtime: SkillDiscoveryRuntime
    interval_seconds: float
    lock_path: Path
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)

    def __post_init__(self) -> None:
        if not 300.0 <= self.interval_seconds <= 86_400.0:
            raise ValueError("skill discovery interval must be between 300 and 86400")
        if not self.lock_path.is_absolute():
            raise ValueError("skill discovery lock path must be absolute")

    def run(self, *, max_cycles: int | None = None) -> int:
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        completed = 0
        attempts = 0
        with SingleInstanceLease(self.lock_path):
            while max_cycles is None or attempts < max_cycles:
                attempts += 1
                self.runtime.run_once()
                completed += 1
                if max_cycles is not None and attempts >= max_cycles:
                    continue
                self.sleeper(self.interval_seconds)
        return completed


def build_skill_discovery_runtime(
    settings: Settings,
    *,
    source_file: str | None = None,
    max_candidates: int = 10,
    min_score: float = 0.85,
) -> SkillDiscoveryRuntime:
    now = datetime.now(UTC)
    scout: CandidateScout
    fetcher: DocumentationFetcher
    if source_file:
        source_path = _absolute(Path(source_file))
        candidates = source_file_candidates(source_path, now)
        documents = source_file_documents(source_path)
        scout = StaticCandidateScout(candidates)
        fetcher = StaticDocumentationFetcher(documents)
    else:
        scout = GitHubSearchScout(timeout_seconds=settings.request_timeout_seconds)
        fetcher = GitHubDocumentationFetcher(
            timeout_seconds=settings.request_timeout_seconds
        )
    engine = ContinuousSkillDiscoveryEngine(
        scout=scout,
        fetcher=fetcher,
        staging_directory=_absolute(settings.skill_discovery_staging_directory),
        state_path=_absolute(settings.skill_discovery_state_path),
        ledger_path=_absolute(settings.skill_discovery_ledger_path),
    )
    return SkillDiscoveryRuntime(
        engine=engine,
        max_candidates=max_candidates,
        min_score=min_score,
    )


def read_skill_discovery_status(settings: Settings) -> dict[str, object]:
    state_path = _absolute(settings.skill_discovery_state_path)
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "command": "skill-discovery-status",
            "status": "BLOCKED",
            "state_path": str(state_path),
            "blockers": ("SKILL_DISCOVERY_STATE_UNAVAILABLE",),
            "execution_allowed": False,
            "installation_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    if not isinstance(payload, dict):
        return {
            "command": "skill-discovery-status",
            "status": "BLOCKED",
            "state_path": str(state_path),
            "blockers": ("SKILL_DISCOVERY_STATE_INVALID",),
            "execution_allowed": False,
            "installation_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    blockers = tuple(cast(Sequence[object], payload.get("blockers", ())))
    return {
        "command": "skill-discovery-status",
        "status": "DEGRADED" if blockers else "READY",
        "state_path": str(state_path),
        "report": payload,
        "blockers": blockers,
        "execution_allowed": False,
        "installation_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def report_payload(
    command: str,
    report: ContinuousLearningCycleReport,
) -> dict[str, object]:
    payload = cast(dict[str, object], to_primitive(report))
    return {
        "command": command,
        "status": "DEGRADED" if report.blockers else "READY",
        "report": payload,
        "blockers": report.blockers,
        "execution_allowed": False,
        "installation_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

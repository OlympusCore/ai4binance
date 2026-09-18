"""Bounded, deterministic batch evaluation for local advisory fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ai4binance.agents.evaluation import (
    AdvisoryFixture,
    AdvisoryFixtureProvider,
    AdvisoryFixtureRun,
    run_advisory_fixture,
)

_MAXIMUM_FIXTURES = 32


@dataclass(frozen=True, slots=True)
class LocalAdvisoryFixtureHarnessReport:
    """Non-promoting result for one sequential, bounded advisory batch."""

    fixture_runs: tuple[AdvisoryFixtureRun, ...]
    status: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_evidence: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.fixture_runs:
            raise ValueError("local advisory fixture harness report requires runs")
        fixture_ids = {run.fixture_id for run in self.fixture_runs}
        if len(fixture_ids) != len(self.fixture_runs):
            raise ValueError(
                "local advisory fixture harness report fixture IDs must be unique"
            )
        expected_blockers = tuple(
            dict.fromkeys(
                blocker for run in self.fixture_runs for blocker in run.blockers
            )
        )
        expected_status = "PASS" if not expected_blockers else "BLOCKED"
        if self.blockers != expected_blockers or self.status != expected_status:
            raise ValueError("local advisory fixture harness report status is invalid")
        if (
            self.execution_allowed
            or self.promotion_evidence
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("local advisory fixture harness cannot promote or execute")


@dataclass(frozen=True, slots=True)
class LocalAdvisoryFixtureHarness:
    """Run an injected provider sequentially with a fixed local batch limit."""

    maximum_fixtures: int = _MAXIMUM_FIXTURES

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_fixtures <= _MAXIMUM_FIXTURES:
            raise ValueError("local advisory fixture harness maximum is invalid")

    def run(
        self,
        fixtures: tuple[AdvisoryFixture, ...],
        provider: AdvisoryFixtureProvider,
        *,
        started_at: datetime,
    ) -> LocalAdvisoryFixtureHarnessReport:
        """Evaluate every fixture in the caller-provided deterministic order."""
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError(
                "local advisory fixture harness timestamp must be timezone-aware"
            )
        if not fixtures or len(fixtures) > self.maximum_fixtures:
            raise ValueError("local advisory fixture harness fixture batch is invalid")
        fixture_ids = tuple(fixture.fixture_id for fixture in fixtures)
        if len(set(fixture_ids)) != len(fixture_ids):
            raise ValueError(
                "local advisory fixture harness fixture IDs must be unique"
            )

        fixture_runs = tuple(
            run_advisory_fixture(fixture, provider, started_at=started_at)
            for fixture in fixtures
        )
        blockers = tuple(
            dict.fromkeys(
                blocker
                for fixture_run in fixture_runs
                for blocker in fixture_run.blockers
            )
        )
        return LocalAdvisoryFixtureHarnessReport(
            fixture_runs=fixture_runs,
            status="PASS" if not blockers else "BLOCKED",
            blockers=blockers,
        )

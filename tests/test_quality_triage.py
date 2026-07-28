"""Nightly quality triage safety, persistence, and degraded-path tests."""

import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.ops.quality_triage import (
    CheckStatus,
    QualityCheck,
    QualityTriageAlreadyRunningError,
    QualityTriageConfig,
    run_quality_triage,
)

NOW = datetime(2026, 7, 13, 1, 17, tzinfo=UTC)
CHECKS = (
    QualityCheck("pytest", ("python", "-m", "pytest")),
    QualityCheck("mypy", ("python", "-m", "mypy")),
)


class Clock:
    """Deterministic wall and monotonic clock."""

    def __init__(self) -> None:
        self.wall_calls = 0
        self.monotonic_value = 0.0

    def now(self) -> datetime:
        value = NOW + timedelta(seconds=self.wall_calls)
        self.wall_calls += 1
        return value

    def monotonic(self) -> float:
        self.monotonic_value += 0.01
        return self.monotonic_value


def test_quality_triage_persists_passed_report_without_authority(
    tmp_path: Path,
) -> None:
    clock = Clock()

    def passing_runner(
        arguments: Sequence[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, stdout="All checks passed")

    output = tmp_path / "artifacts"
    report = run_quality_triage(
        QualityTriageConfig(tmp_path, output),
        revision="abc123",
        checks=CHECKS,
        runner=passing_runner,
        clock=clock.now,
        monotonic=clock.monotonic,
    )

    assert report.status == "PASSED"
    assert report.blockers == ()
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert not (output / "quality_triage.lock").exists()
    state = json.loads((output / "state.json").read_text(encoding="utf-8"))
    audit = json.loads((output / "runs.jsonl").read_text(encoding="utf-8"))
    assert state["revision"] == "abc123"
    assert audit["event_type"] == "QUALITY_TRIAGE_COMPLETED"


def test_quality_triage_runs_all_checks_and_redacts_bounded_output(
    tmp_path: Path,
) -> None:
    clock = Clock()
    calls: list[object] = []

    def mixed_runner(
        arguments: Sequence[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                arguments,
                2,
                stdout="api_key=visible-value\n" + ("x" * 80),
            )
        raise subprocess.TimeoutExpired(arguments, 10, output="timed out")

    report = run_quality_triage(
        QualityTriageConfig(tmp_path, tmp_path / "out", max_output_characters=40),
        revision="dirty",
        checks=CHECKS,
        runner=mixed_runner,
        clock=clock.now,
        monotonic=clock.monotonic,
    )

    assert len(calls) == 2
    assert [item.status for item in report.checks] == [
        CheckStatus.FAILED,
        CheckStatus.TIMED_OUT,
    ]
    assert report.checks[0].output_truncated is True
    persisted = (tmp_path / "out" / "runs.jsonl").read_text(encoding="utf-8")
    assert "visible-value" not in persisted
    assert report.status == "FAILED"
    assert report.execution_allowed is False


def test_quality_triage_rejects_overlap_and_invalid_limits(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "quality_triage.lock").write_text("existing", encoding="utf-8")

    with pytest.raises(QualityTriageAlreadyRunningError, match="already running"):
        run_quality_triage(
            QualityTriageConfig(tmp_path, output),
            revision="abc",
            checks=CHECKS,
        )
    with pytest.raises(ValueError, match="positive"):
        QualityTriageConfig(tmp_path, output, command_timeout_seconds=0)

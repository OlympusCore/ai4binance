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
    QualityTriageAdmissionError,
    QualityTriageAlreadyRunningError,
    QualityTriageConfig,
    default_quality_checks,
    run_quality_triage,
)

NOW = datetime(2026, 7, 13, 1, 17, tzinfo=UTC)
CHECKS = (default_quality_checks()[3], default_quality_checks()[2])


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

    output = tmp_path / "runtime/artifacts/quality/triage"
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
        QualityTriageConfig(
            tmp_path, tmp_path / "runtime/out", max_output_characters=40
        ),
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
    persisted = (tmp_path / "runtime/out" / "runs.jsonl").read_text(encoding="utf-8")
    assert "visible-value" not in persisted
    assert report.status == "FAILED"
    assert report.execution_allowed is False


def test_quality_triage_rejects_overlap_and_invalid_limits(tmp_path: Path) -> None:
    output = tmp_path / "runtime/out"
    output.mkdir(parents=True)
    (output / "quality_triage.lock").write_text("existing", encoding="utf-8")

    with pytest.raises(QualityTriageAlreadyRunningError, match="already running"):
        run_quality_triage(
            QualityTriageConfig(tmp_path, output),
            revision="abc",
            checks=CHECKS,
        )
    with pytest.raises(ValueError, match="positive"):
        QualityTriageConfig(tmp_path, output, command_timeout_seconds=0)


@pytest.mark.parametrize("violation", ["command", "timeout", "outside_runtime"])
def test_triage_admission_rejects_before_starting_commands(
    tmp_path: Path, violation: str
) -> None:
    calls: list[object] = []

    def runner(
        arguments: Sequence[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="test-only")

    output = tmp_path / ("outside" if violation == "outside_runtime" else "runtime/out")
    checks = (
        (QualityCheck("unregistered", ("unregistered-command",)),)
        if violation == "command"
        else CHECKS
    )
    with pytest.raises(QualityTriageAdmissionError):
        run_quality_triage(
            QualityTriageConfig(
                tmp_path,
                output,
                command_timeout_seconds=601 if violation == "timeout" else 600,
            ),
            revision="test-only",
            checks=checks,
            runner=runner,
        )
    assert calls == []


def test_triage_persists_verified_admission_before_commands(tmp_path: Path) -> None:
    output = tmp_path / "runtime/out"

    def runner(
        arguments: Sequence[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        evidence = next(output.glob("nightly-quality-triage-*.json"))
        report = json.loads(evidence.read_text())
        assert report["status"] == "ADMITTED_REPORT_ONLY"
        audit = Path(report["persistent_evidence"]["audit_path"])
        from ai4binance.storage import JsonlAuditStore

        assert audit.is_file()
        assert len(JsonlAuditStore(audit, tamper_evident=True).verify_chain()) == 64
        return subprocess.CompletedProcess(arguments, 0, stdout="test-only")

    report = run_quality_triage(
        QualityTriageConfig(tmp_path, output),
        revision="test-only",
        checks=CHECKS,
        runner=runner,
    )
    assert Path(report.runner_admission_ref).is_file()


def test_triage_stops_on_admission_persistence_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai4binance.ops.quality_triage as triage

    calls: list[object] = []

    def failed_write(_: object) -> None:
        raise ValueError("test-only persistence failure")

    def runner(
        arguments: Sequence[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="test-only")

    monkeypatch.setattr(triage, "_persist_admission", failed_write)
    with pytest.raises(ValueError, match="persistence failure"):
        run_quality_triage(
            QualityTriageConfig(tmp_path, tmp_path / "runtime/out"),
            revision="test-only",
            checks=CHECKS,
            runner=runner,
        )
    assert calls == []

"""Bounded nightly quality triage with no code-change or trading authority."""

import argparse
import hashlib
import json
import os
import re

# Import is restricted to the fixed shell-free quality command registry.
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified

_SENSITIVE_OUTPUT = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|authorization)(\s*[:=]\s*)(\S+)"
)


class CheckStatus(StrEnum):
    """Machine-readable outcome of one independent quality check."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class QualityCheck:
    """One fixed command in the quality contract."""

    name: str
    arguments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityCheckResult:
    """Bounded evidence from one quality check."""

    name: str
    status: CheckStatus
    return_code: int | None
    duration_ms: int
    output_tail: str
    output_sha256: str
    output_truncated: bool


@dataclass(frozen=True, slots=True)
class QualityTriageReport:
    """Complete report-only outcome for one quality run."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    revision: str
    repository: str
    checks: tuple[QualityCheckResult, ...]
    status: str
    blockers: tuple[str, ...]
    mode: str = "TRIAGE_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    schema_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class QualityTriageConfig:
    """Resource and persistence limits for unattended triage."""

    repository_root: Path
    output_directory: Path
    command_timeout_seconds: int = 600
    max_output_characters: int = 20_000

    def __post_init__(self) -> None:
        if self.command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        if self.max_output_characters <= 0:
            raise ValueError("max_output_characters must be positive")


class CommandRunner(Protocol):
    """Injectable subprocess boundary used by deterministic tests."""

    def __call__(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        stdout: int,
        stderr: int,
        text: bool,
        errors: str,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


class QualityTriageAlreadyRunningError(RuntimeError):
    """Raised when an overlapping run is rejected fail-closed."""


def default_quality_checks(python: str = sys.executable) -> tuple[QualityCheck, ...]:
    """Return the immutable, shell-free quality command set."""
    return (
        QualityCheck("ruff_format", (python, "-m", "ruff", "format", "--check", ".")),
        QualityCheck("ruff_lint", (python, "-m", "ruff", "check", ".")),
        QualityCheck("mypy", (python, "-m", "mypy")),
        QualityCheck("pytest", (python, "-m", "pytest")),
        QualityCheck("bandit", (python, "-m", "bandit", "-q", "-r", "src")),
    )


def run_quality_triage(
    config: QualityTriageConfig,
    *,
    revision: str,
    checks: tuple[QualityCheck, ...] | None = None,
    runner: CommandRunner | None = None,
    clock: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> QualityTriageReport:
    """Run every gate independently and persist a redacted bounded report."""
    now = clock or (lambda: datetime.now(UTC))
    root = config.repository_root.resolve()
    if not root.is_dir():
        raise ValueError("repository_root must be an existing directory")
    config.output_directory.mkdir(parents=True, exist_ok=True)
    command_runner = runner or _run_command
    lock_path = config.output_directory / "quality_triage.lock"
    lock_descriptor = _acquire_lock(lock_path)
    try:
        started_at = now()
        run_id = f"quality-{started_at:%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"
        results = tuple(
            _run_check(check, config, root, command_runner, monotonic)
            for check in (checks or default_quality_checks())
        )
        blockers = tuple(
            f"QUALITY_{result.name.upper()}_{result.status.value}"
            for result in results
            if result.status is not CheckStatus.PASSED
        )
        report = QualityTriageReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=now(),
            revision=revision.strip() or "UNKNOWN",
            repository=root.name,
            checks=results,
            status="PASSED" if not blockers else "FAILED",
            blockers=blockers,
        )
        _persist_report(config.output_directory, report)
        return report
    finally:
        os.close(lock_descriptor)
        lock_path.unlink(missing_ok=True)


def _acquire_lock(path: Path) -> int:
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise QualityTriageAlreadyRunningError(
            "quality triage is already running"
        ) from error


def _run_command(
    arguments: Sequence[str],
    *,
    cwd: Path,
    stdout: int,
    stderr: int,
    text: bool,
    errors: str,
    timeout: int,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    # Arguments come only from the immutable in-module quality check registry.
    return subprocess.run(  # noqa: S603  # nosec B603
        arguments,
        cwd=cwd,
        stdout=stdout,
        stderr=stderr,
        text=text,
        errors=errors,
        timeout=timeout,
        check=check,
    )


def _run_check(
    check: QualityCheck,
    config: QualityTriageConfig,
    root: Path,
    runner: CommandRunner,
    monotonic: Callable[[], float],
) -> QualityCheckResult:
    started = monotonic()
    status = CheckStatus.ERROR
    return_code: int | None = None
    output = ""
    try:
        completed = runner(
            check.arguments,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=config.command_timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        output = completed.stdout or ""
        status = CheckStatus.PASSED if return_code == 0 else CheckStatus.FAILED
    except subprocess.TimeoutExpired as error:
        status = CheckStatus.TIMED_OUT
        output = _timeout_output(error)
    except OSError as error:
        status = CheckStatus.ERROR
        output = f"{type(error).__name__}: {error}"
    sanitized = _SENSITIVE_OUTPUT.sub(r"\1\2[REDACTED]", output)
    truncated = len(sanitized) > config.max_output_characters
    output_tail = sanitized[-config.max_output_characters :]
    duration_ms = max(0, round((monotonic() - started) * 1000))
    return QualityCheckResult(
        name=check.name,
        status=status,
        return_code=return_code,
        duration_ms=duration_ms,
        output_tail=output_tail,
        output_sha256=hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
        output_truncated=truncated,
    )


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    value = error.stdout or error.output or "command timed out"
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _persist_report(directory: Path, report: QualityTriageReport) -> None:
    primitive = cast(dict[str, object], to_primitive(report))
    latest = directory / "state.json"
    write_json_object_verified(
        latest,
        primitive,
        blocker="QUALITY_TRIAGE_STATE_DESTINATION_VERIFY_FAILED",
        subject_id=report.run_id,
        indent=2,
    )
    JsonlAuditStore(directory / "runs.jsonl", durable=True).append_verified(
        AuditEvent(
            event_type="QUALITY_TRIAGE_COMPLETED",
            timestamp=report.finished_at,
            snapshot_id=report.run_id,
            payload={"report": report},
        )
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only quality triage CLI."""
    parser = argparse.ArgumentParser(description="AI4BINANCE quality triage")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("Artifacts/quality-triage"),
    )
    parser.add_argument("--revision", default=os.environ.get("GITHUB_SHA", "LOCAL"))
    parser.add_argument("--command-timeout-seconds", type=int, default=600)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run triage once; never modify source, trade, commit, or merge."""
    parsed = build_parser().parse_args(arguments)
    config = QualityTriageConfig(
        repository_root=parsed.repository_root,
        output_directory=parsed.output_directory,
        command_timeout_seconds=parsed.command_timeout_seconds,
    )
    try:
        report = run_quality_triage(config, revision=parsed.revision)
    except QualityTriageAlreadyRunningError as error:
        print(json.dumps({"status": "BLOCKED", "blocker": str(error)}))
        return 3
    print(json.dumps(to_primitive(report), ensure_ascii=False, sort_keys=True))
    return 0 if report.status == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

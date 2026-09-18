"""Read-only advisory tools retain bounds and fail closed on provider drift."""

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.local_agent.advisory_fixture import LoopbackAdvisoryFixtureProvider
from ai4binance.local_agent.workbench import (
    LocalQwenWorkbench,
    LocalQwenWorkbenchResult,
    LocalToolEvidence,
)
from tests.test_local_qwen_workbench import FakeRunner


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "remote"},
        {"model": "other"},
        {"provider_attempts": 0},
        {"execution_allowed": True},
        {"promotion_status": "LIVE"},
        {"live_eligibility_status": "LIVE"},
    ],
)
def test_workbench_results_reject_invalid_authority(changes: dict[str, Any]) -> None:
    result = LocalQwenWorkbenchResult("READY", "research", "a" * 64, (), ())
    with pytest.raises(ValueError, match=r"drift|attempts|authorize"):
        replace(result, **changes)


def test_tool_evidence_requires_identity() -> None:
    with pytest.raises(ValueError, match="identity"):
        LocalToolEvidence("", "target", "text", "a" * 64, False)


def test_workbench_rejects_invalid_limits_and_requests(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root is unavailable"):
        LocalQwenWorkbench(tmp_path / "absent")
    with pytest.raises(ValueError, match="limits are invalid"):
        LocalQwenWorkbench(tmp_path, max_file_chars=1)
    runner = FakeRunner()
    tool = LocalQwenWorkbench(tmp_path, runner=runner)
    for query in ("x", "x" * 129):
        with pytest.raises(ValueError, match="query length"):
            tool.search(query)
    with pytest.raises(ValueError, match="task length"):
        tool.run(task="x")
    with pytest.raises(ValueError, match="four files"):
        tool.run(task="Review safely", files=("a",) * 5)
    assert runner.calls == 0


@pytest.mark.parametrize("available", [False, True])
def test_workbench_reports_unavailable_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    monkeypatch.setattr(
        "ai4binance.local_agent.workbench.shutil.which",
        lambda name: "git" if available else None,
    )
    monkeypatch.setattr(
        "ai4binance.local_agent.workbench.subprocess.run",
        lambda *a, **k: CompletedProcess("git", 1, "", "unavailable"),
    )
    assert (
        LocalQwenWorkbench(tmp_path).repository_status().content
        == "GIT_STATUS_UNAVAILABLE"
    )


def test_workbench_search_bounds_and_audit_fallback(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "sample.py").write_text("needle\nneedle\n", encoding="utf-8")
    blocked = source / "secrets"
    blocked.mkdir()
    (blocked / "hidden.py").write_text("needle", encoding="utf-8")
    (source / "oversized.py").write_text("x" * 262145, encoding="utf-8")
    (tmp_path / "runtime/artifacts/system_audit").mkdir(parents=True)
    tool = LocalQwenWorkbench(tmp_path, max_search_matches=1)
    assert tool.search("needle").content == "src/sample.py:1: needle"
    assert tool.search("absent").content == "NO_MATCHES"
    assert tool.latest_system_audit() is None
    with pytest.raises(ValueError, match="allowlist"):
        tool.read_file("src/oversized.py")
    audit = tmp_path / "artifacts/system_audit"
    audit.mkdir(parents=True)
    (audit / "system-report-test.json").write_text("{}", encoding="utf-8")
    evidence = tool.latest_system_audit()
    assert evidence is not None
    assert evidence.target == "artifacts/system_audit/system-report-test.json"
    assert evidence.content == "{}"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("", ()),
        (
            '{"broken":',
            ("LOCAL_QWEN_RESPONSE_TRUNCATED", "LOCAL_QWEN_SAFETY_STAMP_MISSING"),
        ),
        ('["RESEARCH_ONLY", "LIVE_ORDER_BLOCKED"]', ()),
    ],
)
def test_workbench_response_integrity(response: str, expected: tuple[str, ...]) -> None:
    assert LocalQwenWorkbench._response_integrity_blockers(response) == expected


@pytest.mark.parametrize(("fixture_id", "prompt"), [("", "review"), ("one", " ")])
def test_fixture_rejects_empty_request(fixture_id: str, prompt: str) -> None:
    runner = FakeRunner()
    with pytest.raises(ValueError, match="request is invalid"):
        LoopbackAdvisoryFixtureProvider(runner).run_fixture(
            prompt, fixture_id=fixture_id
        )
    assert runner.calls == 0


def test_fixture_rejects_naive_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        LoopbackAdvisoryFixtureProvider(
            FakeRunner(), clock=lambda: datetime(2026, 9, 1)
        ).run_fixture("review", fixture_id="one")


def test_fixture_rejects_untrusted_runner_authority() -> None:
    class UntrustedRunner:
        def run(self, prompt: str, hits: object) -> SimpleNamespace:
            from hashlib import sha256

            return SimpleNamespace(
                prompt_sha256=sha256(prompt.encode()).hexdigest(),
                execution_allowed=True,
                live_eligibility_status="LIVE",
            )

    with pytest.raises(ValueError, match="attempted execution authority"):
        LoopbackAdvisoryFixtureProvider(cast(Any, UntrustedRunner())).run_fixture(
            "review", fixture_id="one"
        )

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai4binance.cli import main

PINNED = "b" * 40


def write_source_file(tmp_path: Path) -> Path:
    source = tmp_path / "candidates.json"
    source.write_text(
        json.dumps(
            [
                {
                    "repository": "example/review-agent",
                    "source_url": "https://github.com/example/review-agent",
                    "description": "Reusable agent workflow for review skills",
                    "stars": 250,
                    "language": "Python",
                    "archived": False,
                    "pushed_at": "2026-07-20T00:00:00+00:00",
                    "pinned_revision": PINNED,
                    "topics": ["agent", "workflow"],
                    "documents": [
                        {
                            "path": "README.md",
                            "text": (
                                "Workflow: discover filter read extract score "
                                "generate review publish reusable agent skill."
                            ),
                        },
                        {
                            "path": "examples/example.md",
                            "text": "Example validation rubric for workflow review.",
                        },
                    ],
                }
            ],
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return source


def test_skill_discovery_cli_once_and_status_are_fail_closed(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = write_source_file(tmp_path)

    assert (
        main(
            [
                "skill-discovery-once",
                "--source-file",
                str(source),
                "--max-candidates",
                "1",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "READY"
    assert payload["execution_allowed"] is False
    assert payload["installation_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["report"]["drafts_created"] == 1
    assert (tmp_path / "State" / "skill-discovery.json").exists()

    assert main(["skill-discovery-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "READY"
    assert status["report"]["drafts_created"] == 1
    assert status["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_skill_discovery_daemon_runs_bounded_cycle(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = write_source_file(tmp_path)

    assert (
        main(
            [
                "skill-discovery-daemon",
                "--source-file",
                str(source),
                "--max-candidates",
                "1",
                "--max-cycles",
                "1",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "STOPPED"
    assert payload["completed_cycles"] == 1
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert (tmp_path / "State" / "skill-discovery.lock").exists() is False


def test_skill_discovery_daemon_reports_existing_instance_without_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = write_source_file(tmp_path)
    state = tmp_path / "State"
    state.mkdir()
    (state / "skill-discovery.lock").write_text(str(os.getpid()), encoding="ascii")

    assert (
        main(
            [
                "skill-discovery-daemon",
                "--source-file",
                str(source),
                "--max-candidates",
                "1",
                "--max-cycles",
                "1",
            ]
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["blockers"] == ["SKILL_DISCOVERY_ALREADY_RUNNING"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

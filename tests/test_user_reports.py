"""User report path and rendering helpers remain local and authority-safe."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.ops import user_reports
from ai4binance.ops.user_reports import (
    canonical_system_root,
    render_professional_summary,
    user_report_paths,
    write_user_report_files,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def test_user_report_paths_write_historical_and_latest_files(tmp_path: Path) -> None:
    paths = user_report_paths(
        tmp_path,
        "ykb",
        "20260823T120000Z",
        file_stem="ykb_report",
    )
    markdown = render_professional_summary(
        title="YKB Local Report",
        observed_at=NOW.isoformat(),
        status="READY",
        summary="Local report is ready for human review.",
        blockers=("LIVE_ORDER_BLOCKED",),
        sections=(
            ("Evidence", ("- Source evidence is local.",)),
            ("Empty Section", ()),
        ),
    )

    write_user_report_files(
        paths,
        {
            "observed_at": NOW,
            "status": "READY",
            "execution_allowed": False,
        },
        markdown,
    )

    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    latest_payload = json.loads(paths.latest_json_path.read_text(encoding="utf-8"))
    assert paths.report_dir == tmp_path / "runtime" / "reports" / "ykb"
    assert (
        paths.artifact_dir
        == tmp_path / "runtime" / "artifacts" / "user_reports" / "ykb"
    )
    assert payload == latest_payload
    assert payload["execution_allowed"] is False
    assert paths.markdown_path.read_text(encoding="utf-8") == markdown
    assert paths.latest_markdown_path.read_text(encoding="utf-8") == markdown
    assert "LIVE_ORDER_BLOCKED" in markdown
    assert "- No reportable item is available." in markdown


def test_canonical_system_root_allows_temp_root_during_pytest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test-user-reports")

    assert canonical_system_root(tmp_path) == tmp_path


def test_canonical_system_root_enforces_configured_root_outside_pytest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    canonical = tmp_path / "canonical"
    requested = tmp_path / "requested"
    monkeypatch.setattr(user_reports, "CANONICAL_SYSTEM_ROOT", canonical)

    with pytest.raises(ValueError, match="UNAVAILABLE"):
        canonical_system_root(requested)

    canonical.mkdir()
    requested.mkdir()
    with pytest.raises(ValueError, match="CANONICAL_ROOT_REQUIRED"):
        canonical_system_root(requested)

    assert canonical_system_root(canonical) == canonical

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from ai4binance.infrastructure.filesystem.runtime_artifacts.layout import (
    RuntimeArtifactLayoutManifest,
    RuntimeRetentionPolicy,
)
from ai4binance.ops.runtime_hygiene import (
    build_runtime_hygiene_report,
    persist_runtime_hygiene_report,
)
from ai4binance.ops import runtime_hygiene


def _manifest() -> RuntimeArtifactLayoutManifest:
    return RuntimeArtifactLayoutManifest(
        canonical_root="runtime/artifacts",
        legacy_root="artifacts",
        roots={"maintenance_archive": "runtime/artifacts/maintenance_archive"},
        legacy_roots={"artifacts/archive": "runtime/artifacts/maintenance_archive"},
        capacity_budgets={"runtime/data": 10, "runtime/dashboard": 10},
        retention={
            "quality": RuntimeRetentionPolicy(
                path="runtime/quality",
                cleanup_mode="OWNER_REVIEW_REQUIRED",
                minimum_age_days=30,
                keep_latest=1,
                automatic_cleanup=False,
            ),
            "logs": RuntimeRetentionPolicy(
                path="runtime/logs",
                cleanup_mode="OWNER_REVIEW_REQUIRED",
                minimum_age_days=7,
                keep_latest=0,
                automatic_cleanup=False,
                entry_kind="log_file",
            ),
        },
    )


def test_runtime_hygiene_report_is_exact_excludes_private_roots_and_tracks_delta(
    tmp_path: Path,
) -> None:
    data = tmp_path / "runtime" / "data"
    dashboard_profile = tmp_path / "runtime" / "dashboard" / "browser-profile"
    dashboard_runtime = tmp_path / "runtime" / "dashboard" / "runtime"
    quality_old = tmp_path / "runtime" / "quality" / "old"
    quality_new = tmp_path / "runtime" / "quality" / "new"
    stale_log = tmp_path / "runtime" / "logs" / "stale.jsonl"
    for directory in (
        data,
        dashboard_profile,
        dashboard_runtime,
        quality_old,
        quality_new,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (data / "snapshot.bin").write_bytes(b"01234567890")
    (dashboard_profile / "private.db").write_bytes(b"private")
    (dashboard_runtime / "manifest.json").write_text("{}", encoding="utf-8")
    (quality_old / "summary.json").write_text("{}", encoding="utf-8")
    (quality_new / "summary.json").write_text("{}", encoding="utf-8")
    stale_log.parent.mkdir(parents=True, exist_ok=True)
    stale_log.write_text("old\n", encoding="utf-8")
    old_timestamp = (datetime.now(UTC) - timedelta(days=31)).timestamp()
    for path in (quality_old, quality_old / "summary.json", stale_log):
        os.utime(path, (old_timestamp, old_timestamp))

    report = build_runtime_hygiene_report(
        tmp_path,
        observed_at=datetime.now(UTC),
        previous_payload={
            "capacity": [
                {"path": "runtime/data", "total_bytes": 1},
                {"path": "runtime/dashboard", "total_bytes": 2},
            ]
        },
        manifest=_manifest(),
    )

    capacity = {
        str(item["path"]): item
        for item in cast(list[dict[str, object]], report["capacity"])
    }
    assert capacity["runtime/data"]["total_bytes"] == 11
    assert capacity["runtime/data"]["delta_bytes"] == 10
    assert capacity["runtime/data"]["review_required"] is True
    assert capacity["runtime/dashboard"]["total_bytes"] == 2
    assert capacity["runtime/dashboard"]["excluded_paths"] == [
        "runtime/dashboard/browser-profile"
    ]
    assert capacity["runtime/dashboard"]["access_errors"] == []
    review = {
        str(item["policy_id"]): item
        for item in cast(list[dict[str, object]], report["retention_review"])
    }
    assert review["quality"]["eligible_entry_count"] == 1
    assert review["logs"]["eligible_entry_count"] == 1
    assert report["status"] == "OWNER_REVIEW_REQUIRED"
    assert report["execution_allowed"] is False
    assert report["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_runtime_hygiene_report_persistence_is_bound_to_maintenance_archive(
    tmp_path: Path,
) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "src").mkdir()
    payload: dict[str, object] = {"status": "PASS"}
    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "maintenance_archive"
        / "runtime_hygiene"
        / "report.json"
    )

    persist_runtime_hygiene_report(payload, output)

    assert output.read_text(encoding="utf-8") == '{\n  "status": "PASS"\n}\n'
    with pytest.raises(ValueError, match="maintenance archive"):
        persist_runtime_hygiene_report(payload, tmp_path / "runtime" / "report.json")


def test_runtime_hygiene_helper_fail_closed_paths_and_retention(tmp_path: Path) -> None:
    assert runtime_hygiene._scan_exact(tmp_path / "missing", tmp_path) == (
        0,
        0,
        None,
        None,
        (),
        (),
    )
    assert runtime_hygiene._review_entries(tmp_path / "missing", "directory") == []
    assert runtime_hygiene._entry_size(tmp_path / "missing") == 0
    assert runtime_hygiene._previous_sizes(None) == {}
    assert runtime_hygiene._previous_sizes({"capacity": "invalid"}) == {}
    assert runtime_hygiene._previous_sizes({"capacity": ["invalid", {"path": 1}]}) == {}
    assert runtime_hygiene._timestamp(None) is None
    assert runtime_hygiene._is_relative_to(tmp_path, tmp_path) is True
    assert runtime_hygiene._is_relative_to(tmp_path, tmp_path / "other") is False
    assert runtime_hygiene._load_previous(None) is None
    previous = tmp_path / "previous.json"
    previous.write_text("[]", encoding="utf-8")
    assert runtime_hygiene._load_previous(previous) is None
    previous.write_text('{"capacity": []}', encoding="utf-8")
    assert runtime_hygiene._load_previous(previous) == {"capacity": []}
    with pytest.raises(ValueError, match="repository root"):
        runtime_hygiene._repository_root_from_output(Path("C:/runtime-hygiene-no-repo/report.json"))


def test_runtime_hygiene_main_resolves_relative_paths_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "src").mkdir()
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        runtime_hygiene,
        "build_runtime_hygiene_report",
        lambda root, **kwargs: observed.update(root=root, **kwargs)
        or {"status": "PASS"},
    )
    monkeypatch.setattr(
        runtime_hygiene,
        "persist_runtime_hygiene_report",
        lambda payload, output: observed.update(payload=payload, output=output),
    )
    assert (
        runtime_hygiene.main(
            [
                "--repository-root",
                str(tmp_path),
                "--output",
                "runtime/artifacts/maintenance_archive/runtime_hygiene/report.json",
                "--previous-report",
                "previous.json",
            ]
        )
        == 0
    )
    assert observed["root"] == tmp_path.resolve()
    assert (
        observed["output"]
        == tmp_path
        / "runtime/artifacts/maintenance_archive/runtime_hygiene/report.json"
    )
    assert observed["previous_payload"] is None
    assert '"status": "PASS"' in capsys.readouterr().out

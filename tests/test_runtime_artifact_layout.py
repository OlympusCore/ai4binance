import tomllib
from pathlib import Path

from ai4binance.infrastructure.filesystem.runtime_artifacts import (
    load_runtime_artifact_layout_manifest,
)


def test_runtime_artifact_layout_manifest_canonicalizes_legacy_paths() -> None:
    layout = load_runtime_artifact_layout_manifest()

    assert layout.root_for("quality_gate") == "runtime/artifacts/quality/gate"
    assert (
        layout.canonicalize_uri("artifacts/quality_gate/latest.json")
        == "runtime/artifacts/quality/gate/latest.json"
    )
    assert (
        layout.canonicalize_uri("artifacts/market-outlook/state.json")
        == "runtime/artifacts/decisions/market_outlook/state.json"
    )
    assert (
        layout.canonicalize_uri(
            "runtime/artifacts/backtest/validation/BTCUSDT/1h/run.jsonl"
        )
        == "runtime/artifacts/research/backtest/validation/BTCUSDT/1h/run.jsonl"
    )


def test_process_temp_layout_contract_matches_runtime_bootstrap_and_cleanup() -> None:
    layout = load_runtime_artifact_layout_manifest()
    with Path("pyproject.toml").open("rb") as stream:
        runtime = tomllib.load(stream)["tool"]["ai4binance"]["runtime"]
    cleanup = (Path("scripts") / "cleanup_generated_artifacts.ps1").read_text(
        encoding="utf-8"
    )

    assert layout.root_for("tmp_process") == runtime["temporary_directory"]
    assert layout.root_for("tmp_process_pytest") == "runtime/tmp/process/pytest"
    runtime_tmp = layout.retention_for("runtime_tmp")
    validator_runs = layout.retention_for("repository_validator_test_runs")
    quality_runs = layout.retention_for("quality_gate_runs")
    runtime_quality_runs = layout.retention_for("runtime_quality_runs")
    runtime_logs = layout.retention_for("runtime_logs")
    assert runtime_tmp.cleanup_mode == "RuntimeTmpRetention"
    assert runtime_tmp.minimum_age_days == 2
    assert runtime_tmp.automatic_cleanup is True
    assert validator_runs.keep_latest == 20
    assert validator_runs.automatic_cleanup is True
    assert quality_runs.automatic_cleanup is False
    assert runtime_quality_runs.path == "runtime/quality"
    assert runtime_quality_runs.keep_latest == 25
    assert runtime_logs.entry_kind == "log_file"
    assert layout.capacity_budgets["runtime/data"] == 20 * 1024 * 1024 * 1024
    assert "runtime_artifact_layout_manifest.json" in cleanup
    assert "$runtimeArtifactLayout.roots.tmp_process" in cleanup
    assert "$runtimeArtifactLayout.roots.tmp_process_pytest" in cleanup
    assert '"ProcessTempRetention"' in cleanup
    assert '"RuntimeTmpRetention"' in cleanup
    assert '"RuntimeRunRetention"' in cleanup

"""Fail-closed coverage for the canonical backtest layout manifest."""

import json
from pathlib import Path
from typing import cast

import pytest

from ai4binance.research.backtesting import layout

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "research" / "backtest_layout_manifest.json"


def _manifest() -> dict[str, object]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _write_manifest(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_backtest_layout_rejects_invalid_manifest_shapes_and_paths(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must be an object"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, ()))

    payload = _manifest()
    payload["schema_version"] = "2.0"
    with pytest.raises(ValueError, match="schema version"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, payload))

    payload = _manifest()
    payload["artifact_roots"] = ()
    with pytest.raises(ValueError, match="artifact_roots must be an object"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, payload))

    payload = _manifest()
    payload["source_code_root"] = " "
    with pytest.raises(ValueError, match="source_code_root must be a non-empty string"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, payload))

    payload = _manifest()
    payload["legacy_source_roots"] = "invalid"
    with pytest.raises(ValueError, match="legacy_source_roots must be a list"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, payload))

    payload = _manifest()
    payload["legacy_source_roots"] = ["", "legacy"]
    with pytest.raises(ValueError, match="must contain non-empty strings"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, payload))

    payload = _manifest()
    payload["legacy_source_roots"] = ["legacy", "legacy"]
    with pytest.raises(ValueError, match="must be unique"):
        layout.load_backtest_layout_manifest(_write_manifest(tmp_path, payload))


def test_backtest_layout_aliases_and_invalid_dataclass_values() -> None:
    manifest = layout.load_backtest_layout_manifest(MANIFEST_PATH)

    assert manifest.canonicalize_uri(
        "src\\ai4binance\\research\\backtesting\\engine.py"
    ) == ("src/ai4binance/research/backtesting/engine.py")
    assert manifest.canonicalize_uri("backtest/validation/BTCUSDT/1h/run.jsonl") == (
        "runtime/artifacts/research/backtest/validation/BTCUSDT/1h/run.jsonl"
    )
    with pytest.raises(ValueError, match="paths must be non-empty"):
        layout.BacktestLayoutManifest(
            source_code_root="",
            legacy_source_roots=("legacy",),
            validation_root="validation",
            walk_forward_root="walk-forward",
            oos_root="oos",
            robustness_root="robustness",
            holdout_root="holdout",
            ledger_root="ledger",
            report_root="report",
        )


def test_backtest_layout_builds_canonical_paths_and_keeps_unknown_uri() -> None:
    manifest = layout.load_backtest_layout_manifest(MANIFEST_PATH)
    root = Path("runtime/artifacts/research/backtest")

    assert layout.default_backtest_layout_manifest_path() == MANIFEST_PATH
    assert manifest.canonicalize_uri("unknown/path") == "unknown/path"
    assert manifest.validation_artifact_path(root, "btcusdt", "1h", "trend") == (
        root / "BTCUSDT" / "1h" / "trend.jsonl"
    )
    assert manifest.validation_run_card_path(root, "btcusdt", "1h", "trend") == (
        root / "BTCUSDT" / "1h" / "trend.run-card.json"
    )
    assert manifest.blocker_dashboard_path(root, "btcusdt") == (
        root / "BTCUSDT" / "blocker-dashboard.json"
    )
    assert (
        manifest.research_run_cards_ledger_path(root)
        == root / "research_run_cards.jsonl"
    )
    assert (
        manifest.blocker_dashboard_ledger_path(root)
        == root / "blocker_dashboards.jsonl"
    )
    artifact, markdown = manifest.report_paths(
        Path("runtime/reports/backtest"), "btcusdt", "1h", "trend"
    )
    assert artifact == (
        Path(
            "runtime/artifacts/research/backtest/reports/validation/BTCUSDT/1h/trend"
        ).with_suffix(".summary.json")
    )
    assert markdown == Path(
        "runtime/reports/backtest/validation/BTCUSDT/1h/trend.summary.md"
    )
    with pytest.raises(ValueError, match="legacy source roots must be unique"):
        layout.BacktestLayoutManifest(
            source_code_root="source",
            legacy_source_roots=("legacy", "legacy"),
            validation_root="validation",
            walk_forward_root="walk-forward",
            oos_root="oos",
            robustness_root="robustness",
            holdout_root="holdout",
            ledger_root="ledger",
            report_root="report",
        )

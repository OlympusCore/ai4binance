"""Canonical backtesting source, artifact, and report layout manifest."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def default_backtest_layout_manifest_path() -> Path:
    """Return the default backtest layout manifest path."""
    return _repository_root().joinpath(
        "config",
        "research",
        "backtest_layout_manifest.json",
    )


@dataclass(frozen=True, slots=True)
class BacktestLayoutManifest:
    """Validated repository layout for backtesting code and evidence."""

    source_code_root: str
    legacy_source_roots: tuple[str, ...]
    validation_root: str
    walk_forward_root: str
    oos_root: str
    robustness_root: str
    holdout_root: str
    ledger_root: str
    report_root: str

    def __post_init__(self) -> None:
        values = (
            self.source_code_root,
            self.validation_root,
            self.walk_forward_root,
            self.oos_root,
            self.robustness_root,
            self.holdout_root,
            self.ledger_root,
            self.report_root,
            *self.legacy_source_roots,
        )
        if any(not value.strip() for value in values):
            raise ValueError("backtest layout paths must be non-empty")
        if len(set(self.legacy_source_roots)) != len(self.legacy_source_roots):
            raise ValueError("legacy source roots must be unique")

    @property
    def artifact_aliases(self) -> tuple[tuple[str, str], ...]:
        """Return legacy-to-canonical artifact prefix mappings."""
        return (
            ("backtest/validation", self.validation_root),
            ("backtest/walk-forward", self.walk_forward_root),
            ("backtest/oos", self.oos_root),
            ("backtest/robustness", self.robustness_root),
            ("backtest/holdout", self.holdout_root),
        )

    @property
    def source_aliases(self) -> tuple[tuple[str, str], ...]:
        """Return legacy-to-canonical source prefix mappings."""
        return tuple(
            (legacy, self.source_code_root) for legacy in self.legacy_source_roots
        )

    def canonicalize_uri(self, uri: str) -> str:
        """Normalize known legacy backtest source and artifact URIs."""
        normalized = uri.replace("\\", "/").strip()
        for legacy, canonical in (*self.source_aliases, *self.artifact_aliases):
            if normalized == legacy or normalized.startswith(f"{legacy}/"):
                suffix = normalized[len(legacy) :].lstrip("/")
                return canonical if not suffix else f"{canonical}/{suffix}"
        return normalized

    def validation_artifact_path(
        self,
        root: Path,
        symbol: str,
        timeframe: str,
        playbook: str,
    ) -> Path:
        """Build the canonical validation JSONL path under a root override."""
        return root / symbol.upper() / timeframe / f"{playbook}.jsonl"

    def validation_run_card_path(
        self,
        root: Path,
        symbol: str,
        timeframe: str,
        playbook: str,
    ) -> Path:
        """Build the canonical run-card path under a root override."""
        return root / symbol.upper() / timeframe / f"{playbook}.run-card.json"

    def blocker_dashboard_path(self, root: Path, symbol: str) -> Path:
        """Build the canonical blocker dashboard path under a root override."""
        return root / symbol.upper() / "blocker-dashboard.json"

    def research_run_cards_ledger_path(self, root: Path) -> Path:
        """Build the canonical run-card ledger path under a root override."""
        return root / "research_run_cards.jsonl"

    def blocker_dashboard_ledger_path(self, root: Path) -> Path:
        """Build the canonical blocker dashboard ledger path under a root override."""
        return root / "blocker_dashboards.jsonl"

    def report_paths(
        self,
        report_root: Path,
        symbol: str,
        timeframe: str,
        playbook: str,
    ) -> tuple[Path, Path]:
        """Return artifact JSON and Markdown paths for one validation run."""
        stem = report_root / "validation" / symbol.upper() / timeframe / playbook
        runtime_root = report_root.parent.parent
        artifact_stem = (
            runtime_root
            / "artifacts"
            / "research"
            / "backtest"
            / "reports"
            / "validation"
            / symbol.upper()
            / timeframe
            / playbook
        )
        return artifact_stem.with_suffix(".summary.json"), stem.with_suffix(
            ".summary.md"
        )


def load_backtest_layout_manifest(
    path: Path | None = None,
) -> BacktestLayoutManifest:
    """Load and validate the backtest layout manifest."""
    manifest_path = path or default_backtest_layout_manifest_path()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("backtest layout manifest must be an object")
    if str(payload.get("schema_version", "")).strip() != "1.0":
        raise ValueError("backtest layout manifest schema version is invalid")
    artifact_roots = _mapping(payload.get("artifact_roots"), "artifact_roots")
    return BacktestLayoutManifest(
        source_code_root=_text(payload, "source_code_root"),
        legacy_source_roots=_text_tuple(payload, "legacy_source_roots"),
        validation_root=_text(artifact_roots, "validation"),
        walk_forward_root=_text(artifact_roots, "walk_forward"),
        oos_root=_text(artifact_roots, "oos"),
        robustness_root=_text(artifact_roots, "robustness"),
        holdout_root=_text(artifact_roots, "holdout"),
        ledger_root=_text(artifact_roots, "ledgers"),
        report_root=_text(payload, "report_root"),
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip().replace("\\", "/")
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _text_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list")
    values = tuple(str(item).strip().replace("\\", "/") for item in raw)
    if not values or any(not item for item in values):
        raise ValueError(f"{key} must contain non-empty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{key} must be unique")
    return values


def _repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "config").is_dir() and (candidate / "src").is_dir():
            return candidate
    raise ValueError("repository root could not be determined from module path")

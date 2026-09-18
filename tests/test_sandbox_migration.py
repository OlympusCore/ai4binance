"""Regression tests for the canonical experiment-sandbox migration."""

from pathlib import Path
from typing import cast

from ai4binance.infrastructure.subprocess import (
    ExperimentManifest,
    ExperimentSandbox,
    ExperimentSandboxBackend,
    ExperimentSandboxPolicy,
    SandboxBackendOutput,
    SandboxCapabilities,
    SandboxRunResult,
    SandboxRunStatus,
    validate_experiment_source,
)
from ai4binance.infrastructure.subprocess.sandbox import (
    ExperimentSandbox as CanonicalExperimentSandbox,
)
from ai4binance.ops.kaizen_quality import build_architecture_baseline
from ai4binance.sandbox import ExperimentManifest as LegacyExperimentManifest
from ai4binance.sandbox import ExperimentSandbox as LegacyExperimentSandbox
from ai4binance.sandbox import (
    ExperimentSandboxBackend as LegacyExperimentSandboxBackend,
)
from ai4binance.sandbox import (
    ExperimentSandboxPolicy as LegacyExperimentSandboxPolicy,
)
from ai4binance.sandbox import SandboxBackendOutput as LegacySandboxBackendOutput
from ai4binance.sandbox import SandboxCapabilities as LegacySandboxCapabilities
from ai4binance.sandbox import SandboxRunResult as LegacySandboxRunResult
from ai4binance.sandbox import SandboxRunStatus as LegacySandboxRunStatus
from ai4binance.sandbox import (
    validate_experiment_source as legacy_validate_experiment_source,
)

ROOT = Path(__file__).resolve().parents[1]


def test_sandbox_facade_preserves_public_identity() -> None:
    assert ExperimentSandbox is CanonicalExperimentSandbox
    assert LegacyExperimentManifest is ExperimentManifest
    assert LegacyExperimentSandbox is ExperimentSandbox
    assert LegacyExperimentSandboxBackend is ExperimentSandboxBackend
    assert LegacyExperimentSandboxPolicy is ExperimentSandboxPolicy
    assert LegacySandboxBackendOutput is SandboxBackendOutput
    assert LegacySandboxCapabilities is SandboxCapabilities
    assert LegacySandboxRunResult is SandboxRunResult
    assert LegacySandboxRunStatus is SandboxRunStatus
    assert legacy_validate_experiment_source is validate_experiment_source


def test_sandbox_migration_is_recorded_as_canonical_and_facade() -> None:
    payload = build_architecture_baseline(ROOT).to_payload()
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    by_path = {cast(str, item["source_path"]): item for item in ledger}

    canonical_path = "src/ai4binance/infrastructure/subprocess/sandbox.py"
    canonical = by_path[canonical_path]
    assert canonical["classification"] == "KEEP"
    assert canonical["confidence"] == "HIGH"
    assert canonical["blockers"] == []

    facade = by_path["src/ai4binance/sandbox.py"]
    assert facade["classification"] == "FACADE"
    assert facade["target_paths"] == [canonical_path]
    assert facade["execution_allowed"] is False
    assert facade["promotion_status"] == "RESEARCH_ONLY"
    assert facade["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

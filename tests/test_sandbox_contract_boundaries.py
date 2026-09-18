"""Sandbox policy and result contracts preserve explicit isolation boundaries."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai4binance.infrastructure.subprocess.sandbox import (
    ExperimentManifest,
    ExperimentSandbox,
    ExperimentSandboxPolicy,
    SandboxRunResult,
    SandboxRunStatus,
)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("allowed_imports", ("math", "math"), "unique"),
        ("max_source_bytes", 1023, "source limit"),
        ("max_source_bytes", 1_048_577, "source limit"),
        ("max_output_bytes", 1023, "output limit"),
        ("max_output_bytes", 1_048_577, "output limit"),
        ("timeout_seconds", float("nan"), "timeout"),
        ("timeout_seconds", 0.09, "timeout"),
        ("timeout_seconds", 61, "timeout"),
        ("memory_limit_mb", 63, "memory"),
        ("memory_limit_mb", 4097, "memory"),
        ("cpu_limit", float("inf"), "CPU"),
        ("cpu_limit", 0.09, "CPU"),
        ("cpu_limit", 4.1, "CPU"),
    ],
)
def test_sandbox_policy_rejects_ambiguous_or_unbounded_limits(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(ExperimentSandboxPolicy(), **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("experiment_id", "", "identity"),
        ("source_sha256", "short", "hash"),
        ("created_at", datetime(2026, 1, 1), "timezone-aware"),
        ("network_allowed", True, "authority"),
        ("execution_authority", True, "authority"),
    ],
)
def test_sandbox_manifest_rejects_unbound_or_privileged_execution(
    field: str, value: object, message: str
) -> None:
    manifest = ExperimentManifest(
        "experiment-1", datetime(2026, 1, 1, tzinfo=UTC), "a" * 64, 1.0, 256, 1.0
    )
    with pytest.raises(ValueError, match=message):
        replace(manifest, **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("experiment_id", "", "identity"),
        ("blockers", (), "requires blockers"),
        ("status", SandboxRunStatus.COMPLETED, "cannot contain blockers"),
        ("promotion_status", "LIVE", "research only"),
        ("execution_allowed", True, "research only"),
    ],
)
def test_sandbox_result_cannot_convert_blockers_to_authority(
    field: str, value: object, message: str
) -> None:
    result = SandboxRunResult(
        "experiment-1", SandboxRunStatus.BLOCKED, None, "a" * 64, ("NO_BACKEND",)
    )
    with pytest.raises(ValueError, match=message):
        replace(result, **{field: cast(Any, value)})


def test_sandbox_rejects_missing_identity_and_unsafe_source_before_backend() -> None:
    sandbox = ExperimentSandbox()
    with pytest.raises(ValueError, match="ID cannot be empty"):
        sandbox.run(
            experiment_id=" ",
            source="1 + 1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    result = sandbox.run(
        experiment_id="experiment-1",
        source="import os",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert result.blockers == ("SANDBOX_IMPORT_NOT_ALLOWED",)
    assert result.backend_name is None
    assert result.execution_allowed is False

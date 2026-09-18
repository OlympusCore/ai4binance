"""Compatibility facade for the canonical experiment sandbox adapter."""

from ai4binance.infrastructure.subprocess.sandbox import (
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

__all__ = (
    "ExperimentManifest",
    "ExperimentSandbox",
    "ExperimentSandboxBackend",
    "ExperimentSandboxPolicy",
    "SandboxBackendOutput",
    "SandboxCapabilities",
    "SandboxRunResult",
    "SandboxRunStatus",
    "validate_experiment_source",
)

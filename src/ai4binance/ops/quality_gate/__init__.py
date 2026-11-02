"""Quality gate profile policy, selection, and evidence helpers."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai4binance.ops.quality_gate.policy import (
        AffectedScopeResolutionError,
        QualityGatePolicy,
        QualityGateProfile,
        load_quality_gate_policy,
        resolve_affected_pytest_arguments,
        resolve_profile_pytest_arguments,
        resolve_standard_pytest_arguments,
    )
    from ai4binance.ops.quality_gate.telemetry import (
        QualityStepTelemetry,
        build_compact_quality_console_summary,
        first_actionable_error,
    )

__all__ = [
    "AffectedScopeResolutionError",
    "QualityGatePolicy",
    "QualityGateProfile",
    "QualityStepTelemetry",
    "build_compact_quality_console_summary",
    "first_actionable_error",
    "load_quality_gate_policy",
    "resolve_affected_pytest_arguments",
    "resolve_profile_pytest_arguments",
    "resolve_standard_pytest_arguments",
]

_EXPORTS: dict[str, str] = {
    "AffectedScopeResolutionError": "ai4binance.ops.quality_gate.policy",
    "QualityGatePolicy": "ai4binance.ops.quality_gate.policy",
    "QualityGateProfile": "ai4binance.ops.quality_gate.policy",
    "load_quality_gate_policy": "ai4binance.ops.quality_gate.policy",
    "resolve_affected_pytest_arguments": "ai4binance.ops.quality_gate.policy",
    "resolve_profile_pytest_arguments": "ai4binance.ops.quality_gate.policy",
    "resolve_standard_pytest_arguments": "ai4binance.ops.quality_gate.policy",
    "QualityStepTelemetry": "ai4binance.ops.quality_gate.telemetry",
    "build_compact_quality_console_summary": "ai4binance.ops.quality_gate.telemetry",
    "first_actionable_error": "ai4binance.ops.quality_gate.telemetry",
}


def __getattr__(name: str) -> object:
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

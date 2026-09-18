"""Bounded, report-only operational workflows."""

from importlib import import_module
from typing import TYPE_CHECKING

from ai4binance.ops.coverage_audit import (
    CoverageAuditConfig,
    CoverageAuditFile,
    CoverageAuditReport,
    CoverageAuditRow,
    CoverageAuditRule,
    CoverageAuditSort,
    build_coverage_audit_report,
    load_coverage_audit_config,
    load_coverage_audit_files,
)
from ai4binance.ops.coverage_policy import (
    CoverageFamilyConfig,
    CoverageFamilyResult,
    CoveragePolicyConfig,
    CoveragePolicySummary,
    evaluate_coverage_policy,
    load_coverage_policy_config,
)
from ai4binance.ops.decision_telemetry import (
    AcceptanceGateStatus,
    AttributionMethod,
    BlockerEffectivenessRecord,
    BlockerOutcome,
    CanonicalTelemetrySnapshot,
    CounterfactualOutcome,
    CounterfactualType,
    DecisionEffectivenessClass,
    DecisionEffectivenessRecord,
    DecisionInputRecord,
    DecisionOutcomeRecord,
    DecisionProcessRecord,
    DecisionTelemetryFabricRecord,
    DecisionTelemetryLedger,
    DecisionTelemetryStatus,
    DgeEffectivenessMetrics,
    DgeEffectivenessStatus,
    DgeRuleEffectivenessMetrics,
    EvidenceQuality,
    ImprovementCandidate,
    LineageStatus,
    MarketType,
    MetricEvidence,
    OpportunityCostType,
    OutcomeAttribution,
    OutcomeLifecycle,
    PerformanceAcceptanceResult,
    PerformanceEvidenceSnapshot,
    TelemetryDomain,
    build_performance_evidence_snapshot,
    evaluate_lineage_completeness,
)
from ai4binance.ops.performance import (
    BenchmarkArtifactWriter,
    BenchmarkMeasurement,
    PerformanceComparison,
    PerformanceRegressionPolicy,
    compare_performance,
    measure_operation,
)
from ai4binance.ops.runtime import (
    PrivateRuntimeStatusStore,
    RuntimeManagementLedger,
    RuntimeStatusStore,
    RuntimeSupervisor,
    SingleInstanceLease,
)

if TYPE_CHECKING:
    from ai4binance.ops.scripts_inventory import (
        DuplicateBlockEvidence,
        ScriptInventoryEntry,
        ScriptsInventoryReport,
        build_scripts_inventory_report,
        persist_scripts_inventory_report,
    )

_SCRIPTS_INVENTORY_EXPORTS = frozenset(
    {
        "DuplicateBlockEvidence",
        "ScriptInventoryEntry",
        "ScriptsInventoryReport",
        "build_scripts_inventory_report",
        "persist_scripts_inventory_report",
    }
)


def __getattr__(name: str) -> object:
    if name in _SCRIPTS_INVENTORY_EXPORTS:
        module = import_module("ai4binance.ops.scripts_inventory")
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = (
    "AcceptanceGateStatus",
    "AttributionMethod",
    "BenchmarkArtifactWriter",
    "BenchmarkMeasurement",
    "BlockerEffectivenessRecord",
    "BlockerOutcome",
    "CanonicalTelemetrySnapshot",
    "CounterfactualOutcome",
    "CounterfactualType",
    "CoverageAuditConfig",
    "CoverageAuditFile",
    "CoverageAuditReport",
    "CoverageAuditRow",
    "CoverageAuditRule",
    "CoverageAuditSort",
    "CoverageFamilyConfig",
    "CoverageFamilyResult",
    "CoveragePolicyConfig",
    "CoveragePolicySummary",
    "DecisionEffectivenessClass",
    "DecisionEffectivenessRecord",
    "DecisionInputRecord",
    "DecisionOutcomeRecord",
    "DecisionProcessRecord",
    "DecisionTelemetryFabricRecord",
    "DecisionTelemetryLedger",
    "DecisionTelemetryStatus",
    "DgeEffectivenessMetrics",
    "DgeEffectivenessStatus",
    "DgeRuleEffectivenessMetrics",
    "DuplicateBlockEvidence",
    "EvidenceQuality",
    "ImprovementCandidate",
    "LineageStatus",
    "MarketType",
    "MetricEvidence",
    "OpportunityCostType",
    "OutcomeAttribution",
    "OutcomeLifecycle",
    "PerformanceAcceptanceResult",
    "PerformanceComparison",
    "PerformanceEvidenceSnapshot",
    "PerformanceRegressionPolicy",
    "PrivateRuntimeStatusStore",
    "RuntimeManagementLedger",
    "RuntimeStatusStore",
    "RuntimeSupervisor",
    "ScriptInventoryEntry",
    "ScriptsInventoryReport",
    "SingleInstanceLease",
    "TelemetryDomain",
    "build_coverage_audit_report",
    "build_performance_evidence_snapshot",
    "build_scripts_inventory_report",
    "compare_performance",
    "evaluate_coverage_policy",
    "evaluate_lineage_completeness",
    "load_coverage_audit_config",
    "load_coverage_audit_files",
    "load_coverage_policy_config",
    "measure_operation",
    "persist_scripts_inventory_report",
)

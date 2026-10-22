"""Isolated test-only Core assurance proofs; never operational observations."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

import pytest

from ai4binance.events.traceability import CanonicalTraceJournal
from ai4binance.governance.architecture import (
    CORE_EVIDENCE_DIMENSIONS,
    CoreAssuranceContract,
    CoreInterfaceBinding,
    load_logical_architecture_registry,
)
from ai4binance.governance.architecture.assurance import resolve_core_assurance
from ai4binance.governance.enforcement.receipt import (
    core_consumption_subject_sha256,
    load_core_consumption_batch,
    persist_core_consumption_receipt,
)
from ai4binance.ops.performance import (
    OperationResourceLimits,
    OperationResourceMeasurement,
    measure_resource_operation,
    resource_budget_blockers,
)

ROOT = Path(__file__).resolve().parents[1]


def _limits() -> OperationResourceLimits:
    """Test-only numeric limits; these are not proposed production budgets."""
    return OperationResourceLimits(
        10, 10, 10, 10, 0, 0, 0, "RUNNER_ENFORCED", "PROCESS_LIFETIME_HIGH_WATERMARK"
    )


def _measurement() -> OperationResourceMeasurement:
    return OperationResourceMeasurement(
        1,
        1,
        1,
        1,
        max_retries=0,
        llm_calls=0,
        gpu_memory_mb=0,
        timeout_policy="RUNNER_ENFORCED",
        operation_scope="CORE_HANDOFF",
    )


def test_all_twelve_cores_declare_contracts_without_inventing_budgets() -> None:
    registry = load_logical_architecture_registry()
    for core in registry.core_modules:
        assert core.assurance is not None
        assert core.assurance.required_dimensions == CORE_EVIDENCE_DIMENSIONS
        assert core.assurance.interfaces
        assert core.assurance.failure_test_refs
        assert core.assurance.resource_budget_ref is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("required_dimensions", ("ownership",)),
        ("evidence_max_age_seconds", True),
        ("evidence_max_age_seconds", 86401),
        ("resource_budget_ref", "../outside.json"),
        ("failure_test_refs", ("../test.py::bad",)),
    ],
)
def test_assurance_contract_rejects_missing_dimensions_and_unsafe_references(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="core"):
        CoreAssuranceContract(**{field: value})  # type: ignore[arg-type]


def test_interface_rejects_missing_symbols_and_foreign_components() -> None:
    with pytest.raises(ValueError, match="symbol reference"):
        CoreInterfaceBinding(
            "test-only", "policy", "AGENTS.md", "../bad.py::run", "bad.py"
        )
    registry = load_logical_architecture_registry()
    core = registry.core_modules[0]
    assert core.assurance is not None
    binding = replace(core.assurance.interfaces[0], component_id="foreign")
    with pytest.raises(ValueError, match="belong to the core"):
        replace(core, assurance=replace(core.assurance, interfaces=(binding,)))


def test_receipt_is_bound_to_canonical_trace_and_never_promotes_test_observations(
    tmp_path: Path,
) -> None:
    registry = load_logical_architecture_registry()
    journal = CanonicalTraceJournal(tmp_path / "test-only-journal.jsonl")
    path = persist_core_consumption_receipt(
        repository_root=ROOT,
        registry=registry,
        core_id="DataCore",
        interface_id="data-snapshot-acquisition",
        cycle_id="TEST_ONLY_CYCLE",
        source_subject_sha256=core_consumption_subject_sha256(ROOT),
        input_sha256="1" * 64,
        output_sha256="2" * 64,
        outcome_sha256="3" * 64,
        resources=asdict(_measurement()),
        journal=journal,
    )
    proofs = load_core_consumption_batch(journal, ROOT, registry)
    assert len(proofs) == 1
    assert proofs[0]["observation_class"] == "TEST_ONLY"
    assert proofs[0]["execution_allowed"] is False
    core = registry.core_modules[0]
    result = resolve_core_assurance(
        registry, core, ROOT, quality={}, quality_blockers=(), consumption=proofs
    )
    assert result.dimensions["runtime_consumer"] == "UNKNOWN"
    assert not result.operationally_verified
    payload = json.loads(path.read_text())
    payload["consumer_ref"] = "test-only-tamper"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        load_core_consumption_batch(journal, ROOT, registry)


def test_test_only_complete_fixture_has_a_reachable_eight_dimension_acceptance_path(
    tmp_path: Path,
) -> None:
    """Exercise the resolver with isolated fixtures, not real runtime evidence."""
    import shutil

    registry = load_logical_architecture_registry()
    core = registry.core_modules[0]
    assert core.assurance is not None
    for reference in core.accountability_refs.values():
        path = tmp_path / reference
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("TEST_ONLY_ACCOUNTABILITY_FIXTURE")
    schema = tmp_path / "schemas/governance/governed_object_enforcement.schema.json"
    schema.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / schema.relative_to(tmp_path), schema)
    budget = tmp_path / "config/test_only_budget.yaml"
    budget.parent.mkdir(parents=True, exist_ok=True)
    budget.write_text(json.dumps(asdict(_limits())))
    core = replace(
        core,
        assurance=replace(
            core.assurance, resource_budget_ref=budget.relative_to(tmp_path).as_posix()
        ),
    )
    registry = replace(registry, core_modules=(core,), relations=())
    assert core.assurance is not None
    interface = core.assurance.interfaces[0]
    # Synthetic records exist only inside this deterministic acceptance test.
    proof: dict[str, object] = {
        **interface.to_payload(),
        "core_id": core.core_id,
        "observation_class": "OBSERVED_LOCAL_CALL",
        "operation_status": "SUCCESS",
        "resources": asdict(_measurement()),
        "cycle_id": "TEST_ONLY",
        "input_sha256": "1" * 64,
        "output_sha256": "2" * 64,
    }
    quality = {
        "test_results": [
            {"node_id": reference, "result": "PASS"}
            for reference in core.assurance.failure_test_refs
        ]
    }
    result = resolve_core_assurance(
        registry,
        core,
        tmp_path,
        quality=quality,
        quality_blockers=(),
        consumption=(proof,),
    )
    assert set(result.dimensions.values()) == {"PROVEN"}
    assert result.operationally_verified
    invalid = resolve_core_assurance(
        registry,
        core,
        tmp_path,
        quality=quality,
        quality_blockers=(),
        consumption=(proof,),
        trace_blockers=("TEST_ONLY_CORRUPTION",),
    )
    assert not invalid.operationally_verified
    stale = resolve_core_assurance(
        registry,
        core,
        tmp_path,
        quality=quality,
        quality_blockers=("QUALITY_EVIDENCE_STALE",),
        consumption=(proof,),
    )
    assert not stale.operationally_verified
    assert stale.dimensions["failure_behavior"] != "PROVEN"


def test_one_interface_cannot_prove_a_multi_component_core() -> None:
    registry = load_logical_architecture_registry()
    core = next(item for item in registry.core_modules if item.core_id == "SystemCore")
    assert core.assurance is not None
    proof: dict[str, object] = {
        **core.assurance.interfaces[0].to_payload(),
        "core_id": core.core_id,
        "observation_class": "OBSERVED_LOCAL_CALL",
        "operation_status": "SUCCESS",
    }
    result = resolve_core_assurance(
        registry, core, ROOT, quality={}, quality_blockers=(), consumption=(proof,)
    )
    assert result.missing_interface_components
    assert result.dimensions["runtime_consumer"] != "PROVEN"


@pytest.mark.parametrize("error", [TimeoutError, ValueError])
def test_failed_measurements_are_emitted_without_swallowing_the_original_error(
    error: type[Exception],
) -> None:
    observations: list[OperationResourceMeasurement] = []

    def failing_operation() -> None:
        raise error("TEST_ONLY_ERROR")

    with pytest.raises(error, match="TEST_ONLY_ERROR"):
        measure_resource_operation(
            failing_operation, on_measurement=observations.append
        )
    assert len(observations) == 1
    assert observations[0].operation_status == (
        "TIMEOUT" if error is TimeoutError else "ERROR"
    )
    assert observations[0].error_type == error.__name__


def test_resource_limits_require_actual_counters_matching_scope_and_timeout() -> None:
    assert resource_budget_blockers(_measurement(), _limits()) == ()
    unknown = OperationResourceMeasurement(1, 1, None, None)
    blockers = resource_budget_blockers(unknown, _limits())
    assert "RESOURCE_TIMEOUT_NOT_ENFORCED" in blockers
    assert "RESOURCE_LLM_CALLS_UNMEASURED" in blockers
    assert "RESOURCE_GPU_MEMORY_MB_UNMEASURED" in blockers
    assert "RESOURCE_MAX_DURATION_MS_EXCEEDED" in resource_budget_blockers(
        replace(_measurement(), max_duration_ms=11),
        _limits(),
    )


def test_an_allow_decision_cannot_bypass_missing_core_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from ai4binance.governance.enforcement import adapters
    from ai4binance.governance.enforcement.contracts import EnforcementOutcome
    from ai4binance.ops import coverage_architecture

    monkeypatch.setattr(
        adapters,
        "evaluate_registered_entrypoint",
        lambda *a, **k: SimpleNamespace(outcome=EnforcementOutcome.ALLOW),
    )
    monkeypatch.setattr(
        coverage_architecture,
        "core_readiness_blockers",
        lambda *a: ("TEST_ONLY_CORE_EVIDENCE_MISSING",),
    )
    with pytest.raises(ValueError, match="CORE_READINESS_BLOCKED"):
        adapters.require_registered_entrypoint(ROOT, "test-only-route", None, None)  # type: ignore[arg-type]


def test_a_later_rejection_invalidates_an_older_successful_handoff() -> None:
    registry = load_logical_architecture_registry()
    core = registry.core_modules[0]
    assert core.assurance is not None
    success: dict[str, object] = {
        **core.assurance.interfaces[0].to_payload(),
        "core_id": core.core_id,
        "observation_class": "OBSERVED_LOCAL_CALL",
        "operation_status": "SUCCESS",
    }
    denied = {**success, "operation_status": "DENIED"}
    result = resolve_core_assurance(
        registry,
        core,
        ROOT,
        quality={},
        quality_blockers=(),
        consumption=(success, denied),
    )
    assert result.dimensions["runtime_consumer"] == "UNKNOWN"
    assert result.unobserved_interfaces


def test_dependency_handoff_requires_matching_cycle_and_content_hash() -> None:
    from ai4binance.governance.architecture import (
        LogicalArchitectureRelation,
        LogicalRelationType,
    )

    registry = load_logical_architecture_registry()
    core = registry.core_modules[0]
    assert core.assurance is not None
    registry = replace(
        registry,
        relations=(
            LogicalArchitectureRelation(
                "test-only-dependency",
                "data-quality",
                "risk-assessment",
                LogicalRelationType.DEPENDS_ON,
            ),
        ),
    )
    consumer: dict[str, object] = {
        **core.assurance.interfaces[0].to_payload(),
        "core_id": core.core_id,
        "observation_class": "OBSERVED_LOCAL_CALL",
        "operation_status": "SUCCESS",
        "cycle_id": "TEST_ONLY_CYCLE",
        "input_sha256": "1" * 64,
    }
    producer = {
        **consumer,
        "core_id": "RiskCore",
        "interface_id": "test-only-risk",
        "component_id": "risk-assessment",
        "output_sha256": "1" * 64,
    }
    for change, expected in (
        ({}, "PROVEN"),
        ({"cycle_id": "TEST_ONLY_OTHER"}, "DECLARED"),
        ({"output_sha256": "2" * 64}, "DECLARED"),
    ):
        resolved = resolve_core_assurance(
            registry,
            core,
            ROOT,
            quality={},
            quality_blockers=(),
            consumption=(consumer, {**producer, **change}),
        )
        assert resolved.dimensions["dependencies"] == expected


def test_auto_audit_uses_the_existing_trace_receipt_after_consumer_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from ai4binance.config import Settings
    from ai4binance.events.traceability import canonical_trace_sha256
    from ai4binance.ops import auto_audit_loop

    registry = load_logical_architecture_registry()

    def forbidden_reserialization() -> object:
        raise AssertionError("TEST_ONLY_MUST_REUSE_FROZEN_PAYLOAD")

    snapshot = SimpleNamespace(
        logical_architecture_registry=registry,
        to_payload=forbidden_reserialization,
    )
    persisted = SimpleNamespace(
        kaizen_quality_snapshot=snapshot,
        to_payload=forbidden_reserialization,
    )
    initial = SimpleNamespace(
        loop_id="TEST_ONLY_AUDIT",
        to_payload=forbidden_reserialization,
    )
    events: list[object] = []

    def persist_artifacts(*args: object) -> tuple[object, str, str, str]:
        events.append("ARTIFACTS_VERIFIED")
        return (
            persisted,
            "1" * 64,
            "2" * 64,
            canonical_trace_sha256({"test_only_persisted": True}),
        )

    monkeypatch.setattr(
        auto_audit_loop.AutoAuditLoop, "_persist_artifacts", persist_artifacts
    )
    monkeypatch.setattr(
        auto_audit_loop,
        "persist_core_consumption_receipt",
        lambda **kwargs: events.append(kwargs),
    )
    loop = auto_audit_loop.AutoAuditLoop(Settings(), ROOT)
    assert loop._persist(
        cast(auto_audit_loop.AutoAuditLoopResult, initial), datetime.now(UTC)
    ) is cast(auto_audit_loop.AutoAuditLoopResult, persisted)
    assert events[0] == "ARTIFACTS_VERIFIED"
    proof = events[1]
    assert isinstance(proof, dict)
    assert proof["core_id"] == "AuditCore"
    assert proof["outcome_sha256"] == canonical_trace_sha256(
        {"test_only_persisted": True}
    )
    assert proof["resources"]["operation_scope"] == "CORE_HANDOFF"


def test_job_admission_exposes_declared_limits_without_claiming_measurements(
    tmp_path: Path,
) -> None:
    from ai4binance.ops.jobs import (
        JobCapability,
        JobManifest,
        JobRequest,
        assess_job_admission,
    )

    capabilities = (JobCapability.READ_REPOSITORY,)
    manifest = JobManifest(
        "TEST_ONLY_JOB", capabilities, (tmp_path,), 10, 1024, 1, tmp_path / "test.lock"
    )
    request = JobRequest(
        "TEST_ONLY_JOB", "TEST_ONLY_KEY", capabilities, (tmp_path,), True, True
    )
    admission = assess_job_admission(manifest, request)
    assert admission.admitted
    assert admission.timeout_limit_seconds == 10
    assert admission.maximum_output_bytes == 1024
    assert admission.timeout_enforced_by_runner
    assert admission.resource_budget_status == "NOT_VERIFIED"
    assert not admission.execution_allowed


def test_executed_test_nodes_are_distinct_from_declared_files() -> None:
    from ai4binance.ops.quality_gate.telemetry import executed_required_test_nodes

    payload = {
        "test_results": [
            {"node_id": "tests/test_only.py::test_pass[1]", "result": "PASS"},
            {"node_id": "tests/test_only.py::test_skip", "result": "SKIPPED"},
            {"node_id": "tests/other.py::test_pass", "result": "PASS"},
        ]
    }
    assert executed_required_test_nodes(payload, ("tests/test_only.py",)) == (
        "tests/test_only.py::test_pass[1]",
    )


@pytest.mark.parametrize(
    "change",
    [
        {
            "consumer_ref": "src/ai4binance/data/acquisition.py::"
            "DataAcquisitionAgent.acquire"
        },
        {"core_id": "TradeCore"},
        {"operation_status": "DENIED"},
        {"cycle_id": "TEST_ONLY_WRONG_CYCLE"},
    ],
)
def test_rehashing_a_semantically_wrong_receipt_cannot_bypass_binding(
    tmp_path: Path,
    change: dict[str, str],
) -> None:
    from datetime import datetime

    from ai4binance.events.traceability import (
        CanonicalTraceRecord,
        ConsequentialTraceKind,
        canonical_trace_sha256,
    )

    registry = load_logical_architecture_registry()
    original = CanonicalTraceJournal(tmp_path / "original-test-only.jsonl")
    path = persist_core_consumption_receipt(
        repository_root=ROOT,
        registry=registry,
        core_id="DataCore",
        interface_id="data-snapshot-acquisition",
        cycle_id="TEST_ONLY_CYCLE",
        source_subject_sha256=core_consumption_subject_sha256(ROOT),
        input_sha256="1" * 64,
        output_sha256="2" * 64,
        outcome_sha256="3" * 64,
        resources=asdict(_measurement()),
        journal=original,
    )
    payload = {**json.loads(path.read_text()), **change}
    digest = canonical_trace_sha256(payload)
    tampered = path.parent / f"{digest}.json"
    tampered.write_text(json.dumps(payload))
    journal = CanonicalTraceJournal(tmp_path / "rehashed-test-only.jsonl")
    journal.append(
        CanonicalTraceRecord.create(
            trace_id="TEST_ONLY_REHASHED",
            trace_kind=ConsequentialTraceKind.GATE,
            subject_ref="DataCore",
            subject_type="CORE_INTERFACE",
            occurred_at=datetime.fromisoformat(payload["observed_at"]),
            event_name="CORE_OUTPUT_CONSUMED",
            event_status="SUCCESS",
            evidence_refs=(str(tampered.resolve()),),
            related_refs=("data-snapshot-acquisition", "TEST_ONLY_CYCLE"),
            subject_sha256=digest,
        )
    )
    with pytest.raises(ValueError, match="CORE_RECEIPT_BINDING_INVALID"):
        load_core_consumption_batch(journal, ROOT, registry)


def test_source_drift_excludes_history_and_detects_a_change_during_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ai4binance.governance.enforcement import receipt

    registry = load_logical_architecture_registry()
    journal = CanonicalTraceJournal(tmp_path / "test-only.jsonl")
    path = persist_core_consumption_receipt(
        repository_root=ROOT,
        registry=registry,
        core_id="DataCore",
        interface_id="data-snapshot-acquisition",
        cycle_id="TEST_ONLY_CYCLE",
        source_subject_sha256=core_consumption_subject_sha256(ROOT),
        input_sha256="1" * 64,
        output_sha256="2" * 64,
        outcome_sha256="3" * 64,
        resources=asdict(_measurement()),
        journal=journal,
    )
    original = json.loads(path.read_text())["source_hashes"]
    changed = {**original, next(iter(original)): "f" * 64}
    monkeypatch.setattr(receipt, "_core_source_hashes", lambda *args: changed)
    assert load_core_consumption_batch(journal, ROOT, registry) == ()
    assert path.exists()
    samples = iter((original, changed))
    monkeypatch.setattr(receipt, "_core_source_hashes", lambda *args: next(samples))
    with pytest.raises(ValueError, match="SOURCE_CHANGED_DURING_READ"):
        load_core_consumption_batch(journal, ROOT, registry)


def test_core_symbol_checks_never_execute_the_referenced_module(tmp_path: Path) -> None:
    from ai4binance.governance.architecture.loader import require_repository_symbol

    (tmp_path / "test_only.py").write_text(
        'raise AssertionError("TEST_ONLY_MUST_NOT_EXECUTE")\n'
        "def existing_symbol():\n    return None\n"
    )
    require_repository_symbol(tmp_path, "test_only.py::existing_symbol")
    with pytest.raises(ValueError, match="ambiguous or missing"):
        require_repository_symbol(tmp_path, "test_only.py::missing_symbol")


def test_measurement_callback_failure_preserves_the_original_operation_error() -> None:
    def operation() -> None:
        raise TimeoutError("TEST_ONLY_OPERATION_TIMEOUT")

    def callback(_: OperationResourceMeasurement) -> None:
        raise OSError("TEST_ONLY_EVIDENCE_FAILURE")

    with pytest.raises(TimeoutError, match="TEST_ONLY_OPERATION_TIMEOUT") as observed:
        measure_resource_operation(operation, on_measurement=callback)
    assert isinstance(observed.value.__cause__, OSError)


def test_core_assurance_cannot_remove_forbidden_authorities() -> None:
    with pytest.raises(ValueError, match="cannot widen"):
        CoreAssuranceContract(forbidden_authorities=())


def test_core_budget_uses_cumulative_cost_and_keeps_unknown_counters_unknown() -> None:
    from ai4binance.ops.performance import aggregate_resource_measurements

    part = replace(_measurement(), max_duration_ms=6)
    assert not resource_budget_blockers(part, _limits())
    total = aggregate_resource_measurements((part, part))
    assert total.max_duration_ms == 12
    assert total.peak_ram_mb == part.peak_ram_mb
    assert total.disk_io_bytes == 2
    assert "RESOURCE_MAX_DURATION_MS_EXCEEDED" in resource_budget_blockers(
        total, _limits()
    )
    unknown = aggregate_resource_measurements((part, replace(part, llm_calls=None)))
    assert unknown.llm_calls is None
    assert "RESOURCE_LLM_CALLS_UNMEASURED" in resource_budget_blockers(
        unknown, _limits()
    )
    with pytest.raises(ValueError, match="actual observations"):
        aggregate_resource_measurements(())


def test_pre_action_readiness_uses_dependency_closure_and_rejects_missing_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.governance.architecture import (
        LogicalArchitectureRelation,
        LogicalRelationType,
        loader,
    )
    from ai4binance.ops import coverage_architecture
    from ai4binance.ops.coverage_architecture import core_readiness_blockers

    registry = load_logical_architecture_registry()
    registry = replace(
        registry,
        relations=(
            LogicalArchitectureRelation(
                "test-only-policy-risk",
                "policy",
                "risk-assessment",
                LogicalRelationType.DEPENDS_ON,
            ),
        ),
    )
    monkeypatch.setattr(
        loader, "load_logical_architecture_registry", lambda *a, **k: registry
    )
    requested: list[frozenset[str]] = []

    def scoped_view(
        *args: object, required_core_ids: frozenset[str]
    ) -> tuple[dict[str, object], ...]:
        requested.append(required_core_ids)
        return tuple(
            {
                "core_id": core_id,
                "operationally_verified": False,
                "blockers": ["TEST_ONLY_MISSING_PROOF"],
            }
            for core_id in sorted(required_core_ids)
        )

    monkeypatch.setattr(coverage_architecture, "build_core_evidence_view", scoped_view)
    blocked = core_readiness_blockers(ROOT, "governed_parameter_activation")
    assert requested == [frozenset({"SystemCore", "RiskCore"})]
    assert "RiskCore:TEST_ONLY_MISSING_PROOF" in blocked
    assert not any("LearningCore" in item for item in blocked)
    assert core_readiness_blockers(ROOT, "TEST_ONLY_UNKNOWN_ROUTE") == (
        "CORE_ENTRYPOINT_OWNER_UNKNOWN",
    )
    monkeypatch.setattr(
        coverage_architecture, "build_core_evidence_view", lambda *a, **k: ()
    )
    assert core_readiness_blockers(ROOT, "governed_parameter_activation") == (
        "CORE_READINESS_SCOPE_INCOMPLETE",
    )

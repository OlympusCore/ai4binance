from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.governance.architecture import (
    LogicalArchitectureComponent,
    LogicalArchitectureRegistry,
    LogicalArchitectureRelation,
    LogicalComponentKind,
    LogicalRelationType,
)
from ai4binance.ops.coverage_architecture import (
    ArchitectureCoverageRow,
    ArchitectureTargetConfig,
    CoverageArchitectureConfig,
    CoverageArchitectureReport,
    CriticalBehaviorCoverageRow,
    CriticalBehaviorObligationConfig,
    RelationProofConfig,
    evaluate_coverage_architecture,
    load_coverage_architecture_config,
)
from ai4binance.ops.coverage_policy import FileCoverage


def test_repository_architecture_assurance_config_uses_registry_selectors() -> None:
    payload = json.loads(
        Path("config/quality/coverage-targets.json").read_text(encoding="utf-8")
    )

    config = load_coverage_architecture_config(payload["architecture_assurance"])

    assert config is not None
    assert config.registry_path == "docs/registries/registry_logical_architecture.yaml"
    assert {target.name for target in config.targets} == {
        "governance",
        "decision",
        "risk",
        "validation",
        "execution",
        "portfolio_accounting",
        "data_quality",
        "evidence_lineage",
        "event_replay",
        "security_controls",
    }
    assert all(target.canonical_domains for target in config.targets)
    assert all(target.component_ids for target in config.targets)
    assert len(config.relation_proofs) == 11
    assert len(config.obligations) == 11


def test_architecture_assurance_resolves_traceability_without_runtime_claim(
    tmp_path: Path,
) -> None:
    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    report = evaluate_coverage_architecture(
        _config(include_unregistered_target=True),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
        generated_at=datetime(2026, 9, 11, tzinfo=UTC),
    )

    decision = next(row for row in report.architecture_view if row.component_id)
    undeclared = next(row for row in report.architecture_view if not row.component_id)
    behavior = report.critical_behavior_view[0]

    assert decision.state == "IMPLEMENTED_AND_COVERED"
    assert decision.relation_status == "PROVEN"
    assert decision.runtime_evidence == "NOT_REQUIRED"
    assert undeclared.target == "security_controls"
    assert undeclared.state == "NOT_MEASURED"
    assert behavior.covered is True
    assert behavior.asserted is True
    assert behavior.runtime_proven is False
    assert behavior.state == "RUNTIME_EVIDENCE_UNKNOWN"
    assert report.result == "BASELINE_DEBT"
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_architecture_assurance_reports_missing_and_stale_evidence(
    tmp_path: Path,
) -> None:
    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    missing_test = tmp_path / "tests" / "test_decision.py"
    missing_test.unlink()

    missing_report = evaluate_coverage_architecture(
        _config(),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
    )

    assert missing_report.architecture_view[0].state == "IMPLEMENTED_TEST_GAP"
    assert missing_report.critical_behavior_view[0].state == "IMPLEMENTED_TEST_GAP"

    missing_test.write_text(
        'def test_fail_closed() -> None:\n    assert "NO_TRADE" == "NO_TRADE"\n',
        encoding="utf-8",
    )
    stale_report = evaluate_coverage_architecture(
        _config(),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
        coverage_generated_at=datetime(2000, 1, 1, tzinfo=UTC),
    )

    assert stale_report.architecture_view[0].state == "STALE_EVIDENCE"
    assert stale_report.critical_behavior_view[0].state == "STALE_EVIDENCE"


def test_architecture_assurance_resolves_negative_and_runtime_evidence_paths(
    tmp_path: Path,
) -> None:
    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    source = tmp_path / "src" / "decision.py"
    source.unlink()
    missing_source = evaluate_coverage_architecture(
        _config(), _registry(), (_coverage(),), repository_root=tmp_path
    )
    assert missing_source.architecture_view[0].state == "DECLARED_IMPLEMENTATION_GAP"
    assert missing_source.critical_behavior_view[0].state == (
        "DECLARED_IMPLEMENTATION_GAP"
    )

    _write_refs(tmp_path, expected_outcome="WAIT")
    base_config = _config()
    assertion_config = replace(
        base_config,
        relation_proofs=(
            replace(base_config.relation_proofs[0], expected_outcome="WAIT"),
        ),
    )
    assertion_gap = evaluate_coverage_architecture(
        assertion_config, _registry(), (_coverage(),), repository_root=tmp_path
    )
    assert assertion_gap.critical_behavior_view[0].state == "ASSERTION_GAP"

    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    for reference in (
        tmp_path / "src" / "decision.py",
        tmp_path / "docs" / "decision.md",
        tmp_path / "tests" / "test_decision.py",
    ):
        os.utime(reference, (1, 1))
    evidence = tmp_path / "runtime" / "evidence.json"
    evidence.parent.mkdir(parents=True)
    _write_runtime_evidence(
        evidence,
        evidence_kind="obligation",
        evidence_id="risk_veto_denial",
        component_id="decision-core",
        generated_at=datetime(2026, 9, 11, tzinfo=UTC),
    )
    obligation = replace(
        _config().obligations[0], evidence_refs=("runtime/evidence.json",)
    )
    resolved = evaluate_coverage_architecture(
        replace(_config(), obligations=(obligation,)),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
        coverage_generated_at=datetime(2026, 9, 12, tzinfo=UTC),
        generated_at=datetime(2026, 9, 12, tzinfo=UTC),
    )
    assert resolved.critical_behavior_view[0].state == "RESOLVED"
    assert resolved.critical_behavior_view[0].runtime_proven is True

    unknown_owner = evaluate_coverage_architecture(
        replace(
            _config(),
            obligations=(replace(obligation, component_id="unknown-component"),),
        ),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
    )
    assert unknown_owner.critical_behavior_view[0].state == (
        "DECLARED_IMPLEMENTATION_GAP"
    )
    assert unknown_owner.critical_behavior_view[0].owner == "NOT_DECLARED"


def test_architecture_assurance_fails_closed_for_relation_proof_gaps(
    tmp_path: Path,
) -> None:
    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    config = _config()

    undeclared = evaluate_coverage_architecture(
        config,
        replace(_registry(), relations=()),
        (_coverage(),),
        repository_root=tmp_path,
    )
    assert undeclared.architecture_view[0].relation_status == "DECLARATION_MISSING"
    assert undeclared.architecture_view[0].state == "DECLARED_IMPLEMENTATION_GAP"

    missing_assertion = evaluate_coverage_architecture(
        replace(
            config,
            relation_proofs=(
                replace(config.relation_proofs[0], expected_outcome="WAIT"),
            ),
        ),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
    )
    assert missing_assertion.architecture_view[0].relation_status == (
        "TEST_PROOF_MISSING"
    )
    assert missing_assertion.architecture_view[0].state == "IMPLEMENTED_TEST_GAP"

    runtime_unknown = evaluate_coverage_architecture(
        replace(
            config,
            relation_proofs=(
                replace(config.relation_proofs[0], requires_runtime_evidence=True),
            ),
        ),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
    )
    assert runtime_unknown.architecture_view[0].relation_status == (
        "RUNTIME_HANDOFF_UNKNOWN"
    )
    assert runtime_unknown.architecture_view[0].state == "RUNTIME_UNKNOWN"


def test_architecture_assurance_rejects_tampered_runtime_evidence(
    tmp_path: Path,
) -> None:
    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    for reference in (
        tmp_path / "src" / "decision.py",
        tmp_path / "docs" / "decision.md",
        tmp_path / "tests" / "test_decision.py",
    ):
        os.utime(reference, (1, 1))
    evidence = tmp_path / "runtime" / "evidence.json"
    evidence.parent.mkdir(parents=True)
    _write_runtime_evidence(
        evidence,
        evidence_kind="obligation",
        evidence_id="risk_veto_denial",
        component_id="decision-core",
        generated_at=datetime(2026, 9, 11, tzinfo=UTC),
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["payload"]["run_id"] = "tampered"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    obligation = replace(
        _config().obligations[0], evidence_refs=("runtime/evidence.json",)
    )

    report = evaluate_coverage_architecture(
        replace(_config(), obligations=(obligation,)),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
        coverage_generated_at=datetime(2026, 9, 12, tzinfo=UTC),
        generated_at=datetime(2026, 9, 12, tzinfo=UTC),
    )

    assert report.critical_behavior_view[0].runtime_proven is False
    assert report.critical_behavior_view[0].state == "RUNTIME_EVIDENCE_UNKNOWN"


def test_architecture_assurance_is_deterministic_for_identical_inputs(
    tmp_path: Path,
) -> None:
    _write_refs(tmp_path, expected_outcome="NO_TRADE")
    generated_at = datetime(2026, 9, 11, tzinfo=UTC)

    first = evaluate_coverage_architecture(
        _config(),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
        generated_at=generated_at,
    )
    second = evaluate_coverage_architecture(
        _config(),
        _registry(),
        (_coverage(),),
        repository_root=tmp_path,
        generated_at=generated_at,
    )

    assert first.to_payload() == second.to_payload()


def test_architecture_assurance_models_reject_invalid_or_authorizing_states() -> None:
    with pytest.raises(ValueError, match="tier is invalid"):
        replace(_config().targets[0], tier="T9")
    with pytest.raises(ValueError, match="requires critical targets"):
        replace(_config(), targets=())
    with pytest.raises(ValueError, match="requires behavior obligations"):
        replace(_config(), obligations=())
    with pytest.raises(ValueError, match="repository-relative"):
        replace(_config().obligations[0], evidence_refs=("../outside.json",))

    architecture_row = ArchitectureCoverageRow(
        target="decision",
        tier="T0",
        component_id="decision-core",
        canonical_domain="07_DECISION",
        logical_plane="DECISION",
        source_refs=(),
        contract_refs=(),
        test_refs=(),
        statement_coverage=100.0,
        branch_coverage=100.0,
        relation_ids=(),
        relation_status="PROVEN",
        runtime_evidence="NOT_REQUIRED",
        state="IMPLEMENTED_AND_COVERED",
    )
    behavior_row = CriticalBehaviorCoverageRow(
        obligation_id="risk_veto",
        category="RISK_VETO_PATH",
        component_id="decision-core",
        owner="Decision Governance",
        requirement_ref="docs/decision.md",
        source_refs=(),
        test_refs=(),
        assertion_refs=("tests/test_decision.py::test_fail_closed",),
        relation_ids=("core-produces-result",),
        relation_status="PROVEN",
        evidence_refs=(),
        expected_outcome="NO_TRADE",
        covered=True,
        asserted=True,
        runtime_required=True,
        runtime_proven=False,
        state="RUNTIME_EVIDENCE_UNKNOWN",
    )
    report = CoverageArchitectureReport(
        registry_id="registry",
        registry_version="1.0.0",
        registry_path="docs/registry.yaml",
        generated_at_utc=datetime.now(UTC),
        architecture_view=(architecture_row,),
        critical_behavior_view=(behavior_row,),
        architecture_failures=(),
        critical_behavior_failures=(),
        result="PASS",
    )
    assert report.to_payload()["execution_allowed"] is False
    with pytest.raises(ValueError, match="coverage state is invalid"):
        replace(architecture_row, state="UNKNOWN")
    with pytest.raises(ValueError, match="runtime evidence state is invalid"):
        replace(architecture_row, runtime_evidence="INVALID")
    with pytest.raises(ValueError, match="behavior coverage state is invalid"):
        replace(behavior_row, state="UNKNOWN")
    with pytest.raises(ValueError, match="assurance result is invalid"):
        replace(report, result="UNKNOWN")
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(report, execution_allowed=True)


def test_architecture_assurance_config_rejects_non_list_obligations() -> None:
    with pytest.raises(
        ValueError, match="critical_behavior_obligations must be a list"
    ):
        load_coverage_architecture_config(
            {
                "registry_path": "docs/registry.yaml",
                "statement_minimum": 95.0,
                "branch_minimum": 95.0,
                "critical_target_groups": {},
                "critical_behavior_obligations": {},
            }
        )


def _config(*, include_unregistered_target: bool = False) -> CoverageArchitectureConfig:
    targets = [
        ArchitectureTargetConfig(
            name="decision",
            tier="T0",
            canonical_domains=("07_DECISION",),
            component_ids=("decision-core",),
            required_relation_ids=("core-produces-result",),
        )
    ]
    if include_unregistered_target:
        targets.append(
            ArchitectureTargetConfig(
                name="security_controls",
                tier="T0",
                canonical_domains=("16_SECURITY",),
            )
        )
    return CoverageArchitectureConfig(
        registry_path="docs/registries/registry_logical_architecture.yaml",
        statement_minimum=95.0,
        branch_minimum=95.0,
        targets=tuple(targets),
        obligations=(
            CriticalBehaviorObligationConfig(
                obligation_id="risk_veto_denial",
                category="RISK_VETO_PATH",
                component_id="decision-core",
                requirement_ref="docs/decision.md",
                expected_outcome="NO_TRADE",
                test_assertion_refs=("tests/test_decision.py::test_fail_closed",),
                required_relation_ids=("core-produces-result",),
            ),
        ),
        relation_proofs=(
            RelationProofConfig(
                relation_id="core-produces-result",
                test_assertion_refs=("tests/test_decision.py::test_fail_closed",),
                expected_outcome="NO_TRADE",
            ),
        ),
    )


def _registry() -> LogicalArchitectureRegistry:
    return LogicalArchitectureRegistry(
        registry_id="AI4B-TEST-REGISTRY",
        version="1.0.0",
        status="ACTIVE",
        source_of_truth=False,
        execution_allowed=False,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
        components=(
            _component("decision-core"),
            _component("decision-result"),
        ),
        relations=(
            LogicalArchitectureRelation(
                relation_id="core-produces-result",
                from_component_id="decision-core",
                to_component_id="decision-result",
                relation_type=LogicalRelationType.PRODUCES,
            ),
        ),
    )


def _component(component_id: str) -> LogicalArchitectureComponent:
    return LogicalArchitectureComponent(
        component_id=component_id,
        component_kind=LogicalComponentKind.ENGINE,
        canonical_domain="07_DECISION",
        logical_plane="DECISION & EXECUTION PLANE",
        dependency_layer="governance",
        runtime_class="GOVERNED_DETERMINISTIC",
        owner="Decision Governance",
        authority_effect="EVIDENCE_ONLY",
        source_paths=("src/decision.py",),
        contract_refs=("docs/decision.md",),
        test_refs=("tests/test_decision.py",),
        hot_path=True,
        deterministic=True,
        llm_dependency=False,
        side_effects=False,
        decision_authority=False,
        risk_override=False,
        validation_override=False,
        source_of_truth=False,
        execution_allowed=False,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )


def _coverage() -> FileCoverage:
    return FileCoverage(
        path="src/decision.py",
        statements=10,
        covered_lines=10,
        missing_lines=0,
        branches=4,
        covered_branches=4,
        missing_branches=0,
        percent_covered=100.0,
    )


def _write_refs(root: Path, *, expected_outcome: str) -> None:
    source = root / "src" / "decision.py"
    contract = root / "docs" / "decision.md"
    test = root / "tests" / "test_decision.py"
    for path in (source, contract, test):
        path.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def decide() -> str:\n    return 'NO_TRADE'\n", encoding="utf-8")
    contract.write_text("# Decision contract\n", encoding="utf-8")
    test.write_text(
        "def test_fail_closed() -> None:\n"
        f"    assert '{expected_outcome}' == '{expected_outcome}'\n",
        encoding="utf-8",
    )


def _write_runtime_evidence(
    path: Path,
    *,
    evidence_kind: str,
    evidence_id: str,
    component_id: str,
    generated_at: datetime,
) -> None:
    payload = {"run_id": "coverage-assurance-test-run"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_text(
        json.dumps(
            {
                "evidence_type": "COVERAGE_ASSURANCE_RUNTIME_PROOF",
                "evidence_kind": evidence_kind,
                "evidence_id": evidence_id,
                "component_id": component_id,
                "generated_at_utc": generated_at.isoformat(),
                "proof_state": "PROVEN",
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                "payload": payload,
                "payload_hash": hashlib.sha256(canonical).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

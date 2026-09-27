"""Regression coverage for deterministic requirement assurance chains."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.governance.enforcement.inventory import (
    RequirementAssuranceDecision,
    load_enforcement_inventory,
)

ROOT = Path(__file__).parent.parent


def test_requirement_assurance_chain_validates_full_linkage_without_authority() -> None:
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability
    assert traceability is not None

    chains = traceability.assurance_chains(ROOT)

    assert len(chains) == 20
    for chain in chains:
        if chain.assurance_decision is RequirementAssuranceDecision.ASSURED:
            assert not chain.blockers
            assert chain.executed_behavioral_tests
        else:
            assert chain.blockers
            assert not chain.executed_behavioral_tests
    assured = next(item for item in chains if item.requirement_id == "RQ-002")
    assert assured.snapshot_bound is True
    assert len(assured.snapshot_evidence_sha256) == 64
    assert assured.authority_inherited is False
    assert assured.execution_allowed is False
    assert assured.promotion_status == "RESEARCH_ONLY"
    assert assured.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_requirement_assurance_keeps_external_evidence_gaps_blocked() -> None:
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability
    assert traceability is not None

    chains = {item.requirement_id: item for item in traceability.assurance_chains(ROOT)}

    assert chains["RQ-003"].enforcement_points == ("market_snapshot_wire_validation",)
    assert chains["RQ-009"].enforcement_points == ("governed_memory_candidate_intake",)
    assert chains["RQ-013"].assurance_decision is RequirementAssuranceDecision.BLOCKED
    assert chains["RQ-015"].assurance_decision is RequirementAssuranceDecision.BLOCKED
    assert chains["RQ-016"].assurance_decision is RequirementAssuranceDecision.BLOCKED


def test_requirement_assurance_chain_rejects_authority_or_execution_expansion() -> None:
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability
    assert traceability is not None
    assured = next(
        item
        for item in traceability.assurance_chains(ROOT)
        if item.requirement_id == "RQ-002"
    )

    with pytest.raises(ValueError, match="cannot inherit authority"):
        replace(assured, authority_inherited=True)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(assured, execution_allowed=True)


def _quality_fixture(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Construct isolated test-only proof bytes, never production evidence."""
    from ai4binance.ops.quality_gate.telemetry import bind_quality_evidence

    for reference in (
        "config/quality/gates.yaml",
        "config/governance/enforcement_inventory.yaml",
    ):
        target = root / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / reference).read_bytes())
    junit = root / "test-only-results.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase file="tests/test_safety.py" '
        'name="test_fixture" /></testsuite></testsuites>'
    )
    subject: dict[str, object] = {
        "repository_root": str(root),
        "repository_tree_sha256": "1" * 64,
        "git_commit": "2" * 40,
        "change_set_sha256": "3" * 64,
    }
    payload = bind_quality_evidence(
        root,
        {
            "schema_version": 2,
            "profile": "standard",
            "status": "STANDARD_PROFILE_PASS",
            "verification_status": "STANDARD_VERIFIED",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "step_exit_codes": dict.fromkeys(
                (
                    "Ruff format",
                    "Ruff lint",
                    "Ruff maintainability ratchet",
                    "MyPy",
                    "Repository governance validator",
                    "Pytest required",
                ),
                0,
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        run_id="20260927T120001Z",
        junit_path=junit,
        workspace_attestation=subject,
    )
    return subject, payload


def test_current_receipt_preserves_source_and_requires_real_test_bindings(
    tmp_path: Path,
) -> None:
    from ai4binance.ops.quality_gate.telemetry import (
        archive_quality_evidence,
        resolve_requirement_quality_evidence,
        verify_quality_evidence,
    )

    subject, payload = _quality_fixture(tmp_path)
    inventory = tmp_path / "config/governance/enforcement_inventory.yaml"
    original = inventory.read_bytes()
    archive_quality_evidence(tmp_path, payload)
    archive_quality_evidence(tmp_path, payload)
    assert inventory.read_bytes() == original
    resolved, blockers = resolve_requirement_quality_evidence(tmp_path, subject)
    assert not blockers
    assert resolved == payload
    assert not verify_quality_evidence(
        tmp_path,
        resolved,
        workspace_attestation=subject,
        required_tests=("tests/test_safety.py",),
    )
    assert (
        "QUALITY_REQUIRED_TEST_NOT_EXECUTED:tests/missing.py"
        in verify_quality_evidence(
            tmp_path,
            resolved,
            workspace_attestation=subject,
            required_tests=("tests/missing.py",),
        )
    )
    with pytest.raises(ValueError, match="IMMUTABLE_RUN_CONFLICT"):
        archive_quality_evidence(tmp_path, {**payload, "command": "changed"})


@pytest.mark.parametrize(
    "mutation", ["inventory", "proof", "receipt", "subject", "missing"]
)
def test_current_receipt_rejects_tampering_and_missing_evidence(
    tmp_path: Path, mutation: str
) -> None:
    from ai4binance.ops.quality_gate.telemetry import (
        archive_quality_evidence,
        resolve_requirement_quality_evidence,
    )

    subject, payload = _quality_fixture(tmp_path)
    if mutation != "missing":
        archive_quality_evidence(tmp_path, payload)
    if mutation == "inventory":
        path = tmp_path / "config/governance/enforcement_inventory.yaml"
        path.write_bytes(path.read_bytes() + b"\n# altered\n")
    elif mutation == "proof":
        path = (
            tmp_path
            / "runtime/artifacts/quality/gate/runs/20260927T120001Z"
            / "quality_evidence.json"
        )
        path.write_text("{}")
    elif mutation == "receipt":
        path = next(
            (tmp_path / "runtime/artifacts/quality/gate/subjects").glob("*/*.json")
        )
        receipt = json.loads(path.read_text())
        receipt["proof_ref"] = "../../outside.json"
        path.write_text(json.dumps(receipt))
    elif mutation == "subject":
        subject["git_commit"] = "4" * 40
    _, blockers = resolve_requirement_quality_evidence(tmp_path, subject)
    assert blockers


@pytest.mark.parametrize("same_run", [False, True])
def test_failed_run_never_falls_back_to_a_passing_receipt(
    tmp_path: Path, same_run: bool
) -> None:
    from ai4binance.ops.quality_gate.telemetry import (
        archive_quality_evidence,
        bind_quality_failure_evidence,
        resolve_requirement_quality_evidence,
        verify_quality_evidence,
    )

    subject, payload = _quality_fixture(tmp_path)
    archive_quality_evidence(tmp_path, payload)
    failed = bind_quality_failure_evidence(
        tmp_path,
        {
            **payload,
            "status": "QUALITY_GATE_FAILED",
            "verification_status": "NOT_VERIFIED",
        },
        run_id="20260927T120001Z" if same_run else "20260927T120002Z",
        workspace_attestation=subject,
    )
    archive_quality_evidence(tmp_path, failed)
    resolved, blockers = resolve_requirement_quality_evidence(tmp_path, subject)
    assert not blockers
    assert verify_quality_evidence(
        tmp_path, resolved, workspace_attestation=subject
    ) == ("QUALITY_RESULT_FAILED",)


def test_current_quality_cannot_replace_historical_provenance_or_domain_blockers(
    tmp_path: Path,
) -> None:
    from ai4binance.governance.enforcement.inventory import _requirement_assurance_chain
    from ai4binance.ops.quality_gate.telemetry import (
        archive_quality_evidence,
        resolve_requirement_quality_evidence,
    )

    subject, payload = _quality_fixture(tmp_path)
    registry = load_enforcement_inventory().requirement_traceability
    assert registry is not None
    entry = registry.entries[0]
    for ref in (
        entry.authority_ref,
        entry.machine_readable_ref,
        *entry.implementation_refs,
        *entry.test_refs,
    ):
        path = tmp_path / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Test-only historical link.")
    evidence = tmp_path / entry.evidence_ref
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('{"historical_provenance": true}')
    entry = replace(entry, evidence_sha256=sha256(evidence.read_bytes()).hexdigest())
    archive_quality_evidence(tmp_path, payload)
    resolved = resolve_requirement_quality_evidence(tmp_path, subject)
    chain = _requirement_assurance_chain(tmp_path, entry, subject, resolved)
    assert chain.assurance_decision is RequirementAssuranceDecision.ASSURED
    assert not chain.execution_allowed
    blocked = _requirement_assurance_chain(
        tmp_path,
        replace(entry, convergence_state="BLOCKED_BY_OOS_PROMOTION_EVIDENCE"),
        subject,
        resolved,
    )
    assert "CONVERGENCE_BLOCKED_BY_OOS_PROMOTION_EVIDENCE" in blocked.blockers
    evidence.write_text('{"historical_provenance": false}')
    assert (
        "SNAPSHOT_EVIDENCE_HASH_MISMATCH"
        in _requirement_assurance_chain(tmp_path, entry, subject, resolved).blockers
    )

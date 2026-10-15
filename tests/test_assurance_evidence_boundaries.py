"""Test-only evidence must not inherit authority or replace verified observations."""

import gzip
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai4binance.governance import adapters
from ai4binance.governance import personal_research as personal
from ai4binance.governance import technology_language_policy as languages
from ai4binance.governance.enforcement.inventory import (
    RequirementAssuranceChain,
    RequirementAssuranceDecision,
    _repository_file,
    load_enforcement_inventory,
)
from tests.test_dge_recovery_replay_shadow import _radar


def _unproven_chain() -> RequirementAssuranceChain:
    return RequirementAssuranceChain(
        requirement_id="TEST_ONLY_REQUIREMENT",
        authority_clause_ref="TEST_ONLY_CLAUSE",
        contract_or_policy_projection_ref="TEST_ONLY_CONTRACT",
        capability="test_only",
        implementing_components=(),
        enforcement_points=(),
        executed_behavioral_tests=(),
        snapshot_evidence_ref="",
        snapshot_evidence_sha256="",
        snapshot_bound=False,
        assurance_decision=RequirementAssuranceDecision.BLOCKED,
        blockers=("SNAPSHOT_EVIDENCE_MISSING",),
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"requirement_id": " "}, "requires requirement_id"),
        ({"authority_inherited": True}, "cannot inherit authority"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "PROMOTED"}, "research-only"),
        ({"live_eligibility_status": "READY"}, "live orders blocked"),
        ({"blockers": ("MISSING", "MISSING")}, "unique"),
        (
            {"assurance_decision": RequirementAssuranceDecision.ASSURED},
            "contain blockers",
        ),
        (
            {
                "assurance_decision": RequirementAssuranceDecision.ASSURED,
                "blockers": (),
            },
            "snapshot evidence",
        ),
    ],
)
def test_assurance_chain_cannot_claim_unobserved_proof_or_authority(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_unproven_chain(), **changes)
    assert _unproven_chain().blocker_codes == (
        "TEST_ONLY_REQUIREMENT:SNAPSHOT_EVIDENCE_MISSING",
    )


def test_evidence_reference_cannot_escape_repository(tmp_path: Path) -> None:
    assert _repository_file(tmp_path, "../outside.json") is None
    with pytest.raises(
        ValueError, match="technology language policy validation failed"
    ):
        languages.load_technology_language_policy(tmp_path)


@pytest.mark.parametrize(
    "source", ["#!", "#!/usr/bin/env -S", "#!/usr/bin/env NAME=value"]
)
def test_empty_or_dynamic_shebang_does_not_assign_language_authority(
    source: str,
) -> None:
    assert languages._rule_for_shebang((), source) is None


def test_compressed_source_is_inspected_without_allowing_oversized_expansion(
    tmp_path: Path,
) -> None:
    source = tmp_path / "test-only-source.py.gz"
    source.write_bytes(gzip.compress(b"print('test-only')\n"))
    assert languages._read_bounded_text(tmp_path, source.name) == "print('test-only')\n"
    source.write_bytes(gzip.compress(b"x" * 2_000_001))
    assert languages._read_bounded_text(tmp_path, source.name) is None


def test_unparseable_python_cannot_pass_language_ownership_inspection() -> None:
    policy = languages.load_technology_language_policy(Path(__file__).parents[1])
    python = next(rule for rule in policy.languages if rule.language == "python")
    violations = languages._content_capability_violations(
        "def broken(:", "src/test_only.py", "src/test_only.py", python
    )
    assert "TECHNOLOGY_SOURCE_UNPARSABLE" in {item.code for item in violations}


def test_personal_research_rejects_placeholder_identity_hash_and_receipt(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="HASH_INVALID"):
        personal._sha("g" * 64)
    with pytest.raises(ValueError, match="IDENTITY_REQUIRED"):
        personal.PersonalResearchConfirmation(" ", "TEST_ONLY", "a" * 64, "b" * 64)
    with pytest.raises(ValueError, match="CONFIRMATION_INVALID"):
        personal.parse_confirmation({"TEST_ONLY": True})
    path = tmp_path / "test-only-object.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="OBJECT_REQUIRED"):
        personal._object(path)


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (None, False),
        ({}, False),
        (
            {
                "gate": SimpleNamespace(
                    status=SimpleNamespace(value="SUCCESS"), blockers=()
                )
            },
            True,
        ),
        (
            {
                "gate": SimpleNamespace(
                    status=SimpleNamespace(value="SUCCESS"), blockers=[]
                )
            },
            False,
        ),
        (
            {
                "gate": SimpleNamespace(
                    status=SimpleNamespace(value="SUCCESS"), blockers=("VETO",)
                )
            },
            False,
        ),
        (
            {
                "gate": SimpleNamespace(
                    status=SimpleNamespace(value="FAILED"), blockers=()
                )
            },
            False,
        ),
    ],
)
def test_adapter_requires_a_typed_success_and_no_blockers(
    results: object, expected: bool
) -> None:
    assert (
        adapters._agent_gate_passed(SimpleNamespace(agent_results=results), "gate")
        is expected
    )


@pytest.mark.parametrize("grade", ["A", "C"])
def test_recovery_adapter_keeps_grade_and_hold_as_advisory_classification(
    grade: str,
) -> None:
    candidate = replace(
        _radar().ladder[0], opportunity_grade=grade, review_action="HOLD_REVIEW"
    )
    assert adapters._setup_tier(candidate).value == ("A" if grade == "A" else "B")
    assert adapters._requested_action(candidate).value == "HOLD"


@pytest.mark.parametrize(
    "changes",
    [
        {"source": " "},
        {"execution_allowed": True},
        {"live_eligibility_status": "READY"},
    ],
)
def test_dge_record_cannot_claim_execution_authority(changes: dict[str, Any]) -> None:
    record = adapters.evaluate_recovery_radar_with_dge(_radar())[0]
    with pytest.raises(ValueError, match=r"source|execution"):
        replace(record, **changes)


def test_dge_record_rejects_decision_from_another_candidate() -> None:
    record = adapters.evaluate_recovery_radar_with_dge(_radar())[0]
    with pytest.raises(ValueError, match="mismatch"):
        replace(
            record,
            candidate=replace(record.candidate, candidate_id="TEST_ONLY_DIFFERENT"),
        )
    with pytest.raises(ValueError, match="ADAPTATION_FAILED"):
        adapters.VirtualMarketDgeAdapter().evaluate(
            snapshot=object(),
            analysis=object(),
            candidate=SimpleNamespace(evidence=[]),
            portfolio=object(),
            market="SPOT",
            quantity=Decimal(1),
            risk_approved=False,
            portfolio_verified=False,
        )


def test_governed_receipt_requires_repository_bound_location_and_authority(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="AUTHORITY_BINDINGS_REQUIRED"):
        personal._activation_inputs(tmp_path, {"authority_bindings": {}})
    with pytest.raises(ValueError, match="ACTIVATION_LOCATION"):
        personal._activation(
            tmp_path,
            {"activation_record": "TEST_ONLY_UNBOUND.json"},
            "a" * 64,
            datetime.now(UTC),
        )
    inventory = load_enforcement_inventory()
    assert inventory.requirement_traceability is not None
    with pytest.raises(ValueError, match="binding mode"):
        replace(
            inventory.requirement_traceability,
            quality_binding_mode="TEST_ONLY_IGNORE_CURRENT_QUALITY",
        )


@pytest.mark.parametrize(
    "source", ["# capability: live_execution_authority", "<script>alert(1)</script>"]
)
def test_language_ownership_rejects_hidden_authority_and_embedded_logic(
    source: str,
) -> None:
    policy = languages.load_technology_language_policy(Path(__file__).parents[1])
    rule = next(rule for rule in policy.languages if rule.language == "css")
    violations = languages._content_capability_violations(
        source, "frontend/test-only.css", "frontend/test-only.css", rule
    )
    assert {item.code for item in violations} & {
        "FORBIDDEN_CAPABILITY_OWNERSHIP",
        "EMBEDDED_EXECUTABLE_SOURCE",
    }

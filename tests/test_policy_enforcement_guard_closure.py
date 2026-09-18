"""Behavioral closure for enforcement policy validation and parser guards."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ai4binance.governance.enforcement.contracts import (
    ActionTransitionRule,
    AttestationResult,
    EnforcementControlResult,
    EnforcementDecision,
    EnforcementGate,
    EnforcementOutcome,
    EnforcementProfile,
    EnforcementRequest,
    GovernedObjectEnvelope,
    VerificationAttestation,
    VerifiedApprovalSet,
)
from ai4binance.governance.enforcement.inventory import (
    EnforcementCoverageState,
    EnforcementInventory,
    EnforcementInventoryEntry,
    RequirementTraceabilityInvariants,
    RequirementTraceabilityRegistry,
    RequirementTraceStatus,
    _entry_from_payload,
    _require_sha256,
    _required_bool,
    _string_tuple,
    _traceability_entry_from_payload,
    _traceability_from_payload,
    load_enforcement_inventory,
)
from ai4binance.governance.enforcement.registry import (
    EnforcementProfileRegistry,
    _profile_from_payload,
    load_enforcement_profile_registry,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
EVALUATED_AT = "2026-09-12T00:00:00+00:00"
VALID_UNTIL = "2026-09-13T00:00:00+00:00"


def _attestation() -> VerificationAttestation:
    return VerificationAttestation(
        attestation_id="attestation-1",
        gate=EnforcementGate.IDENTITY,
        subject_hash=SHA_A,
        provider_id="local-test",
        provider_version="1.0.0",
        policy_version="1.0.0",
        evaluated_at=EVALUATED_AT,
        valid_until=VALID_UNTIL,
        evidence_refs=("artifact://evidence",),
        evidence_hash=SHA_B,
        result=AttestationResult.VERIFIED,
        reason_codes=("IDENTITY_VERIFIED",),
    )


def _approval_set() -> VerifiedApprovalSet:
    return VerifiedApprovalSet(
        approval_set_id="approval-set-1",
        subject_hash=SHA_A,
        scope_hash=SHA_B,
        change_class="C3_GOVERNED",
        required_roles=("GovernanceOwner",),
        satisfied_roles=("GovernanceOwner",),
        principal_ids=("principal-1",),
        approval_ids=("approval-1",),
        evidence_hash=SHA_C,
        verified_at=EVALUATED_AT,
        expires_at=VALID_UNTIL,
        verification_policy_hash=SHA_A,
    )


def _transition_rule(action: str = "UPDATE") -> ActionTransitionRule:
    return ActionTransitionRule(
        action=action,
        transition_required=True,
        allowed_from=("DRAFT",),
        allowed_to=("ACTIVE",),
    )


def _envelope() -> GovernedObjectEnvelope:
    return GovernedObjectEnvelope(
        object_id="policy-1",
        object_type="POLICY",
        version="1.0.0",
        lifecycle_state="DRAFT",
        owner="Enterprise Governance",
        authority_layer="L2_GOVERNANCE_COMPLIANCE",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="enterprise_governance",
        source_of_truth=True,
        canonical_ref="docs/policies/policy-1.md",
        schema_ref="schemas/governance/policy.schema.json",
        content_hash=SHA_A,
        policy_refs=("policy://root",),
        dependencies=("artifact://dependency",),
        evidence_refs=("artifact://evidence",),
    )


def _request() -> EnforcementRequest:
    return EnforcementRequest(
        request_id="request-1",
        actor="repository-agent",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        requested_transition="ACTIVE",
        evidence_refs=("artifact://evidence",),
        authorities=("repository_governance",),
    )


def _profile(object_type: str = "POLICY") -> EnforcementProfile:
    rule = _transition_rule()
    return EnforcementProfile(
        profile_id=f"profile-{object_type.lower()}",
        profile_version="1.0.0",
        object_type=object_type,
        allowed_actions=("UPDATE",),
        required_gates=(EnforcementGate.IDENTITY,),
        required_evidence=("artifact://evidence",),
        required_authorities=("repository_governance",),
        allowed_lifecycle_transitions={"DRAFT": ("ACTIVE",)},
        action_transition_rules={"UPDATE": rule},
        side_effect_class="REPOSITORY_WRITE",
        human_approval_class="C3_GOVERNED",
    )


def _decision() -> EnforcementDecision:
    return EnforcementDecision(
        decision_id="decision-1",
        outcome=EnforcementOutcome.DENY,
        evaluated_controls=(),
        blockers=("LIVE_ORDER_BLOCKED",),
        reason_codes=("POLICY_DENIED",),
        policy_versions=("1.0.0",),
        object_hash=SHA_A,
        evidence_hash=SHA_B,
        authority_snapshot_hash=SHA_C,
        enforcement_profile_version="1.0.0",
        enforcement_profile_hash=SHA_A,
        approval_set_hash=SHA_B,
        blocker_snapshot_hash=SHA_C,
        audit_receipt_hash=SHA_A,
        consequence="NO_CHANGE",
        replay_fingerprint=SHA_B,
    )


def test_enforcement_contracts_reject_invalid_identity_hash_and_time() -> None:
    with pytest.raises(ValueError, match="attestation_id is required"):
        replace(_attestation(), attestation_id="")
    with pytest.raises(ValueError, match="evidence_refs cannot contain blanks"):
        replace(_attestation(), evidence_refs=("",))
    with pytest.raises(ValueError, match="reason_codes must be unique"):
        replace(_attestation(), reason_codes=("A", "A"))
    with pytest.raises(ValueError, match="subject_hash must be a SHA-256"):
        replace(_attestation(), subject_hash="short")
    with pytest.raises(ValueError, match="evaluated_at must be timezone-aware"):
        replace(_attestation(), evaluated_at="2026-09-12T00:00:00")
    with pytest.raises(ValueError, match="valid_until cannot be earlier"):
        replace(
            _attestation(),
            evaluated_at=VALID_UNTIL,
            valid_until=EVALUATED_AT,
        )


def test_approval_and_transition_contracts_reject_incomplete_authority() -> None:
    with pytest.raises(ValueError, match="missing required roles"):
        replace(_approval_set(), satisfied_roles=())
    with pytest.raises(ValueError, match="expires_at cannot be earlier"):
        replace(
            _approval_set(),
            verified_at=VALID_UNTIL,
            expires_at=EVALUATED_AT,
        )
    with pytest.raises(ValueError, match="transition-required action rules"):
        replace(_transition_rule(), allowed_to=())


def test_envelope_request_and_control_contracts_reject_malformed_evidence() -> None:
    with pytest.raises(ValueError, match="schema_ref is required"):
        replace(_envelope(), schema_ref="")
    with pytest.raises(ValueError, match="content_hash must be a SHA-256"):
        replace(_envelope(), content_hash="short")

    request = replace(_request(), correlation_id="correlation-1")
    assert request.correlation_id == "correlation-1"
    with pytest.raises(ValueError, match="context_hash must be a SHA-256"):
        replace(_request(), context_hash="short")
    with pytest.raises(ValueError, match="policy_facts must be non-empty strings"):
        replace(_request(), policy_facts={"": "value"})
    with pytest.raises(ValueError, match="keys must match attestation gates"):
        replace(
            _request(),
            gate_attestations={EnforcementGate.SCHEMA: _attestation()},
        )

    valid_control = EnforcementControlResult(
        gate=EnforcementGate.IDENTITY,
        outcome=EnforcementOutcome.DENY,
        reason_codes=("IDENTITY_DENIED",),
        details={"provider": "local-test"},
    )
    assert valid_control.details["provider"] == "local-test"
    with pytest.raises(ValueError, match="details must use non-empty strings"):
        replace(valid_control, details={"provider": ""})


def test_profile_and_decision_contracts_reject_authority_expansion() -> None:
    with pytest.raises(ValueError, match=r"key must match rule.action"):
        replace(
            _profile(),
            action_transition_rules={"PROMOTE": _transition_rule("UPDATE")},
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(_decision(), execution_allowed=True)
    with pytest.raises(ValueError, match="must keep live execution blocked"):
        replace(_decision(), live_eligibility_status="READY")


def _profile_payload() -> dict[str, object]:
    return {
        "profile_id": "profile-policy",
        "profile_version": "1.0.0",
        "object_type": "POLICY",
        "allowed_actions": ["UPDATE"],
        "required_gates": ["IDENTITY"],
        "required_evidence": ["artifact://evidence"],
        "required_authorities": ["repository_governance"],
        "allowed_lifecycle_transitions": {"DRAFT": ["ACTIVE"]},
        "action_transition_rules": {
            "UPDATE": {
                "transition_required": True,
                "allowed_from": ["DRAFT"],
                "allowed_to": ["ACTIVE"],
            }
        },
        "side_effect_class": "REPOSITORY_WRITE",
        "human_approval_class": "C3_GOVERNED",
    }


def test_enforcement_profile_registry_rejects_identity_and_coverage_drift() -> None:
    profile = _profile()
    with pytest.raises(ValueError, match="version is required"):
        EnforcementProfileRegistry(version="", profiles=(profile,))
    with pytest.raises(ValueError, match="requires profiles"):
        EnforcementProfileRegistry(version="1.0.0", profiles=())
    with pytest.raises(ValueError, match="profile IDs must be unique"):
        EnforcementProfileRegistry(version="1.0.0", profiles=(profile, profile))
    with pytest.raises(ValueError, match="unique per object_type"):
        EnforcementProfileRegistry(
            version="1.0.0",
            profiles=(profile, replace(profile, profile_id="profile-policy-2")),
        )

    registry = EnforcementProfileRegistry(version="1.0.0", profiles=(profile,))
    assert registry.profile_for_object_type("MISSING") is None
    with pytest.raises(ValueError, match="missing=MISSING"):
        registry.assert_full_coverage(("POLICY", "MISSING"))
    with pytest.raises(ValueError, match="extra=POLICY"):
        registry.assert_full_coverage(("MISSING",))


def test_enforcement_profile_payload_parser_rejects_invalid_structures() -> None:
    valid = _profile_payload()
    assert _profile_from_payload(valid).object_type == "POLICY"
    invalid_cases: tuple[tuple[object, str], ...] = (
        ([], "profile must be a mapping"),
        ({**valid, "required_gates": "IDENTITY"}, "required_gates must be a list"),
        (
            {**valid, "allowed_lifecycle_transitions": []},
            "allowed_lifecycle_transitions must be a mapping",
        ),
        (
            {**valid, "action_transition_rules": []},
            "action_transition_rules must be a mapping",
        ),
        (
            {**valid, "allowed_lifecycle_transitions": {"": ["ACTIVE"]}},
            "transition source must be non-empty",
        ),
        (
            {**valid, "allowed_lifecycle_transitions": {"DRAFT": "ACTIVE"}},
            "transition targets must be a list",
        ),
        (
            {**valid, "action_transition_rules": {"": {}}},
            "rule keys must be non-empty",
        ),
        (
            {**valid, "action_transition_rules": {"UPDATE": []}},
            "rule must be a mapping",
        ),
        (
            {
                **valid,
                "action_transition_rules": {
                    "UPDATE": {"allowed_from": "DRAFT", "allowed_to": ["ACTIVE"]}
                },
            },
            "allowed_from and allowed_to must be lists",
        ),
    )
    for payload, error in invalid_cases:
        with pytest.raises(ValueError, match=error):
            _profile_from_payload(payload)


def test_enforcement_profile_registry_loader_rejects_invalid_root(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "profiles.yaml"
    invalid_path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_enforcement_profile_registry(invalid_path)
    invalid_path.write_text("version: 1.0.0\nprofiles: invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="profiles must be a list"):
        load_enforcement_profile_registry(invalid_path)


def _traceability() -> RequirementTraceabilityRegistry:
    inventory = load_enforcement_inventory()
    assert inventory.requirement_traceability is not None
    return inventory.requirement_traceability


def _inventory_entry() -> EnforcementInventoryEntry:
    return load_enforcement_inventory().entries[0]


def test_requirement_traceability_invariants_reject_authority_expansion() -> None:
    invariants = RequirementTraceabilityInvariants(
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(invariants, execution_allowed=True)
    with pytest.raises(ValueError, match="must remain research-only"):
        replace(invariants, promotion_status="PROMOTED")
    with pytest.raises(ValueError, match="must keep live orders blocked"):
        replace(invariants, live_eligibility_status="READY")


def test_requirement_traceability_entry_rejects_invalid_identity_and_lists() -> None:
    entry = _traceability().entries[0]
    invalid_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"canonical_owner": ""}, "canonical_owner is required"),
        ({"requirement_id": "RQ-1"}, "RQ-NNN format"),
        ({"source_documents": ()}, "source_documents cannot be empty"),
        ({"implementation_refs": ("",)}, "cannot contain blanks"),
        ({"test_refs": ("a", "a")}, "must be unique"),
    )
    for changes, error in invalid_cases:
        with pytest.raises(ValueError, match=error):
            replace(entry, **changes)

    not_applicable = replace(
        entry,
        trace_status=RequirementTraceStatus.NOT_APPLICABLE,
        convergence_state="NOT_APPLICABLE",
    )
    assert not_applicable.is_converged is True
    assert replace(not_applicable, convergence_state="BLOCKED").is_converged is False
    blocked = replace(
        entry,
        trace_status=RequirementTraceStatus.BLOCKED,
        convergence_state="BLOCKED_BY_EVIDENCE",
    )
    assert blocked.blocker_codes == (
        f"{entry.requirement_id}:TRACE_STATUS_BLOCKED",
        f"{entry.requirement_id}:CONVERGENCE_BLOCKED_BY_EVIDENCE",
    )


def test_requirement_traceability_registry_rejects_invalid_manifest() -> None:
    traceability = _traceability()
    entry = traceability.entries[0]
    invalid_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"canonical_owner": ""}, "canonical_owner is required"),
        ({"source_corpus_sha256": "short"}, "lowercase SHA-256"),
        ({"allowed_trace_statuses": ()}, "cannot be empty"),
        (
            {
                "allowed_trace_statuses": (
                    RequirementTraceStatus.AUDIT_VERIFIED,
                    RequirementTraceStatus.AUDIT_VERIFIED,
                )
            },
            "must be unique",
        ),
        ({"entries": ()}, "entries cannot be empty"),
        ({"entries": (entry, entry)}, "IDs must be unique"),
        (
            {
                "allowed_trace_statuses": (RequirementTraceStatus.TESTED,),
                "entries": (entry,),
            },
            "contains disallowed statuses",
        ),
    )
    for changes, error in invalid_cases:
        with pytest.raises(ValueError, match=error):
            replace(traceability, **changes)

    with pytest.raises(ValueError, match="unknown enforcement entrypoints"):
        traceability.assert_enforcement_entrypoints_registered(())


def test_enforcement_inventory_entry_and_container_reject_invalid_state() -> None:
    entry = _inventory_entry()
    for changes, error in (
        ({"entrypoint_id": ""}, "entrypoint_id is required"),
        ({"tests": ()}, "tests are required"),
        ({"tests": ("",)}, "cannot contain blanks"),
        ({"tests": ("a", "a")}, "tests must be unique"),
    ):
        with pytest.raises(ValueError, match=error):
            replace(entry, **changes)

    inventory = EnforcementInventory(version="1.0.0", entries=(entry,))
    with pytest.raises(ValueError, match="version is required"):
        replace(inventory, version="")
    with pytest.raises(ValueError, match="requires entries"):
        replace(inventory, entries=())
    with pytest.raises(ValueError, match="entrypoint IDs must be unique"):
        replace(inventory, entries=(entry, entry))
    with pytest.raises(ValueError, match="cannot contain blanks"):
        replace(inventory, non_consequential_examples=("",))
    with pytest.raises(ValueError, match="must be unique"):
        replace(inventory, non_consequential_examples=("a", "a"))


def test_enforcement_inventory_queries_and_exit_guards_fail_closed() -> None:
    entry = _inventory_entry()
    inventory = EnforcementInventory(version="1.0.0", entries=(entry,))
    assert inventory.entry_for("MISSING", "UPDATE") is None
    assert inventory.entry_for_entrypoint("missing") is None

    duplicate_match = replace(entry, entrypoint_id="alternate-entrypoint")
    duplicate_inventory = EnforcementInventory(
        version="1.0.0", entries=(entry, duplicate_match)
    )
    with pytest.raises(ValueError, match="multiple entrypoints"):
        duplicate_inventory.entry_for(entry.object_type, entry.action)

    unresolved = replace(
        entry,
        coverage_state=EnforcementCoverageState.ADAPTER_REQUIRED,
        consequential=True,
    )
    with pytest.raises(ValueError, match="unresolved consequential"):
        EnforcementInventory(
            version="1.0.0", entries=(unresolved,)
        ).assert_exit_invariant()

    bypassable = replace(
        entry,
        coverage_state=EnforcementCoverageState.ROUTED,
        consequential=True,
        bypass_possible=True,
    )
    with pytest.raises(ValueError, match="still permits bypass"):
        EnforcementInventory(
            version="1.0.0", entries=(bypassable,)
        ).assert_exit_invariant()

    with pytest.raises(ValueError, match="missing required scope families"):
        inventory.assert_required_scope_families_covered()
    with pytest.raises(ValueError, match="cannot be tracked as consequential"):
        replace(
            inventory,
            non_consequential_examples=(entry.entrypoint_id,),
        ).assert_non_consequential_examples_excluded()
    with pytest.raises(ValueError, match="unmanaged object types"):
        inventory.assert_profile_registry_alignment(
            EnforcementProfileRegistry(version="1.0.0", profiles=(_profile("OTHER"),))
        )


def test_enforcement_inventory_loader_rejects_malformed_payloads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inventory.yaml"
    with pytest.raises(ValueError, match="could not be loaded"):
        load_enforcement_inventory(path)
    path.write_text("[\n", encoding="utf-8")
    with pytest.raises(ValueError, match="could not be loaded"):
        load_enforcement_inventory(path)
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_enforcement_inventory(path)
    path.write_text("version: 1.0.0\nentries: invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="entries must be a list"):
        load_enforcement_inventory(path)
    path.write_text(
        "version: 1.0.0\nentries: []\nnon_consequential_examples: invalid\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="examples must be a list"):
        load_enforcement_inventory(path)


def test_enforcement_inventory_parsers_reject_invalid_machine_data() -> None:
    with pytest.raises(ValueError, match="entry must be a mapping"):
        _entry_from_payload([])
    with pytest.raises(ValueError, match="tests must be a list"):
        _entry_from_payload({"tests": "invalid"})
    assert _traceability_from_payload(None) is None
    with pytest.raises(ValueError, match="must be a mapping"):
        _traceability_from_payload([])
    with pytest.raises(ValueError, match="invariants must be a mapping"):
        _traceability_from_payload({"invariants": []})
    with pytest.raises(ValueError, match="allowed_trace_statuses must be a list"):
        _traceability_from_payload(
            {"invariants": {}, "allowed_trace_statuses": "invalid"}
        )
    with pytest.raises(ValueError, match="entries must be a list"):
        _traceability_from_payload(
            {"invariants": {}, "allowed_trace_statuses": [], "entries": "invalid"}
        )
    with pytest.raises(ValueError, match="entry must be a mapping"):
        _traceability_entry_from_payload([])
    with pytest.raises(ValueError, match="must be a list"):
        _string_tuple({}, "items")
    with pytest.raises(ValueError, match="cannot be empty"):
        _string_tuple({"items": []}, "items")
    with pytest.raises(ValueError, match="cannot contain blanks"):
        _string_tuple({"items": [""]}, "items")
    with pytest.raises(ValueError, match="must be unique"):
        _string_tuple({"items": ["a", "a"]}, "items")
    with pytest.raises(ValueError, match="must be a boolean"):
        _required_bool({"enabled": "true"}, "enabled")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _require_sha256("digest", "short")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _require_sha256("digest", "G" * 64)

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai4binance.governance.blockers import (
    BLOCKER_REGISTRY_PATH,
    Blocker,
    BlockerAuthority,
    BlockerClass,
    BlockerDomain,
    BlockerEffect,
    BlockerLifecycleState,
    BlockerScope,
    BlockerSeverity,
    ClearanceRule,
    WaiverRequirements,
    blocker_from_payload,
    blocker_registry_from_payload,
    load_blocker_registry,
    validate_lifecycle_transition,
)


def occurrence_payload(blocker_code: str, **overrides: object) -> dict[str, object]:
    registry = load_blocker_registry(Path(BLOCKER_REGISTRY_PATH))
    definition = registry.require_known_code(blocker_code)
    payload: dict[str, object] = {
        "occurrence_id": f"blk-occ:{definition.blocker_code}",
        "definition_id": definition.definition_id,
        "blocker_code": definition.blocker_code,
        "domain": definition.domain.value,
        "blocker_class": definition.blocker_class.value,
        "severity": definition.severity.value,
        "scope": definition.scope.value,
        "scope_ref": "cycle:btc:2026-08-21",
        "authority": definition.authority.value,
        "effects": [effect.value for effect in definition.effects],
        "lifecycle_state": "ACTIVE",
        "evidence_refs": ["evidence:test"],
        "detected_at": "2026-08-21T00:00:00Z",
        "policy_ref": definition.policy_ref,
        "policy_version": definition.policy_version,
        "control_ref": definition.control_ref,
        "control_version": definition.control_version,
        "producer": definition.producer,
        "source_component": definition.source_component,
        "remediation": definition.remediation,
        "correlation_id": "corr:test",
        "cycle_id": "cycle:test",
        "snapshot_id": "snapshot:test",
        "fingerprint": "blkfp:test",
        "occurrence_count": 1,
        "first_seen_at": "2026-08-21T00:00:00Z",
        "last_seen_at": "2026-08-21T00:00:00Z",
        "root_cause_codes": [],
        "resolution_evidence": [],
        "waiver": None,
    }
    payload.update(overrides)
    return payload


def registry_payload() -> dict[str, Any]:
    payload = yaml.safe_load(Path(BLOCKER_REGISTRY_PATH).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_blocker_code_is_cause_not_runtime_state_or_effect() -> None:
    with pytest.raises(ValueError, match="cause code"):
        Blocker(
            occurrence_id="blk-occ:test:forbidden",
            definition_id="AI4B-BLK-EXEC-002",
            blocker_code="LIVE_ORDER_BLOCKED",
            domain=BlockerDomain.EXECUTION,
            blocker_class=BlockerClass.HARD_BLOCKER,
            severity=BlockerSeverity.CRITICAL,
            scope=BlockerScope.EXECUTION_MODE,
            authority=BlockerAuthority.EXECUTION_GATE,
            effects=(BlockerEffect.LIVE_ORDER_BLOCKED,),
            lifecycle_state=BlockerLifecycleState.ACTIVE,
            evidence_refs=("test:evidence",),
            detected_at="2026-08-21T00:00:00Z",
            policy_ref="policy:execution:live",
            policy_version="2.0.0",
            control_ref="control:execution:live-authorization",
            control_version="2.0.0",
            producer="ExecutionGate",
            source_component="execution.gate",
            remediation="Keep live execution blocked.",
        )


def test_blocking_occurrence_requires_effects_and_cannot_be_advisory_critical() -> None:
    with pytest.raises(ValueError, match="declare effects"):
        Blocker(
            occurrence_id="blk-occ:test:no-effects",
            definition_id="AI4B-BLK-RISK-001",
            blocker_code="RISK.VETO",
            domain=BlockerDomain.RISK,
            blocker_class=BlockerClass.HARD_BLOCKER,
            severity=BlockerSeverity.CRITICAL,
            scope=BlockerScope.DECISION_CYCLE,
            authority=BlockerAuthority.RISK_ENGINE,
            effects=(),
            lifecycle_state=BlockerLifecycleState.ACTIVE,
            evidence_refs=("risk:evidence",),
            detected_at="2026-08-21T00:00:00Z",
            policy_ref="policy:risk:veto",
            policy_version="2.0.0",
            control_ref="control:risk:veto",
            control_version="2.0.0",
            producer="RiskEngine",
            source_component="risk.manager",
            remediation="Resolve risk veto.",
        )

    with pytest.raises(ValueError, match="critical severity"):
        Blocker(
            occurrence_id="blk-occ:test:critical-advisory",
            definition_id="AI4B-BLK-SCHEMA-001",
            blocker_code="SCHEMA.PAYLOAD_VALIDATION_FAILED",
            domain=BlockerDomain.SCHEMA,
            blocker_class=BlockerClass.ADVISORY_FINDING,
            severity=BlockerSeverity.CRITICAL,
            scope=BlockerScope.OBJECT,
            authority=BlockerAuthority.GOVERNANCE_ENGINE,
            effects=(BlockerEffect.QUALITY_GATE_BLOCKED,),
            lifecycle_state=BlockerLifecycleState.ACTIVE,
            evidence_refs=("schema:evidence",),
            detected_at="2026-08-21T00:00:00Z",
            policy_ref="policy:schema:payload-validation",
            policy_version="2.0.0",
            control_ref="control:schema:payload-validation",
            control_version="2.0.0",
            producer="GovernanceEngine",
            source_component="schema.validator",
            remediation="Correct payload.",
        )


def test_resolution_lifecycle_and_waiver_rules_fail_closed() -> None:
    with pytest.raises(ValueError, match="resolution evidence"):
        blocker_from_payload(
            occurrence_payload(
                "DATA.STALE_MARKET_DATA",
                lifecycle_state="RESOLVED",
                resolution_evidence=[],
            )
        )

    with pytest.raises(ValueError, match="waived blockers"):
        blocker_from_payload(
            occurrence_payload(
                "GOV.BYPASS_ATTEMPT",
                lifecycle_state="WAIVED",
                waiver={"allowed": False},
            )
        )

    with pytest.raises(ValueError, match="invalid blocker lifecycle transition"):
        validate_lifecycle_transition(
            BlockerLifecycleState.ACTIVE,
            BlockerLifecycleState.RESOLVED,
            resolution_evidence=("resolution:evidence",),
        )

    validate_lifecycle_transition(
        BlockerLifecycleState.PENDING_VERIFICATION,
        BlockerLifecycleState.RESOLVED,
        resolution_evidence=("resolution:evidence",),
    )

    with pytest.raises(ValueError, match="waiver transition"):
        validate_lifecycle_transition(
            BlockerLifecycleState.ACTIVE,
            BlockerLifecycleState.WAIVED,
        )

    with pytest.raises(ValueError, match="resolved transition"):
        validate_lifecycle_transition(
            BlockerLifecycleState.PENDING_VERIFICATION,
            BlockerLifecycleState.RESOLVED,
        )


def test_governance_authority_conflict_affecting_execution_blocks_live_orders() -> None:
    with pytest.raises(ValueError, match="live orders"):
        blocker_from_payload(
            occurrence_payload(
                "GOV.AUTHORITY_CONFLICT",
                effects=["QUALITY_GATE_BLOCKED"],
            )
        )


def test_registry_loads_aliases_and_rejects_unknown_codes() -> None:
    registry = load_blocker_registry(Path(BLOCKER_REGISTRY_PATH))

    assert registry.entries == registry.definitions
    assert registry.require_known_code("GOVERNANCE_BYPASS").blocker_code == (
        "GOV.BYPASS_ATTEMPT"
    )
    assert registry.require_known_code("LIVE_ORDER_BLOCKED").blocker_code == (
        "EXEC.LIVE_EXECUTION_UNAUTHORIZED"
    )
    with pytest.raises(ValueError, match="unknown blocker code"):
        registry.require_known_code("CUSTOM_BLOCKER")
    with pytest.raises(ValueError, match="legacy blocker alias"):
        registry.require_canonical_code("LIVE_ORDER_BLOCKED")


def test_authoritative_blocker_payload_must_be_canonical() -> None:
    registry = load_blocker_registry(Path(BLOCKER_REGISTRY_PATH))
    payload = occurrence_payload("DATA.STALE_MARKET_DATA", fingerprint="")
    payload.pop("fingerprint")
    payload.pop("first_seen_at")
    payload.pop("last_seen_at")

    blocker = blocker_from_payload(payload, registry=registry)

    assert blocker.blocker_code == "DATA.STALE_MARKET_DATA"
    assert blocker.is_blocking is True
    assert blocker.hard_gate is True
    assert blocker.hard_gate_active is True
    assert blocker.first_seen_at == payload["detected_at"]
    assert blocker.last_seen_at == payload["detected_at"]
    assert blocker.fingerprint.startswith("blkfp:")
    assert "hard_gate" not in blocker.to_payload()
    registry.validate_blocker(blocker)

    with pytest.raises(ValueError, match="legacy blocker alias"):
        blocker_from_payload(
            {**payload, "blocker_code": "DATA_STALE"},
            registry=registry,
        )
    migrated = blocker_from_payload(
        {**payload, "blocker_code": "DATA_STALE"},
        registry=registry,
        allow_migration_alias=True,
    )
    assert migrated.blocker_code == "DATA.STALE_MARKET_DATA"


def test_payload_must_match_registry_metadata() -> None:
    registry = load_blocker_registry(Path(BLOCKER_REGISTRY_PATH))
    payload = occurrence_payload("DATA.SNAPSHOT_INCOMPLETE", severity="MEDIUM")

    with pytest.raises(ValueError, match="canonical registry"):
        blocker_from_payload(payload, registry=registry)


def test_blocker_schema_requires_occurrence_lineage_and_no_hard_gate() -> None:
    schema = json.loads(
        Path("schemas/governance/blocker.schema.json").read_text(encoding="utf-8")
    )

    assert {
        "occurrence_id",
        "definition_id",
        "policy_ref",
        "policy_version",
        "control_ref",
        "control_version",
        "producer",
        "source_component",
        "fingerprint",
        "occurrence_count",
        "scope_ref",
        "remediation",
        "resolution_evidence",
    }.issubset(set(schema["required"]))
    assert "hard_gate" not in schema["properties"]
    assert "SECURITY_CRITICAL" not in schema["$defs"]["severity"]["enum"]


def test_registry_rejects_duplicate_semantic_codes() -> None:
    payload = yaml.safe_load(Path(BLOCKER_REGISTRY_PATH).read_text(encoding="utf-8"))
    payload["blocker_definitions"][1]["semantic_key"] = payload["blocker_definitions"][
        0
    ]["semantic_key"]

    with pytest.raises(ValueError, match="semantic keys"):
        blocker_registry_from_payload(payload)


def test_structured_waiver_disallows_not_waivable_codes() -> None:
    with pytest.raises(ValueError, match="not waivable"):
        blocker_from_payload(
            occurrence_payload(
                "SEC.SECRET_EXPOSURE",
                lifecycle_state="WAIVED",
                waiver={
                    "allowed": True,
                    "required_authorities": ["HUMAN_GOVERNANCE"],
                    "requires_written_approval": True,
                    "requires_justification": True,
                    "requires_evidence": True,
                    "requires_expiry": True,
                    "max_duration_hours": 1,
                    "execution_scope_allowed": False,
                },
            )
        )

    waiver = WaiverRequirements(
        allowed=True,
        required_authorities=(BlockerAuthority.HUMAN_GOVERNANCE,),
        requires_written_approval=True,
        requires_justification=True,
        requires_evidence=True,
        requires_expiry=True,
        max_duration_hours=1,
        execution_scope_allowed=False,
    )
    validate_lifecycle_transition(
        BlockerLifecycleState.ACTIVE,
        BlockerLifecycleState.WAIVED,
        waiver=waiver,
    )

    assert waiver.to_payload()["required_authorities"] == ("HUMAN_GOVERNANCE",)


@pytest.mark.parametrize(
    ("waiver_factory", "message"),
    [
        (
            lambda: WaiverRequirements(
                allowed=False,
                required_authorities=(BlockerAuthority.HUMAN_GOVERNANCE,),
            ),
            "disallowed waivers cannot require authorities",
        ),
        (
            lambda: WaiverRequirements(
                allowed=False,
                requires_written_approval=True,
            ),
            "disallowed waivers cannot require waiver controls",
        ),
        (
            lambda: WaiverRequirements(
                allowed=False,
                max_duration_hours=1,
            ),
            "disallowed waivers cannot define a duration",
        ),
        (
            lambda: WaiverRequirements(
                allowed=True,
                max_duration_hours=0,
            ),
            "waiver max_duration_hours must be positive",
        ),
    ],
)
def test_waiver_validation_rejects_inconsistent_controls(
    waiver_factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        waiver_factory()  # type: ignore[operator]


def test_clearance_rule_requires_detect_and_clear_authorities() -> None:
    with pytest.raises(ValueError, match="detect authority"):
        ClearanceRule(
            detect_authorities=(),
            clear_authorities=(BlockerAuthority.GOVERNANCE_ENGINE,),
        )

    with pytest.raises(ValueError, match="clear authority"):
        ClearanceRule(
            detect_authorities=(BlockerAuthority.GOVERNANCE_ENGINE,),
            clear_authorities=(),
        )

    clearance = ClearanceRule(
        detect_authorities=(BlockerAuthority.GOVERNANCE_ENGINE,),
        clear_authorities=(BlockerAuthority.HUMAN_GOVERNANCE,),
        waive_authorities=(BlockerAuthority.HUMAN_GOVERNANCE,),
        downgrade_authorities=(BlockerAuthority.GOVERNANCE_ENGINE,),
    )

    assert clearance.to_payload() == {
        "detect_authorities": ("GOVERNANCE_ENGINE",),
        "clear_authorities": ("HUMAN_GOVERNANCE",),
        "waive_authorities": ("HUMAN_GOVERNANCE",),
        "downgrade_authorities": ("GOVERNANCE_ENGINE",),
    }


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload.__setitem__("blocker_definitions", {}),
            "blocker registry requires blocker_definitions",
        ),
        (
            lambda payload: payload.__setitem__(
                "blocker_definitions", [payload["blocker_definitions"][0], "bad"]
            ),
            "blocker registry definitions must be mappings",
        ),
        (
            lambda payload: payload.__setitem__("aliases", []),
            "blocker aliases must be a mapping",
        ),
        (
            lambda payload: payload.__setitem__("aliases", {"LEGACY": "DATA.UNKNOWN"}),
            "blocker alias target is unknown",
        ),
        (
            lambda payload: payload.__setitem__(
                "aliases", {"LEGACY.CODE": "DATA.STALE_MARKET_DATA"}
            ),
            "legacy non-canonical",
        ),
        (
            lambda payload: payload.__setitem__(
                "aliases", {"bad-alias": "DATA.STALE_MARKET_DATA"}
            ),
            "legacy upper-snake code",
        ),
        (
            lambda payload: payload.__setitem__(
                "aliases", {1: "DATA.STALE_MARKET_DATA"}
            ),
            "alias keys must be strings",
        ),
        (
            lambda payload: payload.__setitem__("aliases", {"LEGACY": 1}),
            "alias targets must be strings",
        ),
    ],
)
def test_registry_payload_rejects_malformed_containers(
    mutator: object, message: str
) -> None:
    payload = registry_payload()
    mutator(payload)  # type: ignore[operator]

    with pytest.raises(ValueError, match=message):
        blocker_registry_from_payload(payload)


def test_registry_loader_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    registry_path = tmp_path / "blockers.yaml"
    registry_path.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="blocker registry must be a mapping"):
        load_blocker_registry(registry_path)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda definition: definition.__setitem__("precedence", -1),
            "precedence must be non-negative",
        ),
        (
            lambda definition: definition.__setitem__("effects", []),
            "blocking definitions must declare effects",
        ),
        (
            lambda definition: definition.__setitem__(
                "blocker_class", "ADVISORY_FINDING"
            ),
            "critical severity cannot be advisory-only",
        ),
        (
            lambda definition: definition.pop("waiver"),
            "blocker definition requires waiver",
        ),
        (
            lambda definition: definition.__setitem__("waiver", []),
            "blocker definition requires waiver",
        ),
        (
            lambda definition: definition.pop("clearance"),
            "blocker definition requires clearance",
        ),
        (
            lambda definition: definition.__setitem__("clearance", []),
            "blocker definition requires clearance",
        ),
        (
            lambda definition: definition.__setitem__("definition_id", " "),
            "definition_id is required",
        ),
        (
            lambda definition: definition.__setitem__("precedence", "1"),
            "precedence must be an integer",
        ),
        (
            lambda definition: definition["waiver"].__setitem__("allowed", "yes"),
            "allowed must be boolean",
        ),
        (
            lambda definition: definition["waiver"].__setitem__(
                "required_authorities", "HUMAN_GOVERNANCE"
            ),
            "required_authorities must be a list",
        ),
        (
            lambda definition: definition["waiver"].__setitem__(
                "required_authorities", [1]
            ),
            "required_authorities must contain only strings",
        ),
        (
            lambda definition: definition["waiver"].__setitem__(
                "max_duration_hours", "1"
            ),
            "max_duration_hours must be an integer or null",
        ),
        (
            lambda definition: definition["clearance"].__setitem__(
                "detect_authorities", "GOVERNANCE_ENGINE"
            ),
            "detect_authorities must be a list",
        ),
        (
            lambda definition: definition["clearance"].__setitem__(
                "detect_authorities", [1]
            ),
            "detect_authorities must contain only strings",
        ),
    ],
)
def test_definition_payload_validation_edges(
    mutator: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    payload = registry_payload()
    definition = payload["blocker_definitions"][0]
    mutator(definition)

    with pytest.raises(ValueError, match=message):
        blocker_registry_from_payload(payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"scope_ref": " "}, "scope_ref must be a nonblank string or null"),
        (
            {"correlation_id": " "},
            "correlation_id must be a nonblank string or null",
        ),
        ({"occurrence_count": 0}, "occurrence_count must be positive"),
        ({"root_cause_codes": ["UNKNOWN.CAUSE"]}, "blocker_code prefix is unknown"),
        ({"root_cause_codes": ["DATA"]}, "DOMAIN.CAUSE format"),
        ({"waiver": []}, "waiver must be a mapping"),
        ({"effects": "LIVE_ORDER_BLOCKED"}, "effects must be a list"),
        ({"effects": [1]}, "effects must contain only strings"),
        ({"resolution_evidence": "evidence"}, "resolution_evidence must be a list"),
        (
            {"resolution_evidence": [1]},
            "resolution_evidence must contain only strings",
        ),
        ({"occurrence_count": "1"}, "occurrence_count must be an integer or null"),
    ],
)
def test_occurrence_payload_validation_edges(
    overrides: dict[str, object], message: str
) -> None:
    payload = occurrence_payload("DATA.STALE_MARKET_DATA", **overrides)

    with pytest.raises(ValueError, match=message):
        blocker_from_payload(payload)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"definition_id": "AI4B-BLK-DATA-OTHER"}, "definition_id"),
        ({"blocker_class": "CONDITIONAL_BLOCKER"}, "blocker_class"),
        ({"severity": "HIGH"}, "severity"),
        ({"scope": "COMPONENT"}, "scope"),
        ({"authority": "RISK_ENGINE"}, "authority"),
        ({"policy_ref": "policy:other"}, "policy_ref"),
        ({"policy_version": "0.0.0"}, "policy_version"),
        ({"control_ref": "control:other"}, "control_ref"),
        ({"control_version": "0.0.0"}, "control_version"),
        ({"producer": "OtherProducer"}, "producer"),
        ({"source_component": "other.component"}, "source_component"),
        (
            {"effects": ["QUALITY_GATE_BLOCKED", "RUNNING_WITH_BLOCKERS"]},
            "effects",
        ),
    ],
)
def test_registry_validation_reports_metadata_mismatch(
    overrides: dict[str, object], field: str
) -> None:
    registry = load_blocker_registry(Path(BLOCKER_REGISTRY_PATH))
    blocker_code = (
        "GOV.AUTHORITY_CONFLICT"
        if field in {"blocker_class", "severity"}
        else "DATA.STALE_MARKET_DATA"
    )
    payload = occurrence_payload(blocker_code, **overrides)

    with pytest.raises(ValueError, match=field):
        blocker_from_payload(payload, registry=registry)

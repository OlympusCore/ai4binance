"""Deterministic branch-coverage closure for the fail-closed model registry."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from ai4binance.governance import model_registry as model_registry_module
from ai4binance.governance.model_registry import (
    ModelArtifact,
    ModelDefinition,
    ModelGatewayDecision,
    ModelInferenceEnvelope,
    ModelRegistryEntry,
    ModelRegistryReport,
    ModelRouteDecision,
    ModelVersion,
    admit_advisory_model_invocation,
    build_advisory_inference_envelope,
    load_model_registry,
    validate_model_registry,
)

HASH = "a" * 64


def _definition() -> ModelDefinition:
    return ModelDefinition(
        model_id="coverage-model",
        name="Coverage Model",
        model_family="LLM",
        provider="local",
        owner="Model Governance",
        intended_use=("ADVISORY_RESEARCH_SYNTHESIS",),
        prohibited_use=("FINAL_DECISION",),
        authority_ceiling="ADVISORY_ONLY",
        decision_authority=False,
        risk_override=False,
        strategy_promotion=False,
        execution_authority=False,
        live_order_authority=False,
    )


def _version() -> ModelVersion:
    return ModelVersion(
        model_id="coverage-model",
        model_version="coverage:v1",
        lifecycle_status="RESEARCH_ONLY",
        input_contract_version="1.0.0",
        output_contract_version="1.0.0",
        source_path="src/models/model.py",
    )


def _artifact() -> ModelArtifact:
    return ModelArtifact(
        artifact_type="SOURCE_CONTRACT",
        artifact_uri="model.bin",
        artifact_sha256=HASH,
        license_status="VERIFIED",
        rollback_binding="coverage:v1",
    )


def _entry() -> ModelRegistryEntry:
    return ModelRegistryEntry(_definition(), _version(), _artifact())


def _route() -> ModelRouteDecision:
    return ModelRouteDecision(
        canonical_model_id="coverage-model",
        provider="local",
        task_type="ADVISORY_RESEARCH_SYNTHESIS",
        model_family="LLM",
        allowed=True,
        blockers=(),
        route_sha256=HASH,
    )


def _gateway() -> ModelGatewayDecision:
    return ModelGatewayDecision(
        model_id="coverage-model",
        provider="local",
        allowed=True,
        blockers=(),
        route_decision=_route(),
    )


def _envelope() -> ModelInferenceEnvelope:
    return ModelInferenceEnvelope(
        canonical_model_id="coverage-model",
        model_version="coverage:v1",
        task_type="ADVISORY_RESEARCH_SYNTHESIS",
        input_snapshot_sha256=HASH,
        provenance_sha256=HASH,
        artifact_sha256=HASH,
    )


def _registry_payload(
    *,
    artifact_type: str = "SOURCE_CONTRACT",
    artifact_uri: str = "model.bin",
    artifact_sha256: str = HASH,
    intended_use: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "entries": [
            {
                "definition": {
                    "model_id": "coverage-model",
                    "name": "Coverage Model",
                    "model_family": "LLM",
                    "provider": "local",
                    "owner": "Model Governance",
                    "intended_use": intended_use
                    if intended_use is not None
                    else ["ADVISORY_RESEARCH_SYNTHESIS"],
                    "prohibited_use": ["FINAL_DECISION"],
                    "authority": {
                        "authority_ceiling": "ADVISORY_ONLY",
                        "decision_authority": False,
                        "risk_override": False,
                        "strategy_promotion": False,
                        "execution_authority": False,
                        "live_order_authority": False,
                    },
                },
                "version": {
                    "model_id": "coverage-model",
                    "model_version": "coverage:v1",
                    "lifecycle_status": "RESEARCH_ONLY",
                    "input_contract_version": "1.0.0",
                    "output_contract_version": "1.0.0",
                    "source_path": "src/models/model.py",
                },
                "artifact": {
                    "artifact_type": artifact_type,
                    "artifact_uri": artifact_uri,
                    "artifact_sha256": artifact_sha256,
                    "license_status": "VERIFIED",
                    "rollback_binding": "coverage:v1",
                },
            }
        ],
    }


def _write_registry(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(
        "# Registry\n\n```json model-registry\n"
        + json.dumps(payload, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"model_id": "!"}, "model_id is invalid"),
        ({"model_family": "DOMAIN_MODEL"}, "family is invalid"),
        ({"name": ""}, "identity is required"),
        ({"intended_use": ()}, "use boundaries are required"),
        ({"authority_ceiling": "FINAL_DECISION"}, "must be advisory-only"),
    ],
)
def test_model_definition_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_definition(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"model_id": "!"}, "model_id is invalid"),
        ({"model_version": ""}, "identity is required"),
        ({"lifecycle_status": "PROMOTED"}, "lifecycle status is invalid"),
        ({"source_path": "docs/model.py"}, "must be repository-relative"),
    ],
)
def test_model_version_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_version(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"artifact_type": "REMOTE_MODEL"}, "type is invalid"),
        ({"artifact_uri": ""}, "identity is required"),
        ({"artifact_sha256": "BAD"}, "hash is invalid"),
        ({"license_status": "APPROVED"}, "license status is invalid"),
    ],
)
def test_model_artifact_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_artifact(), **changes)


def test_model_registry_entry_rejects_identity_and_artifact_drift() -> None:
    with pytest.raises(ValueError, match="identity mismatch"):
        ModelRegistryEntry(
            _definition(),
            replace(_version(), model_id="different-model"),
            _artifact(),
        )
    with pytest.raises(ValueError, match="requires an artifact hash"):
        ModelRegistryEntry(
            _definition(),
            _version(),
            replace(_artifact(), artifact_sha256=None),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"entries": ()}, "requires at least one entry"),
        ({"status": "UNKNOWN"}, "status is invalid"),
        (
            {"status": "PASS", "blockers": ("BLOCKED",)},
            "passing model registry cannot contain blockers",
        ),
        (
            {"status": "RUNNING_WITH_BLOCKERS", "blockers": ()},
            "blocked model registry requires blockers",
        ),
        ({"execution_allowed": True}, "cannot authorize execution or promotion"),
    ],
)
def test_model_registry_report_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    report = ModelRegistryReport((_entry(),), (), "PASS")
    with pytest.raises(ValueError, match=message):
        replace(report, **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"canonical_model_id": "!"}, "model_id is invalid"),
        ({"provider": ""}, "identity is required"),
        ({"model_family": "DOMAIN_MODEL"}, "family is invalid"),
        ({"blockers": ("BLOCKED",)}, "allowed model route"),
        ({"allowed": False}, "blocked model route requires blockers"),
        ({"route_sha256": "BAD"}, "route hash is invalid"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_model_route_decision_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_route(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"model_id": "!"}, "model_id is invalid"),
        ({"provider": ""}, "provider is required"),
        ({"blockers": ("BLOCKED",)}, "admitted model invocation"),
        ({"allowed": False}, "blocked model invocation requires blockers"),
        (
            {"route_decision": replace(_route(), canonical_model_id="different-model")},
            "route decision mismatch",
        ),
        ({"execution_allowed": True}, "cannot authorize execution or promotion"),
    ],
)
def test_model_gateway_decision_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_gateway(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"canonical_model_id": "!"}, "model_id is invalid"),
        ({"model_version": ""}, "identity is required"),
        ({"input_snapshot_sha256": "BAD"}, "input snapshot hash is invalid"),
        ({"provenance_sha256": "BAD"}, "provenance hash is invalid"),
        ({"artifact_sha256": "BAD"}, "artifact hash is invalid"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_model_inference_envelope_rejects_invalid_contracts(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_envelope(), **changes)


def test_inference_builder_rejects_invalid_input_hashes() -> None:
    with pytest.raises(ValueError, match="prompt hash is invalid"):
        build_advisory_inference_envelope(
            canonical_model_id="coverage-model",
            model_version="coverage:v1",
            task_type="ADVISORY_RESEARCH_SYNTHESIS",
            prompt_sha256="BAD",
            source_content_sha256=(HASH,),
        )
    with pytest.raises(ValueError, match="source hash is invalid"):
        build_advisory_inference_envelope(
            canonical_model_id="coverage-model",
            model_version="coverage:v1",
            task_type="ADVISORY_RESEARCH_SYNTHESIS",
            prompt_sha256=HASH,
            source_content_sha256=("BAD",),
        )


def test_registry_loader_rejects_malformed_documents(tmp_path: Path) -> None:
    missing_fence = tmp_path / "missing-fence.md"
    missing_fence.write_text("# Registry\n", encoding="utf-8")
    invalid_json = tmp_path / "invalid-json.md"
    invalid_json.write_text(
        '```json model-registry\n{"broken":\n```\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="canonical JSON block is missing"):
        load_model_registry(missing_fence)
    with pytest.raises(ValueError, match="canonical JSON is invalid"):
        load_model_registry(invalid_json)
    with pytest.raises(ValueError, match="model registry must be an object"):
        load_model_registry(_write_registry(tmp_path, "array.md", []))
    with pytest.raises(ValueError, match="keys mismatch"):
        load_model_registry(
            _write_registry(tmp_path, "keys.md", {"schema_version": "1.0.0"})
        )
    with pytest.raises(ValueError, match="schema version is unsupported"):
        load_model_registry(
            _write_registry(
                tmp_path,
                "version.md",
                {"schema_version": "2.0.0", "entries": []},
            )
        )
    with pytest.raises(ValueError, match="entries are required"):
        load_model_registry(
            _write_registry(
                tmp_path,
                "entries.md",
                {"schema_version": "1.0.0", "entries": []},
            )
        )

    duplicate = _registry_payload()
    duplicate["entries"].append(deepcopy(duplicate["entries"][0]))
    with pytest.raises(ValueError, match="identifiers must be unique"):
        load_model_registry(_write_registry(tmp_path, "duplicate.md", duplicate))


def test_registry_parsing_helpers_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        model_registry_module._mapping([], "payload")
    with pytest.raises(ValueError, match="keys mismatch"):
        model_registry_module._require_keys({"actual": 1}, {"expected"}, "payload")
    with pytest.raises(ValueError, match="must be nonblank text"):
        model_registry_module._text(1, "field")
    with pytest.raises(ValueError, match="must be a non-empty list"):
        model_registry_module._texts([], "items")
    with pytest.raises(ValueError, match="entries must be unique"):
        model_registry_module._texts(["same", "same"], "items")
    with pytest.raises(ValueError, match="must be boolean"):
        model_registry_module._bool(1, "flag")
    with pytest.raises(ValueError, match="lowercase SHA-256 or null"):
        model_registry_module._optional_sha256("A" * 64)


def test_registry_validation_covers_artifact_failure_modes(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"coverage-model")
    model_hash = sha256(model.read_bytes()).hexdigest()

    passed = validate_model_registry(
        tmp_path,
        _write_registry(
            tmp_path,
            "passed.md",
            _registry_payload(artifact_sha256=model_hash),
        ),
    )
    unverifiable = validate_model_registry(
        tmp_path,
        _write_registry(
            tmp_path,
            "unverifiable.md",
            _registry_payload(
                artifact_type="LOCAL_MODEL_MANIFEST",
                artifact_sha256=model_hash,
            ),
        ),
    )
    outside = validate_model_registry(
        tmp_path,
        _write_registry(
            tmp_path,
            "outside.md",
            _registry_payload(artifact_uri="../outside.bin"),
        ),
    )
    missing = validate_model_registry(
        tmp_path,
        _write_registry(
            tmp_path,
            "missing.md",
            _registry_payload(artifact_uri="missing.bin"),
        ),
    )

    assert passed.status == "PASS"
    assert passed.blockers == ()
    assert passed.execution_allowed is False
    assert passed.promotion_status == "RESEARCH_ONLY"
    assert passed.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert unverifiable.blockers == ("ARTIFACT_HASH_UNVERIFIABLE:coverage-model",)
    assert outside.blockers == ("ARTIFACT_URI_OUTSIDE_REPOSITORY:coverage-model",)
    assert missing.blockers == ("ARTIFACT_MISSING:coverage-model",)


def test_advisory_gateway_preserves_unregistered_and_task_blockers(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"coverage-model")
    model_hash = sha256(model.read_bytes()).hexdigest()
    registry = _write_registry(
        tmp_path,
        "registry.md",
        _registry_payload(artifact_sha256=model_hash),
    )
    restricted_registry = _write_registry(
        tmp_path,
        "restricted.md",
        _registry_payload(
            artifact_sha256=model_hash,
            intended_use=["ADVISORY_RESEARCH_SYNTHESIS"],
        ),
    )

    unregistered = admit_advisory_model_invocation(
        tmp_path,
        "missing-model",
        "local",
        "coverage:v1",
        registry,
    )
    task_not_permitted = admit_advisory_model_invocation(
        tmp_path,
        "coverage-model",
        "local",
        "coverage:v1",
        restricted_registry,
        task="READ_ONLY_LOCAL_WORKBENCH",
    )

    assert unregistered.blockers == ("UNREGISTERED_MODEL:missing-model",)
    assert unregistered.route_decision is not None
    assert unregistered.route_decision.allowed is False
    assert task_not_permitted.blockers == (
        "MODEL_TASK_NOT_PERMITTED:READ_ONLY_LOCAL_WORKBENCH:coverage-model",
    )
    assert task_not_permitted.execution_allowed is False
    assert task_not_permitted.promotion_status == "RESEARCH_ONLY"
    assert task_not_permitted.live_eligibility_status == "LIVE_ORDER_BLOCKED"

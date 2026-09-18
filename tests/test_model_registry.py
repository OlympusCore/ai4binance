"""Regression coverage for the fail-closed canonical model registry."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.governance.model_registry import (
    ModelGateway,
    admit_advisory_model_invocation,
    build_advisory_inference_envelope,
    load_model_registry,
    require_registered_model,
    validate_model_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "registries" / "registry_model_registry.md"


def test_registry_loads_observed_model_entries() -> None:
    entries = load_model_registry(REGISTRY)

    qwen = require_registered_model("local-ollama-qwen3-8b", entries)
    scenario = require_registered_model("price-action-scenario-catalog", entries)

    assert qwen.definition.model_family == "LLM"
    assert qwen.version.lifecycle_status == "OBSERVED_UNVERIFIED"
    assert qwen.artifact.artifact_sha256 is None
    assert scenario.definition.model_family == "SCENARIO_MODEL"
    assert scenario.artifact.artifact_sha256 is not None
    assert all(entry.definition.execution_authority is False for entry in entries)
    assert all(entry.definition.live_order_authority is False for entry in entries)


def test_registry_reports_unverified_artifact_and_preserves_live_block() -> None:
    report = validate_model_registry(ROOT, REGISTRY)

    assert report.status == "RUNNING_WITH_BLOCKERS"
    assert "MODEL_OBSERVED_UNVERIFIED:local-ollama-qwen3-8b" in report.blockers
    assert "ARTIFACT_HASH_UNVERIFIED:local-ollama-qwen3-8b" in report.blockers
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_registry_rejects_unregistered_model() -> None:
    with pytest.raises(ValueError, match="UNREGISTERED_MODEL:unregistered-model"):
        require_registered_model("unregistered-model", load_model_registry(REGISTRY))


def test_advisory_gateway_blocks_unverified_and_provider_drift() -> None:
    unverified = admit_advisory_model_invocation(
        ROOT,
        "local-ollama-qwen3-8b",
        "ollama",
        "qwen3:8b",
        REGISTRY,
    )
    provider_drift = admit_advisory_model_invocation(
        ROOT,
        "local-ollama-qwen3-8b",
        "llama.cpp",
        "qwen3:8b",
        REGISTRY,
    )
    version_drift = admit_advisory_model_invocation(
        ROOT,
        "local-ollama-qwen3-8b",
        "ollama",
        "other-model",
        REGISTRY,
    )

    assert unverified.allowed is False
    assert unverified.route_decision is not None
    assert unverified.route_decision.task_type == "ADVISORY_RESEARCH_SYNTHESIS"
    assert unverified.route_decision.route_sha256
    assert "MODEL_OBSERVED_UNVERIFIED:local-ollama-qwen3-8b" in unverified.blockers
    assert provider_drift.allowed is False
    assert "MODEL_PROVIDER_MISMATCH:local-ollama-qwen3-8b:llama.cpp" in (
        provider_drift.blockers
    )
    assert "MODEL_VERSION_MISMATCH:local-ollama-qwen3-8b:other-model" in (
        version_drift.blockers
    )
    assert unverified.execution_allowed is False
    assert unverified.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_advisory_gateway_fails_closed_when_registry_is_unavailable(
    tmp_path: Path,
) -> None:
    decision = admit_advisory_model_invocation(
        ROOT,
        "local-ollama-qwen3-8b",
        "ollama",
        "qwen3:8b",
        tmp_path / "missing-registry.md",
    )

    assert decision.allowed is False
    assert decision.blockers == ("MODEL_REGISTRY_UNAVAILABLE:local-ollama-qwen3-8b",)
    assert decision.execution_allowed is False


def test_model_gateway_uses_its_configured_registry() -> None:
    decision = ModelGateway(ROOT, REGISTRY).admit_advisory(
        "local-ollama-qwen3-8b",
        "ollama",
        "qwen3:8b",
    )

    assert decision.allowed is False
    assert "MODEL_OBSERVED_UNVERIFIED:local-ollama-qwen3-8b" in decision.blockers


def test_advisory_gateway_blocks_unknown_task_and_wrong_model_family() -> None:
    entries = load_model_registry(REGISTRY)
    scenario = require_registered_model("price-action-scenario-catalog", entries)
    unknown_task = admit_advisory_model_invocation(
        ROOT,
        "local-ollama-qwen3-8b",
        "ollama",
        "qwen3:8b",
        REGISTRY,
        task="UNSUPPORTED_ADVISORY_TASK",
    )
    wrong_family = admit_advisory_model_invocation(
        ROOT,
        scenario.definition.model_id,
        scenario.definition.provider,
        scenario.version.model_version,
        REGISTRY,
        task="ADVISORY_RESEARCH_SYNTHESIS",
    )

    assert unknown_task.allowed is False
    assert "MODEL_TASK_UNSUPPORTED:UNSUPPORTED_ADVISORY_TASK" in unknown_task.blockers
    assert wrong_family.allowed is False
    assert (
        "MODEL_TASK_FAMILY_NOT_PERMITTED:ADVISORY_RESEARCH_SYNTHESIS:SCENARIO_MODEL"
        in wrong_family.blockers
    )


def test_inference_envelope_is_deterministic_and_never_authorizes_execution() -> None:
    first = build_advisory_inference_envelope(
        canonical_model_id="local-ollama-qwen3-8b",
        model_version="qwen3:8b",
        task_type="ADVISORY_RESEARCH_SYNTHESIS",
        prompt_sha256="a" * 64,
        source_content_sha256=("b" * 64, "c" * 64),
    )
    second = build_advisory_inference_envelope(
        canonical_model_id="local-ollama-qwen3-8b",
        model_version="qwen3:8b",
        task_type="ADVISORY_RESEARCH_SYNTHESIS",
        prompt_sha256="a" * 64,
        source_content_sha256=("c" * 64, "b" * 64),
    )

    assert first.input_snapshot_sha256 == second.input_snapshot_sha256
    assert first.provenance_sha256 == second.provenance_sha256
    assert first.execution_allowed is False
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_inference_schema_is_canonical_and_fail_closed() -> None:
    document = REGISTRY.read_text(encoding="utf-8")
    schema_path = ROOT / "schemas" / "models" / "model_inference.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert "schemas/models/model_inference.schema.json" in document
    assert schema["additionalProperties"] is False
    assert schema["properties"]["execution_allowed"] == {"const": False}
    assert schema["properties"]["live_eligibility_status"] == {
        "const": "LIVE_ORDER_BLOCKED"
    }


def test_route_decision_schema_is_canonical_and_fail_closed() -> None:
    document = REGISTRY.read_text(encoding="utf-8")
    schema_path = ROOT / "schemas" / "models" / "model_route_decision.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert "schemas/models/model_route_decision.schema.json" in document
    assert schema["additionalProperties"] is False
    assert schema["properties"]["execution_allowed"] == {"const": False}
    assert schema["properties"]["live_eligibility_status"] == {
        "const": "LIVE_ORDER_BLOCKED"
    }
    assert schema["allOf"][0]["then"]["properties"]["blockers"] == {"maxItems": 0}
    assert schema["allOf"][0]["else"]["properties"]["blockers"] == {"minItems": 1}


def test_registry_detects_source_contract_artifact_substitution(tmp_path: Path) -> None:
    document = REGISTRY.read_text(encoding="utf-8")
    payload = _registry_payload(document)
    payload["entries"][1]["artifact"]["artifact_sha256"] = "0" * 64
    tampered = tmp_path / "registry.md"
    tampered.write_text(_registry_document(payload), encoding="utf-8")

    report = validate_model_registry(ROOT, tampered)

    assert "ARTIFACT_HASH_MISMATCH:price-action-scenario-catalog" in report.blockers


def test_registry_rejects_authority_escalation(tmp_path: Path) -> None:
    payload = _registry_payload(REGISTRY.read_text(encoding="utf-8"))
    payload["entries"][0]["definition"]["authority"]["execution_authority"] = True
    invalid = tmp_path / "registry.md"
    invalid.write_text(_registry_document(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot grant authority"):
        load_model_registry(invalid)


def _registry_payload(document: str) -> dict[str, Any]:
    opening = "```json model-registry\n"
    payload = document.split(opening, maxsplit=1)[1].split("\n```", maxsplit=1)[0]
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("model registry payload must be an object")
    return cast(dict[str, Any], decoded)


def _registry_document(payload: dict[str, Any]) -> str:
    return "# Registry\n\n```json model-registry\n" + json.dumps(payload) + "\n```\n"

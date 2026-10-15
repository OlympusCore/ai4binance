"""Proofs for the canonical local-model role bindings."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ai4binance.governance.local_model_roles import (
    load_local_model_role,
    validate_role_runtime,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("extra", True),
        ("schema_version", "unsupported"),
        ("evidence_flow", []),
        ("execution_allowed", True),
        ("roles", {}),
        ("binding", []),
        ("tasks", [None]),
        ("model_id", " "),
    ],
)
def test_role_loader_rejects_malformed_contract_without_runtime_activation(
    tmp_path: Path, key: str, value: object
) -> None:
    payload = json.loads(
        (ROOT / "config/local_models/local_model_roles.json").read_text(
            encoding="utf-8"
        )
    )
    role = "VISION_PERCEPTION_AGENT"
    if key == "binding":
        payload["roles"][role] = value
    elif key == "tasks":
        payload["roles"][role]["allowed_tasks"] = value
    elif key == "model_id":
        payload["roles"][role]["model_id"] = value
    else:
        payload[key] = value
    path = tmp_path / "config/local_models/local_model_roles.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="LOCAL_MODEL_ROLE_CONTRACT_UNAVAILABLE"):
        load_local_model_role(tmp_path, role)


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "EXECUTION_AUTHORITY"},
        {"model_id": " "},
        {"allowed_tasks": ()},
        {"execution_allowed": True},
        {"promotion_status": "PROMOTED"},
        {"live_eligibility_status": "READY"},
    ],
)
def test_role_value_cannot_widen_its_advisory_boundary(
    changes: dict[str, Any],
) -> None:
    role = load_local_model_role(ROOT, "VISION_PERCEPTION_AGENT")
    with pytest.raises(ValueError, match="local model role"):
        replace(role, **changes)


def test_runtime_binding_denies_model_and_provider_mismatch() -> None:
    role = load_local_model_role(ROOT, "VISION_PERCEPTION_AGENT")
    assert validate_role_runtime(
        role,
        model_id="test-only-wrong-model",
        provider="test-only-wrong-provider",
        runtime_model=role.runtime_model,
        task=role.allowed_tasks[0],
    ) == (
        "MODEL_ROLE_MODEL_MISMATCH:VISION_PERCEPTION_AGENT",
        "MODEL_ROLE_PROVIDER_MISMATCH:VISION_PERCEPTION_AGENT",
    )


def test_local_model_roles_bind_roles_to_runtime_implementation() -> None:
    vision = load_local_model_role(ROOT, "VISION_PERCEPTION_AGENT")
    reasoning = load_local_model_role(ROOT, "PRIMARY_LOCAL_REASONING_AGENT")

    assert vision.model_id == "local-llamacpp-qwen25vl-3b"
    assert vision.provider == "llama.cpp"
    assert vision.runtime_model == "Qwen2.5-VL-3B-Instruct-Q4_K_M"
    assert vision.activation_mode == "MANUAL_ONLY"
    assert reasoning.model_id == "local-llamacpp-qwen3-8b"
    assert reasoning.provider == "llama.cpp"
    assert reasoning.runtime_model == "qwen3:8b"
    assert reasoning.activation_mode == "BACKGROUND_ALWAYS_ON"
    assert vision.execution_allowed is False
    assert reasoning.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_local_model_roles_fail_closed_on_runtime_or_task_drift() -> None:
    role = load_local_model_role(ROOT, "VISION_PERCEPTION_AGENT")

    blockers = validate_role_runtime(
        role,
        model_id=role.model_id,
        provider=role.provider,
        runtime_model="other-model",
        task="ADVISORY_RESEARCH_SYNTHESIS",
    )

    assert blockers == (
        "MODEL_ROLE_RUNTIME_MISMATCH:VISION_PERCEPTION_AGENT",
        "MODEL_ROLE_TASK_MISMATCH:VISION_PERCEPTION_AGENT:ADVISORY_RESEARCH_SYNTHESIS",
    )


def test_local_model_roles_fail_closed_when_contract_is_missing(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="LOCAL_MODEL_ROLE_CONTRACT_UNAVAILABLE:VISION_PERCEPTION_AGENT",
    ):
        load_local_model_role(tmp_path, "VISION_PERCEPTION_AGENT")


def test_local_model_roles_fail_closed_on_prohibited_capability_drift(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config" / "local_models"
    config.mkdir(parents=True)
    payload = json.loads(
        (ROOT / "config" / "local_models" / "local_model_roles.json").read_text(
            encoding="utf-8"
        )
    )
    payload["roles"]["VISION_PERCEPTION_AGENT"]["prohibited_capabilities"].pop()
    (config / "local_model_roles.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    with pytest.raises(
        ValueError,
        match="LOCAL_MODEL_ROLE_CONTRACT_UNAVAILABLE:VISION_PERCEPTION_AGENT",
    ):
        load_local_model_role(tmp_path, "VISION_PERCEPTION_AGENT")

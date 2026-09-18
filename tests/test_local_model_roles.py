"""Proofs for the canonical local-model role bindings."""

import json
from pathlib import Path

import pytest

from ai4binance.governance.local_model_roles import (
    load_local_model_role,
    validate_role_runtime,
)

ROOT = Path(__file__).resolve().parents[1]


def test_local_model_roles_bind_roles_to_runtime_implementation() -> None:
    vision = load_local_model_role(ROOT, "VISION_PERCEPTION_AGENT")
    reasoning = load_local_model_role(ROOT, "PRIMARY_LOCAL_REASONING_AGENT")

    assert vision.model_id == "local-llamacpp-qwen25vl-3b"
    assert vision.provider == "llama.cpp"
    assert vision.runtime_model == "Qwen2.5-VL-3B-Instruct-Q4_K_M"
    assert reasoning.model_id == "local-llamacpp-qwen3-8b"
    assert reasoning.provider == "llama.cpp"
    assert reasoning.runtime_model == "qwen3:8b"
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

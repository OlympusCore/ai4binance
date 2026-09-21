"""Fail-closed canonical bindings between local model roles and runtime models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_ROLE_NAMES = frozenset({"VISION_PERCEPTION_AGENT", "PRIMARY_LOCAL_REASONING_AGENT"})
_EVIDENCE_FLOW = (
    "VISION_PERCEPTION_AGENT",
    "STRUCTURED_EVIDENCE",
    "SCHEMA_VALIDATION",
    "PRIMARY_LOCAL_REASONING_AGENT",
    "DETERMINISTIC_VALIDATION_AND_RISK_GATES",
    "DECISION_SUPPORT_OUTPUT",
)
_EXPECTED_BINDINGS = {
    "VISION_PERCEPTION_AGENT": {
        "model_id": "local-llamacpp-qwen25vl-3b",
        "provider": "llama.cpp",
        "runtime_model": "Qwen2.5-VL-3B-Instruct-Q4_K_M",
        "activation_mode": "MANUAL_ONLY",
        "allowed_tasks": ("LOCAL_IMAGE_ADVISORY_ANALYSIS",),
        "prohibited_capabilities": (
            "AUTHORIZE_TRADE",
            "CALCULATE_FINAL_POSITION_SIZE",
            "OVERRIDE_RISK_CONTROLS",
            "APPROVE_LIVE_EXECUTION",
            "MODIFY_GOVERNANCE",
        ),
    },
    "PRIMARY_LOCAL_REASONING_AGENT": {
        "model_id": "local-llamacpp-qwen3-8b",
        "provider": "llama.cpp",
        "runtime_model": "qwen3:8b",
        "activation_mode": "BACKGROUND_ALWAYS_ON",
        "allowed_tasks": (
            "ADVISORY_RESEARCH_SYNTHESIS",
            "READ_ONLY_LOCAL_WORKBENCH",
        ),
        "prohibited_capabilities": (
            "AUTHORIZE_LIVE_EXECUTION",
            "BYPASS_DETERMINISTIC_GATES",
            "OVERRIDE_RISK_LIMITS",
            "MODIFY_GOVERNANCE",
        ),
    },
}


@dataclass(frozen=True, slots=True)
class LocalModelRole:
    role: str
    model_id: str
    provider: str
    runtime_model: str
    activation_mode: str
    allowed_tasks: tuple[str, ...]
    prohibited_capabilities: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.role not in _ROLE_NAMES:
            raise ValueError("local model role is invalid")
        if not all(
            value.strip()
            for value in (
                self.model_id,
                self.provider,
                self.runtime_model,
                self.activation_mode,
            )
        ):
            raise ValueError("local model role identity is required")
        if not self.allowed_tasks or not self.prohibited_capabilities:
            raise ValueError("local model role boundaries are required")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("local model role cannot authorize execution")


def local_model_roles_path(repository_root: Path) -> Path:
    return repository_root / "config" / "local_models" / "local_model_roles.json"


def load_local_model_role(repository_root: Path, role: str) -> LocalModelRole:
    """Return one strict role binding; missing or drifted configuration fails closed."""

    try:
        payload = json.loads(
            local_model_roles_path(repository_root).read_text(encoding="utf-8")
        )
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "roles",
            "evidence_flow",
            "execution_allowed",
            "promotion_status",
            "live_eligibility_status",
        }:
            raise ValueError("local model role contract is invalid")
        if payload["schema_version"] != "1.1.0" or role not in _ROLE_NAMES:
            raise ValueError("local model role contract is unsupported")
        if payload["evidence_flow"] != list(_EVIDENCE_FLOW):
            raise ValueError("local model role evidence flow is invalid")
        if (
            payload["execution_allowed"] is not False
            or payload["promotion_status"] != "RESEARCH_ONLY"
            or payload["live_eligibility_status"] != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("local model role authority boundary is invalid")
        roles = payload["roles"]
        if not isinstance(roles, dict) or set(roles) != _ROLE_NAMES:
            raise ValueError("local model role set is invalid")
        binding = roles.get(role)
        if not isinstance(binding, dict) or set(binding) != {
            "model_id",
            "provider",
            "runtime_model",
            "activation_mode",
            "allowed_tasks",
            "prohibited_capabilities",
        }:
            raise ValueError("local model role binding is invalid")
        tasks = binding["allowed_tasks"]
        prohibited = binding["prohibited_capabilities"]
        if (
            not isinstance(tasks, list)
            or not isinstance(prohibited, list)
            or not all(isinstance(item, str) and item for item in tasks + prohibited)
        ):
            raise ValueError("local model role boundary values are invalid")
        expected = _EXPECTED_BINDINGS[role]
        if (
            _required_text(binding, "model_id") != expected["model_id"]
            or _required_text(binding, "provider") != expected["provider"]
            or _required_text(binding, "runtime_model") != expected["runtime_model"]
            or _required_text(binding, "activation_mode") != expected["activation_mode"]
            or tuple(tasks) != expected["allowed_tasks"]
            or tuple(prohibited) != expected["prohibited_capabilities"]
        ):
            raise ValueError("local model role canonical binding drifted")
        return LocalModelRole(
            role=role,
            model_id=_required_text(binding, "model_id"),
            provider=_required_text(binding, "provider"),
            runtime_model=_required_text(binding, "runtime_model"),
            activation_mode=_required_text(binding, "activation_mode"),
            allowed_tasks=tuple(tasks),
            prohibited_capabilities=tuple(prohibited),
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"LOCAL_MODEL_ROLE_CONTRACT_UNAVAILABLE:{role}") from error


def validate_role_runtime(
    binding: LocalModelRole,
    *,
    model_id: str,
    provider: str,
    runtime_model: str,
    task: str,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if binding.model_id != model_id:
        blockers.append(f"MODEL_ROLE_MODEL_MISMATCH:{binding.role}")
    if binding.provider.casefold() != provider.casefold():
        blockers.append(f"MODEL_ROLE_PROVIDER_MISMATCH:{binding.role}")
    if binding.runtime_model != runtime_model:
        blockers.append(f"MODEL_ROLE_RUNTIME_MISMATCH:{binding.role}")
    if task not in binding.allowed_tasks:
        blockers.append(f"MODEL_ROLE_TASK_MISMATCH:{binding.role}:{task}")
    return tuple(blockers)


def _required_text(binding: dict[str, object], key: str) -> str:
    value = binding.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("local model role identity is invalid")
    return value

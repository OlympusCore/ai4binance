"""Deterministic branch-coverage closure for fail-closed LLMOps policy."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from ai4binance.multiops.llmops import (
    BaselineManifest,
    BudgetLimit,
    EnforcementMode,
    ModelAuthorityCeiling,
    ModelCapabilityEvidence,
    ModelContextRequirement,
    ModelGovernancePolicy,
    ModelInvocationEvidence,
    ModelRoutingCapability,
    ModelSelectionDecision,
    ModelSelectionOutcome,
    ModelSelectionRequest,
    ModelTier,
    PricingSource,
    ProviderRoutingStatus,
    ReasoningEffort,
    SelectionResourceBudget,
    StructuredOutputRequirement,
    TaskClass,
    TaskCriticality,
    TaskRoutingProfile,
    TokenAccountingSource,
    load_baseline_manifest,
    load_model_governance_policy,
    select_model_candidate,
)
from ai4binance.multiops.llmops import policy as policy_module


def _request(**overrides: object) -> ModelSelectionRequest:
    payload: dict[str, Any] = {
        "request_id": "request-coverage",
        "task_type": "normal_feature",
        "task_class": TaskClass.MODERATE,
        "criticality": TaskCriticality.MEDIUM,
        "authority_ceiling": ModelAuthorityCeiling.ADVISORY_ONLY,
        "privacy_class": "LOCAL_ONLY",
        "preferred_tier": ModelTier.BALANCED,
    }
    payload.update(overrides)
    return ModelSelectionRequest(**payload)


def _available_policy() -> ModelGovernancePolicy:
    base = load_model_governance_policy()
    models = tuple(
        replace(
            model,
            model_id=f"verified-{model.tier.value.lower()}",
            available=True,
            reasoning_levels=(ReasoningEffort.LOW,),
            context_window=128_000,
            max_output=8_000,
            input_per_million=Decimal("1"),
            cached_input_per_million=Decimal("0.25"),
            output_per_million=Decimal("4"),
        )
        for model in base.models
    )
    return replace(
        base,
        enforcement_mode=EnforcementMode.ENFORCE,
        pricing_source=PricingSource("openai", "USD", date(2026, 9, 9), True),
        budgets=(
            ("per_task", BudgetLimit(soft_limit=8_000, hard_limit=12_000)),
            ("daily", BudgetLimit(soft_limit=80_000, hard_limit=120_000)),
            ("weekly", BudgetLimit(soft_limit=400_000, hard_limit=600_000)),
            ("monthly", BudgetLimit(soft_limit=1_600_000, hard_limit=2_400_000)),
        ),
        models=models,
    )


def _blocked_evidence() -> ModelCapabilityEvidence:
    return ModelCapabilityEvidence(
        tier=ModelTier.ECONOMY,
        model_id=None,
        available=False,
        eligible=False,
        matched_requirements=(),
        blockers=("MODEL_UNAVAILABLE",),
    )


def _decision() -> ModelSelectionDecision:
    return ModelSelectionDecision(
        request_id="request-coverage",
        task_type="normal_feature",
        outcome=ModelSelectionOutcome.DATA_UNAVAILABLE,
        policy_version="policy-v1",
        classifier_version="classifier-v1",
        model_registry_version="registry-v1",
        authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
        privacy_class="LOCAL_ONLY",
        context_requirement=ModelContextRequirement.LOCAL_ONLY,
        structured_output_requirement=StructuredOutputRequirement.OPTIONAL,
        provider_status=ProviderRoutingStatus.READY,
        selected_tier=None,
        selected_model_id=None,
        selected_reasoning=None,
        used_fallback=False,
        fallback_from_tier=None,
        reason_codes=("NO_POLICY_COMPATIBLE_MODEL",),
        candidate_evidence=(_blocked_evidence(),),
    )


def _invocation() -> ModelInvocationEvidence:
    return ModelInvocationEvidence(
        request_id="request-coverage",
        task_type="normal_feature",
        policy_version="policy-v1",
        authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
        privacy_class="LOCAL_ONLY",
        structured_output_requirement=StructuredOutputRequirement.OPTIONAL,
        provider_status=ProviderRoutingStatus.READY,
        model_id="verified-balanced",
        model_tier=ModelTier.BALANCED,
        reasoning_effort=ReasoningEffort.LOW,
        token_accounting_source=TokenAccountingSource.EXACT_PROVIDER,
        total_tokens=100,
        fallback_used=False,
        output_schema_validated=True,
    )


def _policy_payload() -> dict[str, Any]:
    raw = yaml.safe_load(
        Path("config/governance/codex_model_governance.yaml").read_text(
            encoding="utf-8"
        )
    )
    return cast(dict[str, Any], raw)


def _write_policy(tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_resource_and_task_routing_contracts_reject_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="max context files must be positive"):
        SelectionResourceBudget(max_context_files=0)
    with pytest.raises(ValueError, match="identity and task types are required"):
        TaskRoutingProfile("", ModelTier.ECONOMY, ("normal_feature",))
    with pytest.raises(ValueError, match="identity and task types are required"):
        TaskRoutingProfile("economy", ModelTier.ECONOMY, ())
    with pytest.raises(ValueError, match="unique and nonblank"):
        TaskRoutingProfile(
            "economy",
            ModelTier.ECONOMY,
            ("normal_feature", "normal_feature"),
        )
    with pytest.raises(ValueError, match="unique and nonblank"):
        TaskRoutingProfile("economy", ModelTier.ECONOMY, ("",))


def test_baseline_manifest_rejects_duplicate_ids_and_missing_task_types() -> None:
    manifest = load_baseline_manifest()
    duplicate = replace(manifest.tasks[1], task_id=manifest.tasks[0].task_id)
    duplicate_tasks = (manifest.tasks[0], duplicate, *manifest.tasks[2:])

    with pytest.raises(ValueError, match="task ids must be unique"):
        replace(manifest, tasks=duplicate_tasks)

    missing_documentation = tuple(
        task for task in manifest.tasks if task.task_type != "documentation"
    )
    with pytest.raises(ValueError, match="missing task types"):
        replace(manifest, tasks=missing_documentation)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"privacy_class": ""}, "privacy class is required"),
        ({"required_policy_version": " "}, "policy version cannot be blank"),
        (
            {
                "required_capabilities": (
                    ModelRoutingCapability.LONG_CONTEXT,
                    ModelRoutingCapability.LONG_CONTEXT,
                )
            },
            "required capabilities must be unique",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_model_selection_request_rejects_remaining_invalid_shapes(
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_request(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"model_id": " "}, "model id cannot be blank"),
        (
            {"matched_requirements": ("MODEL_AVAILABLE", "MODEL_AVAILABLE")},
            "matched requirements must be unique",
        ),
        ({"matched_requirements": ("",)}, "matched requirements must be unique"),
        ({"blockers": ("BLOCKED", "BLOCKED")}, "blockers must be unique"),
        ({"blockers": ("",)}, "blockers must be unique"),
        (
            {"eligible": True, "blockers": ("MODEL_UNAVAILABLE",)},
            "eligibility disagrees",
        ),
    ],
)
def test_model_capability_evidence_rejects_inconsistent_shapes(
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_blocked_evidence(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"request_id": ""}, "identity is required"),
        ({"policy_version": ""}, "policy version is required"),
        ({"privacy_class": ""}, "privacy class is required"),
        (
            {"reason_codes": ("BLOCKED", "BLOCKED")},
            "reason codes must be unique",
        ),
        ({"reason_codes": ("",)}, "reason codes must be unique"),
        ({"candidate_evidence": ()}, "requires candidate evidence"),
        ({"outcome": ModelSelectionOutcome.SELECTED}, "requires tier model"),
        (
            {"selected_tier": ModelTier.ECONOMY},
            "cannot carry selected model details",
        ),
        (
            {
                "outcome": ModelSelectionOutcome.SELECTED,
                "selected_tier": ModelTier.ECONOMY,
                "selected_model_id": "verified-economy",
                "selected_reasoning": ReasoningEffort.LOW,
                "fallback_from_tier": ModelTier.ADVANCED,
            },
            "non-fallback decision cannot carry fallback source",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_model_selection_decision_rejects_remaining_invalid_shapes(
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_decision(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"request_id": ""}, "request id is required"),
        ({"total_tokens": -1}, "total tokens cannot be negative"),
        ({"blockers": ("BLOCKED", "BLOCKED")}, "blockers must be unique"),
        ({"actual_cost_usd": Decimal("NaN")}, "cost must be finite"),
    ],
)
def test_model_invocation_evidence_rejects_remaining_invalid_shapes(
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_invocation(), **changes)


def test_soft_budget_and_capability_matrix_remain_fail_closed() -> None:
    available_policy = _available_policy()
    warning = select_model_candidate(
        available_policy,
        load_baseline_manifest(),
        _request(requested_total_tokens=9_000),
    )

    assert warning.outcome is ModelSelectionOutcome.DATA_UNAVAILABLE
    assert "TOKEN_BUDGET_WARNING" in warning.reason_codes
    assert warning.execution_allowed is False
    assert warning.promotion_status == "RESEARCH_ONLY"
    assert warning.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    capability_request = _request(
        required_capabilities=(
            ModelRoutingCapability.VERIFIED_PRICING,
            ModelRoutingCapability.CACHED_INPUT_PRICING,
            ModelRoutingCapability.LONG_CONTEXT,
            ModelRoutingCapability.LARGE_OUTPUT,
        )
    )
    unavailable_policy = load_model_governance_policy()
    unavailable = policy_module._assess_model_candidate(
        unavailable_policy,
        unavailable_policy.models[0],
        capability_request,
        (),
    )
    assert {
        "MODEL_UNAVAILABLE",
        "VERIFIED_PRICING_REQUIRED",
        "CACHED_INPUT_PRICING_REQUIRED",
        "LONG_CONTEXT_REQUIRED",
        "LARGE_OUTPUT_REQUIRED",
    } <= set(unavailable.blockers)
    assert unavailable.eligible is False

    compatible = policy_module._assess_model_candidate(
        available_policy,
        available_policy.models[0],
        capability_request,
        (),
    )
    assert compatible.eligible is True
    expected_capabilities = {
        capability.value for capability in capability_request.required_capabilities
    }
    assert expected_capabilities <= set(compatible.matched_requirements)


def test_selected_reasoning_requires_a_supported_policy_level() -> None:
    unavailable_policy = load_model_governance_policy()
    with pytest.raises(ValueError, match="at least one reasoning level"):
        policy_module._selected_reasoning(unavailable_policy.models[0], _request())

    available = _available_policy().models[0]
    assert (
        policy_module._selected_reasoning(available, _request()) is ReasoningEffort.LOW
    )
    assert (
        policy_module._selected_reasoning(
            available,
            _request(required_reasoning=ReasoningEffort.LOW),
        )
        is ReasoningEffort.LOW
    )


def test_policy_loader_rejects_disabled_or_structurally_drifted_controls(
    tmp_path: Path,
) -> None:
    disabled = deepcopy(_policy_payload())
    disabled["token_governance"]["enabled"] = False
    with pytest.raises(ValueError, match="token governance must remain enabled"):
        load_model_governance_policy(_write_policy(tmp_path, "disabled.yaml", disabled))

    extra_budget = deepcopy(_policy_payload())
    extra_budget["token_governance"]["budgets"]["hourly"] = {
        "soft_limit": None,
        "hard_limit": None,
    }
    with pytest.raises(ValueError, match="unknown periods"):
        load_model_governance_policy(
            _write_policy(tmp_path, "extra-budget.yaml", extra_budget)
        )

    missing_model = deepcopy(_policy_payload())
    del missing_model["models"]["exceptional"]
    with pytest.raises(ValueError, match="define every model tier"):
        load_model_governance_policy(
            _write_policy(tmp_path, "missing-model.yaml", missing_model)
        )

    duplicate_route = deepcopy(_policy_payload())
    duplicate_route["task_routing"]["terra"]["task_types"].append(
        "repository_discovery"
    )
    with pytest.raises(ValueError, match="task types must be unique"):
        load_model_governance_policy(
            _write_policy(tmp_path, "duplicate-route.yaml", duplicate_route)
        )


def test_policy_loading_helpers_cover_bounded_and_invalid_inputs(
    tmp_path: Path,
) -> None:
    oversized = tmp_path / "oversized.yaml"
    oversized.write_bytes(b"x" * (policy_module.MAX_POLICY_BYTES + 1))
    with pytest.raises(ValueError, match="exceeds bounded size"):
        policy_module._load_yaml_mapping(oversized)

    not_mapping = tmp_path / "not-mapping.yaml"
    not_mapping.write_text("- item\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        policy_module._load_yaml_mapping(not_mapping)
    with pytest.raises(ValueError, match="must be a mapping"):
        policy_module._mapping([], "mapping")
    with pytest.raises(ValueError, match="must be a sequence"):
        policy_module._sequence("text", "sequence")
    with pytest.raises(ValueError, match="unique nonblank strings"):
        policy_module._strings(("same", "same"), "strings")
    with pytest.raises(ValueError, match="must be a boolean"):
        policy_module._bool(1, "flag")

    assert policy_module._optional_text(7) == "7"
    with pytest.raises(ValueError, match="cannot be blank"):
        policy_module._optional_text(" ")

    assert policy_module._optional_int(7, "integer") == 7
    with pytest.raises(ValueError, match="integer or null"):
        policy_module._optional_int(True, "integer")
    with pytest.raises(ValueError, match="integer or null"):
        policy_module._optional_int("7", "integer")

    assert policy_module._optional_decimal("1.25") == Decimal("1.25")
    with pytest.raises(ValueError, match="decimal-compatible"):
        policy_module._optional_decimal(True)
    with pytest.raises(ValueError, match="decimal-compatible"):
        policy_module._optional_decimal("not-a-decimal")

    expected_date = date(2026, 9, 9)
    assert policy_module._optional_date(expected_date) is expected_date
    assert policy_module._optional_date("2026-09-09") == expected_date
    with pytest.raises(ValueError, match="must be ISO date"):
        policy_module._optional_date("09/09/2026")


def test_null_optional_helpers_preserve_unavailable_semantics() -> None:
    assert policy_module._optional_text(None) is None
    assert policy_module._optional_int(None, "integer") is None
    assert policy_module._optional_decimal(None) is None
    assert policy_module._optional_date(None) is None

    manifest: BaselineManifest = load_baseline_manifest()
    assert manifest.execution_allowed is False
    assert manifest.promotion_status == "RESEARCH_ONLY"
    assert manifest.live_eligibility_status == "LIVE_ORDER_BLOCKED"

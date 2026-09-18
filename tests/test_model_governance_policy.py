"""Versioned observe-only model_governance policy tests."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai4binance.multiops.llmops import (
    BaselineManifest,
    BaselineTaskDefinition,
    BudgetLimit,
    EnforcementMode,
    ModelAuthorityCeiling,
    ModelCandidate,
    ModelCandidatePolicy,
    ModelCapabilityEvidence,
    ModelContextRequirement,
    ModelGovernancePolicy,
    ModelInvocationEvidence,
    ModelRoutingCapability,
    ModelSelectionDecision,
    ModelSelectionGateway,
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
    TokenAccountingSource,
    load_baseline_manifest,
    load_model_governance_policy,
    route_model_selection_request,
    select_model_candidate,
)
from ai4binance.multiops.llmops.policy import REQUIRED_BASELINE_TASK_TYPES


def test_default_policy_is_unpriced_unavailable_and_observe_only() -> None:
    policy = load_model_governance_policy()

    assert policy.enforcement_mode is EnforcementMode.OBSERVE_ONLY
    assert policy.pricing_status == "PRICING_DATA_STALE"
    assert all(model.available is False for model in policy.models)
    assert all(model.model_id is None for model in policy.models)
    assert {model.tier for model in policy.models} == set(ModelTier)
    assert all(
        limit.soft_limit is None and limit.hard_limit is None
        for _, limit in policy.budgets
    )
    assert policy.execution_allowed is False
    assert policy.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert policy.recommended_tier("repository_discovery") is ModelTier.ECONOMY
    assert policy.recommended_tier("normal_feature") is ModelTier.BALANCED
    assert policy.recommended_tier("architecture_review") is ModelTier.ADVANCED
    assert policy.recommended_tier("red_team_review") is ModelTier.EXCEPTIONAL
    assert policy.recommended_tier("unknown_task") is None


def test_baseline_manifest_covers_required_nonexecuting_workloads() -> None:
    manifest = load_baseline_manifest()

    assert manifest.status == "BASELINE_REQUIRED"
    assert manifest.token_source_required == "EXACT_PROVIDER"  # nosec B105  # noqa: S105
    assert manifest.missing_data_status == "DATA_UNAVAILABLE"
    assert REQUIRED_BASELINE_TASK_TYPES <= {task.task_type for task in manifest.tasks}
    assert all(not task.mutates_trading_core for task in manifest.tasks)
    assert all(not task.live_execution for task in manifest.tasks)
    assert manifest.execution_allowed is False
    assert manifest.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_policy_rejects_authority_and_unknown_keys(tmp_path: Path) -> None:
    source = Path("config/governance/codex_model_governance.yaml")
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["authority"]["execution_allowed"] = True
    unsafe = tmp_path / "unsafe.yaml"
    unsafe.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot authorize"):
        load_model_governance_policy(unsafe)

    payload["authority"]["execution_allowed"] = False
    payload["unexpected"] = True
    unsafe.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="keys mismatch"):
        load_model_governance_policy(unsafe)


def test_policy_rejects_enforcement_without_hard_limits() -> None:
    policy = load_model_governance_policy()

    with pytest.raises(ValueError, match="requires every hard limit"):
        replace(policy, enforcement_mode=EnforcementMode.ENFORCE)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"soft_limit": 0, "hard_limit": None}, "must be positive"),
        ({"soft_limit": 10, "hard_limit": 5}, "cannot exceed"),
    ],
)
def test_budget_limits_reject_invalid_bounds(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        BudgetLimit(**kwargs)


def test_pricing_source_status_and_validation_are_fail_closed() -> None:
    assert PricingSource("OpenAI", "USD", None, False).status == "PRICING_DATA_STALE"
    assert PricingSource("OpenAI", "USD", date(2026, 8, 21), True).status == "READY"
    with pytest.raises(ValueError, match="identity is required"):
        PricingSource(" ", "USD", None, False)
    with pytest.raises(ValueError, match="USD pricing only"):
        PricingSource("OpenAI", "EUR", None, False)
    with pytest.raises(ValueError, match="requires pricing_as_of"):
        PricingSource("OpenAI", "USD", None, True)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model_id": " "}, "model id cannot be blank"),
        (
            {"reasoning_levels": (ReasoningEffort.LOW, ReasoningEffort.LOW)},
            "reasoning levels must be unique",
        ),
        ({"context_window": 0}, "token limits must be positive"),
        ({"max_output": 0}, "token limits must be positive"),
        ({"input_per_million": Decimal("-1")}, "prices must be finite"),
        (
            {"available": True, "model_id": None},
            "available model requires verified capability metadata",
        ),
        (
            {
                "input_per_million": Decimal("1"),
                "cached_input_per_million": Decimal("2"),
            },
            "cached input price cannot exceed input price",
        ),
    ],
)
def test_model_candidate_policy_rejects_invalid_metadata(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    payload: dict[str, Any] = {
        "tier": ModelTier.ECONOMY,
        "model_id": "gpt-test",
        "available": False,
        "reasoning_levels": (ReasoningEffort.LOW,),
        "context_window": 128000,
        "max_output": 4096,
        "input_per_million": Decimal("1"),
        "cached_input_per_million": Decimal("0.5"),
        "output_per_million": Decimal("2"),
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=message):
        ModelCandidatePolicy(**payload)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"policy_version": " "}, "versions are required"),
        ({"budgets": ()}, "budgets must cover each period once"),
        ({"models": ()}, "registry must cover every tier once"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_model_governance_policy_rejects_invalid_contracts(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    policy = load_model_governance_policy()
    payload: dict[str, Any] = {
        "schema_version": policy.schema_version,
        "policy_version": policy.policy_version,
        "classifier_version": policy.classifier_version,
        "model_registry_version": policy.model_registry_version,
        "pricing_version": policy.pricing_version,
        "enforcement_mode": policy.enforcement_mode,
        "pricing_source": policy.pricing_source,
        "budgets": policy.budgets,
        "models": policy.models,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=message):
        ModelGovernancePolicy(**payload)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"task_id": " "}, "identity is required"),
        ({"validation_commands": ()}, "requires validation commands"),
        ({"validation_commands": (" ",)}, "requires validation commands"),
        ({"mutates_trading_core": True}, "cannot mutate trading"),
        ({"live_execution": True}, "cannot mutate trading"),
    ],
)
def test_baseline_task_definition_rejects_unsafe_workloads(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    payload: dict[str, Any] = {
        "task_id": "task",
        "task_type": "unit_tests",
        "description": "Run deterministic unit tests.",
        "validation_commands": ("pytest tests/test_example.py",),
        "mutates_trading_core": False,
        "live_execution": False,
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=message):
        BaselineTaskDefinition(**payload)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"schema_version": " "}, "versions are required"),
        ({"status": "READY"}, "must remain BASELINE_REQUIRED"),
        ({"token_source_required": "ESTIMATED"}, "requires exact provider"),
        ({"missing_data_status": "READY"}, "must be DATA_UNAVAILABLE"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_baseline_manifest_rejects_invalid_contracts(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    manifest = load_baseline_manifest()
    payload: dict[str, Any] = {
        "schema_version": manifest.schema_version,
        "manifest_version": manifest.manifest_version,
        "status": "BASELINE_REQUIRED",
        "token_source_required": "EXACT_PROVIDER",
        "missing_data_status": "DATA_UNAVAILABLE",
        "tasks": manifest.tasks,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=message):
        BaselineManifest(**payload)


def _active_policy() -> ModelGovernancePolicy:
    return ModelGovernancePolicy(
        schema_version="1.0",
        policy_version="policy-v1",
        classifier_version="classifier-v1",
        model_registry_version="registry-v1",
        pricing_version="pricing-v1",
        enforcement_mode=EnforcementMode.ENFORCE,
        pricing_source=PricingSource("openai", "USD", date(2026, 8, 31), True),
        budgets=(
            ("per_task", BudgetLimit(soft_limit=8_000, hard_limit=12_000)),
            ("daily", BudgetLimit(soft_limit=80_000, hard_limit=120_000)),
            ("weekly", BudgetLimit(soft_limit=400_000, hard_limit=600_000)),
            ("monthly", BudgetLimit(soft_limit=1_600_000, hard_limit=2_400_000)),
        ),
        models=(
            ModelCandidatePolicy(
                tier=ModelTier.ECONOMY,
                model_id="gpt-economy",
                available=True,
                reasoning_levels=(ReasoningEffort.LOW,),
                context_window=64_000,
                max_output=2_000,
                input_per_million=Decimal("0.5"),
                cached_input_per_million=Decimal("0.1"),
                output_per_million=Decimal("2"),
            ),
            ModelCandidatePolicy(
                tier=ModelTier.BALANCED,
                model_id="gpt-balanced",
                available=True,
                reasoning_levels=(ReasoningEffort.LOW, ReasoningEffort.MEDIUM),
                context_window=128_000,
                max_output=8_000,
                input_per_million=Decimal("1"),
                cached_input_per_million=Decimal("0.2"),
                output_per_million=Decimal("4"),
            ),
            ModelCandidatePolicy(
                tier=ModelTier.ADVANCED,
                model_id="gpt-advanced",
                available=False,
                reasoning_levels=(ReasoningEffort.MEDIUM, ReasoningEffort.HIGH),
                context_window=256_000,
                max_output=16_000,
                input_per_million=Decimal("3"),
                cached_input_per_million=Decimal("1"),
                output_per_million=Decimal("12"),
            ),
            ModelCandidatePolicy(
                tier=ModelTier.EXCEPTIONAL,
                model_id="gpt-exceptional",
                available=False,
                reasoning_levels=(ReasoningEffort.HIGH, ReasoningEffort.MAX),
                context_window=512_000,
                max_output=32_000,
                input_per_million=Decimal("8"),
                cached_input_per_million=Decimal("4"),
                output_per_million=Decimal("24"),
            ),
        ),
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )


def test_model_selection_request_rejects_unsafe_shapes() -> None:
    with pytest.raises(ValueError, match="identity is required"):
        ModelSelectionRequest(
            request_id=" ",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
        )
    with pytest.raises(ValueError, match="fallback tiers must be unique"):
        ModelSelectionRequest(
            request_id="req-1",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            allowed_fallback_tiers=(ModelTier.ECONOMY, ModelTier.ECONOMY),
        )
    with pytest.raises(ValueError, match="cannot repeat the preferred tier"):
        ModelSelectionRequest(
            request_id="req-1",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            allowed_fallback_tiers=(ModelTier.BALANCED,),
        )
    with pytest.raises(ValueError, match="must be positive"):
        ModelSelectionRequest(
            request_id="req-1",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            requested_total_tokens=0,
        )
    with pytest.raises(ValueError, match="requires minimum context window"):
        ModelSelectionRequest(
            request_id="req-1",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            context_requirement=ModelContextRequirement.REPOSITORY_CONTEXT,
        )
    with pytest.raises(ValueError, match="requires minimum max output"):
        ModelSelectionRequest(
            request_id="req-1",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            structured_output_requirement=StructuredOutputRequirement.REQUIRED,
        )
    with pytest.raises(ValueError, match="single-invocation bounded"):
        ModelSelectionRequest(
            request_id="req-1",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            resource_budget=SelectionResourceBudget(max_parallel_invocations=2),
        )


def test_model_selector_uses_policy_compatible_fallback_only() -> None:
    gateway = ModelSelectionGateway(_active_policy(), load_baseline_manifest())
    request = ModelSelectionRequest(
        request_id="req-2",
        task_type="normal_feature",
        task_class=TaskClass.MODERATE,
        criticality=TaskCriticality.MEDIUM,
        authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
        privacy_class="LOCAL_ONLY",
        preferred_tier=ModelTier.ADVANCED,
        context_requirement=ModelContextRequirement.REPOSITORY_CONTEXT,
        structured_output_requirement=StructuredOutputRequirement.REQUIRED,
        provider_status=ProviderRoutingStatus.READY,
        required_policy_version="policy-v1",
        allowed_fallback_tiers=(ModelTier.BALANCED, ModelTier.ECONOMY),
        required_reasoning=ReasoningEffort.MEDIUM,
        minimum_context_window=120_000,
        minimum_max_output=4_000,
        requested_total_tokens=6_000,
        resource_budget=SelectionResourceBudget(
            max_context_files=4,
            max_context_bytes=64_000,
        ),
        required_capabilities=(
            ModelRoutingCapability.LONG_CONTEXT,
            ModelRoutingCapability.VERIFIED_PRICING,
        ),
    )
    decision = gateway.route(request)
    routed_decision = route_model_selection_request(
        _active_policy(),
        load_baseline_manifest(),
        request,
    )

    assert decision.outcome is ModelSelectionOutcome.SELECTED
    assert routed_decision == decision
    assert decision.selected_tier is ModelTier.BALANCED
    assert decision.selected_model_id == "gpt-balanced"
    assert decision.selected_reasoning is ReasoningEffort.MEDIUM
    assert decision.used_fallback is True
    assert decision.fallback_from_tier is ModelTier.ADVANCED
    assert decision.context_requirement is ModelContextRequirement.REPOSITORY_CONTEXT
    assert (
        decision.structured_output_requirement is StructuredOutputRequirement.REQUIRED
    )
    assert decision.provider_status is ProviderRoutingStatus.READY
    assert decision.provider_health is ProviderRoutingStatus.READY
    assert request.provider_health is ProviderRoutingStatus.READY
    assert request.token_budget == 6_000
    assert decision.reason_codes == ()
    assert isinstance(decision.candidate_evidence[0], ModelCapabilityEvidence)
    assert ModelCandidate is ModelCandidatePolicy
    assert decision.candidate_evidence[0].availability is True


def test_model_selector_refuses_non_permissive_fallback() -> None:
    decision = select_model_candidate(
        _active_policy(),
        load_baseline_manifest(),
        ModelSelectionRequest(
            request_id="req-3",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.HIGH,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="INTERNAL_REDACTED",
            preferred_tier=ModelTier.ADVANCED,
            context_requirement=ModelContextRequirement.REPOSITORY_CONTEXT,
            allowed_fallback_tiers=(ModelTier.ECONOMY,),
            required_reasoning=ReasoningEffort.HIGH,
            minimum_context_window=120_000,
            requested_total_tokens=6_000,
        ),
    )

    assert decision.outcome is ModelSelectionOutcome.DATA_UNAVAILABLE
    assert decision.selected_tier is None
    assert "NO_POLICY_COMPATIBLE_MODEL" in decision.reason_codes
    economy = next(
        item for item in decision.candidate_evidence if item.tier is ModelTier.ECONOMY
    )
    assert "REASONING_UNSUPPORTED" in economy.blockers


def test_model_selector_returns_data_unavailable_for_unknown_task_or_budget() -> None:
    unknown_task = select_model_candidate(
        _active_policy(),
        load_baseline_manifest(),
        ModelSelectionRequest(
            request_id="req-4",
            task_type="live_execution",
            task_class=TaskClass.HIGH,
            criticality=TaskCriticality.CRITICAL,
            authority_ceiling=ModelAuthorityCeiling.REPORT_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            requested_total_tokens=4_000,
        ),
    )
    budget_blocked = select_model_candidate(
        _active_policy(),
        load_baseline_manifest(),
        ModelSelectionRequest(
            request_id="req-5",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            requested_total_tokens=20_000,
        ),
    )

    assert unknown_task.outcome is ModelSelectionOutcome.DATA_UNAVAILABLE
    assert "TASK_TYPE_UNREGISTERED" in unknown_task.reason_codes
    assert budget_blocked.outcome is ModelSelectionOutcome.DATA_UNAVAILABLE
    assert "TOKEN_BUDGET_EXCEEDED" in budget_blocked.reason_codes


def test_model_selector_blocks_unhealthy_provider_or_policy_mismatch() -> None:
    decision = select_model_candidate(
        _active_policy(),
        load_baseline_manifest(),
        ModelSelectionRequest(
            request_id="req-5b",
            task_type="normal_feature",
            task_class=TaskClass.MODERATE,
            criticality=TaskCriticality.MEDIUM,
            authority_ceiling=ModelAuthorityCeiling.ADVISORY_ONLY,
            privacy_class="LOCAL_ONLY",
            preferred_tier=ModelTier.BALANCED,
            provider_status=ProviderRoutingStatus.DEGRADED,
            required_policy_version="policy-v2",
        ),
    )

    assert decision.outcome is ModelSelectionOutcome.DATA_UNAVAILABLE
    assert "PROVIDER_HEALTH_NOT_READY" in decision.reason_codes
    assert "POLICY_VERSION_MISMATCH" in decision.reason_codes


def test_model_selection_decision_and_invocation_remain_fail_closed() -> None:
    decision = ModelSelectionDecision(
        request_id="req-6",
        task_type="documentation",
        outcome=ModelSelectionOutcome.DATA_UNAVAILABLE,
        policy_version="policy-v1",
        classifier_version="classifier-v1",
        model_registry_version="registry-v1",
        authority_ceiling=ModelAuthorityCeiling.REPORT_ONLY,
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
        candidate_evidence=(
            ModelCapabilityEvidence(
                tier=ModelTier.ECONOMY,
                model_id="gpt-economy",
                available=True,
                eligible=False,
                matched_requirements=(),
                blockers=("REASONING_UNSUPPORTED",),
            ),
        ),
    )
    invocation = ModelInvocationEvidence(
        request_id="req-6",
        task_type="documentation",
        policy_version="policy-v1",
        authority_ceiling=ModelAuthorityCeiling.REPORT_ONLY,
        privacy_class="LOCAL_ONLY",
        structured_output_requirement=StructuredOutputRequirement.REQUIRED,
        provider_status=ProviderRoutingStatus.READY,
        model_id="gpt-balanced",
        model_tier=ModelTier.BALANCED,
        reasoning_effort=ReasoningEffort.MEDIUM,
        token_accounting_source=TokenAccountingSource.EXACT_PROVIDER,
        total_tokens=2_000,
        fallback_used=False,
        output_schema_validated=True,
        actual_cost_usd=Decimal("0.02"),
    )

    assert decision.execution_allowed is False
    assert invocation.execution_allowed is False
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(invocation, execution_allowed=True)
    with pytest.raises(ValueError, match="validated output schema"):
        replace(
            invocation,
            structured_output_requirement=StructuredOutputRequirement.REQUIRED,
            output_schema_validated=False,
        )

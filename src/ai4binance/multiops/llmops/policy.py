"""Bounded, versioned policy loading for observe-only Codex governance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

from ai4binance.multiops.llmops.contracts import (
    ModelTier,
    ReasoningEffort,
    TaskClass,
    TaskCriticality,
    TokenAccountingSource,
)

MAX_POLICY_BYTES = 64 * 1024
REQUIRED_BASELINE_TASK_TYPES = frozenset(
    {
        "architecture_review",
        "documentation",
        "integration_tests",
        "normal_feature",
        "refactoring",
        "repository_discovery",
        "risk_engine_review",
        "security_review",
        "simple_bug_fix",
        "unit_tests",
    }
)


class EnforcementMode(StrEnum):
    OBSERVE_ONLY = "OBSERVE_ONLY"
    ENFORCE = "ENFORCE"


class ModelAuthorityCeiling(StrEnum):
    ADVISORY_ONLY = "ADVISORY_ONLY"
    REPORT_ONLY = "REPORT_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class ModelRoutingCapability(StrEnum):
    LONG_CONTEXT = "LONG_CONTEXT"
    LARGE_OUTPUT = "LARGE_OUTPUT"
    VERIFIED_PRICING = "VERIFIED_PRICING"
    CACHED_INPUT_PRICING = "CACHED_INPUT_PRICING"


class ModelContextRequirement(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    REPOSITORY_CONTEXT = "REPOSITORY_CONTEXT"
    EXTENDED_REPOSITORY_CONTEXT = "EXTENDED_REPOSITORY_CONTEXT"


class StructuredOutputRequirement(StrEnum):
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class ProviderRoutingStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ModelSelectionOutcome(StrEnum):
    SELECTED = "SELECTED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    soft_limit: int | None
    hard_limit: int | None

    def __post_init__(self) -> None:
        for value in (self.soft_limit, self.hard_limit):
            if value is not None and value < 1:
                raise ValueError("configured token budget limits must be positive")
        if (
            self.soft_limit is not None
            and self.hard_limit is not None
            and self.soft_limit > self.hard_limit
        ):
            raise ValueError("token budget soft limit cannot exceed hard limit")


@dataclass(frozen=True, slots=True)
class SelectionResourceBudget:
    max_context_files: int | None = None
    max_context_bytes: int | None = None
    max_parallel_invocations: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("max context files", self.max_context_files),
            ("max context bytes", self.max_context_bytes),
            ("max parallel invocations", self.max_parallel_invocations),
        ):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive when provided")
        if self.max_parallel_invocations != 1:
            raise ValueError("model routing must remain single-invocation bounded")


@dataclass(frozen=True, slots=True)
class PricingSource:
    provider: str
    currency: str
    pricing_as_of: date | None
    manually_verified: bool

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.currency.strip():
            raise ValueError("pricing source identity is required")
        if self.currency != "USD":
            raise ValueError("model governance currently supports USD pricing only")
        if self.manually_verified and self.pricing_as_of is None:
            raise ValueError("verified pricing requires pricing_as_of")

    @property
    def status(self) -> str:
        if not self.manually_verified or self.pricing_as_of is None:
            return "PRICING_DATA_STALE"
        return "READY"


@dataclass(frozen=True, slots=True)
class ModelCandidatePolicy:
    tier: ModelTier
    model_id: str | None
    available: bool
    reasoning_levels: tuple[ReasoningEffort, ...]
    context_window: int | None
    max_output: int | None
    input_per_million: Decimal | None
    cached_input_per_million: Decimal | None
    output_per_million: Decimal | None

    def __post_init__(self) -> None:
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("model id cannot be blank")
        if len(set(self.reasoning_levels)) != len(self.reasoning_levels):
            raise ValueError("model reasoning levels must be unique")
        for value in (self.context_window, self.max_output):
            if value is not None and value < 1:
                raise ValueError("model token limits must be positive")
        rates = (
            self.input_per_million,
            self.cached_input_per_million,
            self.output_per_million,
        )
        if any(
            value is not None and (not value.is_finite() or value < 0)
            for value in rates
        ):
            raise ValueError("model prices must be finite and non-negative")
        if self.available and (
            self.model_id is None
            or not self.reasoning_levels
            or self.context_window is None
            or self.max_output is None
        ):
            raise ValueError("available model requires verified capability metadata")
        if (
            self.cached_input_per_million is not None
            and self.input_per_million is not None
            and self.cached_input_per_million > self.input_per_million
        ):
            raise ValueError("cached input price cannot exceed input price")

    @property
    def availability(self) -> bool:
        return self.available


@dataclass(frozen=True, slots=True)
class TaskRoutingProfile:
    """Non-authoritative task-to-tier guidance; provider identity stays unverified."""

    profile_id: str
    tier: ModelTier
    task_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.task_types:
            raise ValueError(
                "task routing profile identity and task types are required"
            )
        if len(set(self.task_types)) != len(self.task_types) or any(
            not task_type.strip() for task_type in self.task_types
        ):
            raise ValueError(
                "task routing profile task types must be unique and nonblank"
            )


@dataclass(frozen=True, slots=True)
class ModelGovernancePolicy:
    schema_version: str
    policy_version: str
    classifier_version: str
    model_registry_version: str
    pricing_version: str
    enforcement_mode: EnforcementMode
    pricing_source: PricingSource
    budgets: tuple[tuple[str, BudgetLimit], ...]
    models: tuple[ModelCandidatePolicy, ...]
    execution_allowed: bool
    promotion_status: str
    live_eligibility_status: str
    task_routing: tuple[TaskRoutingProfile, ...] = ()

    def __post_init__(self) -> None:
        versions = (
            self.schema_version,
            self.policy_version,
            self.classifier_version,
            self.model_registry_version,
            self.pricing_version,
        )
        if any(not value.strip() for value in versions):
            raise ValueError("model governance versions are required")
        expected_periods = {"per_task", "daily", "weekly", "monthly"}
        periods = {name for name, _ in self.budgets}
        if periods != expected_periods or len(periods) != len(self.budgets):
            raise ValueError("model governance budgets must cover each period once")
        tiers = tuple(model.tier for model in self.models)
        if set(tiers) != set(ModelTier) or len(tiers) != len(set(tiers)):
            raise ValueError("model governance registry must cover every tier once")
        if self.enforcement_mode is EnforcementMode.ENFORCE and any(
            limit.hard_limit is None for _, limit in self.budgets
        ):
            raise ValueError("budget enforcement requires every hard limit")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model governance policy cannot authorize execution")

    @property
    def pricing_status(self) -> str:
        return self.pricing_source.status

    def recommended_tier(self, task_type: str) -> ModelTier | None:
        """Return deterministic tier guidance without authorizing invocation."""

        for profile in self.task_routing:
            if task_type in profile.task_types:
                return profile.tier
        return None


@dataclass(frozen=True, slots=True)
class BaselineTaskDefinition:
    task_id: str
    task_type: str
    description: str
    validation_commands: tuple[str, ...]
    mutates_trading_core: bool
    live_execution: bool

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.task_id, self.task_type, self.description)
        ):
            raise ValueError("baseline task identity is required")
        if not self.validation_commands or any(
            not command.strip() for command in self.validation_commands
        ):
            raise ValueError("baseline task requires validation commands")
        if self.mutates_trading_core or self.live_execution:
            raise ValueError("baseline task cannot mutate trading or execute live")


@dataclass(frozen=True, slots=True)
class BaselineManifest:
    schema_version: str
    manifest_version: str
    status: str
    token_source_required: str
    missing_data_status: str
    tasks: tuple[BaselineTaskDefinition, ...]
    execution_allowed: bool
    promotion_status: str
    live_eligibility_status: str

    def __post_init__(self) -> None:
        if not self.schema_version.strip() or not self.manifest_version.strip():
            raise ValueError("baseline manifest versions are required")
        if self.status != "BASELINE_REQUIRED":
            raise ValueError("unmeasured baseline must remain BASELINE_REQUIRED")
        if self.token_source_required != "EXACT_PROVIDER":  # nosec B105  # noqa: S105
            raise ValueError("baseline requires exact provider token accounting")
        if self.missing_data_status != "DATA_UNAVAILABLE":
            raise ValueError("missing baseline observations must be DATA_UNAVAILABLE")
        task_ids = tuple(task.task_id for task in self.tasks)
        task_types = {task.task_type for task in self.tasks}
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("baseline task ids must be unique")
        missing = REQUIRED_BASELINE_TASK_TYPES - task_types
        if missing:
            raise ValueError(
                f"baseline manifest is missing task types: {sorted(missing)}"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("baseline manifest cannot authorize execution")


@dataclass(frozen=True, slots=True)
class ModelSelectionRequest:
    request_id: str
    task_type: str
    task_class: TaskClass
    criticality: TaskCriticality
    authority_ceiling: ModelAuthorityCeiling
    privacy_class: str
    preferred_tier: ModelTier
    context_requirement: ModelContextRequirement = ModelContextRequirement.LOCAL_ONLY
    structured_output_requirement: StructuredOutputRequirement = (
        StructuredOutputRequirement.OPTIONAL
    )
    provider_status: ProviderRoutingStatus = ProviderRoutingStatus.READY
    required_policy_version: str | None = None
    allowed_fallback_tiers: tuple[ModelTier, ...] = ()
    required_reasoning: ReasoningEffort | None = None
    required_capabilities: tuple[ModelRoutingCapability, ...] = ()
    minimum_context_window: int | None = None
    minimum_max_output: int | None = None
    requested_total_tokens: int | None = None
    resource_budget: SelectionResourceBudget = SelectionResourceBudget()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.task_type.strip():
            raise ValueError("model selection request identity is required")
        if not self.privacy_class.strip():
            raise ValueError("model selection privacy class is required")
        if (
            self.required_policy_version is not None
            and not self.required_policy_version.strip()
        ):
            raise ValueError("required policy version cannot be blank")
        if len(set(self.allowed_fallback_tiers)) != len(self.allowed_fallback_tiers):
            raise ValueError("model selection fallback tiers must be unique")
        if self.preferred_tier in self.allowed_fallback_tiers:
            raise ValueError(
                "model selection fallback tiers cannot repeat the preferred tier"
            )
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("model selection required capabilities must be unique")
        for name, value in (
            ("minimum context window", self.minimum_context_window),
            ("minimum max output", self.minimum_max_output),
            ("requested total tokens", self.requested_total_tokens),
        ):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive when provided")
        if (
            self.context_requirement is not ModelContextRequirement.LOCAL_ONLY
            and self.minimum_context_window is None
        ):
            raise ValueError(
                "non-local context routing requires minimum context window"
            )
        if (
            self.structured_output_requirement is StructuredOutputRequirement.REQUIRED
            and self.minimum_max_output is None
        ):
            raise ValueError("structured output routing requires minimum max output")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model selection request cannot authorize execution")

    @property
    def provider_health(self) -> ProviderRoutingStatus:
        return self.provider_status

    @property
    def token_budget(self) -> int | None:
        return self.requested_total_tokens


@dataclass(frozen=True, slots=True)
class ModelCapabilityEvidence:
    tier: ModelTier
    model_id: str | None
    available: bool
    eligible: bool
    matched_requirements: tuple[str, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("model capability evidence model id cannot be blank")
        if len(set(self.matched_requirements)) != len(self.matched_requirements) or any(
            not item.strip() for item in self.matched_requirements
        ):
            raise ValueError(
                "model capability evidence matched requirements must be unique"
            )
        if len(set(self.blockers)) != len(self.blockers) or any(
            not item.strip() for item in self.blockers
        ):
            raise ValueError("model capability evidence blockers must be unique")
        if self.eligible == bool(self.blockers):
            raise ValueError("model capability evidence eligibility disagrees")

    @property
    def availability(self) -> bool:
        return self.available


@dataclass(frozen=True, slots=True)
class ModelSelectionDecision:
    request_id: str
    task_type: str
    outcome: ModelSelectionOutcome
    policy_version: str
    classifier_version: str
    model_registry_version: str
    authority_ceiling: ModelAuthorityCeiling
    privacy_class: str
    context_requirement: ModelContextRequirement
    structured_output_requirement: StructuredOutputRequirement
    provider_status: ProviderRoutingStatus
    selected_tier: ModelTier | None
    selected_model_id: str | None
    selected_reasoning: ReasoningEffort | None
    used_fallback: bool
    fallback_from_tier: ModelTier | None
    reason_codes: tuple[str, ...]
    candidate_evidence: tuple[ModelCapabilityEvidence, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.task_type.strip():
            raise ValueError("model selection decision identity is required")
        if not self.policy_version.strip():
            raise ValueError("model selection decision policy version is required")
        if not self.privacy_class.strip():
            raise ValueError("model selection decision privacy class is required")
        if len(set(self.reason_codes)) != len(self.reason_codes) or any(
            not item.strip() for item in self.reason_codes
        ):
            raise ValueError("model selection decision reason codes must be unique")
        if not self.candidate_evidence:
            raise ValueError("model selection decision requires candidate evidence")
        if self.outcome is ModelSelectionOutcome.SELECTED:
            if (
                self.selected_tier is None
                or self.selected_model_id is None
                or self.selected_reasoning is None
            ):
                raise ValueError(
                    "selected model decision requires tier model and reasoning"
                )
        elif any(
            value is not None
            for value in (
                self.selected_tier,
                self.selected_model_id,
                self.selected_reasoning,
                self.fallback_from_tier,
            )
        ):
            raise ValueError(
                "data unavailable decision cannot carry selected model details"
            )
        if not self.used_fallback and self.fallback_from_tier is not None:
            raise ValueError("non-fallback decision cannot carry fallback source")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model selection decision cannot authorize execution")

    @property
    def provider_health(self) -> ProviderRoutingStatus:
        return self.provider_status


@dataclass(frozen=True, slots=True)
class ModelInvocationEvidence:
    request_id: str
    task_type: str
    policy_version: str
    authority_ceiling: ModelAuthorityCeiling
    privacy_class: str
    structured_output_requirement: StructuredOutputRequirement
    provider_status: ProviderRoutingStatus
    model_id: str
    model_tier: ModelTier
    reasoning_effort: ReasoningEffort
    token_accounting_source: TokenAccountingSource
    total_tokens: int | None
    fallback_used: bool
    output_schema_validated: bool
    blockers: tuple[str, ...] = ()
    actual_cost_usd: Decimal | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for name, value in (
            ("model invocation request id", self.request_id),
            ("model invocation task type", self.task_type),
            ("model invocation policy version", self.policy_version),
            ("model invocation privacy class", self.privacy_class),
            ("model invocation model id", self.model_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if self.total_tokens is not None and self.total_tokens < 0:
            raise ValueError("model invocation total tokens cannot be negative")
        if len(set(self.blockers)) != len(self.blockers) or any(
            not item.strip() for item in self.blockers
        ):
            raise ValueError("model invocation blockers must be unique")
        if self.actual_cost_usd is not None and (
            not self.actual_cost_usd.is_finite() or self.actual_cost_usd < 0
        ):
            raise ValueError("model invocation cost must be finite and non-negative")
        if (
            self.structured_output_requirement is StructuredOutputRequirement.REQUIRED
            and not self.output_schema_validated
        ):
            raise ValueError(
                "structured output invocations require validated output schema"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model invocation evidence cannot authorize execution")

    @property
    def provider_health(self) -> ProviderRoutingStatus:
        return self.provider_status


ModelCandidate = ModelCandidatePolicy


@dataclass(frozen=True, slots=True)
class ModelSelectionGateway:
    policy: ModelGovernancePolicy
    baseline_manifest: BaselineManifest

    def route(self, request: ModelSelectionRequest) -> ModelSelectionDecision:
        return select_model_candidate(self.policy, self.baseline_manifest, request)


def select_model_candidate(
    policy: ModelGovernancePolicy,
    baseline_manifest: BaselineManifest,
    request: ModelSelectionRequest,
) -> ModelSelectionDecision:
    global_reasons: list[str] = []
    registered_task_types = {task.task_type for task in baseline_manifest.tasks}
    if request.task_type not in registered_task_types:
        global_reasons.append("TASK_TYPE_UNREGISTERED")
    if (
        request.required_policy_version is not None
        and request.required_policy_version != policy.policy_version
    ):
        global_reasons.append("POLICY_VERSION_MISMATCH")
    if request.provider_status is not ProviderRoutingStatus.READY:
        global_reasons.append("PROVIDER_HEALTH_NOT_READY")
    per_task_budget = dict(policy.budgets)["per_task"]
    if (
        request.requested_total_tokens is not None
        and per_task_budget.hard_limit is not None
        and request.requested_total_tokens > per_task_budget.hard_limit
    ):
        global_reasons.append("TOKEN_BUDGET_EXCEEDED")
    elif (
        request.requested_total_tokens is not None
        and per_task_budget.soft_limit is not None
        and request.requested_total_tokens > per_task_budget.soft_limit
    ):
        global_reasons.append("TOKEN_BUDGET_WARNING")

    evidence_by_tier = {
        model.tier: _assess_model_candidate(policy, model, request, global_reasons)
        for model in policy.models
    }
    selection_order = (request.preferred_tier, *request.allowed_fallback_tiers)
    for tier in selection_order:
        candidate = evidence_by_tier[tier]
        if candidate.eligible:
            model = next(item for item in policy.models if item.tier is tier)
            return ModelSelectionDecision(
                request_id=request.request_id,
                task_type=request.task_type,
                outcome=ModelSelectionOutcome.SELECTED,
                policy_version=policy.policy_version,
                classifier_version=policy.classifier_version,
                model_registry_version=policy.model_registry_version,
                authority_ceiling=request.authority_ceiling,
                privacy_class=request.privacy_class,
                context_requirement=request.context_requirement,
                structured_output_requirement=request.structured_output_requirement,
                provider_status=request.provider_status,
                selected_tier=tier,
                selected_model_id=model.model_id,
                selected_reasoning=_selected_reasoning(model, request),
                used_fallback=tier is not request.preferred_tier,
                fallback_from_tier=(
                    request.preferred_tier
                    if tier is not request.preferred_tier
                    else None
                ),
                reason_codes=tuple(dict.fromkeys(global_reasons)),
                candidate_evidence=tuple(
                    evidence_by_tier[item.tier] for item in policy.models
                ),
            )

    return ModelSelectionDecision(
        request_id=request.request_id,
        task_type=request.task_type,
        outcome=ModelSelectionOutcome.DATA_UNAVAILABLE,
        policy_version=policy.policy_version,
        classifier_version=policy.classifier_version,
        model_registry_version=policy.model_registry_version,
        authority_ceiling=request.authority_ceiling,
        privacy_class=request.privacy_class,
        context_requirement=request.context_requirement,
        structured_output_requirement=request.structured_output_requirement,
        provider_status=request.provider_status,
        selected_tier=None,
        selected_model_id=None,
        selected_reasoning=None,
        used_fallback=False,
        fallback_from_tier=None,
        reason_codes=tuple(
            dict.fromkeys(
                (
                    *global_reasons,
                    "NO_POLICY_COMPATIBLE_MODEL",
                )
            )
        ),
        candidate_evidence=tuple(evidence_by_tier[item.tier] for item in policy.models),
    )


def route_model_selection_request(
    policy: ModelGovernancePolicy,
    baseline_manifest: BaselineManifest,
    request: ModelSelectionRequest,
) -> ModelSelectionDecision:
    """Deterministic gateway for policy-compatible provider/model routing."""

    return ModelSelectionGateway(policy, baseline_manifest).route(request)


def default_model_governance_policy_path(
    repository_root: Path | None = None,
) -> Path:
    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "governance" / "codex_model_governance.yaml"


def default_baseline_manifest_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "governance" / "codex_benchmark_tasks.yaml"


def load_model_governance_policy(path: Path | None = None) -> ModelGovernancePolicy:
    payload = _load_yaml_mapping(path or default_model_governance_policy_path())
    _require_keys(
        payload,
        {
            "schema_version",
            "policy_version",
            "classifier_version",
            "model_registry_version",
            "pricing_version",
            "enforcement_mode",
            "pricing_source",
            "token_governance",
            "models",
            "authority",
            "task_routing",
        },
        "model governance policy",
    )
    pricing = _mapping(payload["pricing_source"], "pricing source")
    _require_keys(
        pricing,
        {"provider", "currency", "pricing_as_of", "manually_verified"},
        "pricing source",
    )
    token_governance = _mapping(payload["token_governance"], "token governance")
    _require_keys(token_governance, {"enabled", "budgets"}, "token governance")
    if token_governance["enabled"] is not True:
        raise ValueError("token governance must remain enabled")
    budgets = _mapping(token_governance["budgets"], "token budgets")
    parsed_budgets = tuple(
        (name, _budget_limit(budgets.get(name), name))
        for name in ("per_task", "daily", "weekly", "monthly")
    )
    if set(budgets) != {name for name, _ in parsed_budgets}:
        raise ValueError("token budgets contain unknown periods")
    models = _mapping(payload["models"], "model registry")
    if set(models) != {tier.value.lower() for tier in ModelTier}:
        raise ValueError("model registry must define every model tier")
    parsed_models = tuple(
        _model_policy(tier, models[tier.value.lower()]) for tier in ModelTier
    )
    authority = _mapping(payload["authority"], "authority")
    _require_keys(
        authority,
        {"execution_allowed", "promotion_status", "live_eligibility_status"},
        "authority",
    )
    task_routing_raw = _mapping(payload["task_routing"], "task routing")
    parsed_task_routing = tuple(
        TaskRoutingProfile(
            profile_id=profile_id,
            tier=ModelTier(str(value["tier"])),
            task_types=tuple(
                str(item) for item in _sequence(value["task_types"], "task types")
            ),
        )
        for profile_id, raw_value in task_routing_raw.items()
        for value in (_mapping(raw_value, "task routing profile"),)
    )
    routed_task_types = [
        task_type for profile in parsed_task_routing for task_type in profile.task_types
    ]
    if len(routed_task_types) != len(set(routed_task_types)):
        raise ValueError("task routing task types must be unique")
    return ModelGovernancePolicy(
        schema_version=str(payload["schema_version"]),
        policy_version=str(payload["policy_version"]),
        classifier_version=str(payload["classifier_version"]),
        model_registry_version=str(payload["model_registry_version"]),
        pricing_version=str(payload["pricing_version"]),
        enforcement_mode=EnforcementMode(str(payload["enforcement_mode"])),
        pricing_source=PricingSource(
            provider=str(pricing["provider"]),
            currency=str(pricing["currency"]),
            pricing_as_of=_optional_date(pricing["pricing_as_of"]),
            manually_verified=_bool(pricing["manually_verified"], "manually_verified"),
        ),
        budgets=parsed_budgets,
        models=parsed_models,
        execution_allowed=_bool(authority["execution_allowed"], "execution_allowed"),
        promotion_status=str(authority["promotion_status"]),
        live_eligibility_status=str(authority["live_eligibility_status"]),
        task_routing=parsed_task_routing,
    )


def load_baseline_manifest(path: Path | None = None) -> BaselineManifest:
    payload = _load_yaml_mapping(path or default_baseline_manifest_path())
    _require_keys(
        payload,
        {
            "schema_version",
            "manifest_version",
            "status",
            "token_source_required",
            "missing_data_status",
            "tasks",
            "authority",
        },
        "baseline manifest",
    )
    tasks = _sequence(payload["tasks"], "baseline tasks")
    parsed_tasks: list[BaselineTaskDefinition] = []
    for raw_task in tasks:
        task = _mapping(raw_task, "baseline task")
        _require_keys(
            task,
            {
                "task_id",
                "task_type",
                "description",
                "validation_commands",
                "mutates_trading_core",
                "live_execution",
            },
            "baseline task",
        )
        parsed_tasks.append(
            BaselineTaskDefinition(
                task_id=str(task["task_id"]),
                task_type=str(task["task_type"]),
                description=str(task["description"]),
                validation_commands=_strings(
                    task["validation_commands"], "validation commands"
                ),
                mutates_trading_core=_bool(
                    task["mutates_trading_core"], "mutates_trading_core"
                ),
                live_execution=_bool(task["live_execution"], "live_execution"),
            )
        )
    authority = _mapping(payload["authority"], "baseline authority")
    _require_keys(
        authority,
        {"execution_allowed", "promotion_status", "live_eligibility_status"},
        "baseline authority",
    )
    return BaselineManifest(
        schema_version=str(payload["schema_version"]),
        manifest_version=str(payload["manifest_version"]),
        status=str(payload["status"]),
        token_source_required=str(payload["token_source_required"]),
        missing_data_status=str(payload["missing_data_status"]),
        tasks=tuple(parsed_tasks),
        execution_allowed=_bool(authority["execution_allowed"], "execution_allowed"),
        promotion_status=str(authority["promotion_status"]),
        live_eligibility_status=str(authority["live_eligibility_status"]),
    )


def _model_policy(tier: ModelTier, value: object) -> ModelCandidatePolicy:
    payload = _mapping(value, f"{tier.value} model")
    expected = {
        "model_id",
        "available",
        "reasoning_levels",
        "context_window",
        "max_output",
        "input_per_million",
        "cached_input_per_million",
        "output_per_million",
    }
    _require_keys(payload, expected, f"{tier.value} model")
    return ModelCandidatePolicy(
        tier=tier,
        model_id=_optional_text(payload["model_id"]),
        available=_bool(payload["available"], "model available"),
        reasoning_levels=tuple(
            ReasoningEffort(item)
            for item in _strings(payload["reasoning_levels"], "reasoning levels")
        ),
        context_window=_optional_int(payload["context_window"], "context window"),
        max_output=_optional_int(payload["max_output"], "max output"),
        input_per_million=_optional_decimal(payload["input_per_million"]),
        cached_input_per_million=_optional_decimal(payload["cached_input_per_million"]),
        output_per_million=_optional_decimal(payload["output_per_million"]),
    )


def _assess_model_candidate(
    policy: ModelGovernancePolicy,
    model: ModelCandidatePolicy,
    request: ModelSelectionRequest,
    global_reasons: Sequence[str],
) -> ModelCapabilityEvidence:
    blockers = list(global_reasons)
    matched: list[str] = []
    if not model.available:
        blockers.append("MODEL_UNAVAILABLE")
    else:
        matched.append("MODEL_AVAILABLE")
    if request.required_reasoning is not None:
        if request.required_reasoning not in model.reasoning_levels:
            blockers.append("REASONING_UNSUPPORTED")
        else:
            matched.append(f"REASONING:{request.required_reasoning.value}")
    if request.minimum_context_window is not None:
        if (
            model.context_window is None
            or model.context_window < request.minimum_context_window
        ):
            blockers.append("CONTEXT_WINDOW_INSUFFICIENT")
        else:
            matched.append("LONG_CONTEXT")
    if request.minimum_max_output is not None:
        if model.max_output is None or model.max_output < request.minimum_max_output:
            blockers.append("MAX_OUTPUT_INSUFFICIENT")
        else:
            matched.append("LARGE_OUTPUT")
    for capability in request.required_capabilities:
        if capability is ModelRoutingCapability.VERIFIED_PRICING:
            if policy.pricing_status != "READY" or any(
                value is None
                for value in (
                    model.input_per_million,
                    model.output_per_million,
                )
            ):
                blockers.append("VERIFIED_PRICING_REQUIRED")
            else:
                matched.append(capability.value)
        elif capability is ModelRoutingCapability.CACHED_INPUT_PRICING:
            if model.cached_input_per_million is None:
                blockers.append("CACHED_INPUT_PRICING_REQUIRED")
            else:
                matched.append(capability.value)
        elif capability is ModelRoutingCapability.LONG_CONTEXT:
            if model.context_window is None:
                blockers.append("LONG_CONTEXT_REQUIRED")
            else:
                matched.append(capability.value)
        elif capability is ModelRoutingCapability.LARGE_OUTPUT:
            if model.max_output is None:
                blockers.append("LARGE_OUTPUT_REQUIRED")
            else:
                matched.append(capability.value)
    return ModelCapabilityEvidence(
        tier=model.tier,
        model_id=model.model_id,
        available=model.available,
        eligible=not blockers,
        matched_requirements=tuple(dict.fromkeys(matched)),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _selected_reasoning(
    model: ModelCandidatePolicy,
    request: ModelSelectionRequest,
) -> ReasoningEffort:
    if request.required_reasoning is not None:
        return request.required_reasoning
    if not model.reasoning_levels:
        raise ValueError("selected model must expose at least one reasoning level")
    return model.reasoning_levels[-1]


def _budget_limit(value: object, name: str) -> BudgetLimit:
    payload = _mapping(value, f"{name} budget")
    _require_keys(payload, {"soft_limit", "hard_limit"}, f"{name} budget")
    return BudgetLimit(
        soft_limit=_optional_int(payload["soft_limit"], f"{name} soft limit"),
        hard_limit=_optional_int(payload["hard_limit"], f"{name} hard limit"),
    )


def _load_yaml_mapping(path: Path) -> Mapping[str, object]:
    resolved = path.resolve()
    if resolved.stat().st_size > MAX_POLICY_BYTES:
        raise ValueError("model governance YAML exceeds bounded size")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return _mapping(raw, "model governance YAML")


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    return cast(Sequence[object], value)


def _strings(value: object, name: str) -> tuple[str, ...]:
    values = tuple(str(item) for item in _sequence(value, name))
    if any(not item.strip() for item in values) or len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique nonblank strings")
    return values


def _require_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{name} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        raise ValueError("optional text cannot be blank")
    return text


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer or null")
    return value


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("model price must be decimal-compatible or null")
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("model price must be decimal-compatible or null") from error


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError("pricing_as_of must be ISO date or null") from error

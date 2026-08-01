"""Typed fail-closed contracts for the MultiOps control plane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class OpsDomain(StrEnum):
    AIOPS = "AIOPS"
    MLOPS = "MLOPS"
    LLMOPS = "LLMOPS"
    RAGOPS = "RAGOPS"
    AGENTOPS = "AGENTOPS"
    DATAOPS = "DATAOPS"
    DEVSECOPS = "DEVSECOPS"
    TRADEOPS = "TRADEOPS"


class OpsCapability(StrEnum):
    HEALTH = "HEALTH"
    INCIDENT = "INCIDENT"
    ALERT_CORRELATION = "ALERT_CORRELATION"
    SAFE_RUNBOOKS = "SAFE_RUNBOOKS"
    DATASET_REGISTRY = "DATASET_REGISTRY"
    FEATURE_REGISTRY = "FEATURE_REGISTRY"
    MODEL_REGISTRY = "MODEL_REGISTRY"
    DRIFT = "DRIFT"
    PROMOTION = "PROMOTION"
    PROMPT_REGISTRY = "PROMPT_REGISTRY"
    MODEL_ROUTING = "MODEL_ROUTING"
    EVAL = "EVAL"
    GROUNDING = "GROUNDING"
    TOKEN_LATENCY = "TOKEN_LATENCY"  # nosec B105  # noqa: S105
    CORPUS_VERSION = "CORPUS_VERSION"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    RETRIEVAL_QUALITY = "RETRIEVAL_QUALITY"
    SOURCE_LINEAGE = "SOURCE_LINEAGE"
    AGENT_REGISTRY = "AGENT_REGISTRY"
    ROLE_DRIFT = "ROLE_DRIFT"
    LOOP_BUDGET = "LOOP_BUDGET"
    TOOL_AUTHORIZATION = "TOOL_AUTHORIZATION"
    AGENT_RETIREMENT = "AGENT_RETIREMENT"
    FRESHNESS = "FRESHNESS"
    RECONCILIATION = "RECONCILIATION"
    QUALITY = "QUALITY"
    DATASET_LINEAGE = "DATASET_LINEAGE"
    CI = "CI"
    TESTS = "TESTS"
    SECRET_SCANNING = "SECRET_SCANNING"  # nosec B105  # noqa: S105
    RELEASE_GATES = "RELEASE_GATES"
    PAPER_LIFECYCLE = "PAPER_LIFECYCLE"
    ORDER_INTENT = "ORDER_INTENT"
    EXECUTION_BLOCKERS = "EXECUTION_BLOCKERS"
    CLOSURE_REVIEW = "CLOSURE_REVIEW"


class OpsVerdict(StrEnum):
    PASSED = "PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BLOCKED = "BLOCKED"


class OpsBlocker(StrEnum):
    UNKNOWN_DOMAIN = "MULTIOPS_UNKNOWN_DOMAIN"
    CAPABILITY_OUT_OF_SCOPE = "MULTIOPS_CAPABILITY_OUT_OF_SCOPE"
    EVIDENCE_REQUIRED = "MULTIOPS_EVIDENCE_REQUIRED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    LIVE_BLOCKED = "LIVE_ORDER_BLOCKED"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_unique_capabilities(values: tuple[OpsCapability, ...]) -> None:
    if not values:
        raise ValueError("ops domain capabilities cannot be empty")
    if len(set(values)) != len(values):
        raise ValueError("ops domain capabilities must be unique")


def _require_fail_closed(
    *,
    execution_allowed: bool,
    promotion_status: str,
    live_eligibility_status: str,
    label: str,
) -> None:
    if execution_allowed:
        raise ValueError(f"{label} cannot authorize execution")
    if promotion_status != "RESEARCH_ONLY":
        raise ValueError(f"{label} cannot promote production state")
    if live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError(f"{label} must remain live blocked")


@dataclass(frozen=True, slots=True)
class OpsDomainDefinition:
    domain: OpsDomain
    display_name: str
    purpose: str
    capabilities: tuple[OpsCapability, ...]
    owner_department_id: str = "MULTI_OPS"
    independent_control: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("ops domain display name", self.display_name)
        _require_text("ops domain purpose", self.purpose)
        _require_text("ops domain owner department", self.owner_department_id)
        _require_unique_capabilities(self.capabilities)
        if not self.independent_control:
            raise ValueError("ops domain must remain an independent control")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="ops domain",
        )


@dataclass(frozen=True, slots=True)
class OpsControlPlanePolicy:
    max_parallel_checks: int = 4
    evidence_required: bool = True
    external_writes_allowed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not 1 <= self.max_parallel_checks <= 8:
            raise ValueError("ops max_parallel_checks must stay bounded")
        if not self.evidence_required:
            raise ValueError("ops checks must require evidence")
        if self.external_writes_allowed:
            raise ValueError("ops control plane cannot allow external writes")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="ops policy",
        )


@dataclass(frozen=True, slots=True)
class OpsCheckResult:
    check_id: str
    domain: OpsDomain
    capability: OpsCapability
    subject_ref: str
    verdict: OpsVerdict
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    next_actions: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("ops check id", self.check_id)
        _require_text("ops check subject", self.subject_ref)
        _require_unique_text("ops evidence refs", self.evidence_refs)
        _require_unique_text("ops blockers", self.blockers)
        _require_unique_text("ops next actions", self.next_actions)
        if self.verdict is OpsVerdict.PASSED and self.blockers:
            raise ValueError("passed ops check cannot have blockers")
        if self.verdict is not OpsVerdict.PASSED and not self.blockers:
            raise ValueError("unfinished ops check requires blockers")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="ops check result",
        )


@dataclass(frozen=True, slots=True)
class MultiOpsRegistry:
    domains: tuple[OpsDomainDefinition, ...]
    _by_domain: Mapping[OpsDomain, OpsDomainDefinition] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.domains:
            raise ValueError("multiops registry cannot be empty")
        by_domain = {definition.domain: definition for definition in self.domains}
        if len(by_domain) != len(self.domains):
            raise ValueError("multiops domains must be unique")
        missing = set(OpsDomain).difference(by_domain)
        if missing:
            raise ValueError("multiops registry must cover every ops domain")
        object.__setattr__(self, "_by_domain", MappingProxyType(by_domain))

    def get(self, domain: OpsDomain) -> OpsDomainDefinition:
        return self._by_domain[domain]

    def capabilities_for(self, domain: OpsDomain) -> tuple[OpsCapability, ...]:
        return self.get(domain).capabilities

    def validate_capability(
        self,
        *,
        domain: OpsDomain,
        capability: OpsCapability,
    ) -> OpsDomainDefinition:
        definition = self.get(domain)
        if capability not in definition.capabilities:
            raise ValueError("ops capability is outside domain scope")
        return definition

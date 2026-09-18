"""Immutable agent definitions and dependency registry."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ai4binance.schemas import PromotionStatus


class AgentStage(StrEnum):
    """Dependency-aware platform stages."""

    ACQUISITION = "ACQUISITION"
    ELIGIBILITY = "ELIGIBILITY"
    ANALYSIS = "ANALYSIS"
    SYNTHESIS = "SYNTHESIS"
    RISK = "RISK"
    VALIDATION = "VALIDATION"
    EXECUTION = "EXECUTION"
    RESEARCH = "RESEARCH"
    LEARNING = "LEARNING"


class CapabilityExecutionClass(StrEnum):
    """Current bounded runtime lane for an analytical capability."""

    DETERMINISTIC_THREAD_POOL = "DETERMINISTIC_THREAD_POOL"


class CapabilityActivationPolicy(StrEnum):
    """Current scheduler admission policy for an analytical capability."""

    ALWAYS_SCHEDULED = "ALWAYS_SCHEDULED"


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Legacy-compatible declaration for a platform component or capability."""

    name: str
    family: str
    version: str
    stage: AgentStage
    required_data: tuple[str, ...]
    supported_timeframes: tuple[str, ...]
    compatible_regimes: tuple[str, ...]
    output_schema: str = "AgentResult/v1"
    score_range: tuple[float, float] = (0.0, 100.0)
    hard_gate_eligible: bool = False
    false_positive_risk: tuple[str, ...] = field(default_factory=tuple)
    oos_requirements: tuple[str, ...] = field(default_factory=tuple)
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH_ONLY
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    evidence_cluster: str = "diagnostic"
    evidence_layer_schema: str = "AgentEvidenceLayer/v1"
    verification_layer_schema: str = "VerificationLayer/v1"
    required_evidence_domains: tuple[str, ...] = field(default_factory=tuple)
    required_verification_checks: tuple[str, ...] = field(default_factory=tuple)
    expensive: bool = False

    def __post_init__(self) -> None:
        """Reject incomplete or prematurely promoted declarations."""
        for field_name in (
            "name",
            "family",
            "version",
            "output_schema",
            "evidence_layer_schema",
            "verification_layer_schema",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        lower, upper = self.score_range
        if lower < 0.0 or upper > 100.0 or lower > upper:
            raise ValueError("score_range must be ordered within 0 and 100")
        if self.name in self.dependencies:
            raise ValueError("an agent cannot depend on itself")
        if self.hard_gate_eligible and self.promotion_status not in {
            PromotionStatus.PAPER_APPROVED,
            PromotionStatus.LIVE_ELIGIBLE,
        }:
            raise ValueError("hard-gate agents require governed promotion")
        if self.hard_gate_eligible and not self.oos_requirements:
            raise ValueError("hard-gate agents require explicit OOS requirements")
        if len(set(self.required_evidence_domains)) != len(
            self.required_evidence_domains
        ):
            raise ValueError("required evidence domains must be unique")
        if len(set(self.required_verification_checks)) != len(
            self.required_verification_checks
        ):
            raise ValueError("required verification checks must be unique")
        if any(not item.strip() for item in self.required_evidence_domains):
            raise ValueError("required evidence domains cannot contain empty values")
        if any(not item.strip() for item in self.required_verification_checks):
            raise ValueError("required verification checks cannot contain empty values")


@dataclass(frozen=True, slots=True)
class AgentRegistry:
    """Immutable platform-definition registry with validated dependencies."""

    definitions: tuple[AgentDefinition, ...]
    _by_name: Mapping[str, AgentDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build an immutable lookup and reject unknown dependencies."""
        by_name = {definition.name: definition for definition in self.definitions}
        if len(by_name) != len(self.definitions):
            raise ValueError("agent names must be unique")
        for definition in self.definitions:
            unknown = tuple(
                dependency
                for dependency in definition.dependencies
                if dependency not in by_name
            )
            if unknown:
                joined = ", ".join(unknown)
                raise ValueError(
                    f"unknown dependencies for {definition.name}: {joined}"
                )
        unresolved = {
            definition.name: set(definition.dependencies)
            for definition in self.definitions
        }
        resolved: set[str] = set()
        while unresolved:
            ready = tuple(
                name
                for name, dependencies in unresolved.items()
                if dependencies <= resolved
            )
            if not ready:
                raise ValueError("agent dependency graph contains a cycle")
            resolved.update(ready)
            for name in ready:
                del unresolved[name]
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def get(self, name: str) -> AgentDefinition:
        """Return one registered definition."""
        return self._by_name[name]

    def by_stage(self, stage: AgentStage) -> tuple[AgentDefinition, ...]:
        """Return stage definitions in stable registration order."""
        return tuple(item for item in self.definitions if item.stage is stage)

    @property
    def by_name(self) -> Mapping[str, AgentDefinition]:
        """Expose the immutable name lookup."""
        return self._by_name


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Declarative, research-only projection of one analytical capability."""

    capability_id: str
    version: str
    family: str
    dependencies: tuple[str, ...]
    required_data: tuple[str, ...]
    timeframes: tuple[str, ...]
    compatible_regimes: tuple[str, ...]
    cluster: str
    expensive: bool
    runtime_eligible: bool
    execution_class: CapabilityExecutionClass
    activation_policy: CapabilityActivationPolicy
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        """Reject malformed declarations and any attempt to widen authority."""
        for field_name in (
            "capability_id",
            "version",
            "family",
            "cluster",
            "live_eligibility_status",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.capability_id in self.dependencies:
            raise ValueError("a capability cannot depend on itself")
        if not self.timeframes or any(not item.strip() for item in self.timeframes):
            raise ValueError("capability timeframes must contain non-empty values")
        if not self.compatible_regimes or any(
            not item.strip() for item in self.compatible_regimes
        ):
            raise ValueError("capability regimes must contain non-empty values")
        if self.promotion_status is not PromotionStatus.RESEARCH_ONLY:
            raise ValueError("capability declarations must remain research-only")
        if self.execution_allowed:
            raise ValueError("capability declarations cannot allow execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("capability declarations must keep live orders blocked")


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    """Immutable analytical-capability registry with validated dependencies."""

    definitions: tuple[CapabilityDefinition, ...]
    external_dependency_ids: tuple[str, ...] = field(default_factory=tuple)
    _by_id: Mapping[str, CapabilityDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build an immutable lookup and reject invalid dependency graphs."""
        by_id = {
            definition.capability_id: definition for definition in self.definitions
        }
        if len(by_id) != len(self.definitions):
            raise ValueError("capability identifiers must be unique")
        if len(set(self.external_dependency_ids)) != len(self.external_dependency_ids):
            raise ValueError("external capability dependencies must be unique")
        for definition in self.definitions:
            unknown = tuple(
                dependency
                for dependency in definition.dependencies
                if dependency not in by_id
                and dependency not in self.external_dependency_ids
            )
            if unknown:
                joined = ", ".join(unknown)
                raise ValueError(
                    f"unknown dependencies for {definition.capability_id}: {joined}"
                )
        unresolved = {
            definition.capability_id: {
                dependency
                for dependency in definition.dependencies
                if dependency in by_id
            }
            for definition in self.definitions
        }
        resolved: set[str] = set()
        while unresolved:
            ready = tuple(
                capability_id
                for capability_id, dependencies in unresolved.items()
                if dependencies <= resolved
            )
            if not ready:
                raise ValueError("capability dependency graph contains a cycle")
            resolved.update(ready)
            for capability_id in ready:
                del unresolved[capability_id]
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def get(self, capability_id: str) -> CapabilityDefinition:
        """Return one registered analytical capability."""
        return self._by_id[capability_id]

    @property
    def by_id(self) -> Mapping[str, CapabilityDefinition]:
        """Expose the immutable capability identifier lookup."""
        return self._by_id


@dataclass(frozen=True, slots=True)
class CapabilityBundleDefinition:
    """Immutable runtime-planning group for related analytical capabilities."""

    bundle_id: str
    capability_ids: tuple[str, ...]
    execution_class: CapabilityExecutionClass = (
        CapabilityExecutionClass.DETERMINISTIC_THREAD_POOL
    )
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        """Reject ambiguous membership and any widened execution authority."""
        if not self.bundle_id.strip():
            raise ValueError("capability bundle identity cannot be empty")
        if not self.capability_ids or any(
            not item.strip() for item in self.capability_ids
        ):
            raise ValueError("capability bundle requires non-empty capability IDs")
        if len(set(self.capability_ids)) != len(self.capability_ids):
            raise ValueError("capability bundle membership must be unique")
        if self.promotion_status is not PromotionStatus.RESEARCH_ONLY:
            raise ValueError("capability bundles must remain research-only")
        if self.execution_allowed:
            raise ValueError("capability bundles cannot allow execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("capability bundles must keep live orders blocked")


@dataclass(frozen=True, slots=True)
class CapabilityBundleRegistry:
    """Validated one-to-one grouping of a complete capability registry."""

    definitions: tuple[CapabilityBundleDefinition, ...]
    capability_registry: CapabilityRegistry
    _by_id: Mapping[str, CapabilityBundleDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Require exact, non-overlapping coverage of every capability."""
        by_id = {definition.bundle_id: definition for definition in self.definitions}
        if len(by_id) != len(self.definitions):
            raise ValueError("capability bundle identities must be unique")
        known_capability_ids = set(self.capability_registry.by_id)
        member_ids = tuple(
            capability_id
            for definition in self.definitions
            for capability_id in definition.capability_ids
        )
        unknown_ids = tuple(
            capability_id
            for capability_id in member_ids
            if capability_id not in known_capability_ids
        )
        if unknown_ids:
            raise ValueError(
                "capability bundle contains unknown capabilities: "
                + ", ".join(unknown_ids)
            )
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("capabilities cannot belong to multiple bundles")
        if set(member_ids) != known_capability_ids:
            raise ValueError("capability bundles must cover the complete registry")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def get(self, bundle_id: str) -> CapabilityBundleDefinition:
        """Return one registered capability bundle."""
        return self._by_id[bundle_id]

    @property
    def by_id(self) -> Mapping[str, CapabilityBundleDefinition]:
        """Expose the immutable bundle identifier lookup."""
        return self._by_id

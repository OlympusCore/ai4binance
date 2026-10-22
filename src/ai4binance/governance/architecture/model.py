"""Typed contracts for the non-authoritative logical-architecture mirror."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class LogicalComponentKind(StrEnum):
    """Classify a component without assigning decision or execution authority."""

    ADAPTER = "ADAPTER"
    ADVISORY_AGENT = "ADVISORY_AGENT"
    CAPABILITY = "CAPABILITY"
    CONTROL = "CONTROL"
    DOMAIN = "DOMAIN"
    ENGINE = "ENGINE"
    FACADE = "FACADE"
    GATE = "GATE"
    ORCHESTRATOR = "ORCHESTRATOR"
    REGISTRY = "REGISTRY"
    RUNTIME_ACTOR = "RUNTIME_ACTOR"
    SERVICE = "SERVICE"


class LogicalRelationType(StrEnum):
    """Typed relationship between two declared logical components."""

    BLOCKS = "BLOCKS"
    CONSTRAINED_BY = "CONSTRAINED_BY"
    CONSUMES = "CONSUMES"
    CREATES = "CREATES"
    DEPENDS_ON = "DEPENDS_ON"
    EVALUATED_BY = "EVALUATED_BY"
    EXECUTES = "EXECUTES"
    GOVERNED_BY = "GOVERNED_BY"
    IMPLEMENTS = "IMPLEMENTS"
    PRODUCES = "PRODUCES"
    PRODUCES_LESSON = "PRODUCES_LESSON"
    PROPOSES = "PROPOSES"
    PROMOTES = "PROMOTES"
    SUBJECT_TO = "SUBJECT_TO"
    VALIDATED_BY = "VALIDATED_BY"
    VALIDATES = "VALIDATES"


@dataclass(frozen=True, slots=True)
class LogicalArchitectureComponent:
    """One declared component mapping with an explicit non-authority ceiling."""

    component_id: str
    component_kind: LogicalComponentKind
    canonical_domain: str
    logical_plane: str
    dependency_layer: str
    runtime_class: str
    owner: str
    authority_effect: str
    source_paths: tuple[str, ...]
    contract_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    hot_path: bool
    deterministic: bool
    llm_dependency: bool
    side_effects: bool
    decision_authority: bool
    risk_override: bool
    validation_override: bool
    source_of_truth: bool
    execution_allowed: bool
    live_eligibility_status: str

    def __post_init__(self) -> None:
        for field_name in (
            "component_id",
            "canonical_domain",
            "logical_plane",
            "dependency_layer",
            "runtime_class",
            "owner",
            "authority_effect",
            "live_eligibility_status",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"logical architecture {field_name} is required")
        for field_name in ("source_paths", "contract_refs", "test_refs"):
            values = getattr(self, field_name)
            if not values or len(values) != len(set(values)):
                raise ValueError(f"logical architecture {field_name} must be unique")
            if any(_unsafe_repository_path(value) for value in values):
                raise ValueError(
                    f"logical architecture {field_name} must be repository-relative"
                )
        if self.side_effects:
            raise ValueError(
                "logical architecture components cannot declare side effects"
            )
        if self.decision_authority or self.risk_override or self.validation_override:
            raise ValueError("logical architecture components cannot grant authority")
        if self.source_of_truth:
            raise ValueError(
                "logical architecture components cannot become a source of truth"
            )
        if self.execution_allowed:
            raise ValueError(
                "logical architecture components cannot authorize execution"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError(
                "logical architecture components must remain live-order blocked"
            )

    def to_payload(self) -> dict[str, object]:
        """Return the stable, explicitly non-authoritative component payload."""
        return {
            "component_id": self.component_id,
            "component_kind": self.component_kind.value,
            "canonical_domain": self.canonical_domain,
            "logical_plane": self.logical_plane,
            "dependency_layer": self.dependency_layer,
            "runtime_class": self.runtime_class,
            "owner": self.owner,
            "authority_effect": self.authority_effect,
            "source_paths": list(self.source_paths),
            "contract_refs": list(self.contract_refs),
            "test_refs": list(self.test_refs),
            "hot_path": self.hot_path,
            "deterministic": self.deterministic,
            "llm_dependency": self.llm_dependency,
            "side_effects": False,
            "decision_authority": False,
            "risk_override": False,
            "validation_override": False,
            "source_of_truth": False,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class LogicalArchitectureRelation:
    """A typed relation between components declared by one registry."""

    relation_id: str
    from_component_id: str
    to_component_id: str
    relation_type: LogicalRelationType

    def __post_init__(self) -> None:
        if not self.relation_id.strip():
            raise ValueError("logical architecture relation_id is required")
        if not self.from_component_id.strip() or not self.to_component_id.strip():
            raise ValueError("logical architecture relation endpoints are required")
        if self.from_component_id == self.to_component_id:
            raise ValueError("logical architecture relations cannot self-reference")

    def to_payload(self) -> dict[str, str]:
        """Return the stable relation declaration."""
        return {
            "relation_id": self.relation_id,
            "from_component_id": self.from_component_id,
            "to_component_id": self.to_component_id,
            "relation_type": self.relation_type.value,
        }


CORE_EVIDENCE_DIMENSIONS = (
    "ownership",
    "input_output",
    "dependencies",
    "veto_boundary",
    "failure_behavior",
    "resource_budget",
    "tests_evidence",
    "runtime_consumer",
)
CORE_FORBIDDEN_AUTHORITIES = (
    "live_execution_authority",
    "risk_override",
    "validation_override",
    "governance_bypass",
)


@dataclass(frozen=True, slots=True)
class CoreInterfaceBinding:
    """One declared contract handoff; declaration is never runtime evidence."""

    interface_id: str
    component_id: str
    contract_ref: str
    producer_ref: str
    consumer_ref: str

    def __post_init__(self) -> None:
        if not self.interface_id.strip() or not self.component_id.strip():
            raise ValueError("core interface identity is required")
        if _unsafe_repository_path(self.contract_ref):
            raise ValueError("core interface contract must be repository-relative")
        for reference in (self.producer_ref, self.consumer_ref):
            path, separator, symbol = reference.partition("::")
            if _unsafe_repository_path(path) or not separator or not symbol.strip():
                raise ValueError(
                    "core interface requires a repository symbol reference"
                )

    def to_payload(self) -> dict[str, str]:
        return {
            "interface_id": self.interface_id,
            "component_id": self.component_id,
            "contract_ref": self.contract_ref,
            "producer_ref": self.producer_ref,
            "consumer_ref": self.consumer_ref,
        }


@dataclass(frozen=True, slots=True)
class CoreAssuranceContract:
    """Evidence requirements, without budgets, owner appointments or permissions."""

    required_dimensions: tuple[str, ...] = CORE_EVIDENCE_DIMENSIONS
    interfaces: tuple[CoreInterfaceBinding, ...] = ()
    failure_test_refs: tuple[str, ...] = ()
    resource_budget_ref: str | None = None
    evidence_max_age_seconds: int = 86_400
    veto_boundary_refs: tuple[str, ...] = ()
    forbidden_authorities: tuple[str, ...] = CORE_FORBIDDEN_AUTHORITIES

    def __post_init__(self) -> None:
        if self.required_dimensions != CORE_EVIDENCE_DIMENSIONS:
            raise ValueError("core assurance requires all eight canonical dimensions")
        if self.forbidden_authorities != CORE_FORBIDDEN_AUTHORITIES:
            raise ValueError(
                "core assurance cannot widen forbidden authority boundaries"
            )
        if any(_unsafe_repository_path(ref) for ref in self.veto_boundary_refs):
            raise ValueError("core veto boundaries require repository references")
        ids = tuple(item.interface_id for item in self.interfaces)
        if len(ids) != len(set(ids)):
            raise ValueError("core assurance interfaces must be unique")
        if len(self.failure_test_refs) != len(set(self.failure_test_refs)) or any(
            _unsafe_repository_path(ref.partition("::")[0])
            for ref in self.failure_test_refs
        ):
            raise ValueError("core failure tests must be unique repository references")
        if self.resource_budget_ref is not None and _unsafe_repository_path(
            self.resource_budget_ref
        ):
            raise ValueError("core resource budget must be repository-relative")
        if self.resource_budget_ref is not None and (
            not self.resource_budget_ref.startswith("config/")
            or not self.resource_budget_ref.endswith((".yaml", ".toml"))
        ):
            raise ValueError(
                "core resource budget must reference canonical configuration"
            )
        if type(self.evidence_max_age_seconds) is not int or not (
            1 <= self.evidence_max_age_seconds <= 86_400
        ):
            raise ValueError(
                "core evidence freshness cannot exceed current quality freshness"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "required_dimensions": list(self.required_dimensions),
            "interfaces": [item.to_payload() for item in self.interfaces],
            "failure_test_refs": list(self.failure_test_refs),
            "resource_budget_ref": self.resource_budget_ref,
            "evidence_max_age_seconds": self.evidence_max_age_seconds,
            "veto_boundary_refs": list(self.veto_boundary_refs),
            "forbidden_authorities": list(self.forbidden_authorities),
        }


@dataclass(frozen=True, slots=True)
class CoreModule:
    """A logical module boundary; membership never grants runtime authority."""

    core_id: str
    term_id: str
    component_ids: tuple[str, ...]
    enforcement_entrypoints: tuple[str, ...]
    accountability_refs: Mapping[str, str] = field(default_factory=dict)
    accountable_component_id: str | None = None
    assurance: CoreAssuranceContract | None = None

    def __post_init__(self) -> None:
        if not self.core_id.strip() or not self.term_id.strip():
            raise ValueError("core module identity is required")
        if not self.component_ids:
            raise ValueError("core module requires existing components")
        for values in (self.component_ids, self.enforcement_entrypoints):
            if len(values) != len(set(values)) or any(
                not item.strip() for item in values
            ):
                raise ValueError("core module references must be unique and nonblank")
        roles = {
            "human_authority",
            "logical_owner",
            "technical_owner",
            "validation_owner",
        }
        if self.accountability_refs and set(self.accountability_refs) != roles:
            raise ValueError("core accountability requires all four canonical roles")
        if self.accountable_component_id is not None and (
            self.accountable_component_id not in self.component_ids
        ):
            raise ValueError(
                "core module accountable component must belong to the core"
            )
        if self.accountability_refs and self.accountable_component_id is None:
            raise ValueError("core accountability requires an accountable component")
        if self.assurance is not None and any(
            item.component_id not in self.component_ids
            for item in self.assurance.interfaces
        ):
            raise ValueError("core interface component must belong to the core")
        if any(
            _unsafe_repository_path(ref) for ref in self.accountability_refs.values()
        ):
            raise ValueError(
                "core accountability must use repository-relative references"
            )
        object.__setattr__(
            self,
            "accountability_refs",
            MappingProxyType(dict(self.accountability_refs)),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "core_id": self.core_id,
            "term_id": self.term_id,
            "component_ids": list(self.component_ids),
            "enforcement_entrypoints": list(self.enforcement_entrypoints),
        }
        if self.accountability_refs:
            payload["accountability_refs"] = dict(self.accountability_refs)
        if self.accountable_component_id is not None:
            payload["accountable_component_id"] = self.accountable_component_id
        if self.assurance is not None:
            payload["assurance"] = self.assurance.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class LogicalArchitectureRegistry:
    """Validated enforcement mirror of declared logical architecture only."""

    registry_id: str
    version: str
    status: str
    source_of_truth: bool
    execution_allowed: bool
    live_eligibility_status: str
    components: tuple[LogicalArchitectureComponent, ...]
    relations: tuple[LogicalArchitectureRelation, ...]
    core_modules: tuple[CoreModule, ...] = ()

    def __post_init__(self) -> None:
        if not self.registry_id.strip() or not self.version.strip():
            raise ValueError("logical architecture registry identity is required")
        if self.status != "ACTIVE":
            raise ValueError("logical architecture registry must be active")
        if self.source_of_truth:
            raise ValueError(
                "logical architecture registry cannot become a source of truth"
            )
        if self.execution_allowed:
            raise ValueError("logical architecture registry cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError(
                "logical architecture registry must remain live-order blocked"
            )
        component_ids = tuple(component.component_id for component in self.components)
        if not component_ids or component_ids != tuple(sorted(component_ids)):
            raise ValueError(
                "logical architecture components must be non-empty and sorted"
            )
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("logical architecture component IDs must be unique")
        relation_ids = tuple(relation.relation_id for relation in self.relations)
        if relation_ids != tuple(sorted(relation_ids)):
            raise ValueError("logical architecture relations must be sorted")
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("logical architecture relation IDs must be unique")
        relation_semantics = tuple(
            (
                relation.from_component_id,
                relation.relation_type,
                relation.to_component_id,
            )
            for relation in self.relations
        )
        if len(relation_semantics) != len(set(relation_semantics)):
            raise ValueError("logical architecture relation semantics must be unique")
        declared_ids = frozenset(component_ids)
        unknown_endpoints = tuple(
            relation.relation_id
            for relation in self.relations
            if relation.from_component_id not in declared_ids
            or relation.to_component_id not in declared_ids
        )
        if unknown_endpoints:
            raise ValueError(
                "logical architecture relations reference unknown components: "
                + ", ".join(unknown_endpoints)
            )

    def to_payload(self) -> dict[str, object]:
        """Return an enforcement-mirror payload without authority expansion."""
        return {
            "registry_id": self.registry_id,
            "version": self.version,
            "status": self.status,
            "source_of_truth": False,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "components": [component.to_payload() for component in self.components],
            "relations": [relation.to_payload() for relation in self.relations],
            "core_modules": [module.to_payload() for module in self.core_modules],
        }


def _unsafe_repository_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        not normalized.strip()
        or normalized.startswith("/")
        or (len(normalized) > 1 and normalized[1] == ":")
        or ".." in normalized.split("/")
    )

"""Typed contracts for the non-authoritative logical-architecture mirror."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
        }


def _unsafe_repository_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        not normalized.strip()
        or normalized.startswith("/")
        or (len(normalized) > 1 and normalized[1] == ":")
        or ".." in normalized.split("/")
    )

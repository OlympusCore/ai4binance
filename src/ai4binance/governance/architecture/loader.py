"""Fail-closed loading for the local logical-architecture registry."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from ai4binance.governance.architecture.graph import LogicalArchitectureGraph
from ai4binance.governance.architecture.model import (
    LogicalArchitectureComponent,
    LogicalArchitectureRegistry,
    LogicalArchitectureRelation,
    LogicalComponentKind,
    LogicalRelationType,
)
from ai4binance.governance.framework import build_core_architecture
from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

DEFAULT_LOGICAL_ARCHITECTURE_REGISTRY_PATH = Path(
    "docs/registries/registry_logical_architecture.yaml"
)
_LOGICAL_ARCHITECTURE_SCHEMA_ID = (
    "https://ai4binance.local/schemas/architecture/logical_architecture.schema.json"
)
_CANONICAL_TRADE_DECISION_PRODUCER_ID = "decision-governance"
_CANONICAL_ORDER_COMPONENT_ID = "order"
_CANONICAL_LEARNING_CANDIDATE_COMPONENT_ID = "learning-candidate"
_CANONICAL_PRODUCTION_COMPONENT_ID = "production-component"
_DECISION_CONTRACT_NAMES = frozenset({"GovernedDecision", "TradeDecision"})
_DECISION_CONTRACT_MODULES = frozenset(
    {
        "ai4binance.governance",
        "ai4binance.governance.dge_models",
    }
)
_MANDATORY_DGE_HANDOFFS = frozenset({"risk_approved", "validation_approved"})
_DECISION_CHAIN_AUTHORITY_EFFECTS = {
    "closure-review": "EVIDENCE_ONLY",
    "decision-candidate": "EVIDENCE_ONLY",
    "decision-governance": "IMPLEMENTATION",
    "deterministic-core": "IMPLEMENTATION",
    "execution-gate-result": "VETO",
    "execution-record": "EVIDENCE_ONLY",
    "learning-candidate": "EVIDENCE_ONLY",
    "lesson": "EVIDENCE_ONLY",
    "policy": "VETO",
    "position-lifecycle": "EVIDENCE_ONLY",
    "risk-assessment": "VETO",
    "setup": "EVIDENCE_ONLY",
    "trade-decision": "EVIDENCE_ONLY",
    "trade-plan": "EVIDENCE_ONLY",
    "validation": "VETO",
}
_REQUIRED_DECISION_CHAIN_RELATIONS = {
    "candidate-constrained-by-risk-assessment": (
        "decision-candidate",
        LogicalRelationType.CONSTRAINED_BY,
        "risk-assessment",
    ),
    "candidate-validated-by-validation": (
        "decision-candidate",
        LogicalRelationType.VALIDATED_BY,
        "validation",
    ),
    "closure-review-produces-lesson": (
        "closure-review",
        LogicalRelationType.PRODUCES_LESSON,
        "lesson",
    ),
    "decision-governance-produces-trade-decision": (
        "decision-governance",
        LogicalRelationType.PRODUCES,
        "trade-decision",
    ),
    "deterministic-core-produces-decision-candidate": (
        "deterministic-core",
        LogicalRelationType.PRODUCES,
        "decision-candidate",
    ),
    "execution-record-creates-position-lifecycle": (
        "execution-record",
        LogicalRelationType.CREATES,
        "position-lifecycle",
    ),
    "lesson-proposes-learning-candidate": (
        "lesson",
        LogicalRelationType.PROPOSES,
        "learning-candidate",
    ),
    "position-lifecycle-evaluated-by-closure-review": (
        "position-lifecycle",
        LogicalRelationType.EVALUATED_BY,
        "closure-review",
    ),
    "setup-evaluated-by-deterministic-core": (
        "setup",
        LogicalRelationType.EVALUATED_BY,
        "deterministic-core",
    ),
    "trade-decision-governed-by-policy": (
        "trade-decision",
        LogicalRelationType.GOVERNED_BY,
        "policy",
    ),
    "trade-plan-subject-to-execution-gate-result": (
        "trade-plan",
        LogicalRelationType.SUBJECT_TO,
        "execution-gate-result",
    ),
}


@dataclass(frozen=True, slots=True)
class RuntimeArchitectureConformance:
    """Evidence that the canonical final-decision runtime route is singular."""

    trade_decision_contract_path: str
    trade_decision_producer_path: str
    mandatory_dge_handoffs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SourceInspection:
    path: str
    class_definitions: tuple[str, ...]
    compatibility_aliases: tuple[tuple[str, str], ...]
    decision_constructor_calls: int
    context_handoffs: tuple[str, ...]


def load_logical_architecture_registry(
    path: Path = DEFAULT_LOGICAL_ARCHITECTURE_REGISTRY_PATH,
    *,
    schema_root: Path | None = None,
    repository_root: Path | None = None,
) -> LogicalArchitectureRegistry:
    """Load one local, integrity-validated registry without network I/O."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(
            f"logical architecture registry cannot be loaded: {path}"
        ) from error
    if not isinstance(payload, Mapping):
        raise ValueError("logical architecture registry must be a mapping")
    selected_repository_root = (repository_root or Path(__file__).parents[4]).resolve()
    selected_schema_root = schema_root or selected_repository_root / "schemas"
    try:
        OfflineSchemaRegistry.from_directory(selected_schema_root).validate(
            _LOGICAL_ARCHITECTURE_SCHEMA_ID, payload
        )
    except SchemaValidationError as error:
        raise ValueError(
            "logical architecture registry schema validation failed"
        ) from error
    typed_payload = cast(Mapping[str, object], payload)
    registry = LogicalArchitectureRegistry(
        registry_id=_required_string(typed_payload, "registry_id"),
        version=_required_string(typed_payload, "version"),
        status=_required_string(typed_payload, "status"),
        source_of_truth=_required_bool(typed_payload, "source_of_truth"),
        execution_allowed=_required_bool(typed_payload, "execution_allowed"),
        live_eligibility_status=_required_string(
            typed_payload, "live_eligibility_status"
        ),
        components=tuple(
            _component_from_payload(item)
            for item in _required_list(typed_payload, "components")
        ),
        relations=tuple(
            _relation_from_payload(item)
            for item in _required_list(typed_payload, "relations")
        ),
    )
    _validate_canonical_domain_planes(registry)
    _validate_canonical_decision_chain(registry)
    _validate_forbidden_decision_shortcuts(registry)
    _validate_forbidden_execution_shortcuts(registry)
    _validate_forbidden_learning_self_promotion(registry)
    _validate_repository_references(registry, selected_repository_root)
    validate_runtime_architecture_conformance(registry, selected_repository_root)
    LogicalArchitectureGraph(registry).assert_acyclic_dependencies()
    return registry


def _validate_canonical_domain_planes(
    registry: LogicalArchitectureRegistry,
) -> None:
    canonical_planes = {
        domain.domain_id.value: domain.plane.value
        for domain in build_core_architecture().domains
    }
    drift = sorted(
        f"{component.component_id}.logical_plane must be "
        f"{canonical_planes[component.canonical_domain]}"
        for component in registry.components
        if component.logical_plane != canonical_planes[component.canonical_domain]
    )
    if drift:
        raise ValueError(
            "logical architecture canonical domain-plane drift: " + ", ".join(drift)
        )


def _validate_canonical_decision_chain(
    registry: LogicalArchitectureRegistry,
) -> None:
    component_index = {
        component.component_id: component for component in registry.components
    }
    relation_index = {relation.relation_id: relation for relation in registry.relations}
    drift: list[str] = []
    for component_id, expected_effect in _DECISION_CHAIN_AUTHORITY_EFFECTS.items():
        component = component_index.get(component_id)
        if component is None:
            drift.append(f"missing component {component_id}")
            continue
        if component.authority_effect != expected_effect:
            drift.append(f"{component_id}.authority_effect must be {expected_effect}")
        if not component.hot_path:
            drift.append(f"{component_id}.hot_path must be true")
        if not component.deterministic:
            drift.append(f"{component_id}.deterministic must be true")
        if component.llm_dependency:
            drift.append(f"{component_id}.llm_dependency must be false")
    for relation_id, expected in _REQUIRED_DECISION_CHAIN_RELATIONS.items():
        relation = relation_index.get(relation_id)
        if relation is None:
            drift.append(f"missing relation {relation_id}")
            continue
        actual = (
            relation.from_component_id,
            relation.relation_type,
            relation.to_component_id,
        )
        if actual != expected:
            drift.append(f"{relation_id} has non-canonical semantics")
    if drift:
        raise ValueError(
            "logical architecture canonical decision chain drift: " + ", ".join(drift)
        )


def _validate_forbidden_decision_shortcuts(
    registry: LogicalArchitectureRegistry,
) -> None:
    violations = sorted(
        relation.relation_id
        for relation in registry.relations
        if relation.relation_type is LogicalRelationType.PRODUCES
        and relation.to_component_id == "trade-decision"
        and relation.from_component_id != _CANONICAL_TRADE_DECISION_PRODUCER_ID
    )
    if violations:
        raise ValueError(
            "logical architecture unauthorized trade-decision producer: "
            + ", ".join(violations)
        )


def _validate_forbidden_execution_shortcuts(
    registry: LogicalArchitectureRegistry,
) -> None:
    component_index = {
        component.component_id: component for component in registry.components
    }
    violations = sorted(
        relation.relation_id
        for relation in registry.relations
        if relation.relation_type is LogicalRelationType.EXECUTES
        and component_index[relation.from_component_id].component_kind
        is LogicalComponentKind.ADVISORY_AGENT
        and relation.to_component_id == _CANONICAL_ORDER_COMPONENT_ID
    )
    if violations:
        raise ValueError(
            "logical architecture unauthorized agent execution shortcut: "
            + ", ".join(violations)
        )


def _validate_forbidden_learning_self_promotion(
    registry: LogicalArchitectureRegistry,
) -> None:
    violations = sorted(
        relation.relation_id
        for relation in registry.relations
        if relation.relation_type is LogicalRelationType.PROMOTES
        and relation.from_component_id == _CANONICAL_LEARNING_CANDIDATE_COMPONENT_ID
        and relation.to_component_id == _CANONICAL_PRODUCTION_COMPONENT_ID
    )
    if violations:
        raise ValueError(
            "logical architecture unauthorized learning self-promotion shortcut: "
            + ", ".join(violations)
        )


def _validate_repository_references(
    registry: LogicalArchitectureRegistry,
    repository_root: Path,
) -> None:
    unavailable: list[str] = []
    for component in registry.components:
        for field_name in ("source_paths", "contract_refs", "test_refs"):
            for reference in getattr(component, field_name):
                resolved_reference = (repository_root / reference).resolve()
                if (
                    not resolved_reference.is_relative_to(repository_root)
                    or not resolved_reference.is_file()
                ):
                    unavailable.append(
                        f"{component.component_id}.{field_name}:{reference}"
                    )
    if unavailable:
        raise ValueError(
            "logical architecture repository references are unavailable: "
            + ", ".join(sorted(unavailable))
        )


def validate_runtime_architecture_conformance(
    registry: LogicalArchitectureRegistry,
    repository_root: Path,
) -> RuntimeArchitectureConformance:
    """Fail closed when source wiring diverges from the declared decision route."""

    component_index = {
        component.component_id: component for component in registry.components
    }
    try:
        contract_paths = frozenset(component_index["trade-decision"].source_paths)
        producer_paths = frozenset(component_index["decision-governance"].source_paths)
    except KeyError as error:
        raise ValueError(
            "runtime architecture conformance requires decision components"
        ) from error

    source_root = repository_root / "src" / "ai4binance"
    if not source_root.is_dir():
        raise ValueError(
            "runtime architecture conformance source root is unavailable: "
            "src/ai4binance"
        )

    required_paths = contract_paths | producer_paths
    inspections: list[_SourceInspection] = []
    for source_path in sorted(source_root.rglob("*.py")):
        relative_path = source_path.relative_to(repository_root).as_posix()
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(
                f"runtime architecture source cannot be read: {relative_path}"
            ) from error
        if (
            relative_path not in required_paths
            and "TradeDecision" not in source_text
            and "GovernedDecision" not in source_text
        ):
            continue
        try:
            tree = ast.parse(source_text, filename=relative_path)
        except SyntaxError as error:
            raise ValueError(
                f"runtime architecture source cannot be parsed: {relative_path}"
            ) from error
        inspections.append(_inspect_runtime_source(relative_path, tree))

    class_owners = tuple(
        inspection.path
        for inspection in inspections
        if "TradeDecision" in inspection.class_definitions
    )
    if len(class_owners) != 1 or class_owners[0] not in contract_paths:
        raise ValueError(
            "runtime architecture TradeDecision contract owner must be singular: "
            + ", ".join(class_owners or ("MISSING",))
        )
    parallel_alias_classes = tuple(
        inspection.path
        for inspection in inspections
        if "GovernedDecision" in inspection.class_definitions
    )
    if parallel_alias_classes:
        raise ValueError(
            "runtime architecture GovernedDecision compatibility alias cannot define "
            "a parallel contract: " + ", ".join(parallel_alias_classes)
        )

    governed_alias_owners = tuple(
        inspection.path
        for inspection in inspections
        if ("GovernedDecision", "TradeDecision") in inspection.compatibility_aliases
    )
    if governed_alias_owners != class_owners:
        raise ValueError(
            "runtime architecture GovernedDecision alias must map to the canonical "
            "TradeDecision contract"
        )

    observed_producers = tuple(
        inspection.path
        for inspection in inspections
        if inspection.decision_constructor_calls
    )
    unauthorized_producers = tuple(
        path for path in observed_producers if path not in producer_paths
    )
    if unauthorized_producers:
        raise ValueError(
            "runtime architecture unauthorized TradeDecision producer: "
            + ", ".join(unauthorized_producers)
        )
    if len(observed_producers) != 1:
        raise ValueError(
            "runtime architecture requires one canonical TradeDecision producer: "
            + ", ".join(observed_producers or ("MISSING",))
        )

    producer_inspection = next(
        inspection
        for inspection in inspections
        if inspection.path == observed_producers[0]
    )
    missing_handoffs = tuple(
        sorted(_MANDATORY_DGE_HANDOFFS - set(producer_inspection.context_handoffs))
    )
    if missing_handoffs:
        raise ValueError(
            "runtime architecture canonical TradeDecision producer is missing "
            "mandatory handoffs: " + ", ".join(missing_handoffs)
        )

    return RuntimeArchitectureConformance(
        trade_decision_contract_path=class_owners[0],
        trade_decision_producer_path=observed_producers[0],
        mandatory_dge_handoffs=tuple(sorted(_MANDATORY_DGE_HANDOFFS)),
    )


def _inspect_runtime_source(path: str, tree: ast.Module) -> _SourceInspection:
    imported_constructor_names: set[str] = set()
    module_aliases: set[str] = set()
    compatibility_aliases: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module in _DECISION_CONTRACT_MODULES
        ):
            for imported in node.names:
                if imported.name == "*":
                    imported_constructor_names.update(_DECISION_CONTRACT_NAMES)
                elif imported.name in _DECISION_CONTRACT_NAMES:
                    imported_constructor_names.add(imported.asname or imported.name)
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name in _DECISION_CONTRACT_MODULES:
                    module_aliases.add(imported.asname or imported.name)

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if not isinstance(value, ast.Name):
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "GovernedDecision" and value.id == "TradeDecision":
                    compatibility_aliases.append((target.id, value.id))
                if value.id in imported_constructor_names and (
                    target.id not in imported_constructor_names
                ):
                    imported_constructor_names.add(target.id)
                    changed = True

    constructor_calls = 0
    context_handoffs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and (
                node.func.id in imported_constructor_names
            ):
                constructor_calls += 1
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _DECISION_CONTRACT_NAMES
                and _attribute_root(node.func) in module_aliases
            ):
                constructor_calls += 1
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "context"
            and node.attr in _MANDATORY_DGE_HANDOFFS
        ):
            context_handoffs.add(node.attr)

    return _SourceInspection(
        path=path,
        class_definitions=tuple(
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ),
        compatibility_aliases=tuple(compatibility_aliases),
        decision_constructor_calls=constructor_calls,
        context_handoffs=tuple(sorted(context_handoffs)),
    )


def _attribute_root(node: ast.Attribute) -> str:
    value: ast.expr = node
    while isinstance(value, ast.Attribute):
        value = value.value
    return value.id if isinstance(value, ast.Name) else ""


def _component_from_payload(value: object) -> LogicalArchitectureComponent:
    payload = _required_mapping(value, "logical architecture component")
    return LogicalArchitectureComponent(
        component_id=_required_string(payload, "component_id"),
        component_kind=LogicalComponentKind(
            _required_string(payload, "component_kind")
        ),
        canonical_domain=_required_string(payload, "canonical_domain"),
        logical_plane=_required_string(payload, "logical_plane"),
        dependency_layer=_required_string(payload, "dependency_layer"),
        runtime_class=_required_string(payload, "runtime_class"),
        owner=_required_string(payload, "owner"),
        authority_effect=_required_string(payload, "authority_effect"),
        source_paths=tuple(_required_string_list(payload, "source_paths")),
        contract_refs=tuple(_required_string_list(payload, "contract_refs")),
        test_refs=tuple(_required_string_list(payload, "test_refs")),
        hot_path=_required_bool(payload, "hot_path"),
        deterministic=_required_bool(payload, "deterministic"),
        llm_dependency=_required_bool(payload, "llm_dependency"),
        side_effects=_required_bool(payload, "side_effects"),
        decision_authority=_required_bool(payload, "decision_authority"),
        risk_override=_required_bool(payload, "risk_override"),
        validation_override=_required_bool(payload, "validation_override"),
        source_of_truth=_required_bool(payload, "source_of_truth"),
        execution_allowed=_required_bool(payload, "execution_allowed"),
        live_eligibility_status=_required_string(payload, "live_eligibility_status"),
    )


def _relation_from_payload(value: object) -> LogicalArchitectureRelation:
    payload = _required_mapping(value, "logical architecture relation")
    return LogicalArchitectureRelation(
        relation_id=_required_string(payload, "relation_id"),
        from_component_id=_required_string(payload, "from_component_id"),
        to_component_id=_required_string(payload, "to_component_id"),
        relation_type=LogicalRelationType(_required_string(payload, "relation_type")),
    )


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _required_list(payload: Mapping[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"logical architecture registry {key} must be a list")
    return value


def _required_string_list(payload: Mapping[str, object], key: str) -> list[str]:
    values = _required_list(payload, key)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"logical architecture registry {key} must contain strings")
    return cast(list[str], values)


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"logical architecture registry {key} is required")
    return value


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"logical architecture registry {key} must be boolean")
    return value

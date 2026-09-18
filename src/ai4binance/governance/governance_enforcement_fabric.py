"""Single deterministic wiring contract for semantic governance enforcement."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from ai4binance.governance.authority.development import (
    load_authority_layer_development_matrix,
    validate_authority_graph_layer_development,
)
from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.loader import load_authority_graph
from ai4binance.governance.technology_language_policy import (
    POLICY_PATH as TECHNOLOGY_POLICY_PATH,
)
from ai4binance.governance.technology_language_policy import (
    SCHEMA_PATH as TECHNOLOGY_SCHEMA_PATH,
)
from ai4binance.governance.technology_language_policy import (
    evaluate_technology_language_policy,
    load_technology_language_policy,
)
from ai4binance.governance.terminology_policy import (
    POLICY_PATH as TERMINOLOGY_POLICY_PATH,
)
from ai4binance.governance.terminology_policy import (
    SCHEMA_PATH as TERMINOLOGY_SCHEMA_PATH,
)
from ai4binance.governance.terminology_policy import (
    evaluate_terminology_policy,
    load_terminology_policy,
)
from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

FABRIC_PATH = Path("config/governance/governance_enforcement_fabric.yaml")
SCHEMA_PATH = Path("schemas/governance/governance_enforcement_fabric.schema.json")
SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/"
    "governance_enforcement_fabric.schema.json"
)
_EXPECTED_FAMILY_PATHS = {
    "terminology": (TERMINOLOGY_POLICY_PATH, TERMINOLOGY_SCHEMA_PATH),
    "repository_naming": (
        Path("policies/repository-validator/manifest-policy.json"),
        None,
    ),
    "technology_language": (TECHNOLOGY_POLICY_PATH, TECHNOLOGY_SCHEMA_PATH),
}
_EXPECTED_PILLAR_ROLES = {
    "kaizen": "CULTURE",
    "lean": "PROCESS",
    "six_sigma": "PERFORMANCE",
}
_EXPECTED_QUALITY_AXES = {
    "layer",
    "capability",
    "component",
    "guardrail",
    "eval",
    "assurance",
}


@dataclass(frozen=True, slots=True)
class EnforcementFamily:
    """One distinct authority scope connected to the shared fabric."""

    name: str
    authority_scope: str
    standard_path: str
    standard_id: str
    standard_version: str
    standard_content_sha256: str
    projection_path: str
    schema_path: str | None


@dataclass(frozen=True, slots=True)
class GovernanceQualityPillar:
    """One semantic quality pillar routed through existing gate mappings."""

    name: str
    semantic_role: str
    standard_mapping_names: tuple[str, ...]
    required_paths: tuple[str, ...]
    required_tests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GovernanceQualityAxis:
    """One deterministic governance evaluation axis and its proof surfaces."""

    name: str
    objective: str
    standard_mapping_names: tuple[str, ...]
    required_paths: tuple[str, ...]
    required_tests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GovernanceQualityGate:
    """Authority-aware quality-gate contract without consequential authority."""

    authority_pyramid_ref: str
    authority_graph_path: str
    authority_development_matrix_path: str
    quality_policy_path: str
    minimum_profile: str
    deterministic_quality_gate: str
    deterministic_governance_gate: str
    human_governance: str
    pillars: tuple[GovernanceQualityPillar, ...]
    evaluation_axes: tuple[GovernanceQualityAxis, ...]

    def __post_init__(self) -> None:
        if {
            pillar.name: pillar.semantic_role for pillar in self.pillars
        } != _EXPECTED_PILLAR_ROLES:
            raise ValueError("governance quality pillar semantics are invalid")
        if {axis.name for axis in self.evaluation_axes} != _EXPECTED_QUALITY_AXES:
            raise ValueError("governance quality evaluation axes are incomplete")
        if self.minimum_profile != "standard":
            raise ValueError("governance quality gate must require standard profile")
        if (
            self.deterministic_quality_gate != "TECHNICAL_TRUTH"
            or self.deterministic_governance_gate != "POLICY_ELIGIBILITY"
            or self.human_governance != "CONSEQUENTIAL_AUTHORITY"
        ):
            raise ValueError("governance quality authority separation is invalid")


@dataclass(frozen=True, slots=True)
class GovernanceEnforcementFabric:
    """Schema-validated, non-authoritative integration projection."""

    fabric_id: str
    version: str
    authority_scope: str
    families: tuple[EnforcementFamily, ...]
    quality_gate: GovernanceQualityGate

    def __post_init__(self) -> None:
        if self.authority_scope != "governance_enforcement_fabric":
            raise ValueError("governance enforcement fabric scope is invalid")
        names = {family.name for family in self.families}
        if names != set(_EXPECTED_FAMILY_PATHS):
            raise ValueError("governance enforcement fabric families are incomplete")
        if len({family.authority_scope for family in self.families}) != len(
            self.families
        ):
            raise ValueError(
                "governance enforcement fabric scopes must remain distinct"
            )
        for family in self.families:
            expected_projection, expected_schema = _EXPECTED_FAMILY_PATHS[family.name]
            if family.projection_path != expected_projection.as_posix():
                raise ValueError(f"{family.name} projection path is invalid")
            if family.schema_path != (
                expected_schema.as_posix() if expected_schema is not None else None
            ):
                raise ValueError(f"{family.name} schema path is invalid")


@dataclass(frozen=True, slots=True)
class FabricViolation:
    """A deterministic shared-fabric violation without decision authority."""

    family: str
    code: str
    path: str
    detail: str
    blocker: bool


def load_governance_enforcement_fabric(
    repository_root: Path,
) -> GovernanceEnforcementFabric:
    """Load the only orchestration binding for the three governance families."""

    root = repository_root.resolve()
    try:
        payload = yaml.safe_load((root / FABRIC_PATH).read_text(encoding="utf-8"))
        OfflineSchemaRegistry.from_directory(root / "schemas").validate(
            SCHEMA_ID,
            payload,
        )
    except (OSError, UnicodeError, yaml.YAMLError, SchemaValidationError) as exc:
        raise ValueError("governance enforcement fabric validation failed") from exc
    mapping = _mapping(payload, "governance enforcement fabric")
    family_mapping = _mapping(mapping["families"], "families")
    return GovernanceEnforcementFabric(
        fabric_id=_string(mapping["fabric_id"], "fabric_id"),
        version=_string(mapping["version"], "version"),
        authority_scope=_string(mapping["authority_scope"], "authority_scope"),
        families=tuple(
            _family(name, value) for name, value in sorted(family_mapping.items())
        ),
        quality_gate=_quality_gate(mapping["quality_gate"]),
    )


def evaluate_governance_enforcement_fabric(
    repository_root: Path,
    fabric: GovernanceEnforcementFabric,
    repository_paths: Iterable[str],
    locked_standard_hashes: Mapping[str, str],
) -> tuple[FabricViolation, ...]:
    """Evaluate shared chain integrity and domain checks on one path snapshot."""

    root = repository_root.resolve()
    # Materialize once so every domain receives the same reusable inventory.
    paths = tuple(
        sorted(
            {
                path.replace("\\", "/").removeprefix("./")
                for path in repository_paths
                if path.strip()
            }
        )
    )
    violations = list(
        _family_integrity_violations(root, fabric, locked_standard_hashes)
    )
    violations.extend(_quality_gate_violations(root, fabric))
    try:
        terminology = load_terminology_policy(root)
        for violation in evaluate_terminology_policy(
            root,
            terminology,
            paths,
        ):
            violations.append(
                FabricViolation(
                    "terminology",
                    violation.code,
                    violation.path,
                    violation.detail,
                    violation.blocker,
                )
            )
    except ValueError as exc:
        violations.append(
            FabricViolation(
                "terminology",
                "TERMINOLOGY_POLICY_INVALID",
                TERMINOLOGY_POLICY_PATH.as_posix(),
                f"Terminology policy failed validation: {exc}",
                True,
            )
        )
    try:
        technology = load_technology_language_policy(root)
        for technology_violation in evaluate_technology_language_policy(
            root,
            technology,
            paths,
        ):
            violations.append(
                FabricViolation(
                    "technology_language",
                    technology_violation.code,
                    technology_violation.path,
                    technology_violation.detail,
                    True,
                )
            )
    except ValueError as exc:
        violations.append(
            FabricViolation(
                "technology_language",
                "TECHNOLOGY_LANGUAGE_POLICY_INVALID",
                TECHNOLOGY_POLICY_PATH.as_posix(),
                f"Technology language policy failed validation: {exc}",
                True,
            )
        )
    return tuple(violations)


def _quality_gate_violations(
    root: Path,
    fabric: GovernanceEnforcementFabric,
) -> Iterable[FabricViolation]:
    quality_gate = fabric.quality_gate
    quality_items: tuple[GovernanceQualityPillar | GovernanceQualityAxis, ...] = (
        *quality_gate.pillars,
        *quality_gate.evaluation_axes,
    )
    required_paths = {
        quality_gate.authority_pyramid_ref,
        quality_gate.authority_graph_path,
        quality_gate.authority_development_matrix_path,
        quality_gate.quality_policy_path,
        *(
            path
            for item in quality_items
            for path in (*item.required_paths, *item.required_tests)
        ),
    }
    for relative in sorted(required_paths):
        if not (root / relative).is_file():
            yield FabricViolation(
                "quality_gate",
                "QUALITY_GATE_REQUIRED_PATH_MISSING",
                relative,
                "Governance quality gate required path is missing.",
                True,
            )

    try:
        policy_payload = yaml.safe_load(
            (root / quality_gate.quality_policy_path).read_text(encoding="utf-8")
        )
        standard_mappings = _quality_standard_mappings(policy_payload)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        yield FabricViolation(
            "quality_gate",
            "QUALITY_GATE_POLICY_INVALID",
            quality_gate.quality_policy_path,
            f"Quality gate policy failed validation: {exc}",
            True,
        )
        return

    for item in quality_items:
        selected_tests: set[str] = set()
        for mapping_name in item.standard_mapping_names:
            mapping_tests = standard_mappings.get(mapping_name)
            if mapping_tests is None:
                yield FabricViolation(
                    "quality_gate",
                    "QUALITY_GATE_MAPPING_MISSING",
                    quality_gate.quality_policy_path,
                    f"Required STANDARD mapping is missing: {mapping_name}.",
                    True,
                )
                continue
            selected_tests.update(mapping_tests)
        for required_test in item.required_tests:
            if required_test not in selected_tests:
                yield FabricViolation(
                    "quality_gate",
                    "QUALITY_GATE_TEST_NOT_ROUTED",
                    required_test,
                    (
                        f"{item.name} proof is not routed through its declared "
                        "STANDARD mappings."
                    ),
                    True,
                )

    try:
        matrix = load_authority_layer_development_matrix(root)
        graph = load_authority_graph(
            root / quality_gate.authority_graph_path,
            schema_root=root / "schemas",
        )
        for finding in validate_authority_graph_layer_development(graph, matrix):
            yield FabricViolation(
                "quality_gate",
                finding.code,
                finding.path,
                finding.detail,
                True,
            )
        yield from _authority_binding_violations(graph, fabric)
    except ValueError as exc:
        yield FabricViolation(
            "quality_gate",
            "AUTHORITY_DEVELOPMENT_GATE_INVALID",
            quality_gate.authority_development_matrix_path,
            f"Authority development gate failed validation: {exc}",
            True,
        )


def _authority_binding_violations(
    graph: AuthorityGraph,
    fabric: GovernanceEnforcementFabric,
) -> Iterable[FabricViolation]:
    quality_gate = fabric.quality_gate
    nodes_by_path = {node.canonical_path: node for node in graph.nodes}
    required_paths = {
        quality_gate.authority_pyramid_ref,
        FABRIC_PATH.as_posix(),
        quality_gate.authority_development_matrix_path,
        *(family.standard_path for family in fabric.families),
    }
    for path in sorted(required_paths - nodes_by_path.keys()):
        yield FabricViolation(
            "quality_gate",
            "AUTHORITY_BINDING_NODE_MISSING",
            path,
            "Authority graph is missing a quality-gate authority node.",
            True,
        )

    core = nodes_by_path.get(quality_gate.authority_pyramid_ref)
    fabric_node = nodes_by_path.get(FABRIC_PATH.as_posix())
    matrix_node = nodes_by_path.get(quality_gate.authority_development_matrix_path)
    expected_edges: list[tuple[str, str]] = []
    if core is not None and matrix_node is not None:
        expected_edges.append((core.node_id, matrix_node.node_id))
    if fabric_node is not None:
        expected_edges.extend(
            (standard.node_id, fabric_node.node_id)
            for family in fabric.families
            if (standard := nodes_by_path.get(family.standard_path)) is not None
        )
    actual_edges = {
        (edge.from_node_id, edge.to_node_id)
        for edge in graph.edges
        if edge.relation.value == "GOVERNS"
    }
    for source, target in sorted(set(expected_edges) - actual_edges):
        yield FabricViolation(
            "quality_gate",
            "AUTHORITY_BINDING_EDGE_MISSING",
            quality_gate.authority_graph_path,
            f"Required GOVERNS edge is missing: {source} -> {target}.",
            True,
        )


def _family_integrity_violations(
    root: Path,
    fabric: GovernanceEnforcementFabric,
    locked_standard_hashes: Mapping[str, str],
) -> Iterable[FabricViolation]:
    for family in fabric.families:
        standard = root / family.standard_path
        if not standard.is_file():
            yield _blocker(
                family,
                "STANDARD_MISSING",
                family.standard_path,
                "Normative standard is missing from the repository.",
            )
            continue
        metadata = _frontmatter(standard)
        for field, expected in {
            "document_id": family.standard_id,
            "version": family.standard_version,
            "canonical_path": family.standard_path,
            "authority_scope": family.authority_scope,
        }.items():
            if metadata.get(field) != expected:
                yield _blocker(
                    family,
                    "STANDARD_VERSION_MISMATCH",
                    family.standard_path,
                    f"Normative standard {field} does not match its fabric binding.",
                )
        current_hash = _sha256(standard)
        if current_hash != family.standard_content_sha256:
            yield _blocker(
                family,
                "STANDARD_HASH_MISMATCH",
                family.standard_path,
                "Normative standard content does not match the fabric binding.",
            )
        lock_hash = locked_standard_hashes.get(family.standard_path)
        if lock_hash is None:
            yield _blocker(
                family,
                "UNREGISTERED_POLICY_PROJECTION",
                family.standard_path,
                "Normative standard is not registered in the governed document lock.",
            )
        elif lock_hash != family.standard_content_sha256:
            yield _blocker(
                family,
                "STANDARD_HASH_MISMATCH",
                family.standard_path,
                "Fabric hash must reference the governed document lock hash.",
            )
        if not (root / family.projection_path).is_file():
            yield _blocker(
                family,
                "POLICY_MISSING",
                family.projection_path,
                "Required enforcement projection is missing.",
            )
        if family.schema_path is not None and not (root / family.schema_path).is_file():
            yield _blocker(
                family,
                "SCHEMA_MISSING",
                family.schema_path,
                "Required enforcement projection schema is missing.",
            )


def _family(name: str, value: object) -> EnforcementFamily:
    mapping = _mapping(value, f"family {name}")
    schema_value = mapping["schema_path"]
    return EnforcementFamily(
        name=name,
        authority_scope=_string(mapping["authority_scope"], "authority_scope"),
        standard_path=_safe_path(mapping["standard_path"], "standard_path"),
        standard_id=_string(mapping["standard_id"], "standard_id"),
        standard_version=_string(mapping["standard_version"], "standard_version"),
        standard_content_sha256=_sha256_text(
            _string(mapping["standard_content_sha256"], "standard_content_sha256")
        ),
        projection_path=_safe_path(mapping["projection_path"], "projection_path"),
        schema_path=(
            _safe_path(schema_value, "schema_path")
            if schema_value is not None
            else None
        ),
    )


def _quality_gate(value: object) -> GovernanceQualityGate:
    mapping = _mapping(value, "quality_gate")
    separation = _mapping(mapping["authority_separation"], "authority_separation")
    pillar_mapping = _mapping(mapping["pillars"], "pillars")
    axis_mapping = _mapping(mapping["evaluation_axes"], "evaluation_axes")
    return GovernanceQualityGate(
        authority_pyramid_ref=_safe_path(
            mapping["authority_pyramid_ref"], "authority_pyramid_ref"
        ),
        authority_graph_path=_safe_path(
            mapping["authority_graph_path"], "authority_graph_path"
        ),
        authority_development_matrix_path=_safe_path(
            mapping["authority_development_matrix_path"],
            "authority_development_matrix_path",
        ),
        quality_policy_path=_safe_path(
            mapping["quality_policy_path"], "quality_policy_path"
        ),
        minimum_profile=_string(mapping["minimum_profile"], "minimum_profile"),
        deterministic_quality_gate=_string(
            separation["deterministic_quality_gate"], "deterministic_quality_gate"
        ),
        deterministic_governance_gate=_string(
            separation["deterministic_governance_gate"],
            "deterministic_governance_gate",
        ),
        human_governance=_string(separation["human_governance"], "human_governance"),
        pillars=tuple(
            _quality_pillar(name, child)
            for name, child in sorted(pillar_mapping.items())
        ),
        evaluation_axes=tuple(
            _quality_axis(name, child) for name, child in sorted(axis_mapping.items())
        ),
    )


def _quality_pillar(name: str, value: object) -> GovernanceQualityPillar:
    mapping = _mapping(value, f"quality pillar {name}")
    return GovernanceQualityPillar(
        name=name,
        semantic_role=_string(mapping["semantic_role"], "semantic_role"),
        standard_mapping_names=_safe_paths(
            mapping["standard_mapping_names"], "standard_mapping_names", paths=False
        ),
        required_paths=_safe_paths(mapping["required_paths"], "required_paths"),
        required_tests=_safe_paths(mapping["required_tests"], "required_tests"),
    )


def _quality_axis(name: str, value: object) -> GovernanceQualityAxis:
    mapping = _mapping(value, f"quality axis {name}")
    return GovernanceQualityAxis(
        name=name,
        objective=_string(mapping["objective"], "objective"),
        standard_mapping_names=_safe_paths(
            mapping["standard_mapping_names"], "standard_mapping_names", paths=False
        ),
        required_paths=_safe_paths(mapping["required_paths"], "required_paths"),
        required_tests=_safe_paths(mapping["required_tests"], "required_tests"),
    )


def _quality_standard_mappings(value: object) -> dict[str, tuple[str, ...]]:
    payload = _mapping(value, "quality policy")
    standard = _mapping(payload["standard_impact_tests"], "standard_impact_tests")
    mappings = standard.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("standard_impact_tests.mappings must be a list")
    resolved: dict[str, tuple[str, ...]] = {}
    for item in mappings:
        mapping = _mapping(item, "standard impact mapping")
        name = _string(mapping["name"], "mapping name")
        if name in resolved:
            raise ValueError(f"duplicate STANDARD mapping: {name}")
        tests = mapping.get("tests", [])
        if not isinstance(tests, list):
            raise ValueError("mapping tests must be a list")
        resolved[name] = tuple(_safe_path(test, "mapping tests") for test in tests)
    return resolved


def _blocker(
    family: EnforcementFamily,
    code: str,
    path: str,
    detail: str,
) -> FabricViolation:
    return FabricViolation(family.name, code, path, detail, True)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    return _mapping(yaml.safe_load(text.split("---", maxsplit=2)[1]), "frontmatter")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("standard_content_sha256 must be lower-case SHA-256")
    return value


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return {str(key): child for key, child in value.items()}


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _safe_path(value: object, name: str) -> str:
    path = _string(value, name)
    if Path(path).is_absolute() or "\\" in path or ".." in Path(path).parts:
        raise ValueError(f"{name} must be a repository-relative POSIX path")
    return path


def _safe_paths(
    value: object,
    name: str,
    *,
    paths: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    normalized = tuple(
        _safe_path(item, name) if paths else _string(item, name) for item in value
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    return normalized

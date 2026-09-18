"""Deterministic, non-authoritative architecture projection contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

_GENERATED_DOCUMENT_ID = "AI4B-ARCH-PROJECTION-VIEW-001"
_RUNTIME_ROOT_NAME = "runtime"


@dataclass(frozen=True, slots=True)
class ArchitectureProjectionComponent:
    """One declared component mapping without execution or policy authority."""

    component_id: str
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
    source_of_truth: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for name, value in (
            ("component id", self.component_id),
            ("canonical domain", self.canonical_domain),
            ("logical plane", self.logical_plane),
            ("dependency layer", self.dependency_layer),
            ("runtime class", self.runtime_class),
            ("owner", self.owner),
            ("authority effect", self.authority_effect),
        ):
            if not value.strip():
                raise ValueError(f"architecture projection {name} is required")
        for name, paths in (
            ("source paths", self.source_paths),
            ("contract references", self.contract_refs),
            ("test references", self.test_refs),
        ):
            if not paths or any(not path.strip() for path in paths):
                raise ValueError(f"architecture projection {name} are required")
            if len(paths) != len(set(paths)):
                raise ValueError(f"architecture projection {name} must be unique")
            if any(_is_unsafe_path(path) for path in paths):
                raise ValueError(
                    f"architecture projection {name} must be repository-relative"
                )
        if self.source_of_truth:
            raise ValueError("architecture projection cannot become a source of truth")
        if self.execution_allowed:
            raise ValueError("architecture projection cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("architecture projection must remain live-order blocked")

    def to_payload(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
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
            "source_of_truth": False,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class CanonicalArchitectureProjection:
    """Read-only component crosswalk for deterministic change-impact analysis."""

    projection_id: str
    components: tuple[ArchitectureProjectionComponent, ...]
    projection_sha256: str
    source_of_truth: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.projection_id.strip():
            raise ValueError("architecture projection id is required")
        if not self.components:
            raise ValueError("architecture projection requires components")
        component_ids = tuple(component.component_id for component in self.components)
        if component_ids != tuple(sorted(component_ids)):
            raise ValueError("architecture projection components must be sorted")
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("architecture projection component ids must be unique")
        if len(self.projection_sha256) != 64:
            raise ValueError("architecture projection hash is invalid")
        if self.source_of_truth:
            raise ValueError("architecture projection cannot become a source of truth")
        if self.execution_allowed:
            raise ValueError("architecture projection cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("architecture projection must remain live-order blocked")

    def components_for_paths(
        self, changed_paths: tuple[str, ...]
    ) -> tuple[ArchitectureProjectionComponent, ...]:
        """Return stable impacted components for exact repository-relative paths."""
        if any(_is_unsafe_path(path) for path in changed_paths):
            raise ValueError("architecture impact paths must be repository-relative")
        changed = frozenset(changed_paths)
        return tuple(
            component
            for component in self.components
            if changed.intersection(component.source_paths)
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "components": [component.to_payload() for component in self.components],
            "source_of_truth": False,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class ArchitectureProjectionImpact:
    """Read-only change impact that keeps incomplete mapping visible."""

    projection_id: str
    projection_sha256: str
    changed_paths: tuple[str, ...]
    impacted_component_ids: tuple[str, ...]
    unmapped_paths: tuple[str, ...]
    blockers: tuple[str, ...]
    status: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.projection_id.strip() or len(self.projection_sha256) != 64:
            raise ValueError("architecture projection impact identity is invalid")
        for name, values in (
            ("changed paths", self.changed_paths),
            ("impacted component ids", self.impacted_component_ids),
            ("unmapped paths", self.unmapped_paths),
            ("blockers", self.blockers),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    f"architecture projection impact {name} must be unique"
                )
        if self.changed_paths != tuple(sorted(self.changed_paths)):
            raise ValueError("architecture projection impact paths must be sorted")
        if any(_is_unsafe_path(path) for path in self.changed_paths):
            raise ValueError(
                "architecture projection impact paths must be repository-relative"
            )
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("architecture projection impact status is invalid")
        if bool(self.unmapped_paths) != (self.status == "RUNNING_WITH_BLOCKERS"):
            raise ValueError(
                "architecture projection impact status must reflect mapping"
            )
        if self.execution_allowed:
            raise ValueError(
                "architecture projection impact cannot authorize execution"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError(
                "architecture projection impact must remain live-order blocked"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "changed_paths": list(self.changed_paths),
            "impacted_component_ids": list(self.impacted_component_ids),
            "unmapped_paths": list(self.unmapped_paths),
            "blockers": list(self.blockers),
            "status": self.status,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_canonical_architecture_projection(
    *,
    projection_id: str,
    components: tuple[ArchitectureProjectionComponent, ...],
) -> CanonicalArchitectureProjection:
    """Build a hash-addressed, non-authoritative projection from declared inputs."""
    canonical_components = tuple(
        sorted(
            (_canonical_component(component) for component in components),
            key=lambda item: item.component_id,
        )
    )
    payload = {
        "projection_id": projection_id,
        "components": [component.to_payload() for component in canonical_components],
        "source_of_truth": False,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    return CanonicalArchitectureProjection(
        projection_id=projection_id,
        components=canonical_components,
        projection_sha256=sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    )


def analyze_architecture_projection_impact(
    projection: CanonicalArchitectureProjection,
    changed_paths: tuple[str, ...],
) -> ArchitectureProjectionImpact:
    """Analyze declared impact and block on every path absent from the projection."""
    if not changed_paths:
        raise ValueError("architecture projection impact requires changed paths")
    if len(changed_paths) != len(set(changed_paths)):
        raise ValueError("architecture projection impact paths must be unique")
    if any(_is_unsafe_path(path) for path in changed_paths):
        raise ValueError(
            "architecture projection impact paths must be repository-relative"
        )
    canonical_paths = tuple(sorted(changed_paths))
    impacted_components = projection.components_for_paths(canonical_paths)
    mapped_paths = frozenset(
        path for component in impacted_components for path in component.source_paths
    )
    unmapped_paths = tuple(path for path in canonical_paths if path not in mapped_paths)
    blockers = tuple(
        f"ARCHITECTURE_PROJECTION_UNMAPPED_PATH:{path}" for path in unmapped_paths
    )
    return ArchitectureProjectionImpact(
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        changed_paths=canonical_paths,
        impacted_component_ids=tuple(
            component.component_id for component in impacted_components
        ),
        unmapped_paths=unmapped_paths,
        blockers=blockers,
        status="READY" if not unmapped_paths else "RUNNING_WITH_BLOCKERS",
    )


def render_architecture_projection_markdown(
    projection: CanonicalArchitectureProjection,
) -> str:
    """Render an evidence-only Markdown view from a declared projection."""
    lines = [
        "---",
        f"document_id: {_GENERATED_DOCUMENT_ID}",
        "title: Canonical Architecture Projection Generated View",
        "document_type: REFERENCE",
        f"projection_id: {projection.projection_id}",
        f"projection_sha256: {projection.projection_sha256}",
        "authority_level: INFORMATIONAL",
        "authority_effect: EVIDENCE_ONLY",
        "content_role: GENERATED",
        "source_of_truth: false",
        "execution_allowed: false",
        "live_eligibility_status: LIVE_ORDER_BLOCKED",
        "---",
        "",
        "# Canonical Architecture Projection Generated View",
        "",
        "This generated view is evidence-only. It does not define architecture, "
        "grant approval, authorize promotion, or permit execution.",
        "",
        "## Components",
        "",
        "| Component | Domain | Plane | Layer | Runtime | Owner | Effect |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        "| "
        + " | ".join(
            (
                _markdown_table(component.component_id),
                _markdown_table(component.canonical_domain),
                _markdown_table(component.logical_plane),
                _markdown_table(component.dependency_layer),
                _markdown_table(component.runtime_class),
                _markdown_table(component.owner),
                _markdown_table(component.authority_effect),
            )
        )
        + " |"
        for component in projection.components
    )
    lines.extend(
        (
            "",
            "## Safety Boundary",
            "",
            "- This artifact is generated from declared component inputs.",
            "- Missing canonical mapping remains `NOT_PROVIDED`, not inferred.",
            "- Live eligibility remains `LIVE_ORDER_BLOCKED`.",
            "",
        )
    )
    return "\n".join(lines)


def write_runtime_architecture_projection_markdown(
    projection: CanonicalArchitectureProjection,
    root: Path,
    output_path: Path,
) -> Path:
    """Write a generated projection view only below the repository runtime root."""
    resolved_root = root.resolve()
    resolved_output = (
        output_path.resolve()
        if output_path.is_absolute()
        else (resolved_root / output_path).resolve()
    )
    try:
        relative_output = resolved_output.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(
            "architecture projection output must stay inside the repository"
        ) from error
    if not relative_output.parts or relative_output.parts[0] != _RUNTIME_ROOT_NAME:
        raise ValueError("architecture projection output must stay below runtime")
    if resolved_output.suffix != ".md":
        raise ValueError("architecture projection output must use the .md extension")

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        render_architecture_projection_markdown(projection), encoding="utf-8"
    )
    return resolved_output


def _canonical_component(
    component: ArchitectureProjectionComponent,
) -> ArchitectureProjectionComponent:
    return replace(
        component,
        source_paths=tuple(sorted(component.source_paths)),
        contract_refs=tuple(sorted(component.contract_refs)),
        test_refs=tuple(sorted(component.test_refs)),
    )


def _is_unsafe_path(path: str) -> bool:
    normalized_path = path.replace("\\", "/")
    return (
        normalized_path.startswith("/")
        or (len(normalized_path) > 1 and normalized_path[1] == ":")
        or ".." in normalized_path.split("/")
    )


def _markdown_table(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")

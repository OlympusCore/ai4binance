"""Deterministic graph views for the logical-architecture registry."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.governance.architecture.model import (
    LogicalArchitectureRegistry,
    LogicalArchitectureRelation,
    LogicalRelationType,
)

_DEPENDENCY_RELATION_TYPES = frozenset(
    {LogicalRelationType.CONSUMES, LogicalRelationType.DEPENDS_ON}
)


@dataclass(frozen=True, slots=True)
class LogicalArchitectureGraph:
    """A deterministic, read-only graph view with no operational authority."""

    registry: LogicalArchitectureRegistry

    def dependencies_of(self, component_id: str) -> tuple[str, ...]:
        """Return stable declared dependencies for one registered component."""
        self._require_component(component_id)
        return tuple(
            sorted(
                relation.to_component_id
                for relation in self._dependency_relations()
                if relation.from_component_id == component_id
            )
        )

    def dependents_of(self, component_id: str) -> tuple[str, ...]:
        """Return stable declared dependents for one registered component."""
        self._require_component(component_id)
        return tuple(
            sorted(
                relation.from_component_id
                for relation in self._dependency_relations()
                if relation.to_component_id == component_id
            )
        )

    def dependency_cycles(self) -> tuple[tuple[str, ...], ...]:
        """Report dependency cycles deterministically; an empty result is acyclic."""
        dependencies = {
            component.component_id: self.dependencies_of(component.component_id)
            for component in self.registry.components
        }
        cycles: set[tuple[str, ...]] = set()
        for component_id in sorted(dependencies):
            _visit_dependency_path(component_id, dependencies, (), cycles)
        return tuple(sorted(cycles))

    def assert_acyclic_dependencies(self) -> None:
        """Reject dependency cycles while retaining non-dependency flow relations."""
        cycles = self.dependency_cycles()
        if cycles:
            rendered = "; ".join(" -> ".join(cycle) for cycle in cycles)
            raise ValueError(
                f"logical architecture dependency cycle detected: {rendered}"
            )

    def _dependency_relations(self) -> tuple[LogicalArchitectureRelation, ...]:
        return tuple(
            relation
            for relation in self.registry.relations
            if relation.relation_type in _DEPENDENCY_RELATION_TYPES
        )

    def _require_component(self, component_id: str) -> None:
        if component_id not in {
            component.component_id for component in self.registry.components
        }:
            raise ValueError(f"unknown logical architecture component: {component_id}")


def _visit_dependency_path(
    component_id: str,
    dependencies: dict[str, tuple[str, ...]],
    path: tuple[str, ...],
    cycles: set[tuple[str, ...]],
) -> None:
    if component_id in path:
        cycle = (*path[path.index(component_id) :], component_id)
        cycles.add(_canonical_cycle(cycle))
        return
    for dependency_id in dependencies[component_id]:
        _visit_dependency_path(
            dependency_id,
            dependencies,
            (*path, component_id),
            cycles,
        )


def _canonical_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    nodes = cycle[:-1]
    rotations = tuple(nodes[index:] + nodes[:index] for index in range(len(nodes)))
    canonical_nodes = min(rotations)
    return (*canonical_nodes, canonical_nodes[0])

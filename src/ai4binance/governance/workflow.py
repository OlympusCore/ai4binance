"""Read-only typed workflow graphs for research observability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowAuthority(StrEnum):
    READ_ONLY = "READ_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_PROPOSAL = "PAPER_PROPOSAL"


class WorkflowPreviewStatus(StrEnum):
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    node_id: str
    node_type: str
    dependencies: tuple[str, ...]
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    timeout_seconds: int
    authority: WorkflowAuthority
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.node_type.strip():
            raise ValueError("workflow node identity is required")
        if not 1 <= self.timeout_seconds <= 3_600:
            raise ValueError("workflow node timeout is invalid")
        groups = (self.dependencies, self.input_artifacts, self.output_artifacts)
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("workflow node lists must be unique")
        if self.execution_allowed:
            raise ValueError("workflow graph cannot authorize execution")


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    graph_id: str
    nodes: tuple[WorkflowNode, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.graph_id.strip() or not self.nodes:
            raise ValueError("workflow graph requires identity and nodes")
        identities = tuple(node.node_id for node in self.nodes)
        if len(set(identities)) != len(identities):
            raise ValueError("workflow node identities must be unique")
        known = set(identities)
        if any(set(node.dependencies) - known for node in self.nodes):
            raise ValueError("workflow dependency is unknown")
        if self.execution_allowed:
            raise ValueError("workflow graph cannot authorize execution")
        self.topological_order()

    def topological_order(self) -> tuple[str, ...]:
        dependencies = {node.node_id: set(node.dependencies) for node in self.nodes}
        ordered: list[str] = []
        while dependencies:
            ready = sorted(
                node_id for node_id, required in dependencies.items() if not required
            )
            if not ready:
                raise ValueError("workflow graph contains a cycle")
            ordered.extend(ready)
            for node_id in ready:
                del dependencies[node_id]
            for required in dependencies.values():
                required.difference_update(ready)
        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class WorkflowPreview:
    graph_id: str
    topological_order: tuple[str, ...]
    validation_points: tuple[str, ...]
    status: WorkflowPreviewStatus = WorkflowPreviewStatus.HUMAN_REVIEW_REQUIRED
    blockers: tuple[str, ...] = ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.graph_id.strip():
            raise ValueError("workflow preview identity is required")
        if not self.topological_order or not self.validation_points:
            raise ValueError("workflow preview requires order and validation points")
        if set(self.validation_points) - set(self.topological_order):
            raise ValueError("workflow preview validation point is unknown")
        if (
            self.status is not WorkflowPreviewStatus.HUMAN_REVIEW_REQUIRED
            or "HUMAN_REVIEW_REQUIRED" not in self.blockers
            or "LIVE_ORDER_BLOCKED" not in self.blockers
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "workflow preview must remain review-only and live blocked"
            )


def preview_workflow(
    graph: WorkflowGraph,
    *,
    validation_points: tuple[str, ...],
) -> WorkflowPreview:
    return WorkflowPreview(
        graph_id=graph.graph_id,
        topological_order=graph.topological_order(),
        validation_points=validation_points,
    )


def market_outlook_workflow() -> WorkflowGraph:
    definitions = (
        ("market_data", "MARKET_DATA", (), WorkflowAuthority.READ_ONLY),
        (
            "market_outlook",
            "MARKET_OUTLOOK",
            ("market_data",),
            WorkflowAuthority.RESEARCH_ONLY,
        ),
        (
            "setup_radar",
            "SETUP_RADAR",
            ("market_outlook",),
            WorkflowAuthority.RESEARCH_ONLY,
        ),
        (
            "candidate_arbitration",
            "CANDIDATE_ARBITRATION",
            ("setup_radar",),
            WorkflowAuthority.RESEARCH_ONLY,
        ),
        (
            "risk_evaluation",
            "RISK_EVALUATION",
            ("candidate_arbitration",),
            WorkflowAuthority.RESEARCH_ONLY,
        ),
        (
            "paper_proposal",
            "PAPER_PROPOSAL",
            ("risk_evaluation",),
            WorkflowAuthority.PAPER_PROPOSAL,
        ),
        (
            "closure_review",
            "CLOSURE_REVIEW",
            ("paper_proposal",),
            WorkflowAuthority.READ_ONLY,
        ),
    )
    return WorkflowGraph(
        graph_id="market-outlook-intelligent-engine",
        nodes=tuple(
            WorkflowNode(
                node_id=node_id,
                node_type=node_type,
                dependencies=dependencies,
                input_artifacts=(),
                output_artifacts=(f"{node_id}.json",),
                timeout_seconds=60,
                authority=authority,
            )
            for node_id, node_type, dependencies, authority in definitions
        ),
    )

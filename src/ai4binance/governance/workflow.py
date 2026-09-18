"""Read-only typed workflow graphs for research observability."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

OPPORTUNITY_RESEARCH_BRANCH_IDS = (
    "market_outlook_branch",
    "setup_family_branch",
    "backtest_oos_branch",
    "portfolio_context_branch",
    "whale_fusion_branch",
)
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")


class WorkflowAuthority(StrEnum):
    READ_ONLY = "READ_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_PROPOSAL = "PAPER_PROPOSAL"


class OpportunityArtifactReviewStatus(StrEnum):
    PASSED = "PASSED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_OPPORTUNITY = "RESEARCH_ONLY_OPPORTUNITY"
    CONFLICTING = "CONFLICTING"


class OpportunityArtifactReductionStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_OPPORTUNITY = "RESEARCH_ONLY_OPPORTUNITY"


class AgentModelCandidateStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_PROVIDER = "RESEARCH_ONLY_PROVIDER"


class AgentWorkspaceComponentStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_WORKSPACE = "RESEARCH_ONLY_WORKSPACE"


class AgentSkillCandidateStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_SKILL = "RESEARCH_ONLY_SKILL"


class AgentWorkspaceComponentType(StrEnum):
    SKILL = "SKILL"
    SUBAGENT = "SUBAGENT"
    HOOK = "HOOK"
    MCP = "MCP"
    WORKFLOW_YAML = "WORKFLOW_YAML"
    CANARY = "CANARY"


class MarkdownGovernanceArtifactRole(StrEnum):
    AGENT_ONBOARDING = "AGENT_ONBOARDING"
    SKILL_PROCEDURE = "SKILL_PROCEDURE"
    SPECIFICATION = "SPECIFICATION"
    PLAN = "PLAN"
    TASKS = "TASKS"
    REVIEW = "REVIEW"
    ARCHITECTURE = "ARCHITECTURE"
    DOMAIN_RULES = "DOMAIN_RULES"
    MEMORY = "MEMORY"
    VENDOR_BRIDGE = "VENDOR_BRIDGE"


class MarkdownGovernanceReviewerResult(StrEnum):
    PASSED = "PASSED"
    PENDING = "PENDING"
    WATCHLIST = "WATCHLIST"
    CONFLICTING = "CONFLICTING"


class MarkdownGovernanceReviewStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_DOCUMENTATION = "RESEARCH_ONLY_DOCUMENTATION"


class GraphArchitectureReadinessStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_GRAPH_PATTERN = "RESEARCH_ONLY_GRAPH_PATTERN"


class GraphWorkflowManifestReviewStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_GRAPH_WORKFLOW = "RESEARCH_ONLY_GRAPH_WORKFLOW"


class AgentLoopScale(StrEnum):
    SINGLE_AGENT = "SINGLE_AGENT"
    FLEET = "FLEET"


class AgentLoopType(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"


class ClosedLoopAdmissionStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_LOOP = "RESEARCH_ONLY_LOOP"


class ClosedLoopRunTriggerType(StrEnum):
    HEARTBEAT = "HEARTBEAT"
    CRON = "CRON"
    HOOK = "HOOK"
    GOAL = "GOAL"


class GraphRunTerminalState(StrEnum):
    COMPLETED = "COMPLETED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class GraphNodeRouteDecisionType(StrEnum):
    PASSED = "PASSED"
    RETRY = "RETRY"
    REROUTE = "REROUTE"
    ESCALATE = "ESCALATE"
    STOP = "STOP"


class AgentArchitectureLayer(StrEnum):
    HARNESS = "HARNESS"
    LOOP = "LOOP"
    GRAPH = "GRAPH"


AGENT_ARCHITECTURE_LAYERS = (
    AgentArchitectureLayer.HARNESS,
    AgentArchitectureLayer.LOOP,
    AgentArchitectureLayer.GRAPH,
)
_AGENT_ARCHITECTURE_REQUIRED_CONTROL_POINTS = {
    AgentArchitectureLayer.HARNESS: ("permissions", "sandbox", "audit"),
    AgentArchitectureLayer.LOOP: ("stop_condition", "verifier", "budget"),
    AgentArchitectureLayer.GRAPH: ("topology", "reducer", "route_state"),
}


class AgentArchitectureLayerStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_ARCHITECTURE = "RESEARCH_ONLY_ARCHITECTURE"


class AgentInvocationCoverageStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_AGENT_INVOCATION = "RESEARCH_ONLY_AGENT_INVOCATION"


class LoopBuildingBlockCoverageStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_LOOP = "RESEARCH_ONLY_LOOP"


class EvaluatorGateStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_EVALUATOR_GATE = "RESEARCH_ONLY_EVALUATOR_GATE"


class EvaluatorGateBlastRadiusLane(StrEnum):
    REVERSIBLE_CONTAINED = "REVERSIBLE_CONTAINED"
    REVERSIBLE_WIDE = "REVERSIBLE_WIDE"
    HARD_TO_REVERSE = "HARD_TO_REVERSE"


class ResidualEdgeReviewStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_RESIDUAL_EDGE = "RESEARCH_ONLY_RESIDUAL_EDGE"
    NO_TRADE = "NO_TRADE"


class CoworkTaskSuitabilityStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_COWORK_TASK = "RESEARCH_ONLY_COWORK_TASK"


class AgentTrajectoryLearningEligibilityStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_TRAJECTORY_LEARNING = "RESEARCH_ONLY_TRAJECTORY_LEARNING"


class GraphDependencyIntegrityStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_GRAPH_DEPENDENCY = "RESEARCH_ONLY_GRAPH_DEPENDENCY"


class LoopEngineeringReadinessStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_LOOP_PATTERN = "RESEARCH_ONLY_LOOP_PATTERN"


class WorkflowEdgeAuditStatus(StrEnum):
    REAL_EDGES_VERIFIED = "REAL_EDGES_VERIFIED"
    WATCHLIST = "WATCHLIST"


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


@dataclass(frozen=True, slots=True)
class WorkflowEdgeAudit:
    graph_id: str
    status: WorkflowEdgeAuditStatus
    real_edges: tuple[str, ...]
    fake_edges: tuple[str, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_GRAPH_PATTERN"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.graph_id.strip():
            raise ValueError("workflow edge audit identity is required")
        for values in (self.real_edges, self.fake_edges, self.blockers):
            _require_unique_nonblank("workflow edge audit lists", values)
        if (
            self.status is WorkflowEdgeAuditStatus.REAL_EDGES_VERIFIED
            and self.fake_edges
        ):
            raise ValueError("verified workflow edge audit cannot contain fake edges")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("workflow edge audit must keep live blocker visible")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("workflow edge audit requires human review")
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_PATTERN"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("workflow edge audit cannot promote or execute")


@dataclass(frozen=True, slots=True)
class GraphRunNodeCheckpoint:
    run_id: str
    node_id: str
    input_artifact_sha256: str
    output_artifact_sha256: str
    started_at: datetime
    finished_at: datetime
    reviewer_result: str
    retry_count: int
    cost_units: int
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            not self.run_id.strip()
            or not self.node_id.strip()
            or not self.reviewer_result.strip()
        ):
            raise ValueError("graph run checkpoint identity is required")
        if not _SHA256_HEX_RE.fullmatch(self.input_artifact_sha256):
            raise ValueError("graph run checkpoint input hash is invalid")
        if not _SHA256_HEX_RE.fullmatch(self.output_artifact_sha256):
            raise ValueError("graph run checkpoint output hash is invalid")
        _require_timezone_aware("graph run checkpoint start", self.started_at)
        _require_timezone_aware("graph run checkpoint finish", self.finished_at)
        if self.finished_at < self.started_at:
            raise ValueError("graph run checkpoint finish precedes start")
        if self.retry_count < 0 or self.cost_units < 0:
            raise ValueError("graph run checkpoint counters are invalid")
        _require_unique_nonblank("graph run checkpoint blockers", self.blockers)
        if self.execution_allowed:
            raise ValueError("graph run checkpoint cannot authorize execution")


@dataclass(frozen=True, slots=True)
class GraphRunTrace:
    run_id: str
    graph_id: str
    terminal_state: GraphRunTerminalState
    checkpoints: tuple[GraphRunNodeCheckpoint, ...]
    blockers: tuple[str, ...]
    max_cost_units: int
    max_retry_count: int
    promotion_status: str = "RESEARCH_ONLY_GRAPH_RUN"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.graph_id.strip():
            raise ValueError("graph run trace identity is required")
        if not self.checkpoints:
            raise ValueError("graph run trace requires checkpoints")
        checkpoint_keys = tuple(
            (checkpoint.run_id, checkpoint.node_id) for checkpoint in self.checkpoints
        )
        if len(set(checkpoint_keys)) != len(checkpoint_keys):
            raise ValueError("graph run trace checkpoints must be unique per node")
        if any(checkpoint.run_id != self.run_id for checkpoint in self.checkpoints):
            raise ValueError("graph run trace checkpoint run identity mismatch")
        if self.max_cost_units < 1 or self.max_retry_count < 0:
            raise ValueError("graph run trace budgets are invalid")
        _require_unique_nonblank("graph run trace blockers", self.blockers)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("graph run trace requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("graph run trace must keep live blocked")
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_RUN"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("graph run trace cannot promote or execute")


@dataclass(frozen=True, slots=True)
class GraphNodeRouteDecision:
    """Per-node graph route evidence; routing remains advisory and review-only."""

    run_id: str
    graph_id: str
    node_id: str
    decision: GraphNodeRouteDecisionType
    reason: str
    target_node: str
    input_artifact_sha256: str
    output_artifact_sha256: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    retry_count: int
    cost_units: int
    reviewer_result: str
    promotion_status: str = "RESEARCH_ONLY_GRAPH_ROUTE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.run_id.strip()
            or not self.graph_id.strip()
            or not self.node_id.strip()
            or not self.reason.strip()
            or not self.reviewer_result.strip()
        ):
            raise ValueError("graph node route decision identity is required")
        if not _SHA256_HEX_RE.fullmatch(self.input_artifact_sha256):
            raise ValueError("graph node route decision input hash is invalid")
        if not _SHA256_HEX_RE.fullmatch(self.output_artifact_sha256):
            raise ValueError("graph node route decision output hash is invalid")
        for values in (self.citations, self.blockers):
            _require_unique_nonblank("graph node route decision lists", values)
        if self.retry_count < 0 or self.cost_units < 0:
            raise ValueError("graph node route decision counters are invalid")
        if self.decision is GraphNodeRouteDecisionType.PASSED and self.blockers:
            raise ValueError("passed graph node route cannot carry blockers")
        if (
            self.decision
            in {
                GraphNodeRouteDecisionType.RETRY,
                GraphNodeRouteDecisionType.REROUTE,
                GraphNodeRouteDecisionType.ESCALATE,
            }
            and not self.target_node.strip()
        ):
            raise ValueError("non-terminal graph route decision requires target node")
        if (
            self.decision is GraphNodeRouteDecisionType.STOP
            and self.target_node.strip()
        ):
            raise ValueError("stop graph route decision cannot target another node")
        if "LIVE_ORDER_BLOCKED" not in self.blockers and self.blockers:
            raise ValueError("blocked graph route decision must keep live blocked")
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_ROUTE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("graph node route decision cannot promote or execute")


@dataclass(frozen=True, slots=True)
class GraphNodeRouteReduction:
    graph_id: str
    run_id: str
    expected_nodes: tuple[str, ...]
    observed_nodes: tuple[str, ...]
    missing_nodes: tuple[str, ...]
    terminal_state: GraphRunTerminalState
    decisions: tuple[GraphNodeRouteDecision, ...]
    blockers: tuple[str, ...]
    max_cost_units: int
    max_retry_count: int
    promotion_status: str = "RESEARCH_ONLY_GRAPH_ROUTE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.graph_id.strip() or not self.run_id.strip():
            raise ValueError("graph node route reduction identity is required")
        for values in (
            self.expected_nodes,
            self.observed_nodes,
            self.missing_nodes,
            self.blockers,
        ):
            _require_unique_nonblank("graph node route reduction lists", values)
        if self.max_cost_units < 1 or self.max_retry_count < 0:
            raise ValueError("graph node route reduction budgets are invalid")
        if set(self.observed_nodes) - set(self.expected_nodes):
            raise ValueError("graph node route reduction observed an unknown node")
        if self.missing_nodes != tuple(
            node_id
            for node_id in self.expected_nodes
            if node_id not in self.observed_nodes
        ):
            raise ValueError(
                "graph node route reduction missing nodes are inconsistent"
            )
        decision_keys = tuple(
            (decision.run_id, decision.graph_id, decision.node_id)
            for decision in self.decisions
        )
        if len(set(decision_keys)) != len(decision_keys):
            raise ValueError("graph node route reduction decisions must be unique")
        if set(self.observed_nodes) != {
            decision.node_id for decision in self.decisions
        }:
            raise ValueError(
                "graph node route reduction observations must match decisions"
            )
        if any(
            decision.run_id != self.run_id or decision.graph_id != self.graph_id
            for decision in self.decisions
        ):
            raise ValueError("graph node route reduction decision identity mismatch")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("graph node route reduction requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("graph node route reduction must keep live blocked")
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_ROUTE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("graph node route reduction cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AgentArchitectureLayerEvidence:
    """Harness/loop/graph layer evidence; external agent ideas remain advisory."""

    workflow_id: str
    layer: AgentArchitectureLayer
    artifact_uri: str
    artifact_sha256: str
    citations: tuple[str, ...]
    control_points: tuple[str, ...]
    reviewer_result: str
    blockers: tuple[str, ...] = ()
    promotion_status: str = "RESEARCH_ONLY_AGENT_ARCHITECTURE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.workflow_id.strip()
            or not self.artifact_uri.strip()
            or not self.reviewer_result.strip()
        ):
            raise ValueError("agent architecture layer evidence identity is required")
        if not _SHA256_HEX_RE.fullmatch(self.artifact_sha256):
            raise ValueError("agent architecture layer evidence hash is invalid")
        for values in (self.citations, self.control_points, self.blockers):
            _require_unique_nonblank("agent architecture layer evidence lists", values)
        normalized_controls = {control.casefold() for control in self.control_points}
        if len(normalized_controls) != len(self.control_points):
            raise ValueError(
                "agent architecture layer evidence controls must be unique"
            )
        if "LIVE_ORDER_BLOCKED" not in self.blockers and self.blockers:
            raise ValueError(
                "blocked agent architecture evidence must keep live blocked"
            )
        if (
            self.promotion_status != "RESEARCH_ONLY_AGENT_ARCHITECTURE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or self.live_order_authority
        ):
            raise ValueError("agent architecture evidence cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AgentArchitectureLayerReduction:
    workflow_id: str
    expected_layers: tuple[AgentArchitectureLayer, ...]
    observed_layers: tuple[AgentArchitectureLayer, ...]
    missing_layers: tuple[AgentArchitectureLayer, ...]
    final_status: AgentArchitectureLayerStatus
    reviews: tuple[AgentArchitectureLayerEvidence, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_AGENT_ARCHITECTURE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise ValueError("agent architecture layer reduction identity is required")
        for layers in (self.expected_layers, self.observed_layers, self.missing_layers):
            if len(set(layers)) != len(layers):
                raise ValueError(
                    "agent architecture layer reduction lists must be unique"
                )
        if set(self.observed_layers) - set(self.expected_layers):
            raise ValueError("agent architecture reduction observed an unknown layer")
        if self.missing_layers != tuple(
            layer for layer in self.expected_layers if layer not in self.observed_layers
        ):
            raise ValueError(
                "agent architecture layer reduction missing layers are inconsistent"
            )
        review_keys = tuple(
            (review.workflow_id, review.layer) for review in self.reviews
        )
        if len(set(review_keys)) != len(review_keys):
            raise ValueError("agent architecture layer reviews must be unique")
        if {review.layer for review in self.reviews} != set(self.observed_layers):
            raise ValueError("agent architecture observations must match layer reviews")
        if any(review.workflow_id != self.workflow_id for review in self.reviews):
            raise ValueError("agent architecture layer review identity mismatch")
        _require_unique_nonblank(
            "agent architecture layer reduction blockers", self.blockers
        )
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent architecture layer reduction requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError(
                "agent architecture layer reduction must keep live blocked"
            )
        if (
            self.promotion_status != "RESEARCH_ONLY_AGENT_ARCHITECTURE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agent architecture reduction cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AgentArchitectureCoverageSummary:
    """Source-level Harness/Loop/Graph coverage summary for external opportunities."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: AgentArchitectureLayerStatus
    covered_layers: tuple[AgentArchitectureLayer, ...]
    missing_layers: tuple[AgentArchitectureLayer, ...]
    missing_control_points: tuple[str, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_AGENT_ARCHITECTURE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.source_uri.strip():
            raise ValueError("agent architecture coverage summary identity is required")
        if not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("agent architecture coverage summary hash is invalid")
        for layers in (self.covered_layers, self.missing_layers):
            if len(set(layers)) != len(layers):
                raise ValueError("agent architecture coverage layers must be unique")
        if set(self.covered_layers) & set(self.missing_layers):
            raise ValueError("agent architecture coverage layers cannot overlap")
        for values in (self.missing_control_points, self.blockers):
            _require_unique_nonblank(
                "agent architecture coverage summary lists", values
            )
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError(
                "agent architecture coverage summary requires human review"
            )
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError(
                "agent architecture coverage summary must keep live blocked"
            )
        if self.status is AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE and (
            self.missing_layers
            or self.missing_control_points
            or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        ):
            raise ValueError(
                "research-only architecture coverage summary cannot carry gaps"
            )
        if (
            self.promotion_status != "RESEARCH_ONLY_AGENT_ARCHITECTURE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agent architecture coverage summary cannot execute")


@dataclass(frozen=True, slots=True)
class AgentInvocationCoverageSummary:
    """Prompt/context coverage summary; invocation input remains advisory-only."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: AgentInvocationCoverageStatus
    prompt_revision: str
    prompt_sha256: str
    context_sources: tuple[str, ...]
    context_sha256: str
    context_freshness_policy: str
    citations: tuple[str, ...]
    redaction_applied: bool
    private_context_detected: bool
    tool_output_verified: bool
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_AGENT_INVOCATION"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.source_uri.strip():
            raise ValueError("agent invocation coverage summary identity is required")
        for name, value in (
            ("source", self.source_sha256),
            ("prompt", self.prompt_sha256),
            ("context", self.context_sha256),
        ):
            if value and not _SHA256_HEX_RE.fullmatch(value):
                raise ValueError(f"agent invocation coverage {name} hash is invalid")
        for values in (self.context_sources, self.citations, self.blockers):
            _require_unique_nonblank("agent invocation coverage summary lists", values)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent invocation coverage summary requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("agent invocation coverage summary must keep live blocked")
        if self.status is AgentInvocationCoverageStatus.RESEARCH_ONLY_AGENT_INVOCATION:
            if (
                not self.source_sha256
                or not self.prompt_revision.strip()
                or not self.prompt_sha256
                or not self.context_sources
                or not self.context_sha256
                or not self.context_freshness_policy.strip()
                or not self.citations
                or not self.redaction_applied
                or self.private_context_detected
                or not self.tool_output_verified
                or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
            ):
                raise ValueError(
                    "research-only invocation coverage summary cannot carry gaps"
                )
        if (
            self.promotion_status != "RESEARCH_ONLY_AGENT_INVOCATION"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agent invocation coverage summary cannot execute")


@dataclass(frozen=True, slots=True)
class LoopBuildingBlockCoverageSummary:
    """Loop building-block coverage summary; loop proposals remain review-only."""

    loop_id: str
    automation_trigger: str
    worktree_isolation: bool
    skills_declared: tuple[str, ...]
    connectors_declared: tuple[str, ...]
    subagent_roles: tuple[str, ...]
    memory_sources: tuple[str, ...]
    cost_budget: int
    stop_conditions: tuple[str, ...]
    human_handoff: bool
    status: LoopBuildingBlockCoverageStatus
    blockers: tuple[str, ...]
    parallel_edits: bool = False
    connector_credentials_required: bool = False
    memory_private_context_detected: bool = False
    trading_scope_touched: bool = False
    promotion_status: str = "RESEARCH_ONLY_LOOP"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.loop_id.strip():
            raise ValueError("loop building-block coverage identity is required")
        for values in (
            self.skills_declared,
            self.connectors_declared,
            self.subagent_roles,
            self.memory_sources,
            self.stop_conditions,
            self.blockers,
        ):
            _require_unique_nonblank("loop building-block coverage lists", values)
        if self.cost_budget < 0:
            raise ValueError("loop building-block coverage cost budget is invalid")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("loop building-block coverage requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("loop building-block coverage must keep live blocked")
        if self.status is LoopBuildingBlockCoverageStatus.RESEARCH_ONLY_LOOP:
            if (
                not self.automation_trigger.strip()
                or (self.parallel_edits and not self.worktree_isolation)
                or not self.skills_declared
                or not self.subagent_roles
                or not self.memory_sources
                or self.cost_budget < 1
                or not self.stop_conditions
                or not self.human_handoff
                or self.connector_credentials_required
                or self.memory_private_context_detected
                or self.trading_scope_touched
                or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
            ):
                raise ValueError(
                    "research-only loop building-block coverage cannot carry gaps"
                )
        if (
            self.promotion_status != "RESEARCH_ONLY_LOOP"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("loop building-block coverage cannot execute")


@dataclass(frozen=True, slots=True)
class EvaluatorGateReview:
    """Shadow evaluator gate evidence; it can review merges but never execute them."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: EvaluatorGateStatus
    generator_model_family: str
    judge_model_family: str
    judge_version: str
    rubric_hash: str
    rubric_text: str
    deterministic_checks: tuple[str, ...]
    trajectory_checks: tuple[str, ...]
    faithfulness_result: str
    task_completion_result: str
    verifier_canary_passed: bool
    blast_radius_lane: EvaluatorGateBlastRadiusLane
    human_disagreement_rate: float
    agent_self_assessment_weight: float
    shadow_mode: bool
    blockers: tuple[str, ...]
    trading_scope_touched: bool = False
    production_data_touched: bool = False
    money_movement_touched: bool = False
    promotion_status: str = "RESEARCH_ONLY_EVALUATOR_GATE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.source_uri.strip():
            raise ValueError("evaluator gate review identity is required")
        for hash_name, hash_value in (
            ("source", self.source_sha256),
            ("rubric", self.rubric_hash),
        ):
            if hash_value and not _SHA256_HEX_RE.fullmatch(hash_value):
                raise ValueError(f"evaluator gate {hash_name} hash is invalid")
        for values in (
            self.deterministic_checks,
            self.trajectory_checks,
            self.blockers,
        ):
            _require_unique_nonblank("evaluator gate review lists", values)
        for metric_name, metric_value in (
            ("human disagreement rate", self.human_disagreement_rate),
            ("agent self-assessment weight", self.agent_self_assessment_weight),
        ):
            if not math.isfinite(metric_value) or not 0 <= metric_value <= 1:
                raise ValueError(f"evaluator gate {metric_name} is invalid")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("evaluator gate review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("evaluator gate review must keep live blocked")
        if self.status is EvaluatorGateStatus.RESEARCH_ONLY_EVALUATOR_GATE:
            if (
                not self.source_uri.startswith("https://")
                or not self.source_sha256
                or not self.generator_model_family.strip()
                or not self.judge_model_family.strip()
                or self.generator_model_family == self.judge_model_family
                or not self.judge_version.strip()
                or not self.rubric_hash
                or not self.rubric_text.strip()
                or not self.deterministic_checks
                or not self.trajectory_checks
                or self.faithfulness_result != "PASSED"
                or self.task_completion_result != "PASSED"
                or not self.verifier_canary_passed
                or self.blast_radius_lane
                is EvaluatorGateBlastRadiusLane.HARD_TO_REVERSE
                or self.human_disagreement_rate != 0
                or self.agent_self_assessment_weight > 0.1
                or not self.shadow_mode
                or self.trading_scope_touched
                or self.production_data_touched
                or self.money_movement_touched
                or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
            ):
                raise ValueError("research-only evaluator gate cannot carry gaps")
        if (
            self.promotion_status != "RESEARCH_ONLY_EVALUATOR_GATE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("evaluator gate review cannot execute")


@dataclass(frozen=True, slots=True)
class ResidualEdgeReview:
    """Residual edge research evidence; it cannot authorize strategy execution."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: ResidualEdgeReviewStatus
    raw_return: float
    market_component: float
    sector_or_universe_component: float
    factor_component: float
    liquidity_component: float
    residual_return: float
    residual_zscore: float
    expected_value_after_costs: float
    sample_size: int
    independent_repetition_count: int
    fees_bps: float
    slippage_bps: float
    capacity_warning: bool
    regime_split: tuple[str, ...]
    signal_decay_check: str
    data_leakage_check: str
    sizing_status: str
    oos_validation_present: bool
    blockers: tuple[str, ...]
    trading_scope_touched: bool = False
    promotion_status: str = "RESEARCH_ONLY_RESIDUAL_EDGE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.source_uri.strip():
            raise ValueError("residual edge review identity is required")
        if self.source_sha256 and not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("residual edge source hash is invalid")
        for metric_name, metric_value in (
            ("raw return", self.raw_return),
            ("market component", self.market_component),
            ("sector or universe component", self.sector_or_universe_component),
            ("factor component", self.factor_component),
            ("liquidity component", self.liquidity_component),
            ("residual return", self.residual_return),
            ("residual zscore", self.residual_zscore),
            ("expected value after costs", self.expected_value_after_costs),
            ("fees bps", self.fees_bps),
            ("slippage bps", self.slippage_bps),
        ):
            if not math.isfinite(metric_value):
                raise ValueError(f"residual edge {metric_name} is invalid")
        for cost_name, cost_value in (
            ("fees bps", self.fees_bps),
            ("slippage bps", self.slippage_bps),
        ):
            if cost_value < 0:
                raise ValueError(f"residual edge {cost_name} cannot be negative")
        if self.sample_size < 0 or self.independent_repetition_count < 0:
            raise ValueError("residual edge sample counters are invalid")
        for values in (self.regime_split, self.blockers):
            _require_unique_nonblank("residual edge review lists", values)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("residual edge review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("residual edge review must keep live blocked")
        if self.status is ResidualEdgeReviewStatus.RESEARCH_ONLY_RESIDUAL_EDGE:
            if (
                not self.source_uri.startswith("https://")
                or not self.source_sha256
                or abs(self.residual_zscore) < 1.0
                or self.expected_value_after_costs <= 0
                or self.sample_size < 100
                or self.independent_repetition_count < 30
                or self.capacity_warning
                or not self.regime_split
                or self.signal_decay_check != "PASSED"
                or self.data_leakage_check != "PASSED"
                or self.sizing_status != "VALIDATED"
                or not self.oos_validation_present
                or self.trading_scope_touched
                or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
            ):
                raise ValueError("research-only residual edge cannot carry gaps")
        if (
            self.promotion_status != "RESEARCH_ONLY_RESIDUAL_EDGE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("residual edge review cannot execute")


@dataclass(frozen=True, slots=True)
class CoworkTaskSuitabilityReview:
    """Cowork-style task delegation evidence; it cannot grant automation authority."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: CoworkTaskSuitabilityStatus
    task_id: str
    touches_files_apps_or_web: bool
    tedious_repetitive_or_multistep: bool
    done_is_checkable: bool
    mistake_is_survivable: bool
    brain_file_present: bool
    skill_declared: bool
    connector_scope: tuple[str, ...]
    schedule_requested: bool
    manual_run_verified: bool
    draft_only: bool
    human_approval_required: bool
    judgment_required: bool
    secret_access_requested: bool
    trading_scope_touched: bool
    money_movement_touched: bool
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_COWORK_TASK"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.workflow_id.strip()
            or not self.source_uri.strip()
            or not self.task_id.strip()
        ):
            raise ValueError("cowork task suitability identity is required")
        if self.source_sha256 and not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("cowork task suitability source hash is invalid")
        for values in (self.connector_scope, self.blockers):
            _require_unique_nonblank("cowork task suitability lists", values)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("cowork task suitability requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("cowork task suitability must keep live blocked")
        if self.status is CoworkTaskSuitabilityStatus.RESEARCH_ONLY_COWORK_TASK:
            if (
                not self.source_uri.startswith("https://")
                or not self.source_sha256
                or not self.touches_files_apps_or_web
                or not self.tedious_repetitive_or_multistep
                or not self.done_is_checkable
                or not self.mistake_is_survivable
                or not self.brain_file_present
                or not self.skill_declared
                or (self.schedule_requested and not self.manual_run_verified)
                or not self.draft_only
                or not self.human_approval_required
                or self.judgment_required
                or self.secret_access_requested
                or self.trading_scope_touched
                or self.money_movement_touched
                or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
            ):
                raise ValueError("research-only cowork task cannot carry gaps")
        if (
            self.promotion_status != "RESEARCH_ONLY_COWORK_TASK"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("cowork task suitability cannot execute")


@dataclass(frozen=True, slots=True)
class AgentTrajectoryLearningEligibilityReview:
    """Learning-data eligibility for agent traces; it cannot update models."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: AgentTrajectoryLearningEligibilityStatus
    trajectory_id: str
    trajectory_hash: str
    replay_class: str
    privacy_classification: str
    redaction_status: str
    reward_signal: str
    intervention_candidate: str
    tool_schema_version: str
    retrieval_snapshot_id: str
    harness_fingerprint: str
    model_id: str
    causal_step_count: int
    delayed_reward_supported: bool
    provenance_versioned: bool
    governance_metadata_present: bool
    human_correction_present: bool
    training_eligible: bool
    secret_risk_detected: bool
    trading_scope_touched: bool
    money_movement_touched: bool
    model_weight_update_requested: bool
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_TRAJECTORY_LEARNING"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for name, value in (
            ("workflow id", self.workflow_id),
            ("source uri", self.source_uri),
            ("trajectory id", self.trajectory_id),
            ("replay class", self.replay_class),
            ("privacy classification", self.privacy_classification),
            ("redaction status", self.redaction_status),
            ("reward signal", self.reward_signal),
            ("intervention candidate", self.intervention_candidate),
            ("tool schema version", self.tool_schema_version),
            ("retrieval snapshot id", self.retrieval_snapshot_id),
            ("harness fingerprint", self.harness_fingerprint),
            ("model id", self.model_id),
        ):
            if not value.strip():
                raise ValueError(f"trajectory learning eligibility {name} is required")
        if self.source_sha256 and not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("trajectory learning eligibility source hash is invalid")
        if self.trajectory_hash and not _SHA256_HEX_RE.fullmatch(self.trajectory_hash):
            raise ValueError(
                "trajectory learning eligibility trajectory hash is invalid"
            )
        if self.causal_step_count < 0:
            raise ValueError(
                "trajectory learning eligibility step count cannot be negative"
            )
        _require_unique_nonblank(
            "trajectory learning eligibility blockers", self.blockers
        )
        for required in (
            "MODEL_UPDATE_BLOCKED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ):
            if required not in self.blockers:
                raise ValueError(
                    "trajectory learning eligibility must keep model/live blocked"
                )
        research_only_status = (
            AgentTrajectoryLearningEligibilityStatus.RESEARCH_ONLY_TRAJECTORY_LEARNING
        )
        if self.status is research_only_status:
            if (
                not self.source_uri.startswith("https://")
                or not self.source_sha256
                or not self.trajectory_hash
                or self.replay_class != "DETERMINISTIC_REPLAY"
                or self.redaction_status != "REDACTED"
                or self.reward_signal == "NONE"
                or self.intervention_candidate
                not in {
                    "NO_OP",
                    "MEMORY_CANDIDATE",
                    "SKILL_PATCH_CANDIDATE",
                    "HARNESS_REVIEW_REQUIRED",
                    "TOOL_SCHEMA_REVIEW_REQUIRED",
                }
                or self.causal_step_count <= 0
                or not self.delayed_reward_supported
                or not self.provenance_versioned
                or not self.governance_metadata_present
                or not self.human_correction_present
                or not self.training_eligible
                or self.secret_risk_detected
                or self.trading_scope_touched
                or self.money_movement_touched
                or self.model_weight_update_requested
                or self.blockers
                != (
                    "MODEL_UPDATE_BLOCKED",
                    "HUMAN_REVIEW_REQUIRED",
                    "LIVE_ORDER_BLOCKED",
                )
            ):
                raise ValueError(
                    "research-only trajectory learning eligibility cannot carry gaps"
                )
        if (
            self.promotion_status != "RESEARCH_ONLY_TRAJECTORY_LEARNING"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("trajectory learning eligibility cannot execute")


@dataclass(frozen=True, slots=True)
class GraphDependencyIntegrityReview:
    """Graph dependency evidence for opportunity workflows; it cannot execute."""

    workflow_id: str
    source_uri: str
    source_sha256: str
    status: GraphDependencyIntegrityStatus
    graph_id: str
    expected_nodes: tuple[str, ...]
    observed_nodes: tuple[str, ...]
    missing_nodes: tuple[str, ...]
    declared_edges: tuple[str, ...]
    data_carrying_edges: tuple[str, ...]
    fake_edges: tuple[str, ...]
    fanout_width: int
    barrier_count: int
    verifier_context_isolated: bool
    anchor_artifacts: tuple[str, ...]
    merge_input_count_verified: bool
    model_tiering_policy_present: bool
    cost_cap_present: bool
    silent_node_failure_count: int
    trading_scope_touched: bool
    money_movement_touched: bool
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_GRAPH_DEPENDENCY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.workflow_id.strip()
            or not self.source_uri.strip()
            or not self.graph_id.strip()
        ):
            raise ValueError("graph dependency integrity identity is required")
        if self.source_sha256 and not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("graph dependency integrity source hash is invalid")
        for values in (
            self.expected_nodes,
            self.observed_nodes,
            self.missing_nodes,
            self.declared_edges,
            self.data_carrying_edges,
            self.fake_edges,
            self.anchor_artifacts,
            self.blockers,
        ):
            _require_unique_nonblank("graph dependency integrity lists", values)
        if not self.expected_nodes:
            raise ValueError("graph dependency integrity requires expected nodes")
        if set(self.observed_nodes) - set(self.expected_nodes):
            raise ValueError("graph dependency integrity observed an unknown node")
        expected_missing = tuple(
            node for node in self.expected_nodes if node not in set(self.observed_nodes)
        )
        if self.missing_nodes != expected_missing:
            raise ValueError(
                "graph dependency integrity missing nodes are inconsistent"
            )
        if set(self.data_carrying_edges) - set(self.declared_edges):
            raise ValueError("graph dependency data edges must be declared")
        if set(self.fake_edges) - set(self.declared_edges):
            raise ValueError("graph dependency fake edges must be declared")
        if self.fanout_width < 0 or self.barrier_count < 0:
            raise ValueError("graph dependency graph counters are invalid")
        if self.silent_node_failure_count < 0:
            raise ValueError("graph dependency silent failures cannot be negative")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("graph dependency integrity requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("graph dependency integrity must keep live blocked")
        if self.status is GraphDependencyIntegrityStatus.RESEARCH_ONLY_GRAPH_DEPENDENCY:
            if (
                not self.source_uri.startswith("https://")
                or not self.source_sha256
                or self.missing_nodes
                or not self.declared_edges
                or not self.data_carrying_edges
                or self.fake_edges
                or self.fanout_width < 2
                or self.barrier_count < 1
                or not self.verifier_context_isolated
                or not self.anchor_artifacts
                or not self.merge_input_count_verified
                or not self.model_tiering_policy_present
                or not self.cost_cap_present
                or self.silent_node_failure_count != 0
                or self.trading_scope_touched
                or self.money_movement_touched
                or self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
            ):
                raise ValueError(
                    "research-only graph dependency integrity cannot carry gaps"
                )
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_DEPENDENCY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("graph dependency integrity cannot execute")


@dataclass(frozen=True, slots=True)
class AgentModelCandidateEvidence:
    """Provider/model claims captured as hostile-input evidence, not integration."""

    model_id: str
    provider: str
    context_window_tokens: int
    input_price_per_1m: float
    cached_input_price_per_1m: float
    output_price_per_1m: float
    tool_call_support: bool
    json_mode_support: bool
    data_privacy_boundary: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    external_runtime_used: bool = False
    credential_required: bool = False
    trading_signal_authority: bool = False
    execution_allowed: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.provider.strip():
            raise ValueError("agent model candidate identity is required")
        if self.context_window_tokens < 1:
            raise ValueError("agent model candidate context window is invalid")
        for name, value in (
            ("agent model input price", self.input_price_per_1m),
            ("agent model cached input price", self.cached_input_price_per_1m),
            ("agent model output price", self.output_price_per_1m),
        ):
            _require_finite_nonnegative(name, value)
        for values in (self.citations, self.blockers):
            _require_unique_nonblank("agent model candidate lists", values)
        if (
            self.execution_allowed
            or self.live_order_authority
            or self.trading_signal_authority
        ):
            raise ValueError("agent model candidate cannot grant authority")


@dataclass(frozen=True, slots=True)
class AgentModelCandidateReview:
    model_id: str
    provider: str
    status: AgentModelCandidateStatus
    context_window_tokens: int
    input_price_per_1m: float
    cached_input_price_per_1m: float
    output_price_per_1m: float
    tool_call_support: bool
    json_mode_support: bool
    data_privacy_boundary: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_PROVIDER"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.provider.strip():
            raise ValueError("agent model candidate review identity is required")
        if self.context_window_tokens < 1:
            raise ValueError("agent model candidate review context window is invalid")
        for name, value in (
            ("agent model review input price", self.input_price_per_1m),
            ("agent model review cached input price", self.cached_input_price_per_1m),
            ("agent model review output price", self.output_price_per_1m),
        ):
            _require_finite_nonnegative(name, value)
        for values in (self.citations, self.blockers):
            _require_unique_nonblank("agent model candidate review lists", values)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent model candidate review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("agent model candidate review must keep live blocked")
        if (
            self.status is AgentModelCandidateStatus.RESEARCH_ONLY_PROVIDER
            and self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        ):
            raise ValueError("research-only provider review cannot carry blockers")
        if (
            self.promotion_status != "RESEARCH_ONLY_PROVIDER"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agent model candidate review cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AgentSkillCandidateEvidence:
    """External or self-authored agent skill candidate evidence; never executable."""

    skill_id: str
    source_uri: str
    source_sha256: str
    declared_goal: str
    trigger_conditions: tuple[str, ...]
    allowed_inputs: tuple[str, ...]
    required_references: tuple[str, ...]
    declared_tools: tuple[str, ...]
    script_paths: tuple[str, ...]
    expected_output_contract: tuple[str, ...]
    review_checklist: tuple[str, ...]
    test_command: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    reviewer_result: str = "PENDING"
    self_generated: bool = False
    network_access_required: bool = False
    credential_access_required: bool = False
    trading_scope_touched: bool = False
    promotion_status: str = "RESEARCH_ONLY_SKILL"
    execution_allowed: bool = False
    live_order_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.skill_id.strip() or "/" in self.skill_id or "\\" in self.skill_id:
            raise ValueError("agent skill candidate identity is invalid")
        if not self.source_uri.strip() or not self.declared_goal.strip():
            raise ValueError("agent skill candidate source and goal are required")
        if not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("agent skill candidate hash is invalid")
        for values in (
            self.trigger_conditions,
            self.allowed_inputs,
            self.required_references,
            self.declared_tools,
            self.script_paths,
            self.expected_output_contract,
            self.review_checklist,
            self.citations,
            self.blockers,
        ):
            _require_unique_nonblank("agent skill candidate lists", values)
        if not self.reviewer_result.strip():
            raise ValueError("agent skill candidate reviewer result is required")
        if (
            self.promotion_status != "RESEARCH_ONLY_SKILL"
            or self.execution_allowed
            or self.live_order_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agent skill candidate cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AgentSkillCandidateReview:
    skill_id: str
    source_uri: str
    source_sha256: str
    declared_goal: str
    status: AgentSkillCandidateStatus
    trigger_conditions: tuple[str, ...]
    allowed_inputs: tuple[str, ...]
    required_references: tuple[str, ...]
    declared_tools: tuple[str, ...]
    script_paths: tuple[str, ...]
    expected_output_contract: tuple[str, ...]
    review_checklist: tuple[str, ...]
    test_command: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    reviewer_result: str
    promotion_status: str = "RESEARCH_ONLY_SKILL"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.skill_id.strip() or "/" in self.skill_id or "\\" in self.skill_id:
            raise ValueError("agent skill candidate review identity is invalid")
        if not self.source_uri.strip() or not self.declared_goal.strip():
            raise ValueError(
                "agent skill candidate review source and goal are required"
            )
        if not _SHA256_HEX_RE.fullmatch(self.source_sha256):
            raise ValueError("agent skill candidate review hash is invalid")
        for values in (
            self.trigger_conditions,
            self.allowed_inputs,
            self.required_references,
            self.declared_tools,
            self.script_paths,
            self.expected_output_contract,
            self.review_checklist,
            self.citations,
            self.blockers,
        ):
            _require_unique_nonblank("agent skill candidate review lists", values)
        if not self.reviewer_result.strip():
            raise ValueError("agent skill candidate review reviewer result is required")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent skill candidate review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("agent skill candidate review must keep live blocked")
        if (
            self.status is AgentSkillCandidateStatus.RESEARCH_ONLY_SKILL
            and self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        ):
            raise ValueError("research-only skill review cannot carry blockers")
        if (
            self.promotion_status != "RESEARCH_ONLY_SKILL"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agent skill candidate review cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AgentWorkspaceComponentEvidence:
    """Repo-managed agent workspace component metadata; no component is executed."""

    component_id: str
    component_type: AgentWorkspaceComponentType
    source_path: str
    content_sha256: str
    citations: tuple[str, ...]
    declared_authority: str
    canary_command: str
    canary_expected_blockers: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    external_runtime_used: bool = False
    credential_required: bool = False
    writes_enabled: bool = False
    trading_scope_touched: bool = False
    execution_allowed: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("agent workspace component identity is required")
        if not self.source_path.strip() or not _is_repo_relative_loop_path(
            self.source_path
        ):
            raise ValueError("agent workspace component path must be repo-relative")
        if not _SHA256_HEX_RE.fullmatch(self.content_sha256):
            raise ValueError("agent workspace component hash is invalid")
        for values in (self.citations, self.canary_expected_blockers, self.blockers):
            _require_unique_nonblank("agent workspace component lists", values)
        if self.execution_allowed or self.live_order_authority:
            raise ValueError("agent workspace component cannot grant authority")


@dataclass(frozen=True, slots=True)
class AgentWorkspaceComponentReview:
    component_id: str
    component_type: AgentWorkspaceComponentType
    source_path: str
    content_sha256: str
    status: AgentWorkspaceComponentStatus
    declared_authority: str
    canary_command: str
    canary_expected_blockers: tuple[str, ...]
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_WORKSPACE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("agent workspace component review identity is required")
        if not self.source_path.strip() or not _is_repo_relative_loop_path(
            self.source_path
        ):
            raise ValueError(
                "agent workspace component review path must be repo-relative"
            )
        if not _SHA256_HEX_RE.fullmatch(self.content_sha256):
            raise ValueError("agent workspace component review hash is invalid")
        for values in (
            self.canary_expected_blockers,
            self.citations,
            self.blockers,
        ):
            _require_unique_nonblank("agent workspace component review lists", values)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent workspace component review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("agent workspace component review must keep live blocked")
        if (
            self.status is AgentWorkspaceComponentStatus.RESEARCH_ONLY_WORKSPACE
            and self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        ):
            raise ValueError("research-only workspace review cannot carry blockers")
        if (
            self.promotion_status != "RESEARCH_ONLY_WORKSPACE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "agent workspace component review cannot promote or execute"
            )


@dataclass(frozen=True, slots=True)
class MarkdownGovernanceArtifactEvidence:
    """Reviewed Markdown metacode; it informs agents but never executes."""

    artifact_id: str
    source_path: str
    content_sha256: str
    role: MarkdownGovernanceArtifactRole
    reviewer_result: MarkdownGovernanceReviewerResult
    declared_authority: str
    citations: tuple[str, ...]
    owner: str
    freshness_policy: str
    canonical_source_path: str = ""
    blockers: tuple[str, ...] = ()
    contains_private_context: bool = False
    external_runtime_used: bool = False
    credential_required: bool = False
    execution_allowed: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("markdown governance artifact identity is required")
        if not _is_repo_relative_markdown_path(self.source_path):
            raise ValueError("markdown governance artifact path must be repo-relative")
        if self.canonical_source_path and not _is_repo_relative_markdown_path(
            self.canonical_source_path
        ):
            raise ValueError("markdown canonical source path must be repo-relative")
        if not _SHA256_HEX_RE.fullmatch(self.content_sha256):
            raise ValueError("markdown governance artifact hash is invalid")
        for values in (self.citations, self.blockers):
            _require_unique_nonblank("markdown governance artifact lists", values)
        if self.execution_allowed or self.live_order_authority:
            raise ValueError("markdown governance artifact cannot grant authority")


@dataclass(frozen=True, slots=True)
class MarkdownGovernanceArtifactReview:
    artifact_id: str
    source_path: str
    content_sha256: str
    role: MarkdownGovernanceArtifactRole
    status: MarkdownGovernanceReviewStatus
    reviewer_result: MarkdownGovernanceReviewerResult
    declared_authority: str
    citations: tuple[str, ...]
    owner: str
    freshness_policy: str
    canonical_source_path: str
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_DOCUMENTATION"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("markdown governance review identity is required")
        if not _is_repo_relative_markdown_path(self.source_path):
            raise ValueError("markdown governance review path must be repo-relative")
        if self.canonical_source_path and not _is_repo_relative_markdown_path(
            self.canonical_source_path
        ):
            raise ValueError("markdown canonical review path must be repo-relative")
        if not _SHA256_HEX_RE.fullmatch(self.content_sha256):
            raise ValueError("markdown governance review hash is invalid")
        for values in (self.citations, self.blockers):
            _require_unique_nonblank("markdown governance review lists", values)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("markdown governance review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("markdown governance review must keep live blocked")
        if (
            self.status is MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION
            and self.blockers != ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        ):
            raise ValueError(
                "research-only markdown governance review cannot carry blockers"
            )
        if (
            self.promotion_status != "RESEARCH_ONLY_DOCUMENTATION"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("markdown governance review cannot promote or execute")


@dataclass(frozen=True, slots=True)
class MarkdownGovernanceReviewReduction:
    expected_artifacts: tuple[str, ...]
    observed_artifacts: tuple[str, ...]
    missing_artifacts: tuple[str, ...]
    final_status: MarkdownGovernanceReviewStatus
    blockers: tuple[str, ...]
    reviews: tuple[MarkdownGovernanceArtifactReview, ...]
    promotion_status: str = "RESEARCH_ONLY_DOCUMENTATION"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.expected_artifacts:
            raise ValueError("markdown governance reducer requires expected artifacts")
        for values in (
            self.expected_artifacts,
            self.observed_artifacts,
            self.missing_artifacts,
            self.blockers,
        ):
            _require_unique_nonblank("markdown governance reducer lists", values)
        if set(self.observed_artifacts) - set(self.expected_artifacts):
            raise ValueError("markdown governance reducer observed an unknown artifact")
        if self.missing_artifacts != tuple(
            artifact
            for artifact in self.expected_artifacts
            if artifact not in set(self.observed_artifacts)
        ):
            raise ValueError(
                "markdown governance reducer missing artifacts are inconsistent"
            )
        review_ids = tuple(review.artifact_id for review in self.reviews)
        if len(set(review_ids)) != len(review_ids):
            raise ValueError("markdown governance reducer reviews must be unique")
        if set(review_ids) != set(self.observed_artifacts):
            raise ValueError(
                "markdown governance reducer observations must match reviews"
            )
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("markdown governance reducer must keep live blocked")
        if (
            self.promotion_status != "RESEARCH_ONLY_DOCUMENTATION"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("markdown governance reducer cannot promote or execute")


@dataclass(frozen=True, slots=True)
class OpportunityArtifactReviewResult:
    branch_id: str
    artifact_uri: str
    content_sha256: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    reviewer_result: OpportunityArtifactReviewStatus
    reviewer_notes: tuple[str, ...] = ()
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.branch_id.strip() or not self.artifact_uri.strip():
            raise ValueError("opportunity review artifact identity is required")
        if not _SHA256_HEX_RE.fullmatch(self.content_sha256):
            raise ValueError("opportunity review artifact hash is invalid")
        for values in (self.citations, self.blockers, self.reviewer_notes):
            if len(set(values)) != len(values):
                raise ValueError("opportunity review lists must be unique")
            if any(not value.strip() for value in values):
                raise ValueError("opportunity review lists cannot contain blanks")
        if not self.citations:
            raise ValueError("opportunity review requires citations")
        if (
            self.reviewer_result is OpportunityArtifactReviewStatus.PASSED
            and self.blockers
        ):
            raise ValueError("passed opportunity reviews cannot carry blockers")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("opportunity review cannot promote or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("opportunity review must keep live trading blocked")


@dataclass(frozen=True, slots=True)
class OpportunityArtifactReviewReduction:
    expected_branches: tuple[str, ...]
    observed_branches: tuple[str, ...]
    missing_branches: tuple[str, ...]
    final_status: OpportunityArtifactReductionStatus
    blockers: tuple[str, ...]
    reviews: tuple[OpportunityArtifactReviewResult, ...]
    supporting_workspace_reviews: tuple[AgentWorkspaceComponentReview, ...] = ()
    architecture_coverage_summary: AgentArchitectureCoverageSummary | None = None
    invocation_coverage_summary: AgentInvocationCoverageSummary | None = None
    loop_building_block_coverage_summary: LoopBuildingBlockCoverageSummary | None = None
    evaluator_gate_review: EvaluatorGateReview | None = None
    residual_edge_review: ResidualEdgeReview | None = None
    cowork_task_suitability_review: CoworkTaskSuitabilityReview | None = None
    trajectory_learning_eligibility_review: (
        AgentTrajectoryLearningEligibilityReview | None
    ) = None
    graph_dependency_integrity_review: GraphDependencyIntegrityReview | None = None
    expected_workspace_components: tuple[str, ...] = ()
    observed_workspace_components: tuple[str, ...] = ()
    missing_workspace_components: tuple[str, ...] = ()
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.expected_branches:
            raise ValueError("opportunity reducer requires expected branches")
        for values in (
            self.expected_branches,
            self.observed_branches,
            self.missing_branches,
            self.blockers,
            self.expected_workspace_components,
            self.observed_workspace_components,
            self.missing_workspace_components,
        ):
            if len(set(values)) != len(values):
                raise ValueError("opportunity reducer lists must be unique")
            if any(not value.strip() for value in values):
                raise ValueError("opportunity reducer lists cannot contain blanks")
        if set(self.observed_branches) - set(self.expected_branches):
            raise ValueError("opportunity reducer observed an unknown branch")
        if self.missing_branches != tuple(
            branch
            for branch in self.expected_branches
            if branch not in set(self.observed_branches)
        ):
            raise ValueError("opportunity reducer missing branches are inconsistent")
        observed_workspace_review_ids = tuple(
            review.component_id for review in self.supporting_workspace_reviews
        )
        if len(set(observed_workspace_review_ids)) != len(
            observed_workspace_review_ids
        ):
            raise ValueError("opportunity reducer workspace reviews must be unique")
        if self.expected_workspace_components:
            if set(self.observed_workspace_components) - set(
                self.expected_workspace_components
            ):
                raise ValueError(
                    "opportunity reducer observed an unknown workspace component"
                )
            if self.missing_workspace_components != tuple(
                component
                for component in self.expected_workspace_components
                if component not in set(self.observed_workspace_components)
            ):
                raise ValueError(
                    "opportunity reducer missing workspace components are inconsistent"
                )
        elif self.missing_workspace_components:
            raise ValueError(
                "opportunity reducer cannot miss unrequested workspace components"
            )
        if set(self.observed_workspace_components) != set(
            observed_workspace_review_ids
        ):
            raise ValueError(
                "opportunity reducer workspace observations must match reviews"
            )
        if (
            self.architecture_coverage_summary is not None
            and self.architecture_coverage_summary.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError(
                "opportunity reducer architecture coverage workflow is unsupported"
            )
        if (
            self.invocation_coverage_summary is not None
            and self.invocation_coverage_summary.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError(
                "opportunity reducer invocation coverage workflow is unsupported"
            )
        if (
            self.loop_building_block_coverage_summary is not None
            and self.loop_building_block_coverage_summary.loop_id
            not in {"research-quality-loop-v1", "opportunity-loop-v1"}
        ):
            raise ValueError(
                "opportunity reducer loop building-block coverage is unsupported"
            )
        if (
            self.evaluator_gate_review is not None
            and self.evaluator_gate_review.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError("opportunity reducer evaluator gate is unsupported")
        if (
            self.residual_edge_review is not None
            and self.residual_edge_review.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError("opportunity reducer residual edge review is unsupported")
        if (
            self.cowork_task_suitability_review is not None
            and self.cowork_task_suitability_review.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError(
                "opportunity reducer cowork task suitability is unsupported"
            )
        if (
            self.trajectory_learning_eligibility_review is not None
            and self.trajectory_learning_eligibility_review.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError(
                "opportunity reducer trajectory learning eligibility is unsupported"
            )
        if (
            self.graph_dependency_integrity_review is not None
            and self.graph_dependency_integrity_review.workflow_id
            not in {"external-link-opportunity", "opportunity-research-diamond"}
        ):
            raise ValueError(
                "opportunity reducer graph dependency integrity is unsupported"
            )
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("opportunity reducer must keep live blocker visible")
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity reducer cannot promote or execute")


@dataclass(frozen=True, slots=True)
class GraphArchitectureReadinessEvidence:
    """Evidence that a workflow graph has grounded checks around its loops."""

    workflow_id: str
    selected_pattern: str
    graph: WorkflowGraph
    reviewer_nodes: tuple[str, ...]
    anchor_artifacts: tuple[str, ...]
    counter_metrics: tuple[str, ...]
    human_gate_nodes: tuple[str, ...]
    reducer_nodes: tuple[str, ...]
    independent_reviewers: bool
    deterministic_reducer: bool
    trace_artifacts: tuple[str, ...] = ()
    external_runtime_used: bool = False
    llm_signal_authority: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.selected_pattern.strip():
            raise ValueError("graph readiness evidence identity is required")
        node_ids = tuple(node.node_id for node in self.graph.nodes)
        if self.workflow_id != self.graph.graph_id:
            raise ValueError("graph readiness evidence workflow identity mismatch")
        for values in (
            self.reviewer_nodes,
            self.anchor_artifacts,
            self.counter_metrics,
            self.human_gate_nodes,
            self.reducer_nodes,
            self.trace_artifacts,
        ):
            _require_unique_nonblank("graph readiness evidence lists", values)
        for label, values in (
            ("reviewer node", self.reviewer_nodes),
            ("human gate node", self.human_gate_nodes),
            ("reducer node", self.reducer_nodes),
        ):
            if set(values) - set(node_ids):
                raise ValueError(f"graph readiness {label} is unknown")
        if self.execution_allowed or self.llm_signal_authority:
            raise ValueError("graph readiness evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class GraphArchitectureReadinessReview:
    workflow_id: str
    selected_pattern: str
    status: GraphArchitectureReadinessStatus
    blockers: tuple[str, ...]
    reviewer_nodes: tuple[str, ...]
    anchor_artifacts: tuple[str, ...]
    counter_metrics: tuple[str, ...]
    human_gate_nodes: tuple[str, ...]
    reducer_nodes: tuple[str, ...]
    trace_artifacts: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_GRAPH_PATTERN"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.selected_pattern.strip():
            raise ValueError("graph readiness review identity is required")
        for values in (
            self.blockers,
            self.reviewer_nodes,
            self.anchor_artifacts,
            self.counter_metrics,
            self.human_gate_nodes,
            self.reducer_nodes,
            self.trace_artifacts,
        ):
            _require_unique_nonblank("graph readiness review lists", values)
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("graph readiness review must keep live blocker visible")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("graph readiness review requires human review")
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_PATTERN"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("graph readiness review cannot promote or execute")


@dataclass(frozen=True, slots=True)
class GraphWorkflowManifestEvidence:
    """Pre-run manifest evidence for a workflow graph, not an execution grant."""

    workflow_id: str
    selected_pattern: str
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    cycles_allowed: bool
    parallelism_cap: int
    expected_artifacts: tuple[str, ...]
    verifier_nodes: tuple[str, ...]
    human_gate_nodes: tuple[str, ...]
    state_schema_hash: str
    authority_flags: tuple[str, ...]
    declared_blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_order_authority: bool = False
    signal_authority: bool = False

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.selected_pattern.strip():
            raise ValueError("graph workflow manifest identity is required")
        for values in (
            self.nodes,
            self.expected_artifacts,
            self.verifier_nodes,
            self.human_gate_nodes,
            self.authority_flags,
            self.declared_blockers,
        ):
            _require_unique_nonblank("graph workflow manifest lists", values)
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("graph workflow manifest edges must be unique")
        if any(
            len(edge) != 2 or not edge[0].strip() or not edge[1].strip()
            for edge in self.edges
        ):
            raise ValueError("graph workflow manifest edges must be node pairs")
        if not 1 <= self.parallelism_cap <= 256:
            raise ValueError("graph workflow manifest parallelism cap is invalid")
        if self.state_schema_hash and not _SHA256_HEX_RE.fullmatch(
            self.state_schema_hash
        ):
            raise ValueError("graph workflow manifest state hash is invalid")
        if self.execution_allowed or self.live_order_authority or self.signal_authority:
            raise ValueError("graph workflow manifest cannot grant authority")


@dataclass(frozen=True, slots=True)
class GraphWorkflowManifestReview:
    """Fail-closed pre-run review for explicit graph workflow manifests."""

    workflow_id: str
    selected_pattern: str
    status: GraphWorkflowManifestReviewStatus
    blockers: tuple[str, ...]
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    cycles_allowed: bool
    parallelism_cap: int
    expected_artifacts: tuple[str, ...]
    verifier_nodes: tuple[str, ...]
    human_gate_nodes: tuple[str, ...]
    state_schema_hash: str
    authority_flags: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_GRAPH_WORKFLOW"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.selected_pattern.strip():
            raise ValueError("graph workflow manifest review identity is required")
        for values in (
            self.blockers,
            self.nodes,
            self.expected_artifacts,
            self.verifier_nodes,
            self.human_gate_nodes,
            self.authority_flags,
        ):
            _require_unique_nonblank("graph workflow manifest review lists", values)
        if self.status not in set(GraphWorkflowManifestReviewStatus):
            raise ValueError("graph workflow manifest review status is invalid")
        if (
            not _SHA256_HEX_RE.fullmatch(self.state_schema_hash)
            and "GRAPH_MANIFEST_STATE_SCHEMA_HASH_REQUIRED" not in self.blockers
        ):
            raise ValueError("graph workflow manifest review state hash is invalid")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("graph workflow manifest review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("graph workflow manifest review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("graph workflow manifest review cannot become a signal")
        if (
            self.promotion_status != "RESEARCH_ONLY_GRAPH_WORKFLOW"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("graph workflow manifest review cannot promote or execute")


@dataclass(frozen=True, slots=True)
class ClosedLoopAdmissionEvidence:
    """Admission evidence for a bounded agent loop before any run can be planned."""

    loop_id: str
    task: str
    trigger: str
    selected_pattern: str
    loop_type: AgentLoopType
    loop_scale: AgentLoopScale
    allowed_tools: tuple[str, ...]
    allowed_write_roots: tuple[str, ...]
    memory_sources: tuple[str, ...]
    verifier_identity: str
    artifact_log_uri: str
    stop_conditions: tuple[str, ...]
    max_iterations: int
    max_cost_units: int
    human_handoff: bool
    connector_requested: bool = False
    plugin_requested: bool = False
    scheduler_requested: bool = False
    network_requested: bool = False
    trading_scope_touched: bool = False
    execution_allowed: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.loop_id.strip()
            or not self.task.strip()
            or not self.selected_pattern.strip()
        ):
            raise ValueError("closed loop admission identity is required")
        if not 1 <= self.max_iterations <= 100:
            raise ValueError("closed loop admission iteration bound is invalid")
        if not 1 <= self.max_cost_units <= 1_000_000:
            raise ValueError("closed loop admission cost bound is invalid")
        for values in (
            self.allowed_tools,
            self.allowed_write_roots,
            self.memory_sources,
            self.stop_conditions,
        ):
            _require_unique_nonblank("closed loop admission lists", values)
        for root in self.allowed_write_roots:
            if not _is_repo_relative_loop_path(root):
                raise ValueError("closed loop write roots must be repo-relative")
        if self.execution_allowed or self.live_order_authority:
            raise ValueError("closed loop admission cannot grant authority")


@dataclass(frozen=True, slots=True)
class ClosedLoopAdmission:
    loop_id: str
    task: str
    trigger: str
    selected_pattern: str
    loop_type: AgentLoopType
    loop_scale: AgentLoopScale
    status: ClosedLoopAdmissionStatus
    blockers: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_write_roots: tuple[str, ...]
    memory_sources: tuple[str, ...]
    verifier_identity: str
    artifact_log_uri: str
    stop_conditions: tuple[str, ...]
    max_iterations: int
    max_cost_units: int
    promotion_status: str = "RESEARCH_ONLY_LOOP"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.loop_id.strip()
            or not self.task.strip()
            or not self.selected_pattern.strip()
        ):
            raise ValueError("closed loop admission identity is required")
        if not 1 <= self.max_iterations <= 100:
            raise ValueError("closed loop admission iteration bound is invalid")
        if not 1 <= self.max_cost_units <= 1_000_000:
            raise ValueError("closed loop admission cost bound is invalid")
        for values in (
            self.blockers,
            self.allowed_tools,
            self.allowed_write_roots,
            self.memory_sources,
            self.stop_conditions,
        ):
            _require_unique_nonblank("closed loop admission lists", values)
        for root in self.allowed_write_roots:
            if not _is_repo_relative_loop_path(root):
                raise ValueError("closed loop write roots must be repo-relative")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("closed loop admission requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("closed loop admission must keep live blocked")
        if (
            self.promotion_status != "RESEARCH_ONLY_LOOP"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("closed loop admission cannot promote or execute")


@dataclass(frozen=True, slots=True)
class ClosedLoopRunEvidence:
    """Observed outer-loop run evidence; it never grants unattended authority."""

    admission: ClosedLoopAdmission
    run_id: str
    trigger_type: ClosedLoopRunTriggerType
    state_uri: str
    resume_point: str
    verifier_identity: str
    started_at: datetime
    finished_at: datetime
    iteration_count: int
    cost_units: int
    state_read_before_frame: bool
    verification_passed: bool
    state_written_after_verification: bool
    stop_condition_met: bool
    blockers: tuple[str, ...] = ()
    model_claimed_completion: bool = False
    execution_allowed: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("closed loop run identity is required")
        if self.iteration_count < 0 or self.cost_units < 0:
            raise ValueError("closed loop run counters are invalid")
        _require_timezone_aware("closed loop run start", self.started_at)
        _require_timezone_aware("closed loop run finish", self.finished_at)
        if self.finished_at < self.started_at:
            raise ValueError("closed loop run finish precedes start")
        _require_unique_nonblank("closed loop run blockers", self.blockers)
        if self.execution_allowed or self.live_order_authority:
            raise ValueError("closed loop run evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class ClosedLoopRunSummary:
    loop_id: str
    run_id: str
    trigger_type: ClosedLoopRunTriggerType
    status: ClosedLoopAdmissionStatus
    state_uri: str
    resume_point: str
    verifier_identity: str
    iteration_count: int
    cost_units: int
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_LOOP"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.loop_id.strip() or not self.run_id.strip():
            raise ValueError("closed loop run summary identity is required")
        if self.iteration_count < 0 or self.cost_units < 0:
            raise ValueError("closed loop run summary counters are invalid")
        _require_unique_nonblank("closed loop run summary blockers", self.blockers)
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("closed loop run summary requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("closed loop run summary must keep live blocked")
        if (
            self.promotion_status != "RESEARCH_ONLY_LOOP"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("closed loop run summary cannot promote or execute")


@dataclass(frozen=True, slots=True)
class LoopEngineeringReadinessEvidence:
    """Evidence that an iterative loop is bounded, verified, and review-gated."""

    loop_id: str
    task: str
    selected_pattern: str
    objective_metric: str
    deterministic_verifier: bool
    max_iterations: int
    max_cost_units: int
    rollback_or_no_write: bool
    artifact_log_uri: str
    holdout_artifact_uri: str
    oos_artifact_uri: str
    human_gate: bool
    stop_conditions: tuple[str, ...]
    before_after_metrics: tuple[str, ...]
    allowed_write_roots: tuple[str, ...] = ()
    trading_scope_touched: bool = False
    provider_runtime_used: bool = False
    model_can_self_promote: bool = False
    execution_allowed: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.loop_id.strip()
            or not self.task.strip()
            or not self.selected_pattern.strip()
        ):
            raise ValueError("loop readiness evidence identity is required")
        if not 1 <= self.max_iterations <= 100:
            raise ValueError("loop readiness iteration bound is invalid")
        if not 1 <= self.max_cost_units <= 1_000_000:
            raise ValueError("loop readiness cost bound is invalid")
        for values in (
            self.stop_conditions,
            self.before_after_metrics,
            self.allowed_write_roots,
        ):
            _require_unique_nonblank("loop readiness evidence lists", values)
        for root in self.allowed_write_roots:
            if not _is_repo_relative_loop_path(root):
                raise ValueError("loop readiness write roots must be repo-relative")
        if (
            self.execution_allowed
            or self.live_order_authority
            or self.model_can_self_promote
        ):
            raise ValueError("loop readiness evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class LoopEngineeringReadinessReview:
    loop_id: str
    task: str
    selected_pattern: str
    status: LoopEngineeringReadinessStatus
    blockers: tuple[str, ...]
    objective_metric: str
    stop_conditions: tuple[str, ...]
    before_after_metrics: tuple[str, ...]
    artifact_log_uri: str
    holdout_artifact_uri: str
    oos_artifact_uri: str
    promotion_status: str = "RESEARCH_ONLY_LOOP_PATTERN"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.loop_id.strip()
            or not self.task.strip()
            or not self.selected_pattern.strip()
        ):
            raise ValueError("loop readiness review identity is required")
        for values in (self.blockers, self.stop_conditions, self.before_after_metrics):
            _require_unique_nonblank("loop readiness review lists", values)
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("loop readiness review must keep live blocker visible")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("loop readiness review requires human review")
        if (
            self.promotion_status != "RESEARCH_ONLY_LOOP_PATTERN"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("loop readiness review cannot promote or execute")


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


def audit_workflow_edges(graph: WorkflowGraph) -> WorkflowEdgeAudit:
    nodes_by_id = {node.node_id: node for node in graph.nodes}
    real_edges: list[str] = []
    fake_edges: list[str] = []
    for node_id in graph.topological_order():
        node = nodes_by_id[node_id]
        for dependency_id in node.dependencies:
            dependency = nodes_by_id[dependency_id]
            edge_id = f"{dependency_id}->{node.node_id}"
            carried_artifacts = set(dependency.output_artifacts) & set(
                node.input_artifacts
            )
            if carried_artifacts:
                real_edges.append(edge_id)
            else:
                fake_edges.append(edge_id)

    blockers = (
        (
            "WORKFLOW_FAKE_EDGE_DETECTED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
        if fake_edges
        else ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    )
    status = (
        WorkflowEdgeAuditStatus.WATCHLIST
        if fake_edges
        else WorkflowEdgeAuditStatus.REAL_EDGES_VERIFIED
    )
    return WorkflowEdgeAudit(
        graph_id=graph.graph_id,
        status=status,
        real_edges=tuple(real_edges),
        fake_edges=tuple(fake_edges),
        blockers=blockers,
    )


def summarize_graph_run_trace(
    graph: WorkflowGraph,
    *,
    run_id: str,
    checkpoints: tuple[GraphRunNodeCheckpoint, ...],
    max_cost_units: int,
    max_retry_count: int,
) -> GraphRunTrace:
    if not run_id.strip():
        raise ValueError("graph run trace identity is required")
    if max_cost_units < 1 or max_retry_count < 0:
        raise ValueError("graph run trace budgets are invalid")

    expected_nodes = graph.topological_order()
    by_node, blockers = _index_graph_run_checkpoints(
        expected_nodes=expected_nodes,
        checkpoints=checkpoints,
        run_id=run_id,
    )
    missing_nodes = tuple(
        node_id for node_id in expected_nodes if node_id not in by_node
    )
    observed_checkpoints = tuple(
        by_node[node_id] for node_id in expected_nodes if node_id in by_node
    )
    if missing_nodes:
        blockers.append("GRAPH_RUN_MISSING_NODE_CHECKPOINT")
    total_cost_units = sum(checkpoint.cost_units for checkpoint in observed_checkpoints)
    if total_cost_units > max_cost_units:
        blockers.append("GRAPH_RUN_COST_BUDGET_EXCEEDED")
    if any(
        checkpoint.retry_count > max_retry_count for checkpoint in observed_checkpoints
    ):
        blockers.append("GRAPH_RUN_RETRY_BUDGET_EXCEEDED")

    checkpoint_blockers = tuple(
        blocker
        for checkpoint in observed_checkpoints
        for blocker in checkpoint.blockers
    )
    blockers.extend(checkpoint_blockers)
    reviewer_watchlisted = any(
        checkpoint.reviewer_result.casefold() in {"watchlist", "conflicting", "failed"}
        for checkpoint in observed_checkpoints
    )
    if reviewer_watchlisted:
        blockers.append("GRAPH_RUN_REVIEWER_RESULT_NOT_PASSED")

    terminal_state = _graph_run_terminal_state(
        blockers=blockers,
        checkpoint_blockers=checkpoint_blockers,
        missing_nodes=missing_nodes,
        observed_checkpoints=observed_checkpoints,
    )

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    return GraphRunTrace(
        run_id=run_id,
        graph_id=graph.graph_id,
        terminal_state=terminal_state,
        checkpoints=observed_checkpoints,
        blockers=tuple(dict.fromkeys(blockers)),
        max_cost_units=max_cost_units,
        max_retry_count=max_retry_count,
    )


def _index_graph_run_checkpoints(
    *,
    expected_nodes: tuple[str, ...],
    checkpoints: tuple[GraphRunNodeCheckpoint, ...],
    run_id: str,
) -> tuple[dict[str, GraphRunNodeCheckpoint], list[str]]:
    """Index valid checkpoints and retain deterministic integrity blockers."""

    by_node: dict[str, GraphRunNodeCheckpoint] = {}
    blockers: list[str] = []
    for checkpoint in sorted(checkpoints, key=lambda item: (item.node_id, item.run_id)):
        if checkpoint.run_id != run_id:
            blockers.append("GRAPH_RUN_CHECKPOINT_IDENTITY_MISMATCH")
        elif checkpoint.node_id not in expected_nodes:
            blockers.append("GRAPH_RUN_UNKNOWN_NODE_CHECKPOINT")
        elif checkpoint.node_id in by_node:
            blockers.append("GRAPH_RUN_DUPLICATE_NODE_CHECKPOINT")
        else:
            by_node[checkpoint.node_id] = checkpoint
    return by_node, blockers


def _graph_run_terminal_state(
    *,
    blockers: list[str],
    checkpoint_blockers: tuple[str, ...],
    missing_nodes: tuple[str, ...],
    observed_checkpoints: tuple[GraphRunNodeCheckpoint, ...],
) -> GraphRunTerminalState:
    """Derive the fail-closed terminal state from normalized checkpoint evidence."""

    watchlist_blockers = {
        "GRAPH_RUN_CHECKPOINT_IDENTITY_MISMATCH",
        "GRAPH_RUN_UNKNOWN_NODE_CHECKPOINT",
        "GRAPH_RUN_DUPLICATE_NODE_CHECKPOINT",
        "GRAPH_RUN_COST_BUDGET_EXCEEDED",
        "GRAPH_RUN_RETRY_BUDGET_EXCEEDED",
        "GRAPH_RUN_REVIEWER_RESULT_NOT_PASSED",
    }
    if missing_nodes or watchlist_blockers.intersection(blockers):
        return GraphRunTerminalState.WATCHLIST
    if checkpoint_blockers:
        return GraphRunTerminalState.HUMAN_REVIEW_REQUIRED
    if any(
        checkpoint.reviewer_result.casefold() == "research_only"
        for checkpoint in observed_checkpoints
    ):
        return GraphRunTerminalState.RESEARCH_ONLY
    return GraphRunTerminalState.COMPLETED


def reduce_graph_node_route_decisions(
    graph: WorkflowGraph,
    *,
    run_id: str,
    decisions: tuple[GraphNodeRouteDecision, ...],
    max_cost_units: int,
    max_retry_count: int,
) -> GraphNodeRouteReduction:
    if not run_id.strip():
        raise ValueError("graph node route reduction identity is required")
    if max_cost_units < 1 or max_retry_count < 0:
        raise ValueError("graph node route reduction budgets are invalid")

    expected_nodes = graph.topological_order()
    by_node: dict[str, GraphNodeRouteDecision] = {}
    blockers: list[str] = []
    for decision in sorted(decisions, key=lambda item: (item.node_id, item.run_id)):
        if decision.run_id != run_id or decision.graph_id != graph.graph_id:
            blockers.append("GRAPH_ROUTE_DECISION_IDENTITY_MISMATCH")
            continue
        if decision.node_id not in expected_nodes:
            blockers.append("GRAPH_ROUTE_UNKNOWN_NODE_DECISION")
            continue
        if decision.node_id in by_node:
            blockers.append("GRAPH_ROUTE_DUPLICATE_NODE_DECISION")
            continue
        by_node[decision.node_id] = decision

    observed_nodes = tuple(node_id for node_id in expected_nodes if node_id in by_node)
    missing_nodes = tuple(
        node_id for node_id in expected_nodes if node_id not in by_node
    )
    if missing_nodes:
        blockers.append("GRAPH_ROUTE_MISSING_NODE_DECISION")

    observed_decisions = tuple(by_node[node_id] for node_id in observed_nodes)
    total_cost_units = sum(decision.cost_units for decision in observed_decisions)
    if total_cost_units > max_cost_units:
        blockers.append("GRAPH_ROUTE_COST_BUDGET_EXCEEDED")
    if any(decision.retry_count > max_retry_count for decision in observed_decisions):
        blockers.append("GRAPH_ROUTE_RETRY_BUDGET_EXCEEDED")
    if any(
        decision.decision is GraphNodeRouteDecisionType.RETRY
        and decision.retry_count >= max_retry_count
        for decision in observed_decisions
    ):
        blockers.append("GRAPH_ROUTE_RETRY_LIMIT_REACHED")

    route_blockers = tuple(
        blocker for decision in observed_decisions for blocker in decision.blockers
    )
    blockers.extend(route_blockers)
    if any(not decision.citations for decision in observed_decisions):
        blockers.append("GRAPH_ROUTE_CITATION_REQUIRED")
    if any(
        decision.reviewer_result.casefold() in {"watchlist", "failed", "rejected"}
        for decision in observed_decisions
    ):
        blockers.append("GRAPH_ROUTE_REVIEWER_RESULT_NOT_PASSED")
    if any(
        decision.reviewer_result.casefold() == "conflicting"
        for decision in observed_decisions
    ):
        blockers.append("GRAPH_ROUTE_REVIEW_CONFLICTING")
    if any(
        decision.decision is GraphNodeRouteDecisionType.STOP
        for decision in observed_decisions
    ):
        blockers.append("GRAPH_ROUTE_STOP_REQUESTED")
    if any(
        decision.decision is GraphNodeRouteDecisionType.ESCALATE
        for decision in observed_decisions
    ):
        blockers.append("GRAPH_ROUTE_ESCALATION_REQUIRED")
    unknown_targets = tuple(
        decision.target_node
        for decision in observed_decisions
        if decision.target_node and decision.target_node not in expected_nodes
    )
    if unknown_targets:
        blockers.append("GRAPH_ROUTE_TARGET_UNKNOWN")

    hard_blockers = {
        "GRAPH_ROUTE_DECISION_IDENTITY_MISMATCH",
        "GRAPH_ROUTE_UNKNOWN_NODE_DECISION",
        "GRAPH_ROUTE_DUPLICATE_NODE_DECISION",
        "GRAPH_ROUTE_MISSING_NODE_DECISION",
        "GRAPH_ROUTE_COST_BUDGET_EXCEEDED",
        "GRAPH_ROUTE_RETRY_BUDGET_EXCEEDED",
        "GRAPH_ROUTE_RETRY_LIMIT_REACHED",
        "GRAPH_ROUTE_CITATION_REQUIRED",
        "GRAPH_ROUTE_REVIEWER_RESULT_NOT_PASSED",
        "GRAPH_ROUTE_REVIEW_CONFLICTING",
        "GRAPH_ROUTE_STOP_REQUESTED",
        "GRAPH_ROUTE_TARGET_UNKNOWN",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        terminal_state = GraphRunTerminalState.WATCHLIST
    elif "GRAPH_ROUTE_ESCALATION_REQUIRED" in blockers or route_blockers:
        terminal_state = GraphRunTerminalState.HUMAN_REVIEW_REQUIRED
    elif any(
        decision.decision
        in {GraphNodeRouteDecisionType.RETRY, GraphNodeRouteDecisionType.REROUTE}
        for decision in observed_decisions
    ):
        terminal_state = GraphRunTerminalState.RESEARCH_ONLY
    else:
        terminal_state = GraphRunTerminalState.COMPLETED

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    return GraphNodeRouteReduction(
        graph_id=graph.graph_id,
        run_id=run_id,
        expected_nodes=expected_nodes,
        observed_nodes=observed_nodes,
        missing_nodes=missing_nodes,
        terminal_state=terminal_state,
        decisions=observed_decisions,
        blockers=tuple(dict.fromkeys(blockers)),
        max_cost_units=max_cost_units,
        max_retry_count=max_retry_count,
    )


def reduce_agent_architecture_layer_reviews(
    reviews: tuple[AgentArchitectureLayerEvidence, ...],
    *,
    workflow_id: str,
    expected_layers: tuple[AgentArchitectureLayer, ...] = AGENT_ARCHITECTURE_LAYERS,
) -> AgentArchitectureLayerReduction:
    if not workflow_id.strip() or not expected_layers:
        raise ValueError("agent architecture layer reduction identity is required")
    if len(set(expected_layers)) != len(expected_layers):
        raise ValueError("agent architecture layer reduction lists must be unique")

    by_layer: dict[AgentArchitectureLayer, AgentArchitectureLayerEvidence] = {}
    blockers: list[str] = []
    expected_layer_set = set(expected_layers)
    for review in sorted(
        reviews, key=lambda item: (item.layer.value, item.artifact_uri)
    ):
        if review.workflow_id != workflow_id:
            blockers.append("ARCHITECTURE_LAYER_WORKFLOW_MISMATCH")
            continue
        if review.layer not in expected_layer_set:
            blockers.append("ARCHITECTURE_LAYER_UNKNOWN_REVIEW")
            continue
        if review.layer in by_layer:
            blockers.append("ARCHITECTURE_LAYER_DUPLICATE_REVIEW")
            continue
        by_layer[review.layer] = review

    observed_layers = tuple(layer for layer in expected_layers if layer in by_layer)
    missing_layers = tuple(layer for layer in expected_layers if layer not in by_layer)
    if missing_layers:
        blockers.append("ARCHITECTURE_LAYER_MISSING_REVIEW")

    observed_reviews = tuple(by_layer[layer] for layer in observed_layers)
    layer_blockers = tuple(
        blocker for review in observed_reviews for blocker in review.blockers
    )
    blockers.extend(layer_blockers)
    if any(not review.citations for review in observed_reviews):
        blockers.append("ARCHITECTURE_LAYER_CITATION_REQUIRED")
    for review in observed_reviews:
        expected_controls = _AGENT_ARCHITECTURE_REQUIRED_CONTROL_POINTS[review.layer]
        normalized_controls = {control.casefold() for control in review.control_points}
        missing_controls = tuple(
            control
            for control in expected_controls
            if control.casefold() not in normalized_controls
        )
        if missing_controls:
            blockers.append(
                f"ARCHITECTURE_LAYER_{review.layer.value}_CONTROL_POINT_MISSING"
            )
    if any(
        review.reviewer_result.casefold() in {"watchlist", "failed", "rejected"}
        for review in observed_reviews
    ):
        blockers.append("ARCHITECTURE_LAYER_REVIEWER_RESULT_NOT_PASSED")
    if any(
        review.reviewer_result.casefold() == "conflicting"
        for review in observed_reviews
    ):
        blockers.append("ARCHITECTURE_LAYER_REVIEW_CONFLICTING")

    hard_blockers = {
        "ARCHITECTURE_LAYER_WORKFLOW_MISMATCH",
        "ARCHITECTURE_LAYER_UNKNOWN_REVIEW",
        "ARCHITECTURE_LAYER_DUPLICATE_REVIEW",
        "ARCHITECTURE_LAYER_MISSING_REVIEW",
        "ARCHITECTURE_LAYER_CITATION_REQUIRED",
        "ARCHITECTURE_LAYER_REVIEWER_RESULT_NOT_PASSED",
        "ARCHITECTURE_LAYER_REVIEW_CONFLICTING",
        "ARCHITECTURE_LAYER_HARNESS_CONTROL_POINT_MISSING",
        "ARCHITECTURE_LAYER_LOOP_CONTROL_POINT_MISSING",
        "ARCHITECTURE_LAYER_GRAPH_CONTROL_POINT_MISSING",
    }
    final_status = (
        AgentArchitectureLayerStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers) or layer_blockers
        else AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE
    )

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    return AgentArchitectureLayerReduction(
        workflow_id=workflow_id,
        expected_layers=expected_layers,
        observed_layers=observed_layers,
        missing_layers=missing_layers,
        final_status=final_status,
        reviews=observed_reviews,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def summarize_agent_architecture_coverage(
    reduction: AgentArchitectureLayerReduction,
    *,
    source_uri: str,
    source_sha256: str,
) -> AgentArchitectureCoverageSummary:
    blockers = [
        blocker
        for blocker in reduction.blockers
        if blocker not in {"HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"}
    ]
    missing_control_points: list[str] = []
    if not source_uri.startswith("https://"):
        blockers.append("ARCHITECTURE_COVERAGE_EXTERNAL_HTTPS_REQUIRED")

    by_layer = {review.layer: review for review in reduction.reviews}
    for layer in reduction.expected_layers:
        review = by_layer.get(layer)
        expected_controls = _AGENT_ARCHITECTURE_REQUIRED_CONTROL_POINTS[layer]
        if review is None:
            missing_control_points.extend(
                f"{layer.value}:{control}" for control in expected_controls
            )
            continue
        normalized_controls = {control.casefold() for control in review.control_points}
        missing_control_points.extend(
            f"{layer.value}:{control}"
            for control in expected_controls
            if control.casefold() not in normalized_controls
        )

    if missing_control_points:
        blockers.append("ARCHITECTURE_COVERAGE_CONTROL_POINT_MISSING")
    if reduction.final_status is AgentArchitectureLayerStatus.WATCHLIST:
        blockers.append("ARCHITECTURE_COVERAGE_WATCHLIST")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    normalized_blockers = tuple(dict.fromkeys(blockers))
    summary_status = (
        AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE
        if normalized_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else AgentArchitectureLayerStatus.WATCHLIST
    )
    return AgentArchitectureCoverageSummary(
        workflow_id=reduction.workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=summary_status,
        covered_layers=reduction.observed_layers,
        missing_layers=reduction.missing_layers,
        missing_control_points=tuple(dict.fromkeys(missing_control_points)),
        blockers=normalized_blockers,
    )


def summarize_agent_invocation_coverage(
    *,
    workflow_id: str,
    source_uri: str,
    source_sha256: str,
    prompt_revision: str,
    prompt_sha256: str,
    context_sources: tuple[str, ...],
    context_sha256: str,
    context_freshness_policy: str,
    citations: tuple[str, ...],
    redaction_applied: bool,
    private_context_detected: bool,
    tool_output_verified: bool,
    blockers: tuple[str, ...] = (),
) -> AgentInvocationCoverageSummary:
    normalized_blockers = list(blockers)
    if not source_uri.startswith("https://"):
        normalized_blockers.append("AGENT_INVOCATION_SOURCE_HTTPS_REQUIRED")
    if not source_sha256:
        normalized_blockers.append("AGENT_INVOCATION_SOURCE_HASH_REQUIRED")
    if not prompt_revision.strip():
        normalized_blockers.append("AGENT_INVOCATION_PROMPT_REVISION_REQUIRED")
    if not prompt_sha256:
        normalized_blockers.append("AGENT_INVOCATION_PROMPT_HASH_REQUIRED")
    if not context_sources:
        normalized_blockers.append("AGENT_INVOCATION_CONTEXT_SOURCE_REQUIRED")
    if not context_sha256:
        normalized_blockers.append("AGENT_INVOCATION_CONTEXT_HASH_REQUIRED")
    if not context_freshness_policy.strip():
        normalized_blockers.append("AGENT_INVOCATION_CONTEXT_FRESHNESS_REQUIRED")
    if not citations:
        normalized_blockers.append("AGENT_INVOCATION_CITATION_REQUIRED")
    if not redaction_applied:
        normalized_blockers.append("AGENT_INVOCATION_CONTEXT_REDACTION_REQUIRED")
    if private_context_detected:
        normalized_blockers.append("AGENT_INVOCATION_PRIVATE_CONTEXT_DETECTED")
    if not tool_output_verified:
        normalized_blockers.append("AGENT_INVOCATION_TOOL_OUTPUT_UNVERIFIED")

    normalized_blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        AgentInvocationCoverageStatus.RESEARCH_ONLY_AGENT_INVOCATION
        if final_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else AgentInvocationCoverageStatus.WATCHLIST
    )
    return AgentInvocationCoverageSummary(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=status,
        prompt_revision=prompt_revision,
        prompt_sha256=prompt_sha256,
        context_sources=context_sources,
        context_sha256=context_sha256,
        context_freshness_policy=context_freshness_policy,
        citations=citations,
        redaction_applied=redaction_applied,
        private_context_detected=private_context_detected,
        tool_output_verified=tool_output_verified,
        blockers=final_blockers,
    )


def summarize_loop_building_block_coverage(
    *,
    loop_id: str,
    automation_trigger: str,
    worktree_isolation: bool,
    skills_declared: tuple[str, ...],
    connectors_declared: tuple[str, ...],
    subagent_roles: tuple[str, ...],
    memory_sources: tuple[str, ...],
    cost_budget: int,
    stop_conditions: tuple[str, ...],
    human_handoff: bool,
    parallel_edits: bool = False,
    connector_credentials_required: bool = False,
    memory_private_context_detected: bool = False,
    trading_scope_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> LoopBuildingBlockCoverageSummary:
    normalized_blockers = list(blockers)
    if not automation_trigger.strip():
        normalized_blockers.append("LOOP_AUTOMATION_TRIGGER_REQUIRED")
    if parallel_edits and not worktree_isolation:
        normalized_blockers.append("LOOP_WORKTREE_ISOLATION_REQUIRED")
    if not skills_declared:
        normalized_blockers.append("LOOP_SKILL_DECLARATION_REQUIRED")
    if connector_credentials_required:
        normalized_blockers.append("LOOP_CONNECTOR_CREDENTIAL_REVIEW_REQUIRED")
    if not subagent_roles:
        normalized_blockers.append("LOOP_SUBAGENT_REVIEWER_REQUIRED")
    if not memory_sources:
        normalized_blockers.append("LOOP_MEMORY_SOURCE_REQUIRED")
    if cost_budget < 1:
        normalized_blockers.append("LOOP_COST_BUDGET_REQUIRED")
    if not stop_conditions:
        normalized_blockers.append("LOOP_STOP_CONDITION_REQUIRED")
    if not human_handoff:
        normalized_blockers.append("LOOP_HUMAN_HANDOFF_REQUIRED")
    if memory_private_context_detected:
        normalized_blockers.append("LOOP_MEMORY_PRIVATE_CONTEXT_REVIEW_REQUIRED")
    if trading_scope_touched:
        normalized_blockers.append("LOOP_TRADING_SCOPE_REVIEW_REQUIRED")

    normalized_blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        LoopBuildingBlockCoverageStatus.RESEARCH_ONLY_LOOP
        if final_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else LoopBuildingBlockCoverageStatus.WATCHLIST
    )
    return LoopBuildingBlockCoverageSummary(
        loop_id=loop_id,
        automation_trigger=automation_trigger,
        worktree_isolation=worktree_isolation,
        skills_declared=skills_declared,
        connectors_declared=connectors_declared,
        subagent_roles=subagent_roles,
        memory_sources=memory_sources,
        cost_budget=cost_budget,
        stop_conditions=stop_conditions,
        human_handoff=human_handoff,
        status=status,
        blockers=final_blockers,
        parallel_edits=parallel_edits,
        connector_credentials_required=connector_credentials_required,
        memory_private_context_detected=memory_private_context_detected,
        trading_scope_touched=trading_scope_touched,
    )


def review_evaluator_gate(
    *,
    workflow_id: str,
    source_uri: str,
    source_sha256: str,
    generator_model_family: str,
    judge_model_family: str,
    judge_version: str,
    rubric_hash: str,
    rubric_text: str,
    deterministic_checks: tuple[str, ...],
    trajectory_checks: tuple[str, ...],
    faithfulness_result: str,
    task_completion_result: str,
    verifier_canary_passed: bool,
    blast_radius_lane: EvaluatorGateBlastRadiusLane,
    human_disagreement_rate: float,
    agent_self_assessment_weight: float,
    shadow_mode: bool,
    trading_scope_touched: bool = False,
    production_data_touched: bool = False,
    money_movement_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> EvaluatorGateReview:
    normalized_blockers = list(blockers)
    if not source_uri.startswith("https://"):
        normalized_blockers.append("EVALUATOR_GATE_SOURCE_HTTPS_REQUIRED")
    if not source_sha256:
        normalized_blockers.append("EVALUATOR_GATE_SOURCE_HASH_REQUIRED")
    if not generator_model_family.strip():
        normalized_blockers.append("EVALUATOR_GATE_GENERATOR_FAMILY_REQUIRED")
    if not judge_model_family.strip():
        normalized_blockers.append("EVALUATOR_GATE_JUDGE_FAMILY_REQUIRED")
    if (
        generator_model_family.strip()
        and judge_model_family.strip()
        and generator_model_family == judge_model_family
    ):
        normalized_blockers.append("EVALUATOR_GATE_CROSS_FAMILY_JUDGE_REQUIRED")
    if not judge_version.strip():
        normalized_blockers.append("EVALUATOR_GATE_JUDGE_VERSION_REQUIRED")
    if not rubric_hash:
        normalized_blockers.append("EVALUATOR_GATE_RUBRIC_HASH_REQUIRED")
    if not rubric_text.strip():
        normalized_blockers.append("EVALUATOR_GATE_RUBRIC_TEXT_REQUIRED")
    if not deterministic_checks:
        normalized_blockers.append("EVALUATOR_GATE_DETERMINISTIC_CHECK_REQUIRED")
    if not trajectory_checks:
        normalized_blockers.append("EVALUATOR_GATE_TRAJECTORY_CHECK_REQUIRED")
    if faithfulness_result != "PASSED":
        normalized_blockers.append("EVALUATOR_GATE_FAITHFULNESS_NOT_PASSED")
    if task_completion_result != "PASSED":
        normalized_blockers.append("EVALUATOR_GATE_TASK_COMPLETION_NOT_PASSED")
    if not verifier_canary_passed:
        normalized_blockers.append("EVALUATOR_GATE_VERIFIER_CANARY_REQUIRED")
    if blast_radius_lane is EvaluatorGateBlastRadiusLane.HARD_TO_REVERSE:
        normalized_blockers.append("EVALUATOR_GATE_HARD_TO_REVERSE_REVIEW_REQUIRED")
    if human_disagreement_rate > 0:
        normalized_blockers.append("EVALUATOR_GATE_HUMAN_DISAGREEMENT_REVIEW_REQUIRED")
    if agent_self_assessment_weight > 0.1:
        normalized_blockers.append("EVALUATOR_GATE_SELF_ASSESSMENT_WEIGHT_TOO_HIGH")
    if not shadow_mode:
        normalized_blockers.append("EVALUATOR_GATE_SHADOW_MODE_REQUIRED")
    if trading_scope_touched:
        normalized_blockers.append("EVALUATOR_GATE_TRADING_SCOPE_REVIEW_REQUIRED")
    if production_data_touched:
        normalized_blockers.append("EVALUATOR_GATE_PRODUCTION_DATA_REVIEW_REQUIRED")
    if money_movement_touched:
        normalized_blockers.append("EVALUATOR_GATE_MONEY_MOVEMENT_REVIEW_REQUIRED")

    normalized_blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        EvaluatorGateStatus.RESEARCH_ONLY_EVALUATOR_GATE
        if final_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else EvaluatorGateStatus.WATCHLIST
    )
    return EvaluatorGateReview(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=status,
        generator_model_family=generator_model_family,
        judge_model_family=judge_model_family,
        judge_version=judge_version,
        rubric_hash=rubric_hash,
        rubric_text=rubric_text,
        deterministic_checks=deterministic_checks,
        trajectory_checks=trajectory_checks,
        faithfulness_result=faithfulness_result,
        task_completion_result=task_completion_result,
        verifier_canary_passed=verifier_canary_passed,
        blast_radius_lane=blast_radius_lane,
        human_disagreement_rate=human_disagreement_rate,
        agent_self_assessment_weight=agent_self_assessment_weight,
        shadow_mode=shadow_mode,
        blockers=final_blockers,
        trading_scope_touched=trading_scope_touched,
        production_data_touched=production_data_touched,
        money_movement_touched=money_movement_touched,
    )


def review_residual_edge(
    *,
    workflow_id: str,
    source_uri: str,
    source_sha256: str,
    raw_return: float,
    market_component: float,
    sector_or_universe_component: float,
    factor_component: float,
    liquidity_component: float,
    residual_return: float,
    residual_zscore: float,
    expected_value_after_costs: float,
    sample_size: int,
    independent_repetition_count: int,
    fees_bps: float,
    slippage_bps: float,
    capacity_warning: bool,
    regime_split: tuple[str, ...],
    signal_decay_check: str,
    data_leakage_check: str,
    sizing_status: str,
    oos_validation_present: bool,
    trading_scope_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> ResidualEdgeReview:
    normalized_blockers = list(blockers)
    if not source_uri.startswith("https://"):
        normalized_blockers.append("RESIDUAL_EDGE_SOURCE_HTTPS_REQUIRED")
    if not source_sha256:
        normalized_blockers.append("RESIDUAL_EDGE_SOURCE_HASH_REQUIRED")
    if abs(residual_zscore) < 1.0:
        normalized_blockers.append("RESIDUAL_EDGE_STRETCH_TOO_WEAK")
    if expected_value_after_costs <= 0:
        normalized_blockers.append("RESIDUAL_EDGE_NO_TRADE_AFTER_COSTS")
    if sample_size < 100:
        normalized_blockers.append("RESIDUAL_EDGE_SAMPLE_SIZE_TOO_LOW")
    if independent_repetition_count < 30:
        normalized_blockers.append("RESIDUAL_EDGE_REPETITION_COUNT_TOO_LOW")
    if capacity_warning:
        normalized_blockers.append("RESIDUAL_EDGE_CAPACITY_REVIEW_REQUIRED")
    if not regime_split:
        normalized_blockers.append("RESIDUAL_EDGE_REGIME_SPLIT_REQUIRED")
    if signal_decay_check != "PASSED":
        normalized_blockers.append("RESIDUAL_EDGE_SIGNAL_DECAY_NOT_PASSED")
    if data_leakage_check != "PASSED":
        normalized_blockers.append("RESIDUAL_EDGE_DATA_LEAKAGE_REVIEW_REQUIRED")
    if sizing_status != "VALIDATED":
        normalized_blockers.append("RESIDUAL_EDGE_SIZING_VALIDATION_REQUIRED")
    if not oos_validation_present:
        normalized_blockers.append("RESIDUAL_EDGE_OOS_VALIDATION_REQUIRED")
    if trading_scope_touched:
        normalized_blockers.append("RESIDUAL_EDGE_TRADING_SCOPE_REVIEW_REQUIRED")

    normalized_blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        ResidualEdgeReviewStatus.NO_TRADE
        if "RESIDUAL_EDGE_NO_TRADE_AFTER_COSTS" in final_blockers
        else ResidualEdgeReviewStatus.RESEARCH_ONLY_RESIDUAL_EDGE
        if final_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else ResidualEdgeReviewStatus.WATCHLIST
    )
    return ResidualEdgeReview(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=status,
        raw_return=raw_return,
        market_component=market_component,
        sector_or_universe_component=sector_or_universe_component,
        factor_component=factor_component,
        liquidity_component=liquidity_component,
        residual_return=residual_return,
        residual_zscore=residual_zscore,
        expected_value_after_costs=expected_value_after_costs,
        sample_size=sample_size,
        independent_repetition_count=independent_repetition_count,
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        capacity_warning=capacity_warning,
        regime_split=regime_split,
        signal_decay_check=signal_decay_check,
        data_leakage_check=data_leakage_check,
        sizing_status=sizing_status,
        oos_validation_present=oos_validation_present,
        blockers=final_blockers,
        trading_scope_touched=trading_scope_touched,
    )


_BROAD_COWORK_CONNECTOR_SCOPES = frozenset(
    {"*", "all", "everything", "full_access", "whole_digital_life"}
)


def review_cowork_task_suitability(
    *,
    workflow_id: str,
    source_uri: str,
    source_sha256: str,
    task_id: str,
    touches_files_apps_or_web: bool,
    tedious_repetitive_or_multistep: bool,
    done_is_checkable: bool,
    mistake_is_survivable: bool,
    brain_file_present: bool,
    skill_declared: bool,
    connector_scope: tuple[str, ...],
    schedule_requested: bool,
    manual_run_verified: bool,
    draft_only: bool,
    human_approval_required: bool,
    judgment_required: bool,
    secret_access_requested: bool,
    trading_scope_touched: bool,
    money_movement_touched: bool,
    blockers: tuple[str, ...] = (),
) -> CoworkTaskSuitabilityReview:
    normalized_blockers = list(blockers)
    if not source_uri.startswith("https://"):
        normalized_blockers.append("COWORK_TASK_SOURCE_HTTPS_REQUIRED")
    if not source_sha256:
        normalized_blockers.append("COWORK_TASK_SOURCE_HASH_REQUIRED")
    if not task_id.strip():
        normalized_blockers.append("COWORK_TASK_ID_REQUIRED")
    if not touches_files_apps_or_web:
        normalized_blockers.append("COWORK_TASK_SURFACE_REQUIRED")
    if not tedious_repetitive_or_multistep:
        normalized_blockers.append("COWORK_TASK_REPETITION_REQUIRED")
    if not done_is_checkable:
        normalized_blockers.append("COWORK_TASK_CHECKABLE_DONE_REQUIRED")
    if not mistake_is_survivable:
        normalized_blockers.append("COWORK_TASK_SURVIVABLE_MISTAKE_REQUIRED")
    if not brain_file_present:
        normalized_blockers.append("COWORK_TASK_BRAIN_FILE_REQUIRED")
    if not skill_declared:
        normalized_blockers.append("COWORK_TASK_SKILL_REQUIRED")
    if any(
        scope.strip().casefold() in _BROAD_COWORK_CONNECTOR_SCOPES
        for scope in connector_scope
    ):
        normalized_blockers.append("COWORK_TASK_CONNECTOR_SCOPE_TOO_BROAD")
    if schedule_requested and not manual_run_verified:
        normalized_blockers.append("COWORK_TASK_MANUAL_RUN_REQUIRED_BEFORE_SCHEDULE")
    if not draft_only:
        normalized_blockers.append("COWORK_TASK_DRAFT_ONLY_REQUIRED")
    if not human_approval_required:
        normalized_blockers.append("COWORK_TASK_HUMAN_APPROVAL_REQUIRED")
    if judgment_required:
        normalized_blockers.append("COWORK_TASK_JUDGMENT_REVIEW_REQUIRED")
    if secret_access_requested:
        normalized_blockers.append("COWORK_TASK_SECRET_ACCESS_REVIEW_REQUIRED")
    if trading_scope_touched:
        normalized_blockers.append("COWORK_TASK_TRADING_SCOPE_REVIEW_REQUIRED")
    if money_movement_touched:
        normalized_blockers.append("COWORK_TASK_MONEY_MOVEMENT_REVIEW_REQUIRED")

    normalized_blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        CoworkTaskSuitabilityStatus.RESEARCH_ONLY_COWORK_TASK
        if final_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else CoworkTaskSuitabilityStatus.WATCHLIST
    )
    return CoworkTaskSuitabilityReview(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=status,
        task_id=task_id,
        touches_files_apps_or_web=touches_files_apps_or_web,
        tedious_repetitive_or_multistep=tedious_repetitive_or_multistep,
        done_is_checkable=done_is_checkable,
        mistake_is_survivable=mistake_is_survivable,
        brain_file_present=brain_file_present,
        skill_declared=skill_declared,
        connector_scope=connector_scope,
        schedule_requested=schedule_requested,
        manual_run_verified=manual_run_verified,
        draft_only=draft_only,
        human_approval_required=human_approval_required,
        judgment_required=judgment_required,
        secret_access_requested=secret_access_requested,
        trading_scope_touched=trading_scope_touched,
        money_movement_touched=money_movement_touched,
        blockers=final_blockers,
    )


_TRAJECTORY_LEARNING_ALLOWED_INTERVENTIONS = frozenset(
    {
        "NO_OP",
        "MEMORY_CANDIDATE",
        "SKILL_PATCH_CANDIDATE",
        "HARNESS_REVIEW_REQUIRED",
        "TOOL_SCHEMA_REVIEW_REQUIRED",
    }
)


def review_agent_trajectory_learning_eligibility(
    *,
    workflow_id: str,
    source_uri: str,
    source_sha256: str,
    trajectory_id: str,
    trajectory_hash: str,
    replay_class: str,
    privacy_classification: str,
    redaction_status: str,
    reward_signal: str,
    intervention_candidate: str,
    tool_schema_version: str,
    retrieval_snapshot_id: str,
    harness_fingerprint: str,
    model_id: str,
    causal_step_count: int,
    delayed_reward_supported: bool,
    provenance_versioned: bool,
    governance_metadata_present: bool,
    human_correction_present: bool,
    training_eligible: bool,
    secret_risk_detected: bool,
    trading_scope_touched: bool,
    money_movement_touched: bool,
    model_weight_update_requested: bool,
    blockers: tuple[str, ...] = (),
) -> AgentTrajectoryLearningEligibilityReview:
    normalized_blockers = list(blockers)
    if not source_uri.startswith("https://"):
        normalized_blockers.append("TRAJECTORY_LEARNING_SOURCE_HTTPS_REQUIRED")
    if not source_sha256:
        normalized_blockers.append("TRAJECTORY_LEARNING_SOURCE_HASH_REQUIRED")
    if not trajectory_id.strip():
        normalized_blockers.append("TRAJECTORY_LEARNING_ID_REQUIRED")
    if not trajectory_hash:
        normalized_blockers.append("TRAJECTORY_LEARNING_HASH_REQUIRED")
    if replay_class != "DETERMINISTIC_REPLAY":
        normalized_blockers.append("TRAJECTORY_LEARNING_DETERMINISTIC_REPLAY_REQUIRED")
    if redaction_status != "REDACTED":
        normalized_blockers.append("TRAJECTORY_LEARNING_REDACTION_REQUIRED")
    if not privacy_classification.strip():
        normalized_blockers.append("TRAJECTORY_LEARNING_PRIVACY_CLASS_REQUIRED")
    if not reward_signal.strip() or reward_signal == "NONE":
        normalized_blockers.append("TRAJECTORY_LEARNING_REWARD_SIGNAL_REQUIRED")
    if intervention_candidate not in _TRAJECTORY_LEARNING_ALLOWED_INTERVENTIONS:
        normalized_blockers.append(
            "TRAJECTORY_LEARNING_INTERVENTION_SURFACE_REVIEW_REQUIRED"
        )
    if not tool_schema_version.strip():
        normalized_blockers.append("TRAJECTORY_LEARNING_TOOL_SCHEMA_VERSION_REQUIRED")
    if not retrieval_snapshot_id.strip():
        normalized_blockers.append("TRAJECTORY_LEARNING_RETRIEVAL_SNAPSHOT_REQUIRED")
    if not harness_fingerprint.strip():
        normalized_blockers.append("TRAJECTORY_LEARNING_HARNESS_FINGERPRINT_REQUIRED")
    if not model_id.strip():
        normalized_blockers.append("TRAJECTORY_LEARNING_MODEL_ID_REQUIRED")
    if causal_step_count <= 0:
        normalized_blockers.append("TRAJECTORY_LEARNING_CAUSAL_STEP_REQUIRED")
    if not delayed_reward_supported:
        normalized_blockers.append("TRAJECTORY_LEARNING_DELAYED_REWARD_REQUIRED")
    if not provenance_versioned:
        normalized_blockers.append("TRAJECTORY_LEARNING_PROVENANCE_REQUIRED")
    if not governance_metadata_present:
        normalized_blockers.append("TRAJECTORY_LEARNING_GOVERNANCE_METADATA_REQUIRED")
    if not human_correction_present:
        normalized_blockers.append("TRAJECTORY_LEARNING_HUMAN_CORRECTION_REQUIRED")
    if not training_eligible:
        normalized_blockers.append("TRAJECTORY_LEARNING_TRAINING_ELIGIBILITY_REQUIRED")
    if secret_risk_detected:
        normalized_blockers.append("TRAJECTORY_LEARNING_SECRET_RISK_REVIEW_REQUIRED")
    if trading_scope_touched:
        normalized_blockers.append("TRAJECTORY_LEARNING_TRADING_SCOPE_REVIEW_REQUIRED")
    if money_movement_touched:
        normalized_blockers.append("TRAJECTORY_LEARNING_MONEY_SCOPE_REVIEW_REQUIRED")
    if model_weight_update_requested:
        normalized_blockers.append("TRAJECTORY_LEARNING_MODEL_WEIGHT_UPDATE_BLOCKED")

    normalized_blockers.extend(
        ("MODEL_UPDATE_BLOCKED", "HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    )
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        AgentTrajectoryLearningEligibilityStatus.RESEARCH_ONLY_TRAJECTORY_LEARNING
        if final_blockers
        == ("MODEL_UPDATE_BLOCKED", "HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else AgentTrajectoryLearningEligibilityStatus.WATCHLIST
    )
    return AgentTrajectoryLearningEligibilityReview(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=status,
        trajectory_id=trajectory_id,
        trajectory_hash=trajectory_hash,
        replay_class=replay_class,
        privacy_classification=privacy_classification,
        redaction_status=redaction_status,
        reward_signal=reward_signal,
        intervention_candidate=intervention_candidate,
        tool_schema_version=tool_schema_version,
        retrieval_snapshot_id=retrieval_snapshot_id,
        harness_fingerprint=harness_fingerprint,
        model_id=model_id,
        causal_step_count=causal_step_count,
        delayed_reward_supported=delayed_reward_supported,
        provenance_versioned=provenance_versioned,
        governance_metadata_present=governance_metadata_present,
        human_correction_present=human_correction_present,
        training_eligible=training_eligible,
        secret_risk_detected=secret_risk_detected,
        trading_scope_touched=trading_scope_touched,
        money_movement_touched=money_movement_touched,
        model_weight_update_requested=model_weight_update_requested,
        blockers=final_blockers,
    )


def review_graph_dependency_integrity(
    *,
    workflow_id: str,
    source_uri: str,
    source_sha256: str,
    graph_id: str,
    expected_nodes: tuple[str, ...],
    observed_nodes: tuple[str, ...],
    declared_edges: tuple[str, ...],
    data_carrying_edges: tuple[str, ...],
    fake_edges: tuple[str, ...],
    fanout_width: int,
    barrier_count: int,
    verifier_context_isolated: bool,
    anchor_artifacts: tuple[str, ...],
    merge_input_count_verified: bool,
    model_tiering_policy_present: bool,
    cost_cap_present: bool,
    silent_node_failure_count: int,
    trading_scope_touched: bool,
    money_movement_touched: bool,
    blockers: tuple[str, ...] = (),
) -> GraphDependencyIntegrityReview:
    normalized_blockers = list(blockers)
    if not source_uri.startswith("https://"):
        normalized_blockers.append("GRAPH_DEPENDENCY_SOURCE_HTTPS_REQUIRED")
    if not source_sha256:
        normalized_blockers.append("GRAPH_DEPENDENCY_SOURCE_HASH_REQUIRED")
    if not graph_id.strip():
        normalized_blockers.append("GRAPH_DEPENDENCY_GRAPH_ID_REQUIRED")
    if not expected_nodes:
        normalized_blockers.append("GRAPH_DEPENDENCY_EXPECTED_NODE_REQUIRED")
    if set(observed_nodes) - set(expected_nodes):
        normalized_blockers.append("GRAPH_DEPENDENCY_UNKNOWN_NODE_REVIEW_REQUIRED")
    missing_nodes = tuple(
        node for node in expected_nodes if node not in set(observed_nodes)
    )
    if missing_nodes:
        normalized_blockers.append("GRAPH_DEPENDENCY_MISSING_NODE_REVIEW_REQUIRED")
    if not declared_edges:
        normalized_blockers.append("GRAPH_DEPENDENCY_DECLARED_EDGE_REQUIRED")
    if set(data_carrying_edges) - set(declared_edges):
        normalized_blockers.append("GRAPH_DEPENDENCY_UNDECLARED_DATA_EDGE_REQUIRED")
    if set(fake_edges) - set(declared_edges):
        normalized_blockers.append("GRAPH_DEPENDENCY_UNDECLARED_FAKE_EDGE_REQUIRED")
    if not data_carrying_edges:
        normalized_blockers.append("GRAPH_DEPENDENCY_DATA_CARRYING_EDGE_REQUIRED")
    if fake_edges:
        normalized_blockers.append("WATCHLIST_GRAPH_FAKE_EDGE")
    if fanout_width < 2:
        normalized_blockers.append("GRAPH_DEPENDENCY_FANOUT_WIDTH_REQUIRED")
    if barrier_count < 1:
        normalized_blockers.append("GRAPH_DEPENDENCY_BARRIER_REQUIRED")
    if not verifier_context_isolated:
        normalized_blockers.append("WATCHLIST_VERIFIER_CONTEXT_SHARED")
    if not anchor_artifacts:
        normalized_blockers.append("WATCHLIST_GRAPH_ANCHOR_MISSING")
    if not merge_input_count_verified:
        normalized_blockers.append("WATCHLIST_SILENT_NODE_FAILURE_RISK")
    if not model_tiering_policy_present:
        normalized_blockers.append("GRAPH_DEPENDENCY_MODEL_TIERING_POLICY_REQUIRED")
    if not cost_cap_present:
        normalized_blockers.append("WATCHLIST_GRAPH_COST_BOUNDARY_MISSING")
    if silent_node_failure_count > 0:
        normalized_blockers.append("GRAPH_DEPENDENCY_SILENT_NODE_FAILURE_DETECTED")
    if trading_scope_touched:
        normalized_blockers.append("GRAPH_DEPENDENCY_TRADING_SCOPE_REVIEW_REQUIRED")
    if money_movement_touched:
        normalized_blockers.append("GRAPH_DEPENDENCY_MONEY_SCOPE_REVIEW_REQUIRED")

    normalized_blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    final_blockers = tuple(dict.fromkeys(normalized_blockers))
    status = (
        GraphDependencyIntegrityStatus.RESEARCH_ONLY_GRAPH_DEPENDENCY
        if final_blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        else GraphDependencyIntegrityStatus.WATCHLIST
    )
    return GraphDependencyIntegrityReview(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        status=status,
        graph_id=graph_id,
        expected_nodes=expected_nodes,
        observed_nodes=observed_nodes,
        missing_nodes=missing_nodes,
        declared_edges=declared_edges,
        data_carrying_edges=data_carrying_edges,
        fake_edges=fake_edges,
        fanout_width=fanout_width,
        barrier_count=barrier_count,
        verifier_context_isolated=verifier_context_isolated,
        anchor_artifacts=anchor_artifacts,
        merge_input_count_verified=merge_input_count_verified,
        model_tiering_policy_present=model_tiering_policy_present,
        cost_cap_present=cost_cap_present,
        silent_node_failure_count=silent_node_failure_count,
        trading_scope_touched=trading_scope_touched,
        money_movement_touched=money_movement_touched,
        blockers=final_blockers,
    )


def admit_closed_loop(evidence: ClosedLoopAdmissionEvidence) -> ClosedLoopAdmission:
    blockers: list[str] = []
    if evidence.loop_type is not AgentLoopType.CLOSED:
        blockers.append("LOOP_OPEN_SCOPE_REVIEW_REQUIRED")
    if evidence.loop_scale is not AgentLoopScale.SINGLE_AGENT:
        blockers.append("LOOP_FLEET_REVIEW_REQUIRED")
    if not evidence.trigger.strip():
        blockers.append("LOOP_TRIGGER_REQUIRED")
    if not evidence.allowed_tools:
        blockers.append("LOOP_ALLOWED_TOOL_SCOPE_REQUIRED")
    if evidence.allowed_write_roots:
        blockers.append("LOOP_WRITE_SCOPE_REVIEW_REQUIRED")
    if not evidence.memory_sources:
        blockers.append("LOOP_MEMORY_SOURCE_REQUIRED")
    if not evidence.verifier_identity.strip():
        blockers.append("LOOP_VERIFIER_REQUIRED")
    if not evidence.artifact_log_uri.strip():
        blockers.append("LOOP_ARTIFACT_LOG_REQUIRED")
    if not evidence.stop_conditions:
        blockers.append("LOOP_STOP_CONDITION_REQUIRED")
    if not evidence.human_handoff:
        blockers.append("LOOP_HUMAN_HANDOFF_REQUIRED")
    if evidence.connector_requested:
        blockers.append("LOOP_CONNECTOR_REVIEW_REQUIRED")
    if evidence.plugin_requested:
        blockers.append("LOOP_PLUGIN_REVIEW_REQUIRED")
    if evidence.scheduler_requested:
        blockers.append("LOOP_SCHEDULER_REVIEW_REQUIRED")
    if evidence.network_requested:
        blockers.append("LOOP_NETWORK_REVIEW_REQUIRED")
    if evidence.trading_scope_touched:
        blockers.append("LOOP_TRADING_SCOPE_REVIEW_REQUIRED")

    status = (
        ClosedLoopAdmissionStatus.WATCHLIST
        if blockers
        else ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP
    )
    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    return ClosedLoopAdmission(
        loop_id=evidence.loop_id,
        task=evidence.task,
        trigger=evidence.trigger,
        selected_pattern=evidence.selected_pattern,
        loop_type=evidence.loop_type,
        loop_scale=evidence.loop_scale,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        allowed_tools=evidence.allowed_tools,
        allowed_write_roots=evidence.allowed_write_roots,
        memory_sources=evidence.memory_sources,
        verifier_identity=evidence.verifier_identity,
        artifact_log_uri=evidence.artifact_log_uri,
        stop_conditions=evidence.stop_conditions,
        max_iterations=evidence.max_iterations,
        max_cost_units=evidence.max_cost_units,
    )


def summarize_closed_loop_run(
    evidence: ClosedLoopRunEvidence,
) -> ClosedLoopRunSummary:
    blockers = list(evidence.blockers)
    if evidence.admission.status is not ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP:
        blockers.append("LOOP_ADMISSION_NOT_RESEARCH_ONLY")
    if not evidence.state_uri.strip():
        blockers.append("LOOP_STATE_URI_REQUIRED")
    if not evidence.resume_point.strip():
        blockers.append("LOOP_RESUME_POINT_REQUIRED")
    if (
        not evidence.verifier_identity.strip()
        or evidence.verifier_identity != evidence.admission.verifier_identity
    ):
        blockers.append("LOOP_VERIFIER_IDENTITY_MISMATCH")
    if not evidence.state_read_before_frame:
        blockers.append("LOOP_STATE_READ_BEFORE_FRAME_REQUIRED")
    if evidence.verification_passed and not evidence.state_written_after_verification:
        blockers.append("LOOP_STATE_WRITE_AFTER_VERIFY_REQUIRED")
    if not evidence.verification_passed and evidence.state_written_after_verification:
        blockers.append("LOOP_STATE_WRITE_AFTER_FAILED_VERIFY")
    if not evidence.stop_condition_met:
        blockers.append("LOOP_STOP_CONDITION_NOT_MET")
    if evidence.iteration_count > evidence.admission.max_iterations:
        blockers.append("LOOP_ITERATION_BUDGET_EXCEEDED")
    if evidence.cost_units > evidence.admission.max_cost_units:
        blockers.append("LOOP_COST_BUDGET_EXCEEDED")
    if evidence.model_claimed_completion and not evidence.verification_passed:
        blockers.append("LOOP_MODEL_COMPLETION_CLAIM_REQUIRES_VERIFIER")

    hard_blockers = {
        "LOOP_ADMISSION_NOT_RESEARCH_ONLY",
        "LOOP_STATE_URI_REQUIRED",
        "LOOP_RESUME_POINT_REQUIRED",
        "LOOP_VERIFIER_IDENTITY_MISMATCH",
        "LOOP_STATE_READ_BEFORE_FRAME_REQUIRED",
        "LOOP_STATE_WRITE_AFTER_VERIFY_REQUIRED",
        "LOOP_STATE_WRITE_AFTER_FAILED_VERIFY",
        "LOOP_STOP_CONDITION_NOT_MET",
        "LOOP_ITERATION_BUDGET_EXCEEDED",
        "LOOP_COST_BUDGET_EXCEEDED",
        "LOOP_MODEL_COMPLETION_CLAIM_REQUIRES_VERIFIER",
    }
    status = (
        ClosedLoopAdmissionStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP
    )
    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    return ClosedLoopRunSummary(
        loop_id=evidence.admission.loop_id,
        run_id=evidence.run_id,
        trigger_type=evidence.trigger_type,
        status=status,
        state_uri=evidence.state_uri,
        resume_point=evidence.resume_point,
        verifier_identity=evidence.verifier_identity,
        iteration_count=evidence.iteration_count,
        cost_units=evidence.cost_units,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def review_loop_engineering_readiness(
    evidence: LoopEngineeringReadinessEvidence,
) -> LoopEngineeringReadinessReview:
    blockers: list[str] = []
    if not evidence.objective_metric.strip():
        blockers.append("LOOP_OBJECTIVE_METRIC_REQUIRED")
    if not evidence.deterministic_verifier:
        blockers.append("LOOP_DETERMINISTIC_VERIFIER_REQUIRED")
    if not evidence.stop_conditions:
        blockers.append("LOOP_STOP_CONDITION_REQUIRED")
    if not evidence.before_after_metrics:
        blockers.append("LOOP_BEFORE_AFTER_METRIC_REQUIRED")
    if not evidence.rollback_or_no_write:
        blockers.append("LOOP_ROLLBACK_OR_NO_WRITE_REQUIRED")
    if not evidence.artifact_log_uri.strip():
        blockers.append("LOOP_ARTIFACT_LOG_REQUIRED")
    if not evidence.holdout_artifact_uri.strip():
        blockers.append("LOOP_HOLDOUT_EVIDENCE_REQUIRED")
    if not evidence.oos_artifact_uri.strip():
        blockers.append("LOOP_OOS_EVIDENCE_REQUIRED")
    if not evidence.human_gate:
        blockers.append("LOOP_HUMAN_GATE_REQUIRED")
    if evidence.allowed_write_roots:
        blockers.append("LOOP_WRITE_SCOPE_REVIEW_REQUIRED")
    if evidence.provider_runtime_used:
        blockers.append("LOOP_PROVIDER_RUNTIME_REVIEW_REQUIRED")
    if evidence.trading_scope_touched:
        blockers.append("LOOP_TRADING_SCOPE_REVIEW_REQUIRED")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "LOOP_OBJECTIVE_METRIC_REQUIRED",
        "LOOP_DETERMINISTIC_VERIFIER_REQUIRED",
        "LOOP_STOP_CONDITION_REQUIRED",
        "LOOP_BEFORE_AFTER_METRIC_REQUIRED",
        "LOOP_ROLLBACK_OR_NO_WRITE_REQUIRED",
        "LOOP_ARTIFACT_LOG_REQUIRED",
        "LOOP_HOLDOUT_EVIDENCE_REQUIRED",
        "LOOP_OOS_EVIDENCE_REQUIRED",
        "LOOP_HUMAN_GATE_REQUIRED",
        "LOOP_WRITE_SCOPE_REVIEW_REQUIRED",
        "LOOP_PROVIDER_RUNTIME_REVIEW_REQUIRED",
        "LOOP_TRADING_SCOPE_REVIEW_REQUIRED",
    }
    status = (
        LoopEngineeringReadinessStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else LoopEngineeringReadinessStatus.RESEARCH_ONLY_LOOP_PATTERN
    )
    return LoopEngineeringReadinessReview(
        loop_id=evidence.loop_id,
        task=evidence.task,
        selected_pattern=evidence.selected_pattern,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        objective_metric=evidence.objective_metric,
        stop_conditions=evidence.stop_conditions,
        before_after_metrics=evidence.before_after_metrics,
        artifact_log_uri=evidence.artifact_log_uri,
        holdout_artifact_uri=evidence.holdout_artifact_uri,
        oos_artifact_uri=evidence.oos_artifact_uri,
    )


def review_graph_architecture_readiness(
    evidence: GraphArchitectureReadinessEvidence,
    *,
    min_node_count: int = 3,
) -> GraphArchitectureReadinessReview:
    if min_node_count < 2:
        raise ValueError("graph readiness minimum node count is invalid")
    blockers: list[str] = []
    if len(evidence.graph.nodes) < min_node_count:
        blockers.append("GRAPH_NODE_COUNT_TOO_SMALL")
    if not evidence.reviewer_nodes:
        blockers.append("GRAPH_REVIEWER_NODE_REQUIRED")
    if not evidence.independent_reviewers:
        blockers.append("GRAPH_INDEPENDENT_REVIEW_REQUIRED")
    if not evidence.anchor_artifacts:
        blockers.append("GRAPH_ANCHOR_ARTIFACT_REQUIRED")
    if not evidence.counter_metrics:
        blockers.append("GRAPH_COUNTER_METRIC_REQUIRED")
    if not evidence.human_gate_nodes:
        blockers.append("GRAPH_HUMAN_GATE_REQUIRED")
    if not evidence.reducer_nodes:
        blockers.append("GRAPH_REDUCER_NODE_REQUIRED")
    if not evidence.deterministic_reducer:
        blockers.append("GRAPH_DETERMINISTIC_REDUCER_REQUIRED")
    if not evidence.trace_artifacts:
        blockers.append("GRAPH_TRACE_ARTIFACT_RECOMMENDED")
    if evidence.external_runtime_used:
        blockers.append("GRAPH_EXTERNAL_RUNTIME_REVIEW_REQUIRED")
    if any(node.execution_allowed for node in evidence.graph.nodes):
        blockers.append("GRAPH_NODE_AUTHORITY_DRIFT")
    if evidence.graph.execution_allowed:
        blockers.append("GRAPH_EXECUTION_AUTHORITY_DRIFT")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "GRAPH_NODE_COUNT_TOO_SMALL",
        "GRAPH_REVIEWER_NODE_REQUIRED",
        "GRAPH_INDEPENDENT_REVIEW_REQUIRED",
        "GRAPH_ANCHOR_ARTIFACT_REQUIRED",
        "GRAPH_COUNTER_METRIC_REQUIRED",
        "GRAPH_HUMAN_GATE_REQUIRED",
        "GRAPH_REDUCER_NODE_REQUIRED",
        "GRAPH_DETERMINISTIC_REDUCER_REQUIRED",
        "GRAPH_NODE_AUTHORITY_DRIFT",
        "GRAPH_EXECUTION_AUTHORITY_DRIFT",
    }
    status = (
        GraphArchitectureReadinessStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else GraphArchitectureReadinessStatus.RESEARCH_ONLY_GRAPH_PATTERN
    )
    return GraphArchitectureReadinessReview(
        workflow_id=evidence.workflow_id,
        selected_pattern=evidence.selected_pattern,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        reviewer_nodes=evidence.reviewer_nodes,
        anchor_artifacts=evidence.anchor_artifacts,
        counter_metrics=evidence.counter_metrics,
        human_gate_nodes=evidence.human_gate_nodes,
        reducer_nodes=evidence.reducer_nodes,
        trace_artifacts=evidence.trace_artifacts,
    )


def review_graph_workflow_manifest(
    evidence: GraphWorkflowManifestEvidence,
    *,
    max_parallelism_cap: int = 20,
) -> GraphWorkflowManifestReview:
    if not 1 <= max_parallelism_cap <= 256:
        raise ValueError("graph workflow manifest max parallelism cap is invalid")
    blockers: list[str] = list(evidence.declared_blockers)
    node_set = set(evidence.nodes)
    if not evidence.nodes:
        blockers.append("GRAPH_MANIFEST_NODE_REQUIRED")
    if not evidence.edges and len(evidence.nodes) > 1:
        blockers.append("GRAPH_MANIFEST_EDGE_REQUIRED")
    if any(
        source not in node_set or target not in node_set
        for source, target in evidence.edges
    ):
        blockers.append("GRAPH_MANIFEST_EDGE_NODE_UNKNOWN")
    if evidence.edges and _graph_manifest_has_cycle(evidence.nodes, evidence.edges):
        if not evidence.cycles_allowed:
            blockers.append("GRAPH_MANIFEST_CYCLE_REVIEW_REQUIRED")
        if not evidence.human_gate_nodes:
            blockers.append("GRAPH_MANIFEST_CYCLE_HUMAN_GATE_REQUIRED")
    if evidence.parallelism_cap > max_parallelism_cap:
        blockers.append("GRAPH_MANIFEST_PARALLELISM_CAP_REVIEW_REQUIRED")
    if not evidence.expected_artifacts:
        blockers.append("GRAPH_MANIFEST_EXPECTED_ARTIFACT_REQUIRED")
    if not evidence.verifier_nodes:
        blockers.append("GRAPH_MANIFEST_VERIFIER_NODE_REQUIRED")
    elif set(evidence.verifier_nodes) - node_set:
        blockers.append("GRAPH_MANIFEST_VERIFIER_NODE_UNKNOWN")
    if not evidence.human_gate_nodes:
        blockers.append("GRAPH_MANIFEST_HUMAN_GATE_REQUIRED")
    elif set(evidence.human_gate_nodes) - node_set:
        blockers.append("GRAPH_MANIFEST_HUMAN_GATE_NODE_UNKNOWN")
    if not evidence.state_schema_hash:
        blockers.append("GRAPH_MANIFEST_STATE_SCHEMA_HASH_REQUIRED")
    if not evidence.authority_flags:
        blockers.append("GRAPH_MANIFEST_AUTHORITY_FLAG_REQUIRED")
    if _graph_manifest_has_authority_drift(evidence.authority_flags):
        blockers.append("GRAPH_MANIFEST_AUTHORITY_DRIFT")

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "GRAPH_WORKFLOW_MANIFEST_REVIEW_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    hard_blockers = {
        "GRAPH_MANIFEST_NODE_REQUIRED",
        "GRAPH_MANIFEST_EDGE_REQUIRED",
        "GRAPH_MANIFEST_EDGE_NODE_UNKNOWN",
        "GRAPH_MANIFEST_CYCLE_REVIEW_REQUIRED",
        "GRAPH_MANIFEST_CYCLE_HUMAN_GATE_REQUIRED",
        "GRAPH_MANIFEST_PARALLELISM_CAP_REVIEW_REQUIRED",
        "GRAPH_MANIFEST_EXPECTED_ARTIFACT_REQUIRED",
        "GRAPH_MANIFEST_VERIFIER_NODE_REQUIRED",
        "GRAPH_MANIFEST_VERIFIER_NODE_UNKNOWN",
        "GRAPH_MANIFEST_HUMAN_GATE_REQUIRED",
        "GRAPH_MANIFEST_HUMAN_GATE_NODE_UNKNOWN",
        "GRAPH_MANIFEST_STATE_SCHEMA_HASH_REQUIRED",
        "GRAPH_MANIFEST_AUTHORITY_FLAG_REQUIRED",
        "GRAPH_MANIFEST_AUTHORITY_DRIFT",
    }
    status = (
        GraphWorkflowManifestReviewStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else GraphWorkflowManifestReviewStatus.RESEARCH_ONLY_GRAPH_WORKFLOW
    )
    return GraphWorkflowManifestReview(
        workflow_id=evidence.workflow_id,
        selected_pattern=evidence.selected_pattern,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        nodes=evidence.nodes,
        edges=evidence.edges,
        cycles_allowed=evidence.cycles_allowed,
        parallelism_cap=evidence.parallelism_cap,
        expected_artifacts=evidence.expected_artifacts,
        verifier_nodes=evidence.verifier_nodes,
        human_gate_nodes=evidence.human_gate_nodes,
        state_schema_hash=evidence.state_schema_hash,
        authority_flags=evidence.authority_flags,
    )


def _graph_manifest_has_cycle(
    nodes: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
) -> bool:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target in edges:
        if source in adjacency:
            adjacency[source].add(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for target in adjacency.get(node, set()):
            if target in adjacency and visit(target):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in nodes)


def _graph_manifest_has_authority_drift(authority_flags: tuple[str, ...]) -> bool:
    allowed = {"READ_ONLY", "RESEARCH_ONLY", "PAPER_PROPOSAL"}
    risky_terms = (
        "AUTO",
        "CREDENTIAL",
        "EXECUTE",
        "EXECUTION",
        "LIVE",
        "ORDER",
        "SECRET",
        "SIGNAL",
        "TRADE",
        "TRADING",
        "WALLET",
        "WRITE",
    )
    normalized = tuple(flag.strip().upper() for flag in authority_flags)
    return any(flag not in allowed for flag in normalized) or any(
        term in flag for flag in normalized for term in risky_terms
    )


def review_agent_model_candidate(
    evidence: AgentModelCandidateEvidence,
) -> AgentModelCandidateReview:
    blockers = list(evidence.blockers)
    if not evidence.citations:
        blockers.append("PROVIDER_CITATION_REQUIRED")
    if not evidence.data_privacy_boundary.strip():
        blockers.append("PROVIDER_DATA_PRIVACY_BOUNDARY_REQUIRED")
    if not evidence.tool_call_support:
        blockers.append("PROVIDER_TOOL_CALL_SUPPORT_UNVERIFIED")
    if not evidence.json_mode_support:
        blockers.append("PROVIDER_JSON_MODE_SUPPORT_UNVERIFIED")
    if evidence.cached_input_price_per_1m > evidence.input_price_per_1m:
        blockers.append("PROVIDER_CACHED_INPUT_PRICE_EXCEEDS_INPUT_PRICE")
    if evidence.external_runtime_used:
        blockers.append("PROVIDER_EXTERNAL_RUNTIME_REVIEW_REQUIRED")
    if evidence.credential_required:
        blockers.append("PROVIDER_CREDENTIAL_REVIEW_REQUIRED")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "PROVIDER_CITATION_REQUIRED",
        "PROVIDER_DATA_PRIVACY_BOUNDARY_REQUIRED",
        "PROVIDER_TOOL_CALL_SUPPORT_UNVERIFIED",
        "PROVIDER_JSON_MODE_SUPPORT_UNVERIFIED",
        "PROVIDER_CACHED_INPUT_PRICE_EXCEEDS_INPUT_PRICE",
        "PROVIDER_EXTERNAL_RUNTIME_REVIEW_REQUIRED",
        "PROVIDER_CREDENTIAL_REVIEW_REQUIRED",
    }
    status = (
        AgentModelCandidateStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else AgentModelCandidateStatus.RESEARCH_ONLY_PROVIDER
    )
    return AgentModelCandidateReview(
        model_id=evidence.model_id,
        provider=evidence.provider,
        status=status,
        context_window_tokens=evidence.context_window_tokens,
        input_price_per_1m=evidence.input_price_per_1m,
        cached_input_price_per_1m=evidence.cached_input_price_per_1m,
        output_price_per_1m=evidence.output_price_per_1m,
        tool_call_support=evidence.tool_call_support,
        json_mode_support=evidence.json_mode_support,
        data_privacy_boundary=evidence.data_privacy_boundary,
        citations=evidence.citations,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def review_agent_skill_candidate(
    evidence: AgentSkillCandidateEvidence,
) -> AgentSkillCandidateReview:
    blockers = list(evidence.blockers)
    reviewer_result = evidence.reviewer_result.strip().upper()
    if not evidence.citations:
        blockers.append("SKILL_CITATION_REQUIRED")
    if not evidence.trigger_conditions:
        blockers.append("SKILL_TRIGGER_CONDITION_REQUIRED")
    if not evidence.allowed_inputs:
        blockers.append("SKILL_ALLOWED_INPUT_REQUIRED")
    if not evidence.expected_output_contract:
        blockers.append("SKILL_OUTPUT_CONTRACT_REQUIRED")
    if not evidence.review_checklist:
        blockers.append("SKILL_REVIEW_CHECKLIST_REQUIRED")
    if not evidence.test_command.strip():
        blockers.append("SKILL_TEST_COMMAND_REQUIRED")
    if evidence.declared_tools:
        blockers.append("SKILL_TOOL_REVIEW_REQUIRED")
    if evidence.script_paths:
        blockers.append("SKILL_SCRIPT_REVIEW_REQUIRED")
    if evidence.self_generated:
        blockers.append("SELF_GENERATED_SKILL_REVIEW_REQUIRED")
    if evidence.network_access_required:
        blockers.append("SKILL_NETWORK_REVIEW_REQUIRED")
    if evidence.credential_access_required:
        blockers.append("SKILL_CREDENTIAL_REVIEW_REQUIRED")
    if evidence.trading_scope_touched:
        blockers.append("SKILL_TRADING_SCOPE_REVIEW_REQUIRED")
    if reviewer_result in {"WATCHLIST", "FAILED", "REJECTED"}:
        blockers.append("SKILL_REVIEWER_WATCHLIST")
    if reviewer_result == "CONFLICTING":
        blockers.append("SKILL_REVIEW_CONFLICTING")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "SKILL_CITATION_REQUIRED",
        "SKILL_TRIGGER_CONDITION_REQUIRED",
        "SKILL_ALLOWED_INPUT_REQUIRED",
        "SKILL_OUTPUT_CONTRACT_REQUIRED",
        "SKILL_REVIEW_CHECKLIST_REQUIRED",
        "SKILL_TEST_COMMAND_REQUIRED",
        "SKILL_TOOL_REVIEW_REQUIRED",
        "SKILL_SCRIPT_REVIEW_REQUIRED",
        "SELF_GENERATED_SKILL_REVIEW_REQUIRED",
        "SKILL_NETWORK_REVIEW_REQUIRED",
        "SKILL_CREDENTIAL_REVIEW_REQUIRED",
        "SKILL_TRADING_SCOPE_REVIEW_REQUIRED",
        "SKILL_REVIEWER_WATCHLIST",
        "SKILL_REVIEW_CONFLICTING",
    }
    status = (
        AgentSkillCandidateStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else AgentSkillCandidateStatus.RESEARCH_ONLY_SKILL
    )
    return AgentSkillCandidateReview(
        skill_id=evidence.skill_id,
        source_uri=evidence.source_uri,
        source_sha256=evidence.source_sha256,
        declared_goal=evidence.declared_goal,
        status=status,
        trigger_conditions=evidence.trigger_conditions,
        allowed_inputs=evidence.allowed_inputs,
        required_references=evidence.required_references,
        declared_tools=evidence.declared_tools,
        script_paths=evidence.script_paths,
        expected_output_contract=evidence.expected_output_contract,
        review_checklist=evidence.review_checklist,
        test_command=evidence.test_command,
        citations=evidence.citations,
        blockers=tuple(dict.fromkeys(blockers)),
        reviewer_result=evidence.reviewer_result,
    )


def review_agent_workspace_component(
    evidence: AgentWorkspaceComponentEvidence,
) -> AgentWorkspaceComponentReview:
    blockers = list(evidence.blockers)
    if not evidence.citations:
        blockers.append("WORKSPACE_COMPONENT_CITATION_REQUIRED")
    if not evidence.declared_authority.strip():
        blockers.append("WORKSPACE_DECLARED_AUTHORITY_REQUIRED")
    elif evidence.declared_authority not in {"READ_ONLY", "RESEARCH_ONLY"}:
        blockers.append("WORKSPACE_AUTHORITY_REVIEW_REQUIRED")
    if not evidence.canary_command.strip():
        blockers.append("WORKSPACE_CANARY_COMMAND_REQUIRED")
    if not evidence.canary_expected_blockers:
        blockers.append("WORKSPACE_CANARY_EXPECTED_BLOCKER_REQUIRED")
    if "LIVE_ORDER_BLOCKED" not in evidence.canary_expected_blockers:
        blockers.append("WORKSPACE_CANARY_LIVE_BLOCKER_REQUIRED")
    if evidence.external_runtime_used:
        blockers.append("WORKSPACE_EXTERNAL_RUNTIME_REVIEW_REQUIRED")
    if evidence.credential_required:
        blockers.append("WORKSPACE_CREDENTIAL_REVIEW_REQUIRED")
    if evidence.writes_enabled:
        blockers.append("WORKSPACE_WRITE_SCOPE_REVIEW_REQUIRED")
    if evidence.trading_scope_touched:
        blockers.append("WORKSPACE_TRADING_SCOPE_REVIEW_REQUIRED")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "WORKSPACE_COMPONENT_CITATION_REQUIRED",
        "WORKSPACE_DECLARED_AUTHORITY_REQUIRED",
        "WORKSPACE_AUTHORITY_REVIEW_REQUIRED",
        "WORKSPACE_CANARY_COMMAND_REQUIRED",
        "WORKSPACE_CANARY_EXPECTED_BLOCKER_REQUIRED",
        "WORKSPACE_CANARY_LIVE_BLOCKER_REQUIRED",
        "WORKSPACE_EXTERNAL_RUNTIME_REVIEW_REQUIRED",
        "WORKSPACE_CREDENTIAL_REVIEW_REQUIRED",
        "WORKSPACE_WRITE_SCOPE_REVIEW_REQUIRED",
        "WORKSPACE_TRADING_SCOPE_REVIEW_REQUIRED",
    }
    status = (
        AgentWorkspaceComponentStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else AgentWorkspaceComponentStatus.RESEARCH_ONLY_WORKSPACE
    )
    return AgentWorkspaceComponentReview(
        component_id=evidence.component_id,
        component_type=evidence.component_type,
        source_path=evidence.source_path,
        content_sha256=evidence.content_sha256,
        status=status,
        declared_authority=evidence.declared_authority,
        canary_command=evidence.canary_command,
        canary_expected_blockers=evidence.canary_expected_blockers,
        citations=evidence.citations,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def review_markdown_governance_artifact(
    evidence: MarkdownGovernanceArtifactEvidence,
) -> MarkdownGovernanceArtifactReview:
    blockers: list[str] = [*evidence.blockers]
    if not evidence.citations:
        blockers.append("MARKDOWN_CITATION_REQUIRED")
    if not evidence.owner.strip():
        blockers.append("MARKDOWN_OWNER_REQUIRED")
    if not evidence.freshness_policy.strip():
        blockers.append("MARKDOWN_FRESHNESS_POLICY_REQUIRED")
    if evidence.declared_authority not in {"READ_ONLY", "RESEARCH_ONLY"}:
        blockers.append("MARKDOWN_AUTHORITY_REVIEW_REQUIRED")
    if (
        evidence.role is MarkdownGovernanceArtifactRole.VENDOR_BRIDGE
        and not evidence.canonical_source_path.strip()
    ):
        blockers.append("MARKDOWN_VENDOR_BRIDGE_CANONICAL_REQUIRED")
    if evidence.role is MarkdownGovernanceArtifactRole.MEMORY:
        blockers.append("MARKDOWN_MEMORY_PROMOTION_REVIEW_REQUIRED")
    if evidence.reviewer_result is MarkdownGovernanceReviewerResult.PENDING:
        blockers.append("MARKDOWN_REVIEW_PENDING")
    if evidence.reviewer_result is MarkdownGovernanceReviewerResult.WATCHLIST:
        blockers.append("MARKDOWN_REVIEWER_WATCHLIST")
    if evidence.reviewer_result is MarkdownGovernanceReviewerResult.CONFLICTING:
        blockers.append("MARKDOWN_REVIEW_CONFLICTING")
    if evidence.contains_private_context:
        blockers.append("MARKDOWN_PRIVATE_CONTEXT_REDACTION_REQUIRED")
    if evidence.external_runtime_used:
        blockers.append("MARKDOWN_EXTERNAL_RUNTIME_REVIEW_REQUIRED")
    if evidence.credential_required:
        blockers.append("MARKDOWN_CREDENTIAL_REVIEW_REQUIRED")

    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    normalized_blockers = tuple(dict.fromkeys(blockers))
    hard_blockers = {
        "MARKDOWN_CITATION_REQUIRED",
        "MARKDOWN_OWNER_REQUIRED",
        "MARKDOWN_FRESHNESS_POLICY_REQUIRED",
        "MARKDOWN_AUTHORITY_REVIEW_REQUIRED",
        "MARKDOWN_VENDOR_BRIDGE_CANONICAL_REQUIRED",
        "MARKDOWN_MEMORY_PROMOTION_REVIEW_REQUIRED",
        "MARKDOWN_REVIEW_PENDING",
        "MARKDOWN_REVIEWER_WATCHLIST",
        "MARKDOWN_REVIEW_CONFLICTING",
        "MARKDOWN_PRIVATE_CONTEXT_REDACTION_REQUIRED",
        "MARKDOWN_EXTERNAL_RUNTIME_REVIEW_REQUIRED",
        "MARKDOWN_CREDENTIAL_REVIEW_REQUIRED",
    }
    status = (
        MarkdownGovernanceReviewStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in normalized_blockers)
        else MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION
    )
    return MarkdownGovernanceArtifactReview(
        artifact_id=evidence.artifact_id,
        source_path=evidence.source_path,
        content_sha256=evidence.content_sha256,
        role=evidence.role,
        status=status,
        reviewer_result=evidence.reviewer_result,
        declared_authority=evidence.declared_authority,
        citations=evidence.citations,
        owner=evidence.owner,
        freshness_policy=evidence.freshness_policy,
        canonical_source_path=evidence.canonical_source_path,
        blockers=normalized_blockers,
    )


def reduce_markdown_governance_reviews(
    reviews: tuple[MarkdownGovernanceArtifactReview, ...],
    *,
    expected_artifacts: tuple[str, ...],
) -> MarkdownGovernanceReviewReduction:
    by_artifact: dict[str, MarkdownGovernanceArtifactReview] = {}
    reducer_blockers: list[str] = []
    for review in sorted(
        reviews, key=lambda item: (item.artifact_id, item.source_path)
    ):
        if review.artifact_id not in expected_artifacts:
            reducer_blockers.append("UNKNOWN_MARKDOWN_REVIEW_RESULT")
            continue
        if review.artifact_id in by_artifact:
            reducer_blockers.append("DUPLICATE_MARKDOWN_REVIEW_RESULT")
            continue
        by_artifact[review.artifact_id] = review

    observed = tuple(
        artifact for artifact in expected_artifacts if artifact in by_artifact
    )
    missing = tuple(
        artifact for artifact in expected_artifacts if artifact not in by_artifact
    )
    if missing:
        reducer_blockers.append("MISSING_MARKDOWN_REVIEW_RESULT")
    if any(
        review.status is MarkdownGovernanceReviewStatus.WATCHLIST
        for review in by_artifact.values()
    ):
        reducer_blockers.append("WATCHLIST_MARKDOWN_REVIEW_RESULT")
    if any(
        review.reviewer_result is MarkdownGovernanceReviewerResult.CONFLICTING
        for review in by_artifact.values()
    ):
        reducer_blockers.append("CONFLICTING_MARKDOWN_REVIEW_RESULT")

    artifact_blockers = tuple(
        blocker for artifact in observed for blocker in by_artifact[artifact].blockers
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *reducer_blockers,
                *artifact_blockers,
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    unsafe_to_share = bool(missing) or any(
        blocker
        in {
            "UNKNOWN_MARKDOWN_REVIEW_RESULT",
            "DUPLICATE_MARKDOWN_REVIEW_RESULT",
            "MISSING_MARKDOWN_REVIEW_RESULT",
            "WATCHLIST_MARKDOWN_REVIEW_RESULT",
            "CONFLICTING_MARKDOWN_REVIEW_RESULT",
        }
        for blocker in blockers
    )
    final_status = (
        MarkdownGovernanceReviewStatus.WATCHLIST
        if unsafe_to_share
        else MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION
    )
    return MarkdownGovernanceReviewReduction(
        expected_artifacts=expected_artifacts,
        observed_artifacts=observed,
        missing_artifacts=missing,
        final_status=final_status,
        blockers=blockers,
        reviews=tuple(by_artifact[artifact] for artifact in observed),
    )


def reduce_opportunity_artifact_reviews(
    reviews: tuple[OpportunityArtifactReviewResult, ...],
    *,
    expected_branches: tuple[str, ...] = OPPORTUNITY_RESEARCH_BRANCH_IDS,
    supporting_workspace_reviews: tuple[AgentWorkspaceComponentReview, ...] = (),
    architecture_coverage_summary: AgentArchitectureCoverageSummary | None = None,
    invocation_coverage_summary: AgentInvocationCoverageSummary | None = None,
    loop_building_block_coverage_summary: (
        LoopBuildingBlockCoverageSummary | None
    ) = None,
    evaluator_gate_review: EvaluatorGateReview | None = None,
    residual_edge_review: ResidualEdgeReview | None = None,
    cowork_task_suitability_review: CoworkTaskSuitabilityReview | None = None,
    trajectory_learning_eligibility_review: (
        AgentTrajectoryLearningEligibilityReview | None
    ) = None,
    graph_dependency_integrity_review: GraphDependencyIntegrityReview | None = None,
    expected_workspace_components: tuple[str, ...] = (),
) -> OpportunityArtifactReviewReduction:
    by_workspace_component: dict[str, AgentWorkspaceComponentReview] = {}
    workspace_reducer_blockers: list[str] = []
    for review in sorted(
        supporting_workspace_reviews,
        key=lambda item: (item.component_id, item.source_path),
    ):
        if (
            expected_workspace_components
            and review.component_id not in expected_workspace_components
        ):
            workspace_reducer_blockers.append("UNKNOWN_WORKSPACE_COMPONENT_REVIEW")
            continue
        if review.component_id in by_workspace_component:
            workspace_reducer_blockers.append("DUPLICATE_WORKSPACE_COMPONENT_REVIEW")
            continue
        by_workspace_component[review.component_id] = review
    observed_workspace = (
        tuple(
            component
            for component in expected_workspace_components
            if component in by_workspace_component
        )
        if expected_workspace_components
        else tuple(by_workspace_component)
    )
    missing_workspace = tuple(
        component
        for component in expected_workspace_components
        if component not in by_workspace_component
    )
    if missing_workspace:
        workspace_reducer_blockers.append("MISSING_WORKSPACE_COMPONENT_REVIEW")
    if any(
        review.status is AgentWorkspaceComponentStatus.WATCHLIST
        for review in by_workspace_component.values()
    ):
        workspace_reducer_blockers.append("WATCHLIST_WORKSPACE_COMPONENT_REVIEW")
    workspace_blockers = tuple(
        blocker
        for component in observed_workspace
        for blocker in by_workspace_component[component].blockers
    )
    architecture_reducer_blockers: tuple[str, ...] = ()
    architecture_blockers: tuple[str, ...] = ()
    if architecture_coverage_summary is not None:
        architecture_blockers = architecture_coverage_summary.blockers
        if (
            architecture_coverage_summary.status
            is AgentArchitectureLayerStatus.WATCHLIST
        ):
            architecture_reducer_blockers = ("WATCHLIST_AGENT_ARCHITECTURE_COVERAGE",)
    invocation_reducer_blockers: tuple[str, ...] = ()
    invocation_blockers: tuple[str, ...] = ()
    if invocation_coverage_summary is not None:
        invocation_blockers = invocation_coverage_summary.blockers
        if (
            invocation_coverage_summary.status
            is AgentInvocationCoverageStatus.WATCHLIST
        ):
            invocation_reducer_blockers = ("WATCHLIST_AGENT_INVOCATION_COVERAGE",)
    loop_building_reducer_blockers: tuple[str, ...] = ()
    loop_building_blockers: tuple[str, ...] = ()
    if loop_building_block_coverage_summary is not None:
        loop_building_blockers = loop_building_block_coverage_summary.blockers
        if (
            loop_building_block_coverage_summary.status
            is LoopBuildingBlockCoverageStatus.WATCHLIST
        ):
            loop_building_reducer_blockers = ("WATCHLIST_LOOP_BUILDING_BLOCK_COVERAGE",)
    evaluator_gate_reducer_blockers: tuple[str, ...] = ()
    evaluator_gate_blockers: tuple[str, ...] = ()
    if evaluator_gate_review is not None:
        evaluator_gate_blockers = evaluator_gate_review.blockers
        if evaluator_gate_review.status is EvaluatorGateStatus.WATCHLIST:
            evaluator_gate_reducer_blockers = ("WATCHLIST_EVALUATOR_GATE_REVIEW",)
    residual_edge_reducer_blockers: tuple[str, ...] = ()
    residual_edge_blockers: tuple[str, ...] = ()
    if residual_edge_review is not None:
        residual_edge_blockers = residual_edge_review.blockers
        if residual_edge_review.status is ResidualEdgeReviewStatus.WATCHLIST:
            residual_edge_reducer_blockers = ("WATCHLIST_RESIDUAL_EDGE_REVIEW",)
        elif residual_edge_review.status is ResidualEdgeReviewStatus.NO_TRADE:
            residual_edge_reducer_blockers = ("NO_TRADE_RESIDUAL_EDGE_REVIEW",)
    cowork_task_reducer_blockers: tuple[str, ...] = ()
    cowork_task_blockers: tuple[str, ...] = ()
    if cowork_task_suitability_review is not None:
        cowork_task_blockers = cowork_task_suitability_review.blockers
        if (
            cowork_task_suitability_review.status
            is CoworkTaskSuitabilityStatus.WATCHLIST
        ):
            cowork_task_reducer_blockers = ("WATCHLIST_COWORK_TASK_SUITABILITY",)
    trajectory_learning_reducer_blockers: tuple[str, ...] = ()
    trajectory_learning_blockers: tuple[str, ...] = ()
    if trajectory_learning_eligibility_review is not None:
        trajectory_learning_blockers = trajectory_learning_eligibility_review.blockers
        if (
            trajectory_learning_eligibility_review.status
            is AgentTrajectoryLearningEligibilityStatus.WATCHLIST
        ):
            trajectory_learning_reducer_blockers = (
                "WATCHLIST_TRAJECTORY_LEARNING_ELIGIBILITY",
            )
    graph_dependency_reducer_blockers: tuple[str, ...] = ()
    graph_dependency_blockers: tuple[str, ...] = ()
    if graph_dependency_integrity_review is not None:
        graph_dependency_blockers = graph_dependency_integrity_review.blockers
        if (
            graph_dependency_integrity_review.status
            is GraphDependencyIntegrityStatus.WATCHLIST
        ):
            graph_dependency_reducer_blockers = (
                "WATCHLIST_GRAPH_DEPENDENCY_INTEGRITY",
            )
    if not reviews:
        return OpportunityArtifactReviewReduction(
            expected_branches=expected_branches,
            observed_branches=(),
            missing_branches=expected_branches,
            final_status=OpportunityArtifactReductionStatus.WATCHLIST,
            blockers=tuple(
                dict.fromkeys(
                    (
                        "MISSING_BRANCH_REVIEW_RESULT",
                        *workspace_reducer_blockers,
                        *workspace_blockers,
                        *architecture_reducer_blockers,
                        *architecture_blockers,
                        *invocation_reducer_blockers,
                        *invocation_blockers,
                        *loop_building_reducer_blockers,
                        *loop_building_blockers,
                        *evaluator_gate_reducer_blockers,
                        *evaluator_gate_blockers,
                        *residual_edge_reducer_blockers,
                        *residual_edge_blockers,
                        *cowork_task_reducer_blockers,
                        *cowork_task_blockers,
                        *trajectory_learning_reducer_blockers,
                        *trajectory_learning_blockers,
                        *graph_dependency_reducer_blockers,
                        *graph_dependency_blockers,
                        "HUMAN_REVIEW_REQUIRED",
                        "LIVE_ORDER_BLOCKED",
                    )
                )
            ),
            reviews=(),
            supporting_workspace_reviews=tuple(
                by_workspace_component[component] for component in observed_workspace
            ),
            architecture_coverage_summary=architecture_coverage_summary,
            invocation_coverage_summary=invocation_coverage_summary,
            loop_building_block_coverage_summary=loop_building_block_coverage_summary,
            evaluator_gate_review=evaluator_gate_review,
            residual_edge_review=residual_edge_review,
            cowork_task_suitability_review=cowork_task_suitability_review,
            trajectory_learning_eligibility_review=(
                trajectory_learning_eligibility_review
            ),
            graph_dependency_integrity_review=graph_dependency_integrity_review,
            expected_workspace_components=expected_workspace_components,
            observed_workspace_components=observed_workspace,
            missing_workspace_components=missing_workspace,
        )
    by_branch: dict[str, OpportunityArtifactReviewResult] = {}
    reducer_blockers: list[str] = []
    for branch_review_result in sorted(
        reviews, key=lambda item: (item.branch_id, item.artifact_uri)
    ):
        if branch_review_result.branch_id not in expected_branches:
            reducer_blockers.append("UNKNOWN_BRANCH_REVIEW_RESULT")
            continue
        if branch_review_result.branch_id in by_branch:
            reducer_blockers.append("DUPLICATE_BRANCH_REVIEW_RESULT")
            continue
        by_branch[branch_review_result.branch_id] = branch_review_result
    observed = tuple(branch for branch in expected_branches if branch in by_branch)
    missing = tuple(branch for branch in expected_branches if branch not in by_branch)
    if missing:
        reducer_blockers.append("MISSING_BRANCH_REVIEW_RESULT")
    if any(
        review.reviewer_result is OpportunityArtifactReviewStatus.CONFLICTING
        for review in by_branch.values()
    ):
        reducer_blockers.append("CONFLICTING_BRANCH_REVIEW_RESULT")
    branch_blockers = tuple(
        blocker for branch in observed for blocker in by_branch[branch].blockers
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *reducer_blockers,
                *branch_blockers,
                *workspace_reducer_blockers,
                *workspace_blockers,
                *architecture_reducer_blockers,
                *architecture_blockers,
                *invocation_reducer_blockers,
                *invocation_blockers,
                *loop_building_reducer_blockers,
                *loop_building_blockers,
                *evaluator_gate_reducer_blockers,
                *evaluator_gate_blockers,
                *residual_edge_reducer_blockers,
                *residual_edge_blockers,
                *cowork_task_reducer_blockers,
                *cowork_task_blockers,
                *trajectory_learning_reducer_blockers,
                *trajectory_learning_blockers,
                *graph_dependency_reducer_blockers,
                *graph_dependency_blockers,
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    unsafe_to_promote = bool(missing) or any(
        blocker
        in {
            "UNKNOWN_BRANCH_REVIEW_RESULT",
            "DUPLICATE_BRANCH_REVIEW_RESULT",
            "CONFLICTING_BRANCH_REVIEW_RESULT",
            "UNKNOWN_WORKSPACE_COMPONENT_REVIEW",
            "DUPLICATE_WORKSPACE_COMPONENT_REVIEW",
            "MISSING_WORKSPACE_COMPONENT_REVIEW",
            "WATCHLIST_WORKSPACE_COMPONENT_REVIEW",
            "WATCHLIST_AGENT_ARCHITECTURE_COVERAGE",
            "WATCHLIST_AGENT_INVOCATION_COVERAGE",
            "WATCHLIST_LOOP_BUILDING_BLOCK_COVERAGE",
            "WATCHLIST_EVALUATOR_GATE_REVIEW",
            "WATCHLIST_RESIDUAL_EDGE_REVIEW",
            "NO_TRADE_RESIDUAL_EDGE_REVIEW",
            "WATCHLIST_COWORK_TASK_SUITABILITY",
            "WATCHLIST_TRAJECTORY_LEARNING_ELIGIBILITY",
            "WATCHLIST_GRAPH_DEPENDENCY_INTEGRITY",
        }
        for blocker in blockers
    )
    watchlisted = any(
        review.reviewer_result is OpportunityArtifactReviewStatus.WATCHLIST
        for review in by_branch.values()
    )
    final_status = (
        OpportunityArtifactReductionStatus.WATCHLIST
        if unsafe_to_promote or watchlisted
        else OpportunityArtifactReductionStatus.RESEARCH_ONLY_OPPORTUNITY
    )
    return OpportunityArtifactReviewReduction(
        expected_branches=expected_branches,
        observed_branches=observed,
        missing_branches=missing,
        final_status=final_status,
        blockers=blockers,
        reviews=tuple(by_branch[branch] for branch in observed),
        supporting_workspace_reviews=tuple(
            by_workspace_component[component] for component in observed_workspace
        ),
        architecture_coverage_summary=architecture_coverage_summary,
        invocation_coverage_summary=invocation_coverage_summary,
        loop_building_block_coverage_summary=loop_building_block_coverage_summary,
        evaluator_gate_review=evaluator_gate_review,
        residual_edge_review=residual_edge_review,
        cowork_task_suitability_review=cowork_task_suitability_review,
        trajectory_learning_eligibility_review=trajectory_learning_eligibility_review,
        graph_dependency_integrity_review=graph_dependency_integrity_review,
        expected_workspace_components=expected_workspace_components,
        observed_workspace_components=observed_workspace,
        missing_workspace_components=missing_workspace,
    )


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values) or any(not value.strip() for value in values):
        raise ValueError(f"{name} must be unique and non-empty")


def _require_finite_nonnegative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _require_timezone_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _is_repo_relative_loop_path(value: str) -> bool:
    if re.match(r"^[A-Za-z]:", value) or value.startswith(("/", "\\")):
        return False
    parts = tuple(part for part in re.split(r"[\\/]+", value) if part)
    return bool(parts) and ".." not in parts


def _is_repo_relative_markdown_path(value: str) -> bool:
    if not _is_repo_relative_loop_path(value):
        return False
    return value.lower().endswith((".md", ".mdx"))


def opportunity_research_diamond_workflow() -> WorkflowGraph:
    branches = OPPORTUNITY_RESEARCH_BRANCH_IDS
    definitions = (
        (
            "opportunity_inputs",
            "OPPORTUNITY_INPUTS",
            (),
            ("symbol_config.json", "timeframe_config.json"),
            ("opportunity_inputs.json",),
            WorkflowAuthority.READ_ONLY,
            ("RESEARCH_ONLY", "LIVE_ORDER_BLOCKED"),
        ),
        (
            "market_outlook_branch",
            "MARKET_OUTLOOK_BRANCH",
            ("opportunity_inputs",),
            ("opportunity_inputs.json", "market_outlook_state.json"),
            ("market_outlook_findings.json",),
            WorkflowAuthority.RESEARCH_ONLY,
            ("NO_TRADE_ON_WEAK_EVIDENCE",),
        ),
        (
            "setup_family_branch",
            "SETUP_FAMILY_BRANCH",
            ("opportunity_inputs",),
            ("opportunity_inputs.json", "strategy_registry.json"),
            ("setup_family_findings.json",),
            WorkflowAuthority.RESEARCH_ONLY,
            ("VALIDATION_GATE_REQUIRED",),
        ),
        (
            "backtest_oos_branch",
            "BACKTEST_OOS_BRANCH",
            ("opportunity_inputs",),
            ("opportunity_inputs.json", "validation_run_cards.json"),
            ("backtest_oos_findings.json",),
            WorkflowAuthority.RESEARCH_ONLY,
            ("OOS_EVIDENCE_REQUIRED",),
        ),
        (
            "portfolio_context_branch",
            "PORTFOLIO_CONTEXT_BRANCH",
            ("opportunity_inputs",),
            ("opportunity_inputs.json", "read_only_account_snapshot.json"),
            ("portfolio_context_findings.json",),
            WorkflowAuthority.READ_ONLY,
            ("WALLET_BACKTEST_ISOLATION_REQUIRED",),
        ),
        (
            "whale_fusion_branch",
            "WHALE_FUSION_BRANCH",
            ("opportunity_inputs",),
            ("opportunity_inputs.json", "whale_fusion_replay.json"),
            ("whale_fusion_findings.json",),
            WorkflowAuthority.RESEARCH_ONLY,
            ("SUPPLEMENTARY_ONLY",),
        ),
        (
            "opportunity_reduce",
            "DETERMINISTIC_REDUCER",
            branches,
            tuple(
                f"{branch.removesuffix('_branch')}_findings.json" for branch in branches
            ),
            ("deduped_opportunity_candidates.json",),
            WorkflowAuthority.READ_ONLY,
            ("FAN_IN_COUNT_REQUIRED", "MISSING_BRANCH_IS_BLOCKER"),
        ),
        (
            "fresh_skeptic_verify",
            "FRESH_SKEPTIC_VERIFY",
            ("opportunity_reduce",),
            ("deduped_opportunity_candidates.json",),
            ("verified_opportunity_candidates.json",),
            WorkflowAuthority.RESEARCH_ONLY,
            ("FRESH_CONTEXT_VERIFIER_REQUIRED", "HUMAN_REVIEW_REQUIRED"),
        ),
        (
            "opportunity_report",
            "OPPORTUNITY_REPORT",
            ("fresh_skeptic_verify",),
            ("verified_opportunity_candidates.json",),
            ("opportunity_research_report.md",),
            WorkflowAuthority.RESEARCH_ONLY,
            ("RESEARCH_ONLY_OPPORTUNITY", "VALIDATION_GATE_REQUIRED"),
        ),
        (
            "human_review_gate",
            "HUMAN_REVIEW_GATE",
            ("opportunity_report",),
            ("opportunity_research_report.md",),
            ("human_review_required.json",),
            WorkflowAuthority.READ_ONLY,
            ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
    )
    return WorkflowGraph(
        graph_id="opportunity-research-diamond",
        nodes=tuple(
            WorkflowNode(
                node_id=node_id,
                node_type=node_type,
                dependencies=dependencies,
                input_artifacts=input_artifacts,
                output_artifacts=output_artifacts,
                timeout_seconds=120,
                authority=authority,
                blockers=blockers,
            )
            for (
                node_id,
                node_type,
                dependencies,
                input_artifacts,
                output_artifacts,
                authority,
                blockers,
            ) in definitions
        ),
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

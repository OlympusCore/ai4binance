from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, cast

import pytest

from ai4binance.governance import workflow as wf
from tests import test_agent_runtime_governance as fixtures


def _architecture_reduction() -> wf.AgentArchitectureLayerReduction:
    return wf.reduce_agent_architecture_layer_reviews(
        tuple(
            fixtures.architecture_layer_evidence(layer)
            for layer in wf.AGENT_ARCHITECTURE_LAYERS
        ),
        workflow_id="opportunity-research-diamond",
    )


def _architecture_summary() -> wf.AgentArchitectureCoverageSummary:
    return wf.summarize_agent_architecture_coverage(
        _architecture_reduction(),
        source_uri="https://example.com/architecture",
        source_sha256=fixtures.HASH,
    )


def _graph_trace() -> wf.GraphRunTrace:
    return wf.GraphRunTrace(
        run_id="run-1",
        graph_id="graph",
        terminal_state=wf.GraphRunTerminalState.COMPLETED,
        checkpoints=(fixtures.graph_checkpoint("node"),),
        blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        max_cost_units=1,
        max_retry_count=0,
    )


def _route_reduction() -> wf.GraphNodeRouteReduction:
    return wf.GraphNodeRouteReduction(
        graph_id="graph",
        run_id="run-1",
        expected_nodes=("node",),
        observed_nodes=("node",),
        missing_nodes=(),
        terminal_state=wf.GraphRunTerminalState.COMPLETED,
        decisions=(fixtures.route_decision("node", graph_id="graph"),),
        blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        max_cost_units=1,
        max_retry_count=0,
    )


def _workspace_review() -> wf.AgentWorkspaceComponentReview:
    return wf.review_agent_workspace_component(fixtures.workspace_component())


def _markdown_review() -> wf.MarkdownGovernanceArtifactReview:
    return wf.review_markdown_governance_artifact(
        fixtures.markdown_governance_artifact()
    )


def _markdown_reduction() -> wf.MarkdownGovernanceReviewReduction:
    return wf.reduce_markdown_governance_reviews(
        (_markdown_review(),),
        expected_artifacts=("architecture-md",),
    )


def _opportunity_reduction() -> wf.OpportunityArtifactReviewReduction:
    return wf.reduce_opportunity_artifact_reviews(
        tuple(
            fixtures.branch_review(branch)
            for branch in wf.OPPORTUNITY_RESEARCH_BRANCH_IDS
        )
    )


def _workspace_opportunity_reduction() -> wf.OpportunityArtifactReviewReduction:
    review = _workspace_review()
    return wf.reduce_opportunity_artifact_reviews(
        tuple(
            fixtures.branch_review(branch)
            for branch in wf.OPPORTUNITY_RESEARCH_BRANCH_IDS
        ),
        supporting_workspace_reviews=(review,),
        expected_workspace_components=(review.component_id,),
    )


def _graph_readiness_evidence() -> wf.GraphArchitectureReadinessEvidence:
    graph = wf.opportunity_research_diamond_workflow()
    return wf.GraphArchitectureReadinessEvidence(
        workflow_id=graph.graph_id,
        selected_pattern="parallelization+evaluator-optimizer+human-in-the-loop",
        graph=graph,
        reviewer_nodes=("fresh_skeptic_verify",),
        anchor_artifacts=("artifact://reducer-inputs",),
        counter_metrics=("net_return_vs_max_drawdown",),
        human_gate_nodes=("human_review_gate",),
        reducer_nodes=("opportunity_reduce",),
        independent_reviewers=True,
        deterministic_reducer=True,
        trace_artifacts=("artifact://graph-trace",),
    )


InvalidFactory = Callable[[], object]


class ReviewResult(Protocol):
    blockers: tuple[str, ...]
    execution_allowed: bool
    live_eligibility_status: str


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(fixtures.graph_checkpoint("node"), run_id=""),
        lambda: replace(_graph_trace(), max_cost_units=0),
        lambda: replace(_graph_trace(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(
            fixtures.route_decision(
                "node",
                graph_id="graph",
                blockers=("UNSAFE_ROUTE", "LIVE_ORDER_BLOCKED"),
            ),
            blockers=("UNSAFE_ROUTE",),
        ),
        lambda: replace(_route_reduction(), graph_id=""),
        lambda: replace(_route_reduction(), max_retry_count=-1),
        lambda: replace(_route_reduction(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(_architecture_reduction(), workflow_id=""),
        lambda: replace(
            _architecture_reduction(),
            expected_layers=(
                wf.AgentArchitectureLayer.HARNESS,
                wf.AgentArchitectureLayer.HARNESS,
            ),
        ),
        lambda: replace(
            _architecture_reduction(),
            expected_layers=(wf.AgentArchitectureLayer.HARNESS,),
            observed_layers=(wf.AgentArchitectureLayer.LOOP,),
            missing_layers=(wf.AgentArchitectureLayer.HARNESS,),
            reviews=(
                fixtures.architecture_layer_evidence(wf.AgentArchitectureLayer.LOOP),
            ),
        ),
        lambda: replace(
            _architecture_reduction(),
            missing_layers=(wf.AgentArchitectureLayer.GRAPH,),
        ),
        lambda: replace(
            _architecture_reduction(),
            reviews=(
                fixtures.architecture_layer_evidence(wf.AgentArchitectureLayer.HARNESS),
                fixtures.architecture_layer_evidence(wf.AgentArchitectureLayer.HARNESS),
            ),
        ),
        lambda: replace(_architecture_reduction(), reviews=()),
        lambda: replace(_architecture_reduction(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(_architecture_summary(), workflow_id=""),
        lambda: replace(
            _architecture_summary(),
            covered_layers=(
                wf.AgentArchitectureLayer.HARNESS,
                wf.AgentArchitectureLayer.HARNESS,
            ),
        ),
        lambda: replace(_architecture_summary(), blockers=("LIVE_ORDER_BLOCKED",)),
        lambda: replace(_architecture_summary(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(fixtures.invocation_coverage_summary(), workflow_id=""),
        lambda: replace(
            fixtures.invocation_coverage_summary(),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(fixtures.loop_building_block_coverage_summary(), loop_id=""),
        lambda: replace(
            fixtures.loop_building_block_coverage_summary(),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(fixtures.evaluator_gate_review(), workflow_id=""),
        lambda: replace(
            fixtures.evaluator_gate_review(), blockers=("LIVE_ORDER_BLOCKED",)
        ),
        lambda: replace(fixtures.residual_edge_review(), workflow_id=""),
        lambda: replace(fixtures.residual_edge_review(), sample_size=-1),
        lambda: replace(
            fixtures.residual_edge_review(), blockers=("LIVE_ORDER_BLOCKED",)
        ),
        lambda: replace(
            fixtures.residual_edge_review(), blockers=("HUMAN_REVIEW_REQUIRED",)
        ),
        lambda: replace(fixtures.cowork_task_suitability_review(), workflow_id=""),
        lambda: replace(
            fixtures.cowork_task_suitability_review(),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            fixtures.trajectory_learning_eligibility_review(), workflow_id=""
        ),
        lambda: replace(
            fixtures.trajectory_learning_eligibility_review(),
            blockers=("MODEL_UPDATE_BLOCKED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(
            fixtures.graph_dependency_integrity_review(),
            missing_nodes=("unexpected",),
        ),
        lambda: replace(fixtures.graph_dependency_integrity_review(), fanout_width=-1),
        lambda: replace(
            fixtures.graph_dependency_integrity_review(),
            silent_node_failure_count=-1,
        ),
        lambda: replace(
            fixtures.graph_dependency_integrity_review(),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            fixtures.graph_dependency_integrity_review(),
            blockers=("HUMAN_REVIEW_REQUIRED",),
        ),
        lambda: replace(
            wf.review_agent_model_candidate(fixtures.model_candidate()),
            blockers=("HUMAN_REVIEW_REQUIRED",),
        ),
        lambda: replace(
            wf.review_agent_skill_candidate(fixtures.skill_candidate()),
            source_uri="",
        ),
        lambda: replace(
            wf.review_agent_skill_candidate(fixtures.skill_candidate()),
            source_sha256="bad",
        ),
        lambda: replace(
            wf.review_agent_skill_candidate(fixtures.skill_candidate()),
            reviewer_result="",
        ),
        lambda: replace(
            wf.review_agent_skill_candidate(fixtures.skill_candidate()),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(_workspace_review(), component_id=""),
        lambda: replace(_workspace_review(), content_sha256="bad"),
        lambda: replace(_workspace_review(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(
            fixtures.markdown_governance_artifact(),
            canonical_source_path="C:/outside.md",
        ),
        lambda: replace(_markdown_review(), artifact_id=""),
        lambda: replace(_markdown_review(), source_path="README.txt"),
        lambda: replace(_markdown_review(), canonical_source_path="C:/outside.md"),
        lambda: replace(_markdown_review(), content_sha256="bad"),
        lambda: replace(_markdown_review(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(_markdown_reduction(), expected_artifacts=()),
        lambda: replace(_markdown_reduction(), missing_artifacts=("architecture-md",)),
        lambda: replace(
            _markdown_reduction(), reviews=(_markdown_review(), _markdown_review())
        ),
        lambda: replace(_markdown_reduction(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(fixtures.branch_review("market_outlook_branch"), branch_id=""),
        lambda: replace(
            fixtures.branch_review("market_outlook_branch"),
            reviewer_notes=("same", "same"),
        ),
        lambda: replace(
            fixtures.branch_review("market_outlook_branch"),
            reviewer_notes=("",),
        ),
        lambda: replace(
            fixtures.branch_review("market_outlook_branch"),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(_opportunity_reduction(), expected_branches=()),
        lambda: replace(
            _opportunity_reduction(),
            expected_branches=(
                "market_outlook_branch",
                "market_outlook_branch",
            ),
        ),
        lambda: replace(_opportunity_reduction(), blockers=("",)),
        lambda: replace(
            _opportunity_reduction(),
            observed_branches=("unknown",),
            missing_branches=wf.OPPORTUNITY_RESEARCH_BRANCH_IDS,
        ),
        lambda: replace(_opportunity_reduction(), missing_branches=("unexpected",)),
        lambda: replace(
            _workspace_opportunity_reduction(),
            supporting_workspace_reviews=(_workspace_review(), _workspace_review()),
        ),
        lambda: replace(
            _workspace_opportunity_reduction(),
            expected_workspace_components=("other",),
            observed_workspace_components=("ai4binance-validation-first",),
            missing_workspace_components=("other",),
        ),
        lambda: replace(
            _workspace_opportunity_reduction(),
            expected_workspace_components=(
                "ai4binance-validation-first",
                "other",
            ),
            missing_workspace_components=(),
        ),
        lambda: replace(
            _opportunity_reduction(),
            missing_workspace_components=("unrequested",),
        ),
        lambda: replace(
            _opportunity_reduction(),
            observed_workspace_components=("unreviewed",),
        ),
        lambda: replace(
            _opportunity_reduction(),
            architecture_coverage_summary=replace(
                _architecture_summary(), workflow_id="unsupported"
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            invocation_coverage_summary=replace(
                fixtures.invocation_coverage_summary(), workflow_id="unsupported"
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            loop_building_block_coverage_summary=replace(
                fixtures.loop_building_block_coverage_summary(),
                loop_id="unsupported",
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            evaluator_gate_review=replace(
                fixtures.evaluator_gate_review(), workflow_id="unsupported"
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            residual_edge_review=replace(
                fixtures.residual_edge_review(), workflow_id="unsupported"
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            cowork_task_suitability_review=replace(
                fixtures.cowork_task_suitability_review(),
                workflow_id="unsupported",
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            trajectory_learning_eligibility_review=replace(
                fixtures.trajectory_learning_eligibility_review(),
                workflow_id="unsupported",
            ),
        ),
        lambda: replace(
            _opportunity_reduction(),
            graph_dependency_integrity_review=replace(
                fixtures.graph_dependency_integrity_review(),
                workflow_id="unsupported",
            ),
        ),
        lambda: replace(_opportunity_reduction(), blockers=("HUMAN_REVIEW_REQUIRED",)),
        lambda: replace(
            wf.review_graph_architecture_readiness(_graph_readiness_evidence()),
            workflow_id="",
        ),
        lambda: replace(
            wf.review_graph_architecture_readiness(_graph_readiness_evidence()),
            blockers=("HUMAN_REVIEW_REQUIRED",),
        ),
        lambda: replace(base_graph_manifest_review(), workflow_id=""),
        lambda: replace(
            base_graph_manifest_review(),
            status=cast(wf.GraphWorkflowManifestReviewStatus, "INVALID"),
        ),
        lambda: replace(base_graph_manifest_review(), state_schema_hash="bad"),
        lambda: replace(
            base_graph_manifest_review(),
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(
            base_graph_manifest_review(),
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "HUMAN_REVIEW_REQUIRED"),
        ),
        lambda: replace(
            base_graph_manifest_review(),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(
            wf.admit_closed_loop(fixtures.closed_loop_evidence()), loop_id=""
        ),
        lambda: replace(
            wf.admit_closed_loop(fixtures.closed_loop_evidence()), max_iterations=0
        ),
        lambda: replace(
            wf.admit_closed_loop(fixtures.closed_loop_evidence()), max_cost_units=0
        ),
        lambda: replace(
            wf.admit_closed_loop(fixtures.closed_loop_evidence()),
            allowed_write_roots=("C:/outside",),
        ),
        lambda: replace(
            wf.admit_closed_loop(fixtures.closed_loop_evidence()),
            blockers=("HUMAN_REVIEW_REQUIRED",),
        ),
        lambda: replace(
            wf.summarize_closed_loop_run(fixtures.closed_loop_run_evidence()),
            run_id="",
        ),
        lambda: replace(
            wf.summarize_closed_loop_run(fixtures.closed_loop_run_evidence()),
            iteration_count=-1,
        ),
        lambda: replace(
            wf.review_loop_engineering_readiness(fixtures.loop_evidence()),
            loop_id="",
        ),
        lambda: replace(
            wf.review_loop_engineering_readiness(fixtures.loop_evidence()),
            blockers=("HUMAN_REVIEW_REQUIRED",),
        ),
    ],
)
def test_remaining_contract_guards_fail_closed(factory: InvalidFactory) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def base_graph_manifest_review() -> wf.GraphWorkflowManifestReview:
    return wf.review_graph_workflow_manifest(fixtures.graph_manifest())


@pytest.mark.parametrize(
    ("review", "expected_blocker"),
    [
        (
            lambda: fixtures.evaluator_gate_review(source_uri="artifact://source"),
            "EVALUATOR_GATE_SOURCE_HTTPS_REQUIRED",
        ),
        (
            lambda: fixtures.evaluator_gate_review(source_sha256=""),
            "EVALUATOR_GATE_SOURCE_HASH_REQUIRED",
        ),
        (
            lambda: fixtures.evaluator_gate_review(generator_model_family=""),
            "EVALUATOR_GATE_GENERATOR_FAMILY_REQUIRED",
        ),
        (
            lambda: fixtures.evaluator_gate_review(judge_model_family=""),
            "EVALUATOR_GATE_JUDGE_FAMILY_REQUIRED",
        ),
        (
            lambda: fixtures.evaluator_gate_review(rubric_hash=""),
            "EVALUATOR_GATE_RUBRIC_HASH_REQUIRED",
        ),
        (
            lambda: fixtures.evaluator_gate_review(rubric_text=""),
            "EVALUATOR_GATE_RUBRIC_TEXT_REQUIRED",
        ),
        (
            lambda: fixtures.residual_edge_review(source_uri="artifact://source"),
            "RESIDUAL_EDGE_SOURCE_HTTPS_REQUIRED",
        ),
        (
            lambda: fixtures.residual_edge_review(source_sha256=""),
            "RESIDUAL_EDGE_SOURCE_HASH_REQUIRED",
        ),
        (
            lambda: fixtures.cowork_task_suitability_review(
                source_uri="artifact://source"
            ),
            "COWORK_TASK_SOURCE_HTTPS_REQUIRED",
        ),
        (
            lambda: fixtures.cowork_task_suitability_review(source_sha256=""),
            "COWORK_TASK_SOURCE_HASH_REQUIRED",
        ),
        (
            lambda: fixtures.trajectory_learning_eligibility_review(
                source_uri="artifact://source"
            ),
            "TRAJECTORY_LEARNING_SOURCE_HTTPS_REQUIRED",
        ),
        (
            lambda: fixtures.trajectory_learning_eligibility_review(source_sha256=""),
            "TRAJECTORY_LEARNING_SOURCE_HASH_REQUIRED",
        ),
        (
            lambda: fixtures.trajectory_learning_eligibility_review(trajectory_hash=""),
            "TRAJECTORY_LEARNING_HASH_REQUIRED",
        ),
        (
            lambda: fixtures.graph_dependency_integrity_review(
                source_uri="artifact://source"
            ),
            "GRAPH_DEPENDENCY_SOURCE_HTTPS_REQUIRED",
        ),
        (
            lambda: fixtures.graph_dependency_integrity_review(source_sha256=""),
            "GRAPH_DEPENDENCY_SOURCE_HASH_REQUIRED",
        ),
    ],
)
def test_remaining_review_paths_preserve_live_block(
    review: Callable[[], ReviewResult], expected_blocker: str
) -> None:
    result = review()
    assert expected_blocker in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: fixtures.cowork_task_suitability_review(task_id=""),
        lambda: fixtures.trajectory_learning_eligibility_review(trajectory_id=""),
        lambda: fixtures.trajectory_learning_eligibility_review(
            privacy_classification=""
        ),
        lambda: fixtures.trajectory_learning_eligibility_review(tool_schema_version=""),
        lambda: fixtures.trajectory_learning_eligibility_review(
            retrieval_snapshot_id=""
        ),
        lambda: fixtures.trajectory_learning_eligibility_review(harness_fingerprint=""),
        lambda: fixtures.trajectory_learning_eligibility_review(model_id=""),
    ],
)
def test_required_review_identity_fields_reject_blanks(
    factory: InvalidFactory,
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_graph_trace_and_manifest_remaining_branches_are_deterministic() -> None:
    graph = wf.WorkflowGraph(
        "graph",
        (
            wf.WorkflowNode(
                "node",
                "NODE",
                (),
                (),
                ("node.json",),
                1,
                wf.WorkflowAuthority.READ_ONLY,
            ),
        ),
    )
    with pytest.raises(ValueError, match="identity"):
        wf.summarize_graph_run_trace(
            graph,
            run_id="",
            checkpoints=(),
            max_cost_units=1,
            max_retry_count=0,
        )
    with pytest.raises(ValueError, match="budgets"):
        wf.summarize_graph_run_trace(
            graph,
            run_id="run-1",
            checkpoints=(),
            max_cost_units=0,
            max_retry_count=0,
        )

    retry_trace = wf.summarize_graph_run_trace(
        graph,
        run_id="run-1",
        checkpoints=(fixtures.graph_checkpoint("node", retry_count=2),),
        max_cost_units=2,
        max_retry_count=1,
    )
    assert "GRAPH_RUN_RETRY_BUDGET_EXCEEDED" in retry_trace.blockers
    assert retry_trace.terminal_state is wf.GraphRunTerminalState.WATCHLIST

    research_trace = wf.summarize_graph_run_trace(
        graph,
        run_id="run-1",
        checkpoints=(
            fixtures.graph_checkpoint("node", reviewer_result="RESEARCH_ONLY"),
        ),
        max_cost_units=2,
        max_retry_count=1,
    )
    assert research_trace.terminal_state is wf.GraphRunTerminalState.RESEARCH_ONLY

    with pytest.raises(ValueError, match="identity"):
        wf.reduce_graph_node_route_decisions(
            graph,
            run_id="",
            decisions=(),
            max_cost_units=1,
            max_retry_count=1,
        )
    with pytest.raises(ValueError, match="budgets"):
        wf.reduce_graph_node_route_decisions(
            graph,
            run_id="run-1",
            decisions=(),
            max_cost_units=0,
            max_retry_count=1,
        )
    route = fixtures.route_decision(
        "node",
        graph_id="graph",
        decision=wf.GraphNodeRouteDecisionType.RETRY,
        target_node="node",
        retry_count=1,
    )
    route_reduction = wf.reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=(route,),
        max_cost_units=2,
        max_retry_count=1,
    )
    assert "GRAPH_ROUTE_RETRY_LIMIT_REACHED" in route_reduction.blockers

    with pytest.raises(ValueError, match="max parallelism"):
        wf.review_graph_workflow_manifest(
            fixtures.graph_manifest(), max_parallelism_cap=0
        )
    empty_review = wf.review_graph_workflow_manifest(
        replace(
            fixtures.graph_manifest(),
            nodes=(),
            edges=(),
            verifier_nodes=(),
            human_gate_nodes=(),
        )
    )
    assert "GRAPH_MANIFEST_NODE_REQUIRED" in empty_review.blockers

    cycle_review = wf.review_graph_workflow_manifest(
        replace(
            fixtures.graph_manifest(),
            edges=(
                ("market_outlook_branch", "setup_family_branch"),
                ("setup_family_branch", "market_outlook_branch"),
            ),
            human_gate_nodes=(),
        )
    )
    assert "GRAPH_MANIFEST_CYCLE_REVIEW_REQUIRED" in cycle_review.blockers
    assert "GRAPH_MANIFEST_CYCLE_HUMAN_GATE_REQUIRED" in cycle_review.blockers

    unknown_edge_review = wf.review_graph_workflow_manifest(
        replace(
            fixtures.graph_manifest(),
            edges=(("unknown", "market_outlook_branch"),),
        )
    )
    assert "GRAPH_MANIFEST_EDGE_NODE_UNKNOWN" in unknown_edge_review.blockers
    assert unknown_edge_review.execution_allowed is False


def test_graph_readiness_external_runtime_remains_review_only() -> None:
    review = wf.review_graph_architecture_readiness(
        replace(_graph_readiness_evidence(), external_runtime_used=True)
    )
    assert "GRAPH_EXTERNAL_RUNTIME_REVIEW_REQUIRED" in review.blockers
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_reducer_propagates_all_watchlist_surfaces() -> None:
    workspace = wf.review_agent_workspace_component(
        fixtures.workspace_component(citations=())
    )
    architecture = wf.AgentArchitectureCoverageSummary(
        workflow_id="opportunity-research-diamond",
        source_uri="artifact://architecture",
        source_sha256=fixtures.HASH,
        status=wf.AgentArchitectureLayerStatus.WATCHLIST,
        covered_layers=(wf.AgentArchitectureLayer.HARNESS,),
        missing_layers=(wf.AgentArchitectureLayer.LOOP,),
        missing_control_points=("loop:verifier",),
        blockers=(
            "AGENT_ARCHITECTURE_LAYER_MISSING",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    invocation = replace(
        fixtures.invocation_coverage_summary(),
        status=wf.AgentInvocationCoverageStatus.WATCHLIST,
        blockers=(
            "AGENT_INVOCATION_CONTEXT_REDACTION_REQUIRED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    loop_building = replace(
        fixtures.loop_building_block_coverage_summary(),
        status=wf.LoopBuildingBlockCoverageStatus.WATCHLIST,
        blockers=(
            "LOOP_BUILDING_BLOCK_HUMAN_HANDOFF_REQUIRED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    evaluator = replace(
        fixtures.evaluator_gate_review(),
        status=wf.EvaluatorGateStatus.WATCHLIST,
        blockers=(
            "EVALUATOR_GATE_SHADOW_MODE_REQUIRED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    residual = fixtures.residual_edge_review(expected_value_after_costs=0.0)
    cowork = replace(
        fixtures.cowork_task_suitability_review(),
        status=wf.CoworkTaskSuitabilityStatus.WATCHLIST,
        blockers=(
            "COWORK_TASK_HUMAN_APPROVAL_REQUIRED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    trajectory = replace(
        fixtures.trajectory_learning_eligibility_review(),
        status=wf.AgentTrajectoryLearningEligibilityStatus.WATCHLIST,
        blockers=(
            "MODEL_UPDATE_BLOCKED",
            "TRAJECTORY_LEARNING_REDACTION_REQUIRED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    dependency = replace(
        fixtures.graph_dependency_integrity_review(),
        status=wf.GraphDependencyIntegrityStatus.WATCHLIST,
        blockers=(
            "GRAPH_DEPENDENCY_FAKE_EDGE_DETECTED",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
    )
    reviews = tuple(
        fixtures.branch_review(branch) for branch in wf.OPPORTUNITY_RESEARCH_BRANCH_IDS
    )

    reduction = wf.reduce_opportunity_artifact_reviews(
        reviews,
        supporting_workspace_reviews=(workspace, workspace),
        expected_workspace_components=(workspace.component_id, "missing"),
        architecture_coverage_summary=architecture,
        invocation_coverage_summary=invocation,
        loop_building_block_coverage_summary=loop_building,
        evaluator_gate_review=evaluator,
        residual_edge_review=residual,
        cowork_task_suitability_review=cowork,
        trajectory_learning_eligibility_review=trajectory,
        graph_dependency_integrity_review=dependency,
    )

    expected = {
        "DUPLICATE_WORKSPACE_COMPONENT_REVIEW",
        "MISSING_WORKSPACE_COMPONENT_REVIEW",
        "WATCHLIST_WORKSPACE_COMPONENT_REVIEW",
        "WATCHLIST_AGENT_ARCHITECTURE_COVERAGE",
        "WATCHLIST_AGENT_INVOCATION_COVERAGE",
        "WATCHLIST_LOOP_BUILDING_BLOCK_COVERAGE",
        "WATCHLIST_EVALUATOR_GATE_REVIEW",
        "NO_TRADE_RESIDUAL_EDGE_REVIEW",
        "WATCHLIST_COWORK_TASK_SUITABILITY",
        "WATCHLIST_TRAJECTORY_LEARNING_ELIGIBILITY",
        "WATCHLIST_GRAPH_DEPENDENCY_INTEGRITY",
        "LIVE_ORDER_BLOCKED",
    }
    assert expected <= set(reduction.blockers)
    assert reduction.final_status is wf.OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_empty_opportunity_reducer_keeps_optional_evidence_and_live_blocked() -> None:
    result = wf.reduce_opportunity_artifact_reviews(
        (),
        architecture_coverage_summary=_architecture_summary(),
        invocation_coverage_summary=fixtures.invocation_coverage_summary(),
        loop_building_block_coverage_summary=(
            fixtures.loop_building_block_coverage_summary()
        ),
        evaluator_gate_review=fixtures.evaluator_gate_review(),
        residual_edge_review=fixtures.residual_edge_review(),
        cowork_task_suitability_review=fixtures.cowork_task_suitability_review(),
        trajectory_learning_eligibility_review=(
            fixtures.trajectory_learning_eligibility_review()
        ),
        graph_dependency_integrity_review=(
            fixtures.graph_dependency_integrity_review()
        ),
    )
    assert result.final_status is wf.OpportunityArtifactReductionStatus.WATCHLIST
    assert "MISSING_BRANCH_REVIEW_RESULT" in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.agents.evaluation import (
    AdvisoryEvalExpectation,
    AdvisoryEvalResult,
    AdvisoryTrace,
    evaluate_advisory_trace,
)
from ai4binance.governance.sidecar import (
    SidecarPilotAssessment,
    SidecarPilotEvidence,
    assess_sidecar_pilot,
)
from ai4binance.governance.workflow import (
    AGENT_ARCHITECTURE_LAYERS,
    OPPORTUNITY_RESEARCH_BRANCH_IDS,
    AgentArchitectureCoverageSummary,
    AgentArchitectureLayer,
    AgentArchitectureLayerEvidence,
    AgentArchitectureLayerReduction,
    AgentArchitectureLayerStatus,
    AgentInvocationCoverageStatus,
    AgentInvocationCoverageSummary,
    AgentLoopScale,
    AgentLoopType,
    AgentModelCandidateEvidence,
    AgentModelCandidateReview,
    AgentModelCandidateStatus,
    AgentSkillCandidateEvidence,
    AgentSkillCandidateReview,
    AgentSkillCandidateStatus,
    AgentTrajectoryLearningEligibilityReview,
    AgentTrajectoryLearningEligibilityStatus,
    AgentWorkspaceComponentEvidence,
    AgentWorkspaceComponentReview,
    AgentWorkspaceComponentStatus,
    AgentWorkspaceComponentType,
    ClosedLoopAdmission,
    ClosedLoopAdmissionEvidence,
    ClosedLoopAdmissionStatus,
    ClosedLoopRunEvidence,
    ClosedLoopRunSummary,
    ClosedLoopRunTriggerType,
    CoworkTaskSuitabilityReview,
    CoworkTaskSuitabilityStatus,
    EvaluatorGateBlastRadiusLane,
    EvaluatorGateReview,
    EvaluatorGateStatus,
    GraphArchitectureReadinessEvidence,
    GraphArchitectureReadinessReview,
    GraphArchitectureReadinessStatus,
    GraphDependencyIntegrityReview,
    GraphDependencyIntegrityStatus,
    GraphNodeRouteDecision,
    GraphNodeRouteDecisionType,
    GraphNodeRouteReduction,
    GraphRunNodeCheckpoint,
    GraphRunTerminalState,
    GraphRunTrace,
    GraphWorkflowManifestEvidence,
    GraphWorkflowManifestReview,
    GraphWorkflowManifestReviewStatus,
    LoopBuildingBlockCoverageStatus,
    LoopBuildingBlockCoverageSummary,
    LoopEngineeringReadinessEvidence,
    LoopEngineeringReadinessReview,
    LoopEngineeringReadinessStatus,
    MarkdownGovernanceArtifactEvidence,
    MarkdownGovernanceArtifactReview,
    MarkdownGovernanceArtifactRole,
    MarkdownGovernanceReviewerResult,
    MarkdownGovernanceReviewReduction,
    MarkdownGovernanceReviewStatus,
    OpportunityArtifactReductionStatus,
    OpportunityArtifactReviewReduction,
    OpportunityArtifactReviewResult,
    OpportunityArtifactReviewStatus,
    ResidualEdgeReview,
    ResidualEdgeReviewStatus,
    WorkflowAuthority,
    WorkflowEdgeAudit,
    WorkflowEdgeAuditStatus,
    WorkflowGraph,
    WorkflowNode,
    WorkflowPreview,
    WorkflowPreviewStatus,
    admit_closed_loop,
    audit_workflow_edges,
    market_outlook_workflow,
    opportunity_research_diamond_workflow,
    preview_workflow,
    reduce_agent_architecture_layer_reviews,
    reduce_graph_node_route_decisions,
    reduce_markdown_governance_reviews,
    reduce_opportunity_artifact_reviews,
    review_agent_model_candidate,
    review_agent_skill_candidate,
    review_agent_trajectory_learning_eligibility,
    review_agent_workspace_component,
    review_cowork_task_suitability,
    review_evaluator_gate,
    review_graph_architecture_readiness,
    review_graph_dependency_integrity,
    review_graph_workflow_manifest,
    review_loop_engineering_readiness,
    review_markdown_governance_artifact,
    review_residual_edge,
    summarize_agent_architecture_coverage,
    summarize_agent_invocation_coverage,
    summarize_closed_loop_run,
    summarize_graph_run_trace,
    summarize_loop_building_block_coverage,
)
from ai4binance.learning.governance import (
    GovernedLesson,
    LessonStatus,
    stage_learning_summary,
)
from ai4binance.learning.models import LearningSummary, LessonCandidate
from ai4binance.ops.jobs import (
    JobAdmission,
    JobCapability,
    JobManifest,
    JobRequest,
    assess_job_admission,
    nightly_quality_job_manifest,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)
HASH = "a" * 64


def model_candidate(
    *,
    model_id: str = "kimi-k3",
    provider: str = "moonshot-ai",
    context_window_tokens: int = 1_048_576,
    input_price_per_1m: float = 3.0,
    cached_input_price_per_1m: float = 0.3,
    output_price_per_1m: float = 15.0,
    tool_call_support: bool = True,
    json_mode_support: bool = True,
    data_privacy_boundary: str = "external_api_research_only_no_secrets",
    citations: tuple[str, ...] = (
        "https://www.kimi.com/resources/kimi-k3-pricing",
        "https://huggingface.co/moonshotai/Kimi-K3",
    ),
    blockers: tuple[str, ...] = (),
    external_runtime_used: bool = False,
    credential_required: bool = False,
) -> AgentModelCandidateEvidence:
    return AgentModelCandidateEvidence(
        model_id=model_id,
        provider=provider,
        context_window_tokens=context_window_tokens,
        input_price_per_1m=input_price_per_1m,
        cached_input_price_per_1m=cached_input_price_per_1m,
        output_price_per_1m=output_price_per_1m,
        tool_call_support=tool_call_support,
        json_mode_support=json_mode_support,
        data_privacy_boundary=data_privacy_boundary,
        citations=citations,
        blockers=blockers,
        external_runtime_used=external_runtime_used,
        credential_required=credential_required,
    )


def skill_candidate(
    *,
    skill_id: str = "agent-skill-authoring",
    source_uri: str = "https://x.com/free_ai_guides/status/2071666929451094227",
    source_sha256: str = HASH,
    declared_goal: str = "Turn cited agent-skill guidance into a reusable workflow.",
    trigger_conditions: tuple[str, ...] = (
        "external agent skill guidance is proposed",
        "workflow reuse is requested",
    ),
    allowed_inputs: tuple[str, ...] = (
        "source uri",
        "source hash",
        "human approval",
    ),
    required_references: tuple[str, ...] = (
        ".agents/skills/ai4binance-validation-first/SKILL.md",
    ),
    declared_tools: tuple[str, ...] = (),
    script_paths: tuple[str, ...] = (),
    expected_output_contract: tuple[str, ...] = (
        "RESEARCH_ONLY_SKILL",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    ),
    review_checklist: tuple[str, ...] = (
        "citation present",
        "no credential access",
        "no trading authority",
    ),
    test_command: str = (
        ".\\.venv\\Scripts\\python.exe -m pytest "
        "tests\\test_agent_runtime_governance.py --no-cov -q"
    ),
    citations: tuple[str, ...] = (
        "https://x.com/free_ai_guides/status/2071666929451094227",
    ),
    blockers: tuple[str, ...] = (),
    reviewer_result: str = "PASSED",
    self_generated: bool = False,
    network_access_required: bool = False,
    credential_access_required: bool = False,
    trading_scope_touched: bool = False,
) -> AgentSkillCandidateEvidence:
    return AgentSkillCandidateEvidence(
        skill_id=skill_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        declared_goal=declared_goal,
        trigger_conditions=trigger_conditions,
        allowed_inputs=allowed_inputs,
        required_references=required_references,
        declared_tools=declared_tools,
        script_paths=script_paths,
        expected_output_contract=expected_output_contract,
        review_checklist=review_checklist,
        test_command=test_command,
        citations=citations,
        blockers=blockers,
        reviewer_result=reviewer_result,
        self_generated=self_generated,
        network_access_required=network_access_required,
        credential_access_required=credential_access_required,
        trading_scope_touched=trading_scope_touched,
    )


def workspace_component(
    *,
    component_id: str = "ai4binance-validation-first",
    component_type: AgentWorkspaceComponentType = AgentWorkspaceComponentType.SKILL,
    source_path: str = ".agents/skills/ai4binance-validation-first/SKILL.md",
    content_sha256: str = HASH,
    citations: tuple[str, ...] = (
        "artifact://.agents/skills/ai4binance-validation-first/SKILL.md",
    ),
    declared_authority: str = "RESEARCH_ONLY",
    canary_command: str = (
        ".\\.venv\\Scripts\\python.exe -m pytest "
        "tests\\test_agent_runtime_governance.py --no-cov -q"
    ),
    canary_expected_blockers: tuple[str, ...] = (
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    ),
    blockers: tuple[str, ...] = (),
    external_runtime_used: bool = False,
    credential_required: bool = False,
    writes_enabled: bool = False,
    trading_scope_touched: bool = False,
) -> AgentWorkspaceComponentEvidence:
    return AgentWorkspaceComponentEvidence(
        component_id=component_id,
        component_type=component_type,
        source_path=source_path,
        content_sha256=content_sha256,
        citations=citations,
        declared_authority=declared_authority,
        canary_command=canary_command,
        canary_expected_blockers=canary_expected_blockers,
        blockers=blockers,
        external_runtime_used=external_runtime_used,
        credential_required=credential_required,
        writes_enabled=writes_enabled,
        trading_scope_touched=trading_scope_touched,
    )


def markdown_governance_artifact(
    *,
    artifact_id: str = "architecture-md",
    source_path: str = "Docs/ARCHITECTURE.md",
    role: MarkdownGovernanceArtifactRole = MarkdownGovernanceArtifactRole.ARCHITECTURE,
    reviewer_result: MarkdownGovernanceReviewerResult = (
        MarkdownGovernanceReviewerResult.PASSED
    ),
    declared_authority: str = "RESEARCH_ONLY",
    citations: tuple[str, ...] = ("artifact://Docs/ARCHITECTURE.md",),
    owner: str = "architecture-reviewer",
    freshness_policy: str = "Re-review after workflow or live-gate changes.",
    canonical_source_path: str = "",
    blockers: tuple[str, ...] = (),
    contains_private_context: bool = False,
    external_runtime_used: bool = False,
    credential_required: bool = False,
) -> MarkdownGovernanceArtifactEvidence:
    return MarkdownGovernanceArtifactEvidence(
        artifact_id=artifact_id,
        source_path=source_path,
        content_sha256=HASH,
        role=role,
        reviewer_result=reviewer_result,
        declared_authority=declared_authority,
        citations=citations,
        owner=owner,
        freshness_policy=freshness_policy,
        canonical_source_path=canonical_source_path,
        blockers=blockers,
        contains_private_context=contains_private_context,
        external_runtime_used=external_runtime_used,
        credential_required=credential_required,
    )


def graph_manifest(
    *,
    state_schema_hash: str = HASH,
    verifier_nodes: tuple[str, ...] = ("fresh_skeptic_verify",),
    human_gate_nodes: tuple[str, ...] = ("human_review_gate",),
    authority_flags: tuple[str, ...] = ("READ_ONLY", "RESEARCH_ONLY"),
    parallelism_cap: int = 5,
    cycles_allowed: bool = False,
    edges: tuple[tuple[str, str], ...] = (
        ("market_outlook_branch", "fresh_skeptic_verify"),
        ("setup_family_branch", "fresh_skeptic_verify"),
        ("backtest_oos_branch", "fresh_skeptic_verify"),
        ("fresh_skeptic_verify", "opportunity_reduce"),
        ("opportunity_reduce", "human_review_gate"),
    ),
    expected_artifacts: tuple[str, ...] = (
        "Artifacts/opportunity-diamond/reducer-inputs.sha256",
        "Logs/opportunity-diamond-trace.jsonl",
    ),
) -> GraphWorkflowManifestEvidence:
    return GraphWorkflowManifestEvidence(
        workflow_id="opportunity-diamond-v1",
        selected_pattern="parallelization+evaluator-optimizer+human-in-the-loop",
        nodes=(
            "market_outlook_branch",
            "setup_family_branch",
            "backtest_oos_branch",
            "fresh_skeptic_verify",
            "opportunity_reduce",
            "human_review_gate",
        ),
        edges=edges,
        cycles_allowed=cycles_allowed,
        parallelism_cap=parallelism_cap,
        expected_artifacts=expected_artifacts,
        verifier_nodes=verifier_nodes,
        human_gate_nodes=human_gate_nodes,
        state_schema_hash=state_schema_hash,
        authority_flags=authority_flags,
    )


def branch_review(
    branch_id: str,
    *,
    reviewer_result: OpportunityArtifactReviewStatus = (
        OpportunityArtifactReviewStatus.PASSED
    ),
    blockers: tuple[str, ...] = (),
    digest: str = HASH,
) -> OpportunityArtifactReviewResult:
    return OpportunityArtifactReviewResult(
        branch_id=branch_id,
        artifact_uri=f"Artifacts/opportunity-diamond/{branch_id}.json",
        content_sha256=digest,
        citations=(f"artifact://{branch_id}",),
        blockers=blockers,
        reviewer_result=reviewer_result,
    )


def loop_evidence() -> LoopEngineeringReadinessEvidence:
    return LoopEngineeringReadinessEvidence(
        loop_id="opportunity-loop-v1",
        task="Improve opportunity report quality from verified artifacts",
        selected_pattern="evaluator-optimizer+human-in-the-loop",
        objective_metric="artifact_review_pass_rate",
        deterministic_verifier=True,
        max_iterations=5,
        max_cost_units=25,
        rollback_or_no_write=True,
        artifact_log_uri="Artifacts/loops/opportunity-loop-v1.jsonl",
        holdout_artifact_uri="Backtest/holdout/HOTUSDT/holdout-report.json",
        oos_artifact_uri="Backtest/oos/HOTUSDT/walk-forward-report.json",
        human_gate=True,
        stop_conditions=("max_iterations_reached", "quality_gate_passed_or_failed"),
        before_after_metrics=("pytest_pass_count", "coverage_percent"),
    )


def closed_loop_evidence() -> ClosedLoopAdmissionEvidence:
    return ClosedLoopAdmissionEvidence(
        loop_id="research-quality-loop-v1",
        task="Review one generated research artifact against deterministic checks",
        trigger="manual_codex_request",
        selected_pattern="evaluator-optimizer+human-in-the-loop",
        loop_type=AgentLoopType.CLOSED,
        loop_scale=AgentLoopScale.SINGLE_AGENT,
        allowed_tools=("pytest", "ruff"),
        allowed_write_roots=(),
        memory_sources=(".agents/skills/ai4binance-validation-first/SKILL.md",),
        verifier_identity="deterministic-quality-gate",
        artifact_log_uri="Artifacts/loops/research-quality-loop-v1.jsonl",
        stop_conditions=("max_iterations_reached", "quality_gate_passed_or_failed"),
        max_iterations=3,
        max_cost_units=20,
        human_handoff=True,
    )


def loop_building_block_coverage_summary(
    *,
    loop_id: str = "research-quality-loop-v1",
    automation_trigger: str = "manual_codex_request",
    worktree_isolation: bool = False,
    skills_declared: tuple[str, ...] = (
        ".agents/skills/ai4binance-validation-first/SKILL.md",
    ),
    connectors_declared: tuple[str, ...] = (),
    subagent_roles: tuple[str, ...] = ("maker", "checker"),
    memory_sources: tuple[str, ...] = (
        ".agents/skills/ai4binance-validation-first/SKILL.md",
    ),
    cost_budget: int = 20,
    stop_conditions: tuple[str, ...] = (
        "max_iterations_reached",
        "quality_gate_passed_or_failed",
    ),
    human_handoff: bool = True,
    parallel_edits: bool = False,
    connector_credentials_required: bool = False,
    memory_private_context_detected: bool = False,
    trading_scope_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> LoopBuildingBlockCoverageSummary:
    return summarize_loop_building_block_coverage(
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
        parallel_edits=parallel_edits,
        connector_credentials_required=connector_credentials_required,
        memory_private_context_detected=memory_private_context_detected,
        trading_scope_touched=trading_scope_touched,
        blockers=blockers,
    )


def evaluator_gate_review(
    *,
    workflow_id: str = "opportunity-research-diamond",
    source_uri: str = "https://x.com/hanakoxbt/status/2083540339147567268",
    source_sha256: str = HASH,
    generator_model_family: str = "claude",
    judge_model_family: str = "gpt",
    judge_version: str = "gpt-5.2-2026-08-01",
    rubric_hash: str = HASH,
    rubric_text: str = "Pass if the independently observable outcome happened.",
    deterministic_checks: tuple[str, ...] = ("ruff", "pytest"),
    trajectory_checks: tuple[str, ...] = ("tool_trace_grounded",),
    faithfulness_result: str = "PASSED",
    task_completion_result: str = "PASSED",
    verifier_canary_passed: bool = True,
    blast_radius_lane: EvaluatorGateBlastRadiusLane = (
        EvaluatorGateBlastRadiusLane.REVERSIBLE_CONTAINED
    ),
    human_disagreement_rate: float = 0.0,
    agent_self_assessment_weight: float = 0.0,
    shadow_mode: bool = True,
    trading_scope_touched: bool = False,
    production_data_touched: bool = False,
    money_movement_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> EvaluatorGateReview:
    return review_evaluator_gate(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
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
        trading_scope_touched=trading_scope_touched,
        production_data_touched=production_data_touched,
        money_movement_touched=money_movement_touched,
        blockers=blockers,
    )


def residual_edge_review(
    *,
    workflow_id: str = "opportunity-research-diamond",
    source_uri: str = "https://x.com/0xkvro/status/2074815948062650819",
    source_sha256: str = HASH,
    raw_return: float = 0.018,
    market_component: float = 0.010,
    sector_or_universe_component: float = 0.002,
    factor_component: float = 0.001,
    liquidity_component: float = 0.001,
    residual_return: float = 0.004,
    residual_zscore: float = 1.8,
    expected_value_after_costs: float = 0.0012,
    sample_size: int = 240,
    independent_repetition_count: int = 45,
    fees_bps: float = 7.5,
    slippage_bps: float = 4.0,
    capacity_warning: bool = False,
    regime_split: tuple[str, ...] = ("trend", "range"),
    signal_decay_check: str = "PASSED",
    data_leakage_check: str = "PASSED",
    sizing_status: str = "VALIDATED",
    oos_validation_present: bool = True,
    trading_scope_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> ResidualEdgeReview:
    return review_residual_edge(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
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
        trading_scope_touched=trading_scope_touched,
        blockers=blockers,
    )


def cowork_task_suitability_review(
    *,
    workflow_id: str = "opportunity-research-diamond",
    source_uri: str = "https://x.com/ridark_eth/status/2072666887276618071",
    source_sha256: str = HASH,
    task_id: str = "daily-research-digest",
    touches_files_apps_or_web: bool = True,
    tedious_repetitive_or_multistep: bool = True,
    done_is_checkable: bool = True,
    mistake_is_survivable: bool = True,
    brain_file_present: bool = True,
    skill_declared: bool = True,
    connector_scope: tuple[str, ...] = ("repo_artifacts_readonly",),
    schedule_requested: bool = True,
    manual_run_verified: bool = True,
    draft_only: bool = True,
    human_approval_required: bool = True,
    judgment_required: bool = False,
    secret_access_requested: bool = False,
    trading_scope_touched: bool = False,
    money_movement_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> CoworkTaskSuitabilityReview:
    return review_cowork_task_suitability(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
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
        blockers=blockers,
    )


def trajectory_learning_eligibility_review(
    *,
    workflow_id: str = "opportunity-research-diamond",
    source_uri: str = "https://arxiv.org/abs/2607.01120v2",
    source_sha256: str = HASH,
    trajectory_id: str = "research-trace-001",
    trajectory_hash: str = HASH,
    replay_class: str = "DETERMINISTIC_REPLAY",
    privacy_classification: str = "INTERNAL_REDACTED",
    redaction_status: str = "REDACTED",
    reward_signal: str = "HUMAN_CORRECTION_ACCEPTED",
    intervention_candidate: str = "MEMORY_CANDIDATE",
    tool_schema_version: str = "tool-schema-v1",
    retrieval_snapshot_id: str = "retrieval-snapshot-001",
    harness_fingerprint: str = "harness-v1",
    model_id: str = "advisory-local",
    causal_step_count: int = 4,
    delayed_reward_supported: bool = True,
    provenance_versioned: bool = True,
    governance_metadata_present: bool = True,
    human_correction_present: bool = True,
    training_eligible: bool = True,
    secret_risk_detected: bool = False,
    trading_scope_touched: bool = False,
    money_movement_touched: bool = False,
    model_weight_update_requested: bool = False,
    blockers: tuple[str, ...] = (),
) -> AgentTrajectoryLearningEligibilityReview:
    return review_agent_trajectory_learning_eligibility(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
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
        blockers=blockers,
    )


def graph_dependency_integrity_review(
    *,
    workflow_id: str = "opportunity-research-diamond",
    source_uri: str = "https://x.com/rvaniaaaa/status/2083577068374085960",
    source_sha256: str = HASH,
    graph_id: str = "opportunity-research-diamond-v1",
    expected_nodes: tuple[str, ...] = (
        "plan",
        "market",
        "risk",
        "verifier",
        "reducer",
        "synthesizer",
    ),
    observed_nodes: tuple[str, ...] = (
        "plan",
        "market",
        "risk",
        "verifier",
        "reducer",
        "synthesizer",
    ),
    declared_edges: tuple[str, ...] = (
        "plan->market",
        "plan->risk",
        "market->verifier",
        "risk->verifier",
        "verifier->reducer",
        "reducer->synthesizer",
    ),
    data_carrying_edges: tuple[str, ...] = (
        "plan->market",
        "plan->risk",
        "market->verifier",
        "risk->verifier",
        "verifier->reducer",
        "reducer->synthesizer",
    ),
    fake_edges: tuple[str, ...] = (),
    fanout_width: int = 2,
    barrier_count: int = 1,
    verifier_context_isolated: bool = True,
    anchor_artifacts: tuple[str, ...] = ("quality-gate:passed",),
    merge_input_count_verified: bool = True,
    model_tiering_policy_present: bool = True,
    cost_cap_present: bool = True,
    silent_node_failure_count: int = 0,
    trading_scope_touched: bool = False,
    money_movement_touched: bool = False,
    blockers: tuple[str, ...] = (),
) -> GraphDependencyIntegrityReview:
    return review_graph_dependency_integrity(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        graph_id=graph_id,
        expected_nodes=expected_nodes,
        observed_nodes=observed_nodes,
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
        blockers=blockers,
    )


def closed_loop_run_evidence(
    *,
    admission: ClosedLoopAdmission | None = None,
    trigger_type: ClosedLoopRunTriggerType = ClosedLoopRunTriggerType.GOAL,
    iteration_count: int = 2,
    cost_units: int = 8,
    state_read_before_frame: bool = True,
    verification_passed: bool = True,
    state_written_after_verification: bool = True,
    stop_condition_met: bool = True,
    blockers: tuple[str, ...] = (),
    model_claimed_completion: bool = False,
) -> ClosedLoopRunEvidence:
    return ClosedLoopRunEvidence(
        admission=admission or admit_closed_loop(closed_loop_evidence()),
        run_id="loop-run-1",
        trigger_type=trigger_type,
        state_uri="Artifacts/loops/research-quality-loop-v1.state.json",
        resume_point="queue:next-artifact",
        verifier_identity="deterministic-quality-gate",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=5),
        iteration_count=iteration_count,
        cost_units=cost_units,
        state_read_before_frame=state_read_before_frame,
        verification_passed=verification_passed,
        state_written_after_verification=state_written_after_verification,
        stop_condition_met=stop_condition_met,
        blockers=blockers,
        model_claimed_completion=model_claimed_completion,
    )


def graph_checkpoint(
    node_id: str,
    *,
    run_id: str = "run-1",
    offset_seconds: int = 0,
    reviewer_result: str = "PASSED",
    retry_count: int = 0,
    cost_units: int = 1,
    blockers: tuple[str, ...] = (),
) -> GraphRunNodeCheckpoint:
    return GraphRunNodeCheckpoint(
        run_id=run_id,
        node_id=node_id,
        input_artifact_sha256=HASH,
        output_artifact_sha256=HASH,
        started_at=NOW + timedelta(seconds=offset_seconds),
        finished_at=NOW + timedelta(seconds=offset_seconds + 1),
        reviewer_result=reviewer_result,
        retry_count=retry_count,
        cost_units=cost_units,
        blockers=blockers,
    )


def route_decision(
    node_id: str,
    *,
    run_id: str = "run-1",
    graph_id: str = "opportunity-research-diamond",
    decision: GraphNodeRouteDecisionType = GraphNodeRouteDecisionType.PASSED,
    reason: str = "Node output met its deterministic route contract.",
    target_node: str = "",
    citations: tuple[str, ...] = ("artifact://route-evidence",),
    blockers: tuple[str, ...] = (),
    retry_count: int = 0,
    cost_units: int = 1,
    reviewer_result: str = "PASSED",
) -> GraphNodeRouteDecision:
    return GraphNodeRouteDecision(
        run_id=run_id,
        graph_id=graph_id,
        node_id=node_id,
        decision=decision,
        reason=reason,
        target_node=target_node,
        input_artifact_sha256=HASH,
        output_artifact_sha256=HASH,
        citations=citations,
        blockers=blockers,
        retry_count=retry_count,
        cost_units=cost_units,
        reviewer_result=reviewer_result,
    )


def architecture_layer_evidence(
    layer: AgentArchitectureLayer,
    *,
    workflow_id: str = "opportunity-research-diamond",
    artifact_uri: str = "artifact://architecture-layer-review",
    citations: tuple[str, ...] = ("artifact://architecture-layer-review",),
    control_points: tuple[str, ...] | None = None,
    reviewer_result: str = "PASSED",
    blockers: tuple[str, ...] = (),
) -> AgentArchitectureLayerEvidence:
    defaults = {
        AgentArchitectureLayer.HARNESS: ("permissions", "sandbox", "audit"),
        AgentArchitectureLayer.LOOP: ("stop_condition", "verifier", "budget"),
        AgentArchitectureLayer.GRAPH: ("topology", "reducer", "route_state"),
    }
    return AgentArchitectureLayerEvidence(
        workflow_id=workflow_id,
        layer=layer,
        artifact_uri=f"{artifact_uri}/{layer.value.casefold()}",
        artifact_sha256=HASH,
        citations=citations,
        control_points=control_points
        if control_points is not None
        else defaults[layer],
        reviewer_result=reviewer_result,
        blockers=blockers,
    )


def invocation_coverage_summary(
    *,
    workflow_id: str = "opportunity-research-diamond",
    source_uri: str = "https://x.com/akshay_pachaar/status/2081089131808243999",
    source_sha256: str = HASH,
    prompt_revision: str = "agent-stack-v1",
    prompt_sha256: str = HASH,
    context_sources: tuple[str, ...] = (
        "https://x.com/akshay_pachaar/status/2081089131808243999",
        "artifact://HOF74j8boAAI44E.jpg",
    ),
    context_sha256: str = HASH,
    context_freshness_policy: str = (
        "Re-review when prompt, context, or source changes."
    ),
    citations: tuple[str, ...] = (
        "https://x.com/akshay_pachaar/status/2081089131808243999",
    ),
    redaction_applied: bool = True,
    private_context_detected: bool = False,
    tool_output_verified: bool = True,
    blockers: tuple[str, ...] = (),
) -> AgentInvocationCoverageSummary:
    return summarize_agent_invocation_coverage(
        workflow_id=workflow_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        prompt_revision=prompt_revision,
        prompt_sha256=prompt_sha256,
        context_sources=context_sources,
        context_sha256=context_sha256,
        context_freshness_policy=context_freshness_policy,
        citations=citations,
        redaction_applied=redaction_applied,
        private_context_detected=private_context_detected,
        tool_output_verified=tool_output_verified,
        blockers=blockers,
    )


def lesson() -> GovernedLesson:
    return GovernedLesson.from_candidate(
        LessonCandidate("WEAK_OOS", 3, "Repeated weak OOS evidence"),
        lesson_id="lesson-1",
        source_artifact_id="learning-summary-1",
        observed_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )


def test_lesson_lifecycle_requires_validation_human_approval_and_expiry() -> None:
    item = lesson()
    for status in (
        LessonStatus.DEDUPLICATED,
        LessonStatus.CONTRADICTION_CHECKED,
        LessonStatus.VALIDATION_PENDING,
    ):
        item = item.transition(status, at=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="validation artifacts"):
        item.transition(LessonStatus.RESEARCH_ONLY, at=NOW + timedelta(minutes=2))
    item = item.transition(
        LessonStatus.RESEARCH_ONLY,
        at=NOW + timedelta(minutes=2),
        validation_artifact_ids=("oos-report-1",),
    )
    with pytest.raises(ValueError, match="human approval"):
        item.transition(LessonStatus.HUMAN_APPROVED, at=NOW + timedelta(minutes=3))
    item = item.transition(
        LessonStatus.HUMAN_APPROVED,
        at=NOW + timedelta(minutes=3),
        human_approved=True,
    )
    item = item.transition(LessonStatus.ACTIVE_LESSON, at=NOW + timedelta(minutes=4))
    assert item.execution_allowed is False
    assert item.risk_change_allowed is False
    assert item.parameter_change_allowed is False
    expired = item.transition(LessonStatus.EXPIRED, at=NOW + timedelta(days=31))
    assert expired.status is LessonStatus.EXPIRED


def test_lesson_blocks_skipped_and_expired_approval() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        lesson().transition(LessonStatus.RESEARCH_ONLY, at=NOW)
    item = lesson()
    for status in (
        LessonStatus.DEDUPLICATED,
        LessonStatus.CONTRADICTION_CHECKED,
        LessonStatus.VALIDATION_PENDING,
        LessonStatus.RESEARCH_ONLY,
    ):
        item = item.transition(
            status,
            at=NOW + timedelta(minutes=1),
            validation_artifact_ids=("oos-report",),
        )
    with pytest.raises(ValueError, match="expired"):
        item.transition(
            LessonStatus.HUMAN_APPROVED,
            at=NOW + timedelta(days=31),
            human_approved=True,
        )


def job_manifest(root: Path) -> JobManifest:
    return JobManifest(
        job_id="nightly-quality",
        allowed_capabilities=(
            JobCapability.READ_REPOSITORY,
            JobCapability.WRITE_ARTIFACT,
            JobCapability.RUN_FIXED_QUALITY_COMMANDS,
        ),
        allowed_roots=(root,),
        timeout_seconds=600,
        maximum_output_bytes=100_000,
        maximum_concurrency=1,
        lock_path=root / ".nightly.lock",
    )


def test_job_admission_requires_capability_path_timeout_and_lock(
    tmp_path: Path,
) -> None:
    request = JobRequest(
        job_id="nightly-quality",
        idempotency_key="2026-07-13",
        requested_capabilities=(JobCapability.READ_REPOSITORY,),
        target_paths=(tmp_path / "repo",),
        timeout_enforced_by_runner=True,
        lock_acquired=True,
    )
    result = assess_job_admission(job_manifest(tmp_path), request)
    assert result.admitted is True
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    blocked = assess_job_admission(
        job_manifest(tmp_path),
        replace(
            request,
            job_id="other",
            target_paths=(tmp_path.parent / "outside",),
            network_requested=True,
            timeout_enforced_by_runner=False,
            lock_acquired=False,
        ),
    )
    assert blocked.blockers == (
        "JOB_IDENTITY_MISMATCH",
        "JOB_PATH_NOT_ALLOWED",
        "JOB_NETWORK_NOT_ALLOWED",
        "JOB_TIMEOUT_NOT_ENFORCED",
        "JOB_LOCK_NOT_ACQUIRED",
    )


def advisory_trace(
    *,
    fixture_id: str = "fixture-1",
    citations: tuple[str, ...] = ("artifact-1",),
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",),
    duration_ms: int = 50,
) -> AdvisoryTrace:
    return AdvisoryTrace(
        trace_id="trace-1",
        fixture_id=fixture_id,
        model_id="advisory-model",
        prompt_revision="prompt-v1",
        input_sha256=HASH,
        output_sha256=HASH,
        citations=citations,
        blockers=blockers,
        started_at=NOW,
        finished_at=NOW + timedelta(milliseconds=duration_ms),
    )


def test_advisory_eval_is_deterministic_and_never_promotion_evidence() -> None:
    expectation = AdvisoryEvalExpectation(
        fixture_id="fixture-1",
        required_citations=("artifact-1",),
        required_blockers=("LIVE_ORDER_BLOCKED",),
        maximum_duration_ms=100,
    )
    passed = evaluate_advisory_trace(advisory_trace(), expectation)
    assert passed.passed is True
    assert passed.grader == "DETERMINISTIC_RULES"
    assert passed.promotion_evidence is False
    assert passed.execution_allowed is False

    failed = evaluate_advisory_trace(
        advisory_trace(
            fixture_id="other",
            citations=(),
            blockers=(),
            duration_ms=101,
        ),
        expectation,
    )
    assert failed.blockers == (
        "ADVISORY_FIXTURE_MISMATCH",
        "ADVISORY_REQUIRED_CITATION_MISSING",
        "ADVISORY_REQUIRED_BLOCKER_MISSING",
        "ADVISORY_LATENCY_BUDGET_EXCEEDED",
    )


def test_market_outlook_graph_is_deterministic_read_only_dag() -> None:
    graph = market_outlook_workflow()
    assert graph.topological_order() == (
        "market_data",
        "market_outlook",
        "setup_radar",
        "candidate_arbitration",
        "risk_evaluation",
        "paper_proposal",
        "closure_review",
    )
    assert graph.execution_allowed is False
    assert graph.nodes[-2].authority is WorkflowAuthority.PAPER_PROPOSAL
    preview = preview_workflow(
        graph,
        validation_points=("risk_evaluation", "paper_proposal", "closure_review"),
    )
    assert preview.status == "HUMAN_REVIEW_REQUIRED"
    assert preview.execution_allowed is False
    assert preview.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "LIVE_ORDER_BLOCKED" in preview.blockers


def test_opportunity_research_diamond_fans_out_verifies_and_stays_blocked() -> None:
    graph = opportunity_research_diamond_workflow()
    order = graph.topological_order()
    branches = {
        "market_outlook_branch",
        "setup_family_branch",
        "backtest_oos_branch",
        "portfolio_context_branch",
        "whale_fusion_branch",
    }
    reduce_node = next(
        node for node in graph.nodes if node.node_id == "opportunity_reduce"
    )
    verifier_node = next(
        node for node in graph.nodes if node.node_id == "fresh_skeptic_verify"
    )
    gate_node = graph.nodes[-1]

    assert graph.graph_id == "opportunity-research-diamond"
    assert graph.execution_allowed is False
    assert order[0] == "opportunity_inputs"
    assert set(order[1:6]) == branches
    assert set(reduce_node.dependencies) == branches
    assert reduce_node.authority is WorkflowAuthority.READ_ONLY
    assert "FAN_IN_COUNT_REQUIRED" in reduce_node.blockers
    assert verifier_node.dependencies == ("opportunity_reduce",)
    assert "FRESH_CONTEXT_VERIFIER_REQUIRED" in verifier_node.blockers
    assert gate_node.node_id == "human_review_gate"
    assert gate_node.authority is WorkflowAuthority.READ_ONLY
    assert gate_node.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")

    preview = preview_workflow(
        graph,
        validation_points=(
            "opportunity_reduce",
            "fresh_skeptic_verify",
            "human_review_gate",
        ),
    )

    assert preview.status == "HUMAN_REVIEW_REQUIRED"
    assert preview.execution_allowed is False
    assert preview.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_workflow_edge_audit_verifies_diamond_artifact_handoffs() -> None:
    audit = audit_workflow_edges(opportunity_research_diamond_workflow())

    assert audit.status is WorkflowEdgeAuditStatus.REAL_EDGES_VERIFIED
    assert audit.fake_edges == ()
    assert len(audit.real_edges) == 13
    assert "opportunity_inputs->market_outlook_branch" in audit.real_edges
    assert "backtest_oos_branch->opportunity_reduce" in audit.real_edges
    assert audit.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert audit.execution_allowed is False
    assert audit.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_workflow_edge_audit_watchlists_fake_edges_without_artifact_handoff() -> None:
    audit = audit_workflow_edges(market_outlook_workflow())

    assert audit.status is WorkflowEdgeAuditStatus.WATCHLIST
    assert "market_data->market_outlook" in audit.fake_edges
    assert "candidate_arbitration->risk_evaluation" in audit.fake_edges
    assert "WORKFLOW_FAKE_EDGE_DETECTED" in audit.blockers
    assert "LIVE_ORDER_BLOCKED" in audit.blockers
    assert audit.execution_allowed is False


def test_graph_run_trace_summarizes_complete_diamond_checkpoints() -> None:
    graph = opportunity_research_diamond_workflow()
    checkpoints = tuple(
        graph_checkpoint(node.node_id, offset_seconds=index)
        for index, node in enumerate(reversed(graph.nodes))
    )

    trace = summarize_graph_run_trace(
        graph,
        run_id="run-1",
        checkpoints=checkpoints,
        max_cost_units=20,
        max_retry_count=1,
    )

    assert trace.terminal_state is GraphRunTerminalState.COMPLETED
    assert tuple(checkpoint.node_id for checkpoint in trace.checkpoints) == (
        graph.topological_order()
    )
    assert trace.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert trace.promotion_status == "RESEARCH_ONLY_GRAPH_RUN"
    assert trace.execution_allowed is False
    assert trace.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_graph_run_trace_watchlists_missing_or_over_budget_checkpoints() -> None:
    graph = opportunity_research_diamond_workflow()
    checkpoints = tuple(
        graph_checkpoint(node.node_id, cost_units=5)
        for node in graph.nodes
        if node.node_id != "human_review_gate"
    )

    trace = summarize_graph_run_trace(
        graph,
        run_id="run-1",
        checkpoints=checkpoints,
        max_cost_units=10,
        max_retry_count=1,
    )

    assert trace.terminal_state is GraphRunTerminalState.WATCHLIST
    assert "GRAPH_RUN_MISSING_NODE_CHECKPOINT" in trace.blockers
    assert "GRAPH_RUN_COST_BUDGET_EXCEEDED" in trace.blockers
    assert "LIVE_ORDER_BLOCKED" in trace.blockers


def test_graph_run_trace_keeps_node_blockers_for_human_review() -> None:
    graph = opportunity_research_diamond_workflow()
    checkpoints = tuple(
        graph_checkpoint(
            node.node_id,
            blockers=(
                ("NODE_REVIEW_BLOCKER",) if node.node_id == "opportunity_report" else ()
            ),
        )
        for node in graph.nodes
    )

    trace = summarize_graph_run_trace(
        graph,
        run_id="run-1",
        checkpoints=checkpoints,
        max_cost_units=20,
        max_retry_count=1,
    )

    assert trace.terminal_state is GraphRunTerminalState.HUMAN_REVIEW_REQUIRED
    assert "NODE_REVIEW_BLOCKER" in trace.blockers
    assert trace.execution_allowed is False


def test_graph_node_route_reducer_accepts_passed_route_decisions() -> None:
    graph = opportunity_research_diamond_workflow()
    decisions = tuple(route_decision(node.node_id) for node in graph.nodes)

    reduction = reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=decisions,
        max_cost_units=20,
        max_retry_count=2,
    )

    assert reduction.terminal_state is GraphRunTerminalState.COMPLETED
    assert reduction.observed_nodes == graph.topological_order()
    assert reduction.missing_nodes == ()
    assert reduction.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert reduction.promotion_status == "RESEARCH_ONLY_GRAPH_ROUTE"
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_graph_node_route_reducer_keeps_retry_and_reroute_research_only() -> None:
    graph = opportunity_research_diamond_workflow()
    decisions = tuple(
        route_decision(
            node.node_id,
            decision=(
                GraphNodeRouteDecisionType.RETRY
                if node.node_id == "market_outlook_branch"
                else (
                    GraphNodeRouteDecisionType.REROUTE
                    if node.node_id == "setup_family_branch"
                    else GraphNodeRouteDecisionType.PASSED
                )
            ),
            target_node=(
                node.node_id
                if node.node_id == "market_outlook_branch"
                else (
                    "fresh_skeptic_verify"
                    if node.node_id == "setup_family_branch"
                    else ""
                )
            ),
            reason=(
                "Primary source retry required."
                if node.node_id == "market_outlook_branch"
                else (
                    "Verifier branch is better suited."
                    if node.node_id == "setup_family_branch"
                    else "Node output met its deterministic route contract."
                )
            ),
        )
        for node in graph.nodes
    )

    reduction = reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=decisions,
        max_cost_units=20,
        max_retry_count=2,
    )

    assert reduction.terminal_state is GraphRunTerminalState.RESEARCH_ONLY
    assert reduction.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert reduction.execution_allowed is False


def test_graph_node_route_reducer_escalates_without_live_authority() -> None:
    graph = opportunity_research_diamond_workflow()
    decisions = tuple(
        route_decision(
            node.node_id,
            decision=(
                GraphNodeRouteDecisionType.ESCALATE
                if node.node_id == "fresh_skeptic_verify"
                else GraphNodeRouteDecisionType.PASSED
            ),
            target_node=(
                "human_review_gate" if node.node_id == "fresh_skeptic_verify" else ""
            ),
            reason=(
                "Verifier found high-impact disagreement."
                if node.node_id == "fresh_skeptic_verify"
                else "Node output met its deterministic route contract."
            ),
        )
        for node in graph.nodes
    )

    reduction = reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=decisions,
        max_cost_units=20,
        max_retry_count=2,
    )

    assert reduction.terminal_state is GraphRunTerminalState.HUMAN_REVIEW_REQUIRED
    assert "GRAPH_ROUTE_ESCALATION_REQUIRED" in reduction.blockers
    assert "LIVE_ORDER_BLOCKED" in reduction.blockers
    assert reduction.execution_allowed is False


def test_graph_node_route_reducer_watchlists_missing_conflicting_or_stopped_route() -> (
    None
):
    graph = opportunity_research_diamond_workflow()
    decisions = tuple(
        route_decision(
            node.node_id,
            decision=(
                GraphNodeRouteDecisionType.STOP
                if node.node_id == "fresh_skeptic_verify"
                else GraphNodeRouteDecisionType.PASSED
            ),
            reason=(
                "Continuing would spread unsupported claims."
                if node.node_id == "fresh_skeptic_verify"
                else "Node output met its deterministic route contract."
            ),
            citations=(
                ()
                if node.node_id == "market_outlook_branch"
                else ("artifact://route-evidence",)
            ),
            reviewer_result=(
                "CONFLICTING" if node.node_id == "backtest_oos_branch" else "PASSED"
            ),
            retry_count=(3 if node.node_id == "setup_family_branch" else 0),
            cost_units=5,
        )
        for node in graph.nodes
        if node.node_id != "human_review_gate"
    )

    reduction = reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=decisions,
        max_cost_units=10,
        max_retry_count=2,
    )

    assert reduction.terminal_state is GraphRunTerminalState.WATCHLIST
    assert reduction.missing_nodes == ("human_review_gate",)
    assert "GRAPH_ROUTE_MISSING_NODE_DECISION" in reduction.blockers
    assert "GRAPH_ROUTE_COST_BUDGET_EXCEEDED" in reduction.blockers
    assert "GRAPH_ROUTE_RETRY_BUDGET_EXCEEDED" in reduction.blockers
    assert "GRAPH_ROUTE_CITATION_REQUIRED" in reduction.blockers
    assert "GRAPH_ROUTE_REVIEW_CONFLICTING" in reduction.blockers
    assert "GRAPH_ROUTE_STOP_REQUESTED" in reduction.blockers
    assert "LIVE_ORDER_BLOCKED" in reduction.blockers


def test_graph_node_route_reducer_watchlists_malformed_route_evidence() -> None:
    graph = opportunity_research_diamond_workflow()
    first_node = graph.topological_order()[0]
    remaining_decisions = tuple(
        route_decision(node.node_id)
        for node in graph.nodes
        if node.node_id != first_node
    )
    decisions = (
        route_decision("unknown_branch"),
        route_decision(first_node, run_id="other-run"),
        route_decision(first_node, reviewer_result="FAILED"),
        route_decision(first_node),
        *remaining_decisions,
    )

    reduction = reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=decisions,
        max_cost_units=20,
        max_retry_count=2,
    )

    assert reduction.terminal_state is GraphRunTerminalState.WATCHLIST
    assert "GRAPH_ROUTE_UNKNOWN_NODE_DECISION" in reduction.blockers
    assert "GRAPH_ROUTE_DECISION_IDENTITY_MISMATCH" in reduction.blockers
    assert "GRAPH_ROUTE_DUPLICATE_NODE_DECISION" in reduction.blockers
    assert "GRAPH_ROUTE_REVIEWER_RESULT_NOT_PASSED" in reduction.blockers
    assert "LIVE_ORDER_BLOCKED" in reduction.blockers


def test_graph_node_route_reducer_watchlists_unknown_reroute_target() -> None:
    graph = opportunity_research_diamond_workflow()
    decisions = tuple(
        route_decision(
            node.node_id,
            decision=(
                GraphNodeRouteDecisionType.REROUTE
                if node.node_id == "market_outlook_branch"
                else GraphNodeRouteDecisionType.PASSED
            ),
            target_node=(
                "missing_verifier_node"
                if node.node_id == "market_outlook_branch"
                else ""
            ),
            reason=(
                "Verifier route target must exist before graph execution can continue."
                if node.node_id == "market_outlook_branch"
                else "Node output met its deterministic route contract."
            ),
        )
        for node in graph.nodes
    )

    reduction = reduce_graph_node_route_decisions(
        graph,
        run_id="run-1",
        decisions=decisions,
        max_cost_units=20,
        max_retry_count=2,
    )

    assert reduction.terminal_state is GraphRunTerminalState.WATCHLIST
    assert "GRAPH_ROUTE_TARGET_UNKNOWN" in reduction.blockers
    assert reduction.execution_allowed is False


def test_agent_architecture_layer_reducer_accepts_complete_review_set() -> None:
    reviews = tuple(
        architecture_layer_evidence(layer) for layer in AGENT_ARCHITECTURE_LAYERS
    )

    reduction = reduce_agent_architecture_layer_reviews(
        reviews,
        workflow_id="opportunity-research-diamond",
    )

    assert (
        reduction.final_status
        is AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE
    )
    assert reduction.expected_layers == AGENT_ARCHITECTURE_LAYERS
    assert reduction.observed_layers == AGENT_ARCHITECTURE_LAYERS
    assert reduction.missing_layers == ()
    assert reduction.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_architecture_layer_reducer_watchlists_missing_or_weak_layers() -> None:
    reviews = (
        architecture_layer_evidence(
            AgentArchitectureLayer.HARNESS,
            citations=(),
            control_points=("permissions", "audit"),
        ),
        architecture_layer_evidence(
            AgentArchitectureLayer.LOOP,
            reviewer_result="CONFLICTING",
        ),
    )

    reduction = reduce_agent_architecture_layer_reviews(
        reviews,
        workflow_id="opportunity-research-diamond",
    )

    assert reduction.final_status is AgentArchitectureLayerStatus.WATCHLIST
    assert reduction.missing_layers == (AgentArchitectureLayer.GRAPH,)
    assert "ARCHITECTURE_LAYER_MISSING_REVIEW" in reduction.blockers
    assert "ARCHITECTURE_LAYER_CITATION_REQUIRED" in reduction.blockers
    assert "ARCHITECTURE_LAYER_HARNESS_CONTROL_POINT_MISSING" in reduction.blockers
    assert "ARCHITECTURE_LAYER_REVIEW_CONFLICTING" in reduction.blockers
    assert "LIVE_ORDER_BLOCKED" in reduction.blockers


def test_agent_architecture_reducer_watchlists_duplicate_and_mismatch() -> None:
    reviews = (
        architecture_layer_evidence(
            AgentArchitectureLayer.HARNESS,
            workflow_id="other-workflow",
        ),
        architecture_layer_evidence(
            AgentArchitectureLayer.HARNESS,
            reviewer_result="FAILED",
        ),
        architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
        architecture_layer_evidence(AgentArchitectureLayer.LOOP),
        architecture_layer_evidence(AgentArchitectureLayer.GRAPH),
    )

    reduction = reduce_agent_architecture_layer_reviews(
        reviews,
        workflow_id="opportunity-research-diamond",
    )

    assert reduction.final_status is AgentArchitectureLayerStatus.WATCHLIST
    assert "ARCHITECTURE_LAYER_WORKFLOW_MISMATCH" in reduction.blockers
    assert "ARCHITECTURE_LAYER_DUPLICATE_REVIEW" in reduction.blockers
    assert "ARCHITECTURE_LAYER_REVIEWER_RESULT_NOT_PASSED" in reduction.blockers
    assert reduction.execution_allowed is False


def test_agent_architecture_reducer_watchlists_layer_blockers() -> None:
    reviews = tuple(
        architecture_layer_evidence(
            layer,
            blockers=(
                ("LIVE_ORDER_BLOCKED",) if layer is AgentArchitectureLayer.LOOP else ()
            ),
        )
        for layer in AGENT_ARCHITECTURE_LAYERS
    )

    reduction = reduce_agent_architecture_layer_reviews(
        reviews,
        workflow_id="opportunity-research-diamond",
    )

    assert reduction.final_status is AgentArchitectureLayerStatus.WATCHLIST
    assert reduction.blockers == ("LIVE_ORDER_BLOCKED", "HUMAN_REVIEW_REQUIRED")
    assert reduction.execution_allowed is False


def test_agent_architecture_reducer_watchlists_unknown_layer_review() -> None:
    reviews = (
        architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
        architecture_layer_evidence(AgentArchitectureLayer.GRAPH),
    )

    reduction = reduce_agent_architecture_layer_reviews(
        reviews,
        workflow_id="opportunity-research-diamond",
        expected_layers=(AgentArchitectureLayer.HARNESS, AgentArchitectureLayer.LOOP),
    )

    assert reduction.final_status is AgentArchitectureLayerStatus.WATCHLIST
    assert "ARCHITECTURE_LAYER_UNKNOWN_REVIEW" in reduction.blockers
    assert "ARCHITECTURE_LAYER_MISSING_REVIEW" in reduction.blockers


def test_agent_architecture_coverage_summary_accepts_complete_external_link() -> None:
    reduction = reduce_agent_architecture_layer_reviews(
        tuple(
            architecture_layer_evidence(layer) for layer in AGENT_ARCHITECTURE_LAYERS
        ),
        workflow_id="opportunity-research-diamond",
    )

    summary = summarize_agent_architecture_coverage(
        reduction,
        source_uri="https://x.com/marfinxx/status/2081687570488954915",
        source_sha256=HASH,
    )

    assert summary.status is AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE
    assert summary.covered_layers == AGENT_ARCHITECTURE_LAYERS
    assert summary.missing_layers == ()
    assert summary.missing_control_points == ()
    assert summary.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_architecture_coverage_summary_watchlists_gaps() -> None:
    reduction = reduce_agent_architecture_layer_reviews(
        (
            architecture_layer_evidence(
                AgentArchitectureLayer.HARNESS,
                control_points=("permissions", "audit"),
            ),
            architecture_layer_evidence(AgentArchitectureLayer.LOOP),
        ),
        workflow_id="opportunity-research-diamond",
    )

    summary = summarize_agent_architecture_coverage(
        reduction,
        source_uri="http://example.com/agent-architecture",
        source_sha256=HASH,
    )

    assert summary.status is AgentArchitectureLayerStatus.WATCHLIST
    assert summary.covered_layers == (
        AgentArchitectureLayer.HARNESS,
        AgentArchitectureLayer.LOOP,
    )
    assert summary.missing_layers == (AgentArchitectureLayer.GRAPH,)
    assert "HARNESS:sandbox" in summary.missing_control_points
    assert "GRAPH:topology" in summary.missing_control_points
    assert "GRAPH:reducer" in summary.missing_control_points
    assert "ARCHITECTURE_COVERAGE_EXTERNAL_HTTPS_REQUIRED" in summary.blockers
    assert "ARCHITECTURE_COVERAGE_CONTROL_POINT_MISSING" in summary.blockers
    assert "ARCHITECTURE_COVERAGE_WATCHLIST" in summary.blockers
    assert "LIVE_ORDER_BLOCKED" in summary.blockers


def test_agent_invocation_coverage_summary_accepts_redacted_context() -> None:
    summary = invocation_coverage_summary()

    assert summary.status is (
        AgentInvocationCoverageStatus.RESEARCH_ONLY_AGENT_INVOCATION
    )
    assert summary.prompt_revision == "agent-stack-v1"
    assert summary.prompt_sha256 == HASH
    assert summary.context_sha256 == HASH
    assert summary.redaction_applied is True
    assert summary.private_context_detected is False
    assert summary.tool_output_verified is True
    assert summary.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_invocation_coverage_summary_watchlists_prompt_context_gaps() -> None:
    summary = invocation_coverage_summary(
        source_uri="http://example.com/agent-stack",
        source_sha256="",
        prompt_revision="",
        prompt_sha256="",
        context_sources=(),
        context_sha256="",
        context_freshness_policy="",
        citations=(),
        redaction_applied=False,
        private_context_detected=True,
        tool_output_verified=False,
    )

    assert summary.status is AgentInvocationCoverageStatus.WATCHLIST
    assert "AGENT_INVOCATION_SOURCE_HTTPS_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_SOURCE_HASH_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_PROMPT_REVISION_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_PROMPT_HASH_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_CONTEXT_SOURCE_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_CONTEXT_HASH_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_CONTEXT_FRESHNESS_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_CITATION_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_CONTEXT_REDACTION_REQUIRED" in summary.blockers
    assert "AGENT_INVOCATION_PRIVATE_CONTEXT_DETECTED" in summary.blockers
    assert "AGENT_INVOCATION_TOOL_OUTPUT_UNVERIFIED" in summary.blockers
    assert "LIVE_ORDER_BLOCKED" in summary.blockers


def test_graph_architecture_readiness_accepts_grounded_graph_as_research_only() -> None:
    graph = opportunity_research_diamond_workflow()
    review = review_graph_architecture_readiness(
        GraphArchitectureReadinessEvidence(
            workflow_id=graph.graph_id,
            selected_pattern="parallelization+evaluator-optimizer+human-in-the-loop",
            graph=graph,
            reviewer_nodes=("fresh_skeptic_verify",),
            anchor_artifacts=(
                "Backtest/validation/HOTUSDT/walk-forward-report.json",
                "Artifacts/opportunity-diamond/reducer-inputs.sha256",
            ),
            counter_metrics=(
                "net_return_vs_max_drawdown",
                "win_rate_vs_expectancy",
            ),
            human_gate_nodes=("human_review_gate",),
            reducer_nodes=("opportunity_reduce",),
            independent_reviewers=True,
            deterministic_reducer=True,
            trace_artifacts=("Logs/opportunity-diamond-trace.jsonl",),
        )
    )

    assert review.status is GraphArchitectureReadinessStatus.RESEARCH_ONLY_GRAPH_PATTERN
    assert review.promotion_status == "RESEARCH_ONLY_GRAPH_PATTERN"
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_graph_architecture_readiness_watchlists_missing_controls() -> None:
    graph = market_outlook_workflow()
    review = review_graph_architecture_readiness(
        GraphArchitectureReadinessEvidence(
            workflow_id=graph.graph_id,
            selected_pattern="single-loop-to-graph-readiness",
            graph=graph,
            reviewer_nodes=(),
            anchor_artifacts=(),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            independent_reviewers=False,
            deterministic_reducer=False,
        )
    )

    assert review.status is GraphArchitectureReadinessStatus.WATCHLIST
    assert "GRAPH_REVIEWER_NODE_REQUIRED" in review.blockers
    assert "GRAPH_INDEPENDENT_REVIEW_REQUIRED" in review.blockers
    assert "GRAPH_ANCHOR_ARTIFACT_REQUIRED" in review.blockers
    assert "GRAPH_COUNTER_METRIC_REQUIRED" in review.blockers
    assert "GRAPH_HUMAN_GATE_REQUIRED" in review.blockers
    assert "GRAPH_REDUCER_NODE_REQUIRED" in review.blockers
    assert "GRAPH_DETERMINISTIC_REDUCER_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_graph_workflow_manifest_keeps_grounded_manifest_research_only() -> None:
    review = review_graph_workflow_manifest(graph_manifest())

    assert (
        review.status is GraphWorkflowManifestReviewStatus.RESEARCH_ONLY_GRAPH_WORKFLOW
    )
    assert review.promotion_status == "RESEARCH_ONLY_GRAPH_WORKFLOW"
    assert review.state_schema_hash == HASH
    assert review.verifier_nodes == ("fresh_skeptic_verify",)
    assert review.human_gate_nodes == ("human_review_gate",)
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "GRAPH_WORKFLOW_MANIFEST_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_graph_workflow_manifest_watchlists_missing_controls_and_authority() -> None:
    review = review_graph_workflow_manifest(
        GraphWorkflowManifestEvidence(
            workflow_id="wide-graph-v0",
            selected_pattern="parallelization",
            nodes=("research", "synthesize"),
            edges=(("research", "missing"),),
            cycles_allowed=False,
            parallelism_cap=64,
            expected_artifacts=(),
            verifier_nodes=(),
            human_gate_nodes=(),
            state_schema_hash="",
            authority_flags=("READ_ONLY", "LIVE_ORDER_EXECUTION"),
        )
    )

    assert review.status is GraphWorkflowManifestReviewStatus.WATCHLIST
    assert "GRAPH_MANIFEST_EDGE_NODE_UNKNOWN" in review.blockers
    assert "GRAPH_MANIFEST_PARALLELISM_CAP_REVIEW_REQUIRED" in review.blockers
    assert "GRAPH_MANIFEST_EXPECTED_ARTIFACT_REQUIRED" in review.blockers
    assert "GRAPH_MANIFEST_VERIFIER_NODE_REQUIRED" in review.blockers
    assert "GRAPH_MANIFEST_HUMAN_GATE_REQUIRED" in review.blockers
    assert "GRAPH_MANIFEST_STATE_SCHEMA_HASH_REQUIRED" in review.blockers
    assert "GRAPH_MANIFEST_AUTHORITY_DRIFT" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_graph_workflow_manifest_watchlists_unreviewed_cycles() -> None:
    review = review_graph_workflow_manifest(
        graph_manifest(
            edges=(
                ("market_outlook_branch", "fresh_skeptic_verify"),
                ("fresh_skeptic_verify", "opportunity_reduce"),
                ("opportunity_reduce", "market_outlook_branch"),
            ),
            cycles_allowed=False,
            human_gate_nodes=(),
        )
    )

    assert review.status is GraphWorkflowManifestReviewStatus.WATCHLIST
    assert "GRAPH_MANIFEST_CYCLE_REVIEW_REQUIRED" in review.blockers
    assert "GRAPH_MANIFEST_CYCLE_HUMAN_GATE_REQUIRED" in review.blockers


def test_agent_model_candidate_review_keeps_cited_model_research_only() -> None:
    review = review_agent_model_candidate(model_candidate())

    assert review.status is AgentModelCandidateStatus.RESEARCH_ONLY_PROVIDER
    assert review.model_id == "kimi-k3"
    assert review.context_window_tokens == 1_048_576
    assert review.input_price_per_1m == 3.0
    assert review.cached_input_price_per_1m == 0.3
    assert review.output_price_per_1m == 15.0
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_PROVIDER"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_model_candidate_review_watchlists_provider_risk() -> None:
    review = review_agent_model_candidate(
        model_candidate(
            tool_call_support=False,
            json_mode_support=False,
            data_privacy_boundary="",
            cached_input_price_per_1m=4.0,
            blockers=("PROVIDER_BENCHMARK_SELF_REPORTED",),
            external_runtime_used=True,
            credential_required=True,
        )
    )

    assert review.status is AgentModelCandidateStatus.WATCHLIST
    assert "PROVIDER_DATA_PRIVACY_BOUNDARY_REQUIRED" in review.blockers
    assert "PROVIDER_TOOL_CALL_SUPPORT_UNVERIFIED" in review.blockers
    assert "PROVIDER_JSON_MODE_SUPPORT_UNVERIFIED" in review.blockers
    assert "PROVIDER_CACHED_INPUT_PRICE_EXCEEDS_INPUT_PRICE" in review.blockers
    assert "PROVIDER_EXTERNAL_RUNTIME_REVIEW_REQUIRED" in review.blockers
    assert "PROVIDER_CREDENTIAL_REVIEW_REQUIRED" in review.blockers
    assert "PROVIDER_BENCHMARK_SELF_REPORTED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_agent_model_candidate_review_watchlists_missing_citations() -> None:
    review = review_agent_model_candidate(model_candidate(citations=()))

    assert review.status is AgentModelCandidateStatus.WATCHLIST
    assert "PROVIDER_CITATION_REQUIRED" in review.blockers
    assert review.execution_allowed is False


def test_agent_skill_candidate_review_keeps_cited_skill_research_only() -> None:
    review = review_agent_skill_candidate(skill_candidate())

    assert review.status is AgentSkillCandidateStatus.RESEARCH_ONLY_SKILL
    assert review.skill_id == "agent-skill-authoring"
    assert review.source_sha256 == HASH
    assert review.declared_tools == ()
    assert review.script_paths == ()
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_SKILL"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_skill_candidate_review_watchlists_executable_or_private_risk() -> None:
    review = review_agent_skill_candidate(
        skill_candidate(
            declared_tools=("web.run",),
            script_paths=("scripts/install_skill.ps1",),
            blockers=("SKILL_SOURCE_SELF_REPORTED",),
            self_generated=True,
            network_access_required=True,
            credential_access_required=True,
            trading_scope_touched=True,
        )
    )

    assert review.status is AgentSkillCandidateStatus.WATCHLIST
    assert "SKILL_TOOL_REVIEW_REQUIRED" in review.blockers
    assert "SKILL_SCRIPT_REVIEW_REQUIRED" in review.blockers
    assert "SELF_GENERATED_SKILL_REVIEW_REQUIRED" in review.blockers
    assert "SKILL_NETWORK_REVIEW_REQUIRED" in review.blockers
    assert "SKILL_CREDENTIAL_REVIEW_REQUIRED" in review.blockers
    assert "SKILL_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "HUMAN_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers
    assert review.execution_allowed is False


def test_agent_skill_candidate_review_watchlists_missing_contract_or_review() -> None:
    review = review_agent_skill_candidate(
        skill_candidate(
            trigger_conditions=(),
            allowed_inputs=(),
            expected_output_contract=(),
            review_checklist=(),
            test_command="",
            citations=(),
            reviewer_result="CONFLICTING",
        )
    )

    assert review.status is AgentSkillCandidateStatus.WATCHLIST
    assert "SKILL_CITATION_REQUIRED" in review.blockers
    assert "SKILL_TRIGGER_CONDITION_REQUIRED" in review.blockers
    assert "SKILL_ALLOWED_INPUT_REQUIRED" in review.blockers
    assert "SKILL_OUTPUT_CONTRACT_REQUIRED" in review.blockers
    assert "SKILL_REVIEW_CHECKLIST_REQUIRED" in review.blockers
    assert "SKILL_TEST_COMMAND_REQUIRED" in review.blockers
    assert "SKILL_REVIEW_CONFLICTING" in review.blockers


def test_agent_workspace_component_review_keeps_cited_skill_research_only() -> None:
    review = review_agent_workspace_component(workspace_component())

    assert review.status is AgentWorkspaceComponentStatus.RESEARCH_ONLY_WORKSPACE
    assert review.component_type is AgentWorkspaceComponentType.SKILL
    assert review.source_path == ".agents/skills/ai4binance-validation-first/SKILL.md"
    assert review.content_sha256 == HASH
    assert review.canary_expected_blockers == (
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_WORKSPACE"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_workspace_component_review_watchlists_active_workspace_risk() -> None:
    review = review_agent_workspace_component(
        workspace_component(
            component_id="github-agent-workflow",
            component_type=AgentWorkspaceComponentType.WORKFLOW_YAML,
            source_path=".github/workflows/agent.yml",
            declared_authority="PAPER_PROPOSAL",
            canary_command="",
            canary_expected_blockers=("HUMAN_REVIEW_REQUIRED",),
            blockers=("WORKSPACE_CANARY_NOT_RUN",),
            external_runtime_used=True,
            credential_required=True,
            writes_enabled=True,
            trading_scope_touched=True,
        )
    )

    assert review.status is AgentWorkspaceComponentStatus.WATCHLIST
    assert review.component_type is AgentWorkspaceComponentType.WORKFLOW_YAML
    assert "WORKSPACE_AUTHORITY_REVIEW_REQUIRED" in review.blockers
    assert "WORKSPACE_CANARY_COMMAND_REQUIRED" in review.blockers
    assert "WORKSPACE_CANARY_LIVE_BLOCKER_REQUIRED" in review.blockers
    assert "WORKSPACE_EXTERNAL_RUNTIME_REVIEW_REQUIRED" in review.blockers
    assert "WORKSPACE_CREDENTIAL_REVIEW_REQUIRED" in review.blockers
    assert "WORKSPACE_WRITE_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "WORKSPACE_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "WORKSPACE_CANARY_NOT_RUN" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_agent_workspace_component_review_watchlists_missing_citations_or_canary() -> (
    None
):
    review = review_agent_workspace_component(
        workspace_component(
            component_type=AgentWorkspaceComponentType.MCP,
            citations=(),
            canary_expected_blockers=(),
        )
    )

    assert review.status is AgentWorkspaceComponentStatus.WATCHLIST
    assert "WORKSPACE_COMPONENT_CITATION_REQUIRED" in review.blockers
    assert "WORKSPACE_CANARY_EXPECTED_BLOCKER_REQUIRED" in review.blockers
    assert "WORKSPACE_CANARY_LIVE_BLOCKER_REQUIRED" in review.blockers


def test_markdown_governance_review_accepts_canonical_doc_research_only() -> None:
    review = review_markdown_governance_artifact(markdown_governance_artifact())

    assert review.status is MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION
    assert review.role is MarkdownGovernanceArtifactRole.ARCHITECTURE
    assert review.source_path == "Docs/ARCHITECTURE.md"
    assert review.content_sha256 == HASH
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_DOCUMENTATION"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_markdown_governance_review_watchlists_incomplete_vendor_bridge() -> None:
    review = review_markdown_governance_artifact(
        markdown_governance_artifact(
            artifact_id="claude-md",
            source_path="CLAUDE.md",
            role=MarkdownGovernanceArtifactRole.VENDOR_BRIDGE,
            declared_authority="WRITE",
            citations=(),
            owner="",
            freshness_policy="",
            reviewer_result=MarkdownGovernanceReviewerResult.PENDING,
            contains_private_context=True,
            external_runtime_used=True,
            credential_required=True,
        )
    )

    assert review.status is MarkdownGovernanceReviewStatus.WATCHLIST
    assert "MARKDOWN_CITATION_REQUIRED" in review.blockers
    assert "MARKDOWN_OWNER_REQUIRED" in review.blockers
    assert "MARKDOWN_FRESHNESS_POLICY_REQUIRED" in review.blockers
    assert "MARKDOWN_AUTHORITY_REVIEW_REQUIRED" in review.blockers
    assert "MARKDOWN_VENDOR_BRIDGE_CANONICAL_REQUIRED" in review.blockers
    assert "MARKDOWN_REVIEW_PENDING" in review.blockers
    assert "MARKDOWN_PRIVATE_CONTEXT_REDACTION_REQUIRED" in review.blockers
    assert "MARKDOWN_EXTERNAL_RUNTIME_REVIEW_REQUIRED" in review.blockers
    assert "MARKDOWN_CREDENTIAL_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_markdown_governance_reducer_accepts_complete_review_set() -> None:
    reviews = (
        review_markdown_governance_artifact(markdown_governance_artifact()),
        review_markdown_governance_artifact(
            markdown_governance_artifact(
                artifact_id="skills-governance-md",
                source_path="Docs/SKILLS_GOVERNANCE.md",
                role=MarkdownGovernanceArtifactRole.DOMAIN_RULES,
                citations=("artifact://Docs/SKILLS_GOVERNANCE.md",),
            )
        ),
    )

    reduction = reduce_markdown_governance_reviews(
        reviews,
        expected_artifacts=("architecture-md", "skills-governance-md"),
    )

    assert (
        reduction.final_status
        is MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION
    )
    assert reduction.observed_artifacts == (
        "architecture-md",
        "skills-governance-md",
    )
    assert reduction.missing_artifacts == ()
    assert reduction.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert reduction.promotion_status == "RESEARCH_ONLY_DOCUMENTATION"
    assert reduction.execution_allowed is False


def test_markdown_governance_reducer_downgrades_missing_or_conflicting_reviews() -> (
    None
):
    missing = reduce_markdown_governance_reviews(
        (review_markdown_governance_artifact(markdown_governance_artifact()),),
        expected_artifacts=("architecture-md", "review-md"),
    )
    conflicting = reduce_markdown_governance_reviews(
        (
            review_markdown_governance_artifact(markdown_governance_artifact()),
            review_markdown_governance_artifact(
                markdown_governance_artifact(
                    artifact_id="review-md",
                    source_path="factory/REVIEW.md",
                    role=MarkdownGovernanceArtifactRole.REVIEW,
                    reviewer_result=MarkdownGovernanceReviewerResult.CONFLICTING,
                    citations=("artifact://factory/REVIEW.md",),
                )
            ),
        ),
        expected_artifacts=("architecture-md", "review-md"),
    )
    duplicate = reduce_markdown_governance_reviews(
        (
            review_markdown_governance_artifact(markdown_governance_artifact()),
            review_markdown_governance_artifact(
                markdown_governance_artifact(
                    source_path="Docs/README.md",
                    citations=("artifact://Docs/README.md",),
                )
            ),
        ),
        expected_artifacts=("architecture-md",),
    )

    assert missing.final_status is MarkdownGovernanceReviewStatus.WATCHLIST
    assert missing.missing_artifacts == ("review-md",)
    assert "MISSING_MARKDOWN_REVIEW_RESULT" in missing.blockers

    assert conflicting.final_status is MarkdownGovernanceReviewStatus.WATCHLIST
    assert "CONFLICTING_MARKDOWN_REVIEW_RESULT" in conflicting.blockers
    assert "MARKDOWN_REVIEW_CONFLICTING" in conflicting.blockers

    assert duplicate.final_status is MarkdownGovernanceReviewStatus.WATCHLIST
    assert "DUPLICATE_MARKDOWN_REVIEW_RESULT" in duplicate.blockers


def test_closed_loop_admission_accepts_bounded_manual_loop_as_research_only() -> None:
    admission = admit_closed_loop(closed_loop_evidence())

    assert admission.status is ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP
    assert admission.loop_type is AgentLoopType.CLOSED
    assert admission.loop_scale is AgentLoopScale.SINGLE_AGENT
    assert admission.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert admission.promotion_status == "RESEARCH_ONLY_LOOP"
    assert admission.execution_allowed is False
    assert admission.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_closed_loop_admission_watchlists_open_fleet_or_connector_scope() -> None:
    admission = admit_closed_loop(
        ClosedLoopAdmissionEvidence(
            loop_id="open-fleet-loop-v0",
            task="Explore and repair anything the agent finds",
            trigger="",
            selected_pattern="autonomous_workflow",
            loop_type=AgentLoopType.OPEN,
            loop_scale=AgentLoopScale.FLEET,
            allowed_tools=(),
            allowed_write_roots=("Artifacts/generated",),
            memory_sources=(),
            verifier_identity="",
            artifact_log_uri="",
            stop_conditions=(),
            max_iterations=10,
            max_cost_units=100,
            human_handoff=False,
            connector_requested=True,
            plugin_requested=True,
            scheduler_requested=True,
            network_requested=True,
            trading_scope_touched=True,
        )
    )

    assert admission.status is ClosedLoopAdmissionStatus.WATCHLIST
    assert "LOOP_OPEN_SCOPE_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_FLEET_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_TRIGGER_REQUIRED" in admission.blockers
    assert "LOOP_ALLOWED_TOOL_SCOPE_REQUIRED" in admission.blockers
    assert "LOOP_WRITE_SCOPE_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_MEMORY_SOURCE_REQUIRED" in admission.blockers
    assert "LOOP_VERIFIER_REQUIRED" in admission.blockers
    assert "LOOP_ARTIFACT_LOG_REQUIRED" in admission.blockers
    assert "LOOP_STOP_CONDITION_REQUIRED" in admission.blockers
    assert "LOOP_HUMAN_HANDOFF_REQUIRED" in admission.blockers
    assert "LOOP_CONNECTOR_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_PLUGIN_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_SCHEDULER_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_NETWORK_REVIEW_REQUIRED" in admission.blockers
    assert "LOOP_TRADING_SCOPE_REVIEW_REQUIRED" in admission.blockers
    assert "LIVE_ORDER_BLOCKED" in admission.blockers


def test_loop_building_block_coverage_accepts_bounded_loop_as_research_only() -> None:
    summary = loop_building_block_coverage_summary()

    assert summary.status is LoopBuildingBlockCoverageStatus.RESEARCH_ONLY_LOOP
    assert summary.automation_trigger == "manual_codex_request"
    assert summary.subagent_roles == ("maker", "checker")
    assert summary.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert summary.promotion_status == "RESEARCH_ONLY_LOOP"
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_loop_building_block_coverage_watchlists_missing_or_risky_blocks() -> None:
    summary = loop_building_block_coverage_summary(
        automation_trigger="",
        worktree_isolation=False,
        skills_declared=(),
        connector_credentials_required=True,
        subagent_roles=(),
        memory_sources=(),
        cost_budget=0,
        stop_conditions=(),
        human_handoff=False,
        parallel_edits=True,
        memory_private_context_detected=True,
        trading_scope_touched=True,
    )

    assert summary.status is LoopBuildingBlockCoverageStatus.WATCHLIST
    assert "LOOP_AUTOMATION_TRIGGER_REQUIRED" in summary.blockers
    assert "LOOP_WORKTREE_ISOLATION_REQUIRED" in summary.blockers
    assert "LOOP_SKILL_DECLARATION_REQUIRED" in summary.blockers
    assert "LOOP_CONNECTOR_CREDENTIAL_REVIEW_REQUIRED" in summary.blockers
    assert "LOOP_SUBAGENT_REVIEWER_REQUIRED" in summary.blockers
    assert "LOOP_MEMORY_SOURCE_REQUIRED" in summary.blockers
    assert "LOOP_COST_BUDGET_REQUIRED" in summary.blockers
    assert "LOOP_STOP_CONDITION_REQUIRED" in summary.blockers
    assert "LOOP_HUMAN_HANDOFF_REQUIRED" in summary.blockers
    assert "LOOP_MEMORY_PRIVATE_CONTEXT_REVIEW_REQUIRED" in summary.blockers
    assert "LOOP_TRADING_SCOPE_REVIEW_REQUIRED" in summary.blockers
    assert "LIVE_ORDER_BLOCKED" in summary.blockers


def test_evaluator_gate_accepts_clean_shadow_gate_as_research_only() -> None:
    review = evaluator_gate_review()

    assert review.status is EvaluatorGateStatus.RESEARCH_ONLY_EVALUATOR_GATE
    assert review.blast_radius_lane is EvaluatorGateBlastRadiusLane.REVERSIBLE_CONTAINED
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_EVALUATOR_GATE"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_evaluator_gate_watchlists_biased_or_hard_to_reverse_gate() -> None:
    review = evaluator_gate_review(
        generator_model_family="gpt",
        judge_model_family="gpt",
        judge_version="",
        deterministic_checks=(),
        trajectory_checks=(),
        faithfulness_result="FAILED",
        task_completion_result="FAILED",
        verifier_canary_passed=False,
        blast_radius_lane=EvaluatorGateBlastRadiusLane.HARD_TO_REVERSE,
        human_disagreement_rate=0.2,
        agent_self_assessment_weight=0.5,
        shadow_mode=False,
        trading_scope_touched=True,
        production_data_touched=True,
        money_movement_touched=True,
    )

    assert review.status is EvaluatorGateStatus.WATCHLIST
    assert "EVALUATOR_GATE_CROSS_FAMILY_JUDGE_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_JUDGE_VERSION_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_DETERMINISTIC_CHECK_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_TRAJECTORY_CHECK_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_FAITHFULNESS_NOT_PASSED" in review.blockers
    assert "EVALUATOR_GATE_TASK_COMPLETION_NOT_PASSED" in review.blockers
    assert "EVALUATOR_GATE_VERIFIER_CANARY_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_HARD_TO_REVERSE_REVIEW_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_HUMAN_DISAGREEMENT_REVIEW_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_SELF_ASSESSMENT_WEIGHT_TOO_HIGH" in review.blockers
    assert "EVALUATOR_GATE_SHADOW_MODE_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_PRODUCTION_DATA_REVIEW_REQUIRED" in review.blockers
    assert "EVALUATOR_GATE_MONEY_MOVEMENT_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_residual_edge_review_accepts_costed_oos_edge_as_research_only() -> None:
    review = residual_edge_review()

    assert review.status is ResidualEdgeReviewStatus.RESEARCH_ONLY_RESIDUAL_EDGE
    assert review.expected_value_after_costs > 0
    assert review.sample_size == 240
    assert review.independent_repetition_count == 45
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_RESIDUAL_EDGE"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_residual_edge_review_returns_no_trade_when_costs_remove_edge() -> None:
    review = residual_edge_review(expected_value_after_costs=-0.0001)

    assert review.status is ResidualEdgeReviewStatus.NO_TRADE
    assert "RESIDUAL_EDGE_NO_TRADE_AFTER_COSTS" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers
    assert review.execution_allowed is False


def test_residual_edge_review_watchlists_underpowered_or_leaky_edge() -> None:
    review = residual_edge_review(
        residual_zscore=0.4,
        sample_size=20,
        independent_repetition_count=4,
        capacity_warning=True,
        regime_split=(),
        signal_decay_check="FAILED",
        data_leakage_check="FAILED",
        sizing_status="UNVALIDATED",
        oos_validation_present=False,
        trading_scope_touched=True,
    )

    assert review.status is ResidualEdgeReviewStatus.WATCHLIST
    assert "RESIDUAL_EDGE_STRETCH_TOO_WEAK" in review.blockers
    assert "RESIDUAL_EDGE_SAMPLE_SIZE_TOO_LOW" in review.blockers
    assert "RESIDUAL_EDGE_REPETITION_COUNT_TOO_LOW" in review.blockers
    assert "RESIDUAL_EDGE_CAPACITY_REVIEW_REQUIRED" in review.blockers
    assert "RESIDUAL_EDGE_REGIME_SPLIT_REQUIRED" in review.blockers
    assert "RESIDUAL_EDGE_SIGNAL_DECAY_NOT_PASSED" in review.blockers
    assert "RESIDUAL_EDGE_DATA_LEAKAGE_REVIEW_REQUIRED" in review.blockers
    assert "RESIDUAL_EDGE_SIZING_VALIDATION_REQUIRED" in review.blockers
    assert "RESIDUAL_EDGE_OOS_VALIDATION_REQUIRED" in review.blockers
    assert "RESIDUAL_EDGE_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_cowork_task_suitability_accepts_bounded_report_task_as_research_only() -> None:
    review = cowork_task_suitability_review()

    assert review.status is CoworkTaskSuitabilityStatus.RESEARCH_ONLY_COWORK_TASK
    assert review.task_id == "daily-research-digest"
    assert review.connector_scope == ("repo_artifacts_readonly",)
    assert review.schedule_requested is True
    assert review.manual_run_verified is True
    assert review.draft_only is True
    assert review.human_approval_required is True
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_COWORK_TASK"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_cowork_task_suitability_watchlists_uncheckable_or_risky_task() -> None:
    review = cowork_task_suitability_review(
        touches_files_apps_or_web=False,
        tedious_repetitive_or_multistep=False,
        done_is_checkable=False,
        mistake_is_survivable=False,
        brain_file_present=False,
        skill_declared=False,
        connector_scope=("all",),
        schedule_requested=True,
        manual_run_verified=False,
        draft_only=False,
        human_approval_required=False,
        judgment_required=True,
        secret_access_requested=True,
        trading_scope_touched=True,
        money_movement_touched=True,
    )

    assert review.status is CoworkTaskSuitabilityStatus.WATCHLIST
    assert "COWORK_TASK_SURFACE_REQUIRED" in review.blockers
    assert "COWORK_TASK_REPETITION_REQUIRED" in review.blockers
    assert "COWORK_TASK_CHECKABLE_DONE_REQUIRED" in review.blockers
    assert "COWORK_TASK_SURVIVABLE_MISTAKE_REQUIRED" in review.blockers
    assert "COWORK_TASK_BRAIN_FILE_REQUIRED" in review.blockers
    assert "COWORK_TASK_SKILL_REQUIRED" in review.blockers
    assert "COWORK_TASK_CONNECTOR_SCOPE_TOO_BROAD" in review.blockers
    assert "COWORK_TASK_MANUAL_RUN_REQUIRED_BEFORE_SCHEDULE" in review.blockers
    assert "COWORK_TASK_DRAFT_ONLY_REQUIRED" in review.blockers
    assert "COWORK_TASK_HUMAN_APPROVAL_REQUIRED" in review.blockers
    assert "COWORK_TASK_JUDGMENT_REVIEW_REQUIRED" in review.blockers
    assert "COWORK_TASK_SECRET_ACCESS_REVIEW_REQUIRED" in review.blockers
    assert "COWORK_TASK_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "COWORK_TASK_MONEY_MOVEMENT_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_trajectory_learning_eligibility_accepts_redacted_replayable_trace() -> None:
    review = trajectory_learning_eligibility_review()

    assert (
        review.status
        is AgentTrajectoryLearningEligibilityStatus.RESEARCH_ONLY_TRAJECTORY_LEARNING
    )
    assert review.replay_class == "DETERMINISTIC_REPLAY"
    assert review.redaction_status == "REDACTED"
    assert review.intervention_candidate == "MEMORY_CANDIDATE"
    assert review.blockers == (
        "MODEL_UPDATE_BLOCKED",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.promotion_status == "RESEARCH_ONLY_TRAJECTORY_LEARNING"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_trajectory_learning_eligibility_watchlists_unreplayable_or_risky_trace() -> (
    None
):
    review = trajectory_learning_eligibility_review(
        replay_class="NON_REPLAYABLE",
        redaction_status="RAW",
        reward_signal="NONE",
        intervention_candidate="MODEL_WEIGHT_UPDATE",
        causal_step_count=0,
        delayed_reward_supported=False,
        provenance_versioned=False,
        governance_metadata_present=False,
        human_correction_present=False,
        training_eligible=False,
        secret_risk_detected=True,
        trading_scope_touched=True,
        money_movement_touched=True,
        model_weight_update_requested=True,
    )

    assert review.status is AgentTrajectoryLearningEligibilityStatus.WATCHLIST
    assert "TRAJECTORY_LEARNING_DETERMINISTIC_REPLAY_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_REDACTION_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_REWARD_SIGNAL_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_INTERVENTION_SURFACE_REVIEW_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_CAUSAL_STEP_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_DELAYED_REWARD_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_PROVENANCE_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_GOVERNANCE_METADATA_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_HUMAN_CORRECTION_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_TRAINING_ELIGIBILITY_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_SECRET_RISK_REVIEW_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_MONEY_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "TRAJECTORY_LEARNING_MODEL_WEIGHT_UPDATE_BLOCKED" in review.blockers
    assert "MODEL_UPDATE_BLOCKED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_graph_dependency_integrity_accepts_anchored_diamond_as_research_only() -> None:
    review = graph_dependency_integrity_review()

    assert (
        review.status is GraphDependencyIntegrityStatus.RESEARCH_ONLY_GRAPH_DEPENDENCY
    )
    assert review.graph_id == "opportunity-research-diamond-v1"
    assert review.missing_nodes == ()
    assert review.fake_edges == ()
    assert review.fanout_width == 2
    assert review.verifier_context_isolated is True
    assert review.anchor_artifacts == ("quality-gate:passed",)
    assert review.merge_input_count_verified is True
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.promotion_status == "RESEARCH_ONLY_GRAPH_DEPENDENCY"
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_graph_dependency_integrity_watchlists_fake_edges_and_missing_anchors() -> None:
    review = graph_dependency_integrity_review(
        observed_nodes=("plan", "market", "verifier", "reducer", "synthesizer"),
        declared_edges=("plan->market", "market->verifier", "risk->verifier"),
        data_carrying_edges=("plan->market", "market->verifier"),
        fake_edges=("risk->verifier",),
        fanout_width=1,
        barrier_count=0,
        verifier_context_isolated=False,
        anchor_artifacts=(),
        merge_input_count_verified=False,
        model_tiering_policy_present=False,
        cost_cap_present=False,
        silent_node_failure_count=1,
        trading_scope_touched=True,
        money_movement_touched=True,
    )

    assert review.status is GraphDependencyIntegrityStatus.WATCHLIST
    assert "risk" in review.missing_nodes
    assert "GRAPH_DEPENDENCY_MISSING_NODE_REVIEW_REQUIRED" in review.blockers
    assert "WATCHLIST_GRAPH_FAKE_EDGE" in review.blockers
    assert "GRAPH_DEPENDENCY_FANOUT_WIDTH_REQUIRED" in review.blockers
    assert "GRAPH_DEPENDENCY_BARRIER_REQUIRED" in review.blockers
    assert "WATCHLIST_VERIFIER_CONTEXT_SHARED" in review.blockers
    assert "WATCHLIST_GRAPH_ANCHOR_MISSING" in review.blockers
    assert "WATCHLIST_SILENT_NODE_FAILURE_RISK" in review.blockers
    assert "GRAPH_DEPENDENCY_MODEL_TIERING_POLICY_REQUIRED" in review.blockers
    assert "WATCHLIST_GRAPH_COST_BOUNDARY_MISSING" in review.blockers
    assert "GRAPH_DEPENDENCY_SILENT_NODE_FAILURE_DETECTED" in review.blockers
    assert "GRAPH_DEPENDENCY_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "GRAPH_DEPENDENCY_MONEY_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_graph_dependency_integrity_watchlists_untrusted_source() -> None:
    review = graph_dependency_integrity_review(
        source_uri="http://example.test/graph",
        source_sha256="",
        declared_edges=(),
        data_carrying_edges=(),
    )

    assert review.status is GraphDependencyIntegrityStatus.WATCHLIST
    assert "GRAPH_DEPENDENCY_SOURCE_HTTPS_REQUIRED" in review.blockers
    assert "GRAPH_DEPENDENCY_SOURCE_HASH_REQUIRED" in review.blockers
    assert "GRAPH_DEPENDENCY_DECLARED_EDGE_REQUIRED" in review.blockers
    assert "GRAPH_DEPENDENCY_DATA_CARRYING_EDGE_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_graph_dependency_integrity_rejects_inconsistent_graph_shapes() -> None:
    with pytest.raises(ValueError, match="identity"):
        graph_dependency_integrity_review(graph_id="")
    with pytest.raises(ValueError, match="expected nodes"):
        graph_dependency_integrity_review(expected_nodes=(), observed_nodes=())
    with pytest.raises(ValueError, match="unknown node"):
        graph_dependency_integrity_review(observed_nodes=("plan", "unknown"))
    with pytest.raises(ValueError, match="data edges"):
        graph_dependency_integrity_review(
            declared_edges=("plan->market",),
            data_carrying_edges=("market->verifier",),
        )
    with pytest.raises(ValueError, match="fake edges"):
        graph_dependency_integrity_review(
            declared_edges=("plan->market",),
            data_carrying_edges=("plan->market",),
            fake_edges=("market->verifier",),
        )


def test_closed_loop_run_summary_accepts_verified_goal_run_as_research_only() -> None:
    summary = summarize_closed_loop_run(
        closed_loop_run_evidence(trigger_type=ClosedLoopRunTriggerType.GOAL)
    )

    assert summary.status is ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP
    assert summary.trigger_type is ClosedLoopRunTriggerType.GOAL
    assert summary.resume_point == "queue:next-artifact"
    assert summary.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert summary.promotion_status == "RESEARCH_ONLY_LOOP"
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_closed_loop_run_summary_watchlists_unverified_state_or_budget_drift() -> None:
    summary = summarize_closed_loop_run(
        closed_loop_run_evidence(
            iteration_count=4,
            cost_units=21,
            state_read_before_frame=False,
            verification_passed=False,
            state_written_after_verification=True,
            stop_condition_met=False,
            model_claimed_completion=True,
        )
    )

    assert summary.status is ClosedLoopAdmissionStatus.WATCHLIST
    assert "LOOP_STATE_READ_BEFORE_FRAME_REQUIRED" in summary.blockers
    assert "LOOP_STATE_WRITE_AFTER_FAILED_VERIFY" in summary.blockers
    assert "LOOP_STOP_CONDITION_NOT_MET" in summary.blockers
    assert "LOOP_ITERATION_BUDGET_EXCEEDED" in summary.blockers
    assert "LOOP_COST_BUDGET_EXCEEDED" in summary.blockers
    assert "LOOP_MODEL_COMPLETION_CLAIM_REQUIRES_VERIFIER" in summary.blockers
    assert "LIVE_ORDER_BLOCKED" in summary.blockers


def test_closed_loop_run_summary_watchlists_unadmitted_loop_run() -> None:
    admission = admit_closed_loop(
        ClosedLoopAdmissionEvidence(
            loop_id="open-fleet-loop-v0",
            task="Explore and repair anything the agent finds",
            trigger="",
            selected_pattern="autonomous_workflow",
            loop_type=AgentLoopType.OPEN,
            loop_scale=AgentLoopScale.FLEET,
            allowed_tools=(),
            allowed_write_roots=("Artifacts/generated",),
            memory_sources=(),
            verifier_identity="",
            artifact_log_uri="",
            stop_conditions=(),
            max_iterations=10,
            max_cost_units=100,
            human_handoff=False,
            trading_scope_touched=True,
        )
    )

    summary = summarize_closed_loop_run(
        closed_loop_run_evidence(
            admission=admission,
            trigger_type=ClosedLoopRunTriggerType.CRON,
        )
    )

    assert summary.status is ClosedLoopAdmissionStatus.WATCHLIST
    assert summary.trigger_type is ClosedLoopRunTriggerType.CRON
    assert "LOOP_ADMISSION_NOT_RESEARCH_ONLY" in summary.blockers
    assert "LOOP_VERIFIER_IDENTITY_MISMATCH" in summary.blockers


def test_loop_readiness_accepts_bounded_verified_loop_as_research_only() -> None:
    review = review_loop_engineering_readiness(
        LoopEngineeringReadinessEvidence(
            loop_id="opportunity-loop-v1",
            task="Improve opportunity report quality from verified artifacts",
            selected_pattern="evaluator-optimizer+human-in-the-loop",
            objective_metric="artifact_review_pass_rate",
            deterministic_verifier=True,
            max_iterations=5,
            max_cost_units=25,
            rollback_or_no_write=True,
            artifact_log_uri="Artifacts/loops/opportunity-loop-v1.jsonl",
            holdout_artifact_uri="Backtest/holdout/HOTUSDT/holdout-report.json",
            oos_artifact_uri="Backtest/oos/HOTUSDT/walk-forward-report.json",
            human_gate=True,
            stop_conditions=(
                "max_iterations_reached",
                "quality_gate_passed_or_failed",
            ),
            before_after_metrics=(
                "pytest_pass_count",
                "coverage_percent",
                "review_blocker_count",
            ),
        )
    )

    assert review.status is LoopEngineeringReadinessStatus.RESEARCH_ONLY_LOOP_PATTERN
    assert review.promotion_status == "RESEARCH_ONLY_LOOP_PATTERN"
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_loop_engineering_readiness_watchlists_unbounded_or_unverified_loop() -> None:
    review = review_loop_engineering_readiness(
        LoopEngineeringReadinessEvidence(
            loop_id="prompt-loop-v0",
            task="Optimize prompts without validation evidence",
            selected_pattern="open-ended-self-improvement-loop",
            objective_metric="",
            deterministic_verifier=False,
            max_iterations=10,
            max_cost_units=100,
            rollback_or_no_write=False,
            artifact_log_uri="",
            holdout_artifact_uri="",
            oos_artifact_uri="",
            human_gate=False,
            stop_conditions=(),
            before_after_metrics=(),
            allowed_write_roots=("Artifacts/generated",),
            trading_scope_touched=True,
            provider_runtime_used=True,
        )
    )

    assert review.status is LoopEngineeringReadinessStatus.WATCHLIST
    assert "LOOP_OBJECTIVE_METRIC_REQUIRED" in review.blockers
    assert "LOOP_DETERMINISTIC_VERIFIER_REQUIRED" in review.blockers
    assert "LOOP_STOP_CONDITION_REQUIRED" in review.blockers
    assert "LOOP_BEFORE_AFTER_METRIC_REQUIRED" in review.blockers
    assert "LOOP_ROLLBACK_OR_NO_WRITE_REQUIRED" in review.blockers
    assert "LOOP_ARTIFACT_LOG_REQUIRED" in review.blockers
    assert "LOOP_HOLDOUT_EVIDENCE_REQUIRED" in review.blockers
    assert "LOOP_OOS_EVIDENCE_REQUIRED" in review.blockers
    assert "LOOP_HUMAN_GATE_REQUIRED" in review.blockers
    assert "LOOP_WRITE_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "LOOP_PROVIDER_RUNTIME_REVIEW_REQUIRED" in review.blockers
    assert "LOOP_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_opportunity_artifact_reducer_keeps_complete_reviews_research_only() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)

    reduction = reduce_opportunity_artifact_reviews(reviews)

    assert reduction.observed_branches == OPPORTUNITY_RESEARCH_BRANCH_IDS
    assert reduction.missing_branches == ()
    assert (
        reduction.final_status
        is OpportunityArtifactReductionStatus.RESEARCH_ONLY_OPPORTUNITY
    )
    assert reduction.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert reduction.promotion_status == "RESEARCH_ONLY"
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_downgrades_missing_or_conflicting_reviews() -> (
    None
):
    missing = reduce_opportunity_artifact_reviews(
        tuple(
            branch_review(branch)
            for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS
            if branch != "whale_fusion_branch"
        )
    )
    conflicting = reduce_opportunity_artifact_reviews(
        (
            *tuple(
                branch_review(branch)
                for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS
                if branch != "backtest_oos_branch"
            ),
            branch_review(
                "backtest_oos_branch",
                reviewer_result=OpportunityArtifactReviewStatus.CONFLICTING,
                blockers=("OOS_REVIEW_CONFLICT",),
            ),
        )
    )

    assert missing.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert missing.missing_branches == ("whale_fusion_branch",)
    assert "MISSING_BRANCH_REVIEW_RESULT" in missing.blockers
    assert conflicting.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert "CONFLICTING_BRANCH_REVIEW_RESULT" in conflicting.blockers
    assert "OOS_REVIEW_CONFLICT" in conflicting.blockers


def test_opportunity_artifact_reducer_preserves_branch_blockers_without_execution() -> (
    None
):
    reviews = tuple(
        branch_review(
            branch,
            reviewer_result=(
                OpportunityArtifactReviewStatus.RESEARCH_ONLY_OPPORTUNITY
                if branch == "setup_family_branch"
                else OpportunityArtifactReviewStatus.PASSED
            ),
            blockers=(
                ("VALIDATION_GATE_REQUIRED",) if branch == "setup_family_branch" else ()
            ),
        )
        for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS
    )

    reduction = reduce_opportunity_artifact_reviews(reviews)

    assert (
        reduction.final_status
        is OpportunityArtifactReductionStatus.RESEARCH_ONLY_OPPORTUNITY
    )
    assert "VALIDATION_GATE_REQUIRED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_requires_workspace_component_reviews() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    workspace_review = review_agent_workspace_component(workspace_component())

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        supporting_workspace_reviews=(workspace_review,),
        expected_workspace_components=("ai4binance-validation-first",),
    )
    missing = reduce_opportunity_artifact_reviews(
        reviews,
        supporting_workspace_reviews=(),
        expected_workspace_components=("ai4binance-validation-first",),
    )
    watchlisted = reduce_opportunity_artifact_reviews(
        reviews,
        supporting_workspace_reviews=(
            review_agent_workspace_component(
                workspace_component(
                    component_id="github-agent-workflow",
                    component_type=AgentWorkspaceComponentType.WORKFLOW_YAML,
                    source_path=".github/workflows/agent.yml",
                    declared_authority="WRITE",
                    canary_command="",
                    external_runtime_used=True,
                    credential_required=True,
                    writes_enabled=True,
                    trading_scope_touched=True,
                )
            ),
        ),
        expected_workspace_components=("github-agent-workflow",),
    )

    assert (
        reduction.final_status
        is OpportunityArtifactReductionStatus.RESEARCH_ONLY_OPPORTUNITY
    )
    assert reduction.observed_workspace_components == ("ai4binance-validation-first",)
    assert reduction.missing_workspace_components == ()
    assert reduction.supporting_workspace_reviews == (workspace_review,)
    assert reduction.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")

    assert missing.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert missing.missing_workspace_components == ("ai4binance-validation-first",)
    assert "MISSING_WORKSPACE_COMPONENT_REVIEW" in missing.blockers

    assert watchlisted.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert "WATCHLIST_WORKSPACE_COMPONENT_REVIEW" in watchlisted.blockers
    assert "WORKSPACE_WRITE_SCOPE_REVIEW_REQUIRED" in watchlisted.blockers
    assert "LIVE_ORDER_BLOCKED" in watchlisted.blockers


def test_opportunity_artifact_reducer_watchlists_architecture_coverage_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    architecture_reduction = reduce_agent_architecture_layer_reviews(
        (
            architecture_layer_evidence(
                AgentArchitectureLayer.HARNESS,
                control_points=("permissions", "audit"),
            ),
            architecture_layer_evidence(AgentArchitectureLayer.LOOP),
        ),
        workflow_id="opportunity-research-diamond",
    )
    coverage_summary = summarize_agent_architecture_coverage(
        architecture_reduction,
        source_uri="https://x.com/marfinxx/status/2081687570488954915",
        source_sha256=HASH,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        architecture_coverage_summary=coverage_summary,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.architecture_coverage_summary == coverage_summary
    assert "WATCHLIST_AGENT_ARCHITECTURE_COVERAGE" in reduction.blockers
    assert "ARCHITECTURE_COVERAGE_CONTROL_POINT_MISSING" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_invocation_coverage_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    coverage_summary = invocation_coverage_summary(
        prompt_sha256="",
        context_sources=(),
        context_sha256="",
        redaction_applied=False,
        tool_output_verified=False,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        invocation_coverage_summary=coverage_summary,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.invocation_coverage_summary == coverage_summary
    assert "WATCHLIST_AGENT_INVOCATION_COVERAGE" in reduction.blockers
    assert "AGENT_INVOCATION_PROMPT_HASH_REQUIRED" in reduction.blockers
    assert "AGENT_INVOCATION_CONTEXT_REDACTION_REQUIRED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_loop_building_block_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    coverage_summary = loop_building_block_coverage_summary(
        automation_trigger="",
        worktree_isolation=False,
        cost_budget=0,
        stop_conditions=(),
        human_handoff=False,
        parallel_edits=True,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        loop_building_block_coverage_summary=coverage_summary,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.loop_building_block_coverage_summary == coverage_summary
    assert "WATCHLIST_LOOP_BUILDING_BLOCK_COVERAGE" in reduction.blockers
    assert "LOOP_AUTOMATION_TRIGGER_REQUIRED" in reduction.blockers
    assert "LOOP_WORKTREE_ISOLATION_REQUIRED" in reduction.blockers
    assert "LOOP_STOP_CONDITION_REQUIRED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_evaluator_gate_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    gate_review = evaluator_gate_review(
        deterministic_checks=(),
        trajectory_checks=(),
        verifier_canary_passed=False,
        blast_radius_lane=EvaluatorGateBlastRadiusLane.HARD_TO_REVERSE,
        trading_scope_touched=True,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        evaluator_gate_review=gate_review,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.evaluator_gate_review == gate_review
    assert "WATCHLIST_EVALUATOR_GATE_REVIEW" in reduction.blockers
    assert "EVALUATOR_GATE_DETERMINISTIC_CHECK_REQUIRED" in reduction.blockers
    assert "EVALUATOR_GATE_TRAJECTORY_CHECK_REQUIRED" in reduction.blockers
    assert "EVALUATOR_GATE_HARD_TO_REVERSE_REVIEW_REQUIRED" in reduction.blockers
    assert "EVALUATOR_GATE_TRADING_SCOPE_REVIEW_REQUIRED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_residual_edge_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    edge_review = residual_edge_review(
        sample_size=10,
        independent_repetition_count=2,
        data_leakage_check="FAILED",
        oos_validation_present=False,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        residual_edge_review=edge_review,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.residual_edge_review == edge_review
    assert "WATCHLIST_RESIDUAL_EDGE_REVIEW" in reduction.blockers
    assert "RESIDUAL_EDGE_SAMPLE_SIZE_TOO_LOW" in reduction.blockers
    assert "RESIDUAL_EDGE_REPETITION_COUNT_TOO_LOW" in reduction.blockers
    assert "RESIDUAL_EDGE_DATA_LEAKAGE_REVIEW_REQUIRED" in reduction.blockers
    assert "RESIDUAL_EDGE_OOS_VALIDATION_REQUIRED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_no_trade_residual_edge() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    edge_review = residual_edge_review(expected_value_after_costs=0.0)

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        residual_edge_review=edge_review,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.residual_edge_review == edge_review
    assert "NO_TRADE_RESIDUAL_EDGE_REVIEW" in reduction.blockers
    assert "RESIDUAL_EDGE_NO_TRADE_AFTER_COSTS" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_cowork_task_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    cowork_review = cowork_task_suitability_review(
        done_is_checkable=False,
        connector_scope=("full_access",),
        schedule_requested=True,
        manual_run_verified=False,
        secret_access_requested=True,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        cowork_task_suitability_review=cowork_review,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.cowork_task_suitability_review == cowork_review
    assert "WATCHLIST_COWORK_TASK_SUITABILITY" in reduction.blockers
    assert "COWORK_TASK_CHECKABLE_DONE_REQUIRED" in reduction.blockers
    assert "COWORK_TASK_CONNECTOR_SCOPE_TOO_BROAD" in reduction.blockers
    assert "COWORK_TASK_MANUAL_RUN_REQUIRED_BEFORE_SCHEDULE" in reduction.blockers
    assert "COWORK_TASK_SECRET_ACCESS_REVIEW_REQUIRED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_trajectory_learning_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    learning_review = trajectory_learning_eligibility_review(
        redaction_status="RAW",
        model_weight_update_requested=True,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        trajectory_learning_eligibility_review=learning_review,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.trajectory_learning_eligibility_review == learning_review
    assert "WATCHLIST_TRAJECTORY_LEARNING_ELIGIBILITY" in reduction.blockers
    assert "TRAJECTORY_LEARNING_REDACTION_REQUIRED" in reduction.blockers
    assert "TRAJECTORY_LEARNING_MODEL_WEIGHT_UPDATE_BLOCKED" in reduction.blockers
    assert "MODEL_UPDATE_BLOCKED" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_artifact_reducer_watchlists_graph_dependency_gap() -> None:
    reviews = tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS)
    graph_review = graph_dependency_integrity_review(
        fake_edges=("plan->risk",),
        verifier_context_isolated=False,
        anchor_artifacts=(),
        merge_input_count_verified=False,
        cost_cap_present=False,
    )

    reduction = reduce_opportunity_artifact_reviews(
        reviews,
        graph_dependency_integrity_review=graph_review,
    )

    assert reduction.final_status is OpportunityArtifactReductionStatus.WATCHLIST
    assert reduction.graph_dependency_integrity_review == graph_review
    assert "WATCHLIST_GRAPH_DEPENDENCY_INTEGRITY" in reduction.blockers
    assert "WATCHLIST_GRAPH_FAKE_EDGE" in reduction.blockers
    assert "WATCHLIST_VERIFIER_CONTEXT_SHARED" in reduction.blockers
    assert "WATCHLIST_GRAPH_ANCHOR_MISSING" in reduction.blockers
    assert "WATCHLIST_SILENT_NODE_FAILURE_RISK" in reduction.blockers
    assert "WATCHLIST_GRAPH_COST_BOUNDARY_MISSING" in reduction.blockers
    assert reduction.execution_allowed is False
    assert reduction.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_workflow_graph_rejects_unknown_dependencies_and_cycles() -> None:
    node = WorkflowNode(
        "a", "TEST", ("missing",), (), (), 1, WorkflowAuthority.READ_ONLY
    )
    with pytest.raises(ValueError, match="unknown"):
        WorkflowGraph("graph", (node,))
    cycle_a = replace(node, dependencies=("b",))
    cycle_b = replace(node, node_id="b", dependencies=("a",))
    with pytest.raises(ValueError, match="cycle"):
        WorkflowGraph("graph", (cycle_a, cycle_b))


def test_workflow_preview_rejects_authority_drift() -> None:
    with pytest.raises(ValueError, match="identity"):
        WorkflowPreview(
            "",
            ("a",),
            ("a",),
        )
    with pytest.raises(ValueError, match="validation point"):
        WorkflowPreview(
            "graph",
            ("a",),
            ("missing",),
        )
    with pytest.raises(ValueError, match="review-only"):
        WorkflowPreview(
            "graph",
            ("a",),
            ("a",),
            status=WorkflowPreviewStatus.HUMAN_REVIEW_REQUIRED,
            blockers=("HUMAN_REVIEW_REQUIRED",),
        )
    with pytest.raises(ValueError, match="review-only"):
        WorkflowPreview(
            "graph",
            ("a",),
            ("a",),
            execution_allowed=True,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(lesson(), lesson_id=""),
        lambda: replace(lesson(), evidence_count=0),
        lambda: replace(lesson(), source_artifact_ids=()),
        lambda: replace(lesson(), source_artifact_ids=("a", "a")),
        lambda: replace(lesson(), source_artifact_ids=("",)),
        lambda: replace(lesson(), observed_at=datetime(2026, 7, 13)),
        lambda: replace(lesson(), expires_at=NOW),
        lambda: replace(lesson(), validation_artifact_ids=("a", "a")),
        lambda: replace(lesson(), execution_allowed=True),
        lambda: replace(
            lesson(),
            status=LessonStatus.HUMAN_APPROVED,
            validation_artifact_ids=(),
        ),
    ],
)
def test_lesson_contract_rejects_invalid_shapes(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_lesson_terminal_and_blocked_transitions_are_rejected() -> None:
    rejected = lesson().transition(LessonStatus.REJECTED, at=NOW)
    with pytest.raises(ValueError, match="terminal"):
        rejected.transition(LessonStatus.EXPIRED, at=NOW)
    with pytest.raises(ValueError, match="terminal"):
        rejected.transition(LessonStatus.DEDUPLICATED, at=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        lesson().transition(LessonStatus.DEDUPLICATED, at=datetime(2026, 7, 13))

    item = lesson()
    for status in (
        LessonStatus.DEDUPLICATED,
        LessonStatus.CONTRADICTION_CHECKED,
        LessonStatus.VALIDATION_PENDING,
        LessonStatus.RESEARCH_ONLY,
    ):
        item = item.transition(
            status,
            at=NOW + timedelta(minutes=1),
            validation_artifact_ids=("oos",),
        )
    with pytest.raises(ValueError, match="blocked"):
        item.transition(
            LessonStatus.HUMAN_APPROVED,
            at=NOW + timedelta(minutes=2),
            blockers=("CONTRADICTION",),
            human_approved=True,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(job_manifest(Path("C:/repo")), job_id=""),
        lambda: replace(job_manifest(Path("C:/repo")), allowed_capabilities=()),
        lambda: replace(job_manifest(Path("C:/repo")), allowed_roots=(Path("repo"),)),
        lambda: replace(job_manifest(Path("C:/repo")), lock_path=Path("lock")),
        lambda: replace(job_manifest(Path("C:/repo")), timeout_seconds=0),
        lambda: replace(job_manifest(Path("C:/repo")), maximum_output_bytes=1),
        lambda: replace(job_manifest(Path("C:/repo")), maximum_concurrency=0),
        lambda: replace(job_manifest(Path("C:/repo")), network_allowed=True),
        lambda: JobRequest("", "key", (JobCapability.READ_REPOSITORY,), (), True, True),
        lambda: JobRequest("job", "key", (), (), True, True),
        lambda: JobRequest(
            "job",
            "key",
            (JobCapability.READ_REPOSITORY,),
            (Path("relative"),),
            True,
            True,
        ),
        lambda: JobAdmission("job", "key", True, ("BLOCKER",)),
        lambda: JobAdmission("job", "key", True, (), execution_allowed=True),
    ],
)
def test_job_contract_rejects_invalid_shapes(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_job_blocks_unlisted_capability(tmp_path: Path) -> None:
    request = JobRequest(
        "nightly-quality",
        "key",
        (JobCapability.RUN_FIXED_QUALITY_COMMANDS,),
        (),
        True,
        True,
    )
    restricted = replace(
        job_manifest(tmp_path),
        allowed_capabilities=(JobCapability.READ_REPOSITORY,),
    )
    assert assess_job_admission(restricted, request).blockers == (
        "JOB_CAPABILITY_NOT_ALLOWED",
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(advisory_trace(), trace_id=""),
        lambda: replace(advisory_trace(), input_sha256="bad"),
        lambda: replace(advisory_trace(), citations=("a", "a")),
        lambda: replace(advisory_trace(), started_at=datetime(2026, 7, 13)),
        lambda: replace(advisory_trace(), finished_at=NOW - timedelta(seconds=1)),
        lambda: replace(advisory_trace(), redacted=False),
        lambda: AdvisoryEvalExpectation("", (), (), 1),
        lambda: AdvisoryEvalExpectation("fixture", (), (), 0),
        lambda: AdvisoryEvalResult("trace", True, ("BLOCKER",)),
        lambda: AdvisoryEvalResult("trace", True, (), promotion_evidence=True),
    ],
)
def test_advisory_contract_rejects_invalid_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: WorkflowNode("", "TEST", (), (), (), 1, WorkflowAuthority.READ_ONLY),
        lambda: WorkflowNode("a", "TEST", (), (), (), 0, WorkflowAuthority.READ_ONLY),
        lambda: WorkflowNode(
            "a", "TEST", ("b", "b"), (), (), 1, WorkflowAuthority.READ_ONLY
        ),
        lambda: WorkflowNode(
            "a",
            "TEST",
            (),
            (),
            (),
            1,
            WorkflowAuthority.READ_ONLY,
            execution_allowed=True,
        ),
        lambda: WorkflowGraph("", (market_outlook_workflow().nodes[0],)),
        lambda: WorkflowGraph("graph", (market_outlook_workflow().nodes[0],) * 2),
        lambda: replace(market_outlook_workflow(), execution_allowed=True),
        lambda: WorkflowEdgeAudit(
            graph_id="",
            status=WorkflowEdgeAuditStatus.REAL_EDGES_VERIFIED,
            real_edges=(),
            fake_edges=(),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: WorkflowEdgeAudit(
            graph_id="graph",
            status=WorkflowEdgeAuditStatus.REAL_EDGES_VERIFIED,
            real_edges=("a->b",),
            fake_edges=("c->d",),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: WorkflowEdgeAudit(
            graph_id="graph",
            status=WorkflowEdgeAuditStatus.WATCHLIST,
            real_edges=(),
            fake_edges=("a->b",),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            audit_workflow_edges(opportunity_research_diamond_workflow()),
            execution_allowed=True,
        ),
        lambda: replace(graph_checkpoint("node"), input_artifact_sha256="bad"),
        lambda: replace(graph_checkpoint("node"), started_at=datetime(2026, 7, 13)),
        lambda: replace(graph_checkpoint("node"), retry_count=-1),
        lambda: replace(graph_checkpoint("node"), execution_allowed=True),
        lambda: replace(route_decision("node"), node_id=""),
        lambda: replace(route_decision("node"), input_artifact_sha256="bad"),
        lambda: replace(route_decision("node"), output_artifact_sha256="bad"),
        lambda: replace(route_decision("node"), citations=("same", "same")),
        lambda: replace(route_decision("node"), retry_count=-1),
        lambda: replace(
            route_decision("node", decision=GraphNodeRouteDecisionType.RETRY),
            target_node="",
        ),
        lambda: route_decision(
            "node",
            decision=GraphNodeRouteDecisionType.STOP,
            target_node="other",
        ),
        lambda: route_decision(
            "node",
            decision=GraphNodeRouteDecisionType.PASSED,
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(route_decision("node"), execution_allowed=True),
        lambda: replace(route_decision("node"), promotion_status="STAGED_CANDIDATE"),
        lambda: GraphNodeRouteReduction(
            graph_id="graph",
            run_id="run",
            expected_nodes=("node",),
            observed_nodes=("node",),
            missing_nodes=(),
            terminal_state=GraphRunTerminalState.COMPLETED,
            decisions=(route_decision("node", graph_id="graph", run_id="run"),),
            blockers=("LIVE_ORDER_BLOCKED",),
            max_cost_units=1,
            max_retry_count=0,
        ),
        lambda: replace(
            reduce_graph_node_route_decisions(
                opportunity_research_diamond_workflow(),
                run_id="run-1",
                decisions=tuple(
                    route_decision(node.node_id)
                    for node in opportunity_research_diamond_workflow().nodes
                ),
                max_cost_units=20,
                max_retry_count=1,
            ),
            execution_allowed=True,
        ),
        lambda: replace(
            architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
            workflow_id="",
        ),
        lambda: replace(
            architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
            artifact_sha256="bad",
        ),
        lambda: replace(
            architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
            citations=("same", "same"),
        ),
        lambda: replace(
            architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
            control_points=("audit", "AUDIT"),
        ),
        lambda: replace(
            architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
            blockers=("BLOCKER_WITHOUT_LIVE",),
        ),
        lambda: replace(
            architecture_layer_evidence(AgentArchitectureLayer.HARNESS),
            execution_allowed=True,
        ),
        lambda: AgentArchitectureLayerReduction(
            workflow_id="workflow",
            expected_layers=(AgentArchitectureLayer.HARNESS,),
            observed_layers=(AgentArchitectureLayer.HARNESS,),
            missing_layers=(),
            final_status=AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE,
            reviews=(
                architecture_layer_evidence(
                    AgentArchitectureLayer.HARNESS,
                    workflow_id="workflow",
                ),
            ),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            reduce_agent_architecture_layer_reviews(
                tuple(
                    architecture_layer_evidence(layer)
                    for layer in AGENT_ARCHITECTURE_LAYERS
                ),
                workflow_id="opportunity-research-diamond",
            ),
            execution_allowed=True,
        ),
        lambda: reduce_agent_architecture_layer_reviews(
            (),
            workflow_id="",
        ),
        lambda: reduce_agent_architecture_layer_reviews(
            (),
            workflow_id="workflow",
            expected_layers=(
                AgentArchitectureLayer.HARNESS,
                AgentArchitectureLayer.HARNESS,
            ),
        ),
        lambda: summarize_agent_architecture_coverage(
            reduce_agent_architecture_layer_reviews(
                tuple(
                    architecture_layer_evidence(layer)
                    for layer in AGENT_ARCHITECTURE_LAYERS
                ),
                workflow_id="opportunity-research-diamond",
            ),
            source_uri="https://x.com/marfinxx/status/2081687570488954915",
            source_sha256="bad",
        ),
        lambda: AgentArchitectureCoverageSummary(
            workflow_id="opportunity-research-diamond",
            source_uri="https://x.com/marfinxx/status/2081687570488954915",
            source_sha256=HASH,
            status=AgentArchitectureLayerStatus.RESEARCH_ONLY_ARCHITECTURE,
            covered_layers=(AgentArchitectureLayer.HARNESS,),
            missing_layers=(AgentArchitectureLayer.GRAPH,),
            missing_control_points=("GRAPH:topology",),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(
            summarize_agent_architecture_coverage(
                reduce_agent_architecture_layer_reviews(
                    tuple(
                        architecture_layer_evidence(layer)
                        for layer in AGENT_ARCHITECTURE_LAYERS
                    ),
                    workflow_id="opportunity-research-diamond",
                ),
                source_uri="https://x.com/marfinxx/status/2081687570488954915",
                source_sha256=HASH,
            ),
            execution_allowed=True,
        ),
        lambda: invocation_coverage_summary(prompt_sha256="bad"),
        lambda: AgentInvocationCoverageSummary(
            workflow_id="opportunity-research-diamond",
            source_uri="https://x.com/akshay_pachaar/status/2081089131808243999",
            source_sha256=HASH,
            status=AgentInvocationCoverageStatus.RESEARCH_ONLY_AGENT_INVOCATION,
            prompt_revision="",
            prompt_sha256="",
            context_sources=(),
            context_sha256="",
            context_freshness_policy="",
            citations=(),
            redaction_applied=False,
            private_context_detected=False,
            tool_output_verified=False,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(invocation_coverage_summary(), execution_allowed=True),
        lambda: GraphRunTrace(
            run_id="",
            graph_id="graph",
            terminal_state=GraphRunTerminalState.COMPLETED,
            checkpoints=(graph_checkpoint("node"),),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            max_cost_units=1,
            max_retry_count=0,
        ),
        lambda: GraphRunTrace(
            run_id="run-1",
            graph_id="graph",
            terminal_state=GraphRunTerminalState.COMPLETED,
            checkpoints=(graph_checkpoint("node"), graph_checkpoint("node")),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            max_cost_units=1,
            max_retry_count=0,
        ),
        lambda: GraphRunTrace(
            run_id="run-1",
            graph_id="graph",
            terminal_state=GraphRunTerminalState.COMPLETED,
            checkpoints=(graph_checkpoint("node", run_id="other"),),
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            max_cost_units=1,
            max_retry_count=0,
        ),
        lambda: GraphRunTrace(
            run_id="run-1",
            graph_id="graph",
            terminal_state=GraphRunTerminalState.COMPLETED,
            checkpoints=(graph_checkpoint("node"),),
            blockers=("LIVE_ORDER_BLOCKED",),
            max_cost_units=1,
            max_retry_count=0,
        ),
        lambda: replace(
            summarize_graph_run_trace(
                WorkflowGraph(
                    "graph",
                    (
                        WorkflowNode(
                            "node",
                            "NODE",
                            (),
                            (),
                            ("node.json",),
                            1,
                            WorkflowAuthority.READ_ONLY,
                        ),
                    ),
                ),
                run_id="run-1",
                checkpoints=(graph_checkpoint("node"),),
                max_cost_units=1,
                max_retry_count=0,
            ),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(model_candidate(), model_id=""),
        lambda: replace(model_candidate(), context_window_tokens=0),
        lambda: replace(model_candidate(), input_price_per_1m=-1.0),
        lambda: replace(model_candidate(), output_price_per_1m=float("nan")),
        lambda: replace(model_candidate(), citations=("same", "same")),
        lambda: replace(model_candidate(), execution_allowed=True),
        lambda: replace(model_candidate(), live_order_authority=True),
        lambda: replace(model_candidate(), trading_signal_authority=True),
        lambda: AgentModelCandidateReview(
            model_id="kimi-k3",
            provider="moonshot-ai",
            status=AgentModelCandidateStatus.RESEARCH_ONLY_PROVIDER,
            context_window_tokens=1_048_576,
            input_price_per_1m=3.0,
            cached_input_price_per_1m=0.3,
            output_price_per_1m=15.0,
            tool_call_support=True,
            json_mode_support=True,
            data_privacy_boundary="external_api_research_only_no_secrets",
            citations=("https://www.kimi.com/resources/kimi-k3-pricing",),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            review_agent_model_candidate(model_candidate()),
            blockers=(
                "PROVIDER_BENCHMARK_SELF_REPORTED",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        ),
        lambda: replace(
            review_agent_model_candidate(model_candidate()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            review_agent_model_candidate(model_candidate()),
            execution_allowed=True,
        ),
        lambda: replace(skill_candidate(), skill_id="nested/skill"),
        lambda: replace(skill_candidate(), source_uri=""),
        lambda: replace(skill_candidate(), source_sha256="bad"),
        lambda: replace(skill_candidate(), declared_goal=""),
        lambda: replace(skill_candidate(), citations=("same", "same")),
        lambda: replace(skill_candidate(), reviewer_result=""),
        lambda: replace(skill_candidate(), promotion_status="STAGED_CANDIDATE"),
        lambda: replace(skill_candidate(), execution_allowed=True),
        lambda: replace(skill_candidate(), live_order_authority=True),
        lambda: AgentSkillCandidateReview(
            skill_id="agent-skill-authoring",
            source_uri="https://x.com/free_ai_guides/status/2071666929451094227",
            source_sha256=HASH,
            declared_goal="Turn cited agent-skill guidance into a reusable workflow.",
            status=AgentSkillCandidateStatus.RESEARCH_ONLY_SKILL,
            trigger_conditions=("external agent skill guidance is proposed",),
            allowed_inputs=("source uri",),
            required_references=(
                ".agents/skills/ai4binance-validation-first/SKILL.md",
            ),
            declared_tools=(),
            script_paths=(),
            expected_output_contract=("RESEARCH_ONLY_SKILL",),
            review_checklist=("citation present",),
            test_command=(
                ".\\.venv\\Scripts\\python.exe -m pytest "
                "tests\\test_agent_runtime_governance.py --no-cov -q"
            ),
            citations=("https://x.com/free_ai_guides/status/2071666929451094227",),
            blockers=("HUMAN_REVIEW_REQUIRED",),
            reviewer_result="PASSED",
        ),
        lambda: replace(
            review_agent_skill_candidate(skill_candidate()),
            blockers=(
                "SKILL_SCRIPT_REVIEW_REQUIRED",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        ),
        lambda: replace(
            review_agent_skill_candidate(skill_candidate()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            review_agent_skill_candidate(skill_candidate()),
            execution_allowed=True,
        ),
        lambda: replace(workspace_component(), component_id=""),
        lambda: replace(workspace_component(), source_path="C:/outside/SKILL.md"),
        lambda: replace(workspace_component(), content_sha256="bad"),
        lambda: replace(workspace_component(), citations=("same", "same")),
        lambda: replace(
            workspace_component(),
            canary_expected_blockers=("LIVE_ORDER_BLOCKED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(workspace_component(), execution_allowed=True),
        lambda: replace(workspace_component(), live_order_authority=True),
        lambda: AgentWorkspaceComponentReview(
            component_id="component",
            component_type=AgentWorkspaceComponentType.SKILL,
            source_path=".agents/skills/example/SKILL.md",
            content_sha256=HASH,
            status=AgentWorkspaceComponentStatus.RESEARCH_ONLY_WORKSPACE,
            declared_authority="RESEARCH_ONLY",
            canary_command="pytest -q",
            canary_expected_blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            citations=("artifact://.agents/skills/example/SKILL.md",),
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            review_agent_workspace_component(workspace_component()),
            blockers=(
                "WORKSPACE_CANARY_NOT_RUN",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        ),
        lambda: replace(
            review_agent_workspace_component(workspace_component()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            review_agent_workspace_component(workspace_component()),
            execution_allowed=True,
        ),
        lambda: replace(markdown_governance_artifact(), artifact_id=""),
        lambda: replace(markdown_governance_artifact(), source_path="Docs/readme.txt"),
        lambda: replace(markdown_governance_artifact(), source_path="../README.md"),
        lambda: replace(markdown_governance_artifact(), content_sha256="bad"),
        lambda: replace(markdown_governance_artifact(), citations=("same", "same")),
        lambda: replace(markdown_governance_artifact(), execution_allowed=True),
        lambda: replace(markdown_governance_artifact(), live_order_authority=True),
        lambda: MarkdownGovernanceArtifactReview(
            artifact_id="doc",
            source_path="Docs/ARCHITECTURE.md",
            content_sha256=HASH,
            role=MarkdownGovernanceArtifactRole.ARCHITECTURE,
            status=MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION,
            reviewer_result=MarkdownGovernanceReviewerResult.PASSED,
            declared_authority="RESEARCH_ONLY",
            citations=("artifact://Docs/ARCHITECTURE.md",),
            owner="architecture-reviewer",
            freshness_policy="Re-review after workflow changes.",
            canonical_source_path="",
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            review_markdown_governance_artifact(markdown_governance_artifact()),
            blockers=(
                "MARKDOWN_CITATION_REQUIRED",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        ),
        lambda: replace(
            review_markdown_governance_artifact(markdown_governance_artifact()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            review_markdown_governance_artifact(markdown_governance_artifact()),
            execution_allowed=True,
        ),
        lambda: MarkdownGovernanceReviewReduction(
            expected_artifacts=("doc",),
            observed_artifacts=("doc",),
            missing_artifacts=(),
            final_status=MarkdownGovernanceReviewStatus.RESEARCH_ONLY_DOCUMENTATION,
            blockers=("LIVE_ORDER_BLOCKED",),
            reviews=(
                review_markdown_governance_artifact(markdown_governance_artifact()),
            ),
        ),
        lambda: replace(
            reduce_markdown_governance_reviews(
                (review_markdown_governance_artifact(markdown_governance_artifact()),),
                expected_artifacts=("architecture-md",),
            ),
            execution_allowed=True,
        ),
        lambda: replace(closed_loop_evidence(), loop_id=""),
        lambda: replace(closed_loop_evidence(), max_iterations=0),
        lambda: replace(closed_loop_evidence(), max_cost_units=0),
        lambda: replace(closed_loop_evidence(), allowed_tools=("pytest", "pytest")),
        lambda: replace(closed_loop_evidence(), allowed_write_roots=("C:/outside",)),
        lambda: replace(closed_loop_evidence(), execution_allowed=True),
        lambda: replace(closed_loop_evidence(), live_order_authority=True),
        lambda: ClosedLoopAdmission(
            loop_id="loop",
            task="task",
            trigger="manual",
            selected_pattern="human-in-the-loop",
            loop_type=AgentLoopType.CLOSED,
            loop_scale=AgentLoopScale.SINGLE_AGENT,
            status=ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP,
            blockers=("LIVE_ORDER_BLOCKED",),
            allowed_tools=("pytest",),
            allowed_write_roots=(),
            memory_sources=("README.md",),
            verifier_identity="verifier",
            artifact_log_uri="Artifacts/loops/loop.jsonl",
            stop_conditions=("max_iterations_reached",),
            max_iterations=1,
            max_cost_units=1,
        ),
        lambda: replace(
            admit_closed_loop(closed_loop_evidence()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            admit_closed_loop(closed_loop_evidence()),
            execution_allowed=True,
        ),
        lambda: replace(closed_loop_run_evidence(), run_id=""),
        lambda: replace(closed_loop_run_evidence(), iteration_count=-1),
        lambda: replace(closed_loop_run_evidence(), started_at=datetime(2026, 7, 13)),
        lambda: replace(
            closed_loop_run_evidence(),
            finished_at=NOW - timedelta(seconds=1),
        ),
        lambda: replace(closed_loop_run_evidence(), blockers=("BLOCKER", "BLOCKER")),
        lambda: replace(closed_loop_run_evidence(), execution_allowed=True),
        lambda: replace(closed_loop_run_evidence(), live_order_authority=True),
        lambda: ClosedLoopRunSummary(
            loop_id="loop",
            run_id="run",
            trigger_type=ClosedLoopRunTriggerType.GOAL,
            status=ClosedLoopAdmissionStatus.RESEARCH_ONLY_LOOP,
            state_uri="Artifacts/loops/loop.state.json",
            resume_point="queue:next",
            verifier_identity="verifier",
            iteration_count=1,
            cost_units=1,
            blockers=("LIVE_ORDER_BLOCKED",),
        ),
        lambda: replace(
            summarize_closed_loop_run(closed_loop_run_evidence()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            summarize_closed_loop_run(closed_loop_run_evidence()),
            execution_allowed=True,
        ),
        lambda: GraphArchitectureReadinessEvidence(
            workflow_id="other",
            selected_pattern="routing",
            graph=market_outlook_workflow(),
            reviewer_nodes=(),
            anchor_artifacts=(),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            independent_reviewers=False,
            deterministic_reducer=False,
        ),
        lambda: GraphArchitectureReadinessEvidence(
            workflow_id=market_outlook_workflow().graph_id,
            selected_pattern="routing",
            graph=market_outlook_workflow(),
            reviewer_nodes=("missing",),
            anchor_artifacts=(),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            independent_reviewers=False,
            deterministic_reducer=False,
        ),
        lambda: GraphArchitectureReadinessEvidence(
            workflow_id=market_outlook_workflow().graph_id,
            selected_pattern="routing",
            graph=market_outlook_workflow(),
            reviewer_nodes=(),
            anchor_artifacts=("same", "same"),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            independent_reviewers=False,
            deterministic_reducer=False,
        ),
        lambda: GraphArchitectureReadinessEvidence(
            workflow_id=market_outlook_workflow().graph_id,
            selected_pattern="routing",
            graph=market_outlook_workflow(),
            reviewer_nodes=(),
            anchor_artifacts=(),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            independent_reviewers=False,
            deterministic_reducer=False,
            llm_signal_authority=True,
        ),
        lambda: GraphArchitectureReadinessReview(
            workflow_id="graph",
            selected_pattern="routing",
            status=GraphArchitectureReadinessStatus.RESEARCH_ONLY_GRAPH_PATTERN,
            blockers=("LIVE_ORDER_BLOCKED",),
            reviewer_nodes=(),
            anchor_artifacts=(),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            trace_artifacts=(),
        ),
        lambda: GraphArchitectureReadinessReview(
            workflow_id="graph",
            selected_pattern="routing",
            status=GraphArchitectureReadinessStatus.RESEARCH_ONLY_GRAPH_PATTERN,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            reviewer_nodes=(),
            anchor_artifacts=(),
            counter_metrics=(),
            human_gate_nodes=(),
            reducer_nodes=(),
            trace_artifacts=(),
            execution_allowed=True,
        ),
        lambda: replace(graph_manifest(), workflow_id=""),
        lambda: replace(graph_manifest(), edges=(("a", "b"), ("a", "b"))),
        lambda: replace(graph_manifest(), state_schema_hash="bad"),
        lambda: replace(graph_manifest(), parallelism_cap=0),
        lambda: replace(graph_manifest(), execution_allowed=True),
        lambda: GraphWorkflowManifestReview(
            workflow_id="graph",
            selected_pattern="routing",
            status=GraphWorkflowManifestReviewStatus.RESEARCH_ONLY_GRAPH_WORKFLOW,
            blockers=("LIVE_ORDER_BLOCKED",),
            nodes=("a",),
            edges=(),
            cycles_allowed=False,
            parallelism_cap=1,
            expected_artifacts=("artifact.json",),
            verifier_nodes=("a",),
            human_gate_nodes=("a",),
            state_schema_hash=HASH,
            authority_flags=("READ_ONLY",),
        ),
        lambda: replace(
            review_graph_workflow_manifest(graph_manifest()),
            promotion_status="STAGED_CANDIDATE",
        ),
        lambda: replace(
            review_graph_workflow_manifest(graph_manifest()),
            live_eligibility_status="PAPER_APPROVED",
        ),
        lambda: replace(loop_evidence(), loop_id=""),
        lambda: replace(loop_evidence(), max_iterations=0),
        lambda: replace(loop_evidence(), max_cost_units=0),
        lambda: replace(
            loop_evidence(),
            stop_conditions=("max_iterations_reached", "max_iterations_reached"),
        ),
        lambda: replace(loop_evidence(), allowed_write_roots=("C:/outside",)),
        lambda: replace(loop_evidence(), model_can_self_promote=True),
        lambda: replace(loop_evidence(), live_order_authority=True),
        lambda: loop_building_block_coverage_summary(cost_budget=-1),
        lambda: LoopBuildingBlockCoverageSummary(
            loop_id="research-quality-loop-v1",
            automation_trigger="",
            worktree_isolation=False,
            skills_declared=(),
            connectors_declared=(),
            subagent_roles=(),
            memory_sources=(),
            cost_budget=0,
            stop_conditions=(),
            human_handoff=False,
            status=LoopBuildingBlockCoverageStatus.RESEARCH_ONLY_LOOP,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(loop_building_block_coverage_summary(), execution_allowed=True),
        lambda: evaluator_gate_review(source_sha256="bad"),
        lambda: evaluator_gate_review(human_disagreement_rate=-0.1),
        lambda: EvaluatorGateReview(
            workflow_id="opportunity-research-diamond",
            source_uri="https://x.com/hanakoxbt/status/2083540339147567268",
            source_sha256=HASH,
            status=EvaluatorGateStatus.RESEARCH_ONLY_EVALUATOR_GATE,
            generator_model_family="gpt",
            judge_model_family="gpt",
            judge_version="",
            rubric_hash=HASH,
            rubric_text="Pass on independently observable outcomes.",
            deterministic_checks=(),
            trajectory_checks=(),
            faithfulness_result="FAILED",
            task_completion_result="FAILED",
            verifier_canary_passed=False,
            blast_radius_lane=EvaluatorGateBlastRadiusLane.HARD_TO_REVERSE,
            human_disagreement_rate=0.5,
            agent_self_assessment_weight=0.5,
            shadow_mode=False,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            trading_scope_touched=True,
        ),
        lambda: replace(evaluator_gate_review(), execution_allowed=True),
        lambda: residual_edge_review(source_sha256="bad"),
        lambda: residual_edge_review(fees_bps=-1.0),
        lambda: ResidualEdgeReview(
            workflow_id="opportunity-research-diamond",
            source_uri="https://x.com/0xkvro/status/2074815948062650819",
            source_sha256=HASH,
            status=ResidualEdgeReviewStatus.RESEARCH_ONLY_RESIDUAL_EDGE,
            raw_return=0.01,
            market_component=0.01,
            sector_or_universe_component=0.0,
            factor_component=0.0,
            liquidity_component=0.0,
            residual_return=0.0,
            residual_zscore=0.2,
            expected_value_after_costs=-0.001,
            sample_size=5,
            independent_repetition_count=1,
            fees_bps=7.5,
            slippage_bps=4.0,
            capacity_warning=True,
            regime_split=(),
            signal_decay_check="FAILED",
            data_leakage_check="FAILED",
            sizing_status="UNVALIDATED",
            oos_validation_present=False,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            trading_scope_touched=True,
        ),
        lambda: replace(residual_edge_review(), execution_allowed=True),
        lambda: cowork_task_suitability_review(source_sha256="bad"),
        lambda: CoworkTaskSuitabilityReview(
            workflow_id="opportunity-research-diamond",
            source_uri="https://x.com/ridark_eth/status/2072666887276618071",
            source_sha256=HASH,
            status=CoworkTaskSuitabilityStatus.RESEARCH_ONLY_COWORK_TASK,
            task_id="daily-research-digest",
            touches_files_apps_or_web=True,
            tedious_repetitive_or_multistep=True,
            done_is_checkable=False,
            mistake_is_survivable=False,
            brain_file_present=False,
            skill_declared=False,
            connector_scope=("all",),
            schedule_requested=True,
            manual_run_verified=False,
            draft_only=False,
            human_approval_required=False,
            judgment_required=True,
            secret_access_requested=True,
            trading_scope_touched=True,
            money_movement_touched=True,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(cowork_task_suitability_review(), execution_allowed=True),
        lambda: trajectory_learning_eligibility_review(source_sha256="bad"),
        lambda: trajectory_learning_eligibility_review(trajectory_hash="bad"),
        lambda: AgentTrajectoryLearningEligibilityReview(
            workflow_id="opportunity-research-diamond",
            source_uri="https://arxiv.org/abs/2607.01120v2",
            source_sha256=HASH,
            status=AgentTrajectoryLearningEligibilityStatus.RESEARCH_ONLY_TRAJECTORY_LEARNING,
            trajectory_id="research-trace-001",
            trajectory_hash=HASH,
            replay_class="NON_REPLAYABLE",
            privacy_classification="INTERNAL_REDACTED",
            redaction_status="RAW",
            reward_signal="NONE",
            intervention_candidate="MODEL_WEIGHT_UPDATE",
            tool_schema_version="tool-schema-v1",
            retrieval_snapshot_id="retrieval-snapshot-001",
            harness_fingerprint="harness-v1",
            model_id="advisory-local",
            causal_step_count=0,
            delayed_reward_supported=False,
            provenance_versioned=False,
            governance_metadata_present=False,
            human_correction_present=False,
            training_eligible=False,
            secret_risk_detected=True,
            trading_scope_touched=True,
            money_movement_touched=True,
            model_weight_update_requested=True,
            blockers=(
                "MODEL_UPDATE_BLOCKED",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        ),
        lambda: replace(
            trajectory_learning_eligibility_review(), execution_allowed=True
        ),
        lambda: graph_dependency_integrity_review(source_sha256="bad"),
        lambda: GraphDependencyIntegrityReview(
            workflow_id="opportunity-research-diamond",
            source_uri="https://x.com/rvaniaaaa/status/2083577068374085960",
            source_sha256=HASH,
            status=GraphDependencyIntegrityStatus.RESEARCH_ONLY_GRAPH_DEPENDENCY,
            graph_id="opportunity-research-diamond-v1",
            expected_nodes=("plan", "market", "risk", "verifier"),
            observed_nodes=("plan", "market", "verifier"),
            missing_nodes=("risk",),
            declared_edges=("plan->market", "risk->verifier"),
            data_carrying_edges=("plan->market",),
            fake_edges=("risk->verifier",),
            fanout_width=1,
            barrier_count=0,
            verifier_context_isolated=False,
            anchor_artifacts=(),
            merge_input_count_verified=False,
            model_tiering_policy_present=False,
            cost_cap_present=False,
            silent_node_failure_count=1,
            trading_scope_touched=True,
            money_movement_touched=True,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
        ),
        lambda: replace(graph_dependency_integrity_review(), execution_allowed=True),
        lambda: LoopEngineeringReadinessReview(
            loop_id="loop",
            task="task",
            selected_pattern="pattern",
            status=LoopEngineeringReadinessStatus.RESEARCH_ONLY_LOOP_PATTERN,
            blockers=("LIVE_ORDER_BLOCKED",),
            objective_metric="metric",
            stop_conditions=("max_iterations_reached",),
            before_after_metrics=("coverage_percent",),
            artifact_log_uri="Artifacts/loops/loop.jsonl",
            holdout_artifact_uri="Backtest/holdout/report.json",
            oos_artifact_uri="Backtest/oos/report.json",
        ),
        lambda: replace(
            review_loop_engineering_readiness(loop_evidence()),
            execution_allowed=True,
        ),
        lambda: replace(branch_review("market_outlook_branch"), content_sha256="bad"),
        lambda: replace(branch_review("market_outlook_branch"), citations=()),
        lambda: replace(
            branch_review("market_outlook_branch"),
            blockers=("BLOCKER",),
        ),
        lambda: replace(
            branch_review("market_outlook_branch"),
            live_eligibility_status="LIVE_ELIGIBLE",
        ),
        lambda: OpportunityArtifactReviewReduction(
            OPPORTUNITY_RESEARCH_BRANCH_IDS,
            OPPORTUNITY_RESEARCH_BRANCH_IDS,
            (),
            OpportunityArtifactReductionStatus.RESEARCH_ONLY_OPPORTUNITY,
            (),
            tuple(branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS),
        ),
        lambda: replace(
            reduce_opportunity_artifact_reviews(
                tuple(
                    branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS
                ),
                supporting_workspace_reviews=(
                    review_agent_workspace_component(workspace_component()),
                ),
                expected_workspace_components=("ai4binance-validation-first",),
            ),
            observed_workspace_components=(),
        ),
        lambda: replace(
            reduce_opportunity_artifact_reviews(
                tuple(
                    branch_review(branch) for branch in OPPORTUNITY_RESEARCH_BRANCH_IDS
                )
            ),
            execution_allowed=True,
        ),
    ],
)
def test_workflow_contract_rejects_invalid_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_learning_summary_stages_only_unapproved_lessons() -> None:
    summary = LearningSummary(
        summary_id="summary-1",
        created_at=NOW,
        lessons=(LessonCandidate("WEAK_OOS", 2, "Needs validation"),),
        experiments=(),
    )
    staged = stage_learning_summary(summary, expires_at=NOW + timedelta(days=30))
    assert len(staged) == 1
    assert staged[0].status is LessonStatus.OBSERVED
    assert staged[0].source_artifact_ids == ("summary-1",)
    assert staged[0].execution_allowed is False


def test_nightly_quality_manifest_matches_existing_safe_loop(tmp_path: Path) -> None:
    manifest = nightly_quality_job_manifest(tmp_path, tmp_path / "artifacts")
    assert manifest.maximum_concurrency == 1
    assert manifest.network_allowed is False
    assert manifest.secret_access_allowed is False
    assert manifest.trading_authority is False
    with pytest.raises(ValueError, match="absolute"):
        nightly_quality_job_manifest(Path("relative"), tmp_path)


def sidecar_evidence(
    *,
    localhost_bound: bool = True,
    authentication_enabled: bool = True,
    ssrf_protection_enabled: bool = True,
    external_network_disabled: bool = True,
    arbitrary_code_disabled: bool = True,
    read_only_artifacts: bool = True,
    resource_limits_enabled: bool = True,
    secrets_mounted: bool = False,
    exchange_adapter_present: bool = False,
) -> SidecarPilotEvidence:
    return SidecarPilotEvidence(
        component_id="langflow-isolated-pilot",
        image_digest=f"sha256:{HASH}",
        localhost_bound=localhost_bound,
        authentication_enabled=authentication_enabled,
        ssrf_protection_enabled=ssrf_protection_enabled,
        external_network_disabled=external_network_disabled,
        arbitrary_code_disabled=arbitrary_code_disabled,
        read_only_artifacts=read_only_artifacts,
        resource_limits_enabled=resource_limits_enabled,
        secrets_mounted=secrets_mounted,
        exchange_adapter_present=exchange_adapter_present,
    )


def test_sidecar_pilot_is_default_deny_and_read_only() -> None:
    allowed = assess_sidecar_pilot(sidecar_evidence())
    assert allowed.pilot_allowed is True
    assert allowed.read_only is True
    assert allowed.execution_allowed is False
    assert allowed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    blocked = assess_sidecar_pilot(
        sidecar_evidence(
            localhost_bound=False,
            authentication_enabled=False,
            ssrf_protection_enabled=False,
            external_network_disabled=False,
            arbitrary_code_disabled=False,
            read_only_artifacts=False,
            resource_limits_enabled=False,
            secrets_mounted=True,
            exchange_adapter_present=True,
        )
    )
    assert blocked.pilot_allowed is False
    assert len(blocked.blockers) == 9


def test_sidecar_contract_rejects_unpinned_or_authorized_shapes() -> None:
    with pytest.raises(ValueError, match="digest"):
        replace(sidecar_evidence(), image_digest="latest")
    with pytest.raises(ValueError, match="disagree"):
        SidecarPilotAssessment("langflow", True, ("BLOCKER",))
    with pytest.raises(ValueError, match="read-only"):
        SidecarPilotAssessment("langflow", True, (), execution_allowed=True)

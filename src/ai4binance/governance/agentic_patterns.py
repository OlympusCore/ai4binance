"""Governed agentic workflow pattern selection contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgenticPatternId(StrEnum):
    PROMPT_CHAINING = "prompt_chaining"
    PARALLELIZATION = "parallelization"
    ORCHESTRATOR_WORKER = "orchestrator_worker"
    EVALUATOR_OPTIMIZER = "evaluator_optimizer"
    ROUTING = "routing"
    AUTONOMOUS_WORKFLOW = "autonomous_workflow"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    REFLECTION = "reflection"
    MULTI_AGENT_DEBATE = "multi_agent_debate"


class AgenticRiskDomain(StrEnum):
    GENERAL = "general"
    FINANCE = "finance"
    TRADING = "trading"
    LEGAL = "legal"
    MEDICAL = "medical"
    HIRING = "hiring"
    CUSTOMER_PROMISE = "customer_promise"
    CODE_DEPLOYMENT = "code_deployment"
    SECURITY = "security"


HIGH_RISK_DOMAINS = frozenset(
    {
        AgenticRiskDomain.FINANCE,
        AgenticRiskDomain.TRADING,
        AgenticRiskDomain.LEGAL,
        AgenticRiskDomain.MEDICAL,
        AgenticRiskDomain.HIRING,
        AgenticRiskDomain.CUSTOMER_PROMISE,
        AgenticRiskDomain.CODE_DEPLOYMENT,
        AgenticRiskDomain.SECURITY,
    }
)


@dataclass(frozen=True, slots=True)
class AgenticPatternDefinition:
    pattern_id: AgenticPatternId
    display_name: str
    role: str
    use_when: tuple[str, ...]
    required_inputs: tuple[str, ...]
    stopping_rule: str
    review_rule: str
    bounded_authority: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.display_name.strip() or not self.role.strip():
            raise ValueError("agentic pattern identity is required")
        for values in (self.use_when, self.required_inputs):
            if not values or len(set(values)) != len(values):
                raise ValueError("agentic pattern lists must be non-empty and unique")
            if any(not value.strip() for value in values):
                raise ValueError("agentic pattern lists cannot contain blanks")
        if not self.stopping_rule.strip() or not self.review_rule.strip():
            raise ValueError("agentic pattern requires stop and review rules")
        if self.bounded_authority != "RESEARCH_ONLY":
            raise ValueError("agentic patterns cannot promote beyond research")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("agentic patterns cannot authorize execution")


@dataclass(frozen=True, slots=True)
class AgenticSkillPlan:
    task_name: str
    selected_pattern: AgenticPatternDefinition
    input_contract: tuple[str, ...]
    stopping_point: str
    review_rule: str
    measurement_plan: tuple[str, ...]
    blockers: tuple[str, ...]
    escalation_required: bool
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.task_name.strip():
            raise ValueError("agentic skill plan task name is required")
        for values in (self.input_contract, self.measurement_plan, self.blockers):
            if len(set(values)) != len(values):
                raise ValueError("agentic skill plan lists must be unique")
            if any(not value.strip() for value in values):
                raise ValueError("agentic skill plan lists cannot contain blanks")
        if not self.stopping_point.strip() or not self.review_rule.strip():
            raise ValueError("agentic skill plan requires stop and review rules")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("agentic skill plans cannot promote or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agentic skill plans must remain live blocked")


def build_default_agentic_pattern_catalog() -> tuple[AgenticPatternDefinition, ...]:
    """Return the nine inspectable workflow patterns in stable order."""
    return (
        AgenticPatternDefinition(
            AgenticPatternId.PROMPT_CHAINING,
            "Prompt Chaining",
            "assembly_line",
            ("work_has_ordered_stages", "each_stage_consumes_previous_output"),
            ("task", "ordered_steps", "stage_acceptance_checks"),
            "stop after the final stage passes its acceptance check",
            "review each stage boundary before using its output downstream",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.PARALLELIZATION,
            "Parallelization",
            "search_party",
            ("checks_are_independent", "merge_order_can_be_deterministic"),
            ("task", "independent_checks", "merge_rule"),
            "stop after every independent branch returns or times out",
            "merge by stable key and record missing branches as blockers",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.ORCHESTRATOR_WORKER,
            "Orchestrator-Worker",
            "project_manager",
            (
                "one_planner_assigns_specialized_subtasks",
                "workers_have_least_privilege_scopes",
            ),
            ("task", "worker_roles", "dependency_graph"),
            "stop after the orchestrator receives all required worker outputs",
            "validate worker outputs against schemas before synthesis",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.EVALUATOR_OPTIMIZER,
            "Evaluator-Optimizer",
            "editor",
            ("quality_rubric_exists", "iteration_budget_is_bounded"),
            ("draft", "rubric", "iteration_budget"),
            "stop when the rubric passes or the repair budget is exhausted",
            "record critique, revision and unresolved blockers",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.ROUTING,
            "Routing",
            "switchboard",
            ("inputs_need_different_paths", "classification_schema_is_known"),
            ("input", "route_taxonomy", "fallback_route"),
            "stop after one route is selected with a fallback on ambiguity",
            "review ambiguous or high-risk routes before action",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.AUTONOMOUS_WORKFLOW,
            "Autonomous Workflow",
            "bounded_machine",
            ("rules_are_clear", "actions_are_bounded", "downside_is_controlled"),
            ("task", "allowed_actions", "stop_conditions", "rollback_plan"),
            "stop at the first failed gate, timeout or completed bounded action",
            "require admission checks and audit records before every action",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.HUMAN_IN_THE_LOOP,
            "Human-in-the-loop",
            "safety_gate",
            (
                "domain_is_high_risk",
                "promise_or_deployment_requires_owner_approval",
            ),
            ("task", "risk_threshold", "approver", "approval_record"),
            "stop at human review unless explicit approval is recorded",
            "block legal, finance, hiring, medical, customer promises and deploys",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.REFLECTION,
            "Reflection",
            "second_look",
            (
                "first_answer_may_miss_assumptions",
                "edge_cases_or_weak_evidence_are_likely",
            ),
            ("draft", "assumption_list", "edge_case_checklist"),
            "stop after assumptions, gaps and revisions are recorded",
            "separate first answer evidence from second-look critique",
        ),
        AgenticPatternDefinition(
            AgenticPatternId.MULTI_AGENT_DEBATE,
            "Multi-agent Debate",
            "pressure_test",
            (
                "decision_benefits_from_opposing_views",
                "roles_have_clear_perspectives",
            ),
            ("decision", "role_set", "judge_rubric"),
            "stop after each role argues and the judge records unresolved disputes",
            "treat debate as advisory pressure test, not execution authority",
        ),
    )


def recommend_agentic_skill_plan(
    *,
    task_name: str,
    risk_domain: str = "general",
    independent_checks: int = 0,
    requires_human_review: bool = False,
    stages: int = 0,
    needs_routing: bool = False,
    quality_sensitive: bool = False,
    bounded_actions: bool = False,
    downside_controlled: bool = False,
    opposing_views: bool = False,
) -> AgenticSkillPlan:
    """Choose one pattern without widening execution authority."""
    if independent_checks < 0 or stages < 0:
        raise ValueError("agentic planning counts cannot be negative")
    domain = _normalize_risk_domain(risk_domain)
    inferred = _infer_task_flags(task_name)
    high_risk = domain in HIGH_RISK_DOMAINS
    catalog = {
        item.pattern_id: item for item in build_default_agentic_pattern_catalog()
    }
    pattern_id = _select_pattern(
        high_risk=high_risk,
        requires_human_review=requires_human_review,
        independent_checks=independent_checks,
        stages=stages,
        needs_routing=needs_routing or inferred["needs_routing"],
        quality_sensitive=quality_sensitive or inferred["quality_sensitive"],
        bounded_actions=bounded_actions or inferred["bounded_actions"],
        downside_controlled=downside_controlled,
        opposing_views=opposing_views or inferred["opposing_views"],
    )
    return AgenticSkillPlan(
        task_name=task_name.strip(),
        selected_pattern=catalog[pattern_id],
        input_contract=(
            "name_the_task",
            "define_inputs",
            "define_stopping_point",
            "define_review_rule",
            "define_before_after_measure",
        ),
        stopping_point=catalog[pattern_id].stopping_rule,
        review_rule=catalog[pattern_id].review_rule,
        measurement_plan=(
            "baseline_error_or_cycle_time",
            "post_workflow_error_or_cycle_time",
            "blocker_count",
            "human_review_outcome",
        ),
        blockers=_plan_blockers(
            pattern_id,
            high_risk=high_risk,
            bounded_actions=bounded_actions or inferred["bounded_actions"],
            downside_controlled=downside_controlled,
        ),
        escalation_required=high_risk or requires_human_review,
    )


def _normalize_risk_domain(value: str) -> AgenticRiskDomain:
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "customer": AgenticRiskDomain.CUSTOMER_PROMISE,
        "customer_support": AgenticRiskDomain.CUSTOMER_PROMISE,
        "deployment": AgenticRiskDomain.CODE_DEPLOYMENT,
        "code": AgenticRiskDomain.CODE_DEPLOYMENT,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return AgenticRiskDomain(normalized or "general")
    except ValueError:
        return AgenticRiskDomain.GENERAL


def _infer_task_flags(task_name: str) -> dict[str, bool]:
    text = task_name.casefold()
    return {
        "needs_routing": any(
            token in text
            for token in ("complaint", "ticket", "lead", "classify", "route")
        ),
        "quality_sensitive": any(
            token in text for token in ("draft", "policy", "tone", "evaluate")
        ),
        "bounded_actions": any(
            token in text for token in ("sync", "archive", "refresh", "cleanup")
        ),
        "opposing_views": any(
            token in text for token in ("debate", "cfo", "buyer", "operator")
        ),
    }


def _select_pattern(
    *,
    high_risk: bool,
    requires_human_review: bool,
    independent_checks: int,
    stages: int,
    needs_routing: bool,
    quality_sensitive: bool,
    bounded_actions: bool,
    downside_controlled: bool,
    opposing_views: bool,
) -> AgenticPatternId:
    if high_risk or requires_human_review:
        return AgenticPatternId.HUMAN_IN_THE_LOOP
    if opposing_views:
        return AgenticPatternId.MULTI_AGENT_DEBATE
    if needs_routing:
        return AgenticPatternId.ROUTING
    if independent_checks >= 2:
        return AgenticPatternId.PARALLELIZATION
    if quality_sensitive:
        return AgenticPatternId.EVALUATOR_OPTIMIZER
    if stages >= 2:
        return AgenticPatternId.PROMPT_CHAINING
    if bounded_actions and downside_controlled:
        return AgenticPatternId.AUTONOMOUS_WORKFLOW
    if bounded_actions:
        return AgenticPatternId.ORCHESTRATOR_WORKER
    return AgenticPatternId.REFLECTION


def _plan_blockers(
    pattern_id: AgenticPatternId,
    *,
    high_risk: bool,
    bounded_actions: bool,
    downside_controlled: bool,
) -> tuple[str, ...]:
    blockers = ["LIVE_ORDER_BLOCKED"]
    if high_risk:
        blockers.append("HUMAN_REVIEW_REQUIRED")
    if pattern_id is AgenticPatternId.AUTONOMOUS_WORKFLOW and not (
        bounded_actions and downside_controlled
    ):
        blockers.append("AUTONOMOUS_WORKFLOW_NOT_BOUNDED")
    if pattern_id is not AgenticPatternId.AUTONOMOUS_WORKFLOW and bounded_actions:
        blockers.append("AUTONOMOUS_EXECUTION_NOT_SELECTED")
    return tuple(dict.fromkeys(blockers))

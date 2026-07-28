"""Fail-closed crew, workflow and local-LLM orchestration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CrewAuthority(StrEnum):
    READ_ONLY = "READ_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_PROPOSAL = "PAPER_PROPOSAL"


class CrewCadence(StrEnum):
    ON_DEMAND = "ON_DEMAND"
    DAILY = "DAILY"
    BIWEEKLY = "BIWEEKLY"


class CrewPlanStatus(StrEnum):
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class CrewRoleDefinition:
    role_id: str
    display_name: str
    authority: CrewAuthority
    responsibilities: tuple[str, ...]
    may_call_local_llm: bool = False
    may_retrieve_context: bool = False
    may_emit_signal_opportunity: bool = False
    may_mutate_parameters: bool = False
    may_emit_trading_signal: bool = False
    may_submit_orders: bool = False

    def __post_init__(self) -> None:
        if not self.role_id.strip() or not self.display_name.strip():
            raise ValueError("crew role identity is required")
        if not self.responsibilities or len(set(self.responsibilities)) != len(
            self.responsibilities
        ):
            raise ValueError("crew role responsibilities must be non-empty and unique")
        if (
            self.may_mutate_parameters
            or self.may_emit_trading_signal
            or self.may_submit_orders
        ):
            raise ValueError("crew roles cannot receive trading authority")


@dataclass(frozen=True, slots=True)
class EngineBinding:
    engine_id: str
    engine_type: str
    provider: str
    authority: CrewAuthority
    loopback_only: bool
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.engine_id.strip()
            or not self.engine_type.strip()
            or not self.provider.strip()
        ):
            raise ValueError("engine identity is required")
        for values in (self.input_artifacts, self.output_artifacts):
            if len(set(values)) != len(values):
                raise ValueError("engine artifact lists must be unique")
        if "llm" in self.engine_type.lower() and not self.loopback_only:
            raise ValueError("local LLM engines must be loopback-only")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("engine binding cannot authorize live execution")


@dataclass(frozen=True, slots=True)
class CrewTaskDefinition:
    task_id: str
    role_id: str
    engine_id: str
    cadence: CrewCadence
    dependencies: tuple[str, ...]
    symbol: str | None
    timeframes: tuple[str, ...]
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    authority: CrewAuthority
    interval_days: int | None = None
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    emits_signal_opportunity: bool = False
    mutates_parameters: bool = False
    emits_trading_signal: bool = False
    submits_orders: bool = False

    def __post_init__(self) -> None:
        if (
            not self.task_id.strip()
            or not self.role_id.strip()
            or not self.engine_id.strip()
        ):
            raise ValueError("crew task identity is required")
        for values in (
            self.dependencies,
            self.timeframes,
            self.input_artifacts,
            self.output_artifacts,
            self.blockers,
        ):
            if len(set(values)) != len(values):
                raise ValueError("crew task lists must be unique")
        if self.cadence is CrewCadence.BIWEEKLY and self.interval_days != 14:
            raise ValueError("biweekly validation tasks must run every 14 days")
        if self.cadence is not CrewCadence.BIWEEKLY and self.interval_days is not None:
            raise ValueError("interval_days is only valid for biweekly tasks")
        if self.symbol is not None:
            normalized = self.symbol.strip().upper()
            if not normalized or not normalized.isalnum():
                raise ValueError("crew task symbol is invalid")
            object.__setattr__(self, "symbol", normalized)
        if self.execution_allowed or self.mutates_parameters or self.submits_orders:
            raise ValueError("crew tasks cannot mutate parameters or trade")
        if self.emits_trading_signal:
            raise ValueError("crew tasks cannot emit final trading signals")


@dataclass(frozen=True, slots=True)
class CrewGovernanceAgreement:
    agreement_id: str
    role_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    validation_points: tuple[str, ...]
    local_llm_only: bool = True
    cloud_fallback_allowed: bool = False
    autonomous_execution_allowed: bool = False
    status: CrewPlanStatus = CrewPlanStatus.HUMAN_REVIEW_REQUIRED
    blockers: tuple[str, ...] = ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.agreement_id.strip():
            raise ValueError("crew governance agreement identity is required")
        for values in (self.role_ids, self.task_ids, self.validation_points):
            if not values or len(set(values)) != len(values):
                raise ValueError(
                    "crew governance agreement lists must be non-empty and unique"
                )
            if any(not value.strip() for value in values):
                raise ValueError(
                    "crew governance agreement lists cannot contain blanks"
                )
        if set(self.validation_points) - set(self.task_ids):
            raise ValueError("crew governance validation point is unknown")
        if not self.local_llm_only:
            raise ValueError("crew governance must remain local-LLM only")
        if self.cloud_fallback_allowed:
            raise ValueError("cloud fallback is not allowed")
        if self.autonomous_execution_allowed:
            raise ValueError("autonomous execution is not allowed")
        if (
            self.status is not CrewPlanStatus.HUMAN_REVIEW_REQUIRED
            or "HUMAN_REVIEW_REQUIRED" not in self.blockers
            or "LIVE_ORDER_BLOCKED" not in self.blockers
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "crew governance agreement must remain review-only and live blocked"
            )


@dataclass(frozen=True, slots=True)
class CrewProcessPlan:
    process_id: str
    validation_symbol: str
    roles: tuple[CrewRoleDefinition, ...]
    engines: tuple[EngineBinding, ...]
    tasks: tuple[CrewTaskDefinition, ...]
    governance: CrewGovernanceAgreement | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.process_id.strip() or not self.validation_symbol.strip():
            raise ValueError("crew process identity is required")
        validation_symbol = self.validation_symbol.strip().upper()
        if not validation_symbol.isalnum():
            raise ValueError("validation symbol is invalid")
        object.__setattr__(self, "validation_symbol", validation_symbol)
        if not self.roles or not self.engines or not self.tasks:
            raise ValueError("crew process requires roles, engines and tasks")
        role_ids = tuple(role.role_id for role in self.roles)
        engine_ids = tuple(engine.engine_id for engine in self.engines)
        task_ids = tuple(task.task_id for task in self.tasks)
        if len(set(role_ids)) != len(role_ids):
            raise ValueError("crew role identities must be unique")
        if len(set(engine_ids)) != len(engine_ids):
            raise ValueError("engine identities must be unique")
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("crew task identities must be unique")
        known_roles = set(role_ids)
        known_engines = set(engine_ids)
        known_tasks = set(task_ids)
        if any(task.role_id not in known_roles for task in self.tasks):
            raise ValueError("crew task role is unknown")
        if any(task.engine_id not in known_engines for task in self.tasks):
            raise ValueError("crew task engine is unknown")
        if any(set(task.dependencies) - known_tasks for task in self.tasks):
            raise ValueError("crew task dependency is unknown")
        if self.governance is not None:
            if set(self.governance.role_ids) != known_roles:
                raise ValueError("crew governance roles do not match plan roles")
            if set(self.governance.task_ids) != known_tasks:
                raise ValueError("crew governance tasks do not match plan tasks")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("crew process cannot authorize live execution")
        self.topological_order()

    def topological_order(self) -> tuple[str, ...]:
        dependencies = {task.task_id: set(task.dependencies) for task in self.tasks}
        ordered: list[str] = []
        while dependencies:
            ready = sorted(
                task_id for task_id, required in dependencies.items() if not required
            )
            if not ready:
                raise ValueError("crew process contains a dependency cycle")
            ordered.extend(ready)
            for task_id in ready:
                del dependencies[task_id]
            for required in dependencies.values():
                required.difference_update(ready)
        return tuple(ordered)

    @property
    def biweekly_validation_task(self) -> CrewTaskDefinition:
        matches = tuple(
            task
            for task in self.tasks
            if task.cadence is CrewCadence.BIWEEKLY
            and task.symbol == self.validation_symbol
        )
        if len(matches) != 1:
            raise ValueError("exactly one validation-symbol biweekly task is required")
        return matches[0]


def build_enterprise_ai_crew_plan(
    *,
    validation_symbol: str = "BTCUSDT",
    timeframes: tuple[str, ...] = ("15m", "1h", "4h", "1d"),
) -> CrewProcessPlan:
    symbol = validation_symbol.strip().upper()
    roles = _crew_roles()
    engines = _engine_bindings(symbol)
    tasks = _crew_tasks(symbol, timeframes)
    governance = CrewGovernanceAgreement(
        agreement_id=f"ai4binance-{symbol.lower()}-review-only",
        role_ids=tuple(role.role_id for role in roles),
        task_ids=tuple(task.task_id for task in tasks),
        validation_points=(
            _validation_task_id(symbol),
            "risk_gatekeeper_review",
            "local_llm_advisory_loop",
        ),
    )
    return CrewProcessPlan(
        process_id="ai4binance-enterprise-ai-crew",
        validation_symbol=symbol,
        roles=roles,
        engines=engines,
        tasks=tasks,
        governance=governance,
    )


def _crew_roles() -> tuple[CrewRoleDefinition, ...]:
    return (
        CrewRoleDefinition(
            "chief_research_coordinator",
            "Chief Research Coordinator",
            CrewAuthority.RESEARCH_ONLY,
            ("coordinate_tasks", "merge_audit_states", "preserve_fail_closed_order"),
        ),
        CrewRoleDefinition(
            "market_outlook_agent",
            "Market Outlook Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("summarize_outlook_artifacts", "report_mtf_bias", "list_blockers"),
            may_emit_signal_opportunity=True,
        ),
        CrewRoleDefinition(
            "technical_governance_agent",
            "Technical Indicator Governance Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("audit_indicator_families", "check_oos_eligibility", "flag_overfit"),
        ),
        CrewRoleDefinition(
            "trend_detection_agent",
            "Trend Detection Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("review_trend_events", "compare_timeframes", "report_conflicts"),
        ),
        CrewRoleDefinition(
            "support_resistance_agent",
            "Support Resistance Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("review_level_reactions", "summarize_atr_zones", "report_sensitivity"),
        ),
        CrewRoleDefinition(
            "price_action_candlestick_agent",
            "Price Action Candlestick Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("review_playbook_triggers", "flag_single_candle_noise", "rank_setups"),
        ),
        CrewRoleDefinition(
            "strategy_candidate_builder",
            "Strategy Candidate Builder",
            CrewAuthority.RESEARCH_ONLY,
            (
                "build_research_candidates",
                "require_registry_playbooks",
                "log_rejections",
            ),
            may_emit_signal_opportunity=True,
        ),
        CrewRoleDefinition(
            "backtest_tuning_agent",
            "Backtest Tuning Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("run_archived_backtests", "run_walk_forward", "stage_tuning_candidates"),
            may_emit_signal_opportunity=True,
        ),
        CrewRoleDefinition(
            "auto_learn_agent",
            "Auto Learn Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("rank_lessons", "propose_experiments", "require_human_approval"),
        ),
        CrewRoleDefinition(
            "portfolio_management_agent",
            "Portfolio Management Agent",
            CrewAuthority.PAPER_PROPOSAL,
            ("read_wallet_context", "assess_exposure", "propose_rebalance_only"),
        ),
        CrewRoleDefinition(
            "risk_gatekeeper_agent",
            "Risk And Gatekeeper Agent",
            CrewAuthority.RESEARCH_ONLY,
            ("merge_blockers", "enforce_no_trade", "keep_live_order_blocked"),
        ),
        CrewRoleDefinition(
            "second_brain_agent",
            "Second Brain Agent",
            CrewAuthority.READ_ONLY,
            ("index_allowed_artifacts", "verify_hashes", "return_cited_context"),
            may_call_local_llm=True,
            may_retrieve_context=True,
            may_emit_signal_opportunity=True,
        ),
    )


def _engine_bindings(symbol: str) -> tuple[EngineBinding, ...]:
    return (
        EngineBinding(
            "deterministic_core",
            "ai4binance_core",
            "ai4binance",
            CrewAuthority.RESEARCH_ONLY,
            loopback_only=True,
            input_artifacts=("Data/market", "Artifacts", "State"),
            output_artifacts=("Logs/crew_core_events.jsonl",),
        ),
        EngineBinding(
            "rag_second_brain",
            "local_rag_index",
            "ai4binance_artifact_index",
            CrewAuthority.READ_ONLY,
            loopback_only=True,
            input_artifacts=("Docs", "Artifacts", "Backtest/validation", "Logs"),
            output_artifacts=("State/second-brain-index.json",),
        ),
        EngineBinding(
            "local_llm_advisory",
            "local_llm_llama_cpp",
            "qwen3:8b",
            CrewAuthority.RESEARCH_ONLY,
            loopback_only=True,
            input_artifacts=("State/second-brain-index.json",),
            output_artifacts=("Logs/local_llm_advisory_events.jsonl",),
        ),
        EngineBinding(
            "validation_pipeline",
            "backtest_walk_forward_tuning",
            "ResearchValidationService",
            CrewAuthority.RESEARCH_ONLY,
            loopback_only=True,
            input_artifacts=("Data/market",),
            output_artifacts=(f"Backtest/validation/{symbol}",),
        ),
    )


def _crew_tasks(
    symbol: str,
    timeframes: tuple[str, ...],
) -> tuple[CrewTaskDefinition, ...]:
    validation_task_id = _validation_task_id(symbol)
    return (
        CrewTaskDefinition(
            "second_brain_refresh",
            "second_brain_agent",
            "rag_second_brain",
            CrewCadence.DAILY,
            (),
            None,
            (),
            ("Docs", "Artifacts", "Backtest/validation", "Logs"),
            ("State/second-brain-index.json",),
            CrewAuthority.READ_ONLY,
        ),
        CrewTaskDefinition(
            "market_outlook_review",
            "market_outlook_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("second_brain_refresh",),
            None,
            timeframes,
            ("Artifacts/market-outlook/state.json",),
            ("Logs/market_outlook_crew_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
            emits_signal_opportunity=True,
        ),
        CrewTaskDefinition(
            "technical_governance_review",
            "technical_governance_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("market_outlook_review",),
            None,
            timeframes,
            ("src/ai4binance/agents", "src/ai4binance/strategies"),
            ("Logs/technical_governance_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
            emits_signal_opportunity=True,
        ),
        CrewTaskDefinition(
            "trend_detection_review",
            "trend_detection_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("technical_governance_review",),
            None,
            timeframes,
            ("Artifacts/market-outlook/state.json",),
            ("Logs/trend_detection_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
        ),
        CrewTaskDefinition(
            "support_resistance_review",
            "support_resistance_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("technical_governance_review",),
            None,
            timeframes,
            ("Artifacts/market-outlook/state.json",),
            ("Logs/support_resistance_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
        ),
        CrewTaskDefinition(
            "price_action_review",
            "price_action_candlestick_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("support_resistance_review", "trend_detection_review"),
            None,
            ("15m", "1h"),
            ("src/ai4binance/strategies/price_action.py",),
            ("Logs/price_action_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
        ),
        CrewTaskDefinition(
            "strategy_candidate_build",
            "strategy_candidate_builder",
            "deterministic_core",
            CrewCadence.DAILY,
            ("price_action_review",),
            None,
            timeframes,
            ("src/ai4binance/strategies/registry.py",),
            ("Logs/strategy_candidate_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
        ),
        CrewTaskDefinition(
            validation_task_id,
            "backtest_tuning_agent",
            "validation_pipeline",
            CrewCadence.BIWEEKLY,
            ("strategy_candidate_build",),
            symbol,
            timeframes,
            (f"Data/market/{symbol}",),
            (f"Backtest/validation/{symbol}",),
            CrewAuthority.RESEARCH_ONLY,
            interval_days=14,
            blockers=("LIVE_ORDER_BLOCKED",),
            emits_signal_opportunity=True,
        ),
        CrewTaskDefinition(
            "auto_learn_review",
            "auto_learn_agent",
            "deterministic_core",
            CrewCadence.ON_DEMAND,
            (validation_task_id,),
            symbol,
            timeframes,
            (f"Backtest/validation/{symbol}",),
            ("State/learning_summary.json", "Logs/learning_events.jsonl"),
            CrewAuthority.RESEARCH_ONLY,
        ),
        CrewTaskDefinition(
            "portfolio_proposal_review",
            "portfolio_management_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("second_brain_refresh",),
            None,
            (),
            ("State/private/account-management.json",),
            ("Logs/portfolio_proposal_events.jsonl",),
            CrewAuthority.PAPER_PROPOSAL,
            blockers=("EXECUTION_NOT_ALLOWED",),
        ),
        CrewTaskDefinition(
            "risk_gatekeeper_review",
            "risk_gatekeeper_agent",
            "deterministic_core",
            CrewCadence.DAILY,
            ("auto_learn_review", "portfolio_proposal_review"),
            symbol,
            timeframes,
            (f"Backtest/validation/{symbol}", "State/private/account-management.json"),
            ("Logs/risk_gatekeeper_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
            blockers=("NO_TRADE", "LIVE_ORDER_BLOCKED"),
        ),
        CrewTaskDefinition(
            "local_llm_advisory_loop",
            "second_brain_agent",
            "local_llm_advisory",
            CrewCadence.ON_DEMAND,
            ("risk_gatekeeper_review",),
            symbol,
            timeframes,
            ("State/second-brain-index.json", "Logs/risk_gatekeeper_events.jsonl"),
            ("Logs/local_llm_advisory_events.jsonl",),
            CrewAuthority.RESEARCH_ONLY,
            blockers=("ADVISORY_ONLY", "LIVE_ORDER_BLOCKED"),
            emits_signal_opportunity=True,
        ),
    )


def _validation_task_id(symbol: str) -> str:
    normalized = symbol.strip().lower()
    if not normalized or not normalized.isalnum():
        raise ValueError("validation symbol is invalid")
    return f"{normalized}_biweekly_backtest_tuning"

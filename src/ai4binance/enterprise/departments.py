"""Default pyramid-governance department registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ai4binance.enterprise.contracts import DepartmentId


class AgentClassification(StrEnum):
    MANAGEMENT_CONTROLLER = "MANAGEMENT_CONTROLLER"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    DETERMINISTIC_SERVICE = "DETERMINISTIC_SERVICE"
    DETERMINISTIC_SKILL = "DETERMINISTIC_SKILL"
    STATELESS_SPECIALIST_WORKER = "STATELESS_SPECIALIST_WORKER"
    LLM_ADVISORY_AGENT = "LLM_ADVISORY_AGENT"
    RAG_RETRIEVAL_AGENT = "RAG_RETRIEVAL_AGENT"
    DATA_ACQUISITION_AGENT = "DATA_ACQUISITION_AGENT"
    QUALITY_REVIEWER = "QUALITY_REVIEWER"
    RISK_GATE = "RISK_GATE"
    VALIDATION_GATE = "VALIDATION_GATE"
    EXECUTION_ADAPTER = "EXECUTION_ADAPTER"
    DEPRECATED_OR_DUPLICATE = "DEPRECATED_OR_DUPLICATE"


class ResourceClass(StrEnum):
    IO_BOUND = "IO_BOUND"
    CPU_LIGHT = "CPU_LIGHT"
    CPU_HEAVY = "CPU_HEAVY"
    GPU_LLM_SINGLE_LANE = "GPU_LLM_SINGLE_LANE"
    BACKTEST_PROCESS = "BACKTEST_PROCESS"
    REPORTING_LOW_PRIORITY = "REPORTING_LOW_PRIORITY"


_INDEPENDENT_CONTROL_DEPARTMENTS = frozenset(
    {
        DepartmentId.QUALITY_AUDIT,
        DepartmentId.RISK_VALIDATION,
        DepartmentId.MULTI_OPS,
    }
)


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"department {name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"department {name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"department {name} must be unique")


@dataclass(frozen=True, slots=True)
class DepartmentDefinition:
    department_id: DepartmentId
    display_name: str
    manager_role: str
    purpose: str
    authority_scope: tuple[str, ...]
    allowed_classifications: tuple[AgentClassification, ...]
    resource_class: ResourceClass
    max_runtime_concurrency: int
    reports_to: DepartmentId | None = DepartmentId.EXECUTIVE_OFFICE
    independent_control: bool = False
    veto_authority: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("display_name", self.display_name)
        _require_text("manager_role", self.manager_role)
        _require_text("purpose", self.purpose)
        _require_unique_text("authority_scope", self.authority_scope)
        if not self.allowed_classifications:
            raise ValueError("department classifications cannot be empty")
        if len(set(self.allowed_classifications)) != len(self.allowed_classifications):
            raise ValueError("department classifications must be unique")
        if not 1 <= self.max_runtime_concurrency <= 10:
            raise ValueError("department concurrency must stay bounded")
        should_be_independent = self.department_id in _INDEPENDENT_CONTROL_DEPARTMENTS
        if self.independent_control != should_be_independent:
            raise ValueError("department independent-control flag is inconsistent")
        if self.veto_authority and not self.independent_control:
            raise ValueError("only independent control departments may veto")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("department cannot authorize live execution")


@dataclass(frozen=True, slots=True)
class DepartmentRegistry:
    departments: tuple[DepartmentDefinition, ...]
    _by_id: Mapping[DepartmentId, DepartmentDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.departments:
            raise ValueError("department registry cannot be empty")
        by_id = {
            department.department_id: department for department in self.departments
        }
        if len(by_id) != len(self.departments):
            raise ValueError("department IDs must be unique")
        missing_controls = _INDEPENDENT_CONTROL_DEPARTMENTS.difference(by_id)
        if missing_controls:
            raise ValueError("registry requires independent quality/risk/ops controls")
        for department in self.departments:
            if department.reports_to is not None and department.reports_to not in by_id:
                raise ValueError("department reports_to target is unknown")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def get(self, department_id: DepartmentId) -> DepartmentDefinition:
        return self._by_id[department_id]

    def independent_controls(self) -> tuple[DepartmentDefinition, ...]:
        return tuple(
            item
            for item in self.departments
            if item.department_id in _INDEPENDENT_CONTROL_DEPARTMENTS
        )

    def operational_departments(self) -> tuple[DepartmentDefinition, ...]:
        return tuple(item for item in self.departments if not item.independent_control)

    def validate_assignment(
        self,
        *,
        department_id: DepartmentId,
        classification: AgentClassification,
    ) -> DepartmentDefinition:
        department = self.get(department_id)
        if classification not in department.allowed_classifications:
            raise ValueError("agent classification is outside department authority")
        return department


@dataclass(frozen=True, slots=True)
class SeparationOfDutiesRule:
    rule_id: str
    subject_department: DepartmentId
    prohibited_authority: str
    blocker: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("rule_id", self.rule_id)
        _require_text("prohibited_authority", self.prohibited_authority)
        _require_text("blocker", self.blocker)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("separation rule cannot authorize live execution")


def build_default_department_registry() -> DepartmentRegistry:
    manager = AgentClassification.DEPARTMENT_MANAGER
    specialist = AgentClassification.STATELESS_SPECIALIST_WORKER
    llm = AgentClassification.LLM_ADVISORY_AGENT
    deterministic = AgentClassification.DETERMINISTIC_SERVICE
    return DepartmentRegistry(
        (
            DepartmentDefinition(
                DepartmentId.EXECUTIVE_OFFICE,
                "Executive Office",
                "GeneralManagerController",
                "Classify board directives and coordinate department managers.",
                ("WORK_ORDER_PREVIEW", "MEETING_ORCHESTRATION", "ESCALATION"),
                (AgentClassification.MANAGEMENT_CONTROLLER, manager, llm),
                ResourceClass.CPU_LIGHT,
                1,
                reports_to=None,
            ),
            DepartmentDefinition(
                DepartmentId.BUSINESS_DEVELOPMENT,
                "Business Development Department",
                "BusinessDevelopmentManager",
                "Research platform opportunities without creating trade signals.",
                ("OPPORTUNITY_RESEARCH", "FEASIBILITY_ASSESSMENT"),
                (manager, specialist, llm),
                ResourceClass.REPORTING_LOW_PRIORITY,
                2,
            ),
            DepartmentDefinition(
                DepartmentId.RESEARCH_DEVELOPMENT,
                "Research and Development Department",
                "ResearchAndDevelopmentManager",
                "Develop hypotheses, experiments and validation plans.",
                ("HYPOTHESIS_DESIGN", "EXPERIMENT_DESIGN", "MODEL_RESEARCH"),
                (manager, specialist, deterministic, llm),
                ResourceClass.CPU_HEAVY,
                2,
            ),
            DepartmentDefinition(
                DepartmentId.SOFTWARE_ENGINEERING,
                "Software Engineering Department",
                "SoftwareDepartmentManager",
                "Implement approved software changes and tests.",
                ("ARCHITECTURE_PLAN", "IMPLEMENTATION", "TEST_ENGINEERING"),
                (manager, specialist, deterministic, llm),
                ResourceClass.CPU_LIGHT,
                3,
            ),
            DepartmentDefinition(
                DepartmentId.DATA_SUPPLY,
                "Data Supply Department",
                "DataSupplyDepartmentManager",
                "Centralize external data acquisition and immutable data products.",
                ("SOURCE_REGISTRY", "FETCH_CACHE_VALIDATE", "DATA_PRODUCT_PUBLISH"),
                (
                    manager,
                    AgentClassification.DATA_ACQUISITION_AGENT,
                    deterministic,
                ),
                ResourceClass.IO_BOUND,
                10,
            ),
            DepartmentDefinition(
                DepartmentId.MARKET_INTELLIGENCE,
                "Market Intelligence Department",
                "MarketIntelligenceManager",
                "Analyze supplied evidence packs without refetching raw data.",
                ("NEWS_INTELLIGENCE", "SOCIAL_INTELLIGENCE", "WHALE_ANALYSIS"),
                (manager, specialist, llm, AgentClassification.RAG_RETRIEVAL_AGENT),
                ResourceClass.CPU_LIGHT,
                3,
            ),
            DepartmentDefinition(
                DepartmentId.AGENT_FACTORY,
                "Human Resources and Agent Factory Department",
                "AgentFactoryManager",
                "Design and evaluate agent roles without production activation.",
                ("ROLE_DESIGN", "SKILL_PROPOSAL", "COMPETENCY_EVALUATION"),
                (manager, specialist, llm),
                ResourceClass.REPORTING_LOW_PRIORITY,
                2,
            ),
            DepartmentDefinition(
                DepartmentId.QUALITY_AUDIT,
                "Quality, Audit and Continuous Improvement Department",
                "QualityDepartmentManager",
                "Review methodology, code, evidence and process compliance.",
                ("QUALITY_REVIEW", "AUDIT", "CAPA", "NCR"),
                (manager, AgentClassification.QUALITY_REVIEWER, llm),
                ResourceClass.CPU_LIGHT,
                2,
                independent_control=True,
                veto_authority=True,
            ),
            DepartmentDefinition(
                DepartmentId.RISK_VALIDATION,
                "Independent Risk and Deterministic Validation Department",
                "RiskValidationManager",
                "Apply approved risk rules and deterministic validation gates.",
                ("RISK_GATE", "VALIDATION_GATE", "EXECUTION_BLOCKERS"),
                (
                    manager,
                    AgentClassification.RISK_GATE,
                    AgentClassification.VALIDATION_GATE,
                    deterministic,
                ),
                ResourceClass.CPU_LIGHT,
                2,
                independent_control=True,
                veto_authority=True,
            ),
            DepartmentDefinition(
                DepartmentId.TRADER,
                "Trader Department",
                "TraderDepartmentManager",
                "Produce setup and trade-plan candidates for independent review.",
                ("SETUP_SELECTION", "TRADE_PLAN_PROPOSAL", "CLOSURE_REVIEW"),
                (manager, specialist, deterministic, llm),
                ResourceClass.CPU_LIGHT,
                3,
            ),
            DepartmentDefinition(
                DepartmentId.EDUCATION,
                "Education and Knowledge Management Department",
                "EducationDepartmentManager",
                "Prepare lessons learned and training proposals.",
                ("LESSONS_LEARNED", "TRAINING_NEEDS", "CURRICULUM_PROPOSAL"),
                (manager, specialist, llm, AgentClassification.RAG_RETRIEVAL_AGENT),
                ResourceClass.REPORTING_LOW_PRIORITY,
                2,
            ),
            DepartmentDefinition(
                DepartmentId.FINANCE_PORTFOLIO,
                "Finance and Portfolio Governance Department",
                "FinanceDepartmentManager",
                "Assess accounting, cost, capital and portfolio impact.",
                ("ACCOUNTING_REVIEW", "CAPITAL_ALLOCATION_PROPOSAL", "COST_ANALYSIS"),
                (manager, specialist, deterministic),
                ResourceClass.CPU_LIGHT,
                2,
            ),
            DepartmentDefinition(
                DepartmentId.MULTI_OPS,
                "Multi-Ops Department",
                "MultiOpsManager",
                "Observe AIOps, MLOps, LLMOps, RAGOps, DataOps and TradeOps.",
                ("AIOPS", "MLOPS", "LLMOPS", "RAGOPS", "DATAOPS", "TRADEOPS"),
                (manager, specialist, deterministic, llm),
                ResourceClass.CPU_LIGHT,
                2,
                independent_control=True,
                veto_authority=True,
            ),
        )
    )


def default_separation_of_duties_rules() -> tuple[SeparationOfDutiesRule, ...]:
    return (
        SeparationOfDutiesRule(
            "SOFTWARE_CANNOT_SELF_APPROVE",
            DepartmentId.SOFTWARE_ENGINEERING,
            "QUALITY_APPROVAL",
            "SOFTWARE_SELF_APPROVAL_BLOCKED",
        ),
        SeparationOfDutiesRule(
            "RESEARCH_CANNOT_PROMOTE_MODEL",
            DepartmentId.RESEARCH_DEVELOPMENT,
            "PRODUCTION_PROMOTION",
            "RESEARCH_SELF_PROMOTION_BLOCKED",
        ),
        SeparationOfDutiesRule(
            "TRADER_CANNOT_OVERRIDE_RISK",
            DepartmentId.TRADER,
            "RISK_OVERRIDE",
            "TRADER_RISK_OVERRIDE_BLOCKED",
        ),
        SeparationOfDutiesRule(
            "FINANCE_CANNOT_TRANSFER_FUNDS",
            DepartmentId.FINANCE_PORTFOLIO,
            "WALLET_TRANSFER",
            "FINANCE_TRANSFER_BLOCKED",
        ),
        SeparationOfDutiesRule(
            "AGENT_FACTORY_CANNOT_ACTIVATE_PRODUCTION",
            DepartmentId.AGENT_FACTORY,
            "PRODUCTION_AGENT_ACTIVATION",
            "AGENT_FACTORY_PROMOTION_BLOCKED",
        ),
        SeparationOfDutiesRule(
            "GENERAL_MANAGER_CANNOT_REMOVE_VETO",
            DepartmentId.EXECUTIVE_OFFICE,
            "VETO_OVERRIDE",
            "EXECUTIVE_VETO_OVERRIDE_BLOCKED",
        ),
    )

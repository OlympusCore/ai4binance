"""Modern AI agent stack audit mapped to AI4BINANCE safety boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ai4binance.governance_primitives import TECHNICAL_QUALITY_PRIMARY_STATUS


class AgentStackAuditStatus(StrEnum):
    PASSED = "PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class AgentStackLayerRequirement:
    layer_id: str
    purpose: str
    required_paths: tuple[str, ...]
    required_commands: tuple[str, ...] = ()
    required_controls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("agent stack layer id", self.layer_id)
        _require_text("agent stack layer purpose", self.purpose)
        _require_unique_text("agent stack layer paths", self.required_paths)
        _require_unique_text("agent stack layer commands", self.required_commands)
        _require_unique_text("agent stack layer controls", self.required_controls)


@dataclass(frozen=True, slots=True)
class AgentStackLayerCheck:
    layer_id: str
    purpose: str
    passed: bool
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    corrective_actions: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("agent stack check layer id", self.layer_id)
        _require_text("agent stack check purpose", self.purpose)
        _require_unique_text("agent stack check evidence refs", self.evidence_refs)
        _require_unique_text("agent stack check blockers", self.blockers)
        _require_unique_text(
            "agent stack check corrective actions", self.corrective_actions
        )
        if self.passed == bool(self.blockers):
            raise ValueError("agent stack check status and blockers disagree")
        if self.execution_allowed:
            raise ValueError("agent stack check cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("agent stack check cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agent stack check must remain live blocked")


@dataclass(frozen=True, slots=True)
class AgentStackAuditReport:
    audit_id: str
    observed_at: datetime
    status: AgentStackAuditStatus
    layers: tuple[AgentStackLayerCheck, ...]
    blockers: tuple[str, ...]
    corrective_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("agent stack audit id", self.audit_id)
        _require_aware("agent stack observed_at", self.observed_at)
        if not self.layers:
            raise ValueError("agent stack audit requires layer checks")
        _require_unique_text("agent stack audit blockers", self.blockers)
        _require_unique_text("agent stack audit actions", self.corrective_actions)
        expected_status = (
            AgentStackAuditStatus.REVISION_REQUIRED
            if self.blockers
            else AgentStackAuditStatus.PASSED
        )
        if self.status is not expected_status:
            raise ValueError("agent stack audit status does not match blockers")
        if self.execution_allowed:
            raise ValueError("agent stack audit cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("agent stack audit cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agent stack audit must remain live blocked")


def modern_agent_stack_requirements() -> tuple[AgentStackLayerRequirement, ...]:
    """Return AI4BINANCE's bounded interpretation of the 2026 agent stack."""
    return (
        AgentStackLayerRequirement(
            "RAG",
            "Use sourced retrieval as advisory evidence before answering.",
            ("src/ai4binance/rag.py", "src/ai4binance/rag_corrective.py"),
            ("second-brain",),
            ("RAG_CITATION_REQUIRED", "RAG_EVIDENCE_QUALITY_BLOCKED"),
        ),
        AgentStackLayerRequirement(
            "CONTEXT",
            "Build bounded context packets instead of unbounded prompt stuffing.",
            (
                "src/ai4binance/enterprise/context_contracts.py",
                "src/ai4binance/application/runtime.py",
            ),
        ),
        AgentStackLayerRequirement(
            "MEMORY",
            "Keep reviewed research memory separate from trading authority.",
            (
                "src/ai4binance/research_catalog.py",
                "src/ai4binance/multiops/ragops/__init__.py",
            ),
            ("second-brain",),
            ("RESEARCH_ONLY",),
        ),
        AgentStackLayerRequirement(
            "AGENT",
            "Represent agents as advisory roles with no final execution authority.",
            ("src/ai4binance/agents/registry.py", "src/ai4binance/agents/base.py"),
            ("agents",),
            ("LIVE_ORDER_BLOCKED",),
        ),
        AgentStackLayerRequirement(
            "AGENTIC_AI",
            "Plan and self-review workflows without self-promoting production state.",
            (
                "src/ai4binance/governance/agentic_patterns.py",
                "src/ai4binance/governance/crew.py",
            ),
            ("agentic-skills", "crew-plan"),
            ("HUMAN_REVIEW_REQUIRED",),
        ),
        AgentStackLayerRequirement(
            "TOOLS",
            "Route tool calls through policy and audit boundaries.",
            (
                "src/ai4binance/governance/tool_gateway.py",
                "src/ai4binance/governance/tool_policy.py",
            ),
        ),
        AgentStackLayerRequirement(
            "MCP",
            "Expose read-only evidence through optional local MCP surfaces.",
            (
                "src/ai4binance/mcp/server.py",
                "docs/contracts/interface_contract_read_only_evidence_mcp.md",
            ),
            ("second-brain",),
            ("LIVE_ORDER_BLOCKED",),
        ),
        AgentStackLayerRequirement(
            "SKILLS",
            "Load reusable know-how only through repo-local audited skills.",
            (".agents/skills/ai4binance-validation-first/SKILL.md",),
            ("skills-audit", "skill-discovery-status"),
            ("SKILL_SCRIPT_REVIEW_REQUIRED",),
        ),
        AgentStackLayerRequirement(
            "HOOKS",
            "Use scheduled/read-only hooks for reports, never hidden execution.",
            ("scripts/install_startup_task.ps1", "scripts/startup_status.ps1"),
            ("runtime-daemon", "skill-discovery-daemon", "system-report"),
        ),
        AgentStackLayerRequirement(
            "SUBAGENTS",
            "Keep specialist helpers bounded by deterministic merge and veto rules.",
            (
                "src/ai4binance/agents/specialists.py",
                "src/ai4binance/agents/validation.py",
            ),
            ("agents",),
        ),
        AgentStackLayerRequirement(
            "ORCHESTRATION",
            "Coordinate multi-step work with explicit state and degraded outcomes.",
            (
                "src/ai4binance/application/research.py",
                "src/ai4binance/ops/runtime.py",
            ),
            ("runtime-once", "quality-system-audit"),
        ),
        AgentStackLayerRequirement(
            "EVAL",
            "Measure advisory, research, and quality outputs before promotion.",
            (
                "src/ai4binance/agents/evaluation.py",
                "scripts/quality.ps1",
            ),
            ("quality-system-audit", "validate-research"),
            (TECHNICAL_QUALITY_PRIMARY_STATUS,),
        ),
        AgentStackLayerRequirement(
            "GOVERNANCE_AUTHORITY",
            "Bind every agent-stack change to OEK and human-review controls.",
            (
                "docs/governance/policy_organization_constitution_handbook.md",
                "src/ai4binance/enterprise/oek_compliance.py",
            ),
            ("oek-gap-analysis",),
            ("OEK_CONSTITUTION_COMPLIANCE", "LIVE_ORDER_BLOCKED"),
        ),
        AgentStackLayerRequirement(
            "DETERMINISTIC_CORE",
            "Keep final signals, risk, validation, and execution gates deterministic.",
            (
                "src/ai4binance/strategies/engine.py",
                "src/ai4binance/risk.py",
                "src/ai4binance/validation/summary.py",
                "src/ai4binance/execution/live_readiness.py",
            ),
            ("validation-summary", "live-preview-spot"),
            ("NO_TRADE", "LIVE_ORDER_BLOCKED"),
        ),
        AgentStackLayerRequirement(
            "SECURITY_SANDBOX",
            "Treat tools, web, MCP, social, and LLM context as hostile input.",
            (
                "src/ai4binance/privacy_boundary.py",
                "src/ai4binance/sandbox.py",
                "src/ai4binance/security_scan.py",
            ),
            ("privacy-boundary",),
            ("RESEARCH_ONLY",),
        ),
        AgentStackLayerRequirement(
            "OBSERVABILITY_AUDIT",
            "Persist traceable reports and audit events for every control surface.",
            (
                "src/ai4binance/events/journal.py",
                "src/ai4binance/ops/system_report.py",
                "src/ai4binance/enterprise/storage.py",
            ),
            ("system-report",),
            ("AUDIT_TRAIL_REQUIRED",),
        ),
        AgentStackLayerRequirement(
            "DATA_PROVENANCE",
            "Require source, freshness, validation, and destination proof.",
            (
                "src/ai4binance/research_governance.py",
                "src/ai4binance/storage/destination_verification.py",
                "src/ai4binance/validation/artifacts.py",
            ),
            ("sync-validation-data", "validate-research"),
            ("DESTINATION_VERIFY_REQUIRED",),
        ),
    )


def run_agent_stack_audit(
    workspace_root: Path,
    command_names: tuple[str, ...],
    observed_at: datetime,
) -> AgentStackAuditReport:
    _require_aware("agent stack observed_at", observed_at)
    checks = tuple(
        _check_requirement(workspace_root, command_names, requirement)
        for requirement in modern_agent_stack_requirements()
    )
    blockers = _stable_unique(
        tuple(blocker for check in checks for blocker in check.blockers)
    )
    corrective_actions = _stable_unique(
        tuple(action for check in checks for action in check.corrective_actions)
    )
    return AgentStackAuditReport(
        audit_id=f"agent-stack-audit:{int(observed_at.timestamp())}",
        observed_at=observed_at,
        status=(
            AgentStackAuditStatus.REVISION_REQUIRED
            if blockers
            else AgentStackAuditStatus.PASSED
        ),
        layers=checks,
        blockers=blockers,
        corrective_actions=corrective_actions,
    )


def _check_requirement(
    workspace_root: Path,
    command_names: tuple[str, ...],
    requirement: AgentStackLayerRequirement,
) -> AgentStackLayerCheck:
    missing_paths = tuple(
        path
        for path in requirement.required_paths
        if not (workspace_root / path).exists()
    )
    missing_commands = tuple(
        command
        for command in requirement.required_commands
        if command not in command_names
    )
    blockers = (
        *(
            f"AGENT_STACK_PATH_MISSING:{requirement.layer_id}:{path}"
            for path in missing_paths
        ),
        *(
            f"AGENT_STACK_COMMAND_MISSING:{requirement.layer_id}:{command}"
            for command in missing_commands
        ),
    )
    return AgentStackLayerCheck(
        layer_id=requirement.layer_id,
        purpose=requirement.purpose,
        passed=not blockers,
        evidence_refs=(
            *(f"path:{path}" for path in requirement.required_paths),
            *(f"cli-command:{command}" for command in requirement.required_commands),
            *(f"control:{control}" for control in requirement.required_controls),
        ),
        blockers=blockers,
        corrective_actions=_stable_unique(
            tuple(
                _corrective_action(requirement.layer_id, blocker)
                for blocker in blockers
            )
        ),
    )


def _corrective_action(layer_id: str, blocker: str) -> str:
    if blocker.startswith("AGENT_STACK_PATH_MISSING"):
        return f"Restore or implement the {layer_id} agent-stack source surface."
    return f"Register the missing {layer_id} CLI/reporting surface."

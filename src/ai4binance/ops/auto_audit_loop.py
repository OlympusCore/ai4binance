"""Bounded auto-audit loops for local, fail-closed system supervision."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ai4binance.config import Settings
from ai4binance.governance.dge_engine import DecisionGovernanceEngine
from ai4binance.governance.dge_models import (
    DgeGovernanceContext,
    DgeMarketAction,
    DgeTradeCandidate,
    GovernedDecision,
)
from ai4binance.local_agent.workbench import AdvisoryRunner, LocalQwenWorkbench
from ai4binance.ops.continuous_assurance import (
    AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
    EAACIE_INSTRUCTION_REFS,
    ContinuousAssurancePlan,
    build_continuous_assurance_plan,
    events_from_auto_audit_cycle,
    events_from_performance_evidence_snapshot,
)
from ai4binance.ops.kaizen_quality import (
    KaizenQualitySnapshot,
    build_kaizen_quality_snapshot,
    load_current_gate_evidence,
)
from ai4binance.ops.privacy_leak_guard import scan_public_privacy_leaks
from ai4binance.ops.system_report import (
    SystemReportResult,
    build_system_report,
    system_report_summary_payload,
)
from ai4binance.ops.user_reports import (
    canonical_system_root,
    user_report_paths,
    write_user_report_files,
)
from ai4binance.storage import write_json_object_verified

if TYPE_CHECKING:
    from ai4binance.ops.decision_telemetry import PerformanceEvidenceSnapshot

_DEFAULT_INTERVAL_SECONDS = 300.0


class SystemReportBuilder(Protocol):
    def __call__(
        self,
        settings: Settings,
        *,
        observed_at: datetime | None = None,
        workspace_root: Path | None = None,
    ) -> SystemReportResult: ...


@dataclass(frozen=True, slots=True)
class AutoAuditCycle:
    cycle_index: int
    observed_at: datetime
    system_status: str
    blocker_count: int
    blockers: tuple[str, ...]
    new_blockers: tuple[str, ...]
    resolved_blockers: tuple[str, ...]
    persistent_blockers: tuple[str, ...]
    system_report_path: Path
    system_report_json_path: Path
    local_qwen_status: str
    local_qwen_report_path: Path | None
    local_qwen_blockers: tuple[str, ...]
    action_refs: tuple[str, ...]
    privacy_leak_status: str = "CLEAR"
    privacy_leak_findings: tuple[str, ...] = ()
    privacy_dge_decision_id: str = ""
    privacy_dge_required_changes: tuple[str, ...] = ()
    continuous_assurance_plan: ContinuousAssurancePlan | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.cycle_index < 1:
            raise ValueError("auto-audit cycle index must be positive")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("auto-audit cycles cannot authorize trading")


@dataclass(frozen=True, slots=True)
class AutoAuditLoopResult:
    loop_id: str
    status: str
    cycles: tuple[AutoAuditCycle, ...]
    blockers: tuple[str, ...]
    json_path: Path
    latest_json_path: Path
    markdown_path: Path
    kaizen_quality_snapshot: KaizenQualitySnapshot | None = None
    workflow_pattern: str = "HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER"
    stop_reason: str = "MAX_CYCLES_REACHED"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.loop_id.strip() or not self.cycles:
            raise ValueError("auto-audit loop result identity is invalid")
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS", "DEGRADED"}:
            raise ValueError("auto-audit loop status is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("auto-audit loops cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "command": "auto-audit-loop",
            "loop_id": self.loop_id,
            "status": self.status,
            "workflow_pattern": self.workflow_pattern,
            "stop_reason": self.stop_reason,
            "cycles": [_cycle_payload(cycle) for cycle in self.cycles],
            "blockers": list(self.blockers),
            "json_path": str(self.json_path),
            "latest_json_path": str(self.latest_json_path),
            "markdown_path": str(self.markdown_path),
            "kaizen_quality_snapshot": (
                None
                if self.kaizen_quality_snapshot is None
                else self.kaizen_quality_snapshot.to_payload()
            ),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(slots=True)
class AutoAuditLoop:
    settings: Settings
    repository_root: Path
    report_builder: SystemReportBuilder = build_system_report
    qwen_runner: AdvisoryRunner | None = None
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        root = canonical_system_root(self.repository_root).resolve()
        if not root.is_dir():
            raise ValueError("auto-audit repository root is unavailable")
        self.repository_root = root

    def run(
        self,
        *,
        max_cycles: int = 1,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        use_local_qwen: bool = False,
        performance_snapshots: tuple[PerformanceEvidenceSnapshot, ...] = (),
        observed_at_factory: Callable[[], datetime] | None = None,
    ) -> AutoAuditLoopResult:
        if max_cycles < 1:
            raise ValueError("auto-audit max_cycles must be positive")
        if interval_seconds < 0:
            raise ValueError("auto-audit interval must be non-negative")
        now_factory = observed_at_factory or (lambda: datetime.now(UTC))
        loop_started_at = now_factory()
        previous_blockers: tuple[str, ...] = ()
        cycles: list[AutoAuditCycle] = []
        for index in range(1, max_cycles + 1):
            observed_at = now_factory()
            cycle = self._run_cycle(
                index=index,
                observed_at=observed_at,
                previous_blockers=previous_blockers,
                use_local_qwen=use_local_qwen,
                performance_snapshots=performance_snapshots,
            )
            cycles.append(cycle)
            previous_blockers = cycle.blockers
            if index < max_cycles:
                self.sleep(interval_seconds)
        status = _aggregate_status(tuple(cycles))
        blockers = tuple(
            dict.fromkeys(item for cycle in cycles for item in cycle.blockers)
        )
        return self._persist(
            AutoAuditLoopResult(
                loop_id=f"auto-audit:{int(loop_started_at.timestamp())}",
                status=status,
                cycles=tuple(cycles),
                blockers=blockers,
                json_path=Path("."),
                latest_json_path=Path("."),
                markdown_path=Path("."),
            ),
            loop_started_at,
        )

    def _run_cycle(
        self,
        *,
        index: int,
        observed_at: datetime,
        previous_blockers: tuple[str, ...],
        use_local_qwen: bool,
        performance_snapshots: tuple[PerformanceEvidenceSnapshot, ...],
    ) -> AutoAuditCycle:
        report = self.report_builder(
            self.settings,
            observed_at=observed_at,
            workspace_root=self.repository_root,
        )
        summary = system_report_summary_payload(report)
        system_blockers = _blocker_tuple(summary.get("blockers"))
        privacy_scan = scan_public_privacy_leaks(self.repository_root)
        privacy_blockers = tuple(
            f"privacy:{blocker}" for blocker in privacy_scan.blockers
        )
        blockers = tuple(dict.fromkeys((*system_blockers, *privacy_blockers)))
        previous = set(previous_blockers)
        current = set(blockers)
        privacy_decision = _privacy_dge_decision(
            self.settings.symbol,
            privacy_blockers,
            observed_at,
        )
        action_refs = (
            *_action_refs(summary),
            *(f"resolve:{blocker}" for blocker in privacy_blockers),
            *(
                (
                    f"dge-privacy-remediation:{privacy_decision.decision_id}",
                    *(
                        f"privacy-dge-change:{change}"
                        for change in privacy_decision.required_changes
                    ),
                )
                if privacy_decision is not None
                else ()
            ),
        )
        qwen_status = "SKIPPED"
        qwen_report_path: Path | None = None
        qwen_blockers: tuple[str, ...] = ("LOCAL_QWEN_REVIEW_NOT_REQUESTED",)
        if use_local_qwen:
            qwen = LocalQwenWorkbench(
                self.repository_root,
                runner=self.qwen_runner,
                max_file_chars=2_000,
                max_evidence_chars=6_000,
            ).run(
                task=(
                    "Auto-audit cycle icin blocker trendini yorumla. "
                    "Sadece Kaizen/Lean/Six Sigma/5S oncelik onerisi ver."
                ),
                query="LIVE_ORDER_BLOCKED RESEARCH_ONLY system-report blockers",
                files=("src/ai4binance/ops/auto_audit_loop.py",),
            )
            qwen_status = qwen.status
            qwen_report_path = qwen.report_path
            qwen_blockers = qwen.blockers
        auto_audit_events = events_from_auto_audit_cycle(
            observed_at=observed_at,
            system_status=str(summary.get("status", "DEGRADED")),
            blockers=blockers,
            new_blockers=tuple(sorted(current - previous)),
            resolved_blockers=tuple(sorted(previous - current)),
            privacy_leak_status=privacy_scan.status,
        )
        performance_events = tuple(
            event
            for snapshot in performance_snapshots
            for event in events_from_performance_evidence_snapshot(snapshot)
        )
        continuous_assurance_plan = build_continuous_assurance_plan(
            (*auto_audit_events, *performance_events),
            repository_root=self.repository_root,
        )
        return AutoAuditCycle(
            cycle_index=index,
            observed_at=observed_at,
            system_status=str(summary.get("status", "DEGRADED")),
            blocker_count=len(blockers),
            blockers=blockers,
            new_blockers=tuple(sorted(current - previous)),
            resolved_blockers=tuple(sorted(previous - current)),
            persistent_blockers=tuple(item for item in blockers if item in previous),
            system_report_path=Path(str(summary.get("markdown_path", ""))),
            system_report_json_path=Path(str(summary.get("json_path", ""))),
            local_qwen_status=qwen_status,
            local_qwen_report_path=qwen_report_path,
            local_qwen_blockers=qwen_blockers,
            action_refs=action_refs,
            privacy_leak_status=privacy_scan.status,
            privacy_leak_findings=tuple(
                f"{finding.relative_path}:{finding.category}"
                for finding in privacy_scan.findings
            ),
            privacy_dge_decision_id=(
                privacy_decision.decision_id if privacy_decision is not None else ""
            ),
            privacy_dge_required_changes=(
                privacy_decision.required_changes
                if privacy_decision is not None
                else ()
            ),
            continuous_assurance_plan=continuous_assurance_plan,
        )

    def _persist(
        self,
        result: AutoAuditLoopResult,
        observed_at: datetime,
    ) -> AutoAuditLoopResult:
        stamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
        artifact_dir = self.repository_root / "runtime" / "artifacts" / "auto_audit"
        paths = user_report_paths(
            self.repository_root,
            "audit",
            stamp,
            file_stem="auto_audit",
            latest_stem="auto_audit_latest",
        )
        json_path = artifact_dir / f"auto-audit-{stamp}.json"
        latest_json_path = artifact_dir / "auto-audit-latest.json"
        markdown_path = paths.markdown_path
        pending = AutoAuditLoopResult(
            loop_id=result.loop_id,
            status=result.status,
            cycles=result.cycles,
            blockers=result.blockers,
            json_path=json_path,
            latest_json_path=latest_json_path,
            markdown_path=markdown_path,
            stop_reason=result.stop_reason,
        )
        latest = pending.cycles[-1]
        current_gate_evidence = load_current_gate_evidence(self.repository_root)
        kaizen_snapshot = build_kaizen_quality_snapshot(
            observed_at=observed_at,
            blocker_cycles=tuple(
                (cycle.observed_at, cycle.blockers) for cycle in pending.cycles
            ),
            repository_root=self.repository_root,
            continuous_assurance_payload=_kaizen_continuous_assurance_contract_payload(
                latest.continuous_assurance_plan
            ),
            quality_gate_payload=current_gate_evidence.quality_gate_payload,
            governance_gate_payload=current_gate_evidence.governance_gate_payload,
            gate_evidence_blockers=current_gate_evidence.blockers,
        )
        persisted = AutoAuditLoopResult(
            loop_id=pending.loop_id,
            status=pending.status,
            cycles=pending.cycles,
            blockers=pending.blockers,
            json_path=pending.json_path,
            latest_json_path=pending.latest_json_path,
            markdown_path=pending.markdown_path,
            kaizen_quality_snapshot=kaizen_snapshot,
            stop_reason=pending.stop_reason,
        )
        payload = persisted.to_payload()
        write_json_object_verified(
            json_path,
            payload,
            blocker="AUTO_AUDIT_DESTINATION_VERIFY_FAILED",
            subject_id=result.loop_id,
            indent=2,
        )
        write_json_object_verified(
            latest_json_path,
            payload,
            blocker="AUTO_AUDIT_DESTINATION_VERIFY_FAILED",
            subject_id=result.loop_id,
            indent=2,
        )
        write_user_report_files(paths, payload, _render_markdown(persisted))
        return persisted


def run_auto_audit_loop(
    settings: Settings,
    *,
    repository_root: Path | None = None,
    max_cycles: int = 1,
    interval_seconds: float | None = None,
    use_local_qwen: bool = False,
    performance_snapshots: tuple[PerformanceEvidenceSnapshot, ...] = (),
    report_builder: SystemReportBuilder = build_system_report,
    qwen_runner: AdvisoryRunner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AutoAuditLoopResult:
    """Run a bounded report-only loop; never fixes, trades, or changes risk."""
    root = repository_root or Path.cwd()
    interval = (
        _DEFAULT_INTERVAL_SECONDS if interval_seconds is None else interval_seconds
    )
    return AutoAuditLoop(
        settings=settings,
        repository_root=root,
        report_builder=report_builder,
        qwen_runner=qwen_runner,
        sleep=sleep,
    ).run(
        max_cycles=max_cycles,
        interval_seconds=interval,
        use_local_qwen=use_local_qwen,
        performance_snapshots=performance_snapshots,
    )


def _aggregate_status(cycles: tuple[AutoAuditCycle, ...]) -> str:
    if any(cycle.local_qwen_status == "BLOCKED" for cycle in cycles):
        return "DEGRADED"
    if any(cycle.system_status == "DEGRADED" for cycle in cycles):
        return "DEGRADED"
    if any(cycle.blockers for cycle in cycles):
        return "RUNNING_WITH_BLOCKERS"
    return "READY"


def _cycle_payload(cycle: AutoAuditCycle) -> dict[str, object]:
    return {
        "cycle_index": cycle.cycle_index,
        "observed_at": cycle.observed_at.isoformat(),
        "system_status": cycle.system_status,
        "blocker_count": cycle.blocker_count,
        "blockers": list(cycle.blockers),
        "new_blockers": list(cycle.new_blockers),
        "resolved_blockers": list(cycle.resolved_blockers),
        "persistent_blockers": list(cycle.persistent_blockers),
        "system_report_path": str(cycle.system_report_path),
        "system_report_json_path": str(cycle.system_report_json_path),
        "local_qwen_status": cycle.local_qwen_status,
        "local_qwen_report_path": (
            str(cycle.local_qwen_report_path)
            if cycle.local_qwen_report_path is not None
            else None
        ),
        "local_qwen_blockers": list(cycle.local_qwen_blockers),
        "action_refs": list(cycle.action_refs),
        "privacy_leak_status": cycle.privacy_leak_status,
        "privacy_leak_findings": list(cycle.privacy_leak_findings),
        "privacy_dge_decision_id": cycle.privacy_dge_decision_id,
        "privacy_dge_required_changes": list(cycle.privacy_dge_required_changes),
        "continuous_assurance": (
            cycle.continuous_assurance_plan.to_payload()
            if cycle.continuous_assurance_plan is not None
            else None
        ),
        "execution_allowed": False,
        "promotion_status": cycle.promotion_status,
        "live_eligibility_status": cycle.live_eligibility_status,
    }


def _action_refs(summary: dict[str, object]) -> tuple[str, ...]:
    cards = summary.get("dashboard_cards")
    if not isinstance(cards, dict):
        return ()
    refs = cards.get("open_action_refs")
    return _blocker_tuple(refs)


def _privacy_dge_decision(
    symbol: str,
    privacy_blockers: tuple[str, ...],
    observed_at: datetime,
) -> GovernedDecision | None:
    if not privacy_blockers:
        return None
    target_symbol = symbol.strip().upper() or "SYSTEM"
    candidate = DgeTradeCandidate(
        candidate_id=f"privacy-remediation:{int(observed_at.timestamp())}",
        symbol=target_symbol,
        market="GOVERNANCE",
        requested_action=DgeMarketAction.HOLD,
        setup_name="privacy_leak_remediation",
        score=Decimal("100"),
        confidence=Decimal("1"),
        risk_reward=Decimal("2"),
        capital_source="NO_CAPITAL",
        primary_timeframe="SYSTEM",
        mtf_bias="N/A",
        regime="N/A",
        evidence_refs=("privacy-leak-guard",),
    )
    context = DgeGovernanceContext(
        context_id=f"privacy-context:{int(observed_at.timestamp())}",
        data_snapshot_id="privacy-leak-scan",
        semantic_graph_id="privacy-governance",
        position_context_ref="privacy-remediation",
        wallet_verified=True,
        oos_approved=True,
        risk_approved=True,
        execution_feasible=False,
        human_approval_recorded=False,
        no_new_capital_required=True,
        blockers=privacy_blockers,
        evidence_refs=("privacy-leak-guard",),
        evaluation_timestamp_utc=observed_at.isoformat(),
    )
    return DecisionGovernanceEngine().evaluate(candidate, context)


def _blocker_tuple(value: object = ()) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()


def _render_markdown(result: AutoAuditLoopResult) -> str:
    latest = result.cycles[-1]
    lines = [
        f"# AI4BINANCE Auto-Audit Loop - {result.loop_id}",
        "",
        "## ELI10",
        "",
        (
            "This report shows whether the system is healthy and what is still "
            "blocking it. It is read-only. It does not trade, change risk, or "
            "fix anything automatically."
        ),
        "",
        "## Executive Summary",
        "",
        (
            "This report monitors system health across bounded audit cycles. "
            "It highlights new, persistent, and resolved blockers. It does not "
            "place orders, increase risk, enable live mode, or perform cleanup."
        ),
        "",
        "## Summary",
        "",
        f"- status: `{result.status}`",
        f"- workflow_pattern: `{result.workflow_pattern}`",
        f"- stop_reason: `{result.stop_reason}`",
        f"- cycles: `{len(result.cycles)}`",
        f"- latest_system_status: `{latest.system_status}`",
        f"- latest_blocker_count: `{latest.blocker_count}`",
        f"- execution_allowed: `{result.execution_allowed}`",
        f"- promotion_status: `{result.promotion_status}`",
        f"- live_eligibility_status: `{result.live_eligibility_status}`",
        "",
        "## Latest Cycle",
        "",
        f"- system_report: `{latest.system_report_path}`",
        f"- system_report_json: `{latest.system_report_json_path}`",
        f"- local_qwen_status: `{latest.local_qwen_status}`",
        f"- local_qwen_report: `{latest.local_qwen_report_path or '-'}`",
        f"- privacy_leak_status: `{latest.privacy_leak_status}`",
        (f"- privacy_dge_decision_id: `{latest.privacy_dge_decision_id or '-'}`"),
        f"- continuous_assurance: `{_continuous_assurance_status(latest)}`",
        f"- kaizen_quality: `{_kaizen_quality_status(result)}`",
        "",
        "## Blocker Movement",
        "",
        f"- new: {', '.join(latest.new_blockers[:12]) or '-'}",
        f"- persistent: {', '.join(latest.persistent_blockers[:12]) or '-'}",
        f"- resolved: {', '.join(latest.resolved_blockers[:12]) or '-'}",
        "",
        "## Kaizen Quality",
        "",
        *(_render_kaizen_quality(result.kaizen_quality_snapshot)),
        "",
        "## Privacy / KVKK Guard",
        "",
        f"- leak_status: `{latest.privacy_leak_status}`",
        f"- findings: `{', '.join(latest.privacy_leak_findings[:8]) or '-'}`",
        (
            "- dge_required_changes: "
            f"`{', '.join(latest.privacy_dge_required_changes[:8]) or '-'}`"
        ),
        "",
        "## Enterprise Auto-Audit & Continuous Improvement",
        "",
        *(
            _render_continuous_assurance(latest.continuous_assurance_plan)
            if latest.continuous_assurance_plan is not None
            else ("- status: `SKIPPED`",)
        ),
        "",
        "## Safety",
        "",
        "- Auto-audit loop is report-only.",
        "- It does not place orders, mutate risk limits, or approve live mode.",
        "- KVKK/e-posta/wallet leak findings are blockers, not publishable details.",
        "- Local Qwen output is advisory evidence only.",
        "- Human review is required before finance, trading, or deployment action.",
        "",
    ]
    return "\n".join(lines)


def _render_continuous_assurance(
    plan: ContinuousAssurancePlan,
) -> tuple[str, ...]:
    latest_routes = ", ".join(
        (
            f"{decision.trigger_type.value}->"
            f"{'+'.join(domain.value for domain in decision.domains[:2])}"
        )
        for decision in plan.route_decisions[:4]
    )
    return (
        f"- instruction_ref: `{AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF}`",
        f"- instruction_refs: `{', '.join(EAACIE_INSTRUCTION_REFS)}`",
        f"- status: `{plan.status}`",
        f"- workflow_pattern: `{plan.workflow_pattern}`",
        f"- accepted_count: `{plan.accepted_count}`",
        f"- suppressed_count: `{plan.suppressed_count}`",
        (
            "- security_triggers: `"
            f"{', '.join(item.value for item in plan.security_trigger_types) or '-'}"
            "`"
        ),
        (
            "- security_domains: `"
            f"{', '.join(item.value for item in plan.security_domains) or '-'}"
            "`"
        ),
        f"- blockers: `{', '.join(plan.blockers[:8]) or '-'}`",
        f"- latest_routes: `{latest_routes or '-'}`",
    )


def _continuous_assurance_status(cycle: AutoAuditCycle) -> str:
    if cycle.continuous_assurance_plan is None:
        return "SKIPPED"
    return cycle.continuous_assurance_plan.status


def _kaizen_continuous_assurance_contract_payload(
    plan: ContinuousAssurancePlan | None,
) -> dict[str, object] | None:
    if plan is None:
        return None
    return {
        "trust_assurance": {
            "provenance": {
                "decision_kind": "CONTINUOUS_ASSURANCE_PLAN",
                "decision_id": f"provenance:{plan.plan_id}",
                "provenance_hash": "0" * 64,
                "evidence_refs": [
                    decision.event_id for decision in plan.route_decisions
                ],
                "blockers": list(plan.blockers),
                "execution_allowed": False,
                "live_eligibility_status": plan.live_eligibility_status,
            }
        }
    }


def _kaizen_quality_status(result: AutoAuditLoopResult) -> str:
    if result.kaizen_quality_snapshot is None:
        return "SKIPPED"
    return result.kaizen_quality_snapshot.status


def _render_kaizen_quality(
    snapshot: KaizenQualitySnapshot | None,
) -> tuple[str, ...]:
    if snapshot is None:
        return ("- status: `SKIPPED`",)
    persistent = tuple(
        signal.blocker
        for signal in snapshot.blocker_signals
        if signal.state == "PERSISTENT"
    )
    trace_gaps = tuple(
        row.entrypoint_id
        for row in snapshot.traceability_matrix
        if row.traceability_status == "REQUIRED_NOT_RECORDED"
    )
    instruction_token_count = sum(
        document.estimated_token_count
        for document in snapshot.instruction_baseline.documents
    )
    context_benchmark = snapshot.instruction_context_benchmark
    approval = snapshot.closure_gate.governance_approval_evidence
    return (
        f"- snapshot_id: `{snapshot.snapshot_id}`",
        f"- status: `{snapshot.status}`",
        f"- persistent_blockers: `{', '.join(persistent[:8]) or '-'}`",
        f"- traceability_gaps: `{', '.join(trace_gaps[:8]) or '-'}`",
        (
            "- closure_entrypoint_order: "
            f"`{', '.join(snapshot.closure_entrypoint_order[:8]) or '-'}`"
        ),
        f"- closure_gate: `{snapshot.closure_gate.status}`",
        (
            "- technical_quality_status: "
            f"`{snapshot.closure_gate.technical_quality_status}`"
        ),
        (
            "- governance_closure_status: "
            f"`{snapshot.closure_gate.governance_closure_status}`"
        ),
        (
            "- governance_approval: "
            f"`class={approval.change_class}; status={approval.status}; "
            f"approvals={approval.observed_approval_count}/"
            f"{approval.required_approval_count}; hard_veto="
            f"{str(approval.hard_veto).lower()}; "
            f"blockers={', '.join(approval.blockers) or '-'}`"
        ),
        f"- acceptance_status: `{snapshot.closure_gate.acceptance_status}`",
        (
            "- instruction_baseline: "
            f"`{len(snapshot.instruction_baseline.documents)} files, "
            f"{len(snapshot.instruction_baseline.overlaps)} exact-block overlaps, "
            f"{instruction_token_count} "
            "estimated tokens`"
        ),
        (
            "- instruction_context_benchmark: "
            f"`status={context_benchmark.status}; "
            f"tasks={len(context_benchmark.measurements)}; "
            f"max_bytes={context_benchmark.max_instruction_bytes}; "
            "max_tokens="
            f"{context_benchmark.max_estimated_instruction_tokens}; "
            "token_status=TOKEN_ESTIMATE`"
        ),
        f"- fast_feedback: `{snapshot.fast_feedback_commands[0]}`",
        f"- full_gate: `{snapshot.full_gate_command}`",
        f"- blocker_evidence: `{_kaizen_blocker_evidence_summary(snapshot)}`",
        f"- execution_allowed: `{snapshot.execution_allowed}`",
        f"- live_eligibility_status: `{snapshot.live_eligibility_status}`",
    )


def _kaizen_blocker_evidence_summary(snapshot: KaizenQualitySnapshot) -> str:
    signals = snapshot.blocker_signals[:4]
    if not signals:
        return "-"
    return "; ".join(
        (
            f"{signal.blocker}|{signal.state}|"
            f"{signal.evidence_ref}|{signal.proof_command}"
        )
        for signal in signals
    )

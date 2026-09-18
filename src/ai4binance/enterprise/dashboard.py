"""Executive dashboard snapshot contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai4binance.enterprise.contracts import WorkflowIdentity

_CONTRACT_GUARDRAILS = (
    "EXPLICIT_POLICY_BOUNDARIES",
    "FAIL_CLOSED_DEFAULTS",
    "BOUNDED_ACTIONS",
    "TOOL_POLICY_ENFORCEMENT",
)
_HUMAN_APPROVAL_GATES = (
    "TRADING_SCOPE",
    "MONEY_MOVEMENT_SCOPE",
    "SECRET_ACCESS_SCOPE",
    "CONNECTOR_SCOPE",
    "RISK_OR_POLICY_ESCALATION",
)


@dataclass(frozen=True, slots=True)
class DashboardMetric:
    metric_id: str
    label: str
    value: str
    status: str
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.metric_id.strip()
            or not self.label.strip()
            or not self.value.strip()
        ):
            raise ValueError("dashboard metric identity is required")
        if self.status not in {"OK", "WATCH", "BLOCKED", "UNKNOWN"}:
            raise ValueError("dashboard metric status is invalid")
        if self.status in {"BLOCKED", "UNKNOWN"} and not self.blockers:
            raise ValueError("degraded dashboard metric requires blockers")
        _require_unique("dashboard metric blockers", self.blockers)


@dataclass(frozen=True, slots=True)
class ExecutiveDashboardSnapshot:
    identity: WorkflowIdentity
    snapshot_ref: str
    metrics: tuple[DashboardMetric, ...]
    open_action_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",)
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.snapshot_ref.strip():
            raise ValueError("dashboard snapshot identity is required")
        if not self.metrics:
            raise ValueError("dashboard snapshot requires metrics")
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(set(metric_ids)) != len(metric_ids):
            raise ValueError("dashboard metric IDs must be unique")
        _require_unique("dashboard action refs", self.open_action_refs)
        _require_unique("dashboard blockers", self.blockers)
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("dashboard cannot promote production state")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("dashboard cannot authorize execution")


def build_minimum_dashboard_snapshot(
    identity: WorkflowIdentity,
    *,
    quality_gate_status: str,
    live_gate_status: str = "LIVE_ORDER_BLOCKED",
) -> ExecutiveDashboardSnapshot:
    return ExecutiveDashboardSnapshot(
        identity=identity,
        snapshot_ref=identity.snapshot_id,
        metrics=(
            DashboardMetric(
                "quality_gate",
                "Quality Gate",
                quality_gate_status,
                "OK" if quality_gate_status == "PASSED" else "WATCH",
            ),
            DashboardMetric(
                "live_gate",
                "Live Gate",
                live_gate_status,
                "BLOCKED",
                ("LIVE_ORDER_BLOCKED",),
            ),
        ),
        open_action_refs=(),
    )


def build_system_report_dashboard_snapshot(
    identity: WorkflowIdentity,
    *,
    report_summary: Mapping[str, object],
) -> ExecutiveDashboardSnapshot:
    metrics, blockers = _system_report_dashboard_metrics(report_summary)
    open_action_refs = tuple(
        f"resolve:{blocker}" for blocker in tuple(dict.fromkeys(blockers))[:8]
    )
    report_id = str(report_summary.get("report_id", "system-report-dashboard")).strip()
    snapshot_ref = report_id if report_id else identity.snapshot_id
    return ExecutiveDashboardSnapshot(
        identity=identity,
        snapshot_ref=snapshot_ref,
        metrics=metrics,
        open_action_refs=open_action_refs,
        blockers=tuple(dict.fromkeys(("LIVE_ORDER_BLOCKED", *blockers))),
    )


def dashboard_snapshot_summary_payload(
    snapshot: ExecutiveDashboardSnapshot,
) -> dict[str, object]:
    blocked_metric_ids = tuple(
        metric.metric_id for metric in snapshot.metrics if metric.status == "BLOCKED"
    )
    watch_metric_ids = tuple(
        metric.metric_id for metric in snapshot.metrics if metric.status == "WATCH"
    )
    return {
        "snapshot_ref": snapshot.snapshot_ref,
        "metric_count": len(snapshot.metrics),
        "blocked_metric_count": len(blocked_metric_ids),
        "watch_metric_count": len(watch_metric_ids),
        "blocked_metric_ids": blocked_metric_ids,
        "watch_metric_ids": watch_metric_ids,
        "open_action_refs": snapshot.open_action_refs,
        "metrics": tuple(
            {
                "metric_id": metric.metric_id,
                "label": metric.label,
                "value": metric.value,
                "status": metric.status,
                "blockers": metric.blockers,
            }
            for metric in snapshot.metrics
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def system_report_dashboard_cards_payload(
    report_summary: Mapping[str, object],
) -> dict[str, object]:
    metrics, blockers = _system_report_dashboard_metrics(report_summary)
    blocked_metric_ids = tuple(
        metric.metric_id for metric in metrics if metric.status == "BLOCKED"
    )
    watch_metric_ids = tuple(
        metric.metric_id for metric in metrics if metric.status == "WATCH"
    )
    return {
        "source": "system-report",
        "report_id": str(report_summary.get("report_id", "system-report-dashboard")),
        "metric_count": len(metrics),
        "blocked_metric_count": len(blocked_metric_ids),
        "watch_metric_count": len(watch_metric_ids),
        "blocked_metric_ids": blocked_metric_ids,
        "watch_metric_ids": watch_metric_ids,
        "blockers": tuple(dict.fromkeys(blockers)),
        "open_action_refs": tuple(
            f"resolve:{blocker}" for blocker in tuple(dict.fromkeys(blockers))[:8]
        ),
        "metrics": tuple(
            {
                "metric_id": metric.metric_id,
                "label": metric.label,
                "value": metric.value,
                "status": metric.status,
                "blockers": metric.blockers,
            }
            for metric in metrics
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _system_report_dashboard_metrics(
    report_summary: Mapping[str, object],
) -> tuple[tuple[DashboardMetric, ...], tuple[str, ...]]:
    report_status = str(report_summary.get("status", "UNKNOWN"))
    report_blockers = _text_tuple(report_summary.get("blockers"))

    contract_payload = _mapping(report_summary.get("advanced_agent_operating_contract"))
    contract_status = str(contract_payload.get("status", "UNKNOWN"))
    contract_blockers = _text_tuple(contract_payload.get("blockers"))
    guardrails = _text_tuple(contract_payload.get("guardrails"))
    missing_guardrails = tuple(
        item for item in _CONTRACT_GUARDRAILS if item not in set(guardrails)
    )
    guardrail_blockers = tuple(
        f"MISSING_GUARDRAIL:{item}" for item in missing_guardrails
    )

    human_controls = _mapping(contract_payload.get("human_approval_controls"))
    human_mode = str(human_controls.get("mode", "UNKNOWN"))
    human_required_at = str(human_controls.get("required_at", "UNKNOWN"))
    human_gates = _text_tuple(human_controls.get("gates"))
    missing_human_gates = tuple(
        item for item in _HUMAN_APPROVAL_GATES if item not in set(human_gates)
    )
    approval_candidates: list[str] = []
    if human_mode != "HUMAN_IN_THE_LOOP":
        approval_candidates.append("HUMAN_APPROVAL_MODE_INVALID")
    if human_required_at != "CRITICAL_DECISION_POINTS":
        approval_candidates.append("HUMAN_APPROVAL_REQUIRED_AT_INVALID")
    approval_candidates.extend(
        f"MISSING_HUMAN_GATE:{item}" for item in missing_human_gates
    )
    approval_blockers = tuple(dict.fromkeys(approval_candidates))

    live_gate_status = str(
        report_summary.get("live_eligibility_status", "LIVE_ORDER_BLOCKED")
    )
    live_gate_blockers = (
        ("LIVE_ORDER_BLOCKED",)
        if live_gate_status == "LIVE_ORDER_BLOCKED"
        else ("LIVE_GATE_OVERRIDE_REJECTED",)
    )

    metrics = (
        _status_metric(
            metric_id="system_report",
            label="System Report",
            value=report_status,
            signal=report_status,
            blockers=report_blockers,
            unknown_blocker="SYSTEM_REPORT_STATUS_UNKNOWN",
        ),
        _status_metric(
            metric_id="advanced_agent_contract",
            label="Advanced Agent Contract",
            value=contract_status,
            signal=contract_status,
            blockers=contract_blockers,
            unknown_blocker="ADVANCED_AGENT_CONTRACT_STATUS_UNKNOWN",
        ),
        DashboardMetric(
            metric_id="contract_guardrails",
            label="Contract Guardrails",
            value=f"{len(guardrails)} controls",
            status="OK" if not guardrail_blockers else "BLOCKED",
            blockers=guardrail_blockers,
        ),
        DashboardMetric(
            metric_id="human_approval_controls",
            label="Human Approval Controls",
            value=f"{human_mode} @ {human_required_at}",
            status="OK" if not approval_blockers else "BLOCKED",
            blockers=approval_blockers,
        ),
        DashboardMetric(
            metric_id="live_gate",
            label="Live Gate",
            value=live_gate_status,
            status="BLOCKED",
            blockers=live_gate_blockers,
        ),
    )
    aggregate_blockers = tuple(
        dict.fromkeys(
            (
                *report_blockers,
                *contract_blockers,
                *guardrail_blockers,
                *approval_blockers,
                *live_gate_blockers,
            )
        )
    )
    return metrics, aggregate_blockers


def _status_metric(
    *,
    metric_id: str,
    label: str,
    value: str,
    signal: str,
    blockers: tuple[str, ...],
    unknown_blocker: str,
) -> DashboardMetric:
    normalized_signal = signal.strip().upper()
    if normalized_signal in {"READY", "PASSED", "OK"}:
        return DashboardMetric(metric_id, label, value, "OK")
    if normalized_signal in {"RUNNING_WITH_BLOCKERS", "RESEARCH_ONLY", "WATCH"}:
        return DashboardMetric(metric_id, label, value, "WATCH", blockers)
    if normalized_signal in {
        "DEGRADED",
        "BLOCKED",
        "LIVE_ORDER_BLOCKED",
        "FAILED",
        "ERROR",
    }:
        return DashboardMetric(
            metric_id,
            label,
            value,
            "BLOCKED",
            blockers if blockers else (normalized_signal,),
        )
    return DashboardMetric(metric_id, label, value, "UNKNOWN", (unknown_blocker,))


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    if isinstance(value, list | tuple):
        items = tuple(str(item).strip() for item in value)
        return tuple(item for item in items if item)
    return ()


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

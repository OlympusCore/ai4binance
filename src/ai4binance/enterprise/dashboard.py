"""Executive dashboard snapshot contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.enterprise.contracts import WorkflowIdentity


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


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

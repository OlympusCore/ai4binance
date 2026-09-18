"""Recovery candidate validation queue contracts kept research-only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai4binance.portfolio.opportunity_recovery import (
    OpportunityRecoveryRadar,
    RecoveryCandidate,
)
from ai4binance.research.backtesting.layout import load_backtest_layout_manifest


@dataclass(frozen=True, slots=True)
class RecoveryValidationWorkItem:
    work_id: str
    candidate_id: str
    symbol: str
    setup_name: str
    timeframe: str
    required_artifacts: tuple[str, ...]
    blockers: tuple[str, ...]
    priority: str = "P1"
    status: str = "QUEUED_RESEARCH_ONLY"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        required = (
            self.work_id,
            self.candidate_id,
            self.symbol,
            self.setup_name,
            self.timeframe,
            self.priority,
            self.status,
        )
        if any(not value.strip() for value in required):
            raise ValueError("recovery validation work item identity is required")
        for values in (self.required_artifacts, self.blockers):
            _require_unique_nonblank("recovery validation work item list", values)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("recovery validation work item cannot authorize trading")


@dataclass(frozen=True, slots=True)
class RecoveryValidationQueue:
    queue_id: str
    symbol: str
    items: tuple[RecoveryValidationWorkItem, ...]
    blockers: tuple[str, ...]
    artifact_root: Path | None = None
    command: str = "recovery-validation-queue"
    status: str = "QUEUED_WITH_BLOCKERS"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.queue_id.strip() or not self.symbol.strip():
            raise ValueError("recovery validation queue identity is required")
        if self.status not in {"READY", "QUEUED_WITH_BLOCKERS"}:
            raise ValueError("recovery validation queue status is invalid")
        _require_unique_nonblank("recovery validation queue blockers", self.blockers)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("recovery validation queue cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "command": self.command,
            "queue_id": self.queue_id,
            "symbol": self.symbol,
            "status": self.status,
            "items": [
                {
                    "work_id": item.work_id,
                    "candidate_id": item.candidate_id,
                    "symbol": item.symbol,
                    "setup_name": item.setup_name,
                    "timeframe": item.timeframe,
                    "required_artifacts": list(item.required_artifacts),
                    "blockers": list(item.blockers),
                    "priority": item.priority,
                    "status": item.status,
                    "execution_allowed": False,
                    "promotion_status": item.promotion_status,
                    "live_eligibility_status": item.live_eligibility_status,
                }
                for item in self.items
            ],
            "blockers": list(self.blockers),
            "artifact_root": str(self.artifact_root) if self.artifact_root else None,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_recovery_validation_queue(
    radar: OpportunityRecoveryRadar,
    *,
    artifact_root: Path | None = None,
    max_items: int = 5,
) -> RecoveryValidationQueue:
    """Create deterministic research work items for visible recovery candidates."""
    if max_items < 1:
        raise ValueError("recovery validation max_items must be positive")
    items = tuple(_work_item(candidate) for candidate in radar.ladder[:max_items])
    blockers = tuple(
        dict.fromkeys(
            (
                *(blocker for item in items for blocker in item.blockers),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    return RecoveryValidationQueue(
        queue_id=f"recovery-validation:{radar.symbol}",
        symbol=radar.symbol,
        items=items,
        blockers=blockers,
        artifact_root=artifact_root,
        status="READY" if not blockers else "QUEUED_WITH_BLOCKERS",
    )


def _work_item(candidate: RecoveryCandidate) -> RecoveryValidationWorkItem:
    artifacts = _required_artifacts(candidate)
    blockers = tuple(
        dict.fromkeys(
            (
                "RECOVERY_VALIDATION_ARTIFACTS_MISSING",
                "BACKTEST_APPROVAL_MISSING",
                "WALK_FORWARD_APPROVAL_MISSING",
                "OOS_APPROVAL_MISSING",
                "RISK_APPROVAL_MISSING",
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    return RecoveryValidationWorkItem(
        work_id=f"recovery-validation:{candidate.candidate_id}",
        candidate_id=candidate.candidate_id,
        symbol=candidate.symbol,
        setup_name=candidate.setup_name,
        timeframe=candidate.timeframe,
        required_artifacts=artifacts,
        blockers=blockers,
        priority=(
            "P0" if candidate.opportunity_grade in {"A_REVIEW", "B_REVIEW"} else "P1"
        ),
    )


def _required_artifacts(candidate: RecoveryCandidate) -> tuple[str, ...]:
    layout = load_backtest_layout_manifest()
    base = candidate.symbol
    setup = candidate.setup_name
    timeframe = candidate.timeframe
    return (
        f"{layout.validation_root}/{base}/{timeframe}/{setup}.jsonl",
        f"{layout.walk_forward_root}/{base}/{timeframe}/{setup}.json",
        f"{layout.oos_root}/{base}/{timeframe}/{setup}.json",
        f"{layout.robustness_root}/{base}/{timeframe}/{setup}.json",
    )


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

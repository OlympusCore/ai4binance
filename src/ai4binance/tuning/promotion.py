"""Human-only promotion board and revision-guarded production parameters."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai4binance.domain import ValidationStatus
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.strategies.registry import PlaybookRegistry
from ai4binance.tuning.models import TuningReport
from ai4binance.validation.artifacts import (
    StrategyApprovalArtifact,
    ValidationArtifactRegistry,
)
from ai4binance.validation.models import ParameterSet


@dataclass(frozen=True, slots=True)
class HumanApproval:
    approval_id: str
    approver: str
    approved_at: datetime
    tuning_report_id: str
    parameters: ParameterSet
    target_status: ValidationStatus = ValidationStatus.PAPER_APPROVED

    def __post_init__(self) -> None:
        if not self.approval_id.strip() or not self.approver.strip():
            raise ValueError("approval identity is required")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("approval timestamp must be timezone-aware")
        if self.target_status is not ValidationStatus.PAPER_APPROVED:
            raise ValueError("promotion board cannot approve live eligibility")


@dataclass(frozen=True, slots=True)
class StrategyPromotionTarget:
    playbook: str
    strategy_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (self.playbook, self.strategy_version, self.config_hash)
        ):
            raise ValueError("strategy promotion target identity is required")


@dataclass(frozen=True, slots=True)
class StrategyPromotionResult:
    registry: PlaybookRegistry
    approval_registry: ValidationArtifactRegistry
    artifact: StrategyApprovalArtifact


@dataclass(frozen=True, slots=True)
class PromotionBoard:
    store: JsonlAuditStore

    def record(self, report: TuningReport, approval: HumanApproval) -> None:
        self._validate(report, approval)
        self.store.append_verified(
            AuditEvent(
                event_type="PARAMETER_PROMOTION_APPROVED",
                timestamp=approval.approved_at,
                payload={"approval": to_primitive(approval)},
            )
        )

    def apply_to_strategy_registry(
        self,
        report: TuningReport,
        approval: HumanApproval,
        target: StrategyPromotionTarget,
        registry: PlaybookRegistry,
        approval_registry: ValidationArtifactRegistry | None = None,
    ) -> StrategyPromotionResult:
        """Record human approval and return immutable paper-governed registries."""
        self._validate(report, approval)
        playbook = registry.get(target.playbook)
        if not playbook.implemented:
            raise ValueError("only implemented playbooks may be promoted")
        artifact = StrategyApprovalArtifact(
            approval_id=approval.approval_id,
            approved_at=approval.approved_at,
            symbol=report.symbol,
            timeframe=report.timeframe,
            playbook=target.playbook,
            strategy_version=target.strategy_version,
            config_hash=target.config_hash,
            status=approval.target_status,
        )
        current_approvals = approval_registry or ValidationArtifactRegistry()
        if any(
            item.playbook == artifact.playbook
            and item.symbol.upper() == artifact.symbol.upper()
            and item.timeframe == artifact.timeframe
            and item.strategy_version == artifact.strategy_version
            and item.config_hash == artifact.config_hash
            for item in current_approvals.artifacts
        ):
            raise ValueError("strategy approval artifact already exists")
        next_approvals = ValidationArtifactRegistry(
            (*current_approvals.artifacts, artifact)
        )
        next_registry = registry.with_promotion(
            target.playbook,
            approval.target_status,
        )
        self.store.append_verified(
            AuditEvent(
                event_type="STRATEGY_PROMOTION_APPROVED",
                timestamp=approval.approved_at,
                payload={
                    "approval": to_primitive(approval),
                    "target": to_primitive(target),
                    "artifact": to_primitive(artifact),
                },
            )
        )
        return StrategyPromotionResult(next_registry, next_approvals, artifact)

    @staticmethod
    def _validate(report: TuningReport, approval: HumanApproval) -> None:
        if report.promotion_status is not ValidationStatus.STAGED_CANDIDATE:
            raise ValueError("only staged tuning reports may be approved")
        if approval.tuning_report_id != report.report_id:
            raise ValueError("approval and tuning report IDs must match")
        if approval.parameters != report.selected_parameters:
            raise ValueError("approval parameters must match selected parameters")


@dataclass(frozen=True, slots=True)
class GovernedParameterStore:
    """Activate paper parameters only with approval and revision matching."""

    path: Path

    def activate(
        self,
        report: TuningReport,
        approval: HumanApproval,
        *,
        expected_revision: int,
    ) -> int:
        PromotionBoard._validate(report, approval)
        current_revision = self.current_revision()
        if expected_revision != current_revision:
            raise ValueError("parameter revision conflict")
        next_revision = current_revision + 1
        payload = {
            "revision": next_revision,
            "status": ValidationStatus.PAPER_APPROVED.value,
            "tuning_report_id": report.report_id,
            "approval_id": approval.approval_id,
            "parameters": dict(report.selected_parameters.values),
        }
        write_json_object_verified(
            self.path,
            payload,
            blocker="GOVERNED_PARAMETER_DESTINATION_VERIFY_FAILED",
            subject_id=approval.approval_id,
            indent=2,
        )
        return next_revision

    def current_revision(self) -> int:
        if not self.path.exists():
            return 0
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        revision = payload.get("revision")
        if not isinstance(revision, int) or revision < 1:
            raise ValueError("stored parameter revision is invalid")
        return revision

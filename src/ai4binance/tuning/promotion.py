"""Human-only promotion board and revision-guarded production parameters."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai4binance.domain import ValidationStatus
from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    canonical_trace_journal_path,
    canonical_trace_sha256,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.strategies.registry import (
    GovernedStrategyRegistry,
    PlaybookRegistry,
    build_governed_strategy_registry,
)
from ai4binance.tuning.models import TuningReport
from ai4binance.validation.artifacts import (
    StrategyApprovalArtifact,
    ValidationArtifactRegistry,
)
from ai4binance.validation.models import ParameterSet
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceLedger,
    PromotionEvidenceRecord,
    PromotionEvidenceSourceKind,
)


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
    governed_registry: GovernedStrategyRegistry


@dataclass(frozen=True, slots=True)
class PromotionBoard:
    store: JsonlAuditStore
    evidence_ledger: PromotionEvidenceLedger | None = None
    trace_journal: CanonicalTraceJournal | None = None

    def __post_init__(self) -> None:
        if self.trace_journal is None:
            object.__setattr__(
                self,
                "trace_journal",
                CanonicalTraceJournal(
                    canonical_trace_journal_path(self.store.path.resolve().parent)
                ),
            )

    def record(self, report: TuningReport, approval: HumanApproval) -> None:
        self._validate(report, approval)
        self.store.append_verified(
            AuditEvent(
                event_type="PARAMETER_PROMOTION_APPROVED",
                timestamp=approval.approved_at,
                payload={"approval": to_primitive(approval)},
            )
        )
        self._append_promotion_evidence(
            PromotionEvidenceRecord(
                evidence_id=f"approval:{approval.approval_id}:{report.report_id}",
                symbol=report.symbol,
                source_kind=PromotionEvidenceSourceKind.MANUAL_REVIEW,
                source_ref=report.report_id,
                observed_at=approval.approved_at,
                promotion_status=approval.target_status,
                timeframe=report.timeframe,
            )
        )
        self._record_approval_trace(report, approval)

    def apply_to_strategy_registry(
        self,
        report: TuningReport,
        approval: HumanApproval,
        target: StrategyPromotionTarget,
        registry: PlaybookRegistry,
        approval_registry: ValidationArtifactRegistry | None = None,
        governed_registry: GovernedStrategyRegistry | None = None,
    ) -> StrategyPromotionResult:
        """Record human approval and return immutable paper-governed registries."""
        self._validate(report, approval)
        playbook = registry.get(target.playbook)
        if not playbook.implemented:
            raise ValueError("only implemented playbooks may be promoted")
        current_governed = governed_registry or build_governed_strategy_registry()
        governed_entry = current_governed.resolve_playbook(target.playbook)
        if not governed_entry.evidence_complete:
            raise ValueError(
                "strategy family remains RESEARCH_ONLY until backtest, "
                "walk-forward, OOS, robustness, and paper evidence are bound"
            )
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
        next_governed = current_governed.with_promotion(
            governed_entry.strategy_id,
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
                    "strategy_family": governed_entry.strategy_id,
                },
            )
        )
        self._append_promotion_evidence(
            PromotionEvidenceRecord(
                evidence_id=(
                    f"strategy:{approval.approval_id}:{target.playbook}:"
                    f"{target.strategy_version}:{target.config_hash}"
                ),
                symbol=report.symbol,
                source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
                source_ref=(
                    f"{target.playbook}:{target.strategy_version}:{target.config_hash}"
                ),
                observed_at=approval.approved_at,
                promotion_status=approval.target_status,
                timeframe=report.timeframe,
            )
        )
        self._record_strategy_promotion_trace(report, approval, artifact)
        return StrategyPromotionResult(
            next_registry,
            next_approvals,
            artifact,
            next_governed,
        )

    @staticmethod
    def _validate(report: TuningReport, approval: HumanApproval) -> None:
        if report.promotion_status is not ValidationStatus.STAGED_CANDIDATE:
            raise ValueError("only staged tuning reports may be approved")
        if approval.tuning_report_id != report.report_id:
            raise ValueError("approval and tuning report IDs must match")
        if approval.parameters != report.selected_parameters:
            raise ValueError("approval parameters must match selected parameters")

    def _append_promotion_evidence(self, record: PromotionEvidenceRecord) -> None:
        if self.evidence_ledger is None:
            return
        self.evidence_ledger.append_if_absent(record)

    def _record_approval_trace(
        self,
        report: TuningReport,
        approval: HumanApproval,
    ) -> None:
        if self.trace_journal is None:
            return
        self.trace_journal.append_if_absent(
            CanonicalTraceRecord.create(
                trace_id=f"trace:approval:{approval.approval_id}:{report.report_id}",
                trace_kind=ConsequentialTraceKind.APPROVAL,
                subject_ref=approval.approval_id,
                subject_type="PARAMETER_PROMOTION_APPROVAL",
                occurred_at=approval.approved_at,
                event_name="PARAMETER_PROMOTION_APPROVED",
                event_status=approval.target_status.value,
                evidence_refs=(report.report_id,),
                related_refs=(
                    report.symbol,
                    report.timeframe,
                    approval.tuning_report_id,
                ),
                approval_ref=approval.approval_id,
                subject_sha256=canonical_trace_sha256(to_primitive(approval)),
            )
        )

    def _record_strategy_promotion_trace(
        self,
        report: TuningReport,
        approval: HumanApproval,
        artifact: StrategyApprovalArtifact,
    ) -> None:
        if self.trace_journal is None:
            return
        self.trace_journal.append_if_absent(
            CanonicalTraceRecord.create(
                trace_id=(
                    "trace:promotion:"
                    f"{approval.approval_id}:{artifact.playbook}:"
                    f"{artifact.strategy_version}:{artifact.config_hash}"
                ),
                trace_kind=ConsequentialTraceKind.PROMOTION_CANDIDATE,
                subject_ref=(
                    f"{artifact.playbook}:{artifact.strategy_version}:"
                    f"{artifact.config_hash}"
                ),
                subject_type="STRATEGY_PROMOTION_ARTIFACT",
                occurred_at=approval.approved_at,
                event_name="STRATEGY_PROMOTION_APPROVED",
                event_status=artifact.status.value,
                evidence_refs=(approval.approval_id, report.report_id),
                related_refs=(artifact.symbol, artifact.timeframe, artifact.playbook),
                approval_ref=approval.approval_id,
                subject_sha256=canonical_trace_sha256(to_primitive(artifact)),
            )
        )


@dataclass(frozen=True, slots=True)
class GovernedParameterStore:
    """Activate paper parameters only with approval and revision matching."""

    path: Path
    trace_journal: CanonicalTraceJournal | None = None

    def __post_init__(self) -> None:
        if self.trace_journal is None:
            object.__setattr__(
                self,
                "trace_journal",
                CanonicalTraceJournal(
                    canonical_trace_journal_path(self.path.resolve().parent)
                ),
            )

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
        self._record_parameter_activation_trace(report, approval, payload)
        return next_revision

    def current_revision(self) -> int:
        if not self.path.exists():
            return 0
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        revision = payload.get("revision")
        if not isinstance(revision, int) or revision < 1:
            raise ValueError("stored parameter revision is invalid")
        return revision

    def _record_parameter_activation_trace(
        self,
        report: TuningReport,
        approval: HumanApproval,
        payload: dict[str, object],
    ) -> None:
        if self.trace_journal is None:
            return
        path_ref = str(self.path.resolve())
        self.trace_journal.append_if_absent(
            CanonicalTraceRecord.create(
                trace_id=(
                    "trace:config-change:"
                    f"{approval.approval_id}:{payload['revision']}:"
                    f"{canonical_trace_sha256(path_ref)[:12]}"
                ),
                trace_kind=ConsequentialTraceKind.CONFIG_CHANGE,
                subject_ref=path_ref,
                subject_type="GOVERNED_PARAMETER_STORE",
                occurred_at=approval.approved_at,
                event_name="GOVERNED_PARAMETER_ACTIVATED",
                event_status=ValidationStatus.PAPER_APPROVED.value,
                evidence_refs=(approval.approval_id, report.report_id),
                related_refs=(
                    report.symbol,
                    report.timeframe,
                    f"revision:{payload['revision']}",
                ),
                governed_paths=(path_ref,),
                approval_ref=approval.approval_id,
                subject_sha256=canonical_trace_sha256(payload),
            )
        )

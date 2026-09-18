"""Append-only persistence for walk-forward validation evidence."""

from dataclasses import dataclass

from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.validation.models import WalkForwardReport


def _walk_forward_report_audit_payload(
    report: WalkForwardReport,
) -> dict[str, object]:
    """Render complete decision evidence without duplicating trade ledgers."""

    return {
        "report_id": report.report_id,
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "created_at": report.created_at,
        "config": report.config,
        "folds": tuple(
            {
                "fold_index": fold.fold_index,
                "train_started_at": fold.train_started_at,
                "train_ended_at": fold.train_ended_at,
                "test_started_at": fold.test_started_at,
                "test_ended_at": fold.test_ended_at,
                "selected_parameters": fold.selected_parameters,
                "training_objective": fold.training_objective,
                "training_metrics": fold.training_result.metrics,
                "oos_metrics": fold.oos_result.metrics,
            }
            for fold in report.folds
        ),
        "regime_performance": report.regime_performance,
        "robustness": report.robustness,
        "statistical_evidence": report.statistical_evidence,
        "oos_validation_status": report.oos_validation_status,
        "promotion_status": report.promotion_status,
        "blockers": report.blockers,
        "detail_level": "BOUNDED_SUMMARY",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


@dataclass(frozen=True, slots=True)
class WalkForwardAuditWriter:
    """Persist bounded validation decision evidence through the audit store."""

    store: JsonlAuditStore

    def append(self, report: WalkForwardReport) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="WALK_FORWARD_REPORT",
                timestamp=report.created_at,
                payload={
                    "report": to_primitive(_walk_forward_report_audit_payload(report))
                },
            )
        )

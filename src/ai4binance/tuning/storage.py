"""Append-only tuning experiment persistence."""

from dataclasses import dataclass

from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.tuning.models import StrategyParameterTournamentReport, TuningReport


def _tuning_report_audit_payload(report: TuningReport) -> dict[str, object]:
    """Render bounded tuning evidence without duplicating full backtest ledgers."""

    return {
        "report_id": report.report_id,
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "created_at": report.created_at,
        "search_space": report.search_space,
        "config": report.config,
        "selected_parameters": report.selected_parameters,
        "sensitivity": report.sensitivity,
        "promotion_status": report.promotion_status,
        "blockers": report.blockers,
        "detail_level": "BOUNDED_SUMMARY",
        "evaluations": tuple(
            {
                "parameters": evaluation.parameters,
                "objective": evaluation.objective,
                "walk_forward": {
                    "report_id": evaluation.walk_forward_report.report_id,
                    "created_at": evaluation.walk_forward_report.created_at,
                    "folds": tuple(
                        {
                            "fold_index": fold.fold_index,
                            "train_started_at": fold.train_started_at,
                            "train_ended_at": fold.train_ended_at,
                            "test_started_at": fold.test_started_at,
                            "test_ended_at": fold.test_ended_at,
                            "selected_parameters": fold.selected_parameters,
                            "training_metrics": fold.training_result.metrics,
                            "oos_metrics": fold.oos_result.metrics,
                        }
                        for fold in evaluation.walk_forward_report.folds
                    ),
                    "regime_performance": (
                        evaluation.walk_forward_report.regime_performance
                    ),
                    "robustness": evaluation.walk_forward_report.robustness,
                    "statistical_evidence": (
                        evaluation.walk_forward_report.statistical_evidence
                    ),
                    "oos_validation_status": (
                        evaluation.walk_forward_report.oos_validation_status
                    ),
                    "promotion_status": evaluation.walk_forward_report.promotion_status,
                    "blockers": evaluation.walk_forward_report.blockers,
                },
            }
            for evaluation in report.evaluations
        ),
    }


@dataclass(frozen=True, slots=True)
class TuningAuditWriter:
    store: JsonlAuditStore

    def append(self, report: TuningReport) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="TUNING_REPORT",
                timestamp=report.created_at,
                payload={"report": to_primitive(_tuning_report_audit_payload(report))},
            )
        )


@dataclass(frozen=True, slots=True)
class StrategyParameterTournamentAuditWriter:
    store: JsonlAuditStore

    def append(self, report: StrategyParameterTournamentReport) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="STRATEGY_PARAMETER_TOURNAMENT_REPORT",
                timestamp=report.created_at,
                payload={"report": to_primitive(report)},
            )
        )

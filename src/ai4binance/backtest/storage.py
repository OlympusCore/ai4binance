"""Append-only persistence for complete backtest audit results."""

from dataclasses import dataclass
from datetime import datetime

from ai4binance.backtest.models import BacktestResult
from ai4binance.backtest.robustness import BacktestRobustnessReport
from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class BacktestAuditWriter:
    """Persist a result and its lifecycle events without secret leakage."""

    store: JsonlAuditStore

    def append(self, result: BacktestResult) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="BACKTEST_RESULT",
                timestamp=result.ended_at,
                payload={"result": to_primitive(result)},
            )
        )


@dataclass(frozen=True, slots=True)
class BacktestRobustnessWriter:
    """Persist deterministic stress and bootstrap evidence."""

    store: JsonlAuditStore

    def append(self, report: BacktestRobustnessReport, timestamp: datetime) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="BACKTEST_ROBUSTNESS_REPORT",
                timestamp=timestamp,
                payload={"report": to_primitive(report)},
            )
        )

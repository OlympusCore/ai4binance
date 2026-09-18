"""Append-only persistence for complete backtest audit results."""

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting.models import BacktestResult
from ai4binance.research.backtesting.robustness import BacktestRobustnessReport
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _bounded_backtest_payload(
    result: BacktestResult,
    *,
    full_result: object,
) -> dict[str, object]:
    collections = {
        "trades": result.trades,
        "rejected_signals": result.rejected_signals,
        "audit_events": result.audit_events,
        "equity_curve": result.equity_curve,
        "false_breakouts": result.false_breakouts,
        "trade_outcomes": result.trade_outcomes,
        "missed_opportunity_records": result.missed_opportunity_ledger.records,
        "pre_veto_opportunity_records": result.pre_veto_opportunity_ledger.records,
    }
    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "assumptions": result.assumptions,
        "no_trade_count": result.no_trade_count,
        "metrics": result.metrics,
        "funnel_telemetry": result.funnel_telemetry,
        "trade_edge_ledger": result.trade_edge_ledger,
        "performance_engine_report": result.performance_engine_report,
        "detail_level": "BOUNDED_SUMMARY",
        "full_result_sha256": _canonical_sha256(full_result),
        "collection_counts": {name: len(items) for name, items in collections.items()},
        "collection_sha256": {
            name: _canonical_sha256(to_primitive(items))
            for name, items in collections.items()
        },
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


@dataclass(frozen=True, slots=True)
class BacktestAuditWriter:
    """Persist full or hash-bound bounded result evidence without secrets."""

    store: JsonlAuditStore

    def append(self, result: BacktestResult) -> None:
        full_result = to_primitive(result)
        full_payload_size = len(
            json.dumps(
                {"result": full_result},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
        )
        persisted_result = (
            full_result
            if full_payload_size <= self.store.max_event_bytes * 3 // 4
            else to_primitive(
                _bounded_backtest_payload(
                    result,
                    full_result=full_result,
                )
            )
        )
        self.store.append_verified(
            AuditEvent(
                event_type="BACKTEST_RESULT",
                timestamp=result.ended_at,
                payload={"result": persisted_result},
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

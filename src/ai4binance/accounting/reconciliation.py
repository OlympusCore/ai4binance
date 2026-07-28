"""File-backed REST/WebSocket reconciliation for accounting ledgers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from ai4binance.accounting.records import (
    BinanceAccountLedger,
    ProductType,
    ReconciliationResultRecord,
    SourceType,
)


@dataclass(frozen=True, slots=True)
class FileReconciliationSummary:
    accepted_count: int
    duplicate_count: int
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def status(self) -> str:
        return "CLEAN" if not self.blockers else "DEGRADED"


@dataclass(frozen=True, slots=True)
class AccountingFileReconciler:
    """Reconcile latest REST snapshots against WebSocket evidence on disk."""

    ledger: BinanceAccountLedger
    freshness_seconds: int

    def reconcile_latest(
        self,
        *,
        snapshot_id: str,
        sync_run_id: str,
        observed_at: datetime,
    ) -> FileReconciliationSummary:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("reconciliation timestamp must be timezone-aware")
        accepted = 0
        duplicates = 0
        blockers: list[str] = []
        records = [
            *self._stream_health_records(observed_at),
            *self._spot_order_records(observed_at),
            *self._futures_order_records(observed_at),
            *self._futures_position_records(observed_at),
        ]
        for record in records:
            if self.ledger.append_reconciliation_result(
                record,
                snapshot_id=snapshot_id,
                sync_run_id=sync_run_id,
                source_type=SourceType.DERIVED,
            ):
                accepted += 1
            else:
                duplicates += 1
            if record.severity not in {"OK"}:
                blockers.extend(record.data_quality_issues)
        return FileReconciliationSummary(
            accepted,
            duplicates,
            tuple(dict.fromkeys(blockers)),
        )

    def _stream_health_records(
        self,
        observed_at: datetime,
    ) -> tuple[ReconciliationResultRecord, ...]:
        raw_events = _read_events(self.ledger.root / "shared" / "raw_api_events.jsonl")
        records: list[ReconciliationResultRecord] = []
        for product in (ProductType.SPOT, ProductType.FUTURES_USDM):
            rest_seen = _latest_source_at(raw_events, product, "REST")
            ws_seen = _latest_source_at(raw_events, product, "WEBSOCKET")
            issues: list[str] = []
            if rest_seen is None or _stale(
                rest_seen,
                observed_at,
                self.freshness_seconds,
            ):
                issues.append(f"{product.value}_REST_EVIDENCE_MISSING_OR_STALE")
            if ws_seen is None or _stale(
                ws_seen,
                observed_at,
                self.freshness_seconds,
            ):
                issues.append(f"{product.value}_WEBSOCKET_EVIDENCE_MISSING_OR_STALE")
            records.append(
                ReconciliationResultRecord(
                    product_type=product,
                    entity_type="STREAM_HEALTH",
                    entity_id=product.value,
                    rest_value=rest_seen.isoformat() if rest_seen is not None else None,
                    stream_value=ws_seen.isoformat() if ws_seen is not None else None,
                    difference=tuple(issues),
                    severity="OK" if not issues else "BLOCKED",
                    reconciled_at=observed_at,
                    resolution=(
                        "NO_ACTION" if not issues else "START_OR_REPLAY_COLLECTORS"
                    ),
                    data_quality_issues=tuple(issues),
                )
            )
        return tuple(records)

    def _spot_order_records(
        self,
        observed_at: datetime,
    ) -> tuple[ReconciliationResultRecord, ...]:
        rest = _latest_by_id(
            self.ledger.root / "spot" / "orders.jsonl",
            id_field="order_id",
            value_field="status",
        )
        stream = _latest_by_id(
            self.ledger.root / "spot" / "order_events.jsonl",
            id_field="order_id",
            value_field="order_status",
        )
        return tuple(
            _compare_entity(
                ProductType.SPOT,
                "ORDER_STATUS",
                key,
                rest.get(key),
                stream.get(key),
                observed_at,
            )
            for key in sorted(set(rest) & set(stream))
        )

    def _futures_order_records(
        self,
        observed_at: datetime,
    ) -> tuple[ReconciliationResultRecord, ...]:
        rest = _latest_by_id(
            self.ledger.root / "futures_usdm" / "orders.jsonl",
            id_field="order_id",
            value_field="status",
        )
        stream = _latest_by_id(
            self.ledger.root / "futures_usdm" / "order_events.jsonl",
            id_field="order_id",
            value_field="order_status",
        )
        return tuple(
            _compare_entity(
                ProductType.FUTURES_USDM,
                "ORDER_STATUS",
                key,
                rest.get(key),
                stream.get(key),
                observed_at,
            )
            for key in sorted(set(rest) & set(stream))
        )

    def _futures_position_records(
        self,
        observed_at: datetime,
    ) -> tuple[ReconciliationResultRecord, ...]:
        rest = _latest_position_amounts(
            self.ledger.root / "futures_usdm" / "positions_current.jsonl",
            value_field="position_amt",
        )
        stream = _latest_position_amounts(
            self.ledger.root / "futures_usdm" / "position_events.jsonl",
            value_field="new_position_amt",
        )
        return tuple(
            _compare_entity(
                ProductType.FUTURES_USDM,
                "POSITION_AMOUNT",
                key,
                rest.get(key),
                stream.get(key),
                observed_at,
            )
            for key in sorted(set(rest) & set(stream))
        )


def _compare_entity(
    product_type: ProductType,
    entity_type: str,
    entity_id: str,
    rest_value: object,
    stream_value: object,
    observed_at: datetime,
) -> ReconciliationResultRecord:
    issues: list[str] = []
    if rest_value != stream_value:
        issues.append(f"{entity_type}_REST_WEBSOCKET_MISMATCH")
    return ReconciliationResultRecord(
        product_type=product_type,
        entity_type=entity_type,
        entity_id=entity_id,
        rest_value=rest_value,
        stream_value=stream_value,
        difference=_difference(rest_value, stream_value),
        severity="OK" if not issues else "WARNING",
        reconciled_at=observed_at,
        resolution="NO_ACTION" if not issues else "REST_REPLAY_REQUIRED",
        data_quality_issues=tuple(issues),
    )


def _difference(rest_value: object, stream_value: object) -> object:
    rest_decimal = _optional_decimal(rest_value)
    stream_decimal = _optional_decimal(stream_value)
    if rest_decimal is not None and stream_decimal is not None:
        return rest_decimal - stream_decimal
    return () if rest_value == stream_value else (rest_value, stream_value)


def _latest_by_id(path: Path, *, id_field: str, value_field: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for payload in _payloads(path):
        entity_id = payload.get(id_field)
        if isinstance(entity_id, str) and entity_id.strip():
            values[entity_id] = payload.get(value_field)
    return values


def _latest_position_amounts(path: Path, *, value_field: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for payload in _payloads(path):
        symbol = payload.get("symbol")
        side = payload.get("position_side")
        if isinstance(symbol, str) and isinstance(side, str):
            values[f"{symbol}:{side}"] = payload.get(value_field)
    return values


def _payloads(path: Path) -> Iterable[dict[str, object]]:
    for event in _read_events(path):
        payload = event.get("payload")
        if isinstance(payload, dict):
            yield cast(dict[str, object], payload)


def _read_events(path: Path, *, limit: int = 500) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    events: list[dict[str, object]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            events.append(cast(dict[str, object], loaded))
    return tuple(events)


def _latest_source_at(
    events: Iterable[dict[str, object]],
    product_type: ProductType,
    source_type: str,
) -> datetime | None:
    latest: datetime | None = None
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            continue
        if envelope.get("product_type") != product_type.value:
            continue
        if envelope.get("source_type") != source_type:
            continue
        timestamp = _parse_time(payload.get("received_at") or event.get("timestamp"))
        if timestamp is not None and (latest is None or timestamp > latest):
            latest = timestamp
    return latest


def _stale(value: datetime, observed_at: datetime, freshness_seconds: int) -> bool:
    return (observed_at - value).total_seconds() > freshness_seconds


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None

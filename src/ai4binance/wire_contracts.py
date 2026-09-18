"""Boundary adapters between immutable Python contracts and JSON wire contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import cast

from ai4binance.governance.evidence_contracts import GovernedArtifactEvidence
from ai4binance.governance.execution_envelope import ExecutionEnvelope
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle


def _wire_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(key): _wire_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(child) for child in value]
    return value


def market_snapshot_to_wire(snapshot: MarketSnapshot) -> dict[str, object]:
    """Serialize a MarketSnapshot without losing decimal precision."""

    ohlcv_by_timeframe: dict[str, list[dict[str, object]]] = {}
    for timeframe, candles in snapshot.ohlcv_by_timeframe.items():
        ohlcv_by_timeframe[timeframe] = [
            {
                "timestamp": _wire_value(candle.timestamp),
                "open": _wire_value(candle.open),
                "high": _wire_value(candle.high),
                "low": _wire_value(candle.low),
                "close": _wire_value(candle.close),
                "volume": _wire_value(candle.volume),
            }
            for candle in candles
        ]
    return {
        "schema_version": "1.0.0",
        "snapshot_id": snapshot.snapshot_id,
        "created_at": _wire_value(snapshot.created_at),
        "exchange": snapshot.exchange,
        "market_type": snapshot.market_type,
        "symbol": snapshot.symbol,
        "timeframes": list(snapshot.timeframes),
        "ohlcv_by_timeframe": ohlcv_by_timeframe,
        "latest_price": _wire_value(snapshot.latest_price),
        "bid": _wire_value(snapshot.bid),
        "ask": _wire_value(snapshot.ask),
        "spread": _wire_value(snapshot.spread),
        "server_time": _wire_value(snapshot.server_time),
        "data_quality": snapshot.data_quality.value,
        "data_freshness": _wire_value(snapshot.data_freshness),
    }


def _parse_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a timestamp string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _optional_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a decimal string or null")
    return Decimal(value)


def market_snapshot_from_wire(payload: Mapping[str, object]) -> MarketSnapshot:
    """Deserialize a schema-validated MarketSnapshot wire payload."""

    raw_candles = cast(
        Mapping[str, Sequence[Mapping[str, object]]], payload["ohlcv_by_timeframe"]
    )
    candles = {
        timeframe: tuple(
            OHLCVCandle(
                timestamp=_parse_datetime(item["timestamp"], "timestamp"),
                open=Decimal(cast(str, item["open"])),
                high=Decimal(cast(str, item["high"])),
                low=Decimal(cast(str, item["low"])),
                close=Decimal(cast(str, item["close"])),
                volume=Decimal(cast(str, item["volume"])),
            )
            for item in entries
        )
        for timeframe, entries in raw_candles.items()
    }
    return MarketSnapshot(
        snapshot_id=cast(str, payload["snapshot_id"]),
        created_at=_parse_datetime(payload["created_at"], "created_at"),
        exchange=cast(str, payload["exchange"]),
        market_type=cast(str, payload["market_type"]),
        symbol=cast(str, payload["symbol"]),
        timeframes=tuple(cast(Sequence[str], payload["timeframes"])),
        ohlcv_by_timeframe=candles,
        latest_price=_optional_decimal(payload["latest_price"], "latest_price"),
        bid=_optional_decimal(payload["bid"], "bid"),
        ask=_optional_decimal(payload["ask"], "ask"),
        spread=_optional_decimal(payload["spread"], "spread"),
        server_time=(
            _parse_datetime(payload["server_time"], "server_time")
            if payload["server_time"] is not None
            else None
        ),
        data_quality=DataQuality(cast(str, payload["data_quality"])),
        data_freshness=cast(Mapping[str, object], payload["data_freshness"]),
    )


def governed_artifact_evidence_to_wire(
    evidence: GovernedArtifactEvidence,
) -> dict[str, object]:
    """Serialize advisory artifact evidence with its hard no-live invariant."""

    return {
        "schema_version": "1.0.0",
        "artifact_type": evidence.artifact_type,
        "generated_at": _wire_value(evidence.generated_at),
        "source_artifact": evidence.source_artifact,
        "source_sha256": evidence.source_sha256,
        "freshness_status": evidence.freshness_status,
        "blockers": list(evidence.blockers),
        "data": _wire_value(evidence.data),
        "execution_allowed": evidence.execution_allowed,
        "live_eligibility_status": evidence.live_eligibility_status,
    }


def execution_envelope_to_wire(envelope: ExecutionEnvelope) -> dict[str, object]:
    """Serialize an execution envelope without widening external authority."""

    return {
        "schema_version": "1.0.0",
        "authority_profile_id": envelope.authority_profile_id,
        "execution_surface": envelope.execution_surface.value,
        "automation_mode": envelope.automation_mode.value,
        "manual_confirmation_required": envelope.manual_confirmation_required,
        "virtual_simulation_allowed": envelope.virtual_simulation_allowed,
        "auto_simulation_allowed": envelope.auto_simulation_allowed,
        "paper_execution_allowed": envelope.paper_execution_allowed,
        "external_order_allowed": envelope.external_order_allowed,
        "live_order_allowed": envelope.live_order_allowed,
        "bounded_simulation_only": envelope.bounded_simulation_only,
        "reason_codes": list(envelope.reason_codes),
    }

"""Draft 2020-12 validation and Python parity for the MarketSnapshot boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.governance.evidence_contracts import GovernedArtifactEvidence
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.governance.execution_envelope import execution_envelope_for_surface
from ai4binance.schema_validation import (
    OfflineSchemaRegistry,
    SchemaValidationError,
    compare_object_schema_compatibility,
    validate_contract_schema_mappings,
)
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.wire_contracts import (
    execution_envelope_to_wire,
    governed_artifact_evidence_to_wire,
    market_snapshot_from_wire,
    market_snapshot_to_wire,
)

MARKET_SNAPSHOT_SCHEMA_ID = "urn:ai4binance:schema:snapshots:market-snapshot:1.0.0"
SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"


def _snapshot() -> MarketSnapshot:
    candle = OHLCVCandle(
        timestamp=datetime(2026, 9, 2, tzinfo=UTC),
        open=Decimal("65000.01000000"),
        high=Decimal("66000"),
        low=Decimal("64000"),
        close=Decimal("65500.12500000"),
        volume=Decimal("42.10000000"),
    )
    return MarketSnapshot(
        snapshot_id="snapshot-1",
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
        exchange="Binance",
        market_type="SPOT",
        symbol="BTCUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": (candle,)},
        latest_price=Decimal("65500.12500000"),
        bid=Decimal("65500.12000000"),
        ask=Decimal("65500.13000000"),
        spread=Decimal("0.01000000"),
        data_quality=DataQuality.DATA_VALID,
        data_freshness={"1h": {"stale": False}},
    )


def test_registry_meta_validates_all_local_schemas_and_rejects_network_references(
    tmp_path: Path,
) -> None:
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    registered_ids = {schema.schema_id for schema in registry.schemas}
    assert MARKET_SNAPSHOT_SCHEMA_ID in registered_ids
    validate_contract_schema_mappings(registry)

    invalid = tmp_path / "invalid.schema.json"
    invalid.write_text(
        '{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:ai4binance:schema:test:invalid:1.0.0","$ref":"https://example.test/remote.schema.json"}',
        encoding="utf-8",
    )
    with pytest.raises(SchemaValidationError, match="network schema reference"):
        OfflineSchemaRegistry.from_directory(tmp_path)


def test_market_snapshot_wire_contract_round_trips_with_decimal_precision() -> None:
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    snapshot = _snapshot()
    payload = market_snapshot_to_wire(snapshot)

    registry.validate(MARKET_SNAPSHOT_SCHEMA_ID, payload)
    restored = market_snapshot_from_wire(payload)

    assert restored == snapshot
    assert payload["latest_price"] == "65500.12500000"


def test_market_snapshot_wire_contract_enforces_timestamp_format_and_closed_shape() -> (
    None
):
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    payload = market_snapshot_to_wire(_snapshot())
    payload["created_at"] = "not-a-timestamp"
    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        registry.validate(MARKET_SNAPSHOT_SCHEMA_ID, payload)


def test_schema_dependency_scope_and_closed_object_compatibility_are_fail_closed() -> (
    None
):
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    affected = registry.affected_schema_ids(
        ("schemas/primitives/temporal_primitives.schema.json",)
    )
    assert MARKET_SNAPSHOT_SCHEMA_ID in affected

    previous = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}},
    }
    current = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "new_optional": {"type": "string"},
        },
    }
    result = compare_object_schema_compatibility(
        previous,
        current,
    )
    assert result.forward_read_compatible is True
    assert result.backward_read_compatible is False
    assert "optional fields reject older closed consumers" in result.breaking_changes


def test_evidence_and_execution_wire_contracts_preserve_no_live_authority() -> None:
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    evidence = GovernedArtifactEvidence(
        artifact_type="quality_triage",
        generated_at=datetime(2026, 9, 2, tzinfo=UTC),
        source_artifact="runtime/artifacts/quality_triage/state.json",
        source_sha256="a" * 64,
        freshness_status="FRESH",
        blockers=(),
    )
    envelope = execution_envelope_for_surface(ExecutionSurface.BINANCE_MARKET)

    evidence_payload = governed_artifact_evidence_to_wire(evidence)
    envelope_payload = execution_envelope_to_wire(envelope)

    registry.validate(
        "urn:ai4binance:schema:evidence:evidence-bundle:1.0.0",
        evidence_payload,
    )
    registry.validate(
        "urn:ai4binance:schema:execution:execution-envelope:1.0.0",
        envelope_payload,
    )
    assert evidence_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert envelope_payload["external_order_allowed"] is False

    payload = market_snapshot_to_wire(_snapshot())
    payload["unexpected"] = True
    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        registry.validate(MARKET_SNAPSHOT_SCHEMA_ID, payload)

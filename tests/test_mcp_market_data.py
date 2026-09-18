"""Fail-closed tests for Canonical Market Data MCP contracts."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai4binance.mcp.evidence import FreshnessStatus
from ai4binance.mcp.market_data import MarketDataGateway

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)


def write_artifact(root: Path, relative: Path, payload: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "snapshot_id": "snapshot-1",
        "symbol": "BTCUSDT",
        "timestamp": NOW.isoformat(),
        "status": "READY",
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    payload.update(overrides)
    return payload


def test_market_data_gateway_reads_only_canonical_snapshot(tmp_path: Path) -> None:
    write_artifact(tmp_path, Path("market/snapshot.json"), snapshot_payload())

    report = MarketDataGateway(tmp_path, clock=lambda: NOW).get_snapshot()

    assert report.artifact_type == "market_snapshot"
    assert report.freshness_status is FreshnessStatus.FRESH
    assert report.data["symbol"] == "BTCUSDT"
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_market_data_gateway_degrades_missing_stale_and_unsafe(
    tmp_path: Path,
) -> None:
    gateway = MarketDataGateway(tmp_path, clock=lambda: NOW)
    missing = gateway.get_data_quality()
    assert missing.freshness_status is FreshnessStatus.MISSING
    assert missing.blockers == ("EVIDENCE_ARTIFACT_MISSING",)

    write_artifact(
        tmp_path,
        Path("market/snapshot.json"),
        snapshot_payload(timestamp=(NOW - timedelta(minutes=30)).isoformat()),
    )
    stale = gateway.get_snapshot()
    assert stale.freshness_status is FreshnessStatus.STALE
    assert stale.blockers == ("EVIDENCE_STALE",)

    write_artifact(
        tmp_path,
        Path("market/snapshot.json"),
        snapshot_payload(execution_allowed=True),
    )
    unsafe = gateway.get_snapshot()
    assert unsafe.freshness_status is FreshnessStatus.INVALID
    assert unsafe.blockers == ("EVIDENCE_AUTHORITY_VIOLATION",)


def test_market_data_gateway_reads_quality_and_provenance(tmp_path: Path) -> None:
    write_artifact(
        tmp_path,
        Path("market/data-quality.json"),
        {
            "check_id": "quality-1",
            "timestamp": NOW.isoformat(),
            "status": "PASS",
            "blockers": [],
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    write_artifact(
        tmp_path,
        Path("market/provenance.json"),
        {
            "provenance_id": "provenance-1",
            "timestamp": NOW.isoformat(),
            "sources": ["canonical-ingestion"],
            "blockers": [],
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )

    gateway = MarketDataGateway(tmp_path, clock=lambda: NOW)

    assert gateway.get_data_quality().data["check_id"] == "quality-1"
    assert gateway.get_provenance().data["provenance_id"] == "provenance-1"

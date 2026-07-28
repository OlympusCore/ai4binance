"""Fail-closed tests for the read-only MCP evidence boundary."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.mcp.evidence import (
    MARKET_OUTLOOK_SOURCE,
    EvidenceEnvelope,
    EvidenceGateway,
    FreshnessStatus,
)
from ai4binance.storage.jsonl import SecretRedactor

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)


def write_artifact(root: Path, relative: Path, payload: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def quality_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "quality-1",
        "finished_at": NOW.isoformat(),
        "revision": "abc123",
        "status": "PASSED",
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "api_token": "must-not-leak",
    }
    payload.update(overrides)
    return payload


def outlook_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "snapshot_id": "snapshot-1",
        "symbol": "HOTUSDT",
        "timestamp": NOW.isoformat(),
        "status": "READY",
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    payload.update(overrides)
    return payload


def gateway(root: Path, max_artifact_bytes: int = 1_000_000) -> EvidenceGateway:
    return EvidenceGateway(
        root,
        max_artifact_bytes=max_artifact_bytes,
        clock=lambda: NOW,
    )


def test_gateway_reads_allowlisted_fresh_redacted_evidence(tmp_path: Path) -> None:
    write_artifact(tmp_path, Path("quality-triage/state.json"), quality_payload())

    report = gateway(tmp_path).get_quality_triage()

    assert report.freshness_status is FreshnessStatus.FRESH
    assert report.blockers == ()
    assert report.data["api_token"] == SecretRedactor.REDACTED
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert len(report.source_sha256) == 64


def test_gateway_marks_stale_and_preserves_artifact_blockers(tmp_path: Path) -> None:
    stale_time = NOW - timedelta(days=3)
    write_artifact(
        tmp_path,
        Path("market-outlook/state.json"),
        outlook_payload(
            timestamp=stale_time.isoformat(), blockers=["WEAK_OOS_EVIDENCE"]
        ),
    )

    report = gateway(tmp_path).get_market_outlook()

    assert report.freshness_status is FreshnessStatus.STALE
    assert report.blockers == ("WEAK_OOS_EVIDENCE", "EVIDENCE_STALE")


@pytest.mark.parametrize(
    ("payload", "blocker"),
    [
        ("not-json", "EVIDENCE_ARTIFACT_INVALID"),
        ({"timestamp": NOW.isoformat()}, "EVIDENCE_SCHEMA_INVALID"),
        (outlook_payload(execution_allowed=True), "EVIDENCE_AUTHORITY_VIOLATION"),
        (outlook_payload(timestamp="invalid"), "EVIDENCE_TIMESTAMP_INVALID"),
        (outlook_payload(blockers="invalid"), "EVIDENCE_BLOCKERS_INVALID"),
    ],
)
def test_gateway_rejects_invalid_or_authoritative_evidence(
    tmp_path: Path, payload: object, blocker: str
) -> None:
    path = tmp_path / "market-outlook" / "state.json"
    path.parent.mkdir(parents=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")

    report = gateway(tmp_path).get_market_outlook()

    assert report.freshness_status is FreshnessStatus.INVALID
    assert report.blockers == (blocker,)
    assert report.data == {}


def test_gateway_blocks_missing_and_large_artifacts(tmp_path: Path) -> None:
    missing = gateway(tmp_path).get_market_outlook()
    assert missing.freshness_status is FreshnessStatus.MISSING
    assert missing.blockers == ("EVIDENCE_ARTIFACT_MISSING",)

    write_artifact(tmp_path, Path("market-outlook/state.json"), outlook_payload())
    too_large = gateway(tmp_path, max_artifact_bytes=10).get_market_outlook()
    assert too_large.blockers == ("EVIDENCE_ARTIFACT_TOO_LARGE",)


def test_gateway_health_and_blocker_aggregation_are_non_executing(
    tmp_path: Path,
) -> None:
    write_artifact(
        tmp_path,
        Path("quality-triage/state.json"),
        quality_payload(status="FAILED", blockers=["QUALITY_PYTEST_FAILED"]),
    )
    write_artifact(
        tmp_path,
        Path("market-outlook/state.json"),
        outlook_payload(blockers=["NO_TRADE_WEAK_EVIDENCE"]),
    )
    service = gateway(tmp_path)

    health = service.health_check()
    aggregated = service.get_research_blockers()

    assert health.freshness_status is FreshnessStatus.FRESH
    assert health.data["read_only"] is True
    assert aggregated.blockers == (
        "NO_TRADE_WEAK_EVIDENCE",
        "QUALITY_PYTEST_FAILED",
    )
    assert aggregated.promotion_status == "RESEARCH_ONLY"
    assert aggregated.execution_allowed is False


def test_contracts_reject_unsafe_configuration() -> None:
    with pytest.raises(ValueError, match="relative"):
        replace(MARKET_OUTLOOK_SOURCE, relative_path=Path("../secret.json"))
    with pytest.raises(ValueError, match="positive"):
        replace(MARKET_OUTLOOK_SOURCE, max_age=timedelta(0))
    with pytest.raises(ValueError, match="positive"):
        EvidenceGateway(Path("."), max_artifact_bytes=0)
    with pytest.raises(ValueError, match="live blocked"):
        EvidenceEnvelope(
            artifact_type="bad",
            generated_at=NOW,
            source_artifact="bad.json",
            source_sha256="0" * 64,
            freshness_status=FreshnessStatus.FRESH,
            blockers=(),
            live_eligibility_status="READY",
        )

"""Fail-closed tests for the read-only MCP evidence boundary."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import ai4binance.mcp.evidence as evidence_module
from ai4binance.mcp.evidence import (
    MARKET_OUTLOOK_SOURCE,
    EvidenceEnvelope,
    EvidenceGateway,
    EvidenceSource,
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

    write_artifact(tmp_path, Path("market-outlook/state.json"), quality_payload())
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


def test_gateway_exposes_bounded_evidence_verification_and_bundle(
    tmp_path: Path,
) -> None:
    write_artifact(tmp_path, Path("quality-triage/state.json"), quality_payload())
    write_artifact(
        tmp_path,
        Path("market-outlook/state.json"),
        outlook_payload(blockers=["NO_TRADE_WEAK_EVIDENCE"]),
    )

    service = gateway(tmp_path)
    index = service.get_evidence()
    verification = service.verify_evidence()
    provenance = service.get_provenance()
    conflicts = service.find_conflicts()
    bundle = service.build_bundle()

    assert index.execution_allowed is False
    assert "quality_triage" in index.data
    assert verification.data["degraded_artifacts"] == ("market_outlook",)
    assert "market_outlook" in provenance.data
    assert conflicts.data["conflicts"] == ("NO_TRADE_WEAK_EVIDENCE",)
    assert bundle.promotion_status == "RESEARCH_ONLY"
    assert bundle.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_contracts_reject_unsafe_configuration() -> None:
    with pytest.raises(ValueError, match="identity"):
        replace(MARKET_OUTLOOK_SOURCE, artifact_type=" ")
    with pytest.raises(ValueError, match="relative"):
        replace(MARKET_OUTLOOK_SOURCE, relative_path=Path("../secret.json"))
    with pytest.raises(ValueError, match="positive"):
        replace(MARKET_OUTLOOK_SOURCE, max_age=timedelta(0))
    with pytest.raises(ValueError, match="non-empty and unique"):
        replace(MARKET_OUTLOOK_SOURCE, required_fields=("status", "status"))
    with pytest.raises(ValueError, match="positive"):
        EvidenceGateway(Path("."), max_artifact_bytes=0)
    with pytest.raises(ValueError, match="identity"):
        EvidenceEnvelope(
            artifact_type=" ",
            generated_at=NOW,
            source_artifact="bad.json",
            source_sha256="0" * 64,
            freshness_status=FreshnessStatus.FRESH,
            blockers=(),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceEnvelope(
            artifact_type="bad",
            generated_at=datetime(2026, 7, 13, 12),
            source_artifact="bad.json",
            source_sha256="0" * 64,
            freshness_status=FreshnessStatus.FRESH,
            blockers=(),
        )
    with pytest.raises(ValueError, match="source hash"):
        EvidenceEnvelope(
            artifact_type="bad",
            generated_at=NOW,
            source_artifact="bad.json",
            source_sha256="bad",
            freshness_status=FreshnessStatus.FRESH,
            blockers=(),
        )
    with pytest.raises(ValueError, match="promote or execute"):
        EvidenceEnvelope(
            artifact_type="bad",
            generated_at=NOW,
            source_artifact="bad.json",
            source_sha256="0" * 64,
            freshness_status=FreshnessStatus.FRESH,
            blockers=(),
            promotion_status="PAPER_APPROVED",
        )
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
    with pytest.raises(ValueError, match="requires blockers"):
        EvidenceEnvelope(
            artifact_type="bad",
            generated_at=NOW,
            source_artifact="bad.json",
            source_sha256="0" * 64,
            freshness_status=FreshnessStatus.INVALID,
            blockers=(),
        )


def test_gateway_blocks_symlinks_outside_paths_and_invalid_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    source = object.__new__(EvidenceSource)
    object.__setattr__(source, "artifact_type", "outside")
    object.__setattr__(source, "relative_path", Path("../outside.json"))
    object.__setattr__(source, "timestamp_field", "timestamp")
    object.__setattr__(source, "max_age", timedelta(minutes=1))
    object.__setattr__(source, "required_fields", ("timestamp",))
    gateway_with_foreign_root = EvidenceGateway(
        tmp_path / "root",
        clock=lambda: NOW,
    )
    assert gateway_with_foreign_root.read(source).blockers == (
        "EVIDENCE_PATH_OUTSIDE_ROOT",
    )

    write_artifact(tmp_path, Path("market-outlook/state.json"), quality_payload())
    symlink = tmp_path / "quality-triage" / "state.json"
    symlink.parent.mkdir(parents=True)
    if hasattr(symlink, "symlink_to"):
        try:
            symlink.symlink_to(tmp_path / "market-outlook" / "state.json")
        except OSError:
            pass
    if symlink.is_symlink():
        report = gateway(tmp_path).get_quality_triage()
        assert report.blockers in (("EVIDENCE_SYMLINK_BLOCKED",), ())

    with pytest.raises(ValueError, match="clock"):
        EvidenceGateway(tmp_path, clock=lambda: datetime(2026, 7, 13)).health_check()

    write_artifact(tmp_path, Path("quality-triage/state.json"), quality_payload())

    class ShapeChangingRedactor:
        def redact(self, value: object) -> object:
            del value
            return ()

    monkeypatch.setattr(evidence_module, "SecretRedactor", ShapeChangingRedactor)
    with pytest.raises(RuntimeError, match="redactor"):
        gateway(tmp_path).get_quality_triage()


def test_gateway_helper_parsers_cover_degraded_and_fresh_paths() -> None:
    assert EvidenceGateway._parse_timestamp(None) is None
    assert EvidenceGateway._parse_timestamp("2026-07-13T12:00:00") is None
    assert EvidenceGateway._artifact_blockers(["A", "B"]) == ("A", "B")
    assert EvidenceGateway._artifact_blockers([""]) is None
    assert EvidenceGateway._artifact_blockers(["A"] * 129) is None
    assert (
        EvidenceGateway._aggregate_freshness({FreshnessStatus.MISSING})
        is FreshnessStatus.MISSING
    )
    assert EvidenceGateway._aggregate_freshness(set()) is FreshnessStatus.FRESH

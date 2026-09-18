from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.governance import GovernedArtifactEvidence, GovernedArtifactReader

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def write_artifact(root: Path, relative: str, payload: dict[str, object]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def quality_payload(timestamp: datetime = NOW) -> dict[str, object]:
    return {
        "run_id": "quality-1",
        "finished_at": timestamp.isoformat(),
        "revision": "abc123",
        "status": "PASS",
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def test_artifact_reader_reads_fresh_quality_evidence(tmp_path: Path) -> None:
    write_artifact(
        tmp_path,
        "runtime/artifacts/quality/triage/state.json",
        quality_payload(),
    )

    evidence = GovernedArtifactReader(tmp_path, clock=lambda: NOW).read(
        "quality_triage"
    )

    assert evidence.freshness_status == "FRESH"
    assert evidence.blockers == ()
    assert evidence.data is not None
    assert evidence.data["run_id"] == "quality-1"
    assert evidence.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_artifact_reader_degrades_missing_stale_and_unsafe(tmp_path: Path) -> None:
    reader = GovernedArtifactReader(tmp_path, clock=lambda: NOW)
    missing = reader.read("market_outlook")
    assert missing.freshness_status == "MISSING"
    assert missing.blockers == ("MARKET_OUTLOOK_MISSING",)

    write_artifact(
        tmp_path,
        "runtime/artifacts/quality/triage/state.json",
        quality_payload(NOW - timedelta(hours=3)),
    )
    stale = reader.read("quality_triage")
    assert stale.freshness_status == "STALE"
    assert "QUALITY_TRIAGE_STALE" in stale.blockers

    unsafe = quality_payload()
    unsafe["execution_allowed"] = True
    write_artifact(tmp_path, "runtime/artifacts/quality/triage/state.json", unsafe)
    invalid = reader.read("quality_triage")
    assert invalid.freshness_status == "INVALID"
    assert invalid.blockers == ("QUALITY_TRIAGE_UNSAFE_AUTHORITY",)


def test_artifact_reader_rejects_invalid_schema_and_contracts(tmp_path: Path) -> None:
    write_artifact(
        tmp_path,
        "runtime/artifacts/decisions/market_outlook/state.json",
        {"snapshot_id": "snapshot-1"},
    )
    invalid = GovernedArtifactReader(tmp_path, clock=lambda: NOW).read("market_outlook")
    assert invalid.blockers == ("MARKET_OUTLOOK_SCHEMA_INVALID",)
    with pytest.raises(ValueError, match="unknown"):
        GovernedArtifactReader(tmp_path).read("other")
    with pytest.raises(ValueError, match="cannot authorize"):
        GovernedArtifactEvidence(
            artifact_type="quality_triage",
            generated_at=NOW,
            source_artifact="source.json",
            source_sha256="a" * 64,
            freshness_status="FRESH",
            blockers=(),
            execution_allowed=True,
        )


def test_artifact_reader_degrades_invalid_json_blockers_and_timestamp(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime/artifacts/quality/triage/state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    reader = GovernedArtifactReader(tmp_path, clock=lambda: NOW)
    assert reader.read("quality_triage").blockers == ("QUALITY_TRIAGE_INVALID_JSON",)

    invalid_blockers = quality_payload()
    invalid_blockers["blockers"] = "bad"
    write_artifact(
        tmp_path,
        "runtime/artifacts/quality/triage/state.json",
        invalid_blockers,
    )
    assert reader.read("quality_triage").blockers == (
        "QUALITY_TRIAGE_BLOCKERS_INVALID",
    )

    invalid_timestamp = quality_payload()
    invalid_timestamp["finished_at"] = "2026-07-27T00:00:00"
    write_artifact(
        tmp_path,
        "runtime/artifacts/quality/triage/state.json",
        invalid_timestamp,
    )
    assert reader.read("quality_triage").blockers == (
        "QUALITY_TRIAGE_TIMESTAMP_INVALID",
    )


def test_artifact_reader_contract_edges(tmp_path: Path) -> None:
    write_artifact(
        tmp_path,
        "runtime/artifacts/quality/triage/state.json",
        quality_payload(),
    )
    write_artifact(
        tmp_path,
        "runtime/artifacts/decisions/market_outlook/state.json",
        {
            "snapshot_id": "snapshot-1",
            "symbol": "HOTUSDT",
            "timestamp": NOW.isoformat(),
            "status": "PASS",
            "blockers": [],
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    assert (
        len(GovernedArtifactReader(tmp_path, clock=lambda: NOW).collect_default()) == 2
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        GovernedArtifactReader(tmp_path, clock=lambda: datetime(2026, 1, 1)).read(
            "quality_triage"
        )
    with pytest.raises(ValueError, match="identity"):
        GovernedArtifactEvidence("", NOW, "source", "a" * 64, "FRESH", ())
    with pytest.raises(ValueError, match="timestamp"):
        GovernedArtifactEvidence(
            "quality_triage",
            datetime(2026, 1, 1),
            "source",
            "a" * 64,
            "FRESH",
            (),
        )
    with pytest.raises(ValueError, match="source hash"):
        GovernedArtifactEvidence("quality_triage", NOW, "source", "bad", "FRESH", ())
    with pytest.raises(ValueError, match="freshness"):
        GovernedArtifactEvidence("quality_triage", NOW, "source", "a" * 64, "BAD", ())
    with pytest.raises(ValueError, match="degraded"):
        GovernedArtifactEvidence(
            "quality_triage",
            NOW,
            "source",
            "a" * 64,
            "STALE",
            (),
        )

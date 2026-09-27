"""Test-only canonical receipts exercise the read-only dashboard boundary."""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from ai4binance.domain.research.canonical_cycle import (
    CanonicalCycleEnvelope,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
)

ROOT = Path(__file__).resolve().parents[1]
SERVER = runpy.run_path(str(ROOT / "src/ai4binance/local_dashboard/server.py.in"))
NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


def receipt() -> dict[str, Any]:
    def ref(kind: CycleArtifactKind) -> CycleArtifactRef:
        return CycleArtifactRef(
            artifact_id=f"test-only:{kind.value}",
            artifact_kind=kind,
            cycle_id="test-only-cycle",
            snapshot_id="test-only-snapshot",
            payload_sha256="a" * 64,
        )

    cycle = CanonicalCycleEnvelope(
        cycle_id="test-only-cycle",
        snapshot_id="test-only-snapshot",
        created_at=NOW,
        execution_surface=CycleExecutionSurface.VIRTUAL_MARKET,
        governance_status=CycleGovernanceStatus.NO_TRADE,
        canonical_snapshot=ref(CycleArtifactKind.CANONICAL_SNAPSHOT),
        shared_state=ref(CycleArtifactKind.SHARED_STATE),
        observations=(ref(CycleArtifactKind.OBSERVATION),),
        decision=ref(CycleArtifactKind.DECISION),
        risk_assessment=ref(CycleArtifactKind.RISK_ASSESSMENT),
        governance_result=ref(CycleArtifactKind.GOVERNANCE_RESULT),
        execution_plan=None,
        audit_trail=ref(CycleArtifactKind.AUDIT_TRAIL),
        blockers=("TEST_ONLY_RISK_VETO",),
    )
    return {
        "event_type": "RESEARCH_WORKFLOW_COMPLETED",
        "timestamp": NOW.isoformat(),
        "snapshot_id": cycle.snapshot_id,
        "payload": {
            "canonical_cycle": cycle.to_payload(),
            "snapshot_ref": {
                "snapshot_id": cycle.snapshot_id,
                "symbol": "TEST_ONLY",
                "created_at": NOW.isoformat(),
            },
            "analysis_ref": {
                "snapshot_id": cycle.snapshot_id,
                "final_action": "NO_TRADE",
                "blockers": ["TEST_ONLY_RISK_VETO"],
            },
            "stages": [
                {
                    "name": "risk",
                    "status": "BLOCKED",
                    "blockers": ["TEST_ONLY_RISK_VETO"],
                }
            ],
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "private_payload": "TEST_ONLY_MUST_NOT_LEAK",
        },
    }


def test_receipt_preserves_veto_and_distinguishes_missing_payload() -> None:
    result = SERVER["decision_record"](receipt(), "test-only.jsonl", NOW)
    assert result["status"] == "CURRENT"
    assert result["action"] == "NO_TRADE"
    assert result["governance_status"] == "NO_TRADE"
    assert result["blockers"] == ["TEST_ONLY_RISK_VETO"]
    assert result["stages"][0]["status"] == "BLOCKED"
    assert result["receipt_status"] == "RECEIPT_HASH_MATCH"
    assert result["payload_status"] == "DATA_UNAVAILABLE"
    assert result["historical_authenticity"] == "NOT_VERIFIED"
    assert result["market"] is None
    assert all(row["status"] == "PAYLOAD_UNAVAILABLE" for row in result["references"])
    assert "TEST_ONLY_MUST_NOT_LEAK" not in json.dumps(result)
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "cycle",
        "snapshot",
        "missing",
        "kind",
        "authority",
        "unknown_authority",
        "numeric_authority",
        "blocker_shape",
        "steps",
        "duplicate",
        "outer",
    ],
)
def test_rejects_invalid_receipt(mutation: str) -> None:
    event = receipt()
    raw = event["payload"]["canonical_cycle"]
    if mutation == "hash":
        raw["semantic_sha256"] = "0" * 64
    elif mutation == "cycle":
        raw["risk_assessment"]["cycle_id"] = "test-only-other"
    elif mutation == "snapshot":
        raw["decision"]["snapshot_id"] = "test-only-other"
    elif mutation == "missing":
        del raw["canonical_snapshot"]
    elif mutation == "kind":
        raw["decision"]["artifact_kind"] = "RISK_ASSESSMENT"
    elif mutation == "authority":
        raw["execution_allowed"] = True
    elif mutation == "unknown_authority":
        raw["execution_allowed"] = None
    elif mutation == "numeric_authority":
        raw["execution_allowed"] = 0
    elif mutation == "blocker_shape":
        raw["blockers"] = {"TEST_ONLY_RISK_VETO": "TEST_ONLY_INVALID_SHAPE"}
    elif mutation == "steps":
        raw["completed_steps"].reverse()
    elif mutation == "duplicate":
        raw["observations"].append(copy.deepcopy(raw["observations"][0]))
    else:
        event["snapshot_id"] = "test-only-other"
    with pytest.raises((KeyError, ValueError)):
        SERVER["decision_record"](event, "test-only.jsonl", NOW)


def test_historical_receipt_remains_explicitly_stale() -> None:
    result = SERVER["decision_record"](
        receipt(), "test-only.jsonl", NOW + timedelta(days=1)
    )
    assert result["status"] == "STALE"
    with pytest.raises(ValueError, match="CYCLE_TIME_INVALID"):
        SERVER["decision_record"](receipt(), "test-only.jsonl", NOW - timedelta(days=1))


@pytest.mark.parametrize("mutation", ["valid", "hash", "cycle", "snapshot", "oversize"])
def test_embedded_reference_body_is_bound_and_redacted(mutation: str) -> None:
    body = {
        "action": "NO_TRADE",
        "reason_summary": "TEST_ONLY_VETO",
        "private": "TEST_ONLY_PRIVATE",
    }
    encoded = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    reference = CycleArtifactRef(
        artifact_id="test-only-decision",
        artifact_kind=CycleArtifactKind.DECISION,
        cycle_id="test-only-cycle",
        snapshot_id="test-only-snapshot",
        payload_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    embedded = {**reference.to_payload(), "payload": body}
    if mutation == "hash":
        body["action"] = "BUY"
    elif mutation == "cycle":
        embedded["cycle_id"] = "different-cycle"
    elif mutation == "snapshot":
        embedded["snapshot_id"] = "different-snapshot"
    elif mutation == "oversize":
        body["reason_summary"] = "x" * 16_001
    result = SERVER["decision_reference"](reference, {reference.artifact_id: embedded})
    assert result["status"] == (
        "PAYLOAD_HASH_MATCH" if mutation == "valid" else "PAYLOAD_INVALID"
    )
    assert "TEST_ONLY_PRIVATE" not in json.dumps(result)
    if mutation == "valid":
        assert result["payload"]["action"] == "NO_TRADE"
    else:
        assert "payload" not in result


def test_history_rejects_conflicting_duplicates_and_records_invalid_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AI4BINANCE_AUDIT_DIRECTORY", raising=False)
    directory = tmp_path / "runtime/logs"
    directory.mkdir(parents=True)
    original = receipt()
    conflict = copy.deepcopy(original)
    conflict["payload"]["analysis_ref"]["final_action"] = "TEST_ONLY_CONFLICT"
    path = directory / "research_events.jsonl"
    path.write_text(
        "\n".join(json.dumps(event) for event in [original, original, conflict])
        + "\n{}invalid\n",
        encoding="utf-8",
    )
    result = SERVER["decision_history"](tmp_path, NOW)
    assert result["records"] == []
    assert result["status"] == "DEGRADED"
    assert {row["status"] for row in result["findings"]} == {
        "INVALID_CYCLE_RECEIPT",
        "CONFLICTING_DECISION_ID",
    }
    path.write_text(
        json.dumps(original) + "\n" + json.dumps(original), encoding="utf-8"
    )
    result = SERVER["decision_history"](tmp_path, NOW)
    assert len(result["records"]) == 1
    assert result["status"] == "PARTIALLY_VERIFIED"


def test_missing_history_is_not_a_zero_or_success(tmp_path: Path) -> None:
    result = SERVER["decision_history"](tmp_path, NOW)
    assert result["status"] == "DATA_UNAVAILABLE"
    assert result["records"] == []


def test_oversized_history_fails_closed(tmp_path: Path) -> None:
    directory = tmp_path / "runtime/logs"
    directory.mkdir(parents=True)
    (directory / "research_events.jsonl").write_bytes(b"x" * 4_000_001)
    result = SERVER["decision_history"](tmp_path, NOW)
    assert result["status"] == "UNAVAILABLE"
    assert result["records"] == []


def test_changing_journal_is_not_presented_as_a_stable_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.core

    directory = tmp_path / "runtime/logs"
    directory.mkdir(parents=True)
    path = directory / "research_events.jsonl"
    path.write_text(json.dumps(receipt()), encoding="utf-8")
    reader = ai4binance.core.read_bounded_jsonl_tail

    def changed(source: Path, *, max_lines: int, max_bytes: int) -> tuple[bytes, ...]:
        lines = reader(source, max_lines=max_lines, max_bytes=max_bytes)
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n{}\n")
        return lines

    monkeypatch.setattr(ai4binance.core, "read_bounded_jsonl_tail", changed)
    result = SERVER["decision_history"](tmp_path, NOW)
    assert result["records"] == []
    assert result["findings"] == [{"source": path.name, "status": "SOURCE_CHANGED"}]


def test_listener_reports_loaded_server_hash_not_replaced_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "test-only-server.py"
    source.write_bytes(b"TEST_ONLY_ORIGINAL")
    monkeypatch.setitem(SERVER["create_server"].__globals__, "__file__", str(source))
    server = SERVER["create_server"]({"port": 0, "installation_id": "TEST_ONLY"})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source.write_bytes(b"TEST_ONLY_REPLACED")
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request("GET", "/health")
        response = connection.getresponse()
        assert response.status == 200
        body = json.loads(response.read())
        connection.close()
        assert (
            body["loaded_server_sha256"]
            == hashlib.sha256(b"TEST_ONLY_ORIGINAL").hexdigest()
        )
        assert body["execution_allowed"] is False
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

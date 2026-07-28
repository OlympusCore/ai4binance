from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai4binance.governance import RunContext
from ai4binance.observability import LocalObserver


def test_local_observer_redacts_content_and_hashes_ids(tmp_path: Path) -> None:
    path = tmp_path / "observations.jsonl"
    observer = LocalObserver(path)

    observer.emit(
        RunContext("run-123", "step-1"),
        "local_model_call",
        "COMPLETED",
        metadata={
            "prompt": "do not retain this",
            "evidence_id": "evidence-123",
            "nested": {"response_text": "secret body"},
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["content_capture"] is False
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["metadata"]["prompt"] == "[CONTENT_NOT_CAPTURED]"
    assert payload["metadata"]["nested"]["response_text"] == "[CONTENT_NOT_CAPTURED]"
    assert payload["metadata"]["evidence_id"].startswith("sha256:")
    assert "do not retain this" not in path.read_text(encoding="utf-8")


def test_local_observer_measure_records_failures(tmp_path: Path) -> None:
    observer = LocalObserver(tmp_path / "observations.jsonl")

    with pytest.raises(RuntimeError, match="boom"):
        with observer.measure(RunContext("run", "step"), "operation"):
            raise RuntimeError("boom")

    payload = json.loads((tmp_path / "observations.jsonl").read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert payload["metadata"]["error_type"] == "RuntimeError"


def test_local_observer_rejects_blank_event_or_status(tmp_path: Path) -> None:
    observer = LocalObserver(tmp_path / "observations.jsonl")
    with pytest.raises(ValueError, match="event and status"):
        observer.emit(RunContext("run", "step"), "", "COMPLETED")

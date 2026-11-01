"""Accounting history reads preserve their windows with bounded working memory."""

import json
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from ai4binance.accounting import reconciliation, ui_reports


@pytest.mark.parametrize(
    "reader", [reconciliation._read_events, ui_reports._read_events]
)
def test_recent_events_preserve_physical_line_window(
    reader: Callable[..., tuple[dict[str, object], ...]], tmp_path: Path
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"id": 0}\r\n{"id": 1}\r\n\r\ninvalid\r\n[]\r\n{"id": 2}')
    assert reader(path, limit=4) == ({"id": 2},)
    assert reader(path, limit=5) == ({"id": 1}, {"id": 2})
    assert reader(tmp_path / "missing.jsonl", limit=5) == ()


@pytest.mark.parametrize(
    "reader", [reconciliation._read_events, ui_reports._read_events]
)
def test_recent_events_preserve_unreadable_file_behavior(
    reader: Callable[..., tuple[dict[str, object], ...]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    path.touch()
    monkeypatch.setattr(Path, "open", Mock(side_effect=OSError("unreadable")))
    assert reader(path, limit=5) == ()


@pytest.mark.parametrize("operation", ["reconciliation", "report_tail", "file_status"])
def test_accounting_reads_do_not_allocate_the_entire_history(
    operation: str, tmp_path: Path
) -> None:
    path = tmp_path / "shared" / "raw_api_events.jsonl"
    path.parent.mkdir()
    line = json.dumps({"test_only": True, "padding": "x" * 1024}) + "\n"
    with path.open("w", encoding="utf-8") as stream:
        for _ in range(8192):
            stream.write(line)
        stream.write("\n  \n")
    tracemalloc.start()
    try:
        if operation == "reconciliation":
            events = reconciliation._read_events(path, limit=5)
            assert len(events) == 3
            assert all(event["test_only"] is True for event in events)
        elif operation == "report_tail":
            events = ui_reports._read_events(path, limit=5)
            assert len(events) == 3
            assert all(event["test_only"] is True for event in events)
        else:
            report = ui_reports.AccountingUiReportBuilder(tmp_path, tmp_path, 1800)
            status = report._file_status(
                "shared/raw_api_events.jsonl", datetime.now(UTC)
            )
            assert status["line_count"] == 8192
            assert status["exists"] is True
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024, f"history read allocated {peak} bytes"

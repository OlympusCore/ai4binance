"""Boundary coverage for the third coverage-audit remediation set."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import ai4binance.external_intel.__main__ as external_intel_main
import ai4binance.learning as learning
from ai4binance.agents.evaluation import (
    AdvisoryEvalExpectation,
    AdvisoryEvalResult,
    AdvisoryFixture,
    AdvisoryFixtureProviderResponse,
)
from ai4binance.content.engine import ContentDraftEngine, DraftBlockedError
from ai4binance.data.revision import (
    DatasetRevisionBuilder,
    DatasetRevisionEntry,
    DatasetRevisionManifest,
)
from ai4binance.enterprise.contracts import DepartmentId
from ai4binance.enterprise.dashboard import (
    DashboardMetric,
    _mapping,
    _require_unique,
    _text_tuple,
)
from ai4binance.enterprise.executive import ExecutiveRoutingDecision, _stable_unique
from ai4binance.execution.live_order_lifecycle import LiveOrderLifecycleJournal
from ai4binance.execution.live_spot import (
    GatedSpotOrderExecutor,
    LiveCommandResult,
    LiveCommandStatus,
)
from ai4binance.execution.live_spot_adapter import (
    LiveSpotOrderAdapter,
    LiveSpotOrderPlacement,
)
from ai4binance.outlook.storage import MarketOutlookArtifactStore
from ai4binance.validation.recovery_queue import (
    RecoveryValidationQueue,
    RecoveryValidationWorkItem,
)
from ai4binance.whale_fusion.integration import WhaleFusionEnvelope

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _entry() -> DatasetRevisionEntry:
    return DatasetRevisionEntry(
        timeframe="1h",
        dataset_sha256="a" * 64,
        row_count=1,
        first_timestamp=NOW.isoformat(),
        last_timestamp=NOW.isoformat(),
        gap_count=0,
        source="TEST",
        source_manifest_sha256="b" * 64,
        source_file_count=1,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"revision_id": "bad"}, "identity"),
        ({"entries": ()}, "identity"),
        ({"promotion_status": "PROMOTED"}, "promotion"),
        ({"execution_allowed": True}, "execution"),
    ],
)
def test_dataset_revision_manifest_rejects_unsafe_identity_and_authority(
    kwargs: dict[str, object], message: str
) -> None:
    base: Any = {
        "schema_version": "1.0",
        "revision_id": "dataset:test",
        "symbol": "HOTUSDT",
        "generated_at": NOW.isoformat(),
        "coverage_start": NOW.isoformat(),
        "coverage_end": NOW.isoformat(),
        "total_rows": 1,
        "entries": (_entry(),),
        "warnings": (),
        "research_ready": False,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        DatasetRevisionManifest(**base)


@pytest.mark.parametrize(
    ("symbol", "timeframes", "generated_at", "message"),
    [
        ("bad symbol!", ("1h",), NOW, "symbol"),
        ("HOTUSDT", (), NOW, "timeframes"),
        ("HOTUSDT", ("1h", "1h"), NOW, "timeframes"),
        ("HOTUSDT", ("1h",), datetime(2026, 9, 16), "timezone"),
    ],
)
def test_dataset_revision_builder_rejects_invalid_request_boundaries(
    tmp_path: Path,
    symbol: str,
    timeframes: tuple[str, ...],
    generated_at: datetime,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DatasetRevisionBuilder(tmp_path).build(
            symbol=symbol, timeframes=timeframes, generated_at=generated_at
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"directive_id": " "}, "identity"),
        ({"assigned_departments": ()}, "departments"),
        ({"blockers": ()}, "blockers"),
        ({"promotion_status": "PROMOTED"}, "promote"),
    ],
)
def test_executive_routing_decision_preserves_fail_closed_contract(
    kwargs: dict[str, object], message: str
) -> None:
    base: Any = {
        "directive_id": "directive-1",
        "assigned_departments": (DepartmentId.SOFTWARE_ENGINEERING,),
        "blockers": ("HUMAN_REVIEW_REQUIRED",),
        "meeting_required": True,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        ExecutiveRoutingDecision(**base)


def test_executive_stable_unique_discards_repeated_departments() -> None:
    assert _stable_unique(
        (DepartmentId.TRADER, DepartmentId.TRADER, DepartmentId.QUALITY_AUDIT)
    ) == (DepartmentId.TRADER, DepartmentId.QUALITY_AUDIT)


def test_learning_lazy_export_rejects_unknown_symbol() -> None:
    name = "not_a_learning_export"
    with pytest.raises(AttributeError, match="has no attribute"):
        getattr(learning, name)


def test_market_outlook_store_rejects_unsafe_authority_before_writing(
    tmp_path: Path,
) -> None:
    unsafe = SimpleNamespace(
        execution_allowed=True,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
        snapshot_id="outlook-1",
    )
    with pytest.raises(ValueError, match="unsafe"):
        MarketOutlookArtifactStore(tmp_path / "state.json").save(unsafe)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("queue_kwargs", "message"),
    [
        ({"queue_id": " "}, "identity"),
        ({"status": "INVALID"}, "status"),
        ({"blockers": ("x", "x")}, "unique"),
        ({"execution_allowed": True}, "authorize"),
    ],
)
def test_recovery_validation_queue_rejects_invalid_or_unsafe_state(
    queue_kwargs: dict[str, object], message: str
) -> None:
    base: Any = {
        "queue_id": "queue-1",
        "symbol": "HOTUSDT",
        "items": (),
        "blockers": ("LIVE_ORDER_BLOCKED",),
    }
    base.update(queue_kwargs)
    with pytest.raises(ValueError, match=message):
        RecoveryValidationQueue(**base)


@pytest.mark.parametrize(
    ("item_kwargs", "message"),
    [
        ({"work_id": " "}, "identity"),
        ({"required_artifacts": ("artifact", "artifact")}, "unique"),
        ({"blockers": (" ",)}, "blanks"),
        ({"live_eligibility_status": "LIVE_ALLOWED"}, "authorize"),
    ],
)
def test_recovery_work_item_rejects_invalid_or_unsafe_state(
    item_kwargs: dict[str, object], message: str
) -> None:
    base: Any = {
        "work_id": "work-1",
        "candidate_id": "candidate-1",
        "symbol": "HOTUSDT",
        "setup_name": "setup",
        "timeframe": "1h",
        "required_artifacts": ("artifact",),
        "blockers": ("LIVE_ORDER_BLOCKED",),
    }
    base.update(item_kwargs)
    with pytest.raises(ValueError, match=message):
        RecoveryValidationWorkItem(**base)


def test_whale_fusion_envelope_rejects_blank_snapshot_identity() -> None:
    result = SimpleNamespace(symbol="HOTUSDT")
    with pytest.raises(ValueError, match="snapshot_id"):
        WhaleFusionEnvelope(" ", "HOTUSDT", result)  # type: ignore[arg-type]


def test_external_intel_cli_dispatches_universe_and_non_ready_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        external_intel_main,
        "external_intel_universe_payload",
        lambda: {"status": "READY", "scope": "universe"},
    )
    assert external_intel_main.main(("universe",)) == 0
    assert '"scope": "universe"' in capsys.readouterr().out
    monkeypatch.setattr(
        external_intel_main, "external_intel_payload", lambda **_: {"status": "BLOCKED"}
    )
    assert external_intel_main.main(("scan",)) == 2


def test_live_spot_adapter_preserves_lifecycle_and_authorization() -> None:
    blocked = LiveCommandResult(LiveCommandStatus.BLOCKED, (), "client-1")
    with pytest.raises(ValueError, match="unexpected lifecycle"):
        LiveSpotOrderPlacement(blocked, SimpleNamespace())  # type: ignore[arg-type]

    executor = SimpleNamespace(
        place=lambda *_args, **_kwargs: LiveCommandResult(
            LiveCommandStatus.SUBMITTED, (), "client-1"
        ),
        cancel=lambda **_kwargs: blocked,
    )
    adapter = LiveSpotOrderAdapter(
        cast(GatedSpotOrderExecutor, executor),
        cast(LiveOrderLifecycleJournal, SimpleNamespace()),
    )
    with pytest.raises(RuntimeError, match="requires authorization"):
        adapter.place(SimpleNamespace(), authorization=None)
    assert (
        adapter.cancel(
            symbol="HOTUSDT",
            client_order_id="client-1",
            gate_input=SimpleNamespace(),
        )
        is blocked
    )


@pytest.mark.parametrize("value", [None, 1, "invalid", "2026-09-16T00:00:00"])
def test_content_engine_rejects_invalid_timestamp_boundaries(value: object) -> None:
    assert ContentDraftEngine._timestamp(value) is None


@pytest.mark.parametrize("value", [None, " ", 4])
def test_content_engine_rejects_invalid_required_fields(value: object) -> None:
    with pytest.raises(DraftBlockedError, match="CONTENT_SOURCE_SYMBOL_INVALID"):
        ContentDraftEngine._field({"symbol": value}, "symbol", 20)


@pytest.mark.parametrize("value", [None, "bad", (), ({"timeframe": "1d"},)])
def test_content_engine_rejects_incomplete_biases(value: object) -> None:
    with pytest.raises(DraftBlockedError, match="BIASES"):
        ContentDraftEngine._biases(value)


@pytest.mark.parametrize("value", [None, "bad", ({"setup_name": "x"},)])
def test_content_engine_rejects_invalid_radar(value: object) -> None:
    with pytest.raises(DraftBlockedError, match="RADAR"):
        ContentDraftEngine._radar(value)


def test_dashboard_boundary_helpers_retain_blockers() -> None:
    assert _text_tuple(" ") == ()
    assert _text_tuple([" ok ", " ", 4]) == ("ok", "4")
    assert _mapping("invalid") == {}
    with pytest.raises(ValueError, match="blanks"):
        _require_unique("test", (" ",))
    with pytest.raises(ValueError, match="unique"):
        _require_unique("test", ("a", "a"))
    with pytest.raises(ValueError, match="identity"):
        DashboardMetric(" ", "label", "value", "OK")
    with pytest.raises(ValueError, match="status"):
        DashboardMetric("metric", "label", "value", "INVALID")


def test_advisory_contracts_reject_invalid_and_unsafe_states() -> None:
    with pytest.raises(ValueError, match="expectation"):
        AdvisoryEvalExpectation("fixture", (), (), 0)
    with pytest.raises(ValueError, match="blockers disagree"):
        AdvisoryEvalResult("trace", True, ("BLOCKED",))
    expectation = AdvisoryEvalExpectation("fixture", (), (), 1)
    with pytest.raises(ValueError, match="must match"):
        AdvisoryFixture("other", "prompt", "v1", expectation)
    with pytest.raises(ValueError, match="unavailable"):
        AdvisoryFixtureProviderResponse(
            "model", "", (), (), NOW, available=False, accepted=True
        )

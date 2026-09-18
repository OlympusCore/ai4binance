"""Fail-closed branch coverage for Futures OOS evidence boundaries."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.validation import futures_oos
from ai4binance.validation.futures_oos import (
    FuturesOosEvidenceQuery,
    FuturesOosEvidenceReader,
    FuturesOosEvidenceWriteResult,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SHA256 = "a" * 64
REVISION = "b" * 40


def _query() -> FuturesOosEvidenceQuery:
    return FuturesOosEvidenceQuery(
        symbol="BTCUSDT",
        timeframe="1h",
        setup_name="TREND",
        strategy_sha256=SHA256,
        as_of=NOW,
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": futures_oos.FUTURES_OOS_SCHEMA_VERSION,
        "market": "USD_M_FUTURES",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "setup_name": "TREND",
        "strategy_version": futures_oos.FUTURES_OOS_STRATEGY_VERSION,
        "strategy_sha256": SHA256,
        "validation_status": "OOS_VALIDATED",
        "promotion_status": "STAGED_CANDIDATE",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "evidence_id": "evidence-1",
        "dataset_sha256": SHA256,
        "code_revision": REVISION,
        "blockers": [],
        "created_at": NOW.isoformat(),
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("symbol", "btc", "symbol identity"),
        ("timeframe", "0h", "timeframe identity"),
        ("setup_name", "bad-name", "setup identity"),
        ("strategy_sha256", "bad", "strategy hash"),
    ],
)
def test_query_rejects_invalid_identity_fields(
    field: str,
    value: str,
    message: str,
) -> None:
    """Every identity component is exact-bound before evidence lookup."""
    values = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "setup_name": "TREND",
        "strategy_sha256": SHA256,
        "as_of": NOW,
    }
    values[field] = value
    with pytest.raises(ValueError, match=message):
        FuturesOosEvidenceQuery(**values)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        FuturesOosEvidenceQuery(
            symbol="BTCUSDT",
            timeframe="1h",
            setup_name="TREND",
            strategy_sha256=SHA256,
            as_of=datetime(2026, 1, 1),
        )


def test_reader_and_write_result_reject_unsafe_configuration(tmp_path: Path) -> None:
    """Local evidence cannot accept negative time or execution authority."""
    with pytest.raises(ValueError, match="age bound"):
        FuturesOosEvidenceReader(tmp_path, max_evidence_age=timedelta(0))
    with pytest.raises(ValueError, match="future tolerance"):
        FuturesOosEvidenceReader(tmp_path, future_tolerance=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="identity is required"):
        FuturesOosEvidenceWriteResult("", "artifact", "id", SHA256, False)
    with pytest.raises(ValueError, match="hash is invalid"):
        FuturesOosEvidenceWriteResult("evidence", "artifact", "id", "bad", False)
    with pytest.raises(ValueError, match="cannot grant execution"):
        FuturesOosEvidenceWriteResult("evidence", "artifact", "id", SHA256, False, True)


def test_reader_rejects_non_object_evidence_and_missing_artifact(
    tmp_path: Path,
) -> None:
    """Unreadable or non-object evidence remains unvalidated."""
    query = _query()
    path = tmp_path / query.symbol / query.timeframe
    path.mkdir(parents=True)
    evidence = path / "trend.oos-evidence.json"
    evidence.write_text("[]", encoding="utf-8")

    reader = FuturesOosEvidenceReader(tmp_path)
    assert reader.is_validated(query) is False
    evidence.write_text(json.dumps(_payload()), encoding="utf-8")
    assert reader.is_validated(query) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_id", ""),
        ("dataset_sha256", "bad"),
        ("code_revision", "bad"),
    ],
)
def test_evidence_metadata_must_be_bounded_and_canonical(
    field: str,
    value: str,
    tmp_path: Path,
) -> None:
    """Canonical evidence metadata rejects malformed identity values."""
    payload = _payload()
    payload[field] = value
    assert FuturesOosEvidenceReader(tmp_path)._matches(payload, _query()) is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"short_lookback": 0, "medium_lookback": 2}, "lookbacks"),
        (
            {
                "short_lookback": 2,
                "medium_lookback": 3,
                "stop_loss_ratio": Decimal("0"),
            },
            "ratios",
        ),
        (
            {
                "short_lookback": 2,
                "medium_lookback": 3,
                "take_profit_ratio": Decimal("1"),
            },
            "below one",
        ),
        (
            {
                "short_lookback": 2,
                "medium_lookback": 3,
                "take_profit_ratio": Decimal("0.03"),
            },
            "risk-reward",
        ),
        (
            {
                "short_lookback": 2,
                "medium_lookback": 3,
                "maximum_holding_bars": True,
            },
            "holding bars",
        ),
    ],
)
def test_runtime_strategy_hash_rejects_invalid_parameters(
    kwargs: dict[str, object],
    message: str,
) -> None:
    """Runtime strategy evidence rejects unsafe parameter identities."""
    with pytest.raises(ValueError, match=message):
        futures_oos.runtime_futures_strategy_sha256(**kwargs)  # type: ignore[arg-type]


def test_serialized_lineage_helpers_fail_closed_for_malformed_records() -> None:
    """Stored lineage is never trusted until every nested record is canonical."""
    evidence = _payload()
    artifact = {"artifact_type": "FUTURES_OOS_VALIDATION_REPORT", **evidence}
    assert (
        futures_oos._serialized_artifact_has_futures_lineage(
            artifact,
            evidence=evidence,
        )
        is False
    )

    report = {
        "symbol": evidence["symbol"],
        "timeframe": evidence["timeframe"],
        "created_at": evidence["created_at"],
        "oos_validation_status": "APPROVED",
        "promotion_status": "STAGED_CANDIDATE",
        "blockers": [],
    }
    artifact["walk_forward_report"] = report
    assert (
        futures_oos._serialized_artifact_has_futures_lineage(
            artifact,
            evidence=evidence,
        )
        is False
    )

    report["report_id"] = "report-1"
    evidence["evidence_id"] = futures_oos._evidence_id(
        "report-1",
        str(evidence["setup_name"]),
        str(evidence["strategy_sha256"]),
        str(evidence["dataset_sha256"]),
    )
    assert (
        futures_oos._serialized_artifact_has_futures_lineage(
            artifact,
            evidence=evidence,
        )
        is False
    )
    assert (
        futures_oos._serialized_fold_has_futures_lineage(
            None,
            symbol="BTCUSDT",
            timeframe="1h",
            setup_name="TREND",
            strategy_sha256=SHA256,
        )
        is False
    )
    assert (
        futures_oos._serialized_result_has_futures_lineage(
            None,
            symbol="BTCUSDT",
            timeframe="1h",
            setup_name="TREND",
            strategy_sha256=SHA256,
        )
        is False
    )
    assert (
        futures_oos._serialized_result_has_futures_lineage(
            {},
            symbol="BTCUSDT",
            timeframe="1h",
            setup_name="TREND",
            strategy_sha256=SHA256,
        )
        is False
    )
    assert futures_oos._serialized_rejection_has_missing_data(None) is True


def test_reader_rejects_unsafe_paths_and_oversized_payloads(tmp_path: Path) -> None:
    """Evidence loading rejects oversized documents and untrusted artifact paths."""
    query = _query()
    evidence_path = (
        tmp_path / query.symbol / query.timeframe / "trend.oos-evidence.json"
    )
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    assert (
        FuturesOosEvidenceReader(tmp_path, max_evidence_bytes=1).is_validated(query)
        is False
    )

    reader = FuturesOosEvidenceReader(tmp_path)
    assert (
        reader._artifact_matches(
            {"artifact_path": "C:/unsafe", "artifact_sha256": SHA256}
        )
        is False
    )
    assert (
        reader._artifact_matches(
            {"artifact_path": "missing.json", "artifact_sha256": SHA256}
        )
        is False
    )
    assert (
        reader._artifact_matches(
            {"artifact_path": "../unsafe.json", "artifact_sha256": SHA256}
        )
        is False
    )

    artifact = tmp_path / "artifact.json"
    artifact.write_text("[]", encoding="utf-8")
    assert (
        reader._artifact_matches(
            {
                "artifact_path": artifact.name,
                "artifact_sha256": futures_oos._sha256_file(artifact),
            }
        )
        is False
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("symbol", "bad", "symbol identity"),
        ("timeframe", "bad", "timeframe identity"),
        ("setup_name", "bad-name", "setup identity"),
        ("strategy_sha256", "bad", "strategy hash"),
        ("dataset_sha256", "bad", "dataset hash"),
        ("code_revision", "bad", "code revision"),
    ],
)
def test_report_validation_rejects_invalid_evidence_identity(
    field: str,
    value: str,
    message: str,
) -> None:
    """Publication validation requires exact symbol, hashes, and revision IDs."""
    values: dict[str, object] = {
        "symbol": "BTCUSDT",
        "setup_name": "TREND",
        "strategy_sha256": SHA256,
        "dataset_sha256": SHA256,
        "code_revision": REVISION,
    }
    report = type("Report", (), {"timeframe": "1h"})()
    if field == "timeframe":
        report.timeframe = value
    else:
        values[field] = value
    validator = cast(Any, futures_oos.FuturesOosEvidenceWriter._validate_report)
    with pytest.raises(ValueError, match=message):
        validator(report, **values)

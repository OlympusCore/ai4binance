"""Replay ingestion validates untrusted artifacts before research consumption."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai4binance.validation.futures_replay import RuntimeFuturesReplayLoader
from ai4binance.whale_fusion.models import DerivativesMetric
from tests.test_futures_replay import _dataset


@pytest.mark.parametrize(
    ("pointer", "value", "message"),
    [
        (("schema_version",), "old", "ENVELOPE_INVALID"),
        (("timeframe",), "2h", "ENVELOPE_INVALID"),
        (("execution_allowed",), True, "ENVELOPE_INVALID"),
        (("candles",), [], "CANDLE_COUNT"),
        (("candles",), {}, "must be an array"),
        (("candles", 0), [], "must be an object"),
        (("candles", 0, "open"), "bad", "candle open is invalid"),
        (("candles", 0, "open"), "NaN", "must be finite"),
        (("candles", 0, "open"), "", "candle open is invalid"),
        (("candles", 0, "timestamp"), "bad", "timestamp is invalid"),
        (("candles", 0, "timestamp"), "2026-09-01", "timezone-aware"),
        (("derivatives",), [], "DERIVATIVES_COUNT"),
        (("derivatives", 0, "metric"), "UNKNOWN", "METRIC_INVALID"),
        (
            ("derivatives", 0, "points", 0, "attributes"),
            {str(i): "v" for i in range(65)},
            "ATTRIBUTES_EXCEEDED",
        ),
    ],
)
def test_loader_rejects_corrupt_wire_fields(
    tmp_path: Path, pointer: tuple[str | int, ...], value: object, message: str
) -> None:
    payload: Any = _dataset().to_artifact_payload()
    parent = payload
    for part in pointer[:-1]:
        parent = parent[part]
    parent[pointer[-1]] = value
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        RuntimeFuturesReplayLoader(tmp_path).load(path)


@pytest.mark.parametrize(
    "raw", [b"", b"{", b"\xff", b'{"duplicate": 1, "duplicate": 2}', b"[]"]
)
def test_loader_rejects_invalid_bytes(tmp_path: Path, raw: bytes) -> None:
    (tmp_path / "replay.json").write_bytes(raw)
    with pytest.raises(
        ValueError, match=r"UNSAFE|INVALID_JSON|DUPLICATE_JSON_KEY|must be an object"
    ):
        RuntimeFuturesReplayLoader(tmp_path).load("replay.json")


@pytest.mark.parametrize("changes", [{"max_bytes": 1}, {"max_candles": 1}])
def test_loader_rejects_unsafe_limits(tmp_path: Path, changes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="safe range"):
        RuntimeFuturesReplayLoader(tmp_path, **changes)


@pytest.mark.parametrize(
    "case", ["symbol", "empty", "spacing", "price", "interest", "provenance"]
)
def test_dataset_rejects_invalid_market_lineage(case: str) -> None:
    dataset = _dataset()
    changes: dict[str, Any] = {}
    message = ""
    if case == "symbol":
        changes = {"symbol": "BTC/USDT"}
        message = "ASCII alphanumeric"
    elif case == "empty":
        changes = {"candles": ()}
        message = "candles are required"
    elif case == "spacing":
        changes = {"candles": dataset.candles[::2]}
        message = "spacing"
    elif case == "price":
        changes = {
            "candles": (
                replace(dataset.candles[0], low=Decimal("0")),
                *dataset.candles[1:],
            )
        }
        message = "prices must be positive"
    else:
        series = dict(dataset.derivatives.series)
        points = list(series[DerivativesMetric.OPEN_INTEREST])
        if case == "interest":
            points[0] = replace(points[0], value=Decimal("0"))
            message = "open interest must be positive"
        else:
            points[0] = replace(
                points[0], provenance=replace(points[0].provenance, source_id="OTHER")
            )
            message = "source lineage"
        series[DerivativesMetric.OPEN_INTEREST] = tuple(points)
        changes = {"derivatives": replace(dataset.derivatives, series=series)}
    with pytest.raises(ValueError, match=message):
        replace(dataset, **changes)


def test_loader_rejects_duplicate_derivative_series(tmp_path: Path) -> None:
    payload: Any = _dataset().to_artifact_payload()
    payload["derivatives"].append(payload["derivatives"][0])
    (tmp_path / "replay.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="METRIC_DUPLICATED"):
        RuntimeFuturesReplayLoader(tmp_path).load("replay.json")

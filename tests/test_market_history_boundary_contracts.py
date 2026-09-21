"""Offline collection rejects malformed requests, data, and stale progress."""

import json
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai4binance.core.errors import ExchangeHttpError, ExchangeTransportError
from ai4binance.data import market_history_continuous as h
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_sync import (
    BinanceVisionArchiveCache,
    MarketHistorySourceUnavailableError,
)
from tests.test_market_history_continuous import NOW, Transport, collector, row


def request_payload() -> dict[str, Any]:
    return {
        "schema_version": "MarketHistoryRefreshRequest/v1",
        "request_id": "request:test",
        "requested_at": NOW.isoformat(),
        "requester": "DASHBOARD",
        "market": "SPOT",
        "symbol": "BTCUSDT",
        "status": "PENDING",
        "blockers": [],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"extra": True},
        {"requested_at": "2026-01-01"},
        {"schema_version": "bad"},
        {"requester": "OTHER"},
        {"market": "UNKNOWN"},
        {"symbol": "../bad"},
        {"blockers": ["GAP"]},
        {"execution_allowed": True},
        {"status": "UNKNOWN"},
    ],
)
def test_refresh_request_rejects_forged_or_invalid_shapes(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request_payload() | overrides), encoding="utf-8")
    result = h.market_history_refresh_status(path)
    assert result["state"] == "DATA_BLOCKED"
    assert result["execution_allowed"] is False
    assert result["blockers"] == ["MARKET_HISTORY_REFRESH_REQUEST_INVALID"]


def test_refresh_request_status_and_size_limits(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    assert h.market_history_refresh_status(path)["state"] == "NOT_RUN"
    assert (
        h._refresh_request_path(tmp_path / "state.json").name
        == "market-history-refresh-request.json"
    )
    path.write_text(" " * 16385, encoding="utf-8")
    assert h.market_history_refresh_status(path)["state"] == "DATA_BLOCKED"
    path.write_text(
        json.dumps(
            request_payload()
            | {"status": "DATA_READY", "completed_at": NOW.isoformat()}
        ),
        encoding="utf-8",
    )
    assert h.market_history_refresh_status(path)["state"] == "DATA_READY"
    with pytest.raises(ValueError, match="timezone-aware"):
        h.enqueue_market_history_refresh_request(
            path,
            market="SPOT",
            symbol="BTCUSDT",
            eligible_symbols=("BTCUSDT",),
            requested_at=NOW.replace(tzinfo=None),
        )
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        h._load(path)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"rateLimits": [None, {"rateLimitType": "ORDERS"}]},
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": True,
                    "limit": 100,
                }
            ]
        },
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "UNKNOWN",
                    "intervalNum": 1,
                    "limit": 100,
                }
            ]
        },
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 0,
                    "limit": 100,
                }
            ]
        },
    ],
)
def test_invalid_exchange_rate_limits_do_not_relax_budget(payload: object) -> None:
    budget = h.PublicRequestBudget()
    budget.configure_from_exchange_info(payload)
    assert budget.seconds_per_weight == 0.05


def test_shared_and_transport_cooldowns_block_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "monotonic", lambda: 10)
    budget = h.PublicRequestBudget(cooldown_until=20)
    with pytest.raises(ExchangeHttpError, match="cooldown"):
        budget.acquire("/api/v3/klines")
    underlying = Mock()
    metered = h.MeteredPublicTransport(
        underlying, tmp_path, sleeper=lambda _: None, cooldown_until=20
    )
    with pytest.raises(ExchangeHttpError, match="cooldown"):
        metered.get_json("/api/v3/klines")
    underlying.get_json.assert_not_called()
    metered.cooldown_until = 0
    underlying.get_json.side_effect = ExchangeTransportError("offline")
    with pytest.raises(ExchangeTransportError):
        metered.get_json("/api/v3/klines")
    assert metered.cooldown_until == 40


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("initial_days", 0, "bounds"),
        ("pages_per_stream", 33, "bounds"),
        ("minimum_candles", 0, "minimum_candles"),
        ("refresh_request_path", Path("relative.json"), "absolute"),
    ],
)
def test_collector_configuration_is_bounded(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    instance = collector(tmp_path, Transport())
    setattr(instance, field, value)
    with pytest.raises(ValueError, match=message):
        instance.__post_init__()


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ValueError("progress exceeds dataset"), "PROGRESS_AHEAD_OF_VERIFIED_DATASET"),
        (ValueError("progress invalid"), "COLLECTION_PROGRESS_INVALID"),
        (ValueError("dataset is missing"), "VERIFIED_DATASET_MISSING"),
        (ValueError("checksum"), "DATASET_INTEGRITY_FAILURE"),
        (ValueError("conflicting candle"), "CONFLICTING_CANDLE"),
        (ValueError("gap"), "DATASET_GAP"),
        (ValueError("time boundary"), "CANDLE_TIME_BOUNDARY_INVALID"),
        (ValueError("response"), "BINANCE_RESPONSE_INVALID"),
        (ExchangeHttpError("private details"), "BINANCE_PUBLIC_SOURCE_FAILURE"),
        (OSError("private path"), "MARKET_HISTORY_IO_FAILURE"),
        (ArithmeticError("private number"), "MARKET_HISTORY_NUMERIC_FAILURE"),
        (ValueError("unknown"), "MARKET_HISTORY_STREAM_INVALID"),
    ],
)
def test_stream_errors_publish_only_safe_reason_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: str, reason: str
) -> None:
    instance = collector(tmp_path, Transport())
    monkeypatch.setattr(instance, "_candles", Mock(side_effect=error))
    result = instance._collect_stream(
        "spot", "BTCUSDT", instance.spot, NOW, kind="klines", timeframe="1m"
    )
    assert result == {
        "market": "spot",
        "symbol": "BTCUSDT",
        "kind": "klines",
        "timeframe": "1m",
        "status": "BLOCKED",
        "reason": reason,
    }


def test_collect_symbol_calls_callback_for_each_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    callback = Mock()
    monkeypatch.setattr(
        instance, "_collect_stream", Mock(return_value={"status": "CURRENT"})
    )
    results = instance._collect_symbol(
        "spot", "BTCUSDT", instance.spot, NOW, on_stream_complete=callback
    )
    assert len(results) == len(instance._collection_kinds("spot"))
    assert callback.call_count == len(results)
    assert instance._completion_ratio(0, 0) == "1.000000"


@pytest.mark.parametrize(
    ("raw", "message"),
    [(None, "object array"), ([1], "object array"), ([], "incomplete")],
)
def test_bulk_snapshot_rejects_bad_schema_and_incomplete_universe(
    tmp_path: Path, raw: object, message: str
) -> None:
    instance = collector(tmp_path, Transport())
    with pytest.raises(ValueError, match=message):
        instance._snapshots(
            "usd_m_futures", ("BTCUSDT",), SimpleNamespace(get_json=lambda _: raw), NOW
        )


def test_bulk_snapshot_saves_selected_symbols_and_safety(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    transport = Mock()
    transport.get_json.return_value = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
    instance._snapshots("usd_m_futures", (), transport, NOW)
    transport.get_json.assert_not_called()
    instance._snapshots("usd_m_futures", ("BTCUSDT",), transport, NOW)
    assert transport.get_json.call_count == 3
    stored = h._load(
        instance.history.archive_root / "usd_m_futures/metadata/premiumIndex.json"
    )
    assert stored["rows"] == [{"symbol": "BTCUSDT"}]
    assert stored["execution_allowed"] is False
    futures_coverage = h._load(
        instance.history.archive_root
        / "usd_m_futures/metadata/wallet-price-coverage.json"
    )
    assert futures_coverage["rows"] == [
        {"symbol": "BTCUSDT"},
        {"symbol": "ETHUSDT"},
    ]


def test_spot_ticker_snapshot_retains_wallet_price_coverage(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    transport = Mock()
    transport.get_json.return_value = [
        {"symbol": "BTCUSDT", "lastPrice": "60000"},
        {"symbol": "HOTUSDT", "lastPrice": "0.0012"},
    ]

    instance._snapshots("spot", ("BTCUSDT",), transport, NOW)

    selected = h._load(instance.history.archive_root / "spot/metadata/ticker-24hr.json")
    coverage = h._load(
        instance.history.archive_root / "spot/metadata/wallet-price-coverage.json"
    )
    assert selected["rows"] == [{"symbol": "BTCUSDT", "lastPrice": "60000"}]
    assert coverage["rows"] == [
        {"symbol": "BTCUSDT", "lastPrice": "60000"},
        {"symbol": "HOTUSDT", "lastPrice": "0.0012"},
    ]
    assert coverage["execution_allowed"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (5, "-1", "volume"),
        (7, "NaN", "volume"),
        (8, "-1", "trade count"),
        (6, "0", "time boundary"),
    ],
)
def test_candle_parser_rejects_invalid_values(
    field: int, value: object, message: str
) -> None:
    data = row(int(NOW.timestamp() * 1000))
    data[field] = value
    with pytest.raises(ValueError, match=message):
        h.ContinuousMarketHistory._parse_rows([data], NOW, NOW + timedelta(minutes=1))


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([[]], "twelve fields"),
        ([None], "twelve fields"),
        ([row(int(NOW.timestamp() * 1000))] * 2, "gap, duplicate"),
    ],
)
def test_candle_parser_rejects_shape_and_duplicate_times(
    rows: list[object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        h.ContinuousMarketHistory._parse_rows(rows, NOW, NOW + timedelta(minutes=2))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "must be an array"),
        ([{}] * 501, "page limit"),
        ([{}], "symbol"),
        ([{"symbol": "BTCUSDT", "fundingTime": "0"}], "pagination"),
    ],
)
def test_futures_details_reject_bad_pages(
    tmp_path: Path, raw: object, message: str
) -> None:
    transport = SimpleNamespace(get_json=lambda *a: raw)
    instance = collector(tmp_path, cast(Transport, transport))
    with pytest.raises(ValueError, match=message):
        instance._details("BTCUSDT", "funding", NOW)


@pytest.mark.parametrize(
    ("kind", "value"), [("funding", "NaN"), ("open_interest", "-1")]
)
def test_futures_details_reject_nonfinite_or_negative_values(
    tmp_path: Path, kind: str, value: object
) -> None:
    item = {
        "symbol": "BTCUSDT",
        "fundingTime": int((NOW - timedelta(hours=1)).timestamp() * 1000),
        "timestamp": int((NOW - timedelta(hours=1)).timestamp() * 1000),
        "fundingRate": value,
        "sumOpenInterest": value,
        "sumOpenInterestValue": value,
    }
    instance = collector(
        tmp_path, cast(Transport, SimpleNamespace(get_json=lambda *a: [item]))
    )
    with pytest.raises(ValueError, match="value is invalid"):
        instance._details("BTCUSDT", kind, NOW)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "row count"),
        ([[]], "schema"),
        (
            [
                [
                    "create_time",
                    "symbol",
                    "sum_open_interest",
                    "sum_open_interest_value",
                ],
                ["bad"],
            ],
            "row is incomplete",
        ),
    ],
)
def test_historical_metrics_reject_malformed_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[object], message: str
) -> None:
    instance = collector(tmp_path, Transport())
    cache = SimpleNamespace(
        verified=Mock(
            return_value=(
                SimpleNamespace(downloaded_bytes=1, network_request_count=1),
                b"fixture",
            )
        )
    )
    instance.history = replace(
        instance.history, source_cache=cast(BinanceVisionArchiveCache, cache)
    )
    monkeypatch.setattr(h, "_csv_rows", lambda *a: rows)
    with pytest.raises(ValueError, match=message):
        instance._historical_metrics(
            "BTCUSDT", tmp_path, tmp_path / "progress.json", {}, NOW
        )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([["2026-09-02 00:00:00", "ETHUSDT", "1", "1"]], "identity"),
        (
            [
                ["2026-09-02 00:00:00", "BTCUSDT", "1", "1"],
                ["2026-09-02 00:10:00", "BTCUSDT", "1", "1"],
            ],
            "gap",
        ),
        ([["2026-09-02 00:00:00", "BTCUSDT", "-1", "1"]], "value"),
    ],
)
def test_historical_metrics_reject_bad_identity_gaps_and_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[object], message: str
) -> None:
    instance = collector(tmp_path, Transport())
    cache = SimpleNamespace(
        verified=Mock(
            return_value=(
                SimpleNamespace(downloaded_bytes=1, network_request_count=1),
                b"fixture",
            )
        )
    )
    instance.history = replace(
        instance.history, source_cache=cast(BinanceVisionArchiveCache, cache)
    )
    monkeypatch.setattr(
        h,
        "_csv_rows",
        lambda *a: [
            ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"],
            *rows,
        ],
    )
    with pytest.raises(ValueError, match=message):
        instance._historical_metrics(
            "BTCUSDT", tmp_path, tmp_path / "progress.json", {}, NOW
        )


def test_historical_metrics_before_cursor_do_not_advance_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    cache = SimpleNamespace(
        verified=Mock(
            return_value=(
                SimpleNamespace(downloaded_bytes=1, network_request_count=1),
                b"fixture",
            )
        )
    )
    instance.history = replace(
        instance.history, source_cache=cast(BinanceVisionArchiveCache, cache)
    )
    monkeypatch.setattr(
        h,
        "_csv_rows",
        lambda *a: [
            ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"],
            ["2026-09-02 00:00:00", "BTCUSDT", "1", "1"],
        ],
    )
    result = instance._historical_metrics(
        "BTCUSDT", tmp_path, tmp_path / "progress.json", {}, NOW
    )
    assert result == {"status": "UNAVAILABLE", "next_at": NOW.isoformat()}


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({}, "fields are missing"),
        (
            {"next_at": "2026-01-01", "requested_start": "2026-01-01"},
            "invalid or in the future",
        ),
    ],
)
def test_saved_progress_requires_complete_aware_timestamps(
    tmp_path: Path, state: dict[str, Any], message: str
) -> None:
    instance = collector(tmp_path, Transport())
    (tmp_path / "collection-progress.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=message):
        instance._progress(tmp_path, NOW)


def test_refresh_dataset_blockers_distinguish_gaps_staleness_and_derivatives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    instance.minimum_candles = 10
    cases = [(1, 0, NOW), (20, 1, NOW), (20, 0, NOW - timedelta(days=10))]
    codes = ["INSUFFICIENT_CANDLES", "DATASET_GAPS", "DATA_STALE"]
    for (count, gaps, stamp), code in zip(cases, codes, strict=True):
        monkeypatch.setattr(
            ParquetOHLCVArchive,
            "manifest",
            Mock(
                return_value=SimpleNamespace(
                    row_count=count, gap_count=gaps, last_timestamp=stamp.isoformat()
                )
            ),
        )
        blockers = instance._refresh_request_data_blockers(
            "usd_m_futures", "BTCUSDT", NOW, [{"kind": "funding", "status": "BLOCKED"}]
        )
        assert f"MARKET_HISTORY_REFRESH_{code}:5m" in blockers
        assert "FUTURES_DERIVATIVES_CONTEXT_UNAVAILABLE" in blockers
    instance._complete_refresh_request({}, NOW, status="DATA_READY", blockers=())
    with pytest.raises(ValueError, match="market is invalid"):
        instance._collection_kinds("unknown")


def test_coin_m_shared_index_and_missing_transport_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    instance.coin_m_contracts = {
        "BTCUSD_A": ("BTCUSD", "PERPETUAL"),
        "BTCUSD_B": ("BTCUSD", "PERPETUAL"),
    }
    candles = Mock(return_value={"status": "CURRENT"})
    monkeypatch.setattr(instance, "_candles", candles)
    assert (
        instance._collect_stream(
            "coin_m_futures",
            "BTCUSD_B",
            instance.spot,
            NOW,
            kind="indexPriceKlines",
            timeframe="1m",
        )["status"]
        == "SHARED"
    )
    candles.assert_not_called()
    assert (
        instance._collect_stream(
            "coin_m_futures",
            "BTCUSD_A",
            instance.spot,
            NOW,
            kind="indexPriceKlines",
            timeframe="1m",
        )["status"]
        == "CURRENT"
    )
    assert (
        instance._collect_stream(
            "spot", "BTCUSDT", instance.spot, NOW, kind="klines", timeframe=None
        )["reason"]
        == "MARKET_HISTORY_STREAM_INVALID"
    )
    with pytest.raises(ValueError, match="transport is unavailable"):
        instance._details("BTCUSD_A", "funding", NOW, market="coin_m_futures")
    instance.coin_m_contracts["BTCUSD_A"] = ("BTCUSD", "CURRENT_QUARTER")
    assert (
        instance._details("BTCUSD_A", "funding", NOW, market="coin_m_futures")["status"]
        == "NOT_APPLICABLE"
    )


def test_coin_m_open_interest_validates_contract_type(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    instance.coin_m_contracts = {"BTCUSD_PERP": ("BTCUSD", "PERPETUAL")}
    instance.coin_m = SimpleNamespace(
        get_json=lambda *a: [{"pair": "BTCUSD", "contractType": "CURRENT_QUARTER"}]
    )
    with pytest.raises(ValueError, match="contract type"):
        instance._details("BTCUSD_PERP", "open_interest", NOW, market="coin_m_futures")


def test_futures_details_current_and_empty_open_interest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(
        tmp_path, cast(Transport, SimpleNamespace(get_json=lambda *a: []))
    )
    assert instance._details("BTCUSDT", "open_interest", NOW)["status"] == "UNAVAILABLE"
    monkeypatch.setattr(
        instance, "_progress", lambda *a: (tmp_path / "progress.json", {}, NOW)
    )
    assert instance._details("BTCUSDT", "funding", NOW)["status"] == "CURRENT"


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([["header"], [], ["invalid"]], "timestamp is invalid"),
        ([["header"], []], "fixture.zip"),
    ],
)
def test_vision_candles_reject_bad_or_missing_timestamps(
    monkeypatch: pytest.MonkeyPatch, rows: list[object], message: str
) -> None:
    monkeypatch.setattr(h, "_csv_rows", lambda *a: rows)
    with pytest.raises(
        (ValueError, MarketHistorySourceUnavailableError), match=message
    ):
        h.ContinuousMarketHistory._parse_vision_candles(
            "fixture.zip",
            b"fixture",
            NOW,
            NOW + timedelta(minutes=1),
            interval=timedelta(minutes=1),
        )


@pytest.mark.parametrize(
    ("raw", "message"), [(None, "must be an array"), ([[]] * 500, "page limit")]
)
def test_rest_candles_reject_bad_pages(
    tmp_path: Path, raw: object, message: str
) -> None:
    instance = collector(tmp_path, Transport())
    with pytest.raises(ValueError, match=message):
        instance._candles(
            "spot", "BTCUSDT", "klines", SimpleNamespace(get_json=lambda *a: raw), NOW
        )
    with pytest.raises(ValueError, match="timeframe is invalid"):
        instance._candles(
            "spot", "BTCUSDT", "klines", instance.spot, NOW, timeframe="bad"
        )


def test_rest_candles_empty_page_keeps_cursor_unavailable(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    result = instance._candles(
        "spot", "BTCUSDT", "klines", SimpleNamespace(get_json=lambda *a: []), NOW
    )
    assert result["status"] == "UNAVAILABLE"
    assert "next_at" in result


def test_metered_transport_updates_budget_and_funding_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "monotonic", lambda: 10)
    budget = Mock()
    transport = h.MeteredPublicTransport(
        SimpleNamespace(get_json=lambda *a: {}),
        tmp_path,
        budget=budget,
        sleeper=lambda _: None,
    )
    transport.get_json("/fapi/v1/fundingRate")
    assert transport._last_funding_request == 10
    transport.get_json("/fapi/v1/exchangeInfo")
    budget.configure_from_exchange_info.assert_called_once_with({})


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("CURRENT", "CANDIDATES_AVAILABLE"),
        ("DELEGATED", "ANALYSIS_UNAVAILABLE"),
        ("DATA_BLOCKED", "DATA_UNAVAILABLE"),
        ("BLOCKED", "ANALYSIS_BLOCKED"),
    ],
)
def test_cycle_projection_preserves_analysis_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, expected: str
) -> None:
    instance = collector(tmp_path, Transport())
    instance.max_workers = 1
    monkeypatch.setattr(
        instance, "_collect_stream", lambda *a, **k: {"status": "CURRENT"}
    )
    instance.on_symbol_ready = lambda *a: {
        "status": kind,
        "candidate_count": 1,
        "dashboard_candidates": [
            {
                "market": "SPOT",
                "symbol": "BTCUSDT",
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            {"market": "SPOT", "symbol": "BTCUSDT", "execution_allowed": True},
        ],
    }
    report = instance.sync_cycle(observed_at=NOW)
    projections = cast(
        dict[str, dict[str, Any]], report["dashboard_opportunity_projection"]
    )
    projection = projections["SPOT"]
    assert projection["status"] == expected
    assert projection["execution_allowed"] is False
    if kind == "CURRENT":
        assert len(projection["opportunities"]) == 1


def test_cycle_failure_persists_safe_retry_state(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    with pytest.raises(ValueError, match="timezone-aware"):
        instance.sync_cycle(observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        instance.record_recoverable_cycle_failure(NOW.replace(tzinfo=None), OSError())
    instance.record_recoverable_cycle_failure(NOW, OSError("private path"))
    state = h._load(instance.history.state_path)
    assert state["status"] == "DEGRADED"
    assert state["last_error_type"] == "OSError"
    assert "private path" not in json.dumps(state)


@pytest.mark.parametrize("known", [True, False])
def test_vision_archive_absence_distinguishes_prelisting_from_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, known: bool
) -> None:
    instance = collector(tmp_path, Transport())
    cache = SimpleNamespace(
        verified=Mock(side_effect=MarketHistorySourceUnavailableError("unpublished"))
    )
    instance.history = replace(
        instance.history, source_cache=cast(BinanceVisionArchiveCache, cache)
    )
    cursor = NOW - timedelta(days=1)
    state: dict[str, object] = (
        {"first_available_at": cursor.isoformat()} if known else {}
    )
    archive = Mock()
    end, unavailable = instance._vision_history(
        market="spot",
        symbol="BTCUSDT",
        kind="klines",
        timeframe="1m",
        archive=archive,
        dataset_symbol="BTCUSDT",
        state=state,
        progress_path=tmp_path / "progress.json",
        cursor=cursor,
        closed_history_end=NOW.replace(hour=0, minute=0),
        interval=timedelta(minutes=1),
        now=NOW,
    )
    archive.update.assert_not_called()
    if known:
        assert end == cursor
        assert unavailable is not None
        assert unavailable["reason"] == "BINANCE_VISION_ARCHIVE_UNAVAILABLE"
    else:
        assert unavailable is None
        assert end == NOW.replace(hour=0, minute=0)
        assert state["next_at"] == end.isoformat()


@pytest.mark.parametrize(
    ("timeframe", "error", "raises"),
    [
        ("1m", "corrupt archive", True),
        ("5m", "kline page contains a gap", False),
        ("5m", "checksum mismatch", True),
    ],
)
def test_vision_gap_fallback_does_not_swallow_integrity_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timeframe: str,
    error: str,
    raises: bool,
) -> None:
    instance = collector(tmp_path, Transport())
    cache = SimpleNamespace(
        verified=Mock(
            return_value=(
                SimpleNamespace(network_request_count=1, downloaded_bytes=1),
                b"fixture",
            )
        )
    )
    instance.history = replace(
        instance.history, source_cache=cast(BinanceVisionArchiveCache, cache)
    )
    monkeypatch.setattr(
        instance, "_parse_vision_candles", Mock(side_effect=ValueError(error))
    )
    cursor = NOW.replace(day=1) - timedelta(days=40)
    kwargs: dict[str, Any] = {
        "market": "spot",
        "symbol": "BTCUSDT",
        "kind": "klines",
        "timeframe": timeframe,
        "archive": Mock(),
        "dataset_symbol": "BTCUSDT",
        "state": {},
        "progress_path": tmp_path / "progress.json",
        "cursor": cursor,
        "closed_history_end": NOW,
        "interval": timedelta(minutes=1),
        "now": NOW,
    }
    if raises:
        with pytest.raises(ValueError, match=error):
            instance._vision_history(**kwargs)
    else:
        assert instance._vision_history(**kwargs) == (cursor, None)

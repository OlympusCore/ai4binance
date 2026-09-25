"""Deterministic canonical Binance market-data gateway tests."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.cli import market_gateway as gateway_cli
from ai4binance.cli.market_gateway import (
    _adaptive_candidates,
    _blockers,
    _GatewayStateHeartbeat,
    _reconnect_delay,
)
from ai4binance.core.errors import ExchangeHttpError
from ai4binance.data import market_data_gateway as gateway_module
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_data_gateway import (
    AdaptiveSubscriptionPlan,
    BinanceMarketDataGateway,
    CanonicalMarketStreamProcessor,
    CombinedStreamConnectionManager,
    DirectTimeframeWriter,
    MarketStreamGapError,
    SharedMarketCache,
    build_gateway,
)
from ai4binance.exchange import rate_limit as rate_limit_module
from ai4binance.exchange.public_stream import BinanceSpotKlineParser, SpotKlineUpdate
from ai4binance.exchange.rate_limit import (
    WeightedRateLimitGovernor,
    public_request_weight,
)
from ai4binance.schemas import OHLCVCandle

START = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)


def candle(index: int) -> OHLCVCandle:
    price = Decimal(100 + index)
    return OHLCVCandle(
        timestamp=START + timedelta(minutes=index),
        open=price,
        high=price + 1,
        low=price - 1,
        close=price,
        volume=Decimal("2"),
    )


def test_adaptive_plan_keeps_expensive_streams_candidate_only() -> None:
    symbols = tuple(f"C{index}USDT" for index in range(50))
    plan = AdaptiveSubscriptionPlan(symbols, symbols[:20], include_mark_price=True)

    assert len(plan.candidates) == 10
    assert len(plan.streams()) == 380
    for timeframe in ("5m", "15m", "1h", "4h", "1d"):
        assert (
            sum(stream.endswith(f"@kline_{timeframe}") for stream in plan.streams())
            == 50
        )
    assert sum("@depth" in stream for stream in plan.streams()) == 10
    assert sum("@markPrice" in stream for stream in plan.streams()) == 10
    manager = CombinedStreamConnectionManager(
        "wss://stream.binance.com:9443/stream", plan
    )
    assert "streams=c0usdt@kline_5m" in manager.url
    assert len(plan.streams()) <= 1_024


def test_gateway_uses_official_combined_stream_routes(tmp_path: Path) -> None:
    gateway = build_gateway(
        tmp_path,
        spot_symbols=("BTCUSDT",),
        futures_symbols=("BTCUSDT",),
    )

    assert gateway.spot.url.startswith("wss://stream.binance.com:9443/stream?")
    assert gateway.futures.url.startswith("wss://fstream.binance.com/stream?")
    assert "/public/" not in gateway.futures.url


def test_direct_writer_persists_only_native_timeframes(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    writer = DirectTimeframeWriter(archive, "BINANCE_SPOT_WEBSOCKET_DIRECT")

    writer.append("BTCUSDT", "5m", candle(0), START + timedelta(hours=1))
    writer.append("BTCUSDT", "15m", candle(15), START + timedelta(hours=1))

    assert archive.manifest("BTCUSDT", "5m").row_count == 1
    assert archive.manifest("BTCUSDT", "15m").row_count == 1
    with pytest.raises(FileNotFoundError):
        archive.manifest("BTCUSDT", "1m")


def test_live_gap_requires_rest_recovery_before_append(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    writer = DirectTimeframeWriter(archive, "BINANCE_SPOT_WEBSOCKET_DIRECT")
    writer.append("BTCUSDT", "5m", candle(0), START + timedelta(minutes=1))

    with pytest.raises(MarketStreamGapError, match="REST recovery"):
        writer.append("BTCUSDT", "5m", candle(10), START + timedelta(minutes=11))

    assert archive.manifest("BTCUSDT", "5m").row_count == 1


def test_shared_cache_writes_local_read_path_without_execution_authority(
    tmp_path: Path,
) -> None:
    cache = SharedMarketCache(tmp_path)
    assert cache.apply(
        {"e": "24hrTicker", "s": "BTCUSDT", "c": "60000", "q": "10"},
        START,
    )
    assert cache.apply(
        {"e": "bookTicker", "s": "BTCUSDT", "b": "59999", "a": "60001"},
        START,
    )
    assert cache.apply(
        {
            "e": "markPriceUpdate",
            "s": "BTCUSDT",
            "p": "60000",
            "i": "59990",
            "r": "0.0001",
            "E": 1_789_598_400_000,
            "T": 1_789_627_200_000,
        },
        START,
    )
    cache.flush(START)

    ticker = json.loads((tmp_path / "ticker-24hr.json").read_text(encoding="utf-8"))
    book = json.loads((tmp_path / "ticker-bookTicker.json").read_text(encoding="utf-8"))
    premium = json.loads((tmp_path / "premium-index.json").read_text(encoding="utf-8"))
    assert ticker["rows"][0]["lastPrice"] == "60000"
    assert book["rows"][0]["bidPrice"] == "59999"
    assert premium["rows"][0]["lastFundingRate"] == "0.0001"
    assert ticker["execution_allowed"] is False
    assert ticker["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_shared_cache_waits_for_complete_universe_before_publish(
    tmp_path: Path,
) -> None:
    cache = SharedMarketCache(tmp_path, frozenset({"BTCUSDT", "ETHUSDT"}))
    cache.apply(
        {"e": "24hrTicker", "s": "BTCUSDT", "c": "60000", "q": "10"},
        START,
    )
    cache.flush(START)
    assert not (tmp_path / "ticker-24hr.json").exists()

    cache.apply(
        {"e": "24hrTicker", "s": "ETHUSDT", "c": "3000", "q": "10"},
        START,
    )
    cache.flush(START)
    payload = json.loads((tmp_path / "ticker-24hr.json").read_text(encoding="utf-8"))
    assert [row["symbol"] for row in payload["rows"]] == ["BTCUSDT", "ETHUSDT"]


def test_adaptive_candidates_prefer_current_opportunity_projection() -> None:
    state: dict[str, object] = {
        "dashboard_opportunity_projection": {
            "USD_M_FUTURES": {
                "opportunities": [
                    {"market": "USD_M_FUTURES", "symbol": "SOLUSDT"},
                    {"market": "USD_M_FUTURES", "symbol": "BTCUSDT"},
                ]
            }
        }
    }

    assert _adaptive_candidates(state, "USD_M_FUTURES", ("ETHUSDT",)) == (
        "SOLUSDT",
        "BTCUSDT",
        "ETHUSDT",
    )


def test_reconnect_delay_is_bounded() -> None:
    assert [_reconnect_delay(attempt) for attempt in (1, 2, 3, 10)] == [
        1.0,
        2.0,
        4.0,
        60.0,
    ]


def test_gateway_blockers_are_fail_closed_on_invalid_shape() -> None:
    assert _blockers({"blockers": ["MARKET_DATA_BACKFILL_PENDING"]}) == {
        "MARKET_DATA_BACKFILL_PENDING"
    }
    assert _blockers({"blockers": "unexpected"}) == {"MARKET_GATEWAY_BLOCKERS_INVALID"}


def test_gateway_reuses_the_canonical_continuous_collector_builder() -> None:
    source = Path(gateway_cli.__file__).read_text(encoding="utf-8")

    assert "build_continuous_market_history(" in source
    assert "build_market_depth_collector(" in source
    assert '"market-history-refresh-request.json"' not in source


def test_gateway_heartbeat_preserves_bootstrap_evidence(tmp_path: Path) -> None:
    path = tmp_path / "market-history-latest.json"
    path.write_text(
        json.dumps(
            {
                "observed_at": "2026-01-01T00:00:00+00:00",
                "result_count": 7,
                "blockers": ["OPPORTUNITY_ANALYSIS_DATA_BLOCKED"],
            }
        ),
        encoding="utf-8",
    )
    heartbeat = _GatewayStateHeartbeat(path, interval_seconds=60.0)

    heartbeat(datetime(2026, 9, 17, 10, 0, tzinfo=UTC))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["result_count"] == 7
    assert payload["status"] == "DEGRADED"
    assert payload["ingestion_mode"] == "WEBSOCKET_LIVE"
    assert payload["blockers"] == ["OPPORTUNITY_ANALYSIS_DATA_BLOCKED"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_gateway_helpers_cover_invalid_and_bounded_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"blockers": "invalid"}', encoding="utf-8")
    heartbeat = _GatewayStateHeartbeat(path, interval_seconds=0)
    monkeypatch.setattr(time, "monotonic", lambda: 1.0)
    heartbeat(START)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["blockers"] == ["MARKET_GATEWAY_STATE_BLOCKERS_INVALID"]
    assert gateway_cli._absolute(Path("relative")) == Path.cwd() / "relative"
    assert gateway_cli._adaptive_candidates({}, "SPOT", ("btcusdt",)) == ("BTCUSDT",)
    with pytest.raises(ValueError, match="positive"):
        _reconnect_delay(0)


def test_gateway_heartbeat_handles_read_failures_and_throttles_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("not-json", encoding="utf-8")
    heartbeat = _GatewayStateHeartbeat(path, interval_seconds=10)
    monotonic = iter((10.0, 11.0))
    monkeypatch.setattr(time, "monotonic", lambda: next(monotonic))
    heartbeat(START)
    first = path.read_text(encoding="utf-8")
    heartbeat(START)
    assert path.read_text(encoding="utf-8") == first


def test_gateway_rejects_invalid_cycles_and_routes_cli_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="positive"):
        gateway_cli.run_gateway(object(), max_cycles=0)  # type: ignore[arg-type]
    monkeypatch.setattr(gateway_cli, "Settings", lambda: "settings")
    monkeypatch.setattr(
        gateway_cli,
        "run_gateway",
        lambda settings, max_cycles: 7
        if settings == "settings" and max_cycles == 2
        else 1,
    )
    assert gateway_cli.main(("--max-cycles", "2")) == 7


def test_gateway_run_returns_fail_closed_for_fatal_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _Lease:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> "_Lease":
            return self

        def __exit__(self, *args: object) -> None:
            del args

    synchronizer = type(
        "Synchronizer",
        (),
        {
            "universe_provider": type(
                "Provider",
                (),
                {"spot_transport": object(), "futures_transport": object()},
            )()
        },
    )()
    monkeypatch.setattr(
        gateway_cli,
        "build_market_history_synchronizer",
        lambda _settings: synchronizer,
    )
    monkeypatch.setattr(gateway_cli, "SingleInstanceLease", _Lease)

    class _Collector:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_cycle(self, *, observed_at: datetime) -> dict[str, object]:
            del observed_at
            return {"blockers": ["PUBLIC_MARKET_UNIVERSE_UNAVAILABLE"]}

    monkeypatch.setattr(
        gateway_cli,
        "build_continuous_market_history",
        lambda *_args, **_kwargs: _Collector(),
    )
    settings = type(
        "Settings",
        (),
        {
            "market_history_initial_days": 1,
            "market_history_pages_per_stream": 1,
            "market_history_max_workers": 1,
            "minimum_closed_candles": 1,
            "symbol": "BTCUSDT",
            "fixed_symbols": (),
            "priority_watchlist": (),
            "market_history_state_path": tmp_path / "state.json",
        },
    )()
    assert gateway_cli.run_gateway(settings, max_cycles=1) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "DATA_BLOCKED"


def test_gateway_run_completes_one_valid_local_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Lease:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> "_Lease":
            return self

        def __exit__(self, *args: object) -> None:
            del args

    universe = type(
        "Universe",
        (),
        {"blockers": (), "spot_symbols": ("BTCUSDT",), "futures_symbols": ()},
    )()
    synchronizer = type(
        "Synchronizer",
        (),
        {
            "universe_provider": type(
                "Provider",
                (),
                {"spot_transport": object(), "futures_transport": object()},
            )(),
            "_eligible_universe": lambda self, _at, force_refresh: universe,
        },
    )()

    class _Collector:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_cycle(self, *, observed_at: datetime) -> dict[str, object]:
            del observed_at
            return {"blockers": []}

    class _Gateway:
        async def run_once(self) -> tuple[str, str]:
            return ("PLANNED_ROLLOVER", "PLANNED_ROLLOVER")

    monkeypatch.setattr(
        gateway_cli,
        "build_continuous_market_history",
        lambda *_args, **_kwargs: _Collector(),
    )
    monkeypatch.setattr(gateway_cli, "SingleInstanceLease", _Lease)
    monkeypatch.setattr(
        gateway_cli,
        "build_market_history_synchronizer",
        lambda _settings: synchronizer,
    )
    gateway = _Gateway()
    monkeypatch.setattr(
        gateway_cli,
        "build_gateway",
        lambda *_args, **_kwargs: gateway,
    )
    settings = type(
        "Settings",
        (),
        {
            "market_history_initial_days": 1,
            "market_history_pages_per_stream": 1,
            "market_history_max_workers": 1,
            "minimum_closed_candles": 1,
            "symbol": "BTCUSDT",
            "fixed_symbols": (),
            "priority_watchlist": (),
            "market_history_state_path": tmp_path / "state.json",
            "dataset_directory": tmp_path / "dataset",
        },
    )()
    assert gateway_cli.run_gateway(settings, max_cycles=1) == 0


def test_gateway_recovers_gap_and_reconnects_before_a_completed_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Lease:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> "_Lease":
            return self

        def __exit__(self, *args: object) -> None:
            del args

    universe = type(
        "Universe",
        (),
        {"blockers": (), "spot_symbols": ("BTCUSDT",), "futures_symbols": ()},
    )()
    synchronizer = type(
        "Synchronizer",
        (),
        {
            "universe_provider": type(
                "Provider",
                (),
                {"spot_transport": object(), "futures_transport": object()},
            )(),
            "_eligible_universe": lambda self, _at, force_refresh: universe,
        },
    )()

    class _Collector:
        calls = 0

        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_cycle(self, *, observed_at: datetime) -> dict[str, object]:
            del observed_at
            self.calls += 1
            return {"blockers": []}

    class _Gateway:
        calls = 0

        async def run_once(self) -> tuple[str, str]:
            self.calls += 1
            if self.calls == 1:
                raise MarketStreamGapError("recover")
            if self.calls == 2:
                raise OSError("temporary")
            return ("PLANNED_ROLLOVER", "PLANNED_ROLLOVER")

    monkeypatch.setattr(
        gateway_cli,
        "build_continuous_market_history",
        lambda *_args, **_kwargs: _Collector(),
    )
    monkeypatch.setattr(gateway_cli, "SingleInstanceLease", _Lease)
    fake_time = type("Time", (), {"sleep": staticmethod(lambda _seconds: None)})()
    monkeypatch.setattr(gateway_cli, "time", fake_time)
    monkeypatch.setattr(
        gateway_cli,
        "build_market_history_synchronizer",
        lambda _settings: synchronizer,
    )
    gateway = _Gateway()
    monkeypatch.setattr(
        gateway_cli,
        "build_gateway",
        lambda *_args, **_kwargs: gateway,
    )
    settings = type(
        "Settings",
        (),
        {
            "market_history_initial_days": 1,
            "market_history_pages_per_stream": 1,
            "market_history_max_workers": 1,
            "minimum_closed_candles": 1,
            "symbol": "BTCUSDT",
            "fixed_symbols": (),
            "priority_watchlist": (),
            "market_history_state_path": tmp_path / "state.json",
            "dataset_directory": tmp_path / "dataset",
            "market_history_live_interval_seconds": 1.0,
        },
    )()
    assert gateway_cli.run_gateway(settings, max_cycles=1) == 0


def test_gateway_converts_lock_errors_to_blocked_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _Lease:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> "_Lease":
            raise RuntimeError("runtime instance is already active")

        def __exit__(self, *args: object) -> None:
            del args

    synchronizer = type(
        "Synchronizer",
        (),
        {
            "universe_provider": type(
                "Provider",
                (),
                {"spot_transport": object(), "futures_transport": object()},
            )()
        },
    )()
    monkeypatch.setattr(gateway_cli, "SingleInstanceLease", _Lease)
    monkeypatch.setattr(
        gateway_cli,
        "build_market_history_synchronizer",
        lambda _settings: synchronizer,
    )
    monkeypatch.setattr(
        gateway_cli,
        "build_continuous_market_history",
        lambda *_args, **_kwargs: object(),
    )
    settings = type(
        "Settings",
        (),
        {
            "market_history_initial_days": 1,
            "market_history_pages_per_stream": 1,
            "market_history_max_workers": 1,
            "minimum_closed_candles": 1,
            "symbol": "BTCUSDT",
            "fixed_symbols": (),
            "priority_watchlist": (),
            "market_history_state_path": tmp_path / "state.json",
        },
    )()
    assert gateway_cli.run_gateway(settings, max_cycles=1) == 2
    assert json.loads(capsys.readouterr().out)["blockers"] == [
        "MARKET_GATEWAY_ALREADY_RUNNING"
    ]


def test_gateway_retries_backfill_then_blocks_an_invalid_universe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Lease:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> "_Lease":
            return self

        def __exit__(self, *args: object) -> None:
            del args

    synchronizer = type(
        "Synchronizer",
        (),
        {
            "universe_provider": type(
                "Provider",
                (),
                {"spot_transport": object(), "futures_transport": object()},
            )(),
            "_eligible_universe": lambda self, _at, force_refresh: type(
                "Universe", (), {"blockers": ("UNIVERSE_BLOCKED",)}
            )(),
        },
    )()

    class _Collector:
        calls = 0

        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_cycle(self, *, observed_at: datetime) -> dict[str, object]:
            del observed_at
            self.calls += 1
            if self.calls == 1:
                return {"blockers": ["MARKET_DATA_BACKFILL_PENDING"]}
            return {"blockers": []}

    monkeypatch.setattr(
        gateway_cli,
        "build_continuous_market_history",
        lambda *_args, **_kwargs: _Collector(),
    )
    monkeypatch.setattr(gateway_cli, "SingleInstanceLease", _Lease)
    monkeypatch.setattr(
        gateway_cli,
        "build_market_history_synchronizer",
        lambda _settings: synchronizer,
    )
    monkeypatch.setattr(
        time,
        "sleep",
        lambda _seconds: None,
    )
    settings = type(
        "Settings",
        (),
        {
            "market_history_initial_days": 1,
            "market_history_pages_per_stream": 1,
            "market_history_max_workers": 1,
            "minimum_closed_candles": 1,
            "symbol": "BTCUSDT",
            "fixed_symbols": (),
            "priority_watchlist": (),
            "market_history_state_path": tmp_path / "state.json",
            "market_history_live_interval_seconds": 1.0,
        },
    )()
    assert gateway_cli.run_gateway(settings, max_cycles=1) == 2


def test_governor_uses_runtime_limits_headers_and_hard_stop() -> None:
    now = [0.0]
    governor = WeightedRateLimitGovernor(
        clock=lambda: now[0],
        monotonic=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    governor.configure_from_exchange_info(
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 100,
                }
            ]
        }
    )
    governor.observe_headers({"X-MBX-USED-WEIGHT-1M": "89"})

    with pytest.raises(ExchangeHttpError, match="hard stop"):
        governor.reserve(1)

    status = governor.status()
    assert status["windows"] == (
        {
            "window_seconds": 60,
            "limit": 100,
            "used": 89,
            "usage_ratio": 0.89,
        },
    )
    assert status["state"] == "THROTTLE"


def test_governor_delays_supplemental_work_at_warning_band() -> None:
    now = [0.0]
    governor = WeightedRateLimitGovernor(
        clock=lambda: now[0],
        monotonic=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    governor.configure_from_exchange_info(
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 100,
                }
            ]
        }
    )
    governor.observe_headers({"X-MBX-USED-WEIGHT-1M": "80"})

    governor.reserve(1)

    assert now[0] == 60.0
    windows = governor.status()["windows"]
    assert isinstance(windows, tuple)
    assert isinstance(windows[0], dict)
    assert windows[0]["used"] == 1


def test_endpoint_weight_accounts_for_requested_page_size() -> None:
    assert public_request_weight("/fapi/v1/klines", {"limit": 99}) == 1
    assert public_request_weight("/fapi/v1/klines", {"limit": 499}) == 2
    assert public_request_weight("/fapi/v1/klines", {"limit": 1_000}) == 5
    assert public_request_weight("/api/v3/ticker/24hr") == 80
    assert public_request_weight("/api/v3/ticker/24hr", {"symbol": "BTCUSDT"}) == 2


def test_rate_limit_governor_rejects_invalid_and_resets_elapsed_windows() -> None:
    now = [0.0]
    with pytest.raises(ValueError, match="strictly increasing"):
        rate_limit_module.RateLimitBands(warning=0.6, soft_limit=0.7)
    governor = WeightedRateLimitGovernor(
        clock=lambda: now[0], monotonic=lambda: now[0], sleeper=lambda _: None
    )
    governor.configure_from_exchange_info("invalid")
    with pytest.raises(ExchangeHttpError, match="not configured"):
        governor.reserve(1)
    governor.configure_from_exchange_info(
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "BAD",
                    "intervalNum": "x",
                    "limit": 0,
                }
            ]
        }
    )
    governor.configure_from_exchange_info(
        {"rateLimits": [None, {"rateLimitType": "REQUEST_WEIGHT"}]}
    )
    governor.configure_from_exchange_info(
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "SECOND",
                    "intervalNum": 1,
                    "limit": 10,
                }
            ]
        }
    )
    governor.observe_headers({"X-MBX-USED-WEIGHT-1S": "bad"})
    with pytest.raises(ValueError, match="positive"):
        governor.reserve(0)
    governor.reserve(1, priority=rate_limit_module.RequestPriority.METADATA)
    now[0] = 2.0
    assert governor.status()["windows"][0]["used"] == 0  # type: ignore[index]
    governor.apply_retry_after(0, banned=True)
    with pytest.raises(ExchangeHttpError, match="cooldown"):
        governor.reserve(1)


def test_endpoint_weights_cover_depth_and_fallback_routes() -> None:
    assert public_request_weight("/fapi/v1/klines", {"limit": 99}) == 1
    assert public_request_weight("/api/v3/depth", {"limit": 101}) == 25
    assert public_request_weight("/api/v3/depth", {"limit": 600}) == 50
    assert public_request_weight("/fapi/v1/depth", {"limit": 2_000}) == 20
    assert public_request_weight("/fapi/v1/ticker/bookTicker") == 5
    assert public_request_weight("/api/v3/exchangeInfo") == 20
    assert public_request_weight("/unknown") == 40


def test_processor_handles_cache_and_invalid_combined_stream_payloads() -> None:
    writes: list[tuple[str, str]] = []

    class _Writer:
        def append(self, symbol: str, timeframe: str, *_args: object) -> None:
            writes.append((symbol, timeframe))

    class _Cache:
        def __init__(self) -> None:
            self.flushed = 0

        def apply(self, payload: object, _observed_at: datetime) -> bool:
            return payload == {"e": "24hrTicker"}

        def flush(self, _observed_at: datetime) -> None:
            self.flushed += 1

    cache = _Cache()
    processor = CanonicalMarketStreamProcessor(
        "SPOT",
        cast(DirectTimeframeWriter, _Writer()),
        cast(SharedMarketCache, cache),
        monotonic=lambda: 1.0,
    )
    assert processor.process('{"e":"24hrTicker"}') == "CACHE_UPDATED"
    assert cache.flushed == 1
    assert processor.process('{"e":"unknown"}') == "IGNORED_UNSUPPORTED_EVENT"
    with pytest.raises(ValueError, match="payload must be an object"):
        processor.process("[]")
    with pytest.raises(ValueError, match="data must be an object"):
        processor.process('{"data": []}')


def test_dual_gateway_flushes_both_caches_after_connections_finish() -> None:
    class _Connection:
        async def run_once(self, _handler: object) -> str:
            return "PLANNED_ROLLOVER"

    class _Cache:
        def __init__(self) -> None:
            self.flushes = 0

        def flush(self, _observed_at: datetime) -> None:
            self.flushes += 1

    class _Processor:
        def __init__(self) -> None:
            self.cache = _Cache()

        def process(self, _message: object) -> None:
            return None

    spot_processor = _Processor()
    futures_processor = _Processor()
    gateway = BinanceMarketDataGateway(
        cast(CombinedStreamConnectionManager, _Connection()),
        cast(CombinedStreamConnectionManager, _Connection()),
        cast(CanonicalMarketStreamProcessor, spot_processor),
        cast(CanonicalMarketStreamProcessor, futures_processor),
    )
    assert asyncio.run(gateway.run_once()) == ("PLANNED_ROLLOVER", "PLANNED_ROLLOVER")
    assert spot_processor.cache.flushes == futures_processor.cache.flushes == 1


def test_gateway_rejects_invalid_inputs_and_processes_closed_kline(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="plan is invalid"):
        AdaptiveSubscriptionPlan(("not valid!",))
    with pytest.raises(ValueError, match="connection capacity"):
        AdaptiveSubscriptionPlan(("BTCUSDT",), maximum_streams=1)
    with pytest.raises(ValueError, match="connection configuration"):
        CombinedStreamConnectionManager(
            "https://invalid", AdaptiveSubscriptionPlan(("BTCUSDT",))
        )

    cache = SharedMarketCache(tmp_path)
    assert not cache.apply({"e": "24hrTicker", "s": "!"}, START)
    assert not cache.apply({"e": "24hrTicker", "s": "BTCUSDT", "c": []}, START)
    assert not cache.apply({"e": "bookTicker", "s": "BTCUSDT", "b": []}, START)
    assert not cache.apply({"e": "markPriceUpdate", "s": "BTCUSDT", "p": []}, START)
    assert not cache.apply({"e": "unknown", "s": "BTCUSDT"}, START)
    with pytest.raises(ValueError, match="timezone-aware"):
        cache.flush(datetime(2026, 1, 1))

    writer = DirectTimeframeWriter(ParquetOHLCVArchive(tmp_path / "archive"), "test")
    with pytest.raises(ValueError, match="unsupported"):
        writer.append("BTCUSDT", "1m", candle(0), START)
    with pytest.raises(ValueError, match="timezone-aware"):
        writer.append(
            "BTCUSDT",
            "5m",
            replace(candle(0), timestamp=datetime(2026, 1, 1)),
            START,
        )

    update = SpotKlineUpdate(
        event_time=START + timedelta(minutes=5),
        symbol="BTCUSDT",
        interval="5m",
        open_time=START,
        close_time=START + timedelta(minutes=5) - timedelta(milliseconds=1),
        first_trade_id=1,
        last_trade_id=2,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("1"),
        close=Decimal("2"),
        volume=Decimal("3"),
        trade_count=2,
        is_closed=True,
    )
    writes: list[tuple[str, str]] = []
    processor = CanonicalMarketStreamProcessor(
        "SPOT",
        cast(
            DirectTimeframeWriter,
            SimpleNamespace(
                append=lambda symbol, timeframe, *_: writes.append((symbol, timeframe))
            ),
        ),
        cache,
        parser=cast(
            BinanceSpotKlineParser,
            SimpleNamespace(parse=lambda _: update),
        ),
        activity_observer=lambda _: None,
    )
    assert processor.process('{"e":"kline"}') == "CLOSED_5M_APPLIED"
    assert writes == [("BTCUSDT", "5m")]
    processor.parser = SimpleNamespace(parse=lambda _: object())  # type: ignore[assignment]
    assert processor.process('{"e":"kline"}') == "RECONNECT_REQUIRED"


def test_connection_manager_handles_timeout_and_rejects_nontext_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = AdaptiveSubscriptionPlan(("BTCUSDT",))

    class _Clock:
        values = iter((START, START, START + timedelta(seconds=2)))

        @staticmethod
        def now(_timezone: object) -> datetime:
            return next(_Clock.values)

    class _Socket:
        async def recv(self) -> object:
            raise TimeoutError

    class _Connection:
        async def __aenter__(self) -> _Socket:
            return _Socket()

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(gateway_module, "datetime", _Clock)
    monkeypatch.setattr(
        gateway_module, "connect", lambda *_args, **_kwargs: _Connection()
    )
    manager = CombinedStreamConnectionManager(
        "wss://example.test/stream", plan, maximum_connection_age=timedelta(seconds=1)
    )
    assert (
        asyncio.run(manager.run_once(lambda _message: asyncio.sleep(0)))
        == "PLANNED_ROLLOVER"
    )

    class _NonTextSocket(_Socket):
        async def recv(self) -> object:
            return 123

    class _NonTextConnection(_Connection):
        async def __aenter__(self) -> _NonTextSocket:
            return _NonTextSocket()

    _Clock.values = iter((START, START))
    monkeypatch.setattr(
        gateway_module, "connect", lambda *_args, **_kwargs: _NonTextConnection()
    )
    with pytest.raises(ValueError, match="fragments"):
        asyncio.run(manager.run_once(lambda _message: asyncio.sleep(0)))

"""Deterministic evidence, separation, and refresh tests for market monitoring."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from ai4binance.application.opportunity_monitor import (
    MARKET_TIMEFRAMES,
    SAFE_STATE,
    diagnose_opportunity_generation,
    has_complete_measurable_opportunity,
    has_complete_measurable_trade_plan,
    inspect_market_data,
    market_symbols,
    monitor_directory,
    read_monitor,
    refresh_monitor,
    universe_monitor_summary,
)
from ai4binance.cli.opportunity_monitor import refresh_candle_windows
from ai4binance.compatibility.opportunity_monitor import (
    SAFE_STATE as COMPATIBILITY_SAFE_STATE,
)
from ai4binance.compatibility.opportunity_monitor import (
    refresh_monitor as compatibility_refresh_monitor,
)
from ai4binance.compatibility import opportunity_monitor as monitor_module
from ai4binance.config import Settings
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_sync import read_cached_market_universe
from ai4binance.domain.opportunity_observation import estimate_measurable_trade_plan
from ai4binance.exchange.client import BinancePublicClient
from ai4binance.exchange.models import MarketKline
from ai4binance.opportunity_intelligence import TIMEFRAME_DURATIONS
from ai4binance.opportunity_radar import build_opportunity_radar_snapshot
from ai4binance.schemas import MarketSnapshot, OHLCVCandle
from ai4binance.storage import JsonlAuditStore

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_application_facade_preserves_opportunity_monitor_identity() -> None:
    assert refresh_monitor is compatibility_refresh_monitor
    assert SAFE_STATE is COMPATIBILITY_SAFE_STATE


def test_monitor_artifact_boundaries_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="market or symbol"):
        monitor_directory(tmp_path, "INVALID", "BTCUSDT")
    with pytest.raises(ValueError, match="monitor market"):
        market_symbols(tmp_path, "INVALID", NOW)
    assert read_monitor(tmp_path, "SPOT", "BTCUSDT")["status"] == "NOT_SCANNED"
    path = monitor_directory(tmp_path, "SPOT", "BTCUSDT")
    path.mkdir(parents=True)
    latest = path / "latest.json"
    latest.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="authority"):
        read_monitor(tmp_path, "SPOT", "BTCUSDT")
    latest.write_text(
        json.dumps({**SAFE_STATE, "market": "SPOT", "symbol": "ETHUSDT"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identity"):
        read_monitor(tmp_path, "SPOT", "BTCUSDT")
    with pytest.raises(ValueError, match="timezone-aware"):
        universe_monitor_summary(
            tmp_path,
            ParquetOHLCVArchive(tmp_path / "data"),
            market="SPOT",
            symbols=(),
            now=datetime(2026, 1, 1),
            minimum_candles=1,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"entry": "PENDING_VALIDATED_LEVEL"},
        {"stop_loss": None},
        {"tp1": "0"},
        {"tp2": "104"},
        {"tp3": "104"},
        {"target_risk_reward": "NaN"},
        {"direction": "WATCH_ONLY"},
        {"direction": "BEARISH"},
    ],
)
def test_measurable_trade_plan_rejects_missing_or_invalid_geometry(
    overrides: dict[str, object],
) -> None:
    candidate: dict[str, object] = {
        "direction": "BULLISH",
        "entry": "101",
        "stop_loss": "98",
        "tp1": "105",
        "tp2": "108",
        "tp3": "111",
        "target_risk_reward": "2",
    }
    candidate.update(overrides)

    assert has_complete_measurable_trade_plan(candidate) is False


def test_measurable_trade_plan_accepts_complete_directional_geometry() -> None:
    assert has_complete_measurable_trade_plan(
        {
            "direction": "BEARISH_CAUTION",
            "entry": "101",
            "stop_loss": "104",
            "tp1": "98",
            "tp2": "95",
            "tp3": "92",
            "target_risk_reward": "1",
        }
    )


@pytest.mark.parametrize("direction", ["BULLISH", "BEARISH_CAUTION"])
def test_trade_plan_estimate_contains_all_measurable_levels(direction: str) -> None:
    plan = estimate_measurable_trade_plan(
        entry=Decimal("100"),
        risk=Decimal("2"),
        direction=direction,
    )

    assert set(plan) == {
        "entry",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "target_risk_reward",
    }
    assert has_complete_measurable_trade_plan({**plan, "direction": direction})


@pytest.mark.parametrize(
    ("market", "direction", "side", "extra"),
    [
        ("SPOT", "BULLISH", "BUY", {}),
        ("SPOT", "BEARISH", "SELL", {}),
        ("USD_M_FUTURES", "BULLISH", "LONG", {"leverage": 1}),
        ("USD_M_FUTURES", "BEARISH", "SHORT", {"leverage": 3}),
    ],
)
def test_complete_opportunity_requires_market_specific_side_and_sizing(
    market: str,
    direction: str,
    side: str,
    extra: dict[str, object],
) -> None:
    bullish = direction == "BULLISH"
    candidate: dict[str, object] = {
        "market": market,
        "symbol": "BTCUSDT",
        "direction": direction,
        "side": side,
        "quantity": "0.5",
        "entry": "100",
        "stop_loss": "98" if bullish else "102",
        "tp1": "104" if bullish else "96",
        "tp2": "106" if bullish else "94",
        "tp3": "108" if bullish else "92",
        "target_risk_reward": "2",
        **extra,
    }

    assert has_complete_measurable_opportunity(candidate)
    candidate["quantity"] = "0"
    assert not has_complete_measurable_opportunity(candidate)


def test_generation_diagnostic_distinguishes_no_setup_data_and_sizing() -> None:
    no_setup = diagnose_opportunity_generation(
        {
            "market": "SPOT",
            "symbol": "BTCUSDT",
            "direction": "WATCH_ONLY",
            "status": "WATCH_ONLY",
        }
    )
    assert no_setup.outcome.value == "NO_SETUP"
    assert no_setup.failed_stage.value == "SIGNAL_QUALIFICATION"
    assert "SETUP_NOT_CONFIRMED" in no_setup.reason_codes

    data_blocked = diagnose_opportunity_generation(
        {
            "market": "SPOT",
            "symbol": "BTCUSDT",
            "direction": "WATCH_ONLY",
            "status": "DATA_BLOCKED",
            "blockers": ["DATA_NOT_CURRENT:15m"],
        }
    )
    assert data_blocked.outcome.value == "DATA_BLOCKED"
    assert data_blocked.failed_stage.value == "DATA_QUALITY"
    assert data_blocked.reason_codes[0] == "DATA_NOT_CURRENT:15m"

    sizing = diagnose_opportunity_generation(
        {
            "market": "USD_M_FUTURES",
            "symbol": "BTCUSDT",
            "direction": "BULLISH",
            "side": "LONG",
            "entry": "100",
            "stop_loss": "98",
            "tp1": "104",
            "tp2": "106",
            "tp3": "108",
            "target_risk_reward": "2",
        }
    )
    assert sizing.outcome.value == "INCOMPLETE_PLAN"
    assert sizing.failed_stage.value == "POSITION_SIZING"
    assert sizing.missing_fields == ("quantity", "leverage")


@pytest.mark.parametrize("market", ["SPOT", "USD_M_FUTURES"])
def test_screening_uses_only_baseline_candles_without_relaxing_full_radar(
    tmp_path: Path, market: str
) -> None:
    from ai4binance.compatibility.opportunity_monitor import screen_market_opportunities

    archive = ParquetOHLCVArchive(tmp_path / market)
    for tf in ("15m", "1h"):
        duration = TIMEFRAME_DURATIONS[tf]
        rows = tuple(
            OHLCVCandle(
                timestamp=NOW + duration * i,
                open=Decimal(100),
                high=Decimal(105),
                low=Decimal(95),
                close=Decimal(102 if i == -1 else 99),
                volume=Decimal(100),
            )
            for i in range(-30, 0)
        )
        archive.update("BTCUSDT", tf, rows, source="LOCAL_TEST", generated_at=NOW)
    screened = screen_market_opportunities(
        archive,
        market=market,
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
    )
    assert screened["status"] == "CURRENT"
    assert screened["enrichment_required"] is True
    assert screened["candidate_count"] == 2
    assert screened["execution_allowed"] is False
    assert screened["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    if market == "SPOT":
        full = refresh_monitor(
            tmp_path,
            archive,
            market=market,
            symbol="BTCUSDT",
            now=NOW,
            minimum_candles=21,
            candle_limit=30,
        )
        candidates = cast(list[dict[str, object]], full["candidates"])
        assert all(row["direction"] == "WATCH_ONLY" for row in candidates)
        assert all(
            row["blockers"] and row["execution_allowed"] is False for row in candidates
        )
        assert full["discarded_unmeasurable_candidate_count"] == 5


def test_dashboard_rejects_stale_universe_metadata(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "universe-v3.json"
    cache.write_text(
        """{
  "observed_at": "2026-09-12T23:50:00+00:00",
  "spot_symbols": ["BTCUSDT"],
  "futures_symbols": ["BTCUSDT"],
  "coin_m_contracts": [],
  "excluded_assets": [],
  "execution_allowed": false,
  "live_eligibility_status": "LIVE_ORDER_BLOCKED"
}
""",
        encoding="utf-8",
    )

    assert read_cached_market_universe(cache, NOW) is None
    assert market_symbols(tmp_path, "SPOT", NOW) == ()


def seed(archive: ParquetOHLCVArchive, market: str, *, future: bool = False) -> None:
    for tf in MARKET_TIMEFRAMES[market]:
        duration = TIMEFRAME_DURATIONS[tf]
        rows = tuple(
            OHLCVCandle(
                timestamp=NOW + duration * index,
                open=Decimal(100),
                high=Decimal(105),
                low=Decimal(98),
                close=Decimal(101),
                volume=Decimal(100),
            )
            for index in range(-30, 4 if future else 0)
        )
        archive.update("BTCUSDT", tf, rows, source="LOCAL_TEST", generated_at=NOW)


def futures(snapshot: MarketSnapshot, timeframe: str) -> dict[str, object]:
    assert snapshot.market_type == "USD_M_FUTURES"
    assert timeframe in MARKET_TIMEFRAMES["USD_M_FUTURES"]
    return {
        "direction": "BULLISH",
        "setup_name": "NEW_LONG_PARTICIPATION",
        "status": "FUTURES_RESEARCH_RADAR",
        "entry": "101",
        "stop_loss": "98",
        "tp1": "105",
        "tp2": "108",
        "tp3": "111",
        "target_risk_reward": "2",
        "blockers": ["FUTURES_OOS_NOT_APPROVED"],
    }


def test_each_timeframe_has_separate_checksum_verified_quality(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "SPOT")
    snapshot, quality = inspect_market_data(
        archive,
        market="SPOT",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
    )
    assert tuple(row["timeframe"] for row in quality) == MARKET_TIMEFRAMES["SPOT"]
    assert all(row["status"] == "CURRENT" for row in quality)
    assert all(row["checksum_verified"] is True for row in quality)
    candidates = [
        build_opportunity_radar_snapshot(
            (snapshot,),
            cycle_id="test",
            timeframe=tf,
        ).candidates[0]
        for tf in MARKET_TIMEFRAMES["SPOT"]
    ]
    assert len({c.opportunity_id for c in candidates}) == 5
    assert tuple(c.timeframe for c in candidates) == MARKET_TIMEFRAMES["SPOT"]
    assert all(not c.execution_allowed for c in candidates)


def test_refresh_monitor_supports_virtual_market_four_timeframe_scope(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "SPOT")

    result = refresh_monitor(
        tmp_path,
        archive,
        market="SPOT",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
        timeframes=("5m", "15m", "1h", "4h"),
    )

    quality = cast(list[dict[str, object]], result["quality"])
    candidates = cast(list[dict[str, object]], result["candidates"])
    assert result["timeframes"] == ["5m", "15m", "1h", "4h"]
    assert [row["timeframe"] for row in quality] == [
        "5m",
        "15m",
        "1h",
        "4h",
    ]
    assert candidates == []
    assert result["discarded_unmeasurable_candidate_count"] == 4
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_missing_stale_and_corrupt_data_remain_blocked(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    _, missing = inspect_market_data(
        archive,
        market="SPOT",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
    )
    assert all(row["status"] == "UNAVAILABLE" for row in missing)
    assert all(row["candle_count"] is None for row in missing)
    seed(archive, "SPOT")
    (archive.root / "BTCUSDT/5m.parquet").write_bytes(b"corrupt")
    _, quality = inspect_market_data(
        archive,
        market="SPOT",
        symbol="BTCUSDT",
        now=NOW + timedelta(days=3),
        minimum_candles=21,
        candle_limit=30,
    )
    assert quality[0]["status"] == "INVALID"
    assert not quality[0]["checksum_verified"]
    assert all(row["status"] == "STALE" for row in quality[1:])


def test_refresh_preserves_first_observation_and_evaluates_only_future_bars(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "USD_M_FUTURES")
    first = refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
        futures_builder=futures,
    )
    assert first["history_count"] == 5
    directory = monitor_directory(tmp_path, "USD_M_FUTURES", "BTCUSDT")
    before = (directory / "observations.jsonl").read_bytes()
    refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW + timedelta(seconds=10),
        minimum_candles=21,
        candle_limit=30,
        futures_builder=futures,
    )
    assert (directory / "observations.jsonl").read_bytes() == before
    seed(archive, "USD_M_FUTURES", future=True)
    refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW + timedelta(hours=3),
        minimum_candles=21,
        candle_limit=30,
        futures_builder=futures,
    )
    result = read_monitor(tmp_path, "USD_M_FUTURES", "BTCUSDT")
    history = result["history"]
    assert isinstance(history, list)
    original = [r for r in history if r["observed_at"] == NOW.isoformat()]
    assert len(original) == 5
    assert all(
        r["outcome"]["status"] == "EVALUATED"
        for r in original
        if r["timeframe"] in {"5m", "15m", "1h"}
    )
    assert all(
        r["outcome"]["reference_price"] == "101"
        for r in original
        if r["timeframe"] in {"5m", "15m", "1h"}
    )
    assert all(
        r["outcome"]["status"] == "PENDING_HORIZON"
        for r in original
        if r["timeframe"] in {"4h", "1d"}
    )
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    outcomes_before = (directory / "outcomes.jsonl").read_bytes()
    refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW + timedelta(hours=3, seconds=1),
        minimum_candles=21,
        candle_limit=30,
        futures_builder=futures,
    )
    assert (directory / "outcomes.jsonl").read_bytes() == outcomes_before
    assert JsonlAuditStore(
        directory / "outcomes.jsonl", tamper_evident=True
    ).verify_chain()


def test_futures_provider_failure_does_not_hide_quality_or_other_timeframes(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "USD_M_FUTURES")

    def broken(snapshot: MarketSnapshot, timeframe: str) -> dict[str, object]:
        if timeframe == "5m":
            raise OSError("test provider failure")
        return futures(snapshot, timeframe)

    refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
        futures_builder=broken,
    )
    result = read_monitor(tmp_path, "USD_M_FUTURES", "BTCUSDT")
    candidates = result["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 4
    assert all(c["status"] == "FUTURES_RESEARCH_RADAR" for c in candidates)
    assert result["discarded_unmeasurable_candidate_count"] == 1


@pytest.mark.parametrize(
    ("market", "symbol"), [("SPOT", "../BTC"), ("LIVE", "BTCUSDT")]
)
def test_market_and_symbol_paths_are_allowlisted(
    tmp_path: Path, market: str, symbol: str
) -> None:
    with pytest.raises(ValueError, match="market or symbol is invalid"):
        monitor_directory(tmp_path, market, symbol)


@pytest.mark.parametrize("market", ["SPOT", "USD_M_FUTURES"])
def test_refresh_reuses_archive_without_public_window_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, market: str
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        dataset_directory=tmp_path / "canonical",
        minimum_closed_candles=21,
        candle_limit=30,
    )
    canonical = ParquetOHLCVArchive(
        settings.dataset_directory / ("spot" if market == "SPOT" else "usd_m_futures")
    )
    seed(canonical, market)
    calls: list[tuple[str, str]] = []

    def klines(
        self: BinancePublicClient,
        symbol: str,
        interval: str,
        limit: int,
        *,
        market_type: str = "SPOT",
    ) -> tuple[MarketKline, ...]:
        calls.append((market_type, interval))
        duration = TIMEFRAME_DURATIONS[interval]
        return tuple(
            MarketKline(
                open_time=NOW + duration * i,
                close_time=NOW + duration * (i + 1) - timedelta(milliseconds=1),
                open=Decimal(100),
                high=Decimal(105),
                low=Decimal(98),
                close=Decimal(101),
                volume=Decimal(100),
            )
            for i in range(-30, 1)
        )

    monkeypatch.setattr(BinancePublicClient, "klines", klines)
    client = BinancePublicClient(Mock())
    samples = refresh_candle_windows(
        settings, market, "BTCUSDT", tmp_path / "monitor", NOW, client
    )
    assert calls == []
    assert all(
        samples.manifest("BTCUSDT", tf).row_count == 30
        for tf in MARKET_TIMEFRAMES[market]
    )
    # A checksum failure never grants an independent public read path.
    (canonical.root / "BTCUSDT/5m.parquet").write_bytes(b"corrupt")
    samples = refresh_candle_windows(
        settings, market, "BTCUSDT", tmp_path / "monitor", NOW, client
    )
    assert calls == []
    manifest = samples.manifest("BTCUSDT", "5m")
    assert manifest.row_count == 30  # The still-open bar was excluded.
    assert manifest.source.startswith("CANONICAL_ARCHIVE_SHA256:")


@pytest.mark.parametrize("market", ["SPOT", "USD_M_FUTURES"])
def test_canonical_only_refresh_never_falls_back_to_public_klines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, market: str
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        dataset_directory=tmp_path / "canonical",
        minimum_closed_candles=21,
        candle_limit=30,
    )
    calls: list[str] = []

    def klines(*_args: object, **_kwargs: object) -> tuple[MarketKline, ...]:
        calls.append("called")
        return ()

    client = Mock(spec=BinancePublicClient)
    client.klines.side_effect = klines
    samples = refresh_candle_windows(
        settings,
        market,
        "BTCUSDT",
        tmp_path / "monitor",
        NOW,
        client,
        allow_network=False,
    )
    assert calls == []
    for timeframe in MARKET_TIMEFRAMES[market]:
        with pytest.raises(FileNotFoundError):
            samples.manifest("BTCUSDT", timeframe)


def test_outcome_rejects_gaps_and_waits_for_closed_future_bars(tmp_path: Path) -> None:
    from ai4binance.application.opportunity_monitor import _outcome

    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "USD_M_FUTURES", future=True)
    row: dict[str, object] = {
        "opportunity_id": "test",
        "market": "USD_M_FUTURES",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "observed_at": NOW.isoformat(),
        "direction": "BULLISH",
        "side": "LONG",
        "quantity": "1",
        "leverage": 1,
        "entry": "101",
        "stop_loss": "98",
        "tp1": "105",
        "tp2": "108",
        "tp3": "111",
        "target_risk_reward": "2",
    }
    assert (
        _outcome(row, archive, NOW + timedelta(minutes=14))["status"]
        == "PENDING_HORIZON"
    )
    assert _outcome(row, archive, NOW + timedelta(minutes=15))["status"] == "EVALUATED"
    row["observed_at"] = (NOW - timedelta(days=1)).isoformat()
    result = _outcome(row, archive, NOW + timedelta(minutes=15))
    assert result["status"] == "NOT_EVALUABLE"
    assert result["outcome_reason_codes"] == ["OUTCOME_DATA_GAP"]


def test_universe_summary_uses_all_eligible_symbols_as_each_timeframe_denominator(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "SPOT")
    refresh_monitor(
        tmp_path,
        archive,
        market="SPOT",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
    )

    summary = universe_monitor_summary(
        tmp_path,
        archive,
        market="SPOT",
        symbols=("BTCUSDT", "ETHUSDT"),
        now=NOW,
        minimum_candles=21,
    )

    assert summary["execution_allowed"] is False
    assert summary["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    quality = summary["quality"]
    assert isinstance(quality, list)
    assert all(row["current_count"] == 1 for row in quality)
    assert all(row["unavailable_count"] == 1 for row in quality)
    assert all(row["refresh_required_count"] == 1 for row in quality)
    coverage = summary["opportunity_coverage"]
    assert coverage == {
        "monitored_symbol_count": 1,
        "universe_count": 2,
        "unmonitored_symbol_count": 1,
        "published_opportunity_count": 0,
        "suppressed_opportunity_count": 0,
    }
    opportunities = summary["opportunities"]
    assert isinstance(opportunities, list)
    assert opportunities == []


def test_untrackable_potential_requires_a_complete_measurable_plan(
    tmp_path: Path,
) -> None:
    from ai4binance.application.opportunity_monitor import _outcome

    archive = ParquetOHLCVArchive(tmp_path / "archive")
    result = _outcome(
        {
            "opportunity_id": "potential",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "observed_at": NOW.isoformat(),
            "direction": "WATCH_ONLY",
            "reference_price": "101",
        },
        archive,
        NOW,
    )

    assert result == {
        "status": "NOT_TRACKABLE",
        "outcome_reason_codes": ["COMPLETE_MEASURABLE_TRADE_PLAN_REQUIRED"],
    }


def test_incomplete_candidates_are_not_persisted(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    seed(archive, "USD_M_FUTURES")

    result = refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
        futures_builder=lambda _snapshot, _timeframe: {
            "direction": "BULLISH",
            "status": "FUTURES_RESEARCH_RADAR",
            "entry": "101",
            "stop_loss": "98",
            "tp1": "105",
            "target_risk_reward": "2",
        },
    )

    directory = monitor_directory(tmp_path, "USD_M_FUTURES", "BTCUSDT")
    assert result["candidates"] == []
    assert result["history"] == []
    assert result["discarded_unmeasurable_candidate_count"] == 5
    health = cast(dict[str, object], result["generation_health"])
    assert health["evaluated_attempt_count"] == 5
    assert health["published_opportunity_count"] == 0
    assert health["rejected_attempt_count"] == 5
    assert health["rejected_by_stage"] == {"TRADE_PLAN": 5}
    reasons = cast(dict[str, int], health["rejected_by_reason"])
    assert reasons["TP2_UNAVAILABLE"] == 5
    assert reasons["TP3_UNAVAILABLE"] == 5
    assert len(cast(list[dict[str, object]], health["recent_rejections"])) == 5
    assert not (directory / "observations.jsonl").exists()
    lifecycle = directory / "lifecycle.jsonl"
    assert lifecycle.exists()
    events = [
        json.loads(line)["payload"] for line in lifecycle.read_text().splitlines()
    ]
    assert len(events) == 5
    assert all(event["event_type"] == "OPPORTUNITY_REJECTED" for event in events)
    assert all(event["lifecycle_state"] == "REJECTED" for event in events)
    assert all(event["evaluation_stage"] == "TRADE_PLAN" for event in events)
    assert all(event["execution_allowed"] is False for event in events)

    refresh_monitor(
        tmp_path,
        archive,
        market="USD_M_FUTURES",
        symbol="BTCUSDT",
        now=NOW,
        minimum_candles=21,
        candle_limit=30,
        futures_builder=lambda _snapshot, _timeframe: {
            "direction": "BULLISH",
            "status": "FUTURES_RESEARCH_RADAR",
            "entry": "101",
            "stop_loss": "98",
            "tp1": "105",
            "target_risk_reward": "2",
        },
    )
    assert len(lifecycle.read_text().splitlines()) == 5


def test_refresh_candle_windows_skips_failed_public_timeframes(tmp_path: Path) -> None:
    settings = Settings(
        dataset_directory=tmp_path / "canonical",
        minimum_closed_candles=21,
        candle_limit=30,
    )
    client = Mock(spec=BinancePublicClient)
    client.klines.side_effect = OSError("public source unavailable")

    samples = refresh_candle_windows(
        settings,
        "SPOT",
        "BTCUSDT",
        tmp_path / "monitor",
        NOW,
        client,
    )

    assert client.klines.call_count == 0
    for timeframe in MARKET_TIMEFRAMES["SPOT"]:
        with pytest.raises(FileNotFoundError):
            samples.manifest("BTCUSDT", timeframe)


@pytest.mark.parametrize("market", ["SPOT", "USD_M_FUTURES"])
def test_opportunity_monitor_cli_uses_canonical_local_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    market: str,
) -> None:
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from ai4binance.cli import opportunity_monitor as cli

    settings = SimpleNamespace(
        market_history_source_cache_directory=tmp_path / "cache",
        dataset_directory=tmp_path / "market",
        minimum_closed_candles=21,
        candle_limit=30,
    )
    observed: dict[str, object] = {}

    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(cli, "market_symbols", lambda *_args: ("BTCUSDT",))
    monkeypatch.setattr(cli, "monitor_directory", lambda *_args: tmp_path / "monitor")
    monkeypatch.setattr(cli, "SingleInstanceLease", lambda *_args: nullcontext())
    monkeypatch.setattr(
        cli, "refresh_candle_windows", lambda *_args, **_kwargs: "archive"
    )

    def refresh(*_args: object, **kwargs: object) -> None:
        builder = cast(
            Callable[[object, str], dict[str, object]], kwargs["futures_builder"]
        )
        observed["builder_result"] = builder(Mock(), "5m")

    monkeypatch.setattr(cli, "refresh_monitor", refresh)
    argv = ["opportunity-monitor", "--market", market, "--symbol", "BTCUSDT"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.chdir(tmp_path)

    assert cli.main() == 0
    result = observed["builder_result"]
    assert isinstance(result, dict)
    assert result["status"] == "DATA_BLOCKED"


def test_opportunity_monitor_cli_rejects_symbol_outside_current_universe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from types import SimpleNamespace

    from ai4binance.cli import opportunity_monitor as cli

    monkeypatch.setattr(
        cli,
        "Settings",
        lambda: SimpleNamespace(
            market_history_source_cache_directory=tmp_path / "cache"
        ),
    )
    monkeypatch.setattr(cli, "market_symbols", lambda *_args: ())
    monkeypatch.setattr(
        sys,
        "argv",
        ["opportunity-monitor", "--market", "SPOT", "--symbol", "BTCUSDT"],
    )

    with pytest.raises(ValueError, match="current eligible market universe"):
        cli.main()


def test_opportunity_monitor_entrypoint_starts_and_cancels_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import threading

    from ai4binance.cli import opportunity_monitor as cli

    source = Path(cli.__file__).read_text(encoding="utf-8")
    guard_start = source.index('if __name__ == "__main__":')
    guard = source[guard_start:]
    events: list[str] = []

    class Timer:
        daemon = False

        def __init__(self, _seconds: int, _callback: object) -> None:
            events.append("created")

        def start(self) -> None:
            events.append("started")

        def cancel(self) -> None:
            events.append("cancelled")

    namespace = {
        "__name__": "__main__",
        "threading": threading,
        "os": os,
        "main": lambda: 9,
    }
    monkeypatch.setattr(threading, "Timer", Timer)
    with pytest.raises(SystemExit) as raised:
        exec(compile(guard, cli.__file__, "exec"), namespace)  # noqa: S102

    assert raised.value.code == 9
    assert events == ["created", "started", "cancelled"]

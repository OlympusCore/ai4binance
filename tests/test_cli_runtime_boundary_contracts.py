"""Runtime command routing, traceability, and degraded I/O contracts."""

import io
import json
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai4binance.cli import runtime as r
from ai4binance.config import Settings
from ai4binance.whale_fusion.features import DerivativesFeatureEngine
from ai4binance.whale_fusion.models import PriceOiRegime

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings().model_copy(
        update={
            "runtime_state_path": tmp_path / "state/runtime.json",
            "runtime_context_ledger_path": tmp_path / "state/context.json",
            "runtime_opportunity_report_path": tmp_path / "opportunities.json",
            "runtime_news_feed_path": tmp_path / "news.jsonl",
            "runtime_social_feed_path": tmp_path / "social.jsonl",
            "runtime_content_feed_path": tmp_path / "content.jsonl",
            "runtime_technology_feed_path": tmp_path / "technology.jsonl",
            "market_history_source_cache_directory": tmp_path / "cache",
        }
    )


@pytest.mark.parametrize(
    ("refresh_fails", "supervisor_fails"),
    [(False, False), (True, False), (False, True)],
)
def test_resident_runtime_refreshes_once_and_releases_lease(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    refresh_fails: bool,
    supervisor_fails: bool,
) -> None:
    runtime = SimpleNamespace(run=Mock(return_value="report"))
    monkeypatch.setattr(r, "build_read_only_runtime", lambda _: runtime)
    refresh = Mock(return_value={"status": "READY"})
    if refresh_fails:
        refresh.side_effect = OSError("offline")
    monkeypatch.setattr(r, "_refresh_runtime_research_feeds", refresh)
    writer = Mock()
    monkeypatch.setattr(r, "write_json_object_verified", writer)
    monkeypatch.setattr(r, "SingleInstanceLease", lambda _: nullcontext())
    for name in (
        "RuntimeStatusStore",
        "PrivateRuntimeStatusStore",
        "RuntimeManagementLedger",
    ):
        monkeypatch.setattr(r, name, Mock())

    def supervisor(**kwargs: object) -> SimpleNamespace:
        def run(*, max_cycles: int | None) -> None:
            assert max_cycles == 2
            if supervisor_fails:
                raise RuntimeError("stopped")
            assert cast(Callable[[], object], kwargs["cycle"])() == "report"
            assert cast(Callable[[], object], kwargs["cycle"])() == "report"

        return SimpleNamespace(run=run)

    monkeypatch.setattr(r, "RuntimeSupervisor", supervisor)
    assert r.run_runtime_command("runtime-daemon", settings, max_cycles=2) == (
        2 if supervisor_fails else 0
    )
    if not supervisor_fails:
        refresh.assert_called_once_with(settings)
        assert runtime.run.call_count == 2
        assert writer.call_count == (0 if refresh_fails else 1)


def test_runtime_once_command_preserves_payload_and_exit_code(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        r,
        "_run_runtime_once",
        lambda _: ({"state": "DEGRADED", "execution_allowed": False}, 2),
    )
    assert r.run_runtime_command("runtime-once", settings, max_cycles=1) == 2
    assert json.loads(capsys.readouterr().out)["execution_allowed"] is False
    called = Mock(return_value=2)
    monkeypatch.setattr(r, "run_virtual_market_daemon", called)
    assert r.run_runtime_command("virtual-market-daemon", settings, max_cycles=1) == 2
    called.assert_called_once_with(settings, max_cycles=1, public_acquisition=None)


def test_traceability_reports_each_missing_or_mismatched_evidence(
    settings: Settings,
) -> None:
    settings.runtime_news_feed_path.write_text(
        json.dumps({"event_id": "known", "source_url": "https://example.org/canonical"})
        + "\n",
        encoding="utf-8",
    )
    settings.runtime_opportunity_report_path.write_text(
        json.dumps(
            {
                "opportunities": [
                    {},
                    {
                        "opportunity_id": "invalid",
                        "primary_source_url": "https://example.org/main",
                        "trace_urls": ["https://example.org/other"],
                        "trace_evidence": [
                            {},
                            {
                                "feed": "unknown",
                                "evidence_id": "x",
                                "source_url": "https://example.org/x",
                            },
                            {
                                "feed": "news",
                                "evidence_id": "missing",
                                "source_url": "https://example.org/x",
                            },
                            {
                                "feed": "news",
                                "evidence_id": "known",
                                "source_url": "https://example.org/wrong",
                            },
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    report, code = r._validate_runtime_research_traceability(settings)
    assert code == 2
    assert report["mismatch_count"] == 2
    assert report["validated_count"] == 0
    assert set(cast(list[dict[str, Any]], report["mismatches"])[0]["errors"]) == {
        "PRIMARY_SOURCE_URL_MISSING_OR_INVALID",
        "TRACE_URLS_MISSING",
        "TRACE_EVIDENCE_MISSING",
    }
    assert set(cast(list[dict[str, Any]], report["mismatches"])[1]["errors"]) == {
        "PRIMARY_SOURCE_NOT_IN_TRACE_URLS",
        "TRACE_EVIDENCE_SHAPE_INVALID",
        "TRACE_EVIDENCE_FEED_UNKNOWN:unknown",
        "TRACE_EVIDENCE_ID_NOT_FOUND:news:missing",
        "TRACE_EVIDENCE_URL_MISMATCH:news:known",
        "TRACE_EVIDENCE_URL_NOT_LISTED:news:known",
    }
    assert report["execution_allowed"] is False


def test_trace_report_write_failure_is_visible(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.runtime_opportunity_report_path.write_text(
        '{"opportunities": []}', encoding="utf-8"
    )
    monkeypatch.setattr(
        r, "write_json_object_verified", Mock(side_effect=OSError("disk full"))
    )
    report, code = r._validate_runtime_research_traceability(settings)
    assert code == 2
    assert report["blockers"] == ("RUNTIME_RESEARCH_TRACE_REPORT_WRITE_FAILED",)


def test_jsonl_source_index_skips_invalid_identity_and_urls(tmp_path: Path) -> None:
    path = tmp_path / "feed.jsonl"
    assert r._jsonl_source_index(path, ("event_id",)) == {}
    path.write_text("{bad", encoding="utf-8")
    assert r._jsonl_source_index(path, ("event_id",)) == {}
    rows = [
        {},
        {"source_url": "http://example.org"},
        {"source_url": "https://example.org"},
        {"source_url": "https://example.org", "event_id": "valid"},
    ]
    path.write_text("\n" + "\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    assert r._jsonl_source_index(path, ("missing", "event_id")) == {
        "valid": "https://example.org"
    }
    path.write_text("[]", encoding="utf-8")
    assert r._load_json_mapping(path) is None


@pytest.mark.parametrize(
    "value", [{}, [], {"futures_symbols": "bad"}, {"futures_symbols": ["X"] * 5001}]
)
def test_news_universe_rejects_invalid_payload(
    settings: Settings, value: object
) -> None:
    root = settings.market_history_source_cache_directory
    root.mkdir()
    (root / "universe-v3.json").write_text(json.dumps(value), encoding="utf-8")
    assert r._eligible_news_symbols(settings) == ()


def test_news_universe_corruption_and_symbol_normalization(settings: Settings) -> None:
    root = settings.market_history_source_cache_directory
    root.mkdir()
    path = root / "universe-v3.json"
    path.write_text("broken", encoding="utf-8")
    assert r._eligible_news_symbols(settings) == ()
    path.write_text(
        json.dumps(
            {"futures_symbols": [" btcusdt ", "BTCUSDT", None, "../bad", "ETHUSDT"]}
        ),
        encoding="utf-8",
    )
    assert r._eligible_news_symbols(settings) == ("BTCUSDT", "ETHUSDT")
    assert r._related_news_symbols("Bitcoin", ("USDT", "BTCUSDT")) == ("BTCUSDT",)


def test_feed_fetch_disallows_unapproved_and_oversized_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        r._fetch_feed_items("https://unknown.invalid", max_items=1, max_file_bytes=10)
    url = next(iter(r._ALLOWED_REFRESH_FEED_URLS))
    monkeypatch.setattr(r, "urlopen", lambda *a, **k: io.BytesIO(b"x" * 11))
    with pytest.raises(ValueError, match="max file size"):
        r._fetch_feed_items(url, max_items=1, max_file_bytes=10)
    monkeypatch.setattr(r, "_ALLOWED_REFRESH_FEED_URLS", ("http://example.org",))
    with pytest.raises(ValueError, match="HTTPS"):
        r._fetch_feed_items("http://example.org", max_items=1, max_file_bytes=10)


def test_report_write_failures_remain_explicit(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        r, "write_user_report_files", Mock(side_effect=OSError("disk full"))
    )
    paths, blockers = r._write_runtime_research_user_reports(
        settings,
        fetched_at=NOW,
        news_rows=[],
        social_rows=[],
        content_rows=[],
        technology_rows=[],
    )
    assert paths == {}
    assert blockers == (
        "NEWS_USER_REPORT_WRITE_FAILED",
        "TECHNOLOGY_USER_REPORT_WRITE_FAILED",
    )
    portfolio_paths, blockers = r._write_virtual_portfolio_user_report(settings, {})
    assert paths == {}
    assert portfolio_paths == {}
    assert blockers == ("VIRTUAL_PORTFOLIO_USER_REPORT_WRITE_FAILED",)


@pytest.mark.parametrize(
    ("feed_blocked", "trace_blocked"), [(True, False), (False, True)]
)
def test_research_refresh_fails_closed(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    feed_blocked: bool,
    trace_blocked: bool,
) -> None:
    monkeypatch.setattr(
        r,
        "_refresh_runtime_research_feeds",
        lambda _: {"blockers": ["FEED_UNAVAILABLE"] if feed_blocked else []},
    )
    run = Mock(return_value=({}, 0))
    monkeypatch.setattr(r, "_run_runtime_once", run)
    monkeypatch.setattr(
        r,
        "_validate_runtime_research_traceability",
        lambda _: ({}, 2 if trace_blocked else 0),
    )
    payload, code = r.run_runtime_research_refresh_once(settings)
    assert code == 2
    assert payload["execution_allowed"] is False
    assert payload["blockers"] == (
        ("FEED_UNAVAILABLE",)
        if feed_blocked
        else ("RUNTIME_RESEARCH_TRACE_VALIDATION_FAILED",)
    )
    if feed_blocked:
        run.assert_not_called()


def test_local_only_acquisition_builds_one_canonical_source(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    local, second = Mock(), Mock()
    builder = Mock(side_effect=[local, second])
    monkeypatch.setattr(r, "build_public_acquisition", builder)
    result = r._build_virtual_market_acquisition(
        settings.model_copy(update={"market_history_local_candles": True})
    )
    assert isinstance(result, r._LocalFirstPublicAcquisition)
    assert result.primary is local
    second_result = r._build_virtual_market_acquisition(
        settings.model_copy(update={"market_history_local_candles": False})
    )
    assert isinstance(second_result, r._LocalFirstPublicAcquisition)
    assert second_result.primary is second
    assert builder.call_count == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"extra": 1}, "INVALID"),
        ({"requested_at": "2026-01-01"}, "TIMESTAMP_INVALID"),
        ({"execution_allowed": True}, "INVALID"),
    ],
)
def test_virtual_refresh_request_rejects_invalid_payload(
    tmp_path: Path, overrides: dict[str, Any], message: str
) -> None:
    path = tmp_path / "refresh.json"
    payload = {
        "schema_version": "VirtualMarketRefreshRequest/v1",
        "request_id": "request:test",
        "requested_at": NOW.isoformat(),
        "market": "SPOT",
        "symbol": "BTCUSDT",
        "status": "PENDING",
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    path.write_text(json.dumps(payload | overrides), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        r._pending_virtual_market_refresh_request(path, ("BTCUSDT",), NOW)


def test_runtime_helpers_preserve_safe_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    for value in (None, "", "2026-01-01"):
        path.write_text(json.dumps({"last_success_at": value}), encoding="utf-8")
        assert r._previous_virtual_market_success(path) is None
    path.write_text(" " * 16385, encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID"):
        r._pending_virtual_market_refresh_request(path, (), NOW)
    assert (
        r._pending_virtual_market_refresh_request(tmp_path / "missing", (), NOW) is None
    )
    assert r._stamp_from_iso("2026-01-01") == "20260101T000000Z"
    assert len(r._stamp_from_iso("bad")) == 16
    assert (
        r._virtual_wallet_report_root(tmp_path / "state.json") == Path.cwd().resolve()
    )
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(r, "canonical_system_root", lambda _: tmp_path)
    assert r._user_report_root(path) == tmp_path
    assert r._content_source_label("https://example.org") == "coindesk-content"
    assert r._title_vote("ordinary research") == 0
    assert r._impact_from_title("hack") == "CRITICAL"
    assert r._slug("https://example.org").startswith("item-")
    assert r._text_sequence(3) == ()
    assert r._mapping_sequence(3) == ()
    assert r._mapping_sequence(({}, "bad")) == ({},)
    with pytest.raises(ValueError, match="timeframe"):
        r.RuntimeFuturesAdvisor(Mock(), timeframe="unknown")
    with pytest.raises(ValueError, match="at least two samples"):
        r.virtual_market_soak_payload(0)
    with pytest.raises(ValueError, match="max_cycles"):
        r.run_virtual_market_daemon(Settings(), max_cycles=0)


@pytest.mark.parametrize("approved", [True, False])
def test_futures_advisor_retains_no_trade_with_and_without_oos(approved: bool) -> None:
    dataset = SimpleNamespace(values=lambda _: (1, 2))
    engine = SimpleNamespace(
        short_lookback=2,
        medium_lookback=3,
        compute=Mock(
            return_value=SimpleNamespace(
                symbol="BTCUSDT",
                as_of=NOW,
                price_oi_regime=PriceOiRegime.NEW_LONG_PARTICIPATION,
                blockers=(),
            )
        ),
    )
    resolver = SimpleNamespace(is_validated=Mock(return_value=approved))
    advisor = r.RuntimeFuturesAdvisor(
        Mock(collect=Mock(return_value=dataset)),
        feature_engine=cast(DerivativesFeatureEngine, engine),
        oos_evidence=resolver,
    )
    report = advisor.build(
        SimpleNamespace(
            symbol="BTCUSDT",
            ohlcv_by_timeframe={
                "1h": (SimpleNamespace(close=100), SimpleNamespace(close=101))
            },
        )
    )
    assert report.action == "NO_TRADE"
    assert report.bias == "BULLISH"
    assert ("FUTURES_OOS_NOT_APPROVED" in report.blockers) is (not approved)
    item = r.RuntimeInvestmentManager._item(report.opportunity_radar[0])
    assert item.promotion_status == "RESEARCH_ONLY"
    assert item.score == 50
    resolver.is_validated.assert_called_once()


def test_empty_feed_preserves_source_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(r, "_fetch_feed_items", lambda *a, **k: ())
    assert r._fetch_feed_items_with_blocker(
        "https://example.org", max_items=1, max_file_bytes=100, blocker="FEED_EMPTY"
    ) == ((), "FEED_EMPTY")


def test_simulation_projection_skips_invalid_previous_rows() -> None:
    result = r._dashboard_simulation_projection(
        {"symbol_observations": [None, {"symbol": "INELIGIBLE"}]},
        symbols=("BTCUSDT",),
        observed_at=NOW,
        exit_code=2,
        cycle_report={},
    )
    assert result["status"] == "IN_PROGRESS"
    assert result["scanned_symbol_count"] == 0
    assert result["symbol_observations"] == []

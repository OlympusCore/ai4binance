"""Test-only validation refresh schedules; no exchange or wallet access."""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import TextIO, cast

import pytest

from ai4binance.agents.validation_gate import ValidationGate
from ai4binance.application.validation_pipeline import VALIDATED_PLAYBOOKS
from ai4binance.cli import research as research_cli
from ai4binance.cli import runtime as runtime_cli
from ai4binance.cli.bootstrap import SnapshotAcquirer
from ai4binance.config import Settings
from ai4binance.data import market_history_sync
from ai4binance.enterprise import resources
from ai4binance.integrations import research_market_universe
from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot
from ai4binance.validation.oos_maturity import OOSValidationSubject
from ai4binance.validation_pipeline_runtime import HistoricalValidationRuntime


@pytest.fixture
def local_validation_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep patched test-only producers local; separately verify real spawn below."""
    monkeypatch.setattr(
        runtime_cli,
        "_runtime_validation_executor",
        lambda: ThreadPoolExecutor(max_workers=1),
    )


def test_spawned_validation_worker_preserves_malformed_evidence_denial(
    tmp_path: Path,
) -> None:
    """Real child-process IPC preserves Settings and canonical fail-closed output."""
    deployment = tmp_path / "deployment.json"
    original = b"{}"
    deployment.write_bytes(original)
    settings = Settings(
        validation_artifact_directory=tmp_path / "validation",
        runtime_validation_deployment_path=deployment,
    )
    with runtime_cli._runtime_validation_executor() as executor:
        identities = {executor.submit(os.getpid).result(timeout=30) for _ in range(4)}
        assert len(identities) == 1
        assert os.getpid() not in identities
        result = executor.submit(
            runtime_cli._refresh_runtime_validation_isolated,
            settings,
            as_of=datetime(2026, 11, 6, tzinfo=UTC),
            symbols=("BTCUSDT",),
        ).result(timeout=30)
    assert result["status"] == "BLOCKED"
    assert result["blockers"]
    assert result["execution_allowed"] is False
    assert result["promotion_status"] == "RESEARCH_ONLY"
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert deployment.read_bytes() == original
    assert not settings.validation_artifact_directory.exists()


@pytest.mark.parametrize(
    "gap", ["none", "strategy", "timeframe", "market", "unsupported"]
)
def test_validation_inventory_requires_every_playbook_timeframe(gap: str) -> None:
    """Test-only identities cannot substitute for a missing strategy's evidence."""
    timeframes = ("15m", "1h", "4h")
    subjects = tuple(
        cast(
            OOSValidationSubject,
            SimpleNamespace(
                promotion=SimpleNamespace(
                    symbol="BTCUSDT",
                    timeframe=timeframe,
                    strategy_id=playbook,
                    market_type="USD_M_FUTURES"
                    if gap == "market" and playbook == VALIDATED_PLAYBOOKS[-1]
                    else "SPOT",
                ),
            ),
        )
        for playbook in VALIDATED_PLAYBOOKS
        for timeframe in timeframes
        if not (gap == "strategy" and playbook == VALIDATED_PLAYBOOKS[-1])
        and not (gap == "unsupported" and playbook == "resistance_rejection")
        and not (
            gap == "timeframe"
            and playbook == VALIDATED_PLAYBOOKS[-1]
            and timeframe == "4h"
        )
    )
    assert research_cli._pending_spot_validation_symbols(
        subjects, ("BTCUSDT",), timeframes
    ) == (() if gap in {"none", "unsupported"} else ("BTCUSDT",))


def test_unsupported_spot_inventory_sell_keeps_its_preflight_veto() -> None:
    assert HistoricalValidationRuntime.playbook_preflight_blockers(
        "resistance_rejection"
    ) == ("HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED",)
    assert HistoricalValidationRuntime._preflight("resistance_rejection", ()) == (
        "INSUFFICIENT_VALIDATION_CANDLES",
        "HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED",
    )


def test_refresh_stays_blocked_when_producer_omits_a_supported_playbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful test-only producer exit cannot cover another strategy."""
    subjects = tuple(
        cast(
            OOSValidationSubject,
            SimpleNamespace(
                promotion=SimpleNamespace(
                    symbol="BTCUSDT",
                    timeframe=timeframe,
                    strategy_id="trend_continuation",
                    market_type="SPOT",
                )
            ),
        )
        for timeframe in ("15m", "1h", "4h")
    )
    gate = ValidationGate(expected_subjects=subjects)
    monkeypatch.setattr(ValidationGate, "from_deployment", lambda **_kwargs: gate)
    monkeypatch.setattr(resources, "physical_ram_used_gb", lambda: 1.0)
    calls: list[str | None] = []

    def produce(
        _settings: Settings, symbol: str | None, *, output: TextIO | None = None
    ) -> int:
        calls.append(symbol)
        return 0

    monkeypatch.setattr(research_cli, "run_validate_research", produce)
    result = research_cli.refresh_runtime_validation(
        Settings(validation_artifact_directory=tmp_path / "validation"),
        as_of=datetime(2026, 11, 6, tzinfo=UTC),
        symbols=("BTCUSDT",),
    )
    assert calls == ["BTCUSDT"]
    assert result["producer_exit_code"] == 0
    assert result["status"] == "BLOCKED"
    assert result["pending_symbols"] == ["BTCUSDT"]
    assert result["blockers"] == ["VALIDATION_SYMBOL_EVIDENCE_INCOMPLETE:BTCUSDT"]
    assert result["execution_allowed"] is False
    assert result["promotion_status"] == "RESEARCH_ONLY"
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("status", "expected_seconds"),
    [
        ("BLOCKED", [0, 60]),
        ("DEFERRED", [0, 60]),
        ("CURRENT_SOURCE_BINDING", [0, 60]),
        ("REVALIDATED_RESEARCH_ONLY", [0, 60]),
        ("PARTIAL_RESEARCH_COVERAGE", [0, 5, 60]),
    ],
)
def test_virtual_validation_refresh_is_bounded_and_periodically_rechecked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_validation_executor: None,
    status: str,
    expected_seconds: list[int],
) -> None:
    origin = datetime(2026, 11, 6, tzinfo=UTC)
    now = origin
    refresh_times: list[int] = []
    refresh_symbols: list[str] = []
    sleeps = iter((5, 55))
    settings = Settings(
        runtime_state_path=tmp_path / "runtime.json",
        runtime_cycle_interval_seconds=60,
    )
    monkeypatch.setattr(runtime_cli, "physical_ram_used_gb", lambda: 0.0)
    monkeypatch.setattr(
        research_market_universe, "manual_selection_digest", lambda _path: "test-only"
    )
    monkeypatch.setattr(
        market_history_sync,
        "read_cached_market_universe",
        lambda *_args, **_kwargs: BinanceEligibleMarketSnapshot(
            spot_symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), futures_symbols=()
        ),
    )
    monkeypatch.setattr(
        runtime_cli, "_virtual_market_priority_symbols", lambda *_args: ()
    )
    monkeypatch.setattr(
        runtime_cli,
        "_virtual_wallet_journal",
        lambda _settings: SimpleNamespace(open_position_symbols=lambda **_kwargs: ()),
    )
    monkeypatch.setattr(
        runtime_cli,
        "_virtual_market_learning",
        lambda *_args: {"execution_allowed": False},
    )

    def refresh(
        _settings: Settings, *, as_of: datetime, symbols: tuple[str, ...]
    ) -> dict[str, object]:
        assert set(symbols) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        refresh_times.append(int((as_of - origin).total_seconds()))
        refresh_symbols.append(symbols[0])
        return {"status": status, "execution_allowed": False}

    def cycle(
        _settings: Settings,
        _source: SnapshotAcquirer,
        *,
        observed_at: datetime,
        cycle_report: dict[str, object] | None = None,
    ) -> int:
        assert observed_at == now
        assert cycle_report is not None
        cycle_report.update(
            virtual_order_ready=False,
            research_blockers=["OOS_APPROVAL_MISSING"],
        )
        return 0

    def sleep(_seconds: float) -> None:
        nonlocal now
        now += timedelta(seconds=next(sleeps))

    monkeypatch.setattr(research_cli, "refresh_runtime_validation", refresh)
    monkeypatch.setattr(runtime_cli, "_run_virtual_market_research_cycle", cycle)
    assert (
        runtime_cli.run_virtual_market_daemon(
            settings,
            max_cycles=3,
            public_acquisition=cast(SnapshotAcquirer, object()),
            sleeper=sleep,
            clock=lambda: now,
        )
        == 0
    )
    assert refresh_times == expected_seconds
    assert refresh_symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"][: len(expected_seconds)]
    state = json.loads((tmp_path / "virtual-market.json").read_text())
    assert state["virtual_order_ready"] is False
    assert state["execution_allowed"] is False
    assert state["promotion_status"] == "RESEARCH_ONLY"
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert state["research_blockers"] == ["OOS_APPROVAL_MISSING"]


def test_validation_coverage_loss_without_pending_symbol_fails_closed() -> None:
    result = research_cli._validation_scope_result((), ("BTCUSDT",))
    assert result == {
        "status": "BLOCKED",
        "blockers": ["VALIDATION_SYMBOL_EVIDENCE_INCOMPLETE:BTCUSDT"],
    }


def test_slow_validation_does_not_block_or_duplicate_and_cannot_cover_new_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test-only stalled work never becomes evidence or inherited caller context."""
    now = datetime(2026, 11, 6, tzinfo=UTC)
    release = Event()
    started = Event()
    marker = ContextVar("test_only_observer", default="isolated")
    marker.set("caller")
    scopes: list[tuple[str, ...]] = []

    def refresh(
        _settings: Settings, *, as_of: datetime, symbols: tuple[str, ...]
    ) -> dict[str, object]:
        assert marker.get() == "isolated"
        assert as_of == now
        scopes.append(symbols)
        started.set()
        assert release.wait(timeout=5)
        return {
            "status": "CURRENT_SOURCE_BINDING",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    monkeypatch.setattr(research_cli, "refresh_runtime_validation", refresh)
    settings = Settings(runtime_cycle_interval_seconds=60)
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = runtime_cli._RuntimeValidationRefresh(executor)
        try:
            for symbols in (("BTCUSDT",), ("BTCUSDT",), ("ETHUSDT",)):
                result = worker.observe(settings, symbols=symbols, clock=lambda: now)
                assert result["status"] == "IN_PROGRESS"
                assert result["execution_allowed"] is False
                assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
                assert release.is_set() is False
            assert started.is_set()
            assert scopes == [("BTCUSDT",)]
        finally:
            release.set()
        assert worker.pending is not None
        worker.pending.result(timeout=5)
        changed = worker.observe(settings, symbols=("ETHUSDT",), clock=lambda: now)
        assert changed["status"] == "BLOCKED"
        assert changed["blockers"] == ["VALIDATION_REFRESH_SCOPE_CHANGED"]
        assert changed["execution_allowed"] is False
        current = worker.observe(settings, symbols=("ETHUSDT",), clock=lambda: now)
        assert current["status"] == "CURRENT_SOURCE_BINDING"
        assert scopes == [("BTCUSDT",), ("ETHUSDT",)]


def test_validation_worker_failure_remains_blocked_and_bounds_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 11, 6, tzinfo=UTC)
    calls = 0

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise ValueError("TEST_ONLY_VALIDATION_FAILURE")

    monkeypatch.setattr(research_cli, "refresh_runtime_validation", fail)
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = runtime_cli._RuntimeValidationRefresh(executor)
        with pytest.raises(ValueError, match="TEST_ONLY_VALIDATION_FAILURE"):
            worker.observe(Settings(), symbols=("BTCUSDT",), clock=lambda: now)
        result = worker.observe(Settings(), symbols=("BTCUSDT",), clock=lambda: now)
        assert calls == 1
        assert result["status"] == "BLOCKED"
        assert result["blockers"] == ["VALIDATION_REFRESH_FAILED"]
        assert result["execution_allowed"] is False
        assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_virtual_observation_cycles_continue_while_validation_is_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local_validation_executor: None
) -> None:
    """Test-only blocked validation cannot stall observations or grant a trade."""
    now = datetime(2026, 11, 6, tzinfo=UTC)
    release = Event()
    started = Event()
    refresh_calls = 0
    observed_cycles = 0
    monkeypatch.setattr(runtime_cli, "physical_ram_used_gb", lambda: 0.0)
    monkeypatch.setattr(
        research_market_universe, "manual_selection_digest", lambda _path: "test-only"
    )
    monkeypatch.setattr(
        market_history_sync,
        "read_cached_market_universe",
        lambda *_args, **_kwargs: BinanceEligibleMarketSnapshot(
            spot_symbols=("BTCUSDT",), futures_symbols=()
        ),
    )
    monkeypatch.setattr(
        runtime_cli, "_virtual_market_priority_symbols", lambda *_args: ()
    )
    monkeypatch.setattr(
        runtime_cli,
        "_virtual_wallet_journal",
        lambda _settings: SimpleNamespace(open_position_symbols=lambda **_kwargs: ()),
    )
    monkeypatch.setattr(
        runtime_cli,
        "_virtual_market_learning",
        lambda *_args: {"execution_allowed": False},
    )

    def refresh(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal refresh_calls
        refresh_calls += 1
        started.set()
        assert release.wait(timeout=5)
        return {"status": "BLOCKED", "execution_allowed": False}

    def cycle(
        _settings: Settings,
        _source: SnapshotAcquirer,
        *,
        observed_at: datetime,
        cycle_report: dict[str, object] | None = None,
    ) -> int:
        nonlocal observed_cycles
        assert started.is_set()
        assert release.is_set() is False
        assert cycle_report is not None
        refresh_state = cycle_report["validation_refresh"]
        assert isinstance(refresh_state, dict)
        assert refresh_state["status"] == "IN_PROGRESS"
        assert refresh_state["execution_allowed"] is False
        cycle_report.update(
            virtual_order_ready=False, research_blockers=["OOS_APPROVAL_MISSING"]
        )
        observed_cycles += 1
        if observed_cycles == 3:
            release.set()
        return 0

    monkeypatch.setattr(research_cli, "refresh_runtime_validation", refresh)
    monkeypatch.setattr(runtime_cli, "_run_virtual_market_research_cycle", cycle)
    try:
        assert (
            runtime_cli.run_virtual_market_daemon(
                Settings(runtime_state_path=tmp_path / "runtime.json"),
                max_cycles=3,
                public_acquisition=cast(SnapshotAcquirer, object()),
                sleeper=lambda _seconds: None,
                clock=lambda: now,
            )
            == 0
        )
    finally:
        release.set()
    assert observed_cycles == 3
    assert refresh_calls == 1
    state = json.loads((tmp_path / "virtual-market.json").read_text())
    assert state["cycle_count"] == 3
    assert state["last_success_at"] == now.isoformat()
    assert state["research_blockers"] == ["OOS_APPROVAL_MISSING"]
    assert state["virtual_order_ready"] is False
    assert state["execution_allowed"] is False
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_refresh_log_output_does_not_redirect_other_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = ValidationGate(expected_subjects=())
    monkeypatch.setattr(ValidationGate, "from_deployment", lambda **_kwargs: gate)
    monkeypatch.setattr(resources, "physical_ram_used_gb", lambda: 1.0)
    original_stdout = sys.stdout

    def produce(
        _settings: Settings, _symbol: str | None, *, output: TextIO | None = None
    ) -> int:
        assert sys.stdout is original_stdout
        print("TEST_ONLY_VALIDATION_LOG", file=output)
        print("TEST_ONLY_OTHER_THREAD_OUTPUT")
        return 0

    monkeypatch.setattr(research_cli, "run_validate_research", produce)
    research_cli.refresh_runtime_validation(
        Settings(validation_artifact_directory=tmp_path),
        as_of=datetime(2026, 11, 6, tzinfo=UTC),
        symbols=("BTCUSDT",),
    )
    assert "TEST_ONLY_OTHER_THREAD_OUTPUT" in capsys.readouterr().out
    log = (tmp_path / "runtime-validation-refresh.log").read_text()
    assert "TEST_ONLY_VALIDATION_LOG" in log
    assert "TEST_ONLY_OTHER_THREAD_OUTPUT" not in log

"""Persistent historical replay wallet-epoch state tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.historical_replay_state import (
    VIRTUAL_WALLET_RESET_CONFIRMATION,
    HistoricalReplayResetCapital,
    HistoricalReplayStateStore,
)
from ai4binance.research import VirtualMarket
from ai4binance.storage import DestinationVerificationError
from tests.test_historical_replay_runner import (
    END,
    HASH_A,
    START,
    _dual_market_request,
    _NoCandidateOrchestrator,
    _OpenOnceOrchestrator,
    _request,
    _runner,
    _snapshot,
)


def test_replay_state_store_round_trips_and_is_idempotent(tmp_path: Path) -> None:
    request = _request()
    result = _runner().run(
        request,
        (_snapshot(START, snapshot_id="snapshot-persisted"),),
    )
    store = HistoricalReplayStateStore.for_run(tmp_path, request.run_id)

    assert store.persist(result, persisted_at=START + timedelta(minutes=1)) is True
    assert store.persist(result, persisted_at=START + timedelta(minutes=2)) is False

    restored = store.restore(request)

    assert restored is not None
    assert restored.final_portfolios == result.final_portfolios
    assert restored.open_positions == result.open_positions
    assert restored.closed_trades == result.closed_trades
    assert restored.equity_curves == result.equity_curves
    assert restored.result_semantic_sha256 == result.semantic_result_sha256
    assert restored.result_audit_sha256 == result.audit_result_sha256
    assert restored.execution_allowed is False
    assert restored.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert len(store.path.read_text(encoding="utf-8").splitlines()) == 1


def test_replay_state_store_restores_closed_futures_accounting(tmp_path: Path) -> None:
    dual = _dual_market_request()
    request = replace(
        dual,
        run_id="historical-state-futures",
        market_selections=(dual.market_selections[1],),
        dataset_bindings=(dual.dataset_bindings[1],),
        wallet_epochs=(dual.wallet_epochs[1],),
    )
    result = _runner(orchestrator=_OpenOnceOrchestrator()).run(
        request,
        (
            _snapshot(
                START,
                snapshot_id="snapshot-state-futures-open",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
            _snapshot(
                END,
                snapshot_id="snapshot-state-futures-close",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
                high="120",
                low="60",
                close="72",
                funding_payment_due=True,
            ),
        ),
    )
    store = HistoricalReplayStateStore.for_run(tmp_path, request.run_id)

    assert store.persist(result) is True
    restored = store.restore(request)

    assert restored is not None
    assert restored.open_positions == ()
    assert restored.closed_trades == result.closed_trades
    assert restored.final_portfolios == result.final_portfolios


def test_replay_restart_extends_checkpoint_without_duplicate_economics(
    tmp_path: Path,
) -> None:
    dual = _dual_market_request()
    request = replace(
        dual,
        run_id="historical-state-resume",
        market_selections=(dual.market_selections[1],),
        dataset_bindings=(dual.dataset_bindings[1],),
        wallet_epochs=(dual.wallet_epochs[1],),
    )
    opening = _snapshot(
        START,
        snapshot_id="snapshot-resume-open",
        market=VirtualMarket.USD_M_FUTURES,
        execution_context=True,
    )
    closing = _snapshot(
        END,
        snapshot_id="snapshot-resume-close",
        market=VirtualMarket.USD_M_FUTURES,
        execution_context=True,
        high="120",
        low="60",
        close="72",
        funding_payment_due=True,
    )
    partial = _runner(orchestrator=_OpenOnceOrchestrator()).run(
        request,
        (opening,),
    )
    completed = _runner(orchestrator=_OpenOnceOrchestrator()).run(
        request,
        (opening, closing),
    )
    store = HistoricalReplayStateStore.for_run(tmp_path, request.run_id)

    assert store.persist(partial) is True
    assert store.persist(completed) is True
    assert store.persist(completed) is False

    restored = store.restore(request)
    assert restored is not None
    assert restored.last_sequence == 1
    assert restored.open_positions == ()
    assert len(restored.closed_trades) == 1
    assert restored.closed_trades == completed.closed_trades
    assert restored.final_portfolios == completed.final_portfolios
    assert len(store.path.read_text(encoding="utf-8").splitlines()) == 2

    divergent = _runner(orchestrator=_OpenOnceOrchestrator()).run(
        request,
        (
            _snapshot(
                START,
                snapshot_id="snapshot-resume-divergent-open",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
                high="102",
                low="98",
                close="101",
            ),
            closing,
        ),
    )
    divergent_store = HistoricalReplayStateStore.for_run(
        tmp_path / "divergent",
        request.run_id,
    )
    assert divergent_store.persist(partial) is True
    with pytest.raises(ValueError, match="CHECKPOINT_DIVERGENCE"):
        divergent_store.persist(divergent)


def test_replay_state_store_rejects_tamper_and_request_drift(tmp_path: Path) -> None:
    request = _request()
    result = _runner().run(
        request,
        (_snapshot(START, snapshot_id="snapshot-state-bound"),),
    )
    store = HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    store.persist(result)

    with pytest.raises(ValueError, match="PERSISTED_REQUEST_MISMATCH"):
        store.restore(replace(request, random_seed=1))

    record = json.loads(store.path.read_text(encoding="utf-8"))
    record["payload"]["state"]["request_seed_sha256"] = HASH_A
    store.path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        DestinationVerificationError,
        match="JSONL_AUDIT_TAMPER_EVIDENT_CHAIN_INVALID",
    ):
        store.restore(request)


def test_replay_state_store_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run id is invalid"):
        HistoricalReplayStateStore.for_run(tmp_path, "../escape")


def test_replay_state_store_uses_canonical_runtime_artifact_root(
    tmp_path: Path,
) -> None:
    store = HistoricalReplayStateStore.for_run(tmp_path, "bounded-replay")

    assert (
        store.path
        == (
            tmp_path
            / "runtime"
            / "artifacts"
            / "research"
            / "historical_replay"
            / "wallet_epochs"
            / "bounded-replay.jsonl"
        ).resolve()
    )


def test_wallet_reset_finalizes_epochs_and_preserves_append_only_history(
    tmp_path: Path,
) -> None:
    request = _dual_market_request()
    result = _runner(orchestrator=_NoCandidateOrchestrator()).run(
        request,
        (
            _snapshot(
                START,
                snapshot_id="snapshot-reset-spot",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                START,
                snapshot_id="snapshot-reset-futures",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
        ),
    )
    store = HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    store.persist(result)
    capitals = (
        HistoricalReplayResetCapital(VirtualMarket.SPOT, Decimal("500")),
        HistoricalReplayResetCapital(
            VirtualMarket.USD_M_FUTURES,
            Decimal("250"),
        ),
    )

    reset = store.reset_wallet_epochs(
        result,
        reset_at=END + timedelta(minutes=1),
        capitals=capitals,
        confirmation=VIRTUAL_WALLET_RESET_CONFIRMATION,
    )
    repeated = store.reset_wallet_epochs(
        result,
        reset_at=END + timedelta(minutes=1),
        capitals=capitals,
        confirmation=VIRTUAL_WALLET_RESET_CONFIRMATION,
    )

    assert reset.status == "RESET_COMPLETED"
    assert reset.persisted is True
    assert repeated.status == "RESET_COMPLETED"
    assert repeated.persisted is False
    assert all(epoch.status.value == "FINALIZED" for epoch in reset.previous_epochs)
    assert all(epoch.status.value == "ACTIVE" for epoch in reset.new_epochs)
    assert {portfolio.initial_equity_usdt for portfolio in reset.new_portfolios} == {
        Decimal("500"),
        Decimal("250"),
    }
    assert store.path.exists()
    assert reset.history_path.exists()
    assert len(reset.history_path.read_text(encoding="utf-8").splitlines()) == 1
    payload = json.loads(reset.history_path.read_text(encoding="utf-8"))["payload"]
    assert "PERFORMANCE_HISTORY" in payload["preserved_evidence"]
    assert "LEARNING" in payload["preserved_evidence"]
    assert reset.execution_allowed is False
    assert reset.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="JSONL_AUDIT_IDEMPOTENCY_CONFLICT"):
        store.reset_wallet_epochs(
            result,
            reset_at=END + timedelta(minutes=2),
            capitals=capitals,
            confirmation=VIRTUAL_WALLET_RESET_CONFIRMATION,
        )


def test_wallet_reset_blocks_open_positions_and_requires_confirmation(
    tmp_path: Path,
) -> None:
    request = _dual_market_request()
    result = _runner().run(
        request,
        (
            _snapshot(
                START,
                snapshot_id="snapshot-reset-open-spot",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                START,
                snapshot_id="snapshot-reset-open-futures",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
        ),
    )
    store = HistoricalReplayStateStore.for_run(tmp_path, request.run_id)
    store.persist(result)
    capitals = (
        HistoricalReplayResetCapital(VirtualMarket.SPOT, Decimal("1000")),
        HistoricalReplayResetCapital(
            VirtualMarket.USD_M_FUTURES,
            Decimal("1000"),
        ),
    )

    with pytest.raises(ValueError, match="EXPLICIT_CONFIRMATION_REQUIRED"):
        store.reset_wallet_epochs(
            result,
            reset_at=END,
            capitals=capitals,
            confirmation="",
        )
    blocked = store.reset_wallet_epochs(
        result,
        reset_at=END,
        capitals=capitals,
        confirmation=VIRTUAL_WALLET_RESET_CONFIRMATION,
    )

    assert blocked.status == "RESET_BLOCKED"
    assert blocked.blockers == ("OPEN_VIRTUAL_POSITIONS_REQUIRE_SAFE_FINALIZATION",)
    assert blocked.persisted is False
    assert not blocked.history_path.exists()


def test_wallet_reset_rejects_capital_above_market_cap() -> None:
    with pytest.raises(ValueError, match="at most 1000 USDT"):
        HistoricalReplayResetCapital(VirtualMarket.SPOT, Decimal("1000.01"))

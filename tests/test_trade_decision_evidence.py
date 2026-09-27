"""Decision factors survive closure and restart without inventing legacy evidence."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.application.validation_pipeline import HistoricalPlaybookAdapter
from ai4binance.domain.research.virtual_runtime_attribution import TradeDecisionEvidence
from ai4binance.historical_replay_state import (
    _closed_trade_from_payload,
    _position_from_payload,
)
from ai4binance.indicators import atr
from ai4binance.intelligence.trading import ScenarioEngine
from ai4binance.learning.engine import ControlledLearningEngine
from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting import BacktestEngine, BacktestIntent
from ai4binance.research.backtesting.storage import BacktestAuditWriter
from ai4binance.storage import JsonlAuditStore
from ai4binance.strategies.engine import StrategyEngine
from ai4binance.strategies.registry import build_strategy_risk_profile_registry
from ai4binance.strategies.rules import historical_playbook_decision
from ai4binance.validation import ParameterSet
from tests.test_backtest_engine import NOW, candle, intent
from tests.test_strategy_rules import structural_candles
from tests.test_structural_entries import structural_context
from tests.test_virtual_runtime import attributed_open_virtual_position


def evidence() -> TradeDecisionEvidence:
    return TradeDecisionEvidence(
        status="RECORDED_AT_DECISION",
        as_of=NOW,
        direction_method="CONFIRMED_SWING_GRAPH",
        entry_method="CLOSE_RECLAIM",
        factors_json='{"previous_high":"99","close":"100"}',
    )


def test_evidence_is_immutable_and_digest_covers_factors_and_provenance() -> None:
    recorded = evidence()
    assert (
        replace(recorded, factors_json='{"close":"100","previous_high":"99"}')
        == recorded
    )
    assert (
        replace(recorded, status="RECONSTRUCTED_FROM_ARCHIVE").sha256 != recorded.sha256
    )
    with pytest.raises(FrozenInstanceError):
        cast(Any, recorded).entry_method = "OTHER"
    payload = cast(dict[str, object], to_primitive(recorded))
    assert TradeDecisionEvidence.from_payload(payload) == recorded
    payload["factors_json"] = '{"close":"200"}'
    with pytest.raises(ValueError, match="digest mismatch"):
        TradeDecisionEvidence.from_payload(payload)
    assert TradeDecisionEvidence.from_payload(None).status == "NOT_RECORDED"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "ASSUMED"},
        {"factors_json": "[]"},
        {"factors_json": '{"fabricated":true}'},
        {"status": "RECORDED_AT_DECISION"},
    ],
)
def test_invalid_or_fabricated_evidence_rejected(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError, match=r"evidence|factors"):
        TradeDecisionEvidence(
            status=kwargs.get("status", "NOT_RECORDED"),
            factors_json=kwargs.get("factors_json", "{}"),
        )


def test_historical_decision_records_causal_inputs_and_unique_market_identity() -> None:
    rows = structural_candles()
    intents = []
    for symbol, market, timeframe in (
        ("ETHUSDT", "SPOT", "1h"),
        ("LINKUSDT", "SPOT", "1h"),
        ("ETHUSDT", "SPOT", "4h"),
        ("ETHUSDT", "USD_M_FUTURES", "1h"),
    ):
        adapter = HistoricalPlaybookAdapter(
            "trend_continuation",
            ParameterSet("defaults", (("stop_atr_multiple", 1.5),)),
            historical_playbook_decision,
            atr,
            BacktestIntent,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            risk_profile_registry=build_strategy_risk_profile_registry(),
        )
        proposals = [adapter(rows[:n]) for n in range(1, len(rows) + 1)]
        proposal = next(p for p in proposals if p is not None)
        intents.append(proposal)
        factors = json.loads(proposal.decision_evidence.factors_json)
        assert factors["initial_stop"] == str(proposal.stop_loss)
        assert factors["relative_volume_minimum"] == "1.05"
        assert factors["structure"]["method"] == "CONFIRMED_SWING_GRAPH"
        assert proposal.decision_evidence.as_of == proposal.timestamp + timedelta(
            hours=1
        )
        assert (
            proposal.closed_trade_attribution.decision_evidence
            == proposal.decision_evidence
        )
    assert len({p.signal_id for p in intents}) == 4


def test_trade_closure_audit_and_learning_retain_evidence(tmp_path: Path) -> None:
    proposed = replace(intent(NOW), decision_evidence=evidence())
    rows = (candle(0, "100", "101", "99", "100"), candle(1, "100", "101", "94", "95"))
    engine = BacktestEngine()
    result = engine.run(
        symbol="BTCUSDT",
        timeframe="1h",
        candles=rows,
        signal_provider=lambda history: proposed if len(history) == 1 else None,
    )
    (trade,) = result.trades
    assert trade.attribution.decision_evidence == evidence()
    assert trade.trade_outcome.decision_evidence == evidence()
    assert trade.initial_stop_loss == proposed.stop_loss
    assert trade.initial_take_profit_levels == proposed.targets
    path = tmp_path / "audit.jsonl"
    BacktestAuditWriter(JsonlAuditStore(path)).append(result)
    persisted = json.loads(path.read_text().splitlines()[0])["payload"]["result"][
        "trades"
    ][0]
    assert (
        TradeDecisionEvidence.from_payload(
            persisted["attribution"]["decision_evidence"]
        )
        == evidence()
    )
    summary = ControlledLearningEngine().analyze(created_at=NOW, backtests=(result,))
    codes = {item.code: item.evidence_count for item in summary.lessons}
    assert codes["LOSS_ON_ENTRY_CANDLE"] == 1
    assert "DECISION_TIME_EVIDENCE_MISSING" not in codes


def test_futures_candidate_records_structural_state_and_net_rr() -> None:
    snapshot, results = structural_context()
    state = ScenarioEngine().build(snapshot, results)
    (candidate,) = StrategyEngine().generate(
        snapshot, results, trading_intelligence=state
    )
    recorded = candidate.decision_evidence
    factors = json.loads(recorded.factors_json)
    assert recorded.status == "RECORDED_AT_DECISION"
    assert recorded.as_of == snapshot.created_at
    assert factors["state"]["selected_scenario_id"] == state.selected_scenario_id
    assert factors["net_rr"] == str(candidate.net_risk_reward)
    assert factors["ema_role"] == "NOT_USED"


def test_position_restart_and_closed_trade_decoder_preserve_trace() -> None:
    position = replace(attributed_open_virtual_position(), decision_evidence=evidence())
    payload = cast(dict[str, object], to_primitive(position))
    assert _position_from_payload(payload).decision_evidence == evidence()
    payload.pop("decision_evidence")
    assert _position_from_payload(payload).decision_evidence.status == "NOT_RECORDED"
    # The closure decoder uses the same validated evidence contract.
    from tests.test_historical_replay_runner import (
        END,
        START,
        _OpenOnceOrchestrator,
        _request,
        _runner,
        _snapshot,
    )

    result = _runner(orchestrator=_OpenOnceOrchestrator()).run(
        _request(),
        (
            _snapshot(START, snapshot_id="trace-open"),
            _snapshot(END, snapshot_id="trace-close", high="120", low="60", close="72"),
        ),
    )
    assert result.closed_trades
    trade = result.closed_trades[0]
    trade = replace(
        trade, attribution=replace(trade.attribution, decision_evidence=evidence())
    )
    restored = _closed_trade_from_payload(cast(dict[str, object], to_primitive(trade)))
    assert restored.attribution.decision_evidence == evidence()


def test_runtime_request_preserves_trace_through_actual_fill_and_stop() -> None:
    from ai4binance.domain import Action
    from ai4binance.research.virtual_runtime import (
        VirtualMarketRuntime,
        VirtualPortfolioState,
    )
    from tests.test_virtual_runtime import (
        approved_virtual_runtime_request,
        lifecycle_candle,
    )

    runtime = VirtualMarketRuntime()
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:trace",
        decision_id="decision:trace",
        candidate_id="candidate:trace",
        symbol="BTCUSDT",
        market="SPOT",
        action=Action.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        decision_evidence=evidence(),
        portfolio=VirtualPortfolioState(
            portfolio_id="portfolio:trace",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
    )
    decision = runtime.evaluate(request)
    position = runtime.materialize_managed_position(
        request=request, decision=decision, opened_at=NOW
    )
    assert position.decision_evidence == evidence()
    closed = runtime.process_position(
        position=position,
        portfolio=decision.portfolio_after,
        candle=lifecycle_candle(1, "100", "103", "94", "96"),
    )
    assert closed.closed_trade is not None
    assert closed.closed_trade.attribution.decision_evidence == evidence()

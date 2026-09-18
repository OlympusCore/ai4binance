"""Canonical-pipeline historical replay orchestration tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

from ai4binance.application import ResearchApplicationService
from ai4binance.core.contracts.virtual_governance import (
    DGE_APPROVED_PAPER_ONLY,
    VirtualGovernanceResult,
)
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.reporting import to_primitive
from ai4binance.research import (
    HistoricalMarketReplayRequest,
    HistoricalMarketSelection,
    HistoricalReplayDatasetBinding,
    HistoricalReplayEvidenceClass,
    HistoricalReplayExecutionContext,
    VirtualMarket,
    VirtualSystemVersionSegment,
    VirtualWalletEpoch,
)
from ai4binance.research.virtual_runtime import VirtualMarketRuntime
from ai4binance.research.virtual_runtime_portfolio_state import VirtualPortfolioState
from ai4binance.research_runtime import (
    HistoricalMarketReplayRunner,
    HistoricalReplayCycleResult,
    HistoricalReplayRunResult,
    HistoricalReplayRunStatus,
    HistoricalReplaySnapshot,
)
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle

START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(hours=2)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64
HASH_1 = "1" * 64


class _SuccessStatus:
    value = "SUCCESS"


class _RiskResult:
    status: ClassVar[_SuccessStatus] = _SuccessStatus()
    blockers: ClassVar[tuple[str, ...]] = ()
    calculation_metadata: ClassVar[dict[str, object]] = {
        "candidate_id": "candidate",
        "approved": True,
        "size_usdt": "100",
        "quantity": "1",
        "risk_amount_usdt": "5",
    }


class _Orchestrator:
    def analyze(self, snapshot: MarketSnapshot) -> object:
        candidate = TradeCandidate(
            candidate_id=f"candidate:{snapshot.snapshot_id}",
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframe="1h",
            action=Action.BUY,
            setup_name="historical_replay_test",
            status=CandidateStatus.READY_FOR_RISK,
            entry_zone=PriceZone(Decimal("100"), Decimal("100")),
            invalidation_level=Decimal("95"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            trailing_stop=Decimal("95"),
            atr=Decimal("3"),
            risk_reward=Decimal("2"),
            score=80,
            confidence=0.8,
            market_type=snapshot.market_type,
            promotion_status=ValidationStatus.RESEARCH_ONLY,
        )
        risk = SimpleNamespace(
            agent_name="risk",
            status=_SuccessStatus(),
            blockers=(),
            calculation_metadata={
                **_RiskResult.calculation_metadata,
                "candidate_id": candidate.candidate_id,
            },
        )
        return SimpleNamespace(
            snapshot_id=snapshot.snapshot_id,
            market_snapshot=snapshot,
            blockers=(),
            agent_results={"risk": risk},
            candidate_setups=(candidate,),
            final_decision=SimpleNamespace(action=SimpleNamespace(value="NO_TRADE")),
        )


class _Outlook:
    def build(self, analysis: object) -> object:
        return SimpleNamespace(
            snapshot_id=cast(Any, analysis).snapshot_id,
            execution_allowed=False,
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )


class _ApprovedGovernance:
    def evaluate(self, **kwargs: object) -> VirtualGovernanceResult:
        snapshot = cast(Any, kwargs["snapshot"])
        return VirtualGovernanceResult(
            decision_id=f"dge:{snapshot.snapshot_id}",
            status=DGE_APPROVED_PAPER_ONLY,
            blockers=(),
            simulation_allowed=True,
        )


def _system_version() -> VirtualSystemVersionSegment:
    return VirtualSystemVersionSegment(
        effective_at=START,
        code_revision="historical-replay-test",
        configuration_sha256=HASH_A,
        strategy_bundle_sha256=HASH_B,
        feature_bundle_sha256=HASH_C,
        dge_rule_bundle_sha256=HASH_D,
        risk_policy_sha256=HASH_E,
        validation_policy_sha256=HASH_F,
        execution_model_sha256=HASH_1,
    )


def _binding(
    *,
    market: VirtualMarket = VirtualMarket.SPOT,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
) -> HistoricalReplayDatasetBinding:
    return HistoricalReplayDatasetBinding(
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        dataset_revision_id=f"dataset:{market.value}:{symbol}:{timeframe}",
        dataset_sha256=HASH_A,
        source_manifest_sha256=HASH_B,
        source_provenance_ref="binance-vision:test",
        coverage_start=START - timedelta(hours=1),
        coverage_end=END,
        row_count=3,
    )


def _request(
    *,
    run_id: str = "historical-run-a",
    epoch_id: str = "historical-epoch-a",
    portfolio_id: str = "historical-portfolio-a",
) -> HistoricalMarketReplayRequest:
    version = _system_version()
    return HistoricalMarketReplayRequest(
        run_id=run_id,
        start_at=START,
        end_at=END,
        timeframes=("1h",),
        market_selections=(
            HistoricalMarketSelection(VirtualMarket.SPOT, ("BTCUSDT",)),
        ),
        dataset_bindings=(_binding(),),
        wallet_epochs=(
            VirtualWalletEpoch(
                epoch_id=epoch_id,
                portfolio_id=portfolio_id,
                market=VirtualMarket.SPOT,
                initial_capital_usdt=Decimal("1000"),
                started_at=START,
                start_reason="historical replay test",
                system_segment_sha256=version.semantic_sha256,
                evidence_class=HistoricalReplayEvidenceClass.HISTORICAL_REPLAY,
            ),
        ),
        system_version=version,
    )


def _dual_market_request() -> HistoricalMarketReplayRequest:
    version = _system_version()
    return HistoricalMarketReplayRequest(
        run_id="historical-run-dual",
        start_at=START,
        end_at=END,
        timeframes=("1h",),
        market_selections=(
            HistoricalMarketSelection(VirtualMarket.SPOT, ("BTCUSDT",)),
            HistoricalMarketSelection(
                VirtualMarket.USD_M_FUTURES,
                ("BTCUSDT",),
            ),
        ),
        dataset_bindings=(
            _binding(),
            _binding(market=VirtualMarket.USD_M_FUTURES),
        ),
        wallet_epochs=(
            VirtualWalletEpoch(
                epoch_id="historical-epoch-spot",
                portfolio_id="historical-portfolio-spot",
                market=VirtualMarket.SPOT,
                initial_capital_usdt=Decimal("1000"),
                started_at=START,
                start_reason="historical dual-market replay test",
                system_segment_sha256=version.semantic_sha256,
                evidence_class=HistoricalReplayEvidenceClass.HISTORICAL_REPLAY,
            ),
            VirtualWalletEpoch(
                epoch_id="historical-epoch-futures",
                portfolio_id="historical-portfolio-futures",
                market=VirtualMarket.USD_M_FUTURES,
                initial_capital_usdt=Decimal("1000"),
                started_at=START,
                start_reason="historical dual-market replay test",
                system_segment_sha256=version.semantic_sha256,
                evidence_class=HistoricalReplayEvidenceClass.HISTORICAL_REPLAY,
            ),
        ),
        system_version=version,
    )


def _snapshot(
    created_at: datetime,
    *,
    snapshot_id: str,
    market: VirtualMarket = VirtualMarket.SPOT,
    symbol: str = "BTCUSDT",
    wallet_summary: dict[str, object] | None = None,
    execution_context: bool = False,
    high: str = "101",
    low: str = "99",
    close: str = "100",
    funding_payment_due: bool = False,
) -> HistoricalReplaySnapshot:
    timestamps = tuple(
        START - timedelta(hours=1) + timedelta(hours=index)
        for index in range(int((created_at - START) / timedelta(hours=1)) + 1)
    )
    candles = tuple(
        OHLCVCandle(
            timestamp=timestamp,
            open=Decimal("100"),
            high=(
                Decimal(high)
                if timestamp == created_at - timedelta(hours=1)
                else Decimal("101")
            ),
            low=(
                Decimal(low)
                if timestamp == created_at - timedelta(hours=1)
                else Decimal("99")
            ),
            close=(
                Decimal(close)
                if timestamp == created_at - timedelta(hours=1)
                else Decimal("100")
            ),
            volume=Decimal("1000"),
        )
        for timestamp in timestamps
        if timestamp <= created_at
    )
    snapshot = MarketSnapshot(
        snapshot_id=snapshot_id,
        created_at=created_at,
        exchange="Binance",
        market_type=market.value,
        symbol=symbol,
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": candles},
        latest_price=Decimal(close),
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        spread=Decimal("0.2"),
        data_quality=DataQuality.DATA_VALID,
        wallet_summary=wallet_summary or {},
    )
    binding = _binding(market=market, symbol=symbol)
    context = (
        HistoricalReplayExecutionContext(
            market=market,
            symbol=symbol,
            timeframe="1h",
            observed_at=created_at,
            dataset_revision_id=binding.dataset_revision_id,
            dataset_sha256=binding.dataset_sha256,
            source_manifest_sha256=binding.source_manifest_sha256,
            source_provenance_ref=binding.source_provenance_ref,
            execution_model_sha256=HASH_1,
            fee_ratio=Decimal("0.001"),
            slippage_ratio=Decimal("0.0005"),
            half_spread_ratio=Decimal("0"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.01"),
            minimum_notional=Decimal("5"),
            mark_price=(
                Decimal(close) if market is VirtualMarket.USD_M_FUTURES else None
            ),
            funding_rate=(
                Decimal("0.001") if market is VirtualMarket.USD_M_FUTURES else None
            ),
            funding_payment_due=(
                funding_payment_due if market is VirtualMarket.USD_M_FUTURES else False
            ),
            leverage=5 if market is VirtualMarket.USD_M_FUTURES else None,
            isolated_margin_usdt=(
                Decimal("30") if market is VirtualMarket.USD_M_FUTURES else None
            ),
            maintenance_margin_ratio=(
                Decimal("0.02") if market is VirtualMarket.USD_M_FUTURES else None
            ),
            liquidation_fee_ratio=(
                Decimal("0.005") if market is VirtualMarket.USD_M_FUTURES else None
            ),
        )
        if execution_context
        else None
    )
    return HistoricalReplaySnapshot(snapshot, (binding,), context)


def _runner(**application_overrides: object) -> HistoricalMarketReplayRunner:
    options = {
        "orchestrator": _Orchestrator(),
        "outlook_engine": _Outlook(),
        "primitive_converter": to_primitive,
        "virtual_market_runtime": VirtualMarketRuntime(),
        "virtual_governance_evaluator": _ApprovedGovernance(),
    }
    options.update(application_overrides)
    return HistoricalMarketReplayRunner(
        ResearchApplicationService(**cast(Any, options))
    )


def test_runner_reuses_canonical_pipeline_and_carries_portfolio_forward() -> None:
    later = _snapshot(END, snapshot_id="snapshot-later")
    earlier = _snapshot(START, snapshot_id="snapshot-earlier")

    result = _runner().run(_request(), (later, earlier))

    assert [cycle.replay_snapshot.snapshot.snapshot_id for cycle in result.cycles] == [
        "snapshot-earlier",
        "snapshot-later",
    ]
    assert result.cycles[0].portfolio_after.cash_usdt == Decimal("900")
    assert result.cycles[1].portfolio_before == result.cycles[0].portfolio_after
    assert result.cycles[1].portfolio_after == result.cycles[1].portfolio_before
    assert "VIRTUAL_MAX_CONCURRENT_POSITIONS_EXCEEDED" in result.blockers
    assert result.status is HistoricalReplayRunStatus.RUNNING_WITH_BLOCKERS
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runner_keeps_spot_and_futures_portfolios_independent() -> None:
    result = _runner().run(
        _dual_market_request(),
        (
            _snapshot(START, snapshot_id="snapshot-spot"),
            _snapshot(
                START,
                snapshot_id="snapshot-futures",
                market=VirtualMarket.USD_M_FUTURES,
            ),
        ),
    )

    by_market = {portfolio.market: portfolio for portfolio in result.final_portfolios}
    assert by_market["SPOT"].portfolio_id == "historical-portfolio-spot"
    assert by_market["SPOT"].cash_usdt == Decimal("900")
    assert by_market["USD_M_FUTURES"].portfolio_id == ("historical-portfolio-futures")
    assert by_market["USD_M_FUTURES"].cash_usdt == Decimal("1000")
    assert result.cycles[1].replay_snapshot.market == "USD_M_FUTURES"
    assert result.cycles[1].portfolio_after == result.cycles[1].portfolio_before
    assert result.cycles[1].blockers


def test_runner_is_semantically_deterministic_across_generated_identities() -> None:
    first = _runner().run(
        _request(),
        (_snapshot(START, snapshot_id="snapshot-a"),),
    )
    second = _runner().run(
        _request(
            run_id="historical-run-b",
            epoch_id="historical-epoch-b",
            portfolio_id="historical-portfolio-b",
        ),
        (_snapshot(START, snapshot_id="snapshot-b"),),
    )

    assert first.semantic_result_sha256 == second.semantic_result_sha256
    assert first.audit_result_sha256 != second.audit_result_sha256
    assert first.status is HistoricalReplayRunStatus.COMPLETED


def test_runner_rejects_unbound_dataset_and_incomplete_market_scope() -> None:
    replay_snapshot = _snapshot(START, snapshot_id="snapshot-a")
    unbound = replace(
        replay_snapshot.dataset_bindings[0],
        dataset_revision_id="dataset:unbound",
    )
    with pytest.raises(ValueError, match="unbound dataset revision"):
        _runner().run(
            _request(),
            (replace(replay_snapshot, dataset_bindings=(unbound,)),),
        )

    expanded = replace(
        _request(),
        market_selections=(
            HistoricalMarketSelection(
                VirtualMarket.SPOT,
                ("BTCUSDT", "ETHUSDT"),
            ),
        ),
        dataset_bindings=(_binding(), _binding(symbol="ETHUSDT")),
    )
    with pytest.raises(ValueError, match="cover every selected market symbol"):
        _runner().run(expanded, (replay_snapshot,))


def test_runner_rejects_lookahead_duplicate_and_out_of_window_events() -> None:
    replay_snapshot = _snapshot(START, snapshot_id="snapshot-a")
    unclosed_candle = replace(
        replay_snapshot.snapshot.ohlcv_by_timeframe["1h"][0],
        timestamp=START,
    )
    unclosed = replace(
        replay_snapshot,
        snapshot=replace(
            replay_snapshot.snapshot,
            ohlcv_by_timeframe={"1h": (unclosed_candle,)},
        ),
    )
    with pytest.raises(ValueError, match="unclosed candle"):
        _runner().run(_request(), (unclosed,))
    future_candle = OHLCVCandle(
        timestamp=START + timedelta(minutes=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1000"),
    )
    lookahead = replace(
        replay_snapshot,
        snapshot=replace(
            replay_snapshot.snapshot,
            ohlcv_by_timeframe={"1h": (future_candle,)},
        ),
    )
    with pytest.raises(ValueError, match="look-ahead"):
        _runner().run(_request(), (lookahead,))
    with pytest.raises(ValueError, match="snapshot ids must be unique"):
        _runner().run(_request(), (replay_snapshot, replay_snapshot))
    with pytest.raises(ValueError, match="exceeds request end"):
        _runner().run(
            _request(),
            (_snapshot(END + timedelta(hours=1), snapshot_id="snapshot-late"),),
        )


def test_runner_rejects_real_wallet_and_unbounded_external_state() -> None:
    with pytest.raises(ValueError, match="real wallet state"):
        _snapshot(
            START,
            snapshot_id="snapshot-wallet",
            wallet_summary={"USDT": "1000"},
        )
    with pytest.raises(ValueError, match="unbounded external state: wallet_service"):
        _runner(wallet_service=object())
    with pytest.raises(ValueError, match="unbounded external state: learning_loop"):
        _runner(learning_loop=object())


@pytest.mark.parametrize(
    ("field_name", "value", "expected"),
    [
        ("wallet_capture_enabled", True, "wallet_service"),
        ("market_context_registry", object(), "market_context_registry"),
        ("market_context_provider_ids", ("provider",), "market_context_registry"),
        ("learning_evidence_provider", object(), "learning_evidence_provider"),
    ],
)
def test_runner_rejects_every_unbounded_application_input(
    field_name: str,
    value: object,
    expected: str,
) -> None:
    overrides = {field_name: value}
    if field_name == "wallet_capture_enabled":
        overrides["wallet_service"] = object()
    if field_name in {"market_context_registry", "market_context_provider_ids"}:
        overrides["market_context_registry"] = object()
        overrides["market_context_request_builder"] = lambda **_: object()
    with pytest.raises(ValueError, match=expected):
        _runner(**overrides)


def test_snapshot_contract_rejects_unbound_context_and_identity_drift() -> None:
    replay_snapshot = _snapshot(START, snapshot_id="snapshot-a")
    with pytest.raises(ValueError, match="server_time cannot lead"):
        HistoricalReplaySnapshot(
            replace(
                replay_snapshot.snapshot,
                server_time=START + timedelta(seconds=1),
            ),
            replay_snapshot.dataset_bindings,
        )
    with pytest.raises(ValueError, match="exchange must be Binance"):
        HistoricalReplaySnapshot(
            replace(replay_snapshot.snapshot, exchange="Other"),
            replay_snapshot.dataset_bindings,
        )
    with pytest.raises(ValueError, match="historical context evidence"):
        HistoricalReplaySnapshot(
            replace(replay_snapshot.snapshot, order_book_summary={"bid": "100"}),
            replay_snapshot.dataset_bindings,
        )
    with pytest.raises(ValueError, match="requires dataset bindings"):
        HistoricalReplaySnapshot(replay_snapshot.snapshot, ())
    with pytest.raises(ValueError, match="bindings must be unique"):
        HistoricalReplaySnapshot(
            replay_snapshot.snapshot,
            replay_snapshot.dataset_bindings * 2,
        )
    with pytest.raises(ValueError, match="identity must match"):
        HistoricalReplaySnapshot(
            replay_snapshot.snapshot,
            (replace(replay_snapshot.dataset_bindings[0], symbol="ETHUSDT"),),
        )
    with pytest.raises(ValueError, match="cover snapshot timeframes"):
        HistoricalReplaySnapshot(
            replace(replay_snapshot.snapshot, timeframes=("1h", "4h")),
            replay_snapshot.dataset_bindings,
        )
    non_utc = START.astimezone(timezone(timedelta(hours=3)))
    with pytest.raises(ValueError, match="must use canonical UTC"):
        HistoricalReplaySnapshot(
            replace(replay_snapshot.snapshot, created_at=non_utc),
            replay_snapshot.dataset_bindings,
        )


def test_runner_rejects_ambiguous_and_invalid_candle_prefixes() -> None:
    replay_snapshot = _snapshot(START, snapshot_id="snapshot-a")
    same_event = replace(
        replay_snapshot,
        snapshot=replace(replay_snapshot.snapshot, snapshot_id="snapshot-b"),
    )
    with pytest.raises(ValueError, match="event identities must be unique"):
        _runner().run(_request(), (replay_snapshot, same_event))
    with pytest.raises(ValueError, match="precedes request start"):
        _runner().run(
            _request(),
            (
                replace(
                    replay_snapshot,
                    snapshot=replace(
                        replay_snapshot.snapshot,
                        snapshot_id="snapshot-early",
                        created_at=START - timedelta(seconds=1),
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="candles must exactly cover"):
        _runner().run(
            _request(),
            (
                replace(
                    replay_snapshot,
                    snapshot=replace(
                        replay_snapshot.snapshot,
                        ohlcv_by_timeframe={"4h": ()},
                    ),
                ),
            ),
        )
    expanded_timeframes = replace(
        _request(),
        timeframes=("1h", "4h"),
        dataset_bindings=(_binding(), _binding(timeframe="4h")),
    )
    with pytest.raises(ValueError, match="timeframes must match request"):
        _runner().run(expanded_timeframes, (replay_snapshot,))
    with pytest.raises(ValueError, match="prefix cannot be empty"):
        _runner().run(
            _request(),
            (
                replace(
                    replay_snapshot,
                    snapshot=replace(
                        replay_snapshot.snapshot,
                        ohlcv_by_timeframe={"1h": ()},
                    ),
                ),
            ),
        )
    candle = replay_snapshot.snapshot.ohlcv_by_timeframe["1h"][0]
    with pytest.raises(ValueError, match="strictly chronological"):
        _runner().run(
            _request(),
            (
                replace(
                    replay_snapshot,
                    snapshot=replace(
                        replay_snapshot.snapshot,
                        ohlcv_by_timeframe={"1h": (candle, candle)},
                    ),
                ),
            ),
        )
    gapped_snapshot = _snapshot(END, snapshot_id="snapshot-gapped")
    gapped_candles = tuple(
        gapped_snapshot.snapshot.ohlcv_by_timeframe["1h"][index] for index in (0, 2)
    )
    with pytest.raises(ValueError, match="cadence gap"):
        _runner().run(
            _request(),
            (
                replace(
                    gapped_snapshot,
                    snapshot=replace(
                        gapped_snapshot.snapshot,
                        ohlcv_by_timeframe={"1h": gapped_candles},
                    ),
                ),
            ),
        )
    outside = replace(candle, timestamp=START - timedelta(hours=1, seconds=1))
    with pytest.raises(ValueError, match="outside dataset coverage"):
        _runner().run(
            _request(),
            (
                replace(
                    replay_snapshot,
                    snapshot=replace(
                        replay_snapshot.snapshot,
                        ohlcv_by_timeframe={"1h": (outside,)},
                    ),
                ),
            ),
        )


class _NoCandidateOrchestrator:
    def analyze(self, snapshot: MarketSnapshot) -> object:
        return SimpleNamespace(
            snapshot_id=snapshot.snapshot_id,
            market_snapshot=snapshot,
            blockers=(),
            agent_results={},
            candidate_setups=(),
            final_decision=SimpleNamespace(action=SimpleNamespace(value="NO_TRADE")),
        )


class _OpenOnceOrchestrator(_Orchestrator):
    def analyze(self, snapshot: MarketSnapshot) -> object:
        if snapshot.created_at == START:
            return super().analyze(snapshot)
        return _NoCandidateOrchestrator().analyze(snapshot)


def test_runner_executes_full_futures_lifecycle_through_canonical_runtime() -> None:
    dual = _dual_market_request()
    futures_request = replace(
        dual,
        run_id="historical-run-futures-lifecycle",
        market_selections=(dual.market_selections[1],),
        dataset_bindings=(dual.dataset_bindings[1],),
        wallet_epochs=(dual.wallet_epochs[1],),
    )
    opened = _snapshot(
        START,
        snapshot_id="snapshot-futures-open",
        market=VirtualMarket.USD_M_FUTURES,
        execution_context=True,
    )
    liquidated = _snapshot(
        END,
        snapshot_id="snapshot-futures-liquidated",
        market=VirtualMarket.USD_M_FUTURES,
        execution_context=True,
        high="120",
        low="60",
        close="72",
        funding_payment_due=True,
    )

    result = _runner(orchestrator=_OpenOnceOrchestrator()).run(
        futures_request,
        (liquidated, opened),
    )

    opening_cycle, closing_cycle = result.cycles
    assert opening_cycle.workflow.virtual_runtime_request is not None
    assert opening_cycle.workflow.virtual_runtime_request.fee_ratio == Decimal("0.001")
    assert opening_cycle.managed_position_after is not None
    assert opening_cycle.managed_position_after.market == "USD_M_FUTURES"
    assert closing_cycle.position_update is not None
    assert closing_cycle.position_update.exit_reason is not None
    assert closing_cycle.position_update.exit_reason.value == "LIQUIDATION"
    assert closing_cycle.closed_trade is not None
    assert closing_cycle.closed_trade.funding_cost_usdt > Decimal("0")
    assert result.open_positions == ()
    assert result.closed_trades == (closing_cycle.closed_trade,)
    assert result.final_portfolios[0].open_position_count == 0
    assert result.final_portfolios[0].position_side is None
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_snapshot_execution_context_is_exactly_dataset_and_model_bound() -> None:
    replay_snapshot = _snapshot(
        START,
        snapshot_id="snapshot-futures-context",
        market=VirtualMarket.USD_M_FUTURES,
        execution_context=True,
    )
    context = cast(HistoricalReplayExecutionContext, replay_snapshot.execution_context)

    with pytest.raises(ValueError, match="must match its exact dataset binding"):
        replace(
            replay_snapshot,
            execution_context=replace(context, dataset_revision_id="dataset:drift"),
        )
    with pytest.raises(ValueError, match="must match the request execution model"):
        _runner().run(
            replace(
                _dual_market_request(),
                market_selections=(_dual_market_request().market_selections[1],),
                dataset_bindings=(_dual_market_request().dataset_bindings[1],),
                wallet_epochs=(_dual_market_request().wallet_epochs[1],),
            ),
            (
                replace(
                    replay_snapshot,
                    execution_context=replace(
                        context,
                        execution_model_sha256=HASH_A,
                    ),
                ),
            ),
        )


def test_runner_preserves_portfolio_when_pipeline_has_no_candidate() -> None:
    result = _runner(orchestrator=_NoCandidateOrchestrator()).run(
        _request(),
        (_snapshot(START, snapshot_id="snapshot-a"),),
    )

    assert result.cycles[0].workflow.virtual_runtime_decision is None
    assert result.cycles[0].portfolio_after == result.cycles[0].portfolio_before
    assert result.blockers == (
        "NO_RESEARCH_CANDIDATE",
        "RISK_NOT_EVALUATED",
        "NO_VIRTUAL_SETUP_CANDIDATE",
        "DGE_SIMULATION_NOT_APPROVED",
    )


class _WrongMarketOrchestrator(_Orchestrator):
    def analyze(self, snapshot: MarketSnapshot) -> object:
        analysis = cast(Any, super().analyze(snapshot))
        candidate = replace(
            analysis.candidate_setups[0],
            market_type="USD_M_FUTURES",
        )
        return SimpleNamespace(
            **{
                **vars(analysis),
                "candidate_setups": (candidate,),
            }
        )


class _InvalidRuntime:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def evaluate(self, request: object) -> object:
        typed_request = cast(Any, request)
        decision = VirtualMarketRuntime().evaluate(typed_request)
        if self.mode == "before":
            return replace(
                decision,
                portfolio_before=replace(
                    typed_request.portfolio,
                    cash_usdt=Decimal("999"),
                    equity_usdt=Decimal("999"),
                ),
            )
        return SimpleNamespace(
            status=decision.status,
            eligibility=decision.eligibility,
            trade_intent=decision.trade_intent,
            portfolio_before=decision.portfolio_before,
            portfolio_after=object(),
            audit_refs=decision.audit_refs,
            halt_review=decision.halt_review,
        )


def test_runner_rejects_market_drift_and_invalid_runtime_portfolios() -> None:
    replay_snapshot = _snapshot(START, snapshot_id="snapshot-a")
    with pytest.raises(ValueError, match="candidate, snapshot and portfolio markets"):
        _runner(orchestrator=_WrongMarketOrchestrator()).run(
            _request(),
            (replay_snapshot,),
        )
    with pytest.raises(ValueError, match="changed portfolio input"):
        _runner(virtual_market_runtime=_InvalidRuntime("before")).run(
            _request(),
            (replay_snapshot,),
        )
    with pytest.raises(ValueError, match="returned invalid portfolio"):
        _runner(virtual_market_runtime=_InvalidRuntime("after")).run(
            _request(),
            (replay_snapshot,),
        )


def _cycle_fixture() -> tuple[
    HistoricalReplayRunResult,
    HistoricalReplayCycleResult,
]:
    result = _runner().run(
        _request(),
        (_snapshot(START, snapshot_id="snapshot-a"),),
    )
    return result, result.cycles[0]


def test_cycle_contract_rejects_authority_and_portfolio_drift() -> None:
    _, cycle = _cycle_fixture()
    with pytest.raises(ValueError, match="sequence cannot be negative"):
        replace(cycle, sequence=-1)
    with pytest.raises(ValueError, match="cycle cannot authorize"):
        replace(cycle, execution_allowed=True)
    invalid_workflow = SimpleNamespace(
        execution_allowed=True,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )
    with pytest.raises(ValueError, match="workflow cannot authorize"):
        replace(cycle, workflow=cast(Any, invalid_workflow))
    wrong_live_workflow = SimpleNamespace(
        execution_allowed=False,
        live_eligibility_status="LIVE_ELIGIBLE",
    )
    with pytest.raises(ValueError, match="workflow must remain live blocked"):
        replace(cycle, workflow=cast(Any, wrong_live_workflow))
    other_market = VirtualPortfolioState(
        portfolio_id=cycle.portfolio_after.portfolio_id,
        market="USD_M_FUTURES",
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )
    with pytest.raises(ValueError, match="market must match"):
        replace(cycle, portfolio_after=other_market)
    with pytest.raises(ValueError, match="replace portfolio identity"):
        replace(
            cycle,
            portfolio_after=replace(cycle.portfolio_after, portfolio_id="other"),
        )
    with pytest.raises(ValueError, match="replace initial capital"):
        replace(
            cycle,
            portfolio_after=VirtualPortfolioState(
                portfolio_id=cycle.portfolio_after.portfolio_id,
                market="SPOT",
                cash_usdt=Decimal("500"),
                equity_usdt=Decimal("500"),
                initial_equity_usdt=Decimal("500"),
            ),
        )
    with pytest.raises(ValueError, match="must match canonical runtime"):
        replace(cycle, portfolio_after=cycle.portfolio_before)

    blocked = (
        _runner(orchestrator=_NoCandidateOrchestrator())
        .run(
            _request(),
            (_snapshot(START, snapshot_id="snapshot-no-candidate"),),
        )
        .cycles[0]
    )
    with pytest.raises(ValueError, match="without a runtime decision cannot mutate"):
        replace(
            blocked,
            portfolio_after=replace(blocked.portfolio_after, cash_usdt=Decimal("999")),
        )


def test_run_result_contract_rejects_authority_and_epoch_drift() -> None:
    result, _ = _cycle_fixture()
    with pytest.raises(ValueError, match="requires completed cycles"):
        replace(result, cycles=())
    with pytest.raises(ValueError, match="result cannot authorize"):
        replace(result, execution_allowed=True)
    with pytest.raises(ValueError, match="contiguous and ordered"):
        replace(result, cycles=(replace(result.cycles[0], sequence=1),))
    with pytest.raises(ValueError, match="one final portfolio per market"):
        replace(
            result,
            final_portfolios=(
                VirtualPortfolioState(
                    portfolio_id="futures",
                    market="USD_M_FUTURES",
                    cash_usdt=Decimal("1000"),
                    equity_usdt=Decimal("1000"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="wallet epoch identity"):
        replace(
            result,
            final_portfolios=(
                replace(result.final_portfolios[0], portfolio_id="other"),
            ),
        )
    with pytest.raises(ValueError, match="preserve epoch capital"):
        replace(
            result,
            final_portfolios=(
                VirtualPortfolioState(
                    portfolio_id=result.final_portfolios[0].portfolio_id,
                    market="SPOT",
                    cash_usdt=Decimal("500"),
                    equity_usdt=Decimal("500"),
                    initial_equity_usdt=Decimal("500"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="last cycle state"):
        replace(result, final_portfolios=(result.cycles[0].portfolio_before,))


def test_runner_and_result_contracts_fail_closed() -> None:
    replay_snapshot = _snapshot(START, snapshot_id="snapshot-a")
    with pytest.raises(ValueError, match="at least one snapshot"):
        _runner().run(_request(), ())
    with pytest.raises(TypeError, match="canonical contract"):
        _runner().run(_request(), (object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        HistoricalReplaySnapshot(
            replay_snapshot.snapshot,
            replay_snapshot.dataset_bindings,
            execution_allowed=True,
        )

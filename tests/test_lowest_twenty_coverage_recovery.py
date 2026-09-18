"""Focused regression coverage for the current lowest coverage audit surfaces."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.error import HTTPError

import pytest

import ai4binance.accounting.ui_reports as ui_reports
import ai4binance.application.research as research_app
import ai4binance.cli.accounting as cli_accounting
import ai4binance.historical_replay_evaluation as replay_eval
import ai4binance.ops.system_report as system_report
from ai4binance.agents.preflight import (
    CapabilityBundlePreflightDecision,
    CapabilityBundlePreflightPlan,
    CapabilityPreflightDecision,
    CapabilityPreflightMode,
    CapabilityPreflightPlan,
)
from ai4binance.config import Settings
from ai4binance.core.errors import (
    ExchangeError,
    ExchangeHttpError,
    ExchangePayloadError,
)
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity
from ai4binance.enterprise.departments import build_default_department_registry
from ai4binance.enterprise.prompt_intake import (
    ExecutivePromptIntake,
    PromptAccessDecision,
    PromptAccessPolicy,
    PromptAccessStatus,
    PromptVisibility,
)
from ai4binance.enterprise.reviews import (
    PeriodicReviewRecord,
    ReviewCadence,
    ReviewOutcome,
)
from ai4binance.execution.authorization import (
    ExecutionAuthorizationAlreadyConsumedError,
    ExecutionAuthorizationConsumption,
    ExecutionAuthorizationEnvelope,
    LocalExecutionAuthorizationLedger,
)
from ai4binance.execution.order_command import SpotOrderCommand
from ai4binance.governance.blocker_reduction import VirtualBlockerReduction
from ai4binance.markets import CapitalMarket
from ai4binance.mcp.evidence import (
    EvidenceEnvelope,
    EvidenceGateway,
    EvidenceSource,
    FreshnessStatus,
)
from ai4binance.ops.runtime import (
    RuntimeStatusStore,
    SingleInstanceLease,
    _account_order_view,
    _replace_file_with_retry,
    _stored_order_view,
)
from ai4binance.portfolio.risk_reward_gate import (
    RiskRewardGate,
    RiskRewardGateInput,
    RiskRewardGatePolicy,
    RiskRewardGateResult,
)
from ai4binance.research.virtual_market import DailyEquityPoint, VirtualMarket
from ai4binance.research_runtime import HistoricalMarketEquityCurve
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
)
from ai4binance.strategies.price_action import PriceActionPlaybookEngine
from ai4binance.strategies.regime_router import (
    DeterministicRegimeRouter,
    RoutedMarketRegime,
)
from ai4binance.tuning import StrategyParameterTournament
from ai4binance.tuning.models import (
    StrategyProfileCandidate,
    TournamentConfig,
    TournamentContextEvaluation,
    TournamentEntry,
)
from ai4binance.tuning.promotion import (
    GovernedParameterStore,
    HumanApproval,
    StrategyPromotionTarget,
)
from ai4binance.validation import MarketRegime, ParameterSet, WalkForwardConfig
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceLedger,
    PromotionEvidenceQuery,
    PromotionEvidenceRecord,
    PromotionEvidenceRegistry,
    PromotionEvidenceSourceKind,
    _record_from_payload,
)
from ai4binance.whale_fusion.derivatives.binance_client import (
    BinanceUsdMClient,
    UsdMFuturesPublicTransport,
)
from ai4binance.whale_fusion.models import DerivativesMetric

NOW = datetime(2026, 9, 16, 9, 30, tzinfo=UTC)
SHA = "1" * 64


def _snapshot(
    *,
    latest_price: Decimal | None = Decimal("100"),
    market_type: str = "Spot",
    inventory: bool = False,
) -> MarketSnapshot:
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(hours=30 - index),
            open=Decimal("95") + index,
            high=Decimal("105") + index,
            low=Decimal("90") + index,
            close=Decimal("100") + index,
            volume=Decimal("1000"),
        )
        for index in range(30)
    )
    return MarketSnapshot(
        snapshot_id="snapshot-coverage",
        created_at=NOW,
        exchange="Binance",
        market_type=market_type,
        symbol="BTCUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": candles},
        latest_price=latest_price,
        bid=Decimal("99"),
        ask=Decimal("101"),
        spread=Decimal("2"),
        exchange_filters={},
        data_quality=DataQuality.DATA_VALID,
        inventory_summary={"quantity": "1"} if inventory else {},
        market_metadata={"market_regime": "TREND"},
    )


def _agent(
    name: str,
    vote: float,
    *,
    status: AgentStatus = AgentStatus.SUCCESS,
    setups: tuple[str, ...] = (),
    metadata: dict[str, object] | None = None,
) -> AgentResult:
    return AgentResult(
        agent_name=name,
        agent_version="1",
        snapshot_id="snapshot-coverage",
        timestamp=NOW,
        symbol="BTCUSDT",
        timeframes=("1h",),
        status=status,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=vote,
        score=80.0,
        confidence=0.75,
        evidence=(f"{name}:evidence",),
        reason_codes=("TEST",),
        detected_setups=setups,
        calculation_metadata=metadata or {},
    )


def _candidate(
    action: Action = Action.BUY,
    *,
    inventory_action: str = "NONE",
) -> TradeCandidate:
    stop = Decimal("95") if action is Action.BUY else Decimal("105")
    target = Decimal("110") if action is Action.BUY else Decimal("90")
    return TradeCandidate(
        candidate_id="candidate-coverage",
        snapshot_id="snapshot-coverage",
        timestamp=NOW,
        symbol="BTCUSDT",
        timeframe="1h",
        action=action,
        setup_name="breakout_retest",
        status=CandidateStatus.READY_FOR_RISK,
        entry_zone=PriceZone(Decimal("99"), Decimal("101")),
        invalidation_level=stop,
        stop_loss=stop,
        take_profit_levels=(target,),
        trailing_stop=stop,
        atr=Decimal("2"),
        risk_reward=Decimal("2"),
        score=80.0,
        confidence=0.75,
        promotion_status=ValidationStatus.RESEARCH_ONLY,
        inventory_action=inventory_action,
        evidence=("seed",),
    )


def _authorization(**overrides: object) -> ExecutionAuthorizationEnvelope:
    command = SpotOrderCommand(
        "BTCUSDT",
        "BUY",
        "LIMIT",
        Decimal("1"),
        "client-1",
        Decimal("100"),
        "GTC",
    )
    values: dict[str, object] = {
        "authorization_id": "auth-1",
        "approval_id": "approval-1",
        "preview_hash": command.preview_hash,
        "decision_id": "decision-1",
        "snapshot_id": "snapshot-1",
        "strategy_id": "strategy-1",
        "strategy_version": "1.0.0",
        "symbol": command.symbol,
        "market_type": "SPOT",
        "side": command.side,
        "order_type": command.order_type,
        "quantity": command.quantity,
        "client_order_id": command.client_order_id,
        "risk_assessment_hash": "2" * 64,
        "validation_bundle_hash": "3" * 64,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "approved_by": "GovernanceOwner:test",
        "single_use_nonce": "nonce-1",
        "price": command.price,
        "time_in_force": command.time_in_force,
    }
    values.update(overrides)
    return ExecutionAuthorizationEnvelope(**values)  # type: ignore[arg-type]


def test_accounting_ui_report_private_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ui_reports.AccountingUiReportBuilder(tmp_path, tmp_path, 60).build(
            datetime(2026, 1, 1)
        )
    missing = ui_reports._read_events(tmp_path / "missing.jsonl", limit=10)
    assert missing == ()
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\nnot-json\n"
        + json.dumps({"payload": {"envelope": {"source_type": "REST"}}})
        + "\n",
        encoding="utf-8",
    )
    loaded = ui_reports._read_events(events, limit=10)
    assert ui_reports._source_counts(loaded) == {"REST": 1}
    channels = ui_reports._channel_summary(
        (
            {"payload": {"envelope": "bad"}},
            {
                "payload": {
                    "envelope": {
                        "product_type": "UNKNOWN",
                        "source_type": "REST",
                    }
                }
            },
            {
                "payload": {
                    "envelope": {
                        "product_type": "SPOT",
                        "source_type": "REST",
                        "endpoint": "orders",
                    },
                    "received_at": NOW.isoformat(),
                }
            },
        ),
        observed_at=NOW + timedelta(seconds=30),
        freshness_seconds=60,
    )
    assert channels[0]["status"] == "ACTIVE"
    assert ui_reports._render_blockers(()) == '<p class="muted">No active blockers.</p>'
    assert "No activity yet" in ui_reports._render_activity(())
    assert "no records" in ui_reports._render_endpoint_list(())
    assert ui_reports._parse_time("bad") is None
    assert ui_reports._parse_time("2026-01-01T00:00:00") is None
    assert ui_reports._age(None) == ""
    assert ui_reports._age(90) == "1.5min"


def test_promotion_evidence_boundary_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identity"):
        PromotionEvidenceRecord(
            evidence_id=" ",
            symbol="BTCUSDT",
            source_kind=cast(Any, "MANUAL_REVIEW"),
            source_ref="ref",
            observed_at=NOW,
            promotion_status=ValidationStatus.RESEARCH_ONLY,
        )

    with pytest.raises(ValueError, match="timeframe"):
        PromotionEvidenceRecord(
            "ev-1",
            "btcusdt",
            PromotionEvidenceSourceKind.MANUAL_REVIEW,
            "ref",
            NOW,
            ValidationStatus.RESEARCH_ONLY,
            timeframe=" ",
        )
    with pytest.raises(ValueError, match="complete"):
        PromotionEvidenceRecord(
            "ev-2",
            "btcusdt",
            PromotionEvidenceSourceKind.MANUAL_REVIEW,
            "ref",
            NOW,
            ValidationStatus.PAPER_APPROVED,
            strategy_id="strategy",
        )
    query = PromotionEvidenceQuery(
        "strategy",
        "1.0.0",
        "a" * 64,
        "btcusdt",
        "spot",
        "1h",
        "b" * 64,
        "c" * 64,
        "d" * 40,
        NOW,
    )
    record = PromotionEvidenceRecord(
        "ev-3",
        "btcusdt",
        PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
        "ref",
        NOW,
        ValidationStatus.LIVE_ELIGIBLE,
        timeframe="1h",
        strategy_id="strategy",
        strategy_version="1.0.0",
        strategy_sha256="a" * 64,
        market_type="spot",
        parameter_set_sha256="b" * 64,
        dataset_sha256="c" * 64,
        code_revision="d" * 40,
    )
    assert PromotionEvidenceRegistry((record,)).resolve(query=query) is (
        ValidationStatus.LIVE_ELIGIBLE
    )
    ledger = PromotionEvidenceLedger(tmp_path / "promotion.jsonl")
    assert ledger.records() == ()
    assert ledger.append_if_absent(record) is True
    assert ledger.append_if_absent(record) is False
    assert ledger.as_registry().has_promotion_evidence(query=query)
    payload = record.__dict__ if hasattr(record, "__dict__") else record
    parsed = _record_from_payload(
        {
            "evidence_id": "ev-4",
            "symbol": "btcusdt",
            "source_kind": "MANUAL_REVIEW",
            "source_ref": "ref",
            "observed_at": NOW.isoformat(),
            "promotion_status": "RESEARCH_ONLY",
            "blockers": ["A"],
            "expires_at": (NOW + timedelta(days=1)).isoformat(),
        }
    )
    assert parsed.blockers == ("A",)
    assert payload is not None


def test_runtime_lock_and_status_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RuntimeStatusStore(tmp_path / "runtime.json")
    (tmp_path / "runtime.json").write_text(
        json.dumps({"health": {"consecutive_failures": True}}), encoding="utf-8"
    )
    store.save_failure(RuntimeError("secret detail"), NOW)
    saved = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
    assert saved["health"]["consecutive_failures"] == 1

    with pytest.raises(ValueError, match="positive"):
        _replace_file_with_retry(tmp_path / "a", tmp_path / "b", attempts=0)
    with pytest.raises(ValueError, match="object"):
        _stored_order_view("bad")
    view = _account_order_view(
        cast(
            Any,
            SimpleNamespace(
                market="SPOT",
                client_order_id="client",
                symbol="BTCUSDT",
                remaining_quantity=Decimal("1"),
            ),
        )
    )
    assert view.client_order_id == "SPOT:client"
    invalid = tmp_path / "bad.lock"
    invalid.write_text(json.dumps({"schema_version": 2}), encoding="ascii")
    with pytest.raises(RuntimeError, match="invalid"):
        SingleInstanceLease._read_lock_owner(invalid)
    legacy = tmp_path / "legacy.lock"
    legacy.write_text(str(os.getpid()), encoding="ascii")
    assert SingleInstanceLease.lock_owner_is_active(legacy) is True
    monkeypatch.setattr(
        SingleInstanceLease,
        "_pid_is_alive",
        staticmethod(lambda _pid: False),
    )
    assert SingleInstanceLease.lock_owner_is_active(legacy) is False


def test_binance_usdm_client_error_and_parser_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="official HTTPS"):
        UsdMFuturesPublicTransport(base_url="http://example.com")
    transport = UsdMFuturesPublicTransport(sleeper=lambda _seconds: None)
    assert transport._delay(1, "2.5") == 2.5
    assert transport._delay(1, "bad") == 0.25
    with pytest.raises(ValueError, match="approved"):
        transport.get_json("/fapi/v1/private")

    class RetryTransport(UsdMFuturesPublicTransport):
        calls = 0

        def _request_once(self, url: str, path: str) -> object:
            del url, path
            self.calls += 1
            raise HTTPError("url", 429, "too many", Message(), None)

    with pytest.raises(ExchangeHttpError):
        RetryTransport(max_attempts=1, sleeper=lambda _seconds: None).get_json(
            "/fapi/v1/openInterest"
        )

    class BadTransport:
        def get_json(self, path: str, params: object | None = None) -> object:
            del path, params
            return {"bids": [["1", "0"]], "asks": [["1", "0"]]}

    client = BinanceUsdMClient(BadTransport(), clock=lambda: NOW)
    with pytest.raises(ExchangePayloadError, match="positive"):
        client.order_book_imbalance("btcusdt")
    with pytest.raises(ValueError, match="aggregate-trade"):
        client.large_aggregate_trades("BTCUSDT", limit=0)
    with pytest.raises(ExchangePayloadError, match="boolean"):
        BinanceUsdMClient(
            cast(
                Any,
                SimpleNamespace(
                    get_json=lambda *_args, **_kwargs: [
                        {"p": "10", "q": "1", "m": "bad", "T": 1}
                    ]
                ),
            ),
            clock=lambda: NOW,
        ).large_aggregate_trades("BTCUSDT", minimum_notional=Decimal("1"))
    point = client.liquidation_event(
        {"E": 1, "o": {"s": "btcusdt", "ap": "0", "p": "10", "q": "2", "S": "BUY"}}
    )
    assert point.metric is DerivativesMetric.LIQUIDATION_NOTIONAL
    with pytest.raises(ExchangePayloadError, match="timestamp"):
        BinanceUsdMClient._timestamp(True, "time")
    with pytest.raises(ExchangePayloadError, match="decimal-compatible"):
        BinanceUsdMClient._decimal(object(), "value")


def test_mcp_evidence_gateway_degraded_and_validation_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative"):
        EvidenceSource("x", Path("..") / "x.json", "at", timedelta(seconds=1), ("a",))
    with pytest.raises(ValueError, match="unique"):
        EvidenceSource("x", Path("x.json"), "at", timedelta(seconds=1), ("a", "a"))
    with pytest.raises(ValueError, match="promote"):
        EvidenceEnvelope(
            "x",
            NOW,
            "x",
            SHA,
            FreshnessStatus.FRESH,
            (),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="blockers"):
        EvidenceEnvelope("x", NOW, "x", SHA, FreshnessStatus.STALE, ())

    source = EvidenceSource(
        "quality",
        Path("quality.json"),
        "finished_at",
        timedelta(seconds=1),
        ("finished_at", "blockers", "execution_allowed", "live_eligibility_status"),
    )
    gateway = EvidenceGateway(tmp_path, clock=lambda: NOW)
    missing = gateway.read(source)
    assert missing.freshness_status is FreshnessStatus.MISSING
    target = tmp_path / "quality.json"
    target.write_text("[1]", encoding="utf-8")
    assert gateway.read(source).blockers == ("EVIDENCE_SCHEMA_INVALID",)
    target.write_text(
        json.dumps(
            {
                "finished_at": (NOW - timedelta(seconds=5)).isoformat(),
                "blockers": ["A"],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    stale = gateway.read(source)
    assert stale.freshness_status is FreshnessStatus.STALE
    target.write_text(
        json.dumps(
            {
                "finished_at": NOW.isoformat(),
                "blockers": [" "],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    assert gateway.read(source).blockers == ("EVIDENCE_BLOCKERS_INVALID",)
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceGateway(tmp_path, clock=lambda: datetime(2026, 1, 1)).health_check()
    assert EvidenceGateway._aggregate_freshness({FreshnessStatus.FRESH}) is (
        FreshnessStatus.FRESH
    )


def test_cli_accounting_failure_and_status_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        runtime_state_path=tmp_path / "runtime.json",
        binance_accounting_directory=tmp_path / "accounting",
    )

    class BlockingLease:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> BlockingLease:
            raise RuntimeError("already active")

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setattr(cli_accounting, "SingleInstanceLease", BlockingLease)
    assert (
        cli_accounting._run_locked_accounting_daemon(
            "accounting",
            settings,
            lambda: 0,
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["blockers"] == [
        "ACCOUNTING_DAEMON_ALREADY_ACTIVE"
    ]
    settings.runtime_cycle_interval_seconds = 100.0
    assert cli_accounting._accounting_daemon_backoff_seconds(settings, 3) == 300.0
    payload = cli_accounting._accounting_daemon_failure_payload(
        "accounting",
        ExchangeError("offline"),
        consecutive_failures=3,
        next_retry_seconds=None,
        circuit_open=True,
    )
    assert payload["status"] == "CIRCUIT_OPEN"
    with pytest.raises(ValueError, match="positive"):
        cli_accounting.accounting_collect_daemon(settings, max_cycles=0)
    missing = cli_accounting.latest_reconciliation_status(tmp_path / "missing.jsonl")
    assert missing["blockers"] == ("RECONCILIATION_RESULTS_MISSING",)
    reconciliation = tmp_path / "reconciliation.jsonl"
    reconciliation.write_text("not-json\n{}\n", encoding="utf-8")
    assert cli_accounting.latest_reconciliation_status(reconciliation)["blockers"] == (
        "RECONCILIATION_RESULT_MALFORMED",
    )


def test_execution_authorization_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MARKET"):
        _authorization(order_type="MARKET", price=Decimal("1"), time_in_force=None)
    with pytest.raises(ValueError, match="fields"):
        ExecutionAuthorizationEnvelope.from_payload({"authorization_id": "only"})
    envelope = _authorization()
    command = envelope.to_spot_order_command()
    mismatched = replace(command, quantity=Decimal("2"), price=Decimal("101"))
    blockers = envelope.blockers_for(mismatched, observed_at=NOW - timedelta(seconds=1))
    assert "EXECUTION_AUTHORIZATION_NOT_YET_VALID" in blockers
    assert "EXECUTION_AUTHORIZATION_QUANTITY_MISMATCH" in blockers
    expired = envelope.blockers_for(command, observed_at=NOW + timedelta(minutes=10))
    assert expired == ("EXECUTION_AUTHORIZATION_EXPIRED",)
    with pytest.raises(ValueError, match="authority"):
        ExecutionAuthorizationConsumption(
            "auth",
            "nonce",
            SHA,
            SHA,
            "execution",
            NOW,
            execution_allowed=True,
        )
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "auth.sqlite")
    ledger.claim(envelope, execution_id="execution-1", claimed_at=NOW)
    with pytest.raises(ExecutionAuthorizationAlreadyConsumedError):
        ledger.claim(envelope, execution_id="execution-2", claimed_at=NOW)
    assert ledger.is_consumed("auth-1") is True


def test_historical_replay_helper_edges() -> None:
    class DuplicateMarketMapping:
        def items(self) -> tuple[tuple[VirtualMarket | str, int], ...]:
            return ((cast(Any, "SPOT"), 1), (VirtualMarket.SPOT, 2))

    with pytest.raises(ValueError, match="duplicate"):
        replay_eval._normalize_market_mapping(
            cast(Mapping[VirtualMarket | str, int], DuplicateMarketMapping())
        )
    assert (
        replay_eval._normalize_market_mapping({"spot": "ok"})[VirtualMarket.SPOT]
        == "ok"
    )
    day = datetime(2026, 9, 16, tzinfo=UTC)
    curve = HistoricalMarketEquityCurve(
        VirtualMarket.SPOT,
        (
            DailyEquityPoint(day, Decimal("100")),
            DailyEquityPoint(day + timedelta(days=1), Decimal("90")),
            DailyEquityPoint(day + timedelta(days=2), Decimal("120")),
        ),
    )
    assert replay_eval._counterfactual_equity_curve(curve, ()) == curve.points
    assert replay_eval._average(()) is None
    assert replay_eval._ratio(1, 0) == Decimal("0")
    assert replay_eval._bounded_ratio(Decimal("2"), Decimal("1")) == Decimal("1")
    assert replay_eval._max_drawdown_usdt(curve.points) == Decimal("10")
    assert replay_eval._drawdown_duration(curve.points) == 86_400
    assert replay_eval._portfolio_utilization(
        VirtualMarket.SPOT,
        cast(Any, SimpleNamespace(equity_usdt=Decimal("100"), cash_usdt=Decimal("25"))),
    ) == Decimal("0.75")
    assert replay_eval._portfolio_utilization(
        VirtualMarket.USD_M_FUTURES,
        cast(Any, SimpleNamespace(margin_utilization_ratio=None)),
    ) == Decimal("0")


def test_enterprise_prompt_and_review_fail_closed_edges() -> None:
    identity = WorkflowIdentity("wo", "run", "trace", NOW)
    with pytest.raises(ValueError, match="restricted"):
        PromptAccessDecision(
            PromptAccessStatus.ALLOWED,
            DepartmentId.EXECUTIVE_OFFICE,
            "GeneralManagerController",
            "prompt",
            PromptVisibility.GENERAL_MANAGER_ONLY,
            ("WRONG",),
        )
    intake = ExecutivePromptIntake.from_raw_prompt(
        identity=identity,
        prompt_id="prompt",
        submitted_by="operator",
        raw_prompt="Apply deterministic coverage remediation.",
    )
    blocked = PromptAccessPolicy(
        build_default_department_registry()
    ).authorize_raw_prompt(
        actor_department_id=DepartmentId.SOFTWARE_ENGINEERING,
        actor_role="SoftwareDepartmentManager",
        intake=intake,
    )
    assert blocked.status is PromptAccessStatus.BLOCKED
    for kwargs, match in (
        ({"review_id": " "}, "identity"),
        ({"evidence_refs": ("a", "a")}, "unique"),
        ({"outcome": ReviewOutcome.PAPER_SOAK_CANDIDATE}, "outside cadence"),
        ({"production_mutation_allowed": True}, "mutate production"),
        ({"promotion_status": "LIVE"}, "promote production"),
    ):
        values = {
            "identity": identity,
            "review_id": "review-1",
            "cadence": ReviewCadence.MONTHLY,
            "owner_department_id": DepartmentId.SOFTWARE_ENGINEERING,
            "subject_ref": "subject",
            "outcome": ReviewOutcome.NO_CHANGE,
            "evidence_refs": ("evidence",),
        }
        values.update(kwargs)
        with pytest.raises(ValueError, match=match):
            PeriodicReviewRecord(**values)  # type: ignore[arg-type]


def test_blocker_reduction_regime_and_price_action_edges() -> None:
    with pytest.raises(ValueError, match="unique"):
        VirtualBlockerReduction(
            ("A", "A"),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            ("A",),
            ("A",),
            (),
            1,
        )
    with pytest.raises(ValueError, match="stage order"):
        VirtualBlockerReduction(
            (),
            ("B",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("A",),
            (),
            ("A",),
            1,
        )
    router = DeterministicRegimeRouter()
    assert router.decide({}).regime is RoutedMarketRegime.UNKNOWN
    assert (
        router._decimal_metadata(
            _agent("x", 0, metadata={"atr_ratio": True}),
            "atr_ratio",
        )
        is None
    )
    transition = router.decide(
        {"market_regime": _agent("market_regime", 0.1, metadata={"atr_ratio": "0.5"})}
    )
    assert transition.wait_reason == "REGIME_ROUTE_WAIT_TRANSITION"
    sell_candidate = replace(
        _candidate(
            Action.SELL,
            inventory_action="REDUCE_EXISTING_SPOT_INVENTORY",
        ),
        market_type="Spot",
        inventory_action="REDUCE_EXISTING_SPOT_INVENTORY",
    )
    routed = router.route_candidate(
        _snapshot(inventory=False),
        sell_candidate,
        strategy_id="BREAKOUT_RETEST",
        decision=router.decide(
            {
                "market_regime": _agent(
                    "market_regime",
                    -0.8,
                    metadata={"regime": "STRONG_DOWNTREND"},
                )
            }
        ),
    )
    assert "REGIME_ROUTE_SPOT_DEFENSIVE_CASH" in routed.blockers

    engine = PriceActionPlaybookEngine()
    results = {
        "trend": _agent("trend", -1),
        "market_structure": _agent("market_structure", -1),
        "multi_timeframe": _agent("multi_timeframe", -1),
        "confluence": _agent("confluence", 1),
        "price_action": _agent("price_action", 1, setups=("pullback_continuation",)),
    }
    assert engine.generate(_snapshot(), results) == ()
    sell_results = {
        "trend": _agent("trend", -1),
        "market_structure": _agent("market_structure", -1),
        "multi_timeframe": _agent("multi_timeframe", -1),
        "confluence": _agent("confluence", -1),
        "price_action": _agent("price_action", -1, setups=("resistance_rejection",)),
    }
    spot_sell = engine.generate(_snapshot(inventory=False), sell_results)
    assert spot_sell[0].inventory_action == "REDUCE_EXISTING_SPOT_INVENTORY"
    assert "INVENTORY_UNKNOWN_FOR_SPOT_SELL" in spot_sell[0].blockers


def test_tuning_promotion_and_tournament_private_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identity"):
        HumanApproval(" ", "approver", NOW, "report", ParameterSet("p", (("x", 1.0),)))
    with pytest.raises(ValueError, match="live"):
        HumanApproval(
            "approval",
            "approver",
            NOW,
            "report",
            ParameterSet("p", (("x", 1.0),)),
            ValidationStatus.LIVE_ELIGIBLE,
        )
    with pytest.raises(ValueError, match="identity"):
        StrategyPromotionTarget(" ", "1", "hash")
    store = GovernedParameterStore(tmp_path / "parameters.json", trace_journal=None)
    assert store.current_revision() == 0
    (tmp_path / "parameters.json").write_text(
        json.dumps({"revision": 0}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="revision"):
        store.current_revision()

    tournament = StrategyParameterTournament()
    with pytest.raises(ValueError, match="context"):
        tournament.run(
            contexts=(),
            candidates=(
                StrategyProfileCandidate("p", ParameterSet("p", (("x", 1.0),))),
            ),
            strategy_factory=lambda _params: lambda _history: None,
            regime_classifier=lambda _candle: MarketRegime.TREND,
            config=TournamentConfig(WalkForwardConfig(4, 2, 2)),
        )
    assert tournament._worst_stress_ratio((), 1.0) == 0.0
    assert tournament._worst_stress_ratio((("base", 1.0),), 0.0) == 0.0
    assert tournament._average_r(()) == 0.0
    assert tournament._tail_loss(()) == 0.0
    assert tournament._sortino(()) is None

    class Robustness:
        parameter_switch_rate = 0.25

    evaluation = cast(
        TournamentContextEvaluation,
        SimpleNamespace(
            walk_forward_report=SimpleNamespace(
                robustness=Robustness(),
                regime_performance=(),
                blockers=(),
            ),
            robustness_blockers=(),
            stress_net_returns=(),
            context=SimpleNamespace(symbol="BTCUSDT", timeframe="1h"),
        ),
    )
    assert tournament._parameter_stability((evaluation,)) == 0.75
    entry = cast(
        TournamentEntry,
        SimpleNamespace(
            blockers=(),
            net_return_after_costs=1.0,
            profit_factor=None,
            expectancy=0.1,
            max_drawdown=0.2,
            sharpe=None,
            sortino=None,
            average_r=0.0,
            tail_loss=-1.0,
            parameter_stability=1.0,
            profile_id="p",
        ),
    )
    assert tournament._ranking_key(entry)[0] is False


def test_application_research_preflight_system_and_risk_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="blocked"):
        research_app.ResearchStage(
            "stage",
            research_app.ResearchStageStatus.BLOCKED,
            (),
        )
    with pytest.raises(ValueError, match="live blocked"):
        research_app.ResearchWorkflowResult(
            analysis=object(),
            market_outlook=object(),
            stages=(),
            live_eligibility_status="READY",
        )
    with pytest.raises(ValueError, match="wallet capture"):
        research_app.ResearchApplicationService(
            object(),
            object(),
            lambda value: value,
            wallet_capture_enabled=True,
        )
    assert research_app._has_external_evidence({"source_count": 1}) is True
    assert research_app._canonical_sha256(lambda value: value, {"b": 1}) == (
        research_app._canonical_sha256(lambda value: value, {"b": 1})
    )

    with pytest.raises(ValueError, match="unique"):
        CapabilityPreflightDecision("cap", False, ("A", "A"))
    with pytest.raises(ValueError, match="skip"):
        CapabilityPreflightDecision("cap", True, ("A",))
    plan = CapabilityPreflightPlan(
        CapabilityPreflightMode.STANDARD,
        (CapabilityPreflightDecision("cap", True),),
    )
    assert plan.scheduled_ids == ("cap",)
    with pytest.raises(ValueError, match="membership"):
        CapabilityBundlePreflightDecision("bundle", (), ())
    bundle_plan = CapabilityBundlePreflightPlan(
        (CapabilityBundlePreflightDecision("bundle", ("cap",), ()),)
    )
    assert bundle_plan.scheduled_bundle_ids == ("bundle",)

    preview = system_report._auto_learn_preview(None)
    engine = cast(dict[str, str], preview["engine"])
    assert engine["provider"] == "llama.cpp"
    assert system_report._safe_component("x", lambda: "bad")["blockers"] == (
        "X_PAYLOAD_INVALID",
    )

    def unavailable_component() -> object:
        raise ValueError("bad")

    assert system_report._safe_component("x", unavailable_component)["blockers"] == (
        "X_UNAVAILABLE",
    )
    assert system_report._component_blockers({"a": {"blockers": "ONE"}}) == ("a:ONE",)
    parsed = system_report._parse_datetime("2026-01-01T00:00:00")
    assert parsed is not None
    assert parsed.tzinfo is UTC
    assert system_report._safe_int(True) is None
    assert system_report._as_sequence("x") == ("x",)

    with pytest.raises(ValueError, match="non-negative"):
        RiskRewardGatePolicy(minimum_rr=Decimal("-1"))
    with pytest.raises(ValueError, match="<= one"):
        RiskRewardGatePolicy(maximum_single_opportunity_pct=Decimal("2"))
    with pytest.raises(ValueError, match="symbol"):
        RiskRewardGateInput(
            CapitalMarket.SPOT,
            " ",
            Decimal("1"),
            Decimal("0"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="disagree"):
        RiskRewardGateResult("BTCUSDT", True, ("BLOCKED",))
    futures = RiskRewardGate().evaluate(
        RiskRewardGateInput(
            CapitalMarket.USD_M_FUTURES,
            "btcusdt",
            Decimal("2"),
            Decimal("0.1"),
            Decimal("0.5"),
            futures_capital_pct=Decimal("0.2"),
            data_quality_ok=True,
            stop_valid=True,
            oos_confidence=Decimal("0.9"),
        )
    )
    assert futures.blockers == (
        "FUTURES_CAPITAL_LIMIT",
        "MARGIN_RESERVE_DEFICIT",
        "LIQUIDATION_RISK",
    )

"""Objective portfolio phase tests for proposal-only management layers."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.account import AccountSnapshotBuilder
from ai4binance.accounting import FileReconciliationSummary
from ai4binance.cli import main
from ai4binance.comparison import (
    OpportunityComparisonDecision,
    OpportunityComparisonEngine,
)
from ai4binance.execution import (
    ApprovalRequest,
    ApprovalStatus,
    LocalApprovalQueue,
    ManualActionProposal,
    ManualActionType,
)
from ai4binance.funding import (
    ConversionDecision,
    ConversionSource,
    LiquidityAndConversionAdvisor,
)
from ai4binance.markets import CapitalMarket
from ai4binance.portfolio import (
    AssetClassification,
    AssetClassifier,
    CurrentHoldingInput,
    CurrentHoldingReviewEngine,
    HoldingDecision,
    PortfolioOpportunity,
    RecoveryState,
    RiskRewardGate,
    RiskRewardGateInput,
    RiskRewardProfile,
    SpotBalance,
    WalletSnapshot,
)
from ai4binance.portfolio.futures import FuturesAccountSnapshot
from ai4binance.scanners import ScannerOrchestrator
from ai4binance.universe import (
    FuturesUniverseBuilder,
    SpotUniverseBuilder,
    UniverseMarket,
    UniverseSymbol,
)

NOW = datetime(2026, 7, 19, 12, tzinfo=UTC)


def profile(quality: str, rr: str, risk: str) -> RiskRewardProfile:
    return RiskRewardProfile(Decimal(quality), Decimal(rr), Decimal(risk))


def test_current_holding_review_treats_hot_and_other_assets_objectively() -> None:
    records = AssetClassifier().classify_spot_balances(
        (
            SpotBalance("HOT", Decimal("10000"), Decimal("0")),
            SpotBalance("SOL", Decimal("3"), Decimal("0")),
        ),
        prices_usdt={"HOT": Decimal("0.002"), "SOL": Decimal("150")},
    )
    by_asset = {item.asset: item for item in records}

    report = CurrentHoldingReviewEngine().review(
        (
            CurrentHoldingInput(
                "HOT",
                "HOTUSDT",
                by_asset["HOT"].classification,
                Decimal("20"),
                Decimal("0.04"),
                profile("40", "0.8", "65"),
                Decimal("80"),
            ),
            CurrentHoldingInput(
                "SOL",
                "SOLUSDT",
                by_asset["SOL"].classification,
                Decimal("450"),
                Decimal("0.90"),
                profile("72", "2.1", "35"),
                Decimal("75"),
            ),
        )
    )

    decisions = {item.asset: item for item in report.assessments}
    assert decisions["HOT"].recommended_action is HoldingDecision.CONVERSION_CANDIDATE
    assert decisions["HOT"].recovery_state is RecoveryState.LOW
    assert decisions["SOL"].recommended_action is HoldingDecision.HOLD_OPPORTUNITY
    assert decisions["SOL"].manual_approval_required is False
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_comparison_uses_free_cash_before_rotation() -> None:
    holding = (
        CurrentHoldingReviewEngine()
        .review(
            (
                CurrentHoldingInput(
                    "HOT",
                    "HOTUSDT",
                    AssetClassification.CONVERTIBLE,
                    Decimal("250"),
                    Decimal("0.5"),
                    profile("45", "0.9", "60"),
                    Decimal("80"),
                ),
            )
        )
        .assessments[0]
    )
    opportunity = PortfolioOpportunity(
        CapitalMarket.SPOT,
        "ETHUSDT",
        Decimal("100"),
        profile("80", "2.2", "40"),
    )

    comparison = OpportunityComparisonEngine().compare(
        holding=holding,
        opportunity=opportunity,
        free_cash_usdt=Decimal("120"),
    )

    assert comparison.decision is OpportunityComparisonDecision.USE_FREE_CASH_FIRST
    assert comparison.suggested_reduction_pct == Decimal("0")
    assert comparison.manual_approval_required is True
    assert comparison.execution_allowed is False


def test_opportunity_comparison_proposes_capped_rotation_when_cash_is_low() -> None:
    holding = (
        CurrentHoldingReviewEngine()
        .review(
            (
                CurrentHoldingInput(
                    "HOT",
                    "HOTUSDT",
                    AssetClassification.CONVERTIBLE,
                    Decimal("250"),
                    Decimal("0.5"),
                    profile("45", "0.9", "60"),
                    Decimal("80"),
                ),
            )
        )
        .assessments[0]
    )
    opportunity = PortfolioOpportunity(
        CapitalMarket.USD_M_FUTURES,
        "BTCUSDT",
        Decimal("100"),
        profile("80", "2.2", "40"),
    )

    comparison = OpportunityComparisonEngine().compare(
        holding=holding,
        opportunity=opportunity,
        free_cash_usdt=Decimal("5"),
    )

    assert (
        comparison.decision is OpportunityComparisonDecision.ROTATE_TO_NEW_OPPORTUNITY
    )
    assert comparison.suggested_reduction_pct == Decimal("0.20")
    assert comparison.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_conversion_advisor_ranks_usable_assets_and_rejects_dust() -> None:
    records = AssetClassifier().classify_spot_balances(
        (
            SpotBalance("HOT", Decimal("10000"), Decimal("0")),
            SpotBalance("DUST", Decimal("1"), Decimal("0")),
        ),
        prices_usdt={"HOT": Decimal("0.002"), "DUST": Decimal("0.1")},
    )
    by_asset = {item.asset: item for item in records}

    plan = LiquidityAndConversionAdvisor().review(
        free_quote_capital_usdt=Decimal("0"),
        sources=(
            ConversionSource(
                by_asset["DUST"],
                Decimal("90"),
                Decimal("5"),
                Decimal("100"),
            ),
            ConversionSource(
                by_asset["HOT"],
                Decimal("80"),
                Decimal("20"),
                Decimal("40"),
            ),
        ),
    )

    assert plan.candidates[0].asset == "HOT"
    assert plan.candidates[0].decision is ConversionDecision.CONVERSION_CANDIDATE
    assert plan.candidates[1].asset == "DUST"
    assert plan.candidates[1].decision is ConversionDecision.NOT_FUNDING_SOURCE
    assert "DUST_NOT_CONVERSION_SOURCE" in plan.candidates[1].blockers
    assert plan.execution_allowed is False


def test_manual_financial_actions_have_separate_pending_approvals() -> None:
    sell = ManualActionProposal(
        "act-hot-sell",
        ManualActionType.REDUCE_SPOT_HOLDING,
        "HOT",
        Decimal("50"),
        "Better risk-adjusted opportunity exists.",
        "Frees liquid quote capital.",
        "Slippage and opportunity reversal risk.",
    )
    buy = ManualActionProposal(
        "act-eth-buy",
        ManualActionType.PLACE_SPOT_ORDER,
        "ETHUSDT",
        Decimal("50"),
        "Use separately approved liquid capital.",
        "Opens reviewed Spot exposure.",
        "Entry and stop invalidation risk.",
    )
    sell_approval = ApprovalRequest(
        "approval-hot-sell",
        sell.action_id,
        sell.action_type,
    )
    buy_approval = ApprovalRequest("approval-eth-buy", buy.action_id, buy.action_type)

    assert sell.action_id != buy.action_id
    assert sell_approval.approval_id != buy_approval.approval_id
    assert sell.approval_status is ApprovalStatus.PENDING
    assert buy_approval.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert sell.execution_allowed is False
    assert buy.execution_allowed is False


def test_dynamic_spot_universe_filters_without_hot_hardcode() -> None:
    hot = UniverseSymbol(
        "HOTUSDT",
        UniverseMarket.SPOT,
        "HOT",
        "USDT",
        "TRADING",
        Decimal("5"),
        Decimal("2000000"),
        Decimal("10"),
        Decimal("50000"),
    )
    weak = UniverseSymbol(
        "ABCUSDT",
        UniverseMarket.SPOT,
        "ABC",
        "USDT",
        "TRADING",
        Decimal("5"),
        Decimal("100"),
        Decimal("120"),
        Decimal("10"),
    )

    results = SpotUniverseBuilder().filter((hot, weak))

    assert results[0].accepted is True
    assert results[0].symbol.symbol == "HOTUSDT"
    assert results[0].execution_allowed is False
    assert results[1].accepted is False
    assert "INSUFFICIENT_24H_VOLUME" in results[1].blockers
    assert "SPREAD_EXCEEDS_LIMIT" in results[1].blockers


def test_dynamic_futures_universe_keeps_margin_and_funding_separate() -> None:
    accepted = UniverseSymbol(
        "BTCUSDT",
        UniverseMarket.USD_M_FUTURES,
        "BTC",
        "USDT",
        "TRADING",
        Decimal("5"),
        Decimal("10000000"),
        Decimal("5"),
        Decimal("100000"),
        contract_type="PERPETUAL",
        margin_asset="USDT",
        open_interest_usdt=Decimal("50000000"),
        funding_rate=Decimal("0.0001"),
    )
    blocked = UniverseSymbol(
        "ETHBUSD",
        UniverseMarket.USD_M_FUTURES,
        "ETH",
        "BUSD",
        "TRADING",
        Decimal("5"),
        Decimal("10000000"),
        Decimal("5"),
        Decimal("100000"),
        contract_type="CURRENT_QUARTER",
        margin_asset="BUSD",
        open_interest_usdt=Decimal("100"),
        funding_rate=Decimal("0.05"),
    )

    results = FuturesUniverseBuilder().filter((accepted, blocked))

    assert results[0].accepted is True
    assert results[0].live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert results[1].accepted is False
    assert "CONTRACT_NOT_PERPETUAL" in results[1].blockers
    assert "MARGIN_ASSET_NOT_ALLOWED" in results[1].blockers
    assert "FUNDING_RATE_OUT_OF_POLICY" in results[1].blockers


def test_risk_reward_gate_blocks_low_margin_and_weak_evidence() -> None:
    result = RiskRewardGate().evaluate(
        RiskRewardGateInput(
            CapitalMarket.USD_M_FUTURES,
            "BTCUSDT",
            Decimal("1.2"),
            Decimal("0.05"),
            Decimal("0.12"),
            futures_capital_pct=Decimal("0.08"),
            futures_available_margin_pct=Decimal("0.25"),
            liquidation_distance_pct=Decimal("0.03"),
            oos_confidence=Decimal("0.2"),
            data_quality_ok=True,
            stop_valid=True,
        )
    )

    assert result.accepted is False
    assert "INSUFFICIENT_RR" in result.blockers
    assert "MARGIN_RESERVE_DEFICIT" in result.blockers
    assert "LIQUIDATION_RISK" in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_account_snapshot_binds_rest_state_to_reconciliation_blockers() -> None:
    wallet = WalletSnapshot(
        NOW,
        "SPOT",
        True,
        (
            SpotBalance("HOT", Decimal("10"), Decimal("0")),
            SpotBalance("USDT", Decimal("20"), Decimal("5")),
        ),
        "HOTUSDT",
    )
    futures = FuturesAccountSnapshot(
        NOW,
        "BTCUSDT",
        True,
        Decimal("100"),
        Decimal("60"),
        (),
    )
    reconciliation = FileReconciliationSummary(
        1,
        0,
        ("SPOT_WEBSOCKET_EVIDENCE_MISSING_OR_STALE",),
    )

    snapshot = AccountSnapshotBuilder().build(
        snapshot_id="account-1",
        data_as_of=NOW,
        spot_wallet=wallet,
        futures_account=futures,
        prices_usdt={"HOT": Decimal("2")},
        reconciliation=reconciliation,
    )

    assert snapshot.spot_value_usdt == Decimal("45")
    assert snapshot.futures_equity_usdt == Decimal("100")
    assert snapshot.reconciliation_status == "DEGRADED"
    assert "SPOT_WEBSOCKET_EVIDENCE_MISSING_OR_STALE" in snapshot.blockers
    assert snapshot.execution_allowed is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_local_approval_queue_is_persistent_and_idempotent(tmp_path: Path) -> None:
    queue = LocalApprovalQueue(tmp_path / "approvals.jsonl")
    action = ManualActionProposal(
        "act-hot-convert",
        ManualActionType.CONVERT_ASSET,
        "HOT",
        Decimal("25"),
        "HOT is weaker than the selected opportunity.",
        "Frees liquid quote capital after manual review.",
        "Slippage and reversal risk.",
    )

    first = queue.enqueue(action, approval_id="approval-hot-convert", created_at=NOW)
    second = queue.enqueue(action, approval_id="ignored", created_at=NOW)

    assert first.approval.approval_id == "approval-hot-convert"
    assert second.approval.approval_id == "approval-hot-convert"
    assert len(queue.records()) == 1
    assert queue.records()[0].action.execution_allowed is False


def test_scanner_orchestrator_fails_closed_without_input() -> None:
    report = ScannerOrchestrator().scan_all(spot_symbols=(), futures_symbols=())

    assert report.accepted_symbols == ()
    assert report.rejected_symbols == ()
    assert report.blockers == ("SCANNER_INPUT_UNAVAILABLE",)
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_scan_cli_commands_are_available_and_blocked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["/scan", "spot"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "scan-spot"
    assert payload["status"] == "BLOCKED"
    assert payload["rejected_symbols"] == ["HOTUSDT"]
    assert "INSUFFICIENT_24H_VOLUME" in payload["blockers"]
    assert "DATA_INCOMPLETE" in payload["blockers"]
    assert payload["execution_allowed"] is False

    assert main(["scan", "spot"]) == 2
    alias_payload = json.loads(capsys.readouterr().out)
    assert alias_payload["command"] == "scan-spot"
    assert alias_payload["rejected_symbols"] == ["HOTUSDT"]
    assert alias_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_approvals_cli_reads_persistent_queue(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "approvals.jsonl"
    queue = LocalApprovalQueue(queue_path)
    queue.enqueue(
        ManualActionProposal(
            "act-1",
            ManualActionType.REDUCE_SPOT_HOLDING,
            "HOT",
            Decimal("10"),
            "Manual reduction review.",
            "May reduce concentration.",
            "Manual approval can still be rejected.",
        ),
        approval_id="approval-1",
        created_at=NOW,
    )
    monkeypatch.setenv("AI4BINANCE_MANUAL_APPROVAL_QUEUE_PATH", str(queue_path))

    assert main(["approvals"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["approvals"][0]["approval_id"] == "approval-1"
    assert payload["approvals"][0]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["execution_allowed"] is False

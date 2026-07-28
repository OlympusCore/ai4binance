"""Read-only wallet and controlled-learning boundary tests."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.execution.lifecycle import (
    LifecyclePosition,
    PaperClosureReview,
    PositionStatus,
    StagedExitPlan,
)
from ai4binance.execution.paper import ExitReason
from ai4binance.learning import ControlledLearningEngine, LearningStore
from ai4binance.portfolio import WalletSnapshotService
from ai4binance.storage import DestinationVerificationError

NOW = datetime(2026, 4, 1, tzinfo=UTC)


class StubAccountReader:
    def account(self) -> object:
        return {
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": "HOT", "free": "10", "locked": "2"},
                {"asset": "USDT", "free": "100", "locked": "0"},
            ],
        }

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return [
            {
                "orderId": 1,
                "clientOrderId": "spot-1",
                "symbol": symbol,
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "0.001",
                "origQty": "100",
                "executedQty": "0",
            }
        ]


def test_wallet_service_normalizes_read_only_account_snapshot() -> None:
    snapshot = WalletSnapshotService(StubAccountReader()).capture("hotusdt", NOW)

    assert snapshot.symbol == "HOTUSDT"
    assert snapshot.account_status == "SPOT"
    assert snapshot.can_trade is True
    assert snapshot.open_order_count == 1
    assert snapshot.open_orders[0].client_order_id == "spot-1"
    hot_balance = snapshot.balance("hot")
    assert hot_balance is not None
    assert hot_balance.free == Decimal("10")
    assert not hasattr(StubAccountReader(), "create_order")


class InvalidAccountReader:
    def account(self) -> object:
        return {"accountType": "SPOT", "canTrade": True, "balances": "invalid"}

    def open_orders(self, symbol: str | None = None) -> object:
        return []


def test_wallet_service_rejects_invalid_private_payload() -> None:
    with pytest.raises(ValueError, match="balances must be an array"):
        WalletSnapshotService(InvalidAccountReader()).capture("HOTUSDT", NOW)


def closed_position() -> LifecyclePosition:
    review = PaperClosureReview(
        exit_reason=ExitReason.TRAILING_STOP_EXIT,
        lifecycle_error=None,
        stop_quality="PROTECTIVE",
        trailing_quality="PROTECTIVE",
        ignored_signals=1,
        htf_weakness=True,
        volatility_expansion=False,
        level_break=True,
        staged_exit_alternative="NOT_USED_REVIEW",
        lesson_candidate="REVIEW_PREMATURE_TRAILING",
    )
    return LifecyclePosition(
        position_id="paper:1",
        candidate_id="candidate-1",
        symbol="HOTUSDT",
        opened_at=NOW,
        entry_price=Decimal("100"),
        entry_fee_usdt=Decimal("0.1"),
        initial_quantity=Decimal("1"),
        remaining_quantity=Decimal("0"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("102"),
        atr=Decimal("2"),
        plan=StagedExitPlan((Decimal("110"),), (Decimal("1"),)),
        status=PositionStatus.CLOSED,
        closure_review=review,
    )


def test_learning_ranks_lessons_without_execution_or_risk_authority() -> None:
    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        paper_positions=(closed_position(), closed_position()),
    )

    assert summary.lessons[0].code == "REVIEW_PREMATURE_TRAILING"
    assert summary.lessons[0].evidence_count == 2
    assert summary.experiments[0].rank == 1
    assert summary.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert summary.execution_allowed is False
    assert summary.risk_change_allowed is False


def test_learning_store_writes_atomic_summary_and_append_only_audit(
    tmp_path: Path,
) -> None:
    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        paper_positions=(closed_position(),),
    )
    store = LearningStore(
        tmp_path / "learning_summary.json",
        tmp_path / "learning_events.jsonl",
    )
    store.save(summary)

    persisted = json.loads(store.summary_path.read_text(encoding="utf-8"))
    audit = json.loads(store.audit_path.read_text(encoding="utf-8"))
    assert persisted["summary_id"] == summary.summary_id
    assert audit["event_type"] == "LEARNING_SUMMARY_CREATED"


def test_learning_store_stops_when_summary_read_back_is_tampered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = ControlledLearningEngine().analyze(
        created_at=NOW,
        paper_positions=(closed_position(),),
    )
    store = LearningStore(
        tmp_path / "learning_summary.json",
        tmp_path / "learning_events.jsonl",
    )
    original = Path.read_text

    def tampered_read_text(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        payload = original(self, encoding, errors)
        return (
            payload.replace(summary.summary_id, "other-summary")
            if self == store.summary_path
            else payload
        )

    monkeypatch.setattr(Path, "read_text", tampered_read_text)
    with pytest.raises(DestinationVerificationError, match="LEARNING_SUMMARY"):
        store.save(summary)


def test_empty_learning_evidence_is_deterministic() -> None:
    first = ControlledLearningEngine().analyze(created_at=NOW)
    second = ControlledLearningEngine().analyze(created_at=NOW)

    assert first == second
    assert first.lessons == ()
    assert first.experiments == ()

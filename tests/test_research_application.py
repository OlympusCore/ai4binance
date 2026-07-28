"""End-to-end contract tests for the safe research application service."""

import json
from pathlib import Path

import pytest
from test_cli import public_snapshot

from ai4binance.application import (
    ResearchApplicationService,
    ResearchStage,
    ResearchStageStatus,
    ResearchWorkflowResult,
)
from ai4binance.application.learning_loop import ControlledLearningLoop
from ai4binance.learning.storage import LearningStore
from ai4binance.portfolio.wallet import WalletSnapshotService
from ai4binance.storage import JsonlAuditStore


def test_research_service_runs_all_safe_stages_and_persists_audit(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "research.jsonl"
    workflow = ResearchApplicationService(audit_store=JsonlAuditStore(audit_path)).run(
        public_snapshot()
    )

    assert workflow.analysis.snapshot_id == "public-snapshot-1"
    assert workflow.market_outlook.snapshot_id == "public-snapshot-1"
    assert workflow.market_outlook.execution_allowed is False
    assert [stage.name for stage in workflow.stages] == [
        "acquisition",
        "analysis",
        "strategy",
        "risk",
        "paper",
        "learning",
    ]
    assert workflow.stages[-2].status is ResearchStageStatus.BLOCKED
    assert workflow.stages[-1].status is ResearchStageStatus.NOT_RUN
    assert workflow.execution_allowed is False
    assert workflow.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    event = json.loads(audit_path.read_text(encoding="utf-8"))
    assert event["event_type"] == "RESEARCH_WORKFLOW_COMPLETED"
    assert event["payload"]["execution_allowed"] is False


def test_research_service_publishes_read_only_market_outlook(tmp_path: Path) -> None:
    from ai4binance.outlook import MarketOutlookArtifactStore

    path = tmp_path / "market-outlook" / "state.json"
    workflow = ResearchApplicationService(
        outlook_store=MarketOutlookArtifactStore(path)
    ).run(public_snapshot())

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["snapshot_id"] == workflow.market_outlook.snapshot_id
    assert state["execution_allowed"] is False
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_research_contract_rejects_execution_authority() -> None:
    service_result = ResearchApplicationService().run(public_snapshot())
    with pytest.raises(ValueError, match="cannot grant execution"):
        ResearchWorkflowResult(
            analysis=service_result.analysis,
            market_outlook=service_result.market_outlook,
            stages=service_result.stages,
            execution_allowed=True,
        )


def test_blocked_stage_requires_explicit_blockers() -> None:
    with pytest.raises(ValueError, match="requires blockers"):
        ResearchStage("risk", ResearchStageStatus.BLOCKED)


def test_research_service_runs_idempotent_learning_when_configured(
    tmp_path: Path,
) -> None:
    service = ResearchApplicationService(
        learning_loop=ControlledLearningLoop(
            LearningStore(tmp_path / "learning.json", tmp_path / "learning.jsonl")
        )
    )

    first = service.run(public_snapshot())
    second = service.run(public_snapshot())

    assert first.learning is not None
    assert first.learning.saved is True
    assert second.learning is not None
    assert second.learning.saved is False
    assert first.stages[-1].status is ResearchStageStatus.COMPLETED
    assert first.execution_allowed is False


class _WalletReader:
    def account(self) -> object:
        return {
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": "HOT", "free": "12", "locked": "3"},
                {"asset": "USDT", "free": "100", "locked": "0"},
            ],
        }

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return []


def test_wallet_capture_requires_explicit_opt_in_and_attaches_inventory() -> None:
    with pytest.raises(ValueError, match="explicit wallet service"):
        ResearchApplicationService(wallet_capture_enabled=True)

    disabled = ResearchApplicationService(
        wallet_service=WalletSnapshotService(_WalletReader())
    ).run(public_snapshot())
    assert disabled.wallet is None
    assert disabled.analysis.market_snapshot.wallet_summary == {}

    enabled = ResearchApplicationService(
        wallet_service=WalletSnapshotService(_WalletReader()),
        wallet_capture_enabled=True,
    ).run(public_snapshot())
    assert enabled.wallet is not None
    assert enabled.analysis.market_snapshot.inventory_summary["quantity"] == "15"
    assert enabled.execution_allowed is False

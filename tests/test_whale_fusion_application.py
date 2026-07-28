"""WHALE-FUSION Phase 8 application pipeline tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import (
    WhaleFusionCycle,
    WhaleFusionResearchService,
    WhaleFusionWorkflowResult,
)
from ai4binance.schemas import AgentStatus, DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.whale_fusion import FusionAuditWriter, Provenance, SocialEventType
from ai4binance.whale_fusion.models import WhaleEventType
from ai4binance.whale_fusion.onchain import Chain, WhaleEvent
from ai4binance.whale_fusion.social import SocialEvent, SocialStance

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)
SOURCE = Provenance("APPLICATION_TEST", NOW, "https://application.example")


def snapshot() -> MarketSnapshot:
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(hours=offset),
            open=Decimal("1"),
            high=Decimal("1.1"),
            low=Decimal("0.9"),
            close=Decimal("1.05"),
            volume=Decimal("100"),
        )
        for offset in (2, 1)
    )
    return MarketSnapshot(
        snapshot_id="application-fusion-1",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": candles},
        latest_price=Decimal("1.05"),
        bid=Decimal("1.049"),
        ask=Decimal("1.051"),
        spread=Decimal("0.002"),
        exchange_filters={"PRICE_FILTER": {"tickSize": "0.001"}},
        data_freshness={"1h": {"stale": False}},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={"trading_status": "TRADING", "base_asset": "HOT"},
    )


def whale_event() -> WhaleEvent:
    return WhaleEvent(
        event_id="whale-event-1",
        event_type=WhaleEventType.TOKEN_ACCUMULATION,
        chain=Chain.ETHEREUM,
        timestamp=NOW,
        asset="HOT",
        amount=Decimal("100"),
        usd_value=Decimal("2000000"),
        transfer_ids=("transfer-1",),
        confidence=Decimal("0.8"),
        provenance=(SOURCE,),
        reason_codes=("TEST",),
    )


def social_event() -> SocialEvent:
    return SocialEvent(
        event_id="social-event-1",
        post_id="post-1",
        account_id="account-1",
        timestamp=NOW,
        event_type=SocialEventType.PROJECT_ANNOUNCEMENT,
        stance=SocialStance.SUPPORTIVE,
        assets=("HOT",),
        confidence=Decimal("0.7"),
        provenance=(SOURCE,),
        reason_codes=("TEST",),
    )


def cycle(*, with_evidence: bool = False) -> WhaleFusionCycle:
    return WhaleFusionCycle(
        snapshot_id="application-fusion-1",
        symbol="hotusdt",
        asset="hot",
        whale_events=(whale_event(),) if with_evidence else (),
        social_events=(social_event(),) if with_evidence else (),
    )


def service(path: Path | None = None) -> WhaleFusionResearchService:
    return WhaleFusionResearchService(
        orchestrator=EnterpriseOrchestrator(minimum_candles=2),
        audit_writer=FusionAuditWriter(path) if path is not None else None,
    )


def test_empty_cycle_remains_no_trade_with_explicit_blocker() -> None:
    result = service().run(snapshot(), cycle())
    assert "INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT" in result.blockers
    assert (
        result.analysis.agent_results["whale"].status is AgentStatus.INSUFFICIENT_DATA
    )
    assert result.analysis.final_decision is not None
    assert result.analysis.final_decision.execution_allowed is False
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_two_channel_cycle_runs_snapshot_bound_whale_agent() -> None:
    result = service().run(snapshot(), cycle(with_evidence=True))
    whale = result.analysis.agent_results["whale"]
    assert result.fusion.fusion_score > Decimal("90")
    assert whale.status is AgentStatus.PARTIAL
    assert whale.evidence == ("SNAPSHOT_BOUND_WHALE_FUSION",)
    assert result.audit_written is None


def test_cycle_identity_mismatch_fails_before_fusion() -> None:
    with pytest.raises(ValueError, match="IDs must match"):
        service().run(snapshot(), replace(cycle(), snapshot_id="other"))
    with pytest.raises(ValueError, match="symbols must match"):
        service().run(snapshot(), replace(cycle(), symbol="BTCUSDT"))


def test_audit_is_idempotent_and_corruption_becomes_blocker(tmp_path: Path) -> None:
    path = tmp_path / "fusion.jsonl"
    first = service(path).run(snapshot(), cycle(with_evidence=True))
    second = service(path).run(snapshot(), cycle(with_evidence=True))
    assert first.audit_written is True
    assert second.audit_written is False
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    path.write_text("invalid-json\n", encoding="utf-8")
    failed = service(path).run(snapshot(), cycle(with_evidence=True))
    assert failed.audit_written is False
    assert "FUSION_AUDIT_WRITE_FAILED" in failed.blockers
    assert failed.execution_allowed is False


def test_workflow_contract_cannot_enable_execution() -> None:
    result = service().run(snapshot(), cycle())
    with pytest.raises(ValueError, match="execution authority"):
        WhaleFusionWorkflowResult(
            snapshot_id=result.snapshot_id,
            fusion=result.fusion,
            analysis=result.analysis,
            audit_written=result.audit_written,
            blockers=result.blockers,
            execution_allowed=True,
        )


def test_cycle_and_workflow_identity_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="snapshot_id and asset"):
        WhaleFusionCycle("", "HOTUSDT", "HOT")
    with pytest.raises(ValueError, match="snapshot_id and asset"):
        WhaleFusionCycle("snapshot", "HOTUSDT", "")
    with pytest.raises(ValueError, match="symbol cannot be empty"):
        WhaleFusionCycle("snapshot", "", "HOT")

    result = service().run(snapshot(), cycle())
    with pytest.raises(ValueError, match="snapshot_id cannot be empty"):
        replace(result, snapshot_id="")
    with pytest.raises(ValueError, match="live blocked"):
        replace(result, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="must use the fusion snapshot"):
        replace(result, snapshot_id="different")

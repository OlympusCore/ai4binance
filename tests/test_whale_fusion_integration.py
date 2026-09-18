"""WHALE-FUSION Phase 7 snapshot, agent, orchestrator and audit tests."""

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.schemas import AgentStatus, DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.whale_fusion import (
    FusionAuditWriter,
    FusionChannel,
    FusionResult,
    WhaleFusionEnvelope,
    attach_fusion_result,
)
from ai4binance.whale_fusion.agent import WhaleFusionAgent, build_whale_fusion_agent

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)


def candle(hours_ago: int) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=NOW - timedelta(hours=hours_ago),
        open=Decimal("1"),
        high=Decimal("1.1"),
        low=Decimal("0.9"),
        close=Decimal("1.05"),
        volume=Decimal("100"),
    )


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id="fusion-snapshot-1",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": (candle(2), candle(1))},
        latest_price=Decimal("1.05"),
        bid=Decimal("1.049"),
        ask=Decimal("1.051"),
        spread=Decimal("0.002"),
        exchange_filters={"PRICE_FILTER": {"tickSize": "0.001"}},
        data_freshness={"1h": {"stale": False}},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={"trading_status": "TRADING"},
    )


def fusion_result(*, blockers: tuple[str, ...] = ()) -> FusionResult:
    return FusionResult(
        symbol="HOTUSDT",
        asset="HOT",
        as_of=NOW,
        fusion_score=Decimal("80"),
        direction_score=Decimal("0.6"),
        confidence=Decimal("0.7"),
        active_channels=(FusionChannel.ONCHAIN, FusionChannel.SOCIAL),
        contributions=(),
        contradiction_count=0,
        blockers=blockers,
    )


def envelope(*, blockers: tuple[str, ...] = ()) -> WhaleFusionEnvelope:
    return WhaleFusionEnvelope(
        snapshot_id="fusion-snapshot-1",
        symbol="HOTUSDT",
        result=fusion_result(blockers=blockers),
    )


def test_envelope_attaches_to_new_immutable_snapshot() -> None:
    original = snapshot()
    attached = attach_fusion_result(original, envelope())
    assert original.onchain_snapshot == {}
    raw_payload = attached.onchain_snapshot["whale_fusion"]
    assert isinstance(raw_payload, Mapping)
    payload = cast(Mapping[str, object], raw_payload)
    assert payload["snapshot_id"] == original.snapshot_id
    assert payload["fusion_score"] == "80"
    assert payload["execution_allowed"] is False


def test_envelope_rejects_cross_snapshot_symbol_and_future_data() -> None:
    with pytest.raises(ValueError, match="symbols must match"):
        WhaleFusionEnvelope("fusion-snapshot-1", "BTCUSDT", fusion_result())
    with pytest.raises(ValueError, match="snapshot IDs"):
        attach_fusion_result(
            snapshot(), replace(envelope(), snapshot_id="other-snapshot")
        )
    future = replace(fusion_result(), as_of=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="newer"):
        attach_fusion_result(
            snapshot(), WhaleFusionEnvelope("fusion-snapshot-1", "HOTUSDT", future)
        )


def test_whale_fusion_agent_returns_supplementary_partial_result() -> None:
    attached = attach_fusion_result(snapshot(), envelope())
    agent = WhaleFusionAgent(build_default_registry().get("whale"))
    result = agent.analyze(attached, {})
    assert result.status is AgentStatus.PARTIAL
    assert result.directional_vote == 0.6
    assert result.score == 80
    assert result.confidence == 0.7
    assert result.hard_gate_eligible is False
    assert "SUPPLEMENTARY_SPOT_EVIDENCE_ONLY" in result.warnings


def test_whale_fusion_agent_fails_closed_for_missing_fatal_and_authority_data() -> None:
    agent = WhaleFusionAgent(build_default_registry().get("whale"))
    missing = agent.analyze(snapshot(), {})
    assert missing.status is AgentStatus.INSUFFICIENT_DATA
    assert missing.blockers == ("WHALE_FUSION_SNAPSHOT_MISSING",)

    fatal_snapshot = attach_fusion_result(
        snapshot(), envelope(blockers=("INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT",))
    )
    fatal = agent.analyze(fatal_snapshot, {})
    assert fatal.status is AgentStatus.INSUFFICIENT_DATA
    assert "INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT" in fatal.blockers

    raw_payload = fatal_snapshot.onchain_snapshot["whale_fusion"]
    assert isinstance(raw_payload, Mapping)
    payload = dict(cast(Mapping[str, object], raw_payload))
    payload["execution_allowed"] = True
    unsafe = replace(fatal_snapshot, onchain_snapshot={"whale_fusion": payload})
    rejected = agent.analyze(unsafe, {})
    assert rejected.blockers == ("WHALE_FUSION_AUTHORITY_INVALID",)


def test_whale_fusion_agent_rejects_snapshot_symbol_promotion_and_future_data() -> None:
    agent = WhaleFusionAgent(build_default_registry().get("whale"))
    attached = attach_fusion_result(snapshot(), envelope())
    raw_payload = attached.onchain_snapshot["whale_fusion"]
    assert isinstance(raw_payload, Mapping)
    payload = dict(cast(Mapping[str, object], raw_payload))

    wrong_snapshot = replace(
        attached,
        onchain_snapshot={"whale_fusion": {**payload, "snapshot_id": "other"}},
    )
    assert agent.analyze(wrong_snapshot, {}).blockers == (
        "WHALE_FUSION_SNAPSHOT_ID_MISMATCH",
    )

    wrong_symbol = replace(
        attached,
        onchain_snapshot={"whale_fusion": {**payload, "symbol": "BTCUSDT"}},
    )
    assert agent.analyze(wrong_symbol, {}).blockers == ("WHALE_FUSION_SYMBOL_MISMATCH",)

    wrong_promotion = replace(
        attached,
        onchain_snapshot={
            "whale_fusion": {**payload, "promotion_status": "STAGED_CANDIDATE"}
        },
    )
    assert agent.analyze(wrong_promotion, {}).blockers == (
        "WHALE_FUSION_PROMOTION_INVALID",
    )

    from_future = replace(
        attached,
        onchain_snapshot={
            "whale_fusion": {
                **payload,
                "as_of": (NOW + timedelta(seconds=2)).isoformat(),
            }
        },
    )
    assert agent.analyze(from_future, {}).blockers == ("WHALE_FUSION_FROM_FUTURE",)


def test_whale_fusion_agent_parser_helpers_fail_closed() -> None:
    agent = WhaleFusionAgent(build_default_registry().get("whale"))
    assert agent._decimal(True) is None
    assert agent._decimal("not-a-number") is None
    assert agent._decimal("Infinity") is None
    assert agent._timestamp(123) is None
    assert agent._timestamp("not-a-date") is None
    assert agent._timestamp("2026-07-13T12:00:00") is None
    assert agent._strings("bad") == ()
    assert agent._strings(["ok", 1]) == ()

    attached = attach_fusion_result(snapshot(), envelope())
    raw_payload = attached.onchain_snapshot["whale_fusion"]
    assert isinstance(raw_payload, Mapping)
    payload = dict(cast(Mapping[str, object], raw_payload))
    invalid_payload = replace(
        attached,
        onchain_snapshot={"whale_fusion": {**payload, "direction_score": True}},
    )
    assert agent.analyze(invalid_payload, {}).blockers == (
        "WHALE_FUSION_PAYLOAD_INVALID",
    )


def test_whale_fusion_builder_returns_only_for_whale_definition() -> None:
    registry = build_default_registry()
    assert build_whale_fusion_agent(registry.get("whale")) is not None
    assert build_whale_fusion_agent(registry.get("trend")) is None


def test_orchestrator_uses_snapshot_bound_whale_fusion_agent() -> None:
    attached = attach_fusion_result(snapshot(), envelope())
    state = EnterpriseOrchestrator().analyze(attached)
    result = state.agent_results["whale"]
    assert result.status is AgentStatus.PARTIAL
    assert result.evidence == ("SNAPSHOT_BOUND_WHALE_FUSION",)
    assert state.final_decision is not None
    assert state.final_decision.execution_allowed is False


def test_fusion_audit_writer_is_restart_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fusion.jsonl"
    writer = FusionAuditWriter(path)
    assert writer.append(envelope()) is True
    assert writer.append(envelope()) is False
    assert FusionAuditWriter(path).append(envelope()) is False
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    item = json.loads(lines[0])
    assert item["event_type"] == "WHALE_FUSION_RESULT"
    assert item["payload"]["result"]["execution_allowed"] is False
    assert item["payload"]["result"]["promotion_status"] == "RESEARCH_ONLY"


def test_fusion_audit_writer_rejects_corrupted_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fusion.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        FusionAuditWriter(path).append(envelope())

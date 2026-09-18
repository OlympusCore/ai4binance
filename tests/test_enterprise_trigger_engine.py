from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.events import (
    EnterpriseEventTriggerEngine,
    TriggerDecision,
    TriggerEvent,
    is_binance_coin_research_symbol,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def test_market_research_universe_excludes_only_non_coin_token_classes() -> None:
    assert is_binance_coin_research_symbol("BTCUSDT") is True
    assert is_binance_coin_research_symbol("DOGEUSDT") is True
    assert is_binance_coin_research_symbol("HOTUSDT") is True
    assert is_binance_coin_research_symbol("USDCUSDT") is False
    assert is_binance_coin_research_symbol("WBTCUSDT") is False
    assert is_binance_coin_research_symbol("BTCUPUSDT") is False


def test_social_market_anomaly_starts_alert_without_execution() -> None:
    decision = EnterpriseEventTriggerEngine().evaluate(
        TriggerEvent.create(
            event_id="event-btc-social-volume-1",
            event_type="SOCIAL_VOLUME_SPIKE",
            domain="SOCIAL",
            entity="BTCUSDT",
            detected_at=NOW,
            source="verified-social-cluster",
            severity="0.65",
            confidence="0.70",
            relevance="0.90",
            freshness="1.00",
            evidence_count=3,
            dedup_key="BTCUSDT:SOCIAL_VOLUME_SPIKE:20260809T1200Z",
            payload={
                "source_tier": "verified_social",
                "mention_velocity": "0.90",
                "market_confirmation": "0.70",
                "cross_source_confirmation": "0.50",
            },
        )
    )

    assert decision.action == "ALERT"
    assert decision.research_required is True
    assert decision.execution_allowed is False
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_security_exploit_event_blocks_instead_of_becoming_trade_signal() -> None:
    decision = EnterpriseEventTriggerEngine().evaluate(
        TriggerEvent.create(
            event_id="event-doge-bridge-exploit-1",
            event_type="SECURITY_EXPLOIT",
            domain="NEWS",
            entity="DOGEUSDT",
            detected_at=NOW,
            source="official-project",
            severity="0.95",
            confidence="0.90",
            relevance="0.85",
            freshness="1.00",
            evidence_count=4,
            dedup_key="DOGEUSDT:SECURITY_EXPLOIT:20260809T1200Z",
            payload={
                "source_tier": "official",
                "mention_velocity": "0.70",
                "market_confirmation": "0.80",
                "cross_source_confirmation": "0.80",
                "risk_blocker": "true",
            },
        )
    )

    assert decision.action == "BLOCK"
    assert decision.research_required is True
    assert decision.blockers == ("RISK_RESEARCH_BLOCKER",)
    assert decision.execution_allowed is False


def test_excluded_assets_do_not_trigger_market_research() -> None:
    decisions = EnterpriseEventTriggerEngine().evaluate_many(
        (
            _market_event("USDCUSDT", "stable"),
            _market_event("WBTCUSDT", "wrapped"),
            _market_event("BTCUPUSDT", "leveraged"),
        )
    )

    assert [decision.action for decision in decisions] == ["IGNORE", "IGNORE", "IGNORE"]
    assert {blocker for decision in decisions for blocker in decision.blockers} == {
        "EXCLUDED_STABLE_WRAPPED_OR_LEVERAGED_TOKEN"
    }


def test_technology_release_is_research_candidate_not_install_or_deploy() -> None:
    decision = EnterpriseEventTriggerEngine().evaluate(
        TriggerEvent.create(
            event_id="event-llama-release-1",
            event_type="TECH_RELEASE_DETECTED",
            domain="TECHNOLOGY",
            entity="llama.cpp",
            detected_at=NOW,
            source="github-release",
            severity="0.55",
            confidence="0.80",
            relevance="0.85",
            freshness="1.00",
            evidence_count=2,
            dedup_key="TECH:llama.cpp:release",
            payload={
                "source_tier": "official",
                "mention_velocity": "0.10",
                "market_confirmation": "0.00",
                "cross_source_confirmation": "0.30",
            },
        )
    )

    assert decision.action == "RESEARCH"
    assert decision.action not in {"INSTALL", "REPLACE", "DEPLOY"}
    assert decision.execution_allowed is False


def test_dedup_keeps_highest_impact_cluster_decision() -> None:
    low = _market_event("BTCUSDT", "story", severity="0.40", event_id="event-low")
    high = _market_event(
        "BTCUSDT",
        "story",
        severity="0.90",
        evidence_count=4,
        event_id="event-high",
        detected_at=NOW + timedelta(minutes=1),
    )

    decisions = EnterpriseEventTriggerEngine().evaluate_many((low, high))

    assert len(decisions) == 1
    assert decisions[0].event_id == "event-high"
    assert decisions[0].dedup_key == "BTCUSDT:story"


def test_trigger_contracts_reject_bad_input_and_authority_drift() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TriggerEvent.create(
            event_id="event-naive",
            event_type="SOCIAL_VOLUME_SPIKE",
            domain="SOCIAL",
            entity="BTCUSDT",
            detected_at=datetime(2026, 8, 9, 12, 0),
            source="social",
            severity="0.5",
            confidence="0.5",
            relevance="0.5",
            freshness="0.5",
            evidence_count=1,
            dedup_key="BTCUSDT:naive",
        )
    with pytest.raises(ValueError, match="cannot grant execution"):
        TriggerDecision(
            event_id="decision-authority-drift",
            event_type="SOCIAL_VOLUME_SPIKE",
            domain="SOCIAL",
            entity="BTCUSDT",
            impact_score=Decimal("0"),
            action="WATCH",
            research_required=False,
            blockers=(),
            dedup_key="BTCUSDT:authority",
            source="social",
            detected_at=NOW,
            execution_allowed=True,
        )


def _market_event(
    symbol: str,
    dedup_suffix: str,
    *,
    severity: str = "0.80",
    evidence_count: int = 2,
    event_id: str | None = None,
    detected_at: datetime = NOW,
) -> TriggerEvent:
    return TriggerEvent.create(
        event_id=event_id or f"event-{symbol.lower()}-{dedup_suffix}",
        event_type="MARKET_ANOMALY",
        domain="MARKET",
        entity=symbol,
        detected_at=detected_at,
        source="market-data",
        severity=severity,
        confidence="0.70",
        relevance="0.90",
        freshness="1.00",
        evidence_count=evidence_count,
        dedup_key=f"{symbol}:{dedup_suffix}",
        payload={
            "source_tier": "official",
            "mention_velocity": "0.70",
            "market_confirmation": "0.90",
            "cross_source_confirmation": "0.40",
        },
    )

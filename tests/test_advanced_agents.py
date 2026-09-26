"""Phase E deterministic advanced-agent coverage."""

from dataclasses import replace

from ai4binance.agents.advanced import ADVANCED_AGENT_NAMES, build_advanced_agent
from ai4binance.agents.catalog import ANALYSIS_DEFINITIONS, build_default_registry
from ai4binance.agents.technical import build_core_technical_agent
from ai4binance.agents.trend_events import build_trend_events_agent
from ai4binance.schemas import AgentStatus, PromotionStatus
from tests.test_technical_agents import technical_snapshot


def test_every_analysis_definition_has_a_real_builder() -> None:
    registry = build_default_registry()
    assert len(ADVANCED_AGENT_NAMES) == 23
    assert len(ANALYSIS_DEFINITIONS) == 34
    for definition in ANALYSIS_DEFINITIONS:
        implementation = (
            build_core_technical_agent(definition)
            or build_advanced_agent(definition)
            or build_trend_events_agent(definition)
        )
        assert implementation is not None, definition.name
        assert registry.get(definition.name) == definition


def test_advanced_ohlcv_agents_fail_closed_without_hard_gate() -> None:
    registry = build_default_registry()
    snapshot = technical_snapshot()
    external_names = {
        "sentiment",
        "news",
        "derivatives",
        "long_short",
        "whale",
        "onchain",
        "order_flow",
        "liquidity_analysis",
    }
    for name in sorted(ADVANCED_AGENT_NAMES - external_names):
        agent = build_advanced_agent(registry.get(name))
        assert agent is not None
        result = agent.analyze(snapshot, {})
        assert result.status in {
            AgentStatus.PARTIAL,
            AgentStatus.NOT_APPLICABLE,
            AgentStatus.INSUFFICIENT_DATA,
        }
        assert result.status is not AgentStatus.FAILED
        assert result.hard_gate_eligible is False
        assert result.promotion_status is PromotionStatus.RESEARCH_ONLY


def test_external_agents_require_sourced_numeric_snapshots() -> None:
    registry = build_default_registry()
    empty = technical_snapshot()
    sentiment = build_advanced_agent(registry.get("sentiment"))
    assert sentiment is not None
    missing = sentiment.analyze(empty, {})
    assert missing.status is AgentStatus.INSUFFICIENT_DATA
    assert "EXTERNAL_EVIDENCE_MISSING_OR_UNSOURCED" in missing.blockers

    sourced = replace(
        empty,
        snapshot_id="sourced-context",
        sentiment_snapshot={
            "source_count": 3,
            "directional_vote": "0.4",
            "score": "65",
            "as_of": empty.created_at.isoformat(),
        },
    )
    result = sentiment.analyze(sourced, {})
    assert result.status is AgentStatus.PARTIAL
    assert result.directional_vote == 0.4
    assert result.score == 65.0
    assert result.confidence <= 0.5
    assert result.hard_gate_eligible is False

    stale = sentiment.analyze(
        replace(
            sourced,
            snapshot_id="stale-context",
            sentiment_snapshot={
                "source_count": 3,
                "directional_vote": "0.4",
                "score": "65",
                "as_of": "2026-07-01T00:00:00+00:00",
            },
        ),
        {},
    )
    assert stale.status is AgentStatus.INSUFFICIENT_DATA
    assert stale.blockers == ("EXTERNAL_EVIDENCE_STALE_OR_FUTURE",)


def test_derivatives_context_does_not_require_a_directional_prediction() -> None:
    registry = build_default_registry()
    base = technical_snapshot()
    snapshot = replace(
        base,
        market_type="USD_M_FUTURES",
        derivatives_snapshot={
            "source_count": 4,
            "as_of": base.created_at.isoformat(),
            "funding_rate": "0.0001",
            "open_interest": "500000",
            "mark_price": "1.118",
            "index_price": "1.117",
        },
    )
    agent = build_advanced_agent(registry.get("derivatives"))
    assert agent is not None

    result = agent.analyze(snapshot, {})

    assert result.status is AgentStatus.PARTIAL
    assert result.directional_vote == 0.0
    assert result.score == 50.0
    assert result.warnings == ("SUPPLEMENTARY_FUTURES_CONTEXT_ONLY",)


def test_order_flow_uses_explicit_depth_and_remains_supplementary() -> None:
    registry = build_default_registry()
    snapshot = replace(
        technical_snapshot(),
        snapshot_id="depth-context",
        order_book_summary={"bid_depth": "150", "ask_depth": "50"},
    )
    agent = build_advanced_agent(registry.get("order_flow"))
    assert agent is not None
    result = agent.analyze(snapshot, {})

    assert result.status is AgentStatus.PARTIAL
    assert result.directional_vote == 0.5
    assert result.score == 50.0
    assert "TRANSIENT_ORDER_BOOK_EVIDENCE" in result.warnings
    assert result.hard_gate_eligible is False

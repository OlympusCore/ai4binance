"""Research event contracts and repository discovery enforce bounded intake."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from ai4binance.events import (
    EnterpriseEventTriggerEngine,
    is_binance_coin_research_symbol,
)
from ai4binance.events.trigger_engine import _bounded_decimal
from ai4binance.github_radar.discovery import discover_candidates
from ai4binance.github_radar.local_baseline import build_local_capability_baseline
from ai4binance.github_radar.query_planner import RadarQuery
from tests.test_enterprise_trigger_engine import _market_event
from tests.test_github_radar_discovery import FakeDiscoveryClient


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"event_id": ""}, "identity"),
        ({"detected_at": datetime(2026, 9, 1)}, "timezone-aware"),
        ({"severity": Decimal("1.1")}, "zero and one"),
        ({"evidence_count": -1}, "negative"),
        ({"payload": (("", "v"),)}, "non-empty"),
        ({"payload": (("a", "1"), ("a", "2"))}, "unique"),
        ({"payload": (("b", "1"), ("a", "2"))}, "sorted"),
    ],
)
def test_trigger_event_rejects_invalid_contract(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_market_event("BTCUSDT", "story"), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"event_id": ""}, "identity"),
        ({"impact_score": Decimal("101")}, "score"),
        ({"action": "EXECUTE"}, "action"),
        ({"execution_allowed": True}, "authority"),
    ],
)
def test_trigger_decision_rejects_invalid_authority(
    changes: dict[str, Any], message: str
) -> None:
    decision = EnterpriseEventTriggerEngine().evaluate(
        _market_event("BTCUSDT", "story")
    )
    with pytest.raises(ValueError, match=message):
        replace(decision, **changes)


@pytest.mark.parametrize(
    "changes", [{"watch_threshold": Decimal("60")}, {"watch_threshold": Decimal("-1")}]
)
def test_trigger_rejects_invalid_thresholds(changes: dict[str, Decimal]) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        EnterpriseEventTriggerEngine(**changes)


@pytest.mark.parametrize(("value", "expected"), [("-1", "0"), ("2", "1")])
def test_trigger_metric_clamps_out_of_range_values(value: str, expected: str) -> None:
    assert _bounded_decimal(value) == Decimal(expected)


def test_trigger_rejects_unparseable_metric_and_empty_symbol() -> None:
    with pytest.raises(ValueError, match="decimal-compatible"):
        _bounded_decimal("unavailable")
    assert is_binance_coin_research_symbol(" ") is False


@pytest.mark.parametrize(
    "changes", [{"repositories_per_query": 0}, {"documents_per_repository": 51}]
)
def test_discovery_rejects_unbounded_request(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be between"):
        discover_candidates(FakeDiscoveryClient(), (), **changes)


def test_discovery_deduplicates_same_capability_and_revision() -> None:
    query = RadarQuery(
        "R26-C01", "research", build_local_capability_baseline()[0].status
    )
    candidates = discover_candidates(
        FakeDiscoveryClient(),
        (query, query),
        repositories_per_query=1,
        documents_per_repository=2,
    )
    assert len(candidates) == 1
    assert candidates[0].execution_allowed is False
    assert "EXTERNAL_CODE_EXECUTION_BLOCKED" in candidates[0].blockers

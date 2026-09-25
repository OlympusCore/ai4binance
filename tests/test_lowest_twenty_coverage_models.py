"""Regression coverage for low-coverage value-object boundaries.

These tests exercise invalid public inputs rather than mutating coverage policy
or excluding production code from measurement.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import ai4binance
from ai4binance.agents import trend_events as trend_events_module
from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.trend_events import build_trend_events_agent
from ai4binance.enterprise.contracts import DepartmentId, Priority, WorkflowIdentity
from ai4binance.enterprise.data_supply import (
    DataProduct,
    DataProductRequest,
    DataProductType,
    DataQualityStatus,
    assess_data_product_request,
)
from ai4binance.events.models import DomainEvent
from ai4binance.governance.shadow import DgeShadowDecisionDiff

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def _event() -> DomainEvent:
    return DomainEvent.create(
        event_id="event-1",
        aggregate_id="aggregate-1",
        event_type="CREATED",
        sequence=1,
        occurred_at=NOW,
        payload=(("key", "value"),),
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda event: replace(event, event_id=""), "identity"),
        (lambda event: replace(event, sequence=0), "identity"),
        (
            lambda event: replace(event, occurred_at=NOW.replace(tzinfo=None)),
            "timezone",
        ),
        (lambda event: replace(event, payload=(("", "value"),)), "payload keys"),
        (
            lambda event: replace(event, payload=(("b", "1"), ("a", "2"))),
            "payload must be sorted",
        ),
        (lambda event: replace(event, event_hash="invalid"), "content hash"),
    ],
)
def test_domain_event_rejects_invalid_replay_inputs(
    change: Callable[[DomainEvent], DomainEvent], message: str
) -> None:
    event = _event()
    with pytest.raises(ValueError, match=message):
        change(event)


def test_domain_event_create_sorts_payload_and_exposes_copy() -> None:
    event = DomainEvent.create(
        event_id="event-2",
        aggregate_id="aggregate-1",
        event_type="UPDATED",
        sequence=2,
        occurred_at=NOW,
        payload=(("b", "2"), ("a", "1")),
    )
    assert event.payload == (("a", "1"), ("b", "2"))
    assert event.payload_dict() == {"a": "1", "b": "2"}


@pytest.mark.parametrize(
    "temporary_directory",
    [("C:/outside",), ("runtime/tmp/../outside",)],
)
def test_runtime_environment_rejects_unsafe_temp_contracts(
    monkeypatch: pytest.MonkeyPatch,
    temporary_directory: tuple[str],
) -> None:
    directory = temporary_directory[0]
    monkeypatch.setattr(
        "ai4binance.tomllib.load",
        lambda _stream: {
            "tool": {"ai4binance": {"runtime": {"temporary_directory": directory}}}
        },
    )
    with pytest.raises(ValueError, match="Temporary directory"):
        ai4binance.configure_runtime_environment()


def test_data_supply_requires_evidence_and_never_authorizes_execution() -> None:
    request = DataProductRequest(
        identity=WorkflowIdentity("workflow", "run", "trace", NOW),
        request_id="request-1",
        requester_department_id=DepartmentId.MARKET_INTELLIGENCE,
        product_type=DataProductType.MARKET_SNAPSHOT,
        purpose="Deterministic local research.",
        priority=Priority.P1,
        evidence_refs=(),
    )
    assessment = assess_data_product_request(request)
    assert assessment.allowed is False
    assert assessment.reason_codes == ("DATA_REQUEST_EVIDENCE_REQUIRED",)
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(assessment, execution_allowed=True)


def test_data_supply_value_objects_reject_invalid_boundary_values() -> None:
    request = DataProductRequest(
        identity=WorkflowIdentity("workflow", "run", "trace", NOW),
        request_id="request-1",
        requester_department_id=DepartmentId.MARKET_INTELLIGENCE,
        product_type=DataProductType.MARKET_SNAPSHOT,
        purpose="Deterministic local research.",
        priority=Priority.P1,
        evidence_refs=("evidence:1",),
    )
    product = DataProduct(
        identity=request.identity,
        data_product_id="product-1",
        snapshot_id="snapshot-1",
        product_type=DataProductType.MARKET_SNAPSHOT,
        source_id="source-1",
        source_authority="EXCHANGE_PRIMARY",
        freshness_seconds=0,
        content_hash="a" * 64,
        quality_status=DataQualityStatus.FRESH,
        consumer_departments=(DepartmentId.MARKET_INTELLIGENCE,),
    )
    with pytest.raises(ValueError, match="identity is required"):
        replace(request, request_id="")
    with pytest.raises(ValueError, match="cannot be negative"):
        replace(product, freshness_seconds=-1)
    with pytest.raises(ValueError, match="content hash"):
        replace(product, content_hash="invalid")
    with pytest.raises(ValueError, match="requires consumer"):
        replace(product, consumer_departments=())
    with pytest.raises(ValueError, match="assessment identity"):
        replace(assess_data_product_request(request), request_id="")
    with pytest.raises(ValueError, match="reasons disagree"):
        replace(assess_data_product_request(request), allowed=False)


def test_shadow_diff_cannot_widen_execution_authority() -> None:
    blocked = type("Blocked", (), {"live_eligibility_status": "LIVE_ORDER_BLOCKED"})()
    with pytest.raises(ValueError, match="cannot authorize"):
        DgeShadowDecisionDiff(
            shadow_rule_id="shadow-1",
            baseline_decision=blocked,
            shadow_decision=blocked,
            would_change_decision=False,
            changed_fields=(),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="shadow rule id"):
        DgeShadowDecisionDiff(
            shadow_rule_id=" ",
            baseline_decision=blocked,
            shadow_decision=blocked,
            would_change_decision=False,
            changed_fields=(),
        )


def test_trend_events_builder_rejects_other_agent_definitions() -> None:
    definition = build_default_registry().get("trend_events")
    assert build_trend_events_agent(definition) is not None
    assert build_trend_events_agent(replace(definition, name="other")) is None


@pytest.mark.parametrize(
    ("cross_over_result", "cross_under_result", "expected_event"),
    [
        (True, False, "GOLDEN_CROSS:1h"),
        (False, True, "DEATH_CROSS:1h"),
    ],
)
def test_trend_events_observe_records_crosses_and_confirmed_slope(
    monkeypatch: pytest.MonkeyPatch,
    cross_over_result: bool,
    cross_under_result: bool,
    expected_event: str,
) -> None:
    monkeypatch.setattr(
        trend_events_module,
        "supertrend",
        lambda *_args, **_kwargs: (SimpleNamespace(direction=1, band=1),),
    )
    monkeypatch.setattr(
        trend_events_module,
        "closes",
        lambda _candles: tuple(range(201)),
    )
    monkeypatch.setattr(trend_events_module, "ema", lambda values, _period: values)
    monkeypatch.setattr(
        trend_events_module, "cross_over", lambda *_args: cross_over_result
    )
    monkeypatch.setattr(
        trend_events_module, "cross_under", lambda *_args: cross_under_result
    )
    monkeypatch.setattr(
        trend_events_module,
        "confirmed_swings",
        lambda _candles: (
            SimpleNamespace(kind="HIGH", price=10, index=1),
            SimpleNamespace(kind="HIGH", price=14, index=3),
        ),
    )
    observed = trend_events_module.TrendEventsAgent._observe(
        "1h",
        (object(),) * 201,  # type: ignore[arg-type]
    )
    _timeframe, direction, _band, events, slope = observed
    assert direction == 1
    assert events == (expected_event,)
    assert slope == 2

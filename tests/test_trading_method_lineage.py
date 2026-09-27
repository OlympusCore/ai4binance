"""D2 causal provenance through live producers, hypotheses and lifecycle storage."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.agents.advanced import build_advanced_agent
from ai4binance.agents.catalog import build_default_registry
from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.intelligence.method_lineage import MethodLineage
from ai4binance.intelligence.method_registry import current_method_registry
from ai4binance.intelligence.patterns import PatternHypothesisFabric
from ai4binance.opportunity_intelligence import (
    OpportunityEventType,
    OpportunityLifecycleLedger,
)
from ai4binance.opportunity_ledger import OpportunityLedgerWriter
from ai4binance.reporting import to_primitive
from tests.test_opportunity_intelligence import lifecycle_event
from tests.test_technical_agents import technical_snapshot
from tests.test_trading_intelligence import _result


def test_new_producer_to_pattern_chain_records_current_rules() -> None:
    snapshot = technical_snapshot()
    registry = build_default_registry()
    rows = snapshot.ohlcv_by_timeframe["1d"]
    # Real contextual engulfing input, evaluated by the production detector.
    rows = (
        *rows[:-2],
        replace(
            rows[-2],
            open=Decimal("1.2"),
            close=Decimal("1.1"),
            high=Decimal("1.21"),
            low=Decimal("1.09"),
        ),
        replace(
            rows[-1],
            open=Decimal("1.09"),
            close=Decimal("1.21"),
            high=Decimal("1.22"),
            low=Decimal("1.08"),
        ),
    )
    snapshot = replace(
        snapshot,
        ohlcv_by_timeframe=dict.fromkeys(snapshot.timeframes, rows),
    )
    candle = build_advanced_agent(registry.get("candlestick"))
    assert candle is not None
    result = candle.analyze(snapshot, {})
    recorded = MethodLineage.from_payload(result.calculation_metadata["method_lineage"])
    (hypothesis,) = PatternHypothesisFabric().build(snapshot, {"candlestick": result})
    assert hypothesis.method_lineage == recorded
    assert recorded.method_id == "formations"
    assert not hypothesis.execution_allowed
    assert not hypothesis.primary_direction_signal
    assert "method_lineage" in json.dumps(to_primitive(hypothesis))


@pytest.mark.parametrize(
    ("name", "method_id"),
    [
        ("fibonacci", "fibonacci"),
        ("elliott_wave", "elliott_waves"),
        ("harmonic_pattern", "harmonic_patterns.bat"),
    ],
)
def test_specialized_builders_preserve_lineage(name: str, method_id: str) -> None:
    lineage = current_method_registry().lineage(method_id, "1.0.0", "1.0.0")
    metadata: dict[str, object] = {
        "method_lineage": lineage.to_payload(),
        "pattern_id": "anchors:1",
        "ab_cd": "1.0",
        "pattern_family": "BAT",
    }
    result = _result(name, metadata=metadata)
    (hypothesis,) = PatternHypothesisFabric().build(
        technical_snapshot(), {name: result}
    )
    assert hypothesis.method_lineage == lineage


def test_legacy_observations_are_never_backfilled() -> None:
    result = _result("fibonacci", metadata={"pattern_id": "anchors:legacy"})
    (hypothesis,) = PatternHypothesisFabric().build(
        technical_snapshot(), {"fibonacci": result}
    )
    assert hypothesis.method_lineage is None
    event = lifecycle_event(
        state=OpportunityLifecycleState.DISCOVERED,
        event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
        minute=0,
    )
    assert "method_lineages" not in event.to_payload()


@pytest.mark.parametrize(
    "field", ["method_version", "rule_set_version", "definition_sha256", "source_refs"]
)
def test_unknown_or_tampered_provenance_is_rejected(field: str) -> None:
    payload = (
        current_method_registry().lineage("fibonacci", "1.0.0", "1.0.0").to_payload()
    )
    payload[field] = (
        ("unknown",)
        if field == "source_refs"
        else "0" * 64
        if field == "definition_sha256"
        else "99.0.0"
    )
    result = _result("fibonacci", metadata={"method_lineage": payload})
    with pytest.raises(ValueError, match=r"unknown|registered definition"):
        PatternHypothesisFabric().build(technical_snapshot(), {"fibonacci": result})


def test_foreign_method_cannot_relabel_a_pattern() -> None:
    lineage = current_method_registry().lineage("elliott_waves", "1.0.0", "1.0.0")
    result = _result("fibonacci", metadata={"method_lineage": lineage.to_payload()})
    with pytest.raises(ValueError, match="another family"):
        PatternHypothesisFabric().build(technical_snapshot(), {"fibonacci": result})


def test_harmonic_variant_cannot_borrow_another_variants_lineage() -> None:
    lineage = current_method_registry().lineage(
        "harmonic_patterns.bat", "1.0.0", "1.0.0"
    )
    result = _result(
        "harmonic_pattern",
        metadata={"method_lineage": lineage.to_payload(), "pattern_family": "GARTLEY"},
    )
    with pytest.raises(ValueError, match="another family"):
        PatternHypothesisFabric().build(
            technical_snapshot(), {"harmonic_pattern": result}
        )


def test_versioned_pattern_identity_is_stable_across_observations() -> None:
    snapshot = technical_snapshot()
    lineage = current_method_registry().lineage("fibonacci", "1.0.0", "1.0.0")
    result = _result(
        "fibonacci",
        metadata={
            "method_lineage": lineage.to_payload(),
            "pattern_id": "anchors:stable",
        },
    )
    (first,) = PatternHypothesisFabric().build(snapshot, {"fibonacci": result})
    (second,) = PatternHypothesisFabric().build(
        replace(snapshot, snapshot_id="next"),
        {"fibonacci": replace(result, snapshot_id="next")},
    )
    assert first.hypothesis_id == second.hypothesis_id
    assert first.observation_id != second.observation_id
    assert first.method_lineage == second.method_lineage


def test_lifecycle_writer_retains_lineage_and_prevents_historical_rewrite(
    tmp_path: Path,
) -> None:
    lineage = current_method_registry().lineage("fibonacci", "1.0.0", "1.0.0")
    event = replace(
        lifecycle_event(
            state=OpportunityLifecycleState.DISCOVERED,
            event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
            minute=0,
        ),
        method_lineages=(lineage,),
    )
    ledger = OpportunityLifecycleLedger().append(event)
    with pytest.raises(ValueError, match="cannot change content"):
        ledger.append(replace(event, method_lineages=()))
    path = tmp_path / "lifecycle.jsonl"
    writer = OpportunityLedgerWriter(path, durable=False)
    assert writer.append(event) is not None
    assert writer.append(event) is None
    row = json.loads(path.read_text(encoding="utf-8"))
    restored = MethodLineage.from_payload(row["payload"]["method_lineages"][0])
    assert restored == lineage
    # Reading history is independent of which registry version is now active.
    historical = replace(lineage, registry_version="0.9.0")
    assert MethodLineage.from_payload(historical.to_payload()) == historical

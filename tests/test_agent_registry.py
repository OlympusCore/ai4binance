"""Agent catalog and governance registry tests."""

from dataclasses import replace

import pytest

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.registry import AgentDefinition, AgentRegistry, AgentStage
from ai4binance.schemas import PromotionStatus


def test_default_registry_contains_complete_governed_catalog() -> None:
    registry = build_default_registry()
    assert len(registry.definitions) == 48
    assert registry.get("trend").stage is AgentStage.ANALYSIS
    assert registry.get("qaqc_agent").stage is AgentStage.LEARNING
    assert registry.get("qaqc_agent").dependencies == ("validation", "learning")
    assert registry.get("execution").dependencies == (
        "validation",
        "risk",
        "wallet_inventory",
    )
    assert all(not item.hard_gate_eligible for item in registry.definitions)
    assert all(
        item.promotion_status is PromotionStatus.RESEARCH_ONLY
        for item in registry.definitions
    )
    assert len(registry.by_stage(AgentStage.ANALYSIS)) == 34


def test_registry_rejects_duplicate_unknown_and_cyclic_dependencies() -> None:
    definition = build_default_registry().get("trend")
    with pytest.raises(ValueError, match="unique"):
        AgentRegistry((definition, definition))
    with pytest.raises(ValueError, match="unknown dependencies"):
        AgentRegistry((replace(definition, dependencies=("missing",)),))
    left = replace(definition, name="left", dependencies=("right",))
    right = replace(definition, name="right", dependencies=("left",))
    with pytest.raises(ValueError, match="contains a cycle"):
        AgentRegistry((left, right))


def test_agent_definition_rejects_unsafe_governance() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        AgentDefinition(
            name="",
            family="test",
            version="1",
            stage=AgentStage.ANALYSIS,
            required_data=(),
            supported_timeframes=("1h",),
            compatible_regimes=("ALL",),
        )
    with pytest.raises(ValueError, match="score_range"):
        AgentDefinition(
            name="test",
            family="test",
            version="1",
            stage=AgentStage.ANALYSIS,
            required_data=(),
            supported_timeframes=("1h",),
            compatible_regimes=("ALL",),
            score_range=(101.0, 0.0),
        )
    with pytest.raises(ValueError, match="depend on itself"):
        AgentDefinition(
            name="test",
            family="test",
            version="1",
            stage=AgentStage.ANALYSIS,
            required_data=(),
            supported_timeframes=("1h",),
            compatible_regimes=("ALL",),
            dependencies=("test",),
        )
    with pytest.raises(ValueError, match="governed promotion"):
        AgentDefinition(
            name="test",
            family="test",
            version="1",
            stage=AgentStage.ANALYSIS,
            required_data=(),
            supported_timeframes=("1h",),
            compatible_regimes=("ALL",),
            hard_gate_eligible=True,
        )
    with pytest.raises(ValueError, match="OOS requirements"):
        AgentDefinition(
            name="test",
            family="test",
            version="1",
            stage=AgentStage.ANALYSIS,
            required_data=(),
            supported_timeframes=("1h",),
            compatible_regimes=("ALL",),
            hard_gate_eligible=True,
            promotion_status=PromotionStatus.PAPER_APPROVED,
        )

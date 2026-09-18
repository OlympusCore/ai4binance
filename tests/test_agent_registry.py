"""Agent catalog and governance registry tests."""

from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.agents.catalog import (
    ANALYSIS_DEFINITIONS,
    CAPABILITY_BUNDLE_DEFINITIONS,
    build_default_capability_bundle_registry,
    build_default_capability_registry,
    build_default_registry,
)
from ai4binance.agents.registry import (
    AgentDefinition,
    AgentRegistry,
    AgentStage,
    CapabilityActivationPolicy,
    CapabilityBundleDefinition,
    CapabilityBundleRegistry,
    CapabilityExecutionClass,
    CapabilityRegistry,
)
from ai4binance.schemas import PromotionStatus


def test_default_registry_contains_complete_governed_catalog() -> None:
    registry = build_default_registry()
    assert len(registry.definitions) == 49
    assert registry.get("memory_advisory").stage is AgentStage.ANALYSIS
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
    assert len(registry.by_stage(AgentStage.ANALYSIS)) == 35
    assert len(ANALYSIS_DEFINITIONS) == 34
    assert "memory_advisory" in {
        definition.name for definition in registry.by_stage(AgentStage.ANALYSIS)
    }


def test_agent_registry_scope_separates_role_packages_from_capabilities() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "registries"
        / "registry_agent_registry.md"
    ).read_text(encoding="utf-8")

    assert "source_of_truth_scope: ai_orchestration_role_packages" in text
    assert "It is not a catalog of analytical capabilities" in text
    assert "34 logical analytical capabilities plus one" in text
    assert "Capability runtime contract" in text
    assert "`CapabilityPreflightPlan` evaluates runtime eligibility" in text
    assert "`CapabilityBundleExecutor`" in text
    assert "at most one `CapabilityBundleExecutor`" in text
    assert "`EvidenceFusionEngine`" in text
    assert "`DataQualityGate`" in text
    assert "`RiskGate`" in text
    assert "independent risk rules" in text
    assert "`ValidationGate`" in text
    assert "independent validation rules" in text
    assert "`UniverseLiquidityGate`" in text
    assert "independent eligibility rules" in text
    assert "must not implement independent quality rules" in text
    assert "compatibility facade" in text
    assert "`NOT_APPLICABLE`" in text
    assert "dependency-aware bundle scheduler" in text


def test_capability_registry_projects_the_analytical_catalog_without_authority() -> (
    None
):
    registry = build_default_capability_registry()

    assert len(registry.definitions) == len(ANALYSIS_DEFINITIONS) == 34
    assert tuple(registry.by_id) == tuple(item.name for item in ANALYSIS_DEFINITIONS)
    for agent_definition in ANALYSIS_DEFINITIONS:
        capability = registry.get(agent_definition.name)
        assert capability.version == agent_definition.version
        assert capability.dependencies == agent_definition.dependencies
        assert capability.required_data == agent_definition.required_data
        assert capability.timeframes == agent_definition.supported_timeframes
        assert capability.compatible_regimes == agent_definition.compatible_regimes
        assert capability.cluster == agent_definition.evidence_cluster
        assert capability.expensive is agent_definition.expensive
        assert capability.runtime_eligible is True
        assert (
            capability.execution_class
            is CapabilityExecutionClass.DETERMINISTIC_THREAD_POOL
        )
        assert (
            capability.activation_policy is CapabilityActivationPolicy.ALWAYS_SCHEDULED
        )
        assert capability.promotion_status is PromotionStatus.RESEARCH_ONLY
        assert capability.execution_allowed is False
        assert capability.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_capability_bundle_registry_covers_each_analytical_capability_once() -> None:
    capability_registry = build_default_capability_registry()
    bundle_registry = build_default_capability_bundle_registry()

    assert len(bundle_registry.definitions) == 6
    assert tuple(bundle_registry.by_id) == (
        "market_state",
        "structure_location",
        "momentum_participation",
        "liquidity_flow",
        "cross_market_derivatives",
        "setup_event",
    )
    assert {
        capability_id
        for bundle in bundle_registry.definitions
        for capability_id in bundle.capability_ids
    } == set(capability_registry.by_id)
    assert all(
        bundle.execution_allowed is False
        and bundle.promotion_status is PromotionStatus.RESEARCH_ONLY
        and bundle.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for bundle in bundle_registry.definitions
    )

    with pytest.raises(ValueError, match="identities must be unique"):
        CapabilityBundleRegistry(
            (CAPABILITY_BUNDLE_DEFINITIONS[0], CAPABILITY_BUNDLE_DEFINITIONS[0]),
            capability_registry,
        )
    with pytest.raises(ValueError, match="unknown capabilities"):
        CapabilityBundleRegistry(
            (CapabilityBundleDefinition("unknown", ("missing",)),),
            capability_registry,
        )
    with pytest.raises(ValueError, match="multiple bundles"):
        CapabilityBundleRegistry(
            (
                CAPABILITY_BUNDLE_DEFINITIONS[0],
                replace(
                    CAPABILITY_BUNDLE_DEFINITIONS[1],
                    capability_ids=(
                        *CAPABILITY_BUNDLE_DEFINITIONS[1].capability_ids,
                        "trend",
                    ),
                ),
                *CAPABILITY_BUNDLE_DEFINITIONS[2:],
            ),
            capability_registry,
        )
    definition = CAPABILITY_BUNDLE_DEFINITIONS[0]
    with pytest.raises(ValueError, match="identity"):
        replace(definition, bundle_id="")
    with pytest.raises(ValueError, match="non-empty capability IDs"):
        replace(definition, capability_ids=())
    with pytest.raises(ValueError, match="membership"):
        replace(definition, capability_ids=("trend", "trend"))
    with pytest.raises(ValueError, match="research-only"):
        replace(definition, promotion_status=PromotionStatus.PAPER_APPROVED)
    with pytest.raises(ValueError, match="cannot allow execution"):
        replace(definition, execution_allowed=True)
    with pytest.raises(ValueError, match="keep live orders blocked"):
        replace(definition, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(KeyError):
        bundle_registry.get("missing")


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
    base = build_default_registry().get("trend")
    with pytest.raises(ValueError, match="required evidence domains"):
        replace(base, required_evidence_domains=("A", "A"))
    with pytest.raises(ValueError, match="verification checks"):
        replace(base, required_verification_checks=("A", "A"))
    with pytest.raises(ValueError, match="evidence domains"):
        replace(base, required_evidence_domains=("",))
    with pytest.raises(ValueError, match="verification checks"):
        replace(base, required_verification_checks=("",))


def test_capability_registry_rejects_authority_widening_and_invalid_graphs() -> None:
    definition = build_default_capability_registry().get("trend")
    with pytest.raises(ValueError, match="capability_id"):
        replace(definition, capability_id="")
    with pytest.raises(ValueError, match="depend on itself"):
        replace(definition, dependencies=(definition.capability_id,))
    with pytest.raises(ValueError, match="timeframes"):
        replace(definition, timeframes=())
    with pytest.raises(ValueError, match="regimes"):
        replace(definition, compatible_regimes=("",))
    with pytest.raises(ValueError, match="research-only"):
        replace(definition, promotion_status=PromotionStatus.PAPER_APPROVED)
    with pytest.raises(ValueError, match="cannot allow execution"):
        replace(definition, execution_allowed=True)
    with pytest.raises(ValueError, match="keep live orders blocked"):
        replace(definition, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="external capability dependencies"):
        CapabilityRegistry((definition,), external_dependency_ids=("remote", "remote"))
    with pytest.raises(ValueError, match="unknown dependencies"):
        CapabilityRegistry((replace(definition, dependencies=("missing",)),))
    left = replace(definition, capability_id="left", dependencies=("right",))
    right = replace(definition, capability_id="right", dependencies=("left",))
    with pytest.raises(ValueError, match="contains a cycle"):
        CapabilityRegistry((left, right))
    with pytest.raises(ValueError, match="identifiers must be unique"):
        CapabilityRegistry((definition, definition))
    with pytest.raises(ValueError, match="unknown dependencies"):
        CapabilityRegistry((replace(definition, dependencies=("missing",)),))
    left = replace(definition, capability_id="left", dependencies=("right",))
    right = replace(definition, capability_id="right", dependencies=("left",))
    with pytest.raises(ValueError, match="contains a cycle"):
        CapabilityRegistry((left, right))

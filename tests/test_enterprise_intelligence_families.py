from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.enterprise.departments import AgentClassification
from ai4binance.enterprise.intelligence_families import (
    IntelligenceFamily,
    IntelligenceFamilyId,
    IntelligenceFamilyRegistry,
    SkillDeclaration,
    build_default_intelligence_family_registry,
)


def test_default_intelligence_registry_covers_all_families() -> None:
    registry = build_default_intelligence_family_registry()

    assert len(registry.families) == len(IntelligenceFamilyId)
    assert all(item.promotion_status == "RESEARCH_ONLY" for item in registry.families)
    assert all(
        item.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for item in registry.families
    )


def test_financial_calculations_are_deterministic_skills_not_llm_agents() -> None:
    registry = build_default_intelligence_family_registry()
    momentum = registry.get(IntelligenceFamilyId.MOMENTUM_EXHAUSTION)
    declarations = {item.skill_name: item for item in momentum.skills}

    assert declarations["RSI"].classification is AgentClassification.DETERMINISTIC_SKILL
    assert declarations["MACD"].classification is (
        AgentClassification.DETERMINISTIC_SKILL
    )
    with pytest.raises(ValueError, match="deterministic skills"):
        SkillDeclaration("RSI", AgentClassification.LLM_ADVISORY_AGENT)


def test_advisory_patterns_cannot_become_hard_gates() -> None:
    registry = build_default_intelligence_family_registry()
    family = registry.get(IntelligenceFamilyId.PATTERN_CYCLE)
    advisory = family.skills[0]

    assert family.llm_advisory_allowed is True
    assert advisory.advisory_only is True
    with pytest.raises(ValueError, match="hard gates"):
        replace(advisory, hard_gate_eligible=True)


def test_intelligence_registry_rejects_missing_duplicate_or_unsafe_families() -> None:
    registry = build_default_intelligence_family_registry()
    family = registry.families[0]

    with pytest.raises(ValueError, match="cover every"):
        IntelligenceFamilyRegistry(registry.families[:-1])
    with pytest.raises(ValueError, match="unique"):
        IntelligenceFamilyRegistry((family, family, *registry.families[2:]))
    with pytest.raises(ValueError, match="promote"):
        replace(family, promotion_status="PAPER_APPROVED")
    with pytest.raises(ValueError, match="authorize"):
        replace(family, execution_allowed=True)
    with pytest.raises(ValueError, match="skills must be unique"):
        IntelligenceFamily(
            family.family_id,
            family.coordinator_agent,
            (family.skills[0], family.skills[0]),
            False,
            ("walk_forward",),
        )

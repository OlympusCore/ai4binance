"""Tests for the research-only institutional price-action catalogue."""

import pytest

from Models.model import (
    SCENARIO_BY_ID,
    SCENARIO_FAMILIES,
    SCENARIOS,
    Bias,
    ScenarioFamily,
    ScenarioStatus,
    get_scenario,
)


def test_catalogue_contains_22_families_and_44_mirrored_scenarios() -> None:
    assert len(SCENARIO_FAMILIES) == 22
    assert len(SCENARIOS) == 44
    assert len(SCENARIO_BY_ID) == 44
    for family in SCENARIO_FAMILIES:
        assert {family.for_bias(bias).bias for bias in Bias} == set(Bias)


def test_scenarios_are_research_only_and_non_executable() -> None:
    assert all(item.status is ScenarioStatus.RESEARCH_ONLY for item in SCENARIOS)
    assert not any(item.execution_allowed for item in SCENARIOS)


def test_directional_scenario_has_expected_zone_and_sequence() -> None:
    scenario = get_scenario("qm_quick_retest:bullish")
    assert scenario.bias is Bias.BULLISH
    assert scenario.reaction_zone == "demand/support"
    assert "upward displacement" in scenario.expected_sequence[2]


def test_unknown_scenario_has_explicit_error() -> None:
    with pytest.raises(ValueError, match="unknown scenario_id"):
        get_scenario("does-not-exist")


def test_incomplete_family_is_rejected() -> None:
    with pytest.raises(ValueError, match="structure cannot be empty"):
        ScenarioFamily(
            key="x",
            name="X",
            structure="",
            confirmation="confirm",
            invalidation="invalidate",
            false_positive_risk=("noise",),
        )

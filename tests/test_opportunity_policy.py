from __future__ import annotations

from decimal import Decimal

import pytest

from ai4binance.opportunity_policy import (
    OpportunityGradePolicy,
    bounded_opportunity_score,
    classify_opportunity_grade,
    count_opportunity_grades,
)


def test_opportunity_grade_policy_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="policy version is required"):
        OpportunityGradePolicy(policy_version=" ")

    with pytest.raises(ValueError, match="between 0 and 100"):
        OpportunityGradePolicy(a_threshold=Decimal("-1"))

    with pytest.raises(ValueError, match="descending"):
        OpportunityGradePolicy(
            a_threshold=Decimal("80"),
            b_plus_threshold=Decimal("90"),
        )

    with pytest.raises(ValueError, match="unique"):
        OpportunityGradePolicy(
            a_threshold=Decimal("90"),
            b_plus_threshold=Decimal("90"),
        )


def test_opportunity_grade_policy_classifies_boundaries_and_counts() -> None:
    policy = OpportunityGradePolicy()

    assert bounded_opportunity_score(Decimal("-5")) == Decimal("0")
    assert bounded_opportunity_score(Decimal("105")) == Decimal("100")
    assert bounded_opportunity_score(Decimal("NaN")) == Decimal("0")

    assert policy.classify(Decimal("95")) == "A"
    assert policy.classify(Decimal("90")) == "A"
    assert policy.classify(Decimal("85")) == "B+"
    assert policy.classify(Decimal("70")) == "B"
    assert policy.classify(Decimal("60")) == "B-"
    assert policy.classify(Decimal("50")) == "C"
    assert policy.classify(Decimal("49.9")) == "D"

    assert policy.is_b_or_higher("A") is True
    assert policy.is_b_or_higher("B+") is True
    assert policy.is_b_or_higher("B") is True
    assert policy.is_b_or_higher("C") is False
    assert policy.is_b_plus_or_higher("A") is True
    assert policy.is_b_plus_or_higher("B+") is True
    assert policy.is_b_plus_or_higher("B") is False

    assert classify_opportunity_grade(Decimal("99"), policy=policy) == "A"
    assert count_opportunity_grades(
        (
            Decimal("95"),
            Decimal("84"),
            Decimal("72"),
            Decimal("10"),
        ),
        policy=policy,
    ) == {
        "a_or_better_count": 1,
        "b_plus_count": 1,
        "b_count": 1,
    }

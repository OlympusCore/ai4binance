"""Focused tests for validation overfit diagnostics."""

from dataclasses import replace

import pytest

from ai4binance.validation.overfit import (
    DeflatedSharpeAssessment,
    SelectionOverfitAssessment,
    assess_deflated_sharpe,
    assess_selection_overfit,
)


def test_deflated_sharpe_covers_adjusted_edge_and_insufficient_probability() -> None:
    approved = assess_deflated_sharpe(
        (0.05, 0.051, 0.049, 0.052, 0.05, 0.051),
        hypothesis_count=1,
        minimum_probability=0.90,
    )
    assert approved.expected_max_sharpe == 0.0
    assert approved.blockers == ()
    assert approved.execution_allowed is False

    insufficient = assess_deflated_sharpe(
        (0.02, -0.02, 0.01, -0.01, 0.0, 0.001),
        hypothesis_count=20,
    )
    assert insufficient.hypothesis_count == 20
    assert insufficient.blockers == ("DEFLATED_SHARPE_INSUFFICIENT",)


def test_deflated_sharpe_constant_return_branch_is_fail_closed() -> None:
    positive = assess_deflated_sharpe((0.1, 0.1, 0.1), hypothesis_count=2)
    assert positive.observed_sharpe == 0.0
    assert positive.deflated_sharpe_probability == 1.0
    assert positive.blockers == ()

    flat = assess_deflated_sharpe((0.0, 0.0, 0.0), hypothesis_count=2)
    assert flat.deflated_sharpe_probability == 0.0
    assert flat.blockers == ("DEFLATED_SHARPE_INSUFFICIENT",)


@pytest.mark.parametrize(
    ("returns", "hypothesis_count", "minimum_probability", "message"),
    [
        ((0.1, 0.2), 1, 0.95, "three returns"),
        ((0.1, 0.2, 0.3), 0, 0.95, "three returns"),
        ((0.1, 0.2, float("nan")), 1, 0.95, "finite"),
        ((0.1, 0.2, 0.3), 1, 0.5, "minimum"),
    ],
)
def test_deflated_sharpe_rejects_invalid_inputs(
    returns: tuple[float, ...],
    hypothesis_count: int,
    minimum_probability: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        assess_deflated_sharpe(
            returns,
            hypothesis_count=hypothesis_count,
            minimum_probability=minimum_probability,
        )


def test_deflated_sharpe_assessment_rejects_invalid_contract_values() -> None:
    assessment = assess_deflated_sharpe(
        (0.03, 0.031, 0.032), hypothesis_count=1, minimum_probability=0.90
    )

    invalid_cases = (
        ({"sample_size": 2}, "sample and hypotheses"),
        ({"hypothesis_count": 0}, "sample and hypotheses"),
        ({"observed_sharpe": float("inf")}, "finite"),
        ({"deflated_sharpe_probability": 1.1}, "bounded"),
        ({"minimum_probability": 1.0}, "minimum"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            replace(assessment, **changes)


def test_selection_overfit_selects_stable_train_winners_without_blockers() -> None:
    training = ((3.0, 1.0), (3.5, 2.0), (4.0, 3.0), (4.5, 4.0))
    oos = ((3.0, 1.0), (3.0, 2.0), (3.0, 2.5), (3.0, 2.7))

    report = assess_selection_overfit(training, oos)

    assert report.selected_indices == (0, 0, 0, 0)
    assert report.overfit_probability == 0.0
    assert report.blockers == ()


def test_selection_overfit_blocks_high_probability_and_insufficient_splits() -> None:
    training = ((3.0, 1.0), (1.0, 3.0), (4.0, 1.0))
    oos = ((-2.0, 1.0), (1.0, -2.0), (-3.0, 1.0))

    report = assess_selection_overfit(training, oos, maximum_probability=0.25)

    assert report.overfit_probability == 1.0
    assert report.blockers == (
        "INSUFFICIENT_SELECTION_SPLITS",
        "BACKTEST_SELECTION_OVERFIT_HIGH",
    )


@pytest.mark.parametrize(
    ("training_scores", "oos_scores", "maximum_probability", "message"),
    [
        (((1.0, 2.0),), (), 0.5, "matrices must align"),
        (((1.0,),), ((1.0,),), 0.5, "candidate dimensions"),
        (((1.0, 2.0),), ((1.0, 2.0, 3.0),), 0.5, "candidate dimensions"),
        (((1.0, float("inf")),), ((1.0, 2.0),), 0.5, "finite"),
        (((1.0, 2.0),), ((1.0, 2.0),), 2.0, "bounded"),
    ],
)
def test_selection_overfit_rejects_invalid_inputs(
    training_scores: tuple[tuple[float, ...], ...],
    oos_scores: tuple[tuple[float, ...], ...],
    maximum_probability: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        assess_selection_overfit(
            training_scores,
            oos_scores,
            maximum_probability=maximum_probability,
        )


def test_selection_overfit_assessment_rejects_invalid_contract_values() -> None:
    assessment = SelectionOverfitAssessment(
        split_count=4,
        candidate_count=2,
        overfit_probability=0.25,
        maximum_probability=0.5,
        selected_indices=(0, 1, 0, 1),
        blockers=(),
    )

    invalid_cases = (
        ({"split_count": 0}, "dimensions"),
        ({"candidate_count": 1}, "dimensions"),
        ({"overfit_probability": -0.1}, "probability must be bounded"),
        ({"maximum_probability": 1.1}, "maximum overfit probability"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            replace(assessment, **changes)


def test_assessment_payloads_remain_fail_closed_by_default() -> None:
    deflated = DeflatedSharpeAssessment(
        sample_size=3,
        hypothesis_count=1,
        observed_sharpe=0.1,
        expected_max_sharpe=0.0,
        deflated_sharpe_probability=0.95,
        minimum_probability=0.90,
        blockers=(),
    )
    selected = SelectionOverfitAssessment(
        split_count=1,
        candidate_count=2,
        overfit_probability=0.0,
        maximum_probability=0.5,
        selected_indices=(0,),
        blockers=("INSUFFICIENT_SELECTION_SPLITS",),
    )

    assert deflated.execution_allowed is False
    assert selected.execution_allowed is False

"""Purged walk-forward and selection-overfit governance tests."""

from dataclasses import replace

import pytest

from ai4binance.validation import (
    WalkForwardConfig,
    assess_deflated_sharpe,
    assess_selection_overfit,
)
from ai4binance.validation.walk_forward import WalkForwardValidator
from tests.test_walk_forward import candles


def test_purge_and_embargo_create_explicit_gaps() -> None:
    config = WalkForwardConfig(
        train_size=4,
        test_size=2,
        step_size=2,
        purge_size=1,
        embargo_size=1,
    )
    windows = WalkForwardValidator._build_windows(candles(14), config)
    assert windows[0].train[-1].timestamp.hour == 3
    assert windows[0].test[0].timestamp.hour == 5
    assert windows[1].train[0].timestamp.hour == 3
    assert windows[1].test[0].timestamp.hour == 8


def test_deflated_sharpe_distinguishes_stable_edge_from_noise() -> None:
    strong = assess_deflated_sharpe(
        (0.03, 0.031, 0.029, 0.032, 0.03, 0.031),
        hypothesis_count=2,
        minimum_probability=0.90,
    )
    assert strong.blockers == ()
    assert strong.deflated_sharpe_probability >= 0.90

    weak = assess_deflated_sharpe(
        (0.02, -0.02, 0.01, -0.01, 0.0, 0.001),
        hypothesis_count=20,
    )
    assert weak.blockers == ("DEFLATED_SHARPE_INSUFFICIENT",)
    assert weak.execution_allowed is False


def test_selection_overfit_blocks_train_winners_that_fail_oos() -> None:
    training = ((3.0, 1.0), (1.0, 3.0), (4.0, 1.0), (1.0, 4.0))
    oos = ((-2.0, 1.0), (1.0, -2.0), (-3.0, 1.0), (1.0, -3.0))
    report = assess_selection_overfit(training, oos)
    assert report.overfit_probability == 1.0
    assert report.blockers == ("BACKTEST_SELECTION_OVERFIT_HIGH",)

    insufficient = assess_selection_overfit(training[:2], oos[:2])
    assert "INSUFFICIENT_SELECTION_SPLITS" in insufficient.blockers


def test_overfit_contracts_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        replace(
            WalkForwardConfig(train_size=4, test_size=2, step_size=2),
            purge_size=-1,
        )
    with pytest.raises(ValueError, match="matrices must align"):
        assess_selection_overfit(((1.0, 2.0),), ())
    with pytest.raises(ValueError, match="three returns"):
        assess_deflated_sharpe((0.1, 0.2), hypothesis_count=1)
    with pytest.raises(ValueError, match="finite"):
        assess_deflated_sharpe((0.1, 0.2, float("nan")), hypothesis_count=1)
    with pytest.raises(ValueError, match="candidate dimensions"):
        assess_selection_overfit(((1.0,),), ((1.0,),))
    with pytest.raises(ValueError, match="finite"):
        assess_selection_overfit(
            ((1.0, float("inf")),),
            ((1.0, 2.0),),
        )
    with pytest.raises(ValueError, match="bounded"):
        assess_selection_overfit(((1.0, 2.0),), ((1.0, 2.0),), maximum_probability=2)


def test_deflated_sharpe_constant_return_branch_is_fail_closed() -> None:
    positive = assess_deflated_sharpe((0.1, 0.1, 0.1), hypothesis_count=1)
    assert positive.deflated_sharpe_probability == 1.0
    assert positive.blockers == ()
    flat = assess_deflated_sharpe((0.0, 0.0, 0.0), hypothesis_count=1)
    assert flat.deflated_sharpe_probability == 0.0
    assert flat.blockers == ("DEFLATED_SHARPE_INSUFFICIENT",)

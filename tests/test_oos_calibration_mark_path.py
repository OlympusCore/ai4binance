"""Chronological calibration and isolated native-mark replay regression proofs."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from ai4binance.research.backtesting import FuturesBacktestConfig, FuturesBacktestEngine
from ai4binance.research.backtesting.models import BacktestExitReason, TradeDirection
from ai4binance.research.virtual_market import VirtualMarket, load_acceptance_policy
from ai4binance.research.virtual_runtime_risk import (
    FuturesRiskBracket,
    isolated_liquidation_price,
)
from ai4binance.validation.oos_calibration import (
    CalibratedMarketAssessment,
    evaluate_calibrated_market_acceptance,
)
from ai4binance.validation.overfit import (
    OosProbabilityObservation,
    calibrated_holdout,
    fit_oos_calibration,
)
from ai4binance.whale_fusion.models import DerivativesMetric
from tests.test_futures_backtest_engine import (
    START,
    _candle,
    _dataset,
    _intent,
    _one_signal_provider,
    _point,
)
from tests.test_virtual_market_acceptance import _evidence

D = Decimal
BRACKETS = (
    FuturesRiskBracket(D(0), D(1000), 20, D(".005"), D(0)),
    FuturesRiskBracket(D(1000), D(100000), 10, D(".01"), D(5)),
)


@pytest.mark.parametrize(
    ("long", "margin", "expected"),
    [
        (True, "20", D(80) / D(".995")),
        (False, "20", D(120) / D("1.005")),
        (True, "15", D(85) / D(".995")),
    ],
)
def test_liquidation_solves_mark_maintenance_equation(
    long: bool, margin: str, expected: Decimal
) -> None:
    assert (
        isolated_liquidation_price(
            long=long,
            entry=D(100),
            quantity=D(1),
            wallet_margin=D(margin),
            brackets=BRACKETS,
        )
        == expected
    )


def test_liquidation_changes_tier_and_rejects_discontinuous_brackets() -> None:
    price = isolated_liquidation_price(
        long=False,
        entry=D(100),
        quantity=D(10),
        wallet_margin=D(200),
        brackets=BRACKETS,
    )
    assert price == D(1205) / D("10.1")
    with pytest.raises(ValueError, match="discontinuous"):
        isolated_liquidation_price(
            long=True,
            entry=D(100),
            quantity=D(1),
            wallet_margin=D(20),
            brackets=(BRACKETS[0], replace(BRACKETS[1], cumulative_maintenance=D(0))),
        )


@pytest.mark.parametrize(
    ("mark_low", "reason"),
    [("79", BacktestExitReason.LIQUIDATION), ("94", BacktestExitReason.END_OF_DATA)],
)
def test_mark_excursion_controls_liquidation_independently_of_contract(
    mark_low: str, reason: BacktestExitReason
) -> None:
    candles = tuple(_candle(i, high="102", low="98", close="100") for i in range(3))
    data = _dataset(candles, funding=((2, "0"),))
    marks = tuple(
        replace(
            _point(DerivativesMetric.MARK_PRICE, c.timestamp, "100"),
            attributes={
                "mark_open": "100",
                "mark_high": "102",
                "mark_low": mark_low if i == 1 else "98",
            },
        )
        for i, c in enumerate(candles)
    )
    data = replace(
        data,
        derivatives=replace(
            data.derivatives,
            series={**data.derivatives.series, DerivativesMetric.MARK_PRICE: marks},
        ),
    )
    engine = FuturesBacktestEngine(
        FuturesBacktestConfig(
            leverage=5, require_mark_price_path=True, maintenance_brackets=BRACKETS
        )
    )
    signal = _intent(START, TradeDirection.LONG, stop_loss="90", take_profit="120")
    result = engine.run(dataset=data, signal_provider=_one_signal_provider(signal))
    assert result.trades[0].exit_reason == reason
    assert result.audit_events[0]["model"] == "ISOLATED_MARK_OHLC_TIERED_V1"
    assert not engine.execution_allowed
    changed = replace(marks[1], attributes={**marks[1].attributes, "mark_low": "78"})
    altered = replace(
        data,
        derivatives=replace(
            data.derivatives,
            series={
                **data.derivatives.series,
                DerivativesMetric.MARK_PRICE: (marks[0], changed, marks[2]),
            },
        ),
    )
    assert data.dataset_sha256 != altered.dataset_sha256


def test_strict_replay_never_substitutes_contract_for_missing_mark() -> None:
    engine = FuturesBacktestEngine(
        FuturesBacktestConfig(
            require_mark_price_path=True, maintenance_brackets=BRACKETS
        )
    )
    with pytest.raises(ValueError, match="mark-price"):
        engine.run(
            dataset=_dataset(tuple(_candle(i) for i in range(3))),
            signal_provider=lambda _: None,
        )


def observation(
    index: int, probability: float, outcome: bool
) -> OosProbabilityObservation:
    stamp = START + timedelta(days=index)
    return OosProbabilityObservation(
        str(index),
        "frozen-model",
        "fold-1",
        "RANGE",
        START - timedelta(days=1),
        stamp,
        stamp + timedelta(hours=1),
        stamp + timedelta(hours=2),
        probability,
        outcome,
        1.0 if outcome else -1.0,
    )


def test_calibration_fits_train_only_and_enforces_purged_holdout() -> None:
    rows = tuple(
        observation(i, p, y)
        for i, (p, y) in enumerate(
            ((0.1, False), (0.2, True), (0.3, False), (0.8, True))
        )
    )
    fitted = START + timedelta(days=4)
    model = fit_oos_calibration(
        rows, dataset_sha256="a" * 64, fitted_through=fitted, minimum_observations=4
    )
    assert model.probabilities == (0.0, 0.5, 1.0)
    held = (observation(6, 0.2, True), observation(7, 0.8, False))
    transformed, report = calibrated_holdout(
        model, held, embargo=timedelta(days=1), minimum_observations=3
    )
    assert [o.probability for o in transformed] == [0.5, 1.0]
    assert report.blockers == ("OOS_PROBABILITY_SAMPLE_INSUFFICIENT",)
    assert not report.execution_allowed
    assert model == fit_oos_calibration(
        tuple(reversed(rows)),
        dataset_sha256="a" * 64,
        fitted_through=fitted,
        minimum_observations=4,
    )
    with pytest.raises(ValueError, match="purge"):
        calibrated_holdout(
            model,
            (observation(5, 0.2, True),),
            embargo=timedelta(days=1),
            minimum_observations=1,
        )
    with pytest.raises(ValueError, match="closed horizons"):
        fit_oos_calibration(
            rows, dataset_sha256="a" * 64, fitted_through=START, minimum_observations=4
        )


def test_calibration_rejects_duplicate_identity_and_single_class() -> None:
    row = observation(0, 0.5, True)
    with pytest.raises(ValueError, match="unique"):
        fit_oos_calibration(
            (row, row),
            dataset_sha256="a" * 64,
            fitted_through=START + timedelta(days=2),
            minimum_observations=1,
        )
    with pytest.raises(ValueError, match="both classes"):
        fit_oos_calibration(
            (row,),
            dataset_sha256="a" * 64,
            fitted_through=START + timedelta(days=2),
            minimum_observations=1,
        )


def test_calibrated_acceptance_preserves_market_veto_and_replay_binding() -> None:
    calibration = tuple(observation(i, 0.5, i % 2 == 0) for i in range(100))
    holdout = tuple(observation(i, 0.5, True) for i in range(110, 230))
    performance = _evidence(
        VirtualMarket.USD_M_FUTURES,
        configured_start_at=START + timedelta(days=110),
        feature_warmup_start=START,
        last_replayed_at=START + timedelta(days=475),
        observation_days=365,
        replay_state_hash="b" * 64,
        peak_margin_utilization=D(".3"),
        liquidation_events=1,
    )

    def assess(replay_hash: str) -> CalibratedMarketAssessment:
        return evaluate_calibrated_market_acceptance(
            calibration_rows=calibration,
            holdout_rows=holdout,
            dataset_sha256="a" * 64,
            replay_state_hash=replay_hash,
            fitted_through=START + timedelta(days=101),
            embargo=timedelta(days=1),
            performance=performance,
            policy=load_acceptance_policy(),
            hypothesis_count=20,
        )

    result = assess("b" * 64)
    assert "FUTURES_LIQUIDATION_OCCURRED" in result.blockers
    assert result.block_statistics.adjusted_alpha == pytest.approx(0.0025)
    assert not result.execution_allowed
    with pytest.raises(ValueError, match="exact replay binding"):
        assess("c" * 64)


def test_funding_uses_settlement_mark_and_moves_liquidation_boundary() -> None:
    candles = tuple(_candle(i, high="102", low="98", close="100") for i in range(3))
    data = _dataset(candles, funding=((2, ".15"),))
    marks = tuple(
        replace(
            _point(DerivativesMetric.MARK_PRICE, c.timestamp, "100"),
            attributes={
                "mark_open": "110" if i == 2 else "100",
                "mark_high": "112",
                "mark_low": "95" if i == 2 else "98",
            },
        )
        for i, c in enumerate(candles)
    )
    data = replace(
        data,
        derivatives=replace(
            data.derivatives,
            series={
                **data.derivatives.series,
                DerivativesMetric.MARK_PRICE: marks,
            },
        ),
    )
    engine = FuturesBacktestEngine(
        FuturesBacktestConfig(
            leverage=5,
            quantity=D(1),
            require_mark_price_path=True,
            maintenance_brackets=BRACKETS,
        )
    )
    result = engine.run(
        dataset=data,
        signal_provider=_one_signal_provider(
            _intent(START, TradeDirection.LONG, stop_loss="90", take_profit="120"),
        ),
    )
    assert result.trades[0].exit_reason is BacktestExitReason.LIQUIDATION
    assert result.trades[0].funding_cost_usdt == D("16.5")

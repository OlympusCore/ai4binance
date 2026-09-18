"""Research contracts reject inconsistent geometry and promotion evidence."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting.models import (
    BacktestConfig,
    BacktestIntent,
    PerformanceEngineReport,
    PreVetoOpportunityLedger,
    PreVetoOpportunityRecord,
    TradeDirection,
    VirtualMarketFunnelTelemetry,
)
from ai4binance.schemas import OHLCVCandle, OOSValidationStatus
from ai4binance.validation import ParameterSet, WalkForwardValidator
from ai4binance.validation.integrity import IntegrityStatus
from ai4binance.validation.models import WalkForwardReport
from ai4binance.validation.scalable_integrity import analyze_scalable_lookahead
from tests.test_scalable_integrity import _candles
from tests.test_walk_forward import (
    GOOD,
    NOW,
    candles,
    passing_config,
    regime_classifier,
    strategy_factory,
)


@pytest.mark.parametrize(
    ("name", "values", "message"),
    [
        ("", (("x", 1.0),), "name and values"),
        ("x", (), "name and values"),
        ("x", ((" ", 1.0),), "keys"),
        ("x", (("x", 1.0), ("x", 2.0)), "keys"),
        ("x", (("x", float("nan")),), "finite"),
    ],
)
def test_parameter_candidates_require_unambiguous_finite_values(
    name: str, values: tuple[tuple[str, float], ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ParameterSet(name, values)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("min_folds", 1, "two folds"),
        ("min_regime_count", 1, "two regimes"),
        ("min_oos_trades", 0, "trade count"),
        ("min_effective_sample_size", 1, "sample size"),
        ("min_profitable_fold_ratio", float("nan"), "ratios"),
        ("max_oos_drawdown", 1.1, "ratios"),
        ("max_turnover", -0.1, "ratios"),
        ("min_oos_net_return", float("inf"), "return must be finite"),
        ("confidence_level", 0.8, "confidence level"),
    ],
)
def test_walk_forward_configuration_preserves_evidence_thresholds(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(passing_config(), **{field: cast(Any, value)})


@pytest.fixture
def approved_report() -> WalkForwardReport:
    return WalkForwardValidator().validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles(12),
        parameters=(GOOD,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=passing_config(),
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("report_id", "", "identity"),
        ("symbol", "", "identity"),
        ("timeframe", "", "identity"),
        ("created_at", datetime(2026, 1, 1), "timezone-aware"),
        ("promotion_status", "LIVE", "only stage"),
        ("blockers", ("MISSING_EVIDENCE",), "cannot contain"),
        ("oos_validation_status", OOSValidationStatus.UNVALIDATED, "consistent"),
        ("promotion_status", ValidationStatus.RESEARCH_ONLY, "consistent"),
    ],
)
def test_walk_forward_report_rejects_contradictory_publication(
    approved_report: WalkForwardReport, field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(approved_report, **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("trailing_multiplier", Decimal(0), "trailing_multiplier"),
        ("tick_size", Decimal(0), "tick_size"),
        ("step_size", Decimal(0), "step_size"),
        ("minimum_notional", Decimal(0), "minimum_notional"),
    ],
)
def test_backtest_execution_geometry_must_be_positive(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(BacktestConfig(), **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("strategy_id", "", "strategy_id"),
        ("breakeven_trigger_r", Decimal(0), "breakeven"),
        ("trailing_atr_multiple", Decimal(0), "trailing_atr"),
        ("maximum_holding_bars", 0, "holding"),
        ("entry_score", Decimal(-1), "entry_score"),
        ("evidence_score", Decimal(-1), "evidence_score"),
        ("dge_status", " ", "dge_status"),
        ("blocker_history", ("A", "A"), "unique"),
        ("blocker_history", (" ",), "blanks"),
        ("funnel_stages", ("DISCOVERED", "DISCOVERED"), "unique"),
        ("funnel_stages", (), "empty"),
        ("funnel_stages", ("FILLED",), "unsupported"),
    ],
)
def test_backtest_intent_rejects_invalid_lifecycle_metadata(
    field: str, value: object, message: str
) -> None:
    intent = BacktestIntent("signal", NOW, Decimal(95), Decimal(105), Decimal(2))
    with pytest.raises(ValueError, match=message):
        replace(intent, **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("stage_counts", (), "canonical order"),
        ("reason_code_counts", (("A", 1), ("A", 2)), "unique"),
        ("reason_code_counts", ((" ", 1),), "blank"),
        ("reason_code_counts", (("A", 0),), "positive"),
    ],
)
def test_funnel_telemetry_preserves_count_identity(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(VirtualMarketFunnelTelemetry(), **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("observation_id", "", "identity"),
        ("observed_at", datetime(2026, 1, 1), "timezone-aware"),
        ("take_profit_levels", (), "evidence"),
        ("entry_reason", (), "evidence"),
        ("stop_loss", Decimal(0), "positive"),
        ("blockers", ("LATE_VETO",), "post-veto"),
        ("assessment_status", "APPROVED", "pending"),
        ("execution_allowed", True, "authority"),
        ("promotion_status", "LIVE", "authority"),
        ("live_eligibility_status", "LIVE", "authority"),
    ],
)
def test_pre_veto_record_cannot_claim_later_authority(
    field: str, value: object, message: str
) -> None:
    record = PreVetoOpportunityRecord(
        "observation",
        "signal",
        "snapshot",
        "strategy",
        "1",
        "TREND",
        "BTCUSDT",
        "SPOT",
        TradeDirection.LONG,
        NOW,
        Decimal(100),
        Decimal(95),
        (Decimal(105),),
        ("SIGNAL",),
        "PASS",
    )
    with pytest.raises(ValueError, match=message):
        replace(record, **{field: cast(Any, value)})
    with pytest.raises(ValueError, match="unique"):
        PreVetoOpportunityLedger((record, record))


def test_performance_report_cannot_replace_market_conjunction() -> None:
    with pytest.raises(ValueError, match="anti-masking"):
        PerformanceEngineReport(system_acceptance_operator="SPOT_OR_FUTURES")


@pytest.mark.parametrize("mode", ["missing", "checkpoint", "refinement_shape"])
def test_scalable_integrity_refines_missing_and_inconsistent_prefixes(
    mode: str,
) -> None:
    def compute(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        size = len(values)
        if mode == "refinement_shape" and size == 3:
            return ()
        result: list[float | None] = [1.0] * size
        if size == 64:
            result[3] = None if mode == "missing" else 2.0
        return tuple(result)

    report = analyze_scalable_lookahead(
        _candles(64), compute, minimum_history=2, tail_points=1
    )
    assert report.status is IntegrityStatus.BLOCKED
    assert report.execution_allowed is False
    if mode == "refinement_shape":
        assert report.blockers == ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)
        assert report.first_violation_index is None
    else:
        assert report.blockers == ("LOOKAHEAD_BIAS_DETECTED",)
        assert report.first_violation_index == 3


def test_scalable_integrity_accepts_matching_warmup_and_rejects_authority_drift() -> (
    None
):
    report = analyze_scalable_lookahead(
        _candles(64), lambda values: (None,) * len(values)
    )
    assert report.status is IntegrityStatus.PASSED
    for change in (
        {"status": IntegrityStatus.BLOCKED},
        {"promotion_allowed": False},
        {"execution_allowed": True},
    ):
        with pytest.raises(ValueError, match=r"status|authority"):
            replace(report, **change)

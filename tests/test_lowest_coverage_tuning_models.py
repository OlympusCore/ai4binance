"""Fail-closed coverage for immutable tuning model contracts."""

from datetime import UTC, datetime
from typing import cast

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle
from ai4binance.tuning.models import (
    CandidateEvaluation,
    ParameterDomain,
    SearchSpace,
    SensitivityAssessment,
    StrategyParameterTournamentReport,
    StrategyProfileCandidate,
    TournamentConfig,
    TournamentContext,
    TournamentEntry,
    TuningConfig,
    TuningReport,
)
from ai4binance.validation import ParameterSet, WalkForwardConfig

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def walk_forward_config() -> WalkForwardConfig:
    return WalkForwardConfig(train_size=4, test_size=2, step_size=2)


def parameter_set() -> ParameterSet:
    return ParameterSet("bounded", (("ema_fast", 10.0),))


def test_parameter_domains_and_search_spaces_reject_unbounded_inputs() -> None:
    with pytest.raises(ValueError, match="not approved"):
        ParameterDomain("unapproved", (1.0,))
    with pytest.raises(ValueError, match="non-empty and finite"):
        ParameterDomain("ema_fast", ())
    with pytest.raises(ValueError, match="non-empty and finite"):
        ParameterDomain("ema_fast", (float("inf"),))
    with pytest.raises(ValueError, match="unique"):
        ParameterDomain("ema_fast", (10.0, 10.0))
    with pytest.raises(ValueError, match="outside approved bounds"):
        ParameterDomain("ema_fast", (1.0,))
    with pytest.raises(ValueError, match="must be integers"):
        ParameterDomain("ema_fast", (10.5,))
    with pytest.raises(ValueError, match="between 1 and 4096"):
        SearchSpace((ParameterDomain("ema_fast", (10.0,)),), max_candidates=0)
    with pytest.raises(ValueError, match="non-empty and unique"):
        SearchSpace(())
    with pytest.raises(ValueError, match="exceeds"):
        SearchSpace((ParameterDomain("ema_fast", (10.0, 20.0)),), max_candidates=1)
    with pytest.raises(ValueError, match="neighbor count"):
        TuningConfig(walk_forward_config(), min_neighbor_count=0)
    with pytest.raises(ValueError, match="sensitivity ratios"):
        TuningConfig(walk_forward_config(), min_neighbor_pass_ratio=1.1)


def test_tuning_report_rejects_invalid_identity_timestamp_status_and_blockers() -> None:
    values: dict[str, object] = {
        "report_id": "tuning-1",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "created_at": NOW,
        "search_space": SearchSpace((ParameterDomain("ema_fast", (10.0,)),)),
        "config": TuningConfig(walk_forward_config()),
        "evaluations": (cast(CandidateEvaluation, object()),),
        "selected_parameters": parameter_set(),
        "sensitivity": cast(SensitivityAssessment, object()),
        "promotion_status": ValidationStatus.RESEARCH_ONLY,
        "blockers": ("EVIDENCE_MISSING",),
    }
    invalid_cases = (
        ({"report_id": " "}, "identity and evaluations"),
        ({"evaluations": ()}, "identity and evaluations"),
        ({"created_at": datetime(2026, 9, 15)}, "timezone-aware"),
        ({"promotion_status": ValidationStatus.PAPER_APPROVED}, "only produce"),
        ({"blockers": ()}, "promotion and blockers"),
        (
            {
                "promotion_status": ValidationStatus.STAGED_CANDIDATE,
                "blockers": ("EVIDENCE_MISSING",),
            },
            "promotion and blockers",
        ),
    )
    for overrides, message in invalid_cases:
        attempt = dict(values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            TuningReport(**attempt)  # type: ignore[arg-type]

    staged = dict(values)
    staged.update(
        {"promotion_status": ValidationStatus.STAGED_CANDIDATE, "blockers": ()}
    )
    assert TuningReport(**staged).promotion_status is ValidationStatus.STAGED_CANDIDATE  # type: ignore[arg-type]


def test_tournament_contracts_remain_research_only_and_non_executable() -> None:
    with pytest.raises(ValueError, match="context identity"):
        TournamentContext(" ", "1h", ())
    with pytest.raises(ValueError, match="at least two candles"):
        TournamentContext("BTCUSDT", "1h", cast(tuple[OHLCVCandle, ...], (object(),)))
    assert (
        len(
            TournamentContext(
                "BTCUSDT",
                "1h",
                cast(tuple[OHLCVCandle, ...], (object(), object())),
            ).candles
        )
        == 2
    )
    with pytest.raises(ValueError, match="profile_id"):
        StrategyProfileCandidate(" ", parameter_set())
    assert (
        StrategyProfileCandidate("candidate-1", parameter_set()).profile_id
        == "candidate-1"
    )
    with pytest.raises(ValueError, match="diversity counts"):
        TournamentConfig(walk_forward_config(), min_symbol_count=0)
    with pytest.raises(ValueError, match="trade count"):
        TournamentConfig(walk_forward_config(), min_trade_count=0)
    with pytest.raises(ValueError, match="ratios"):
        TournamentConfig(walk_forward_config(), min_stress_return_ratio=1.1)

    entry_values: dict[str, object] = {
        "profile_id": "candidate-1",
        "parameters": parameter_set(),
        "evaluations": (),
        "net_return_after_costs": 0.0,
        "profit_factor": None,
        "expectancy": 0.0,
        "max_drawdown": 0.0,
        "sharpe": None,
        "sortino": None,
        "trade_count": 0,
        "win_rate": 0.0,
        "average_r": 0.0,
        "tail_loss": 0.0,
        "parameter_stability": 0.0,
        "regime_breakdown": (),
        "blockers": (),
    }
    for overrides, message in (
        ({"profile_id": " "}, "profile identity"),
        ({"status": "PAPER_APPROVED"}, "RESEARCH_CANDIDATE"),
        ({"promotion_status": ValidationStatus.STAGED_CANDIDATE}, "auto-promote"),
        ({"execution_allowed": True}, "cannot allow execution"),
    ):
        attempt = dict(entry_values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            TournamentEntry(**attempt)  # type: ignore[arg-type]
    assert TournamentEntry(**entry_values).execution_allowed is False  # type: ignore[arg-type]

    report_values: dict[str, object] = {
        "report_id": "tournament-1",
        "created_at": NOW,
        "config": TournamentConfig(walk_forward_config()),
        "entries": (cast(TournamentEntry, object()),),
    }
    for overrides, message in (
        ({"report_id": " "}, "identity and entries"),
        ({"entries": ()}, "identity and entries"),
        ({"created_at": datetime(2026, 9, 15)}, "timezone-aware"),
        ({"status": "PAPER_APPROVED"}, "RESEARCH_CANDIDATE"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ):
        attempt = dict(report_values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            StrategyParameterTournamentReport(**attempt)  # type: ignore[arg-type]
    assert StrategyParameterTournamentReport(**report_values).execution_allowed is False  # type: ignore[arg-type]

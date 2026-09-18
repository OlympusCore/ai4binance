from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from inspect import signature
from pathlib import Path
from typing import Any, TypedDict, Unpack, cast

import pytest

from ai4binance.governance.blockers import (
    BlockerClass,
    BlockerDomain,
    BlockerEffect,
    BlockerSeverity,
)
from ai4binance.governance.execution_authority import (
    ExecutionAutomationMode,
    ExecutionSurface,
)
from ai4binance.research.virtual_market import (
    ACCEPTANCE_BLOCKER_CANONICAL_CODES,
    STATUS_BLOCKER_CLASSES,
    AcceptancePolicy,
    AcceptanceStatus,
    CostStressScenarioEvidence,
    DailyEquityPoint,
    MarketAcceptanceResult,
    MarketPerformanceEvidence,
    RegimeAttribution,
    ResearchCandidateResult,
    SystemResearchAcceptance,
    TwoStageProfitabilityEvidence,
    VirtualMarket,
    calculate_daily_returns,
    calculate_daily_sharpe,
    canonical_acceptance_blocker_codes,
    evaluate_market_acceptance,
    evaluate_research_candidate,
    evaluate_two_stage_profitability_evidence,
    load_acceptance_blocker_definitions,
    load_acceptance_policy,
    render_system_acceptance_markdown,
    required_acceptance_blocker_mappings,
    required_system_status_blockers,
)

START = datetime(2025, 1, 1, tzinfo=UTC)
WARMUP = START - timedelta(days=120)
END = datetime(2026, 1, 1, tzinfo=UTC)

# Canonical expectations
# These tuples keep blocker and taxonomy expectations visible near the top.
REQUIRED_ACCEPTANCE_BLOCKER_MAPPINGS = (
    "REPLAY_STATE_HASH_MISSING",
    "DECISION_REPRODUCIBILITY_FAILED",
    "CRITICAL_DATA_GAPS_PRESENT",
    "DUPLICATE_ECONOMIC_EVENTS_APPLIED",
    "LOOKAHEAD_VIOLATIONS_PRESENT",
    "FUTURES_LIQUIDATION_OCCURRED",
    "DAILY_SHARPE_UNAVAILABLE",
    "PROFIT_FACTOR_UNAVAILABLE",
    "FUTURES_MARGIN_UTILIZATION_UNAVAILABLE",
)
REQUIRED_SYSTEM_STATUS_BLOCKERS = (
    "SYSTEM_FAIL",
    "SYSTEM_INSUFFICIENT_EVIDENCE",
    "SYSTEM_DATA_UNAVAILABLE",
    "SYSTEM_NON_REPRODUCIBLE",
    "SYSTEM_NOT_EVALUATED",
)
OVERLOADED_FUTURES_BLOCKERS = (
    "CRITICAL_DATA_GAPS_PRESENT",
    "OBSERVATION_WINDOW_INSUFFICIENT",
    "TRADE_SAMPLE_INSUFFICIENT",
    "DAILY_SHARPE_UNAVAILABLE",
    "MAX_DRAWDOWN_ABOVE_THRESHOLD",
    "FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD",
)
OVERLOADED_FUTURES_CANONICAL_CODES = (
    "DATA.SNAPSHOT_INCOMPLETE",
    "VAL.OOS_NOT_VALIDATED",
    "EVID.CRITICAL_EVIDENCE_MISSING",
    "RISK.RISK_LIMIT_EXCEEDED",
)
MARKET_BLOCKER_METADATA_EXPECTATIONS = (
    (
        "DATA.SNAPSHOT_INCOMPLETE",
        BlockerDomain.DATA,
        BlockerClass.CONDITIONAL_BLOCKER,
        BlockerSeverity.HIGH,
        (
            BlockerEffect.RESEARCH_ONLY,
            BlockerEffect.DECISION_CYCLE_BLOCKED,
        ),
    ),
    (
        "EVID.CRITICAL_EVIDENCE_MISSING",
        BlockerDomain.EVIDENCE,
        None,
        BlockerSeverity.HIGH,
        (BlockerEffect.PROMOTION_BLOCKED,),
    ),
    (
        "VAL.OOS_NOT_VALIDATED",
        BlockerDomain.VALIDATION,
        None,
        BlockerSeverity.HIGH,
        (BlockerEffect.RESEARCH_ONLY,),
    ),
    (
        "RISK.RISK_LIMIT_EXCEEDED",
        BlockerDomain.RISK,
        BlockerClass.HARD_BLOCKER,
        BlockerSeverity.CRITICAL,
        (BlockerEffect.PAPER_ORDER_BLOCKED,),
    ),
)
SYSTEM_STRATEGY_METADATA_EXPECTATION = (
    "STRAT.NOT_APPROVED_FOR_STAGE",
    BlockerDomain.STRATEGY,
    BlockerClass.CONDITIONAL_BLOCKER,
    BlockerSeverity.HIGH,
    (
        BlockerEffect.RESEARCH_ONLY,
        BlockerEffect.CANDIDATE_BLOCKED,
    ),
)


# Taxonomy assertion helpers
# These helpers keep canonical blocker assertions compact and consistent.
def _definitions_by_code(blockers: tuple[str, ...]) -> dict[str, Any]:
    return {
        definition.blocker_code: definition
        for definition in load_acceptance_blocker_definitions(blockers)
    }


def _resolved_blocker_codes(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        definition.blocker_code
        for definition in load_acceptance_blocker_definitions(blockers)
    )


def _assert_canonical_blocker_codes(
    blockers: tuple[str, ...],
    canonical_blocker_codes: tuple[str, ...],
) -> None:
    assert _resolved_blocker_codes(blockers) == canonical_blocker_codes


def _assert_resolved_blocker_effects_present(blockers: tuple[str, ...]) -> None:
    assert all(
        definition.effects
        for definition in load_acceptance_blocker_definitions(blockers)
    )


def _assert_required_blocker_whitelist(
    actual: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    assert actual == expected
    assert set(actual) <= set(ACCEPTANCE_BLOCKER_CANONICAL_CODES)


def _assert_definition_metadata(
    definitions: dict[str, Any],
    blocker_code: str,
    *,
    domain: BlockerDomain,
    blocker_class: BlockerClass | None = None,
    severity: BlockerSeverity,
    effects: tuple[BlockerEffect, ...],
) -> None:
    definition = definitions[blocker_code]

    assert definition.domain is domain
    if blocker_class is not None:
        assert definition.blocker_class is blocker_class
    assert definition.severity is severity
    for effect in effects:
        assert effect in definition.effects


def _assert_fail_closed_authority(
    result: MarketAcceptanceResult | ResearchCandidateResult,
) -> None:
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def _assert_acceptance_outcome(
    result: MarketAcceptanceResult,
    *,
    status: AcceptanceStatus,
    blocker: str,
) -> None:
    assert result.status is status
    assert any(item.startswith(blocker) for item in result.blockers)
    assert result.canonical_blocker_codes


def _assert_value_error(message: str, operation: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=message):
        operation()


class _EvidenceOverrides(TypedDict, total=False):
    session_id: str
    portfolio_id: str
    initial_equity_usdt: Decimal
    ending_equity_usdt: Decimal
    net_return: Decimal
    max_drawdown: Decimal
    daily_sharpe: Decimal | None
    profit_factor: Decimal | None
    modeled_cost_expectancy_usdt: Decimal
    oos_expectancy_usdt: Decimal
    completed_trades: int
    observation_days: int
    critical_data_gaps: int
    critical_data_quality_failure: bool
    applied_duplicate_economic_events: int
    lookahead_violations: int
    liquidation_events: int
    fragile_edge: bool
    cost_stress_evidence: tuple[CostStressScenarioEvidence, ...]
    regime_attribution: tuple[RegimeAttribution, ...]
    peak_margin_utilization: Decimal | None
    generation: int
    configured_start_at: datetime
    feature_warmup_start: datetime
    last_replayed_at: datetime
    replay_state_hash: str | None
    decision_reproducibility_rate: Decimal
    execution_allowed: bool
    promotion_status: str
    live_eligibility_status: str


# Scenario builders
# These builders create reusable market-acceptance inputs for focused tests.
def _accepted_futures_result(
    **overrides: Unpack[_EvidenceOverrides],
) -> MarketAcceptanceResult:
    payload: _EvidenceOverrides = {
        "peak_margin_utilization": Decimal("0.30"),
    }
    payload.update(overrides)
    return evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            **payload,
        )
    )


def _failed_spot_result(
    **overrides: Unpack[_EvidenceOverrides],
) -> MarketAcceptanceResult:
    payload: _EvidenceOverrides = {
        "net_return": Decimal("-0.20"),
        "ending_equity_usdt": Decimal("800"),
    }
    payload.update(overrides)
    return evaluate_market_acceptance(
        _evidence(
            VirtualMarket.SPOT,
            **payload,
        )
    )


def _overloaded_futures_result(
    **overrides: Unpack[_EvidenceOverrides],
) -> MarketAcceptanceResult:
    payload: _EvidenceOverrides = {
        "critical_data_gaps": 1,
        "observation_days": 100,
        "completed_trades": 10,
        "daily_sharpe": None,
        "max_drawdown": Decimal("0.20"),
        "peak_margin_utilization": Decimal("0.80"),
    }
    payload.update(overrides)
    return evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            **payload,
        )
    )


# System scenario helpers
# These helpers centralize SystemResearchAcceptance setup and failure checks.
def _failed_system_acceptance() -> SystemResearchAcceptance:
    return SystemResearchAcceptance.derive(
        _failed_spot_result(),
        _accepted_futures_result(),
    )


def _assert_invalid_system_acceptance(
    *,
    message: str,
    status: AcceptanceStatus,
    blockers: tuple[str, ...],
) -> None:
    spot = evaluate_market_acceptance(_evidence(VirtualMarket.SPOT))
    futures = evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            peak_margin_utilization=Decimal("0.20"),
        )
    )
    _assert_value_error(
        message,
        lambda: SystemResearchAcceptance(
            spot=spot,
            futures=futures,
            status=status,
            blockers=blockers,
            evidence_refs=("spot", "futures"),
        ),
    )


def test_virtual_market_acceptance_enforces_bounded_market_capital() -> None:
    spot = _evidence(
        VirtualMarket.SPOT,
        session_id="spot-session",
        portfolio_id="spot-portfolio",
    )
    futures = _evidence(
        VirtualMarket.USD_M_FUTURES,
        session_id="futures-session",
        portfolio_id="futures-portfolio",
        peak_margin_utilization=Decimal("0.40"),
    )

    assert spot.initial_equity_usdt == Decimal("1000")
    assert futures.initial_equity_usdt == Decimal("1000")
    assert evaluate_market_acceptance(spot).status is AcceptanceStatus.PASS
    assert evaluate_market_acceptance(futures).status is AcceptanceStatus.PASS

    assert _evidence(
        VirtualMarket.SPOT, initial_equity_usdt=Decimal("500")
    ).initial_equity_usdt == Decimal("500")
    with pytest.raises(ValueError, match="positive and at most 1000 USDT"):
        _evidence(VirtualMarket.SPOT, initial_equity_usdt=Decimal("2000"))


def test_system_acceptance_prevents_spot_futures_cross_market_masking() -> None:
    spot_fail = _failed_spot_result()
    futures_pass = evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            net_return=Decimal("1.50"),
            ending_equity_usdt=Decimal("2500"),
            peak_margin_utilization=Decimal("0.30"),
        )
    )

    first = SystemResearchAcceptance.derive(spot_fail, futures_pass)

    assert first.status is AcceptanceStatus.FAIL
    assert "NET_RETURN_NOT_POSITIVE" in first.blockers
    assert "SYSTEM_FAIL" in first.blockers

    spot_pass = evaluate_market_acceptance(_evidence(VirtualMarket.SPOT))
    futures_fail = evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            net_return=Decimal("-0.25"),
            ending_equity_usdt=Decimal("750"),
            peak_margin_utilization=Decimal("0.20"),
        )
    )

    second = SystemResearchAcceptance.derive(spot_pass, futures_fail)

    assert second.status is AcceptanceStatus.FAIL
    assert "NET_RETURN_NOT_POSITIVE" in second.blockers
    assert "SYSTEM_FAIL" in second.blockers


def test_system_acceptance_payload_and_markdown_keep_markets_separate() -> None:
    spot = _failed_spot_result()
    futures = _accepted_futures_result()
    system = SystemResearchAcceptance.derive(spot, futures)

    payload: dict[str, Any] = system.to_payload()
    markdown = render_system_acceptance_markdown(system)

    serialized = json.dumps(payload, sort_keys=True)

    assert payload["surface_kind"] == "SYSTEM_ACCEPTANCE"
    assert payload["status"] == "FAIL"
    assert payload["spot"]["market"] == "SPOT"
    assert payload["spot"]["status"] == "FAIL"
    assert payload["futures"]["market"] == "USD_M_FUTURES"
    assert payload["futures"]["status"] == "PASS"
    assert "combined_pnl" not in serialized
    assert "combined_sharpe" not in serialized
    assert "combined_equity" not in serialized
    assert "Spot Acceptance" in markdown
    assert "USD_M Futures Acceptance" in markdown
    assert "SYSTEM_FAIL" in markdown
    assert "RESEARCH_ONLY" in markdown
    assert "LIVE_ORDER_BLOCKED" in markdown


def test_research_candidate_stage_requires_profitability_cost_stress_and_regimes() -> (
    None
):
    result = evaluate_research_candidate(
        _evidence(
            VirtualMarket.SPOT,
            modeled_cost_expectancy_usdt=Decimal("0"),
            oos_expectancy_usdt=Decimal("-1"),
            cost_stress_evidence=(),
            regime_attribution=(),
        )
    )

    assert result.status is AcceptanceStatus.FAIL
    assert "MODELED_COST_EXPECTANCY_NOT_POSITIVE" in result.blockers
    assert "OOS_EXPECTANCY_NOT_POSITIVE" in result.blockers
    assert "COST_STRESS_EVIDENCE_MISSING" in result.blockers
    assert "REGIME_LEVEL_ATTRIBUTION_MISSING" in result.blockers
    _assert_fail_closed_authority(result)


def test_research_candidate_stage_fails_closed_for_data_quality_and_fragile_edge() -> (
    None
):
    result = evaluate_research_candidate(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            critical_data_quality_failure=True,
            fragile_edge=True,
            peak_margin_utilization=Decimal("0.30"),
        )
    )

    assert result.status is AcceptanceStatus.FAIL
    assert "CRITICAL_DATA_QUALITY_FAILURE_PRESENT" in result.blockers
    assert "FRAGILE_EDGE" in result.blockers
    _assert_fail_closed_authority(result)


def test_research_candidate_stage_cannot_bypass_existing_final_acceptance() -> None:
    evidence = _evidence(
        VirtualMarket.SPOT,
        daily_sharpe=Decimal("0.40"),
        profit_factor=Decimal("1.10"),
    )

    combined = evaluate_two_stage_profitability_evidence(evidence)

    assert combined.research_candidate.stage == "RESEARCH_CANDIDATE"
    assert combined.research_candidate.status is AcceptanceStatus.PASS
    assert combined.final_acceptance.status is AcceptanceStatus.FAIL
    assert "DAILY_SHARPE_BELOW_THRESHOLD" in combined.final_acceptance.blockers
    assert "PROFIT_FACTOR_BELOW_THRESHOLD" in combined.final_acceptance.blockers
    assert combined.execution_allowed is False
    assert combined.promotion_status == "RESEARCH_ONLY"
    parameters = signature(SystemResearchAcceptance.derive).parameters
    assert "combined_pnl" not in parameters
    assert "combined_sharpe" not in parameters
    assert "combined_equity" not in parameters


def test_futures_acceptance_fails_closed_for_liquidation_or_missing_margin() -> None:
    liquidation = evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            liquidation_events=1,
            peak_margin_utilization=Decimal("0.20"),
        )
    )
    missing_margin = evaluate_market_acceptance(_evidence(VirtualMarket.USD_M_FUTURES))

    assert liquidation.status is AcceptanceStatus.FAIL
    assert "FUTURES_LIQUIDATION_OCCURRED" in liquidation.blockers
    assert missing_margin.status is AcceptanceStatus.DATA_UNAVAILABLE
    assert "FUTURES_MARGIN_UTILIZATION_UNAVAILABLE" in missing_margin.blockers


def test_daily_equity_returns_and_sharpe_are_portfolio_level_statistics() -> None:
    curve = (
        DailyEquityPoint(START, Decimal("1000")),
        DailyEquityPoint(START + timedelta(days=1), Decimal("1010")),
        DailyEquityPoint(START + timedelta(days=2), Decimal("1005")),
        DailyEquityPoint(START + timedelta(days=3), Decimal("1030")),
    )

    returns = calculate_daily_returns(curve)
    sharpe = calculate_daily_sharpe(returns)

    assert returns == (
        Decimal("0.01"),
        Decimal("-0.004950495049504950495049505"),
        Decimal("0.02487562189054726368159204"),
    )
    assert sharpe is not None
    assert sharpe.is_finite()

    with pytest.raises(ValueError, match="strictly increasing"):
        calculate_daily_returns((curve[1], curve[0]))


def test_virtual_market_acceptance_policy_loads_from_governed_config() -> None:
    policy = load_acceptance_policy()

    assert policy.policy_id == "virtual-market-research-acceptance-v1"
    assert policy.minimum_observation_days == 365
    assert policy.minimum_completed_trades == 100
    assert policy.research_candidate.minimum_modeled_cost_expectancy_usdt == Decimal(
        "0"
    )
    assert policy.research_candidate.minimum_oos_expectancy_usdt == Decimal("0")
    assert policy.research_candidate.required_cost_stress_scenarios == (
        "BASE",
        "COST_1_5X",
        "COST_2X",
    )
    assert policy.research_candidate.require_regime_level_attribution is True
    assert policy.minimum_daily_sharpe == Decimal("1.00")
    assert policy.minimum_profit_factor == Decimal("1.25")
    assert policy.maximum_spot_drawdown == Decimal("0.15")
    assert policy.maximum_futures_drawdown == Decimal("0.12")
    assert policy.maximum_futures_margin_utilization == Decimal("0.75")
    assert policy.hard_fail_gates == (
        "REPLAY_STATE_HASH_MISSING",
        "DECISION_REPRODUCIBILITY_FAILED",
        "CRITICAL_DATA_GAPS_PRESENT",
        "DUPLICATE_ECONOMIC_EVENTS_APPLIED",
        "LOOKAHEAD_VIOLATIONS_PRESENT",
        "FUTURES_LIQUIDATION_OCCURRED",
    )
    assert policy.system_acceptance_operator == "SPOT_PASS_AND_FUTURES_PASS"
    assert policy.combined_pnl_gate_allowed is False
    assert policy.combined_sharpe_gate_allowed is False
    assert policy.combined_equity_gate_allowed is False
    assert policy.execution_allowed is False
    assert policy.promotion_status == "RESEARCH_ONLY"
    assert policy.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert policy.execution_surface is ExecutionSurface.VIRTUAL_MARKET
    assert policy.authority_profile_id == "VIRTUAL_AUTONOMOUS_SIMULATION_V1"
    assert (
        policy.automation_mode is ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION
    )


def test_virtual_market_acceptance_policy_rejects_authority(
    tmp_path: Path,
) -> None:
    unsafe_policy = tmp_path / "unsafe-acceptance.yaml"
    unsafe_policy.write_text(
        """
schema_version: "1.0"
policy_id: unsafe-acceptance
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: "1.00"
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
authority:
  execution_allowed: true
  promotion_status: LIVE_APPROVED
  live_eligibility_status: LIVE_APPROVED
  execution_surface: BINANCE_MARKET
  authority_profile_id: BINANCE_MANUAL_ONLY_V1
  automation_mode: HUMAN_HAND_MANUAL_ONLY
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cannot authorize execution"):
        load_acceptance_policy(unsafe_policy)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            """
schema_version: "1.0"
policy_id: virtual-market-research-acceptance-v1
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: "1.00"
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: false
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: VIRTUAL_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
            "hard fail gates must match the canonical set",
        ),
        (
            """
schema_version: "1.0"
policy_id: virtual-market-research-acceptance-v1
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: "1.00"
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
  - DECISION_REPRODUCIBILITY_FAILED
  - CRITICAL_DATA_GAPS_PRESENT
  - DUPLICATE_ECONOMIC_EVENTS_APPLIED
  - LOOKAHEAD_VIOLATIONS_PRESENT
  - FUTURES_LIQUIDATION_OCCURRED
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: true
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: VIRTUAL_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
            "cannot enable combined market gates",
        ),
    ],
)
def test_virtual_market_acceptance_policy_rejects_governance_drift(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    drifted_policy = tmp_path / "drifted-acceptance.yaml"
    drifted_policy.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_acceptance_policy(drifted_policy)


def test_virtual_market_acceptance_policy_rejects_non_virtual_surface(
    tmp_path: Path,
) -> None:
    unsafe_policy = tmp_path / "non-virtual-surface.yaml"
    unsafe_policy.write_text(
        """
schema_version: "1.0"
policy_id: virtual-market-research-acceptance-v1
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: "1.00"
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
  - DECISION_REPRODUCIBILITY_FAILED
  - CRITICAL_DATA_GAPS_PRESENT
  - DUPLICATE_ECONOMIC_EVENTS_APPLIED
  - LOOKAHEAD_VIOLATIONS_PRESENT
  - FUTURES_LIQUIDATION_OCCURRED
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: false
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: BINANCE_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must target VIRTUAL_MARKET"):
        load_acceptance_policy(unsafe_policy)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"session_id": " "}, "identity is required"),
        ({"configured_start_at": datetime(2025, 1, 1)}, "timezone-aware"),
        ({"feature_warmup_start": END}, "warm-up cannot start after"),
        ({"generation": 0}, "generation must be positive"),
        ({"ending_equity_usdt": Decimal("0")}, "ending equity must be positive"),
        ({"net_return": Decimal("-1.01")}, "net return must be at least -1"),
        ({"max_drawdown": Decimal("1.01")}, "max drawdown must be between"),
        ({"profit_factor": Decimal("-0.1")}, "profit factor cannot be negative"),
        (
            {"peak_margin_utilization": Decimal("-0.1")},
            "peak margin utilization cannot be negative",
        ),
        (
            {"decision_reproducibility_rate": Decimal("1.01")},
            "decision reproducibility rate must be between",
        ),
        ({"completed_trades": -1}, "completed trades cannot be negative"),
        ({"critical_data_gaps": -1}, "critical data gaps cannot be negative"),
        (
            {"modeled_cost_expectancy_usdt": Decimal("NaN")},
            "modeled cost expectancy must be finite",
        ),
        (
            {"oos_expectancy_usdt": Decimal("Infinity")},
            "OOS expectancy must be finite",
        ),
        (
            {"applied_duplicate_economic_events": -1},
            "applied duplicate economic events cannot be negative",
        ),
        ({"lookahead_violations": -1}, "lookahead violations cannot be negative"),
        ({"liquidation_events": -1}, "liquidation events cannot be negative"),
        (
            {"market": VirtualMarket.SPOT, "liquidation_events": 1},
            "Spot evidence cannot contain liquidation events",
        ),
        (
            {"market": VirtualMarket.SPOT, "peak_margin_utilization": Decimal("0.1")},
            "Spot evidence cannot contain margin utilization",
        ),
        (
            {
                "cost_stress_evidence": (
                    CostStressScenarioEvidence("BASE", Decimal("1")),
                    CostStressScenarioEvidence("BASE", Decimal("2")),
                )
            },
            "cost stress evidence scenarios must be unique",
        ),
        ({"daily_sharpe": Decimal("NaN")}, "daily Sharpe must be finite"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "LIVE_APPROVED"}, "cannot authorize execution"),
        (
            {"execution_surface": ExecutionSurface.BINANCE_MARKET},
            "must target VIRTUAL_MARKET",
        ),
    ],
)
def test_market_performance_evidence_rejects_invalid_inputs(
    overrides: dict[str, Any],
    message: str,
) -> None:
    payload = dict(overrides)
    market = payload.pop("market", VirtualMarket.USD_M_FUTURES)
    with pytest.raises(ValueError, match=message):
        _evidence(market, **payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"policy_id": " "}, "identity is required"),
        ({"minimum_observation_days": 0}, "minimum evidence must be positive"),
        ({"minimum_completed_trades": 0}, "minimum evidence must be positive"),
        ({"minimum_daily_sharpe": Decimal("Infinity")}, "must be finite"),
        ({"minimum_profit_factor": Decimal("NaN")}, "must be finite"),
        ({"maximum_spot_drawdown": Decimal("1.1")}, "must be between"),
        ({"maximum_futures_drawdown": Decimal("-0.1")}, "must be between"),
        ({"maximum_futures_margin_utilization": Decimal("1.1")}, "must be between"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"live_eligibility_status": "LIVE_APPROVED"}, "cannot authorize execution"),
        (
            {"execution_surface": ExecutionSurface.BINANCE_MARKET},
            "must target VIRTUAL_MARKET",
        ),
    ],
)
def test_acceptance_policy_rejects_invalid_inputs(
    overrides: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AcceptancePolicy(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"blockers": ("A", "A")}, "blockers must be unique"),
        ({"blockers": (" ",)}, "blockers cannot contain blanks"),
        ({"evidence_refs": ("ref", "ref")}, "evidence refs must be unique"),
        ({"evidence_refs": (" ",)}, "evidence refs cannot contain blanks"),
        ({"policy_id": " "}, "policy identity is required"),
        (
            {"status": AcceptanceStatus.PASS, "blockers": ("BLOCKED",)},
            "passing market acceptance cannot contain blockers",
        ),
        (
            {"status": AcceptanceStatus.FAIL, "blockers": ()},
            "blocked market acceptance requires blockers",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
        (
            {"execution_surface": ExecutionSurface.BINANCE_MARKET},
            "must target VIRTUAL_MARKET",
        ),
    ],
)
def test_market_acceptance_result_rejects_invalid_inputs(
    overrides: dict[str, Any],
    message: str,
) -> None:
    payload: dict[str, Any] = {
        "market": VirtualMarket.SPOT,
        "status": AcceptanceStatus.FAIL,
        "blockers": ("BLOCKED",),
        "evidence_refs": ("ref",),
        "policy_id": "policy",
    }
    payload.update(overrides)

    with pytest.raises(ValueError, match=message):
        MarketAcceptanceResult(**payload)


def test_market_performance_evidence_rejects_unsupported_market() -> None:
    evidence = _evidence(VirtualMarket.SPOT)

    with pytest.raises(
        ValueError,
        match="virtual market must be SPOT or USD_M_FUTURES",
    ):
        replace(evidence, market=cast(VirtualMarket, "OPTIONS"))


def test_market_acceptance_result_rejects_unsupported_market() -> None:
    with pytest.raises(
        ValueError,
        match="virtual market must be SPOT or USD_M_FUTURES",
    ):
        MarketAcceptanceResult(
            market=cast(VirtualMarket, "OPTIONS"),
            status=AcceptanceStatus.FAIL,
            blockers=("BLOCKED",),
            evidence_refs=("ref",),
            policy_id="policy",
        )


def test_research_candidate_result_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="must be RESEARCH_CANDIDATE"):
        ResearchCandidateResult(
            market=VirtualMarket.SPOT,
            stage="WRONG",
            status=AcceptanceStatus.FAIL,
            blockers=("BLOCKED",),
            evidence_refs=("ref",),
            policy_id="policy",
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        ResearchCandidateResult(
            market=VirtualMarket.SPOT,
            stage="RESEARCH_CANDIDATE",
            status=AcceptanceStatus.FAIL,
            blockers=("BLOCKED",),
            evidence_refs=("ref",),
            policy_id="policy",
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="must target VIRTUAL_MARKET"):
        ResearchCandidateResult(
            market=VirtualMarket.SPOT,
            stage="RESEARCH_CANDIDATE",
            status=AcceptanceStatus.FAIL,
            blockers=("BLOCKED",),
            evidence_refs=("ref",),
            policy_id="policy",
            execution_surface=ExecutionSurface.BINANCE_MARKET,
        )


def test_research_candidate_result_rejects_unsupported_market() -> None:
    with pytest.raises(
        ValueError,
        match="virtual market must be SPOT or USD_M_FUTURES",
    ):
        ResearchCandidateResult(
            market=cast(VirtualMarket, "OPTIONS"),
            stage="RESEARCH_CANDIDATE",
            status=AcceptanceStatus.FAIL,
            blockers=("BLOCKED",),
            evidence_refs=("ref",),
            policy_id="policy",
        )


def test_two_stage_profitability_evidence_rejects_market_mismatch() -> None:
    with pytest.raises(ValueError, match="must target one market"):
        TwoStageProfitabilityEvidence(
            research_candidate=evaluate_research_candidate(
                _evidence(VirtualMarket.SPOT)
            ),
            final_acceptance=evaluate_market_acceptance(
                _evidence(
                    VirtualMarket.USD_M_FUTURES,
                    peak_margin_utilization=Decimal("0.30"),
                )
            ),
        )


def test_system_acceptance_rejects_wrong_market_and_unsafe_authority() -> None:
    spot = evaluate_market_acceptance(_evidence(VirtualMarket.SPOT))
    futures = evaluate_market_acceptance(
        _evidence(
            VirtualMarket.USD_M_FUTURES,
            peak_margin_utilization=Decimal("0.20"),
        )
    )

    with pytest.raises(ValueError, match="requires Spot acceptance evidence"):
        SystemResearchAcceptance.derive(futures, futures)
    with pytest.raises(ValueError, match="requires Futures acceptance evidence"):
        SystemResearchAcceptance.derive(spot, spot)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        SystemResearchAcceptance(
            spot=spot,
            futures=futures,
            status=AcceptanceStatus.PASS,
            blockers=(),
            evidence_refs=("spot", "futures"),
            execution_allowed=True,
        )


@pytest.mark.parametrize(
    ("overrides", "expected_status", "expected_blocker"),
    [
        (
            {"decision_reproducibility_rate": Decimal("0.99")},
            AcceptanceStatus.NON_REPRODUCIBLE,
            "DECISION_REPRODUCIBILITY_FAILED",
        ),
        ({"critical_data_gaps": 1}, AcceptanceStatus.DATA_UNAVAILABLE, "CRITICAL"),
        (
            {"applied_duplicate_economic_events": 1},
            AcceptanceStatus.FAIL,
            "DUPLICATE_ECONOMIC_EVENTS_APPLIED",
        ),
        (
            {"lookahead_violations": 1},
            AcceptanceStatus.FAIL,
            "LOOKAHEAD_VIOLATIONS_PRESENT",
        ),
        (
            {"observation_days": 100},
            AcceptanceStatus.INSUFFICIENT_EVIDENCE,
            "OBSERVATION_WINDOW_INSUFFICIENT",
        ),
        (
            {"completed_trades": 10},
            AcceptanceStatus.INSUFFICIENT_EVIDENCE,
            "TRADE_SAMPLE_INSUFFICIENT",
        ),
        (
            {"daily_sharpe": Decimal("0.5")},
            AcceptanceStatus.FAIL,
            "DAILY_SHARPE_BELOW_THRESHOLD",
        ),
        (
            {"profit_factor": Decimal("1.0")},
            AcceptanceStatus.FAIL,
            "PROFIT_FACTOR_BELOW_THRESHOLD",
        ),
        (
            {"max_drawdown": Decimal("0.20")},
            AcceptanceStatus.FAIL,
            "MAX_DRAWDOWN_ABOVE_THRESHOLD",
        ),
        (
            {
                "market": VirtualMarket.USD_M_FUTURES,
                "peak_margin_utilization": Decimal("0.80"),
            },
            AcceptanceStatus.FAIL,
            "FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD",
        ),
    ],
)
def test_market_acceptance_maps_blockers_to_fail_closed_statuses(
    overrides: dict[str, Any],
    expected_status: AcceptanceStatus,
    expected_blocker: str,
) -> None:
    payload = dict(overrides)
    market = payload.pop("market", VirtualMarket.SPOT)
    result = evaluate_market_acceptance(_evidence(market, **payload))

    _assert_acceptance_outcome(
        result,
        status=expected_status,
        blocker=expected_blocker,
    )
    _assert_fail_closed_authority(result)


def test_market_acceptance_status_blocker_inventory_is_canonical() -> None:
    assert STATUS_BLOCKER_CLASSES == (
        (
            AcceptanceStatus.NON_REPRODUCIBLE,
            (
                "REPLAY_STATE_HASH_MISSING",
                "DECISION_REPRODUCIBILITY_FAILED",
            ),
        ),
        (
            AcceptanceStatus.DATA_UNAVAILABLE,
            (
                "CRITICAL_DATA_GAPS_PRESENT",
                "DAILY_SHARPE_UNAVAILABLE",
                "PROFIT_FACTOR_UNAVAILABLE",
                "FUTURES_MARGIN_UTILIZATION_UNAVAILABLE",
            ),
        ),
    )


def test_market_acceptance_blockers_resolve_to_canonical_registry() -> None:
    result = _overloaded_futures_result()

    assert result.blockers == OVERLOADED_FUTURES_BLOCKERS
    assert result.canonical_blocker_codes == OVERLOADED_FUTURES_CANONICAL_CODES
    _assert_canonical_blocker_codes(result.blockers, result.canonical_blocker_codes)
    _assert_resolved_blocker_effects_present(result.blockers)


def test_system_acceptance_synthetic_blocker_has_canonical_taxonomy() -> None:
    system = _failed_system_acceptance()

    assert "SYSTEM_FAIL" in system.blockers
    assert system.canonical_blocker_codes == ("STRAT.NOT_APPROVED_FOR_STAGE",)
    _assert_canonical_blocker_codes(system.blockers, system.canonical_blocker_codes)


def test_market_acceptance_blocker_registry_metadata_is_consistent() -> None:
    result = _overloaded_futures_result()

    definitions = _definitions_by_code(result.blockers)

    for expectation in MARKET_BLOCKER_METADATA_EXPECTATIONS:
        _assert_definition_metadata(
            definitions,
            expectation[0],
            domain=expectation[1],
            blocker_class=expectation[2],
            severity=expectation[3],
            effects=expectation[4],
        )


def test_system_acceptance_synthetic_blocker_registry_metadata_is_consistent() -> None:
    system = _failed_system_acceptance()
    definitions = _definitions_by_code(system.blockers)

    _assert_definition_metadata(
        definitions,
        SYSTEM_STRATEGY_METADATA_EXPECTATION[0],
        domain=SYSTEM_STRATEGY_METADATA_EXPECTATION[1],
        blocker_class=SYSTEM_STRATEGY_METADATA_EXPECTATION[2],
        severity=SYSTEM_STRATEGY_METADATA_EXPECTATION[3],
        effects=SYSTEM_STRATEGY_METADATA_EXPECTATION[4],
    )


def test_virtual_market_acceptance_blocker_inventory_has_taxonomy_bridge() -> None:
    definitions = load_acceptance_blocker_definitions(
        tuple(ACCEPTANCE_BLOCKER_CANONICAL_CODES)
    )

    assert "GOV.UNKNOWN_CONTROL_CLASSIFICATION" not in {
        definition.blocker_code for definition in definitions
    }
    assert len(definitions) == len(set(ACCEPTANCE_BLOCKER_CANONICAL_CODES.values()))


# fmt: off
def test_virtual_market_acceptance_blocker_mapping_covers_hard_fail_and_status_codes() -> None:  # noqa: E501
# fmt: on
    required_blockers = required_acceptance_blocker_mappings()

    _assert_required_blocker_whitelist(
        required_blockers,
        REQUIRED_ACCEPTANCE_BLOCKER_MAPPINGS,
    )

# fmt: off
def test_unknown_virtual_market_acceptance_blocker_fails_closed_to_governance_unknown() -> None:  # noqa: E501
# fmt: on
    assert canonical_acceptance_blocker_codes(("UNKNOWN_BLOCKER",)) == (
        "GOV.UNKNOWN_CONTROL_CLASSIFICATION",
    )


def test_system_acceptance_synthetic_blocker_whitelist_is_canonical() -> None:
    _assert_required_blocker_whitelist(
        required_system_status_blockers(),
        REQUIRED_SYSTEM_STATUS_BLOCKERS,
    )


@pytest.mark.parametrize(
    ("status", "blockers", "message"),
    [
        (
            AcceptanceStatus.FAIL,
            ("SYSTEM_DATA_UNAVAILABLE",),
            "system acceptance synthetic blockers must match status",
        ),
        (
            AcceptanceStatus.FAIL,
            ("SYSTEM_CUSTOM",),
            "system acceptance contains unknown synthetic blocker",
        ),
    ],
)
def test_system_acceptance_rejects_non_derived_synthetic_blockers(
    status: AcceptanceStatus,
    blockers: tuple[str, ...],
    message: str,
) -> None:
    _assert_invalid_system_acceptance(
        message=message,
        status=status,
        blockers=blockers,
    )


def test_market_acceptance_rejects_missing_replay_hash_reference() -> None:
    _assert_value_error(
        "evidence refs cannot contain blanks",
        lambda: evaluate_market_acceptance(
            _evidence(VirtualMarket.SPOT, replay_state_hash=" "),
        ),
    )


def test_daily_equity_helpers_fail_closed_for_short_or_invalid_series() -> None:
    point = DailyEquityPoint(START, Decimal("1000"))

    assert calculate_daily_returns((point,)) == ()
    assert calculate_daily_sharpe(()) is None
    assert calculate_daily_sharpe((Decimal("0.01"), Decimal("0.01"))) is None
    _assert_value_error(
        "equity returns must be finite",
        lambda: calculate_daily_sharpe((Decimal("0.01"), Decimal("NaN"))),
    )


def test_daily_equity_point_rejects_invalid_observations() -> None:
    _assert_value_error(
        "daily equity timestamp must be timezone-aware",
        lambda: DailyEquityPoint(datetime(2025, 1, 1), Decimal("1000")),
    )
    _assert_value_error(
        "daily equity must be positive",
        lambda: DailyEquityPoint(START, Decimal("0")),
    )


@pytest.mark.parametrize(
    ("overrides", "expected_blocker"),
    [
        ({"daily_sharpe": None}, "DAILY_SHARPE_UNAVAILABLE"),
        ({"profit_factor": None}, "PROFIT_FACTOR_UNAVAILABLE"),
    ],
)
def test_market_acceptance_fails_closed_when_core_metrics_are_unavailable(
    overrides: dict[str, Any],
    expected_blocker: str,
) -> None:
    result = evaluate_market_acceptance(_evidence(VirtualMarket.SPOT, **overrides))

    _assert_acceptance_outcome(
        result,
        status=AcceptanceStatus.DATA_UNAVAILABLE,
        blocker=expected_blocker,
    )
    _assert_fail_closed_authority(result)


@pytest.mark.parametrize(
    ("status", "blockers", "message"),
    [
        (
            AcceptanceStatus.PASS,
            ("BLOCKED",),
            "passing system acceptance cannot contain blockers",
        ),
        (
            AcceptanceStatus.FAIL,
            (),
            "blocked system acceptance requires blockers",
        ),
    ],
)
def test_system_acceptance_rejects_inconsistent_blocker_state(
    status: AcceptanceStatus,
    blockers: tuple[str, ...],
    message: str,
) -> None:
    _assert_invalid_system_acceptance(
        message=message,
        status=status,
        blockers=blockers,
    )


def test_acceptance_policy_loader_rejects_oversized_policy(
    tmp_path: Path,
) -> None:
    oversized_policy = tmp_path / "oversized-acceptance.yaml"
    oversized_policy.write_text("x" * 64_001, encoding="utf-8")

    _assert_value_error(
        "exceeds the bounded size",
        lambda: load_acceptance_policy(oversized_policy),
    )


@pytest.mark.parametrize(
    ("content", "error_type", "message"),
    [
        ("[]", ValueError, "must be a mapping"),
        (
            """
schema_version: "1.0"
policy_id: policy
authority: []
minimum_evidence: {}
performance_gates: {}
risk_gates: {}
""",
            ValueError,
            "authority must be a mapping",
        ),
        (
            """
schema_version: "1.0"
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: "1.00"
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
  - DECISION_REPRODUCIBILITY_FAILED
  - CRITICAL_DATA_GAPS_PRESENT
  - DUPLICATE_ECONOMIC_EVENTS_APPLIED
  - LOOKAHEAD_VIOLATIONS_PRESENT
  - FUTURES_LIQUIDATION_OCCURRED
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: false
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: VIRTUAL_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
            ValueError,
            "policy_id is required",
        ),
        (
            """
schema_version: "1.0"
policy_id: policy
minimum_evidence:
  minimum_observation_days: "365"
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: "1.00"
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
  - DECISION_REPRODUCIBILITY_FAILED
  - CRITICAL_DATA_GAPS_PRESENT
  - DUPLICATE_ECONOMIC_EVENTS_APPLIED
  - LOOKAHEAD_VIOLATIONS_PRESENT
  - FUTURES_LIQUIDATION_OCCURRED
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: false
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: VIRTUAL_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
            ValueError,
            "minimum_observation_days must be an integer",
        ),
        (
            """
schema_version: "1.0"
policy_id: policy
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: 1.00
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
  - DECISION_REPRODUCIBILITY_FAILED
  - CRITICAL_DATA_GAPS_PRESENT
  - DUPLICATE_ECONOMIC_EVENTS_APPLIED
  - LOOKAHEAD_VIOLATIONS_PRESENT
  - FUTURES_LIQUIDATION_OCCURRED
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: false
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: VIRTUAL_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
            ValueError,
            "minimum_daily_sharpe must be a string",
        ),
        (
            """
schema_version: "1.0"
policy_id: policy
minimum_evidence:
  minimum_observation_days: 365
  minimum_completed_trades: 100
performance_gates:
  minimum_daily_sharpe: not-a-decimal
  minimum_profit_factor: "1.25"
risk_gates:
  maximum_spot_drawdown: "0.15"
  maximum_futures_drawdown: "0.12"
  maximum_futures_margin_utilization: "0.75"
hard_fail_gates:
  - REPLAY_STATE_HASH_MISSING
  - DECISION_REPRODUCIBILITY_FAILED
  - CRITICAL_DATA_GAPS_PRESENT
  - DUPLICATE_ECONOMIC_EVENTS_APPLIED
  - LOOKAHEAD_VIOLATIONS_PRESENT
  - FUTURES_LIQUIDATION_OCCURRED
anti_masking:
  system_acceptance_operator: SPOT_PASS_AND_FUTURES_PASS
  combined_pnl_gate_allowed: false
  combined_sharpe_gate_allowed: false
  combined_equity_gate_allowed: false
authority:
  execution_allowed: false
  promotion_status: RESEARCH_ONLY
  live_eligibility_status: LIVE_ORDER_BLOCKED
  execution_surface: VIRTUAL_MARKET
  authority_profile_id: VIRTUAL_AUTONOMOUS_SIMULATION_V1
  automation_mode: BOUNDED_AUTONOMOUS_SIMULATION
""",
            InvalidOperation,
            "",
        ),
    ],
)
def test_acceptance_policy_loader_rejects_invalid_contract_shapes(
    tmp_path: Path,
    content: str,
    error_type: type[Exception],
    message: str,
) -> None:
    policy_path = tmp_path / "invalid-acceptance.yaml"
    policy_path.write_text(content, encoding="utf-8")

    if message:
        with pytest.raises(error_type, match=message):
            load_acceptance_policy(policy_path)
    else:
        with pytest.raises(error_type):
            load_acceptance_policy(policy_path)


def _evidence(
    market: VirtualMarket,
    *,
    session_id: str = "session",
    portfolio_id: str = "portfolio",
    initial_equity_usdt: Decimal = Decimal("1000"),
    ending_equity_usdt: Decimal = Decimal("1200"),
    net_return: Decimal = Decimal("0.20"),
    max_drawdown: Decimal = Decimal("0.05"),
    daily_sharpe: Decimal | None = Decimal("1.30"),
    profit_factor: Decimal | None = Decimal("1.40"),
    modeled_cost_expectancy_usdt: Decimal = Decimal("15"),
    oos_expectancy_usdt: Decimal = Decimal("12"),
    completed_trades: int = 120,
    observation_days: int = 370,
    critical_data_gaps: int = 0,
    critical_data_quality_failure: bool = False,
    applied_duplicate_economic_events: int = 0,
    lookahead_violations: int = 0,
    liquidation_events: int = 0,
    fragile_edge: bool = False,
    cost_stress_evidence: tuple[CostStressScenarioEvidence, ...] = (
        CostStressScenarioEvidence("BASE", Decimal("15")),
        CostStressScenarioEvidence("COST_1_5X", Decimal("10")),
        CostStressScenarioEvidence("COST_2X", Decimal("5")),
    ),
    regime_attribution: tuple[RegimeAttribution, ...] = (
        RegimeAttribution("TREND", 70, Decimal("14")),
        RegimeAttribution("RANGE", 50, Decimal("9")),
    ),
    peak_margin_utilization: Decimal | None = None,
    generation: int = 1,
    configured_start_at: datetime = START,
    feature_warmup_start: datetime = WARMUP,
    last_replayed_at: datetime = END,
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET,
    replay_state_hash: str | None = None,
    decision_reproducibility_rate: Decimal = Decimal("1"),
    execution_allowed: bool = False,
    promotion_status: str = "RESEARCH_ONLY",
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED",
) -> MarketPerformanceEvidence:
    return MarketPerformanceEvidence(
        market=market,
        session_id=session_id,
        portfolio_id=portfolio_id,
        generation=generation,
        configured_start_at=configured_start_at,
        feature_warmup_start=feature_warmup_start,
        last_replayed_at=last_replayed_at,
        initial_equity_usdt=initial_equity_usdt,
        ending_equity_usdt=ending_equity_usdt,
        net_return=net_return,
        max_drawdown=max_drawdown,
        daily_sharpe=daily_sharpe,
        profit_factor=profit_factor,
        modeled_cost_expectancy_usdt=modeled_cost_expectancy_usdt,
        oos_expectancy_usdt=oos_expectancy_usdt,
        completed_trades=completed_trades,
        observation_days=observation_days,
        critical_data_gaps=critical_data_gaps,
        critical_data_quality_failure=critical_data_quality_failure,
        applied_duplicate_economic_events=applied_duplicate_economic_events,
        lookahead_violations=lookahead_violations,
        liquidation_events=liquidation_events,
        fragile_edge=fragile_edge,
        cost_stress_evidence=cost_stress_evidence,
        regime_attribution=regime_attribution,
        peak_margin_utilization=peak_margin_utilization,
        replay_state_hash=(
            replay_state_hash
            if replay_state_hash is not None
            else f"hash-{market.value.lower()}"
        ),
        decision_reproducibility_rate=decision_reproducibility_rate,
        execution_allowed=execution_allowed,
        promotion_status=promotion_status,
        live_eligibility_status=live_eligibility_status,
        execution_surface=execution_surface,
    )

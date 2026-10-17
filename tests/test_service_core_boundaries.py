"""TEST_ONLY rejection contracts for existing ServiceCore orchestration ports."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import ResearchApplicationService, ResearchStage
from ai4binance.application.research import ResearchStageStatus
from ai4binance.ops.jobs import (
    JobCapability,
    JobSideEffect,
    RunnerAdmissionStatus,
    assess_runner_admission,
    local_advisory_fixture_runner_manifest,
)
from ai4binance.reporting import to_primitive
from ai4binance.research import VirtualMarket
from ai4binance.research.virtual_runtime import VirtualPositionLifecycleStatus
from ai4binance.research_runtime import (
    HistoricalMarketEquityCurve,
    HistoricalMarketReplayRunner,
    _require_replay_utc,
    build_research_application_service,
)
from tests.test_cli import public_snapshot
from tests.test_historical_replay_runner import START, _cycle_fixture, _snapshot
from tests.test_local_qwen_workbench import _admitted_fixture_request
from tests.test_research_application import (
    _RuntimeReadyAnalysis,
    _RuntimeReadyOrchestrator,
    _RuntimeReadyOutlook,
)


@pytest.mark.parametrize(
    ("error_type", "diagnostic"),
    [
        (ArithmeticError, "ARITHMETIC_ERROR"),
        (AttributeError, "ATTRIBUTE_ERROR"),
        (KeyError, "KEY_ERROR"),
        (OSError, "PERSISTENCE"),
        (RuntimeError, "RUNTIME_ERROR"),
        (TypeError, "TYPE_ERROR"),
        (ValueError, "VALUE_ERROR"),
        (None, "TYPE_ERROR"),
    ],
)
def test_governance_port_failure_cannot_mutate_portfolio_or_expose_error_detail(
    error_type: type[Exception] | None, diagnostic: str
) -> None:
    class UnavailableGovernance:
        def evaluate(self, **kwargs: object) -> object:
            if error_type is not None:
                raise error_type("TEST_ONLY_PRIVATE_FAILURE_DETAIL")
            return object()

    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_governance_evaluator=UnavailableGovernance(),
    ).run(public_snapshot())
    decision = workflow.virtual_runtime_decision
    assert decision is not None
    assert decision.trade_intent is None
    assert decision.portfolio_after == decision.portfolio_before
    assert f"DGE_EVALUATION_ERROR_TYPE:{diagnostic}" in decision.eligibility.blockers
    diagnostic_payload = {"decision": decision, "stages": workflow.stages}
    assert "TEST_ONLY_PRIVATE_FAILURE_DETAIL" not in json.dumps(
        to_primitive(diagnostic_payload)
    )
    assert workflow.execution_allowed is False
    assert workflow.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize("missing", ["risk", "candidates"])
def test_missing_research_inputs_cannot_create_a_runtime_request(missing: str) -> None:
    class IncompleteOrchestrator:
        def analyze(self, snapshot: object) -> _RuntimeReadyAnalysis:
            analysis = _RuntimeReadyAnalysis()
            if missing == "risk":
                analysis.agent_results = {}
            else:
                analysis.candidate_setups = cast(Any, ())
            return analysis

    workflow = build_research_application_service(
        orchestrator=IncompleteOrchestrator(), outlook_engine=_RuntimeReadyOutlook()
    ).run(public_snapshot())
    assert workflow.virtual_runtime_request is None
    assert workflow.virtual_runtime_decision is None
    assert workflow.execution_allowed is False


def test_completed_stage_cannot_carry_hidden_blockers() -> None:
    with pytest.raises(ValueError, match="only blocked research stages"):
        ResearchStage("test_only_stage", ResearchStageStatus.COMPLETED, ("DENY",))


@pytest.mark.parametrize("field", ["symbol", "market_type"])
def test_compiled_context_identity_drift_stops_orchestration(field: str) -> None:
    snapshot = public_snapshot()
    context = SimpleNamespace(
        market_snapshot_id=snapshot.snapshot_id,
        symbol=snapshot.symbol,
        market_type=snapshot.market_type,
    )
    setattr(context, field, "TEST_ONLY_OTHER_IDENTITY")
    with pytest.raises(ValueError, match="must match"):
        EnterpriseOrchestrator._validate_compiled_context(snapshot, cast(Any, context))


@pytest.mark.parametrize("field", ["capability_registry", "capability_bundle_registry"])
def test_orchestrator_rejects_incompatible_capability_catalogs(field: str) -> None:
    wrong = SimpleNamespace(by_id={"test_only_unregistered": object()})
    value = (
        wrong
        if field == "capability_registry"
        else SimpleNamespace(capability_registry=wrong)
    )
    with pytest.raises(ValueError, match="registry must match"):
        EnterpriseOrchestrator(**{field: cast(Any, value)})


def test_dependency_deadlock_cannot_schedule_a_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = EnterpriseOrchestrator()
    monkeypatch.setattr(
        EnterpriseOrchestrator, "_build_bundle_executors", lambda *_: {}
    )
    agent = SimpleNamespace(
        definition=SimpleNamespace(name="self", dependencies=("self",))
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(RuntimeError, match="cannot make progress"):
            orchestrator._run_dependency_layers(
                public_snapshot(), cast(Any, (agent,)), {}, executor
            )


@pytest.mark.parametrize("case", ["empty", "duplicate", "unordered", "intraday"])
def test_daily_equity_evidence_rejects_ambiguous_time_boundaries(case: str) -> None:
    result, _ = _cycle_fixture()
    curve = result.equity_curves[0]
    point = curve.points[0]
    next_day = replace(point, timestamp=point.timestamp + timedelta(days=1))
    points = {
        "empty": (),
        "duplicate": (point, point),
        "unordered": (next_day, point),
        "intraday": (replace(point, timestamp=point.timestamp + timedelta(hours=1)),),
    }[case]
    with pytest.raises(ValueError, match="equity"):
        HistoricalMarketEquityCurve(curve.market, points)


@pytest.mark.parametrize("field", ["observed_at", "symbol", "timeframe"])
def test_replay_execution_context_must_bind_the_exact_snapshot(field: str) -> None:
    replay = _snapshot(START, snapshot_id="test-only-context", execution_context=True)
    context = replay.execution_context
    assert context is not None
    value = {
        "observed_at": START + timedelta(hours=1),
        "symbol": "ETHUSDT",
        "timeframe": "4h",
    }[field]
    with pytest.raises(ValueError, match="execution context"):
        replace(replay, execution_context=replace(context, **{field: cast(Any, value)}))


def test_untyped_replay_execution_metadata_cannot_replace_the_contract() -> None:
    replay = _snapshot(START, snapshot_id="test-only-untyped-context")
    snapshot = replace(
        replay.snapshot, market_metadata={"historical_virtual_execution": {}}
    )
    with pytest.raises(ValueError, match="typed contract"):
        replace(replay, snapshot=snapshot)


@pytest.mark.parametrize(
    ("case", "blocker"),
    [
        ("capabilities", "RUNNER_CAPABILITY_MANIFEST_MISMATCH"),
        ("roots", "RUNNER_CAPABILITY_ROOT_NOT_ALLOWED"),
        ("side_effects", "RUNNER_SIDE_EFFECT_NOT_ALLOWED"),
        ("missing_command", "RUNNER_COMMAND_REF_REQUIRED"),
        ("unrequested_command", "RUNNER_COMMAND_CAPABILITY_REQUIRED"),
    ],
)
def test_runner_admission_rejects_capability_and_command_scope_drift(
    tmp_path: Path, case: str, blocker: str
) -> None:
    manifest = local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    request = _admitted_fixture_request(tmp_path)
    capability = manifest.capability_manifest
    if case == "capabilities":
        capability = replace(
            capability, allowed_capabilities=(JobCapability.READ_REPOSITORY,)
        )
    elif case == "roots":
        capability = replace(capability, allowed_roots=(tmp_path / "artifacts",))
    elif case == "side_effects":
        capability = replace(
            capability,
            allowed_capabilities=(JobCapability.READ_REPOSITORY,),
            side_effect_allowlist=(JobSideEffect.READ_REPOSITORY,),
        )
    elif case == "missing_command":
        request = replace(request, command_ref="")
    else:
        request = replace(
            request, requested_capabilities=(JobCapability.READ_REPOSITORY,)
        )
    manifest = replace(manifest, capability_manifest=capability)
    report = assess_runner_admission(manifest, request, observed_at=START)
    assert report.status is RunnerAdmissionStatus.BLOCKED
    assert blocker in report.blockers
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runner_manifest_rejects_relative_fixture_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        local_advisory_fixture_runner_manifest(Path("relative"), tmp_path / "artifacts")


def test_replay_clock_rejects_timezone_ambiguity() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _require_replay_utc("test_only_event_time", datetime(2025, 1, 1))


@pytest.mark.parametrize(
    "case", ["duplicate_position", "closed_position", "duplicate_curve"]
)
def test_replay_result_rejects_ambiguous_open_state_and_equity(case: str) -> None:
    result, _ = _cycle_fixture()
    assert result.open_positions
    position = result.open_positions[0]
    changes: dict[str, Any]
    if case == "duplicate_position":
        changes = {"open_positions": (position, position)}
    elif case == "closed_position":
        changes = {
            "open_positions": (
                replace(
                    position,
                    status=VirtualPositionLifecycleStatus.CLOSED,
                    remaining_quantity=Decimal("0"),
                ),
            )
        }
    else:
        changes = {"equity_curves": (*result.equity_curves, result.equity_curves[0])}
    with pytest.raises(ValueError, match=r"open position|equity curve"):
        replace(result, **changes)


@pytest.mark.parametrize("case", ["missing_timeframe", "stale_candle"])
def test_position_candle_requires_current_bound_timeframe(case: str) -> None:
    _, cycle = _cycle_fixture()
    position = cycle.managed_position_after
    assert position is not None
    replay = cycle.replay_snapshot
    if case == "missing_timeframe":
        position = replace(position, timeframe="4h")
    else:
        replay = replace(
            replay,
            snapshot=replace(replay.snapshot, created_at=START + timedelta(hours=1)),
        )
    with pytest.raises(
        ValueError, match=r"timeframe requires candle|close at the event"
    ):
        HistoricalMarketReplayRunner._position_candle(replay, position)


def test_futures_lifecycle_cannot_use_an_untyped_execution_context() -> None:
    replay = _snapshot(
        START,
        snapshot_id="test-only-futures-context-missing",
        market=VirtualMarket.USD_M_FUTURES,
    )
    with pytest.raises(ValueError, match="typed execution context"):
        HistoricalMarketReplayRunner._futures_position_context(replay)


def test_replay_cost_inputs_reject_out_of_bounds_fees() -> None:
    replay = _snapshot(
        START, snapshot_id="test-only-invalid-fee", execution_context=True
    )
    context = replay.execution_context
    assert context is not None
    payload = {**context.to_payload(), "fee_ratio": "0.5"}
    snapshot = replace(
        replay.snapshot, market_metadata={"historical_virtual_execution": payload}
    )
    candidate = _RuntimeReadyAnalysis().candidate_setups[0]
    inputs, blockers = ResearchApplicationService._virtual_execution_inputs(
        snapshot, candidate=candidate, market="SPOT"
    )
    assert inputs == {}
    assert blockers == ("VIRTUAL_EXECUTION_CONTEXT_INVALID",)


def test_simulation_costs_reject_spread_outside_the_bounded_model() -> None:
    snapshot = public_snapshot()
    assert snapshot.latest_price is not None
    model = {
        "model_kind": "BOUNDED_SIMULATION_COST_ASSUMPTIONS",
        "snapshot_id": snapshot.snapshot_id,
        "market": snapshot.market_type,
        "observed_at": snapshot.created_at.isoformat(),
        "execution_allowed": False,
        "fee_ratio": "0.001",
        "slippage_ratio": "0.001",
    }
    snapshot = replace(
        snapshot,
        spread=snapshot.latest_price * Decimal("0.05"),
        market_metadata={
            "virtual_cost_model": model,
            "estimated_fee_ratio": "0.001",
            "estimated_slippage_ratio": "0.001",
        },
    )
    inputs, blockers = ResearchApplicationService._virtual_cost_inputs(snapshot)
    assert inputs == {}
    assert blockers == ("VIRTUAL_COST_SPREAD_INVALID",)

"""End-to-end contract tests for the safe research application service."""

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, Protocol, cast

import pytest

from ai4binance.application import (
    ResearchApplicationService,
    ResearchStage,
    ResearchStageStatus,
    ResearchWorkflowResult,
    VirtualMarketRuntime,
    VirtualPortfolioState,
    VirtualRuntimeDecisionStatus,
)
from ai4binance.application.context.memory import GovernedMemoryCycleBridge
from ai4binance.application.learning_loop import ControlledLearningLoop
from ai4binance.core.contracts.virtual_governance import VirtualGovernanceResult
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.domain.research.canonical_cycle import (
    CycleExecutionSurface,
    CycleGovernanceStatus,
)
from ai4binance.governance.dge_engine import DecisionGovernanceEngine
from ai4binance.governance.dge_models import (
    DgeDecisionStatus,
    DgeGovernanceContext,
    DgeTradeCandidate,
    GovernedDecision,
)
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.infrastructure.persistence.memory import JsonlMemoryStore
from ai4binance.learning.engine import ControlledLearningEngine
from ai4binance.learning.storage import LearningStore
from ai4binance.portfolio.wallet import WalletSnapshotService
from ai4binance.reporting import to_primitive
from ai4binance.research_runtime import build_research_application_service
from ai4binance.storage import JsonlAuditStore
from tests.test_cli import public_snapshot
from tests.test_wallet_learning import closed_position


def test_service_composition_checks_architecture_before_constructing_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance import research_runtime

    def reject(*args: object, **kwargs: object) -> None:
        raise ValueError("TEST_ONLY_CORE_BINDING_INVALID")

    def unexpected_runtime() -> None:
        pytest.fail("Runtime constructed before architecture validation")

    monkeypatch.setattr(research_runtime, "load_logical_architecture_registry", reject)
    monkeypatch.setattr(research_runtime, "EnterpriseOrchestrator", unexpected_runtime)
    with pytest.raises(ValueError, match="TEST_ONLY_CORE_BINDING_INVALID"):
        build_research_application_service()


@pytest.mark.parametrize(
    ("status", "blockers", "expected"),
    [
        (None, (), ResearchStageStatus.NOT_RUN),
        (ValidationStatus.UNVALIDATED, (), ResearchStageStatus.BLOCKED),
        (
            ValidationStatus.REJECTED,
            ("TEST_ONLY_OOS_MISSING",),
            ResearchStageStatus.BLOCKED,
        ),
        (ValidationStatus.PAPER_APPROVED, (), ResearchStageStatus.COMPLETED),
        (
            ValidationStatus.PAPER_APPROVED,
            ("TEST_ONLY_RISK_VETO",),
            ResearchStageStatus.BLOCKED,
        ),
    ],
)
def test_validation_stage_reports_only_the_existing_verdict(
    status: ValidationStatus | None,
    blockers: tuple[str, ...],
    expected: ResearchStageStatus,
) -> None:
    analysis = SimpleNamespace(
        final_decision=None
        if status is None
        else SimpleNamespace(validation_status=status, blockers=blockers)
    )
    stage = ResearchApplicationService._validation_stage(analysis)
    assert stage.name == "validation"
    assert stage.status is expected
    assert bool(stage.blockers) is (expected is ResearchStageStatus.BLOCKED)
    # Reporting does not change the verdict or remove its original vetoes.
    if analysis.final_decision is not None:
        assert analysis.final_decision.validation_status is status
        assert analysis.final_decision.blockers == blockers


def test_cycle_snapshot_hash_binds_prices_and_matches_audit(tmp_path: Path) -> None:
    service = build_research_application_service()
    original = public_snapshot()
    assert original.latest_price is not None
    changed = replace(original, latest_price=original.latest_price + Decimal("1"))
    first = service.run(original)
    second = service.run(changed)
    assert first.canonical_cycle is not None
    assert second.canonical_cycle is not None
    assert (
        first.canonical_cycle.canonical_snapshot.payload_sha256
        != second.canonical_cycle.canonical_snapshot.payload_sha256
    )
    audit = JsonlAuditStore(tmp_path / "research.jsonl", tamper_evident=True)
    audited = build_research_application_service(audit_store=audit)
    audited.run(original)
    event = json.loads(audit.path.read_text())
    assert (
        event["payload"]["snapshot_ref"]["sha256"]
        == first.canonical_cycle.canonical_snapshot.payload_sha256
    )
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        audited.run(changed)


def test_research_memory_bridge_binds_context_and_stages_learning(
    tmp_path: Path,
) -> None:
    from tests.test_governed_memory_fabric import _active_memory

    snapshot = public_snapshot()
    record = _active_memory()
    snapshot = replace(snapshot, created_at=record.effective_recorded_at)
    store = JsonlMemoryStore(tmp_path / "memory.jsonl")
    record = replace(record, market_type=snapshot.market_type, symbol=snapshot.symbol)
    store.append(record)
    service = build_research_application_service(
        memory_bridge=GovernedMemoryCycleBridge(store),
        learning_loop=ControlledLearningLoop(
            LearningStore(tmp_path / "learning.json", tmp_path / "learning.jsonl"),
            ControlledLearningEngine(),
        ),
        learning_evidence_provider=_ClosedPaperEvidence(),
    )
    result = service.run(snapshot)
    assert result.compiled_cycle_context is not None
    assert result.compiled_cycle_context.memory_record_ids == (record.memory_id,)
    assert result.memory_candidate_ids
    assert result.canonical_cycle is not None
    assert result.canonical_cycle.execution_allowed is False
    without_memory = build_research_application_service().run(snapshot)
    assert without_memory.canonical_cycle is not None
    assert (
        result.canonical_cycle.shared_state.payload_sha256
        != without_memory.canonical_cycle.shared_state.payload_sha256
    )


def test_research_service_runs_all_safe_stages_and_persists_audit(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "research.jsonl"
    workflow = build_research_application_service(
        audit_store=JsonlAuditStore(audit_path)
    ).run(public_snapshot())

    assert workflow.analysis.snapshot_id == "public-snapshot-1"
    assert workflow.market_outlook.snapshot_id == "public-snapshot-1"
    assert workflow.market_outlook.execution_allowed is False
    assert [stage.name for stage in workflow.stages] == [
        "acquisition",
        "analysis",
        "strategy",
        "risk",
        "validation",
        "virtual_market_execution",
        "learning",
    ]
    assert workflow.stages[-2].status is ResearchStageStatus.BLOCKED
    assert "STRATEGY_NOT_PROMOTED" not in workflow.stages[-2].blockers
    assert "VIRTUAL_MARKET_AUTONOMOUS_EXECUTION_PENDING" not in (
        workflow.stages[-2].blockers
    )
    assert workflow.stages[-1].status is ResearchStageStatus.NOT_RUN
    assert workflow.execution_allowed is False
    assert workflow.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    validation = next(stage for stage in workflow.stages if stage.name == "validation")
    assert validation.status is ResearchStageStatus.BLOCKED
    assert validation.blockers == (
        f"VALIDATION_STATUS:{workflow.analysis.final_decision.validation_status.value}",
    )
    assert workflow.canonical_cycle is not None
    cycle = workflow.canonical_cycle
    assert cycle.cycle_id == "research:public-snapshot-1"
    assert cycle.snapshot_id == "public-snapshot-1"
    assert cycle.execution_surface is CycleExecutionSurface.VIRTUAL_MARKET
    assert cycle.governance_status is CycleGovernanceStatus.NO_TRADE
    assert cycle.execution_plan is None
    assert {
        artifact.snapshot_id
        for artifact in (
            cycle.canonical_snapshot,
            cycle.shared_state,
            *cycle.observations,
            cycle.decision,
            cycle.risk_assessment,
            cycle.governance_result,
            cycle.audit_trail,
        )
    } == {"public-snapshot-1"}
    event = json.loads(audit_path.read_text(encoding="utf-8"))
    assert event["event_type"] == "RESEARCH_WORKFLOW_COMPLETED"
    assert event["payload"]["execution_allowed"] is False
    assert event["payload"]["snapshot_ref"]["snapshot_id"] == "public-snapshot-1"
    assert event["payload"]["analysis_ref"]["agent_result_count"] > 0
    assert event["payload"]["market_outlook_ref"]["snapshot_id"] == (
        "public-snapshot-1"
    )
    assert event["payload"]["canonical_cycle"]["semantic_sha256"] == (
        cycle.semantic_sha256
    )
    assert "snapshot" not in event["payload"]
    assert "analysis" not in event["payload"]
    assert "wallet" not in event["payload"]
    # Full snapshots and account-bearing agent metadata are never embedded.
    assert workflow.canonical_payloads
    assert all(
        item["artifact_kind"]
        in {"DECISION", "GOVERNANCE_RESULT", "AUDIT_TRAIL", "VIRTUAL_SIMULATION_PLAN"}
        for item in workflow.canonical_payloads.values()
        if isinstance(item, dict)
    )
    assert len(audit_path.read_bytes()) < 16_000


def test_large_mandatory_receipt_retains_bounded_exact_explanations(
    tmp_path: Path,
) -> None:
    """Test-only wide receipts reproduce missing explanations in real cycles."""
    service = build_research_application_service()
    snapshot = public_snapshot()
    workflow = service.run(snapshot)
    assert workflow.canonical_cycle is not None
    original = workflow.canonical_cycle
    observation = original.observations[0]
    cycle = replace(
        original,
        observations=tuple(
            replace(observation, artifact_id=f"TEST_ONLY_OBSERVATION_{index:03}")
            for index in range(64)
        ),
    )
    workflow = replace(workflow, canonical_cycle=cycle)
    from ai4binance.infrastructure.persistence.canonical_payloads import (
        CanonicalExplanationStore,
    )

    explanation_store = CanonicalExplanationStore(
        tmp_path / "explanations", boundary=tmp_path
    )
    audit_path = tmp_path / "wide-audit.jsonl"
    service = replace(
        service,
        audit_store=JsonlAuditStore(audit_path),
        canonical_explanation_store=explanation_store,
    )
    service._persist(snapshot, workflow)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))["payload"]
    bodies = cast(dict[str, object], payload["canonical_payloads"])
    assert len(json.dumps(payload["canonical_cycle"]).encode()) > 16_000
    assert payload["canonical_cycle"] == cycle.to_payload()
    assert (
        explanation_store.read(cycle.decision)
        == workflow.canonical_payloads[cycle.decision.artifact_id]
    )
    assert not bodies
    assert all(
        path.stat().st_size <= 16_001
        for path in explanation_store.directory.glob("*.json")
    )
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_research_service_publishes_read_only_market_outlook(tmp_path: Path) -> None:
    from ai4binance.outlook import MarketOutlookArtifactStore

    path = tmp_path / "market-outlook" / "state.json"
    workflow = build_research_application_service(
        outlook_store=MarketOutlookArtifactStore(path)
    ).run(public_snapshot())

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["snapshot_id"] == workflow.market_outlook.snapshot_id
    assert state["execution_allowed"] is False
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_research_service_defaults_virtual_runtime_when_omitted() -> None:
    service = build_research_application_service(virtual_market_runtime=None)

    assert service.virtual_market_runtime is not None


def test_research_service_routes_virtual_runtime_through_application_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_helper(request: object, *, runtime: object | None = None) -> object:
        captured["request"] = request
        captured["runtime"] = runtime
        return SimpleNamespace(
            decision=SimpleNamespace(
                eligibility=SimpleNamespace(
                    blockers=(),
                    status=SimpleNamespace(value="ELIGIBLE"),
                    live_eligibility_status="LIVE_ORDER_BLOCKED",
                ),
                status=SimpleNamespace(value="ORDER_READY"),
                halt_review=None,
                trade_intent=None,
                portfolio_before=None,
                portfolio_after=None,
                audit_refs=("snapshot", "decision", "portfolio"),
            ),
        )

    monkeypatch.setattr(
        "ai4binance.application.research.run_virtual_market_cycle",
        _fake_helper,
    )

    runtime_marker = object()
    dge = _RecordingDge()
    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_market_runtime=runtime_marker,
        virtual_dge_engine=dge,
        virtual_dge_context_builder=_approved_virtual_dge_context,
    ).run(public_snapshot())

    assert captured["runtime"] is runtime_marker
    assert "request" in captured
    request = cast(Any, captured["request"])
    assert len(dge.calls) == 1
    assert dge.calls[0][1].execution_surface is ExecutionSurface.VIRTUAL_MARKET
    assert request.decision_id == dge.decisions[0].decision_id
    assert request.dge_decision == DgeDecisionStatus.APPROVED_PAPER_ONLY.value
    assert request.dge_blockers == ()
    assert request.dge_simulation_allowed is True
    assert workflow.virtual_runtime_decision is not None
    assert workflow.stages[-2].name == "virtual_market_execution"
    assert workflow.stages[-2].status is ResearchStageStatus.COMPLETED


def test_research_contract_rejects_execution_authority() -> None:
    service_result = build_research_application_service().run(public_snapshot())
    with pytest.raises(ValueError, match="cannot grant execution"):
        ResearchWorkflowResult(
            analysis=service_result.analysis,
            market_outlook=service_result.market_outlook,
            stages=service_result.stages,
            execution_allowed=True,
        )


def test_blocked_stage_requires_explicit_blockers() -> None:
    with pytest.raises(ValueError, match="requires blockers"):
        ResearchStage("risk", ResearchStageStatus.BLOCKED)


def test_research_service_runs_idempotent_learning_when_configured(
    tmp_path: Path,
) -> None:
    service = build_research_application_service(
        learning_loop=ControlledLearningLoop(
            LearningStore(tmp_path / "learning.json", tmp_path / "learning.jsonl"),
            ControlledLearningEngine(),
        )
    )

    first = service.run(public_snapshot())
    second = service.run(public_snapshot())

    assert first.learning is not None
    assert first.learning.saved is True
    assert second.learning is not None
    assert second.learning.saved is False
    assert first.stages[-1].status is ResearchStageStatus.COMPLETED
    assert first.execution_allowed is False


class _ClosedPaperEvidence:
    def load(self, snapshot: object) -> dict[str, object]:
        del snapshot
        return {"paper_positions": (closed_position(),)}


def test_research_service_feeds_closed_paper_positions_to_learning(
    tmp_path: Path,
) -> None:
    service = build_research_application_service(
        learning_loop=ControlledLearningLoop(
            LearningStore(tmp_path / "learning.json", tmp_path / "learning.jsonl"),
            ControlledLearningEngine(),
        ),
        learning_evidence_provider=_ClosedPaperEvidence(),
    )

    workflow = service.run(public_snapshot())

    assert workflow.learning is not None
    assert workflow.learning.summary.lessons[0].code == "REVIEW_PREMATURE_TRAILING"
    assert workflow.learning.summary.execution_allowed is False


class _WalletReader:
    def account(self) -> object:
        return {
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": "HOT", "free": "12", "locked": "3"},
                {"asset": "USDT", "free": "100", "locked": "0"},
            ],
        }

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return []


def test_wallet_capture_requires_explicit_opt_in_and_attaches_inventory() -> None:
    with pytest.raises(ValueError, match="explicit wallet service"):
        build_research_application_service(wallet_capture_enabled=True)

    disabled = build_research_application_service(
        wallet_service=WalletSnapshotService(_WalletReader())
    ).run(public_snapshot())
    assert disabled.wallet is None
    assert disabled.analysis.market_snapshot.wallet_summary == {}

    enabled = build_research_application_service(
        wallet_service=WalletSnapshotService(_WalletReader()),
        wallet_capture_enabled=True,
    ).run(public_snapshot())
    assert enabled.wallet is not None
    assert enabled.analysis.market_snapshot.inventory_summary["quantity"] == "15"
    assert enabled.execution_allowed is False


def test_virtual_market_stage_requires_canonical_dge_decision() -> None:
    class _Status:
        value = "SUCCESS"

    class _RiskResult:
        status = _Status()
        blockers = ()

    class _Action:
        value = "BUY"

    class _Decision:
        action = _Action()

    class _Analysis:
        def __init__(self) -> None:
            snapshot = public_snapshot()
            self.blockers = ()
            self.agent_results = {"risk": _RiskResult()}
            self.candidate_setups = (
                TradeCandidate(
                    candidate_id="candidate-1",
                    snapshot_id="snapshot-1",
                    timestamp=snapshot.created_at,
                    symbol="HOTUSDT",
                    timeframe="1h",
                    action=Action.BUY,
                    setup_name="trend_continuation",
                    status=CandidateStatus.READY_FOR_RISK,
                    entry_zone=PriceZone(Decimal("100"), Decimal("100")),
                    invalidation_level=Decimal("95"),
                    stop_loss=Decimal("95"),
                    take_profit_levels=(Decimal("110"),),
                    trailing_stop=Decimal("95"),
                    atr=Decimal("3"),
                    risk_reward=Decimal("2"),
                    score=80,
                    confidence=0.8,
                    promotion_status=ValidationStatus.RESEARCH_ONLY,
                ),
            )
            self.final_decision = _Decision()

    stages = build_research_application_service()._build_stages(_Analysis())
    virtual_stage = next(
        stage for stage in stages if stage.name == "virtual_market_execution"
    )

    assert virtual_stage.status is ResearchStageStatus.BLOCKED
    assert virtual_stage.blockers == ("DGE_SIMULATION_NOT_APPROVED",)


class _SuccessRiskStatus:
    value = "SUCCESS"


class _SuccessRiskResult:
    status: ClassVar[_SuccessRiskStatus] = _SuccessRiskStatus()
    blockers: ClassVar[tuple[str, ...]] = ()
    calculation_metadata: ClassVar[dict[str, object]] = {
        "candidate_id": "candidate-1",
        "approved": True,
        "size_usdt": "700",
        "quantity": "7",
        "risk_amount_usdt": "35",
    }


class _NoTradeAction:
    value = "NO_TRADE"


class _NoTradeDecision:
    action = _NoTradeAction()


class _HasSnapshotId(Protocol):
    snapshot_id: str


class _RuntimeReadyAnalysis:
    def __init__(self) -> None:
        snapshot = public_snapshot()
        self.snapshot_id = snapshot.snapshot_id
        self.market_snapshot = snapshot
        self.blockers = ()
        self.agent_results: dict[str, object] = {"risk": _SuccessRiskResult()}
        self.candidate_setups = (
            TradeCandidate(
                candidate_id="candidate-1",
                snapshot_id=snapshot.snapshot_id,
                timestamp=snapshot.created_at,
                symbol=snapshot.symbol,
                timeframe="1h",
                action=Action.BUY,
                setup_name="trend_continuation",
                status=CandidateStatus.READY_FOR_RISK,
                entry_zone=PriceZone(Decimal("100"), Decimal("100")),
                invalidation_level=Decimal("95"),
                stop_loss=Decimal("95"),
                take_profit_levels=(Decimal("110"),),
                trailing_stop=Decimal("95"),
                atr=Decimal("3"),
                risk_reward=Decimal("2"),
                score=80,
                confidence=0.8,
                promotion_status=ValidationStatus.RESEARCH_ONLY,
            ),
        )
        self.final_decision = _NoTradeDecision()


class _RuntimeReadyOrchestrator:
    def analyze(self, snapshot: object) -> _RuntimeReadyAnalysis:
        del snapshot
        return _RuntimeReadyAnalysis()


class _RuntimeReadyOutlook:
    def build(self, analysis: _HasSnapshotId) -> object:
        snapshot_id = analysis.snapshot_id
        return type(
            "Outlook",
            (),
            {
                "snapshot_id": snapshot_id,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )()


class _RecordingDge:
    def __init__(self) -> None:
        self.calls: list[tuple[DgeTradeCandidate, DgeGovernanceContext]] = []
        self.decisions: list[GovernedDecision] = []
        self._engine = DecisionGovernanceEngine()

    def evaluate(
        self,
        candidate: DgeTradeCandidate,
        context: DgeGovernanceContext,
    ) -> GovernedDecision:
        self.calls.append((candidate, context))
        decision = self._engine.evaluate(candidate, context)
        self.decisions.append(decision)
        return decision


class _FailingDge:
    def evaluate(
        self,
        candidate: DgeTradeCandidate,
        context: DgeGovernanceContext,
    ) -> GovernedDecision:
        del candidate, context
        raise RuntimeError("deterministic test DGE failure")


def _approved_virtual_dge_context(
    snapshot: object,
    analysis: object,
    candidate: object,
    portfolio: object,
) -> DgeGovernanceContext:
    del analysis
    snapshot_value = cast(Any, snapshot)
    candidate_value = cast(Any, candidate)
    portfolio_value = cast(Any, portfolio)
    return DgeGovernanceContext(
        context_id=(
            f"virtual-dge-context:{snapshot_value.snapshot_id}:"
            f"{candidate_value.candidate_id}"
        ),
        data_snapshot_id=str(snapshot_value.snapshot_id),
        semantic_graph_id="semantic:test:approved",
        position_context_ref=str(portfolio_value.portfolio_id),
        wallet_verified=True,
        snapshot_integrity_verified=True,
        data_quality_passed=True,
        required_timeframes_present=True,
        liquidity_approved=True,
        regime_compatible=True,
        mtf_aligned=True,
        structure_valid=True,
        negative_evidence_clear=True,
        oos_approved=True,
        risk_approved=True,
        validation_approved=True,
        execution_feasible=True,
        human_approval_recorded=True,
        no_new_capital_required=True,
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        evidence_refs=("evidence:test:approved",),
        config_hash="config:test:approved",
        evaluation_timestamp_utc=snapshot_value.created_at.isoformat(),
    )


def test_research_service_runs_virtual_runtime_without_wallet_when_dge_approved() -> (
    None
):
    dge = _RecordingDge()
    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_dge_engine=dge,
        virtual_dge_context_builder=_approved_virtual_dge_context,
    ).run(public_snapshot())

    assert len(dge.calls) == 1
    assert workflow.virtual_runtime_decision is not None
    assert (
        workflow.virtual_runtime_decision.status
        is VirtualRuntimeDecisionStatus.ORDER_READY
    )
    assert workflow.virtual_runtime_decision.trade_intent is not None
    assert workflow.virtual_runtime_decision.trade_intent.quantity == Decimal("7")
    assert workflow.virtual_runtime_decision.portfolio_before.market == "SPOT"
    assert workflow.virtual_runtime_decision.portfolio_before.equity_usdt == (
        Decimal("1000")
    )
    assert workflow.stages[-2].status is ResearchStageStatus.COMPLETED
    assert workflow.wallet is None
    assert workflow.canonical_cycle is not None
    assert (
        workflow.canonical_cycle.governance_status
        is CycleGovernanceStatus.APPROVED_PAPER_ONLY
    )
    assert workflow.canonical_cycle.execution_plan is not None
    assert workflow.canonical_cycle.execution_allowed is False
    assert workflow.canonical_cycle.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_research_service_default_dge_context_fails_closed_without_evidence() -> None:
    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
    ).run(public_snapshot())

    assert workflow.virtual_runtime_decision is not None
    assert (
        workflow.virtual_runtime_decision.status
        is VirtualRuntimeDecisionStatus.NO_ACTION
    )
    assert "DGE_SIMULATION_NOT_APPROVED" in (
        workflow.virtual_runtime_decision.eligibility.blockers
    )
    assert workflow.virtual_runtime_decision.trade_intent is None
    assert (
        workflow.virtual_runtime_decision.portfolio_after
        == workflow.virtual_runtime_decision.portfolio_before
    )
    assert workflow.stages[-2].status is ResearchStageStatus.BLOCKED


def test_paper_dge_evidence_survives_persistence_and_replays_once(
    tmp_path: Path,
) -> None:
    """Test-only paper cycle binds the original evaluation through durable receipts."""
    from ai4binance.governance.audit import dge_decision_log_path, dge_event_log_path
    from ai4binance.governance.replay import replay_dge_decision
    from ai4binance.infrastructure.persistence.canonical_payloads import (
        CanonicalExplanationStore,
    )

    dge = _RecordingDge()
    store = CanonicalExplanationStore(tmp_path / "explanations", boundary=tmp_path)
    audit = JsonlAuditStore(tmp_path / "paper.jsonl", tamper_evident=True)

    def _test_primitive(value: object) -> object:
        if isinstance(value, _RuntimeReadyAnalysis):
            return to_primitive(
                {
                    "snapshot_id": value.snapshot_id,
                    "candidates": value.candidate_setups,
                    "market_snapshot": value.market_snapshot,
                }
            )
        if type(value).__name__ == "Outlook":
            return {"snapshot_id": cast(Any, value).snapshot_id}
        return to_primitive(value)

    service = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_dge_engine=dge,
        virtual_dge_context_builder=_approved_virtual_dge_context,
        dge_record_root=tmp_path,
        audit_store=audit,
        canonical_explanation_store=store,
        primitive_converter=_test_primitive,
    )
    workflow = service.run(public_snapshot())
    cycle = workflow.canonical_cycle
    assert cycle is not None
    assert cycle.execution_plan is not None
    assert workflow.virtual_runtime_request is not None
    evaluation = workflow.virtual_runtime_request.dge_evaluation
    record = json.loads(evaluation.evaluation_record_json)
    assert len(dge.calls) == 1
    assert record["candidate"] == to_primitive(dge.calls[0][0])
    assert record["context"] == to_primitive(dge.calls[0][1])
    assert record["decision"] == to_primitive(dge.decisions[0])
    assert record["decision"]["passed_rules"]
    assert record["decision"]["config_hash"] == "config:test:approved"
    digest = hashlib.sha256(evaluation.evaluation_record_json.encode()).hexdigest()
    for reference in (
        cycle.decision,
        cycle.governance_result,
        cycle.audit_trail,
        cycle.execution_plan,
    ):
        body = store.read(reference)
        assert body is not None
        payload = cast(dict[str, Any], body["payload"])
        assert payload["dge_evidence_ref"]["evaluation_record_sha256"] == digest
        assert payload["dge_evidence_ref"]["decision_id"] == evaluation.decision_id
    governance_body = store.read(cycle.governance_result)
    assert governance_body is not None
    assert cast(dict[str, Any], governance_body["payload"])[
        "dge_evaluation"
    ] == to_primitive(evaluation)
    replay_payload = next(
        event["payload"]
        for line in dge_decision_log_path(tmp_path).read_text().splitlines()
        if (event := json.loads(line))["event_type"] == "DGE_DECISION_REPLAY_RECORD"
    )
    assert replay_payload == record
    replay = replay_dge_decision(tmp_path, evaluation.decision_id)
    assert replay.status == "MATCH"
    assert replay.execution_allowed is False
    assert replay.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    before = {
        path: path.read_bytes()
        for path in (
            audit.path,
            dge_decision_log_path(tmp_path),
            dge_event_log_path(tmp_path),
        )
    }
    repeated = service.run(public_snapshot())
    assert repeated.canonical_cycle == cycle
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "snapshot",
        "candidate",
        "market",
        "stale",
        "status",
        "oversize",
        "invalid",
    ],
)
def test_paper_dge_evidence_mismatch_fails_closed(mutation: str) -> None:
    from ai4binance.governance.adapters import VirtualMarketDgeAdapter

    class _ChangedEvidence:
        def evaluate(self, **kwargs: object) -> VirtualGovernanceResult:
            result = VirtualMarketDgeAdapter(
                context_builder=_approved_virtual_dge_context
            ).evaluate(**cast(Any, kwargs))
            record = json.loads(result.evaluation_record_json or "{}")
            if mutation == "missing":
                return replace(result, evaluation_record_json=None)
            if mutation == "oversize":
                return replace(result, evaluation_record_json="x" * 10_001)
            if mutation == "invalid":
                return replace(result, evaluation_record_json="{}")
            section, key = {
                "snapshot": ("context", "data_snapshot_id"),
                "candidate": ("candidate", "candidate_id"),
                "market": ("decision", "market_type"),
                "stale": ("context", "evaluation_timestamp_utc"),
                "status": ("decision", "governance_status"),
            }[mutation]
            record[section][key] = "TEST_ONLY_CONTRADICTORY_EVIDENCE"
            return replace(result, evaluation_record_json=json.dumps(record))

    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_governance_evaluator=_ChangedEvidence(),
    ).run(public_snapshot())
    decision = workflow.virtual_runtime_decision
    assert decision is not None
    assert decision.trade_intent is None
    assert decision.portfolio_before == decision.portfolio_after
    assert "DGE_EVALUATION_FAILED" in decision.eligibility.blockers
    assert workflow.canonical_cycle is not None
    assert workflow.canonical_cycle.execution_plan is None
    assert workflow.canonical_cycle.execution_allowed is False


def test_paper_dge_persistence_failure_cannot_produce_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _failed_write(*args: object, **kwargs: object) -> None:
        raise OSError("TEST_ONLY_DESTINATION_UNAVAILABLE")

    monkeypatch.setattr(
        "ai4binance.research_runtime.persist_dge_evaluation_record", _failed_write
    )
    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_dge_context_builder=_approved_virtual_dge_context,
        dge_record_root=tmp_path,
    ).run(public_snapshot())
    assert workflow.virtual_runtime_decision is not None
    assert workflow.virtual_runtime_decision.trade_intent is None
    assert (
        "DGE_EVALUATION_FAILED"
        in workflow.virtual_runtime_decision.eligibility.blockers
    )
    assert (
        "DGE_EVALUATION_ERROR_TYPE:PERSISTENCE"
        in workflow.virtual_runtime_decision.eligibility.blockers
    )


def test_research_application_without_governance_evaluator_fails_closed() -> None:
    workflow = ResearchApplicationService(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        primitive_converter=to_primitive,
    ).run(public_snapshot())

    assert workflow.virtual_runtime_decision is not None
    assert (
        workflow.virtual_runtime_decision.status
        is VirtualRuntimeDecisionStatus.NO_ACTION
    )
    assert workflow.virtual_runtime_decision.eligibility.blockers == (
        "DGE_EVALUATION_UNAVAILABLE",
        "DGE_SIMULATION_NOT_APPROVED",
    )
    assert (
        workflow.virtual_runtime_decision.portfolio_after
        == workflow.virtual_runtime_decision.portfolio_before
    )
    assert workflow.virtual_runtime_decision.trade_intent is None


def test_research_builder_rejects_ambiguous_governance_injection() -> None:
    with pytest.raises(
        ValueError,
        match="virtual governance evaluator cannot be combined with legacy DGE inputs",
    ):
        build_research_application_service(
            virtual_governance_evaluator=object(),
            virtual_dge_engine=_FailingDge(),
        )


def test_research_service_dge_failure_is_deterministic_and_preserves_portfolio() -> (
    None
):
    first = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_dge_engine=_FailingDge(),
        virtual_dge_context_builder=_approved_virtual_dge_context,
    ).run(public_snapshot())
    second = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_dge_engine=_FailingDge(),
        virtual_dge_context_builder=_approved_virtual_dge_context,
    ).run(public_snapshot())

    assert first.virtual_runtime_decision == second.virtual_runtime_decision
    assert first.virtual_runtime_decision is not None
    assert (
        first.virtual_runtime_decision.status is VirtualRuntimeDecisionStatus.NO_ACTION
    )
    assert first.virtual_runtime_decision.eligibility.blockers == (
        "DGE_EVALUATION_FAILED",
        "DGE_EVALUATION_ERROR_TYPE:ENGINE_EVALUATION",
        "DGE_SIMULATION_NOT_APPROVED",
    )
    assert (
        first.virtual_runtime_decision.portfolio_after
        == first.virtual_runtime_decision.portfolio_before
    )
    assert first.virtual_runtime_decision.trade_intent is None


def test_research_service_malformed_dge_context_fails_closed_without_mutation() -> None:
    def _malformed_context(
        snapshot: object,
        analysis: object,
        candidate: object,
        portfolio: object,
    ) -> DgeGovernanceContext:
        del snapshot, analysis, candidate, portfolio
        return cast(DgeGovernanceContext, object())

    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_dge_context_builder=_malformed_context,
    ).run(public_snapshot())

    assert workflow.virtual_runtime_decision is not None
    assert (
        workflow.virtual_runtime_decision.status
        is VirtualRuntimeDecisionStatus.NO_ACTION
    )
    assert workflow.virtual_runtime_decision.eligibility.blockers == (
        "DGE_EVALUATION_FAILED",
        "DGE_EVALUATION_ERROR_TYPE:CONTEXT_TYPE",
        "DGE_SIMULATION_NOT_APPROVED",
    )
    assert (
        workflow.virtual_runtime_decision.portfolio_after
        == workflow.virtual_runtime_decision.portfolio_before
    )
    assert workflow.virtual_runtime_decision.trade_intent is None


def test_research_service_skips_virtual_runtime_without_typed_risk_sizing() -> None:
    class _RiskWithoutSizing:
        status: ClassVar[_SuccessRiskStatus] = _SuccessRiskStatus()
        blockers: ClassVar[tuple[str, ...]] = ()
        calculation_metadata: ClassVar[dict[str, object]] = {}

    class _AnalysisWithoutSizing(_RuntimeReadyAnalysis):
        def __init__(self) -> None:
            super().__init__()
            self.agent_results = {"risk": _RiskWithoutSizing()}

    class _OrchestratorWithoutSizing:
        def analyze(self, snapshot: object) -> _AnalysisWithoutSizing:
            del snapshot
            return _AnalysisWithoutSizing()

    workflow = build_research_application_service(
        orchestrator=_OrchestratorWithoutSizing(),
        outlook_engine=_RuntimeReadyOutlook(),
    ).run(public_snapshot())

    assert workflow.virtual_runtime_decision is None
    assert workflow.stages[-2].status is ResearchStageStatus.BLOCKED
    assert workflow.stages[-2].blockers == ("DGE_SIMULATION_NOT_APPROVED",)


def test_research_service_rejects_unsupported_market_type() -> None:
    snapshot = public_snapshot()

    with pytest.raises(ValueError, match="market_type must be SPOT or USD_M_FUTURES"):
        TradeCandidate(
            candidate_id="candidate-unsupported-market",
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframe="1h",
            action=Action.BUY,
            setup_name="trend_continuation",
            status=CandidateStatus.READY_FOR_RISK,
            entry_zone=PriceZone(Decimal("100"), Decimal("100")),
            invalidation_level=Decimal("95"),
            stop_loss=Decimal("95"),
            take_profit_levels=(Decimal("110"),),
            trailing_stop=Decimal("95"),
            atr=Decimal("3"),
            risk_reward=Decimal("2"),
            score=80,
            confidence=0.8,
            market_type="OPTIONS",
            promotion_status=ValidationStatus.RESEARCH_ONLY,
        )


def test_research_service_selects_first_supported_candidate_for_virtual_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_helper(request: object, *, runtime: object | None = None) -> object:
        captured["request"] = request
        captured["runtime"] = runtime
        return SimpleNamespace(
            decision=SimpleNamespace(
                eligibility=SimpleNamespace(
                    blockers=(),
                    status=SimpleNamespace(value="ELIGIBLE"),
                    live_eligibility_status="LIVE_ORDER_BLOCKED",
                ),
                status=SimpleNamespace(value="ORDER_READY"),
                halt_review=None,
                trade_intent=None,
                portfolio_before=None,
                portfolio_after=None,
                audit_refs=("snapshot", "decision", "portfolio"),
            ),
        )

    class _Analysis:
        def __init__(self) -> None:
            snapshot = public_snapshot()
            self.snapshot_id = snapshot.snapshot_id
            self.market_snapshot = snapshot
            self.blockers = ()
            self.warnings = ()
            self.agent_results: dict[str, object] = {"risk": _SuccessRiskResult()}
            self.candidate_setups = (
                SimpleNamespace(
                    candidate_id="candidate-unsupported",
                    market_type="OPTIONS",
                    blockers=(),
                ),
                TradeCandidate(
                    candidate_id="candidate-1",
                    snapshot_id=snapshot.snapshot_id,
                    timestamp=snapshot.created_at,
                    symbol=snapshot.symbol,
                    timeframe="1h",
                    action=Action.BUY,
                    setup_name="trend_continuation",
                    status=CandidateStatus.READY_FOR_RISK,
                    entry_zone=PriceZone(Decimal("100"), Decimal("100")),
                    invalidation_level=Decimal("95"),
                    stop_loss=Decimal("95"),
                    take_profit_levels=(Decimal("110"),),
                    trailing_stop=Decimal("95"),
                    atr=Decimal("3"),
                    risk_reward=Decimal("2"),
                    score=80,
                    confidence=0.8,
                    market_type="SPOT",
                    promotion_status=ValidationStatus.RESEARCH_ONLY,
                ),
            )
            self.final_decision = SimpleNamespace(
                reason_summary=(
                    "No validated final decision is available; prefer NO_TRADE."
                ),
            )

    class _Orchestrator:
        def analyze(self, snapshot: object) -> _Analysis:
            del snapshot
            return _Analysis()

    monkeypatch.setattr(
        "ai4binance.application.research.run_virtual_market_cycle",
        _fake_helper,
    )

    workflow = build_research_application_service(
        orchestrator=_Orchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_market_runtime=object(),
    ).run(public_snapshot())

    assert captured["runtime"] is not None
    request = cast(Any, captured["request"])
    assert request.candidate_id == "candidate-1"
    assert request.market == "SPOT"
    assert workflow.virtual_runtime_decision is not None
    assert workflow.stages[-2].status is ResearchStageStatus.COMPLETED


def test_research_service_falls_back_to_supported_candidate_for_virtual_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_helper(request: object, *, runtime: object | None = None) -> object:
        captured["request"] = request
        captured["runtime"] = runtime
        return SimpleNamespace(
            decision=SimpleNamespace(
                eligibility=SimpleNamespace(
                    blockers=(),
                    status=SimpleNamespace(value="ELIGIBLE"),
                    live_eligibility_status="LIVE_ORDER_BLOCKED",
                ),
                status=SimpleNamespace(value="ORDER_READY"),
                halt_review=None,
                trade_intent=None,
                portfolio_before=None,
                portfolio_after=None,
                audit_refs=("snapshot", "decision", "portfolio"),
            ),
        )

    class _FallbackRiskResult:
        status: ClassVar[_SuccessRiskStatus] = _SuccessRiskStatus()
        blockers: ClassVar[tuple[str, ...]] = ()
        calculation_metadata: ClassVar[dict[str, object]] = {
            "candidate_id": "candidate-missing",
            "approved": True,
            "size_usdt": "700",
            "quantity": "7",
            "risk_amount_usdt": "35",
        }

    class _Analysis:
        def __init__(self) -> None:
            snapshot = public_snapshot()
            self.snapshot_id = snapshot.snapshot_id
            self.market_snapshot = snapshot
            self.blockers = ()
            self.warnings = ()
            self.agent_results: dict[str, object] = {"risk": _FallbackRiskResult()}
            self.candidate_setups = (
                SimpleNamespace(
                    candidate_id="candidate-unsupported",
                    market_type="OPTIONS",
                    blockers=(),
                ),
                TradeCandidate(
                    candidate_id="candidate-1",
                    snapshot_id=snapshot.snapshot_id,
                    timestamp=snapshot.created_at,
                    symbol=snapshot.symbol,
                    timeframe="1h",
                    action=Action.BUY,
                    setup_name="trend_continuation",
                    status=CandidateStatus.READY_FOR_RISK,
                    entry_zone=PriceZone(Decimal("100"), Decimal("100")),
                    invalidation_level=Decimal("95"),
                    stop_loss=Decimal("95"),
                    take_profit_levels=(Decimal("110"),),
                    trailing_stop=Decimal("95"),
                    atr=Decimal("3"),
                    risk_reward=Decimal("2"),
                    score=80,
                    confidence=0.8,
                    market_type="SPOT",
                    promotion_status=ValidationStatus.RESEARCH_ONLY,
                ),
            )
            self.final_decision = SimpleNamespace(
                reason_summary=(
                    "No validated final decision is available; prefer NO_TRADE."
                ),
            )

    class _Orchestrator:
        def analyze(self, snapshot: object) -> _Analysis:
            del snapshot
            return _Analysis()

    monkeypatch.setattr(
        "ai4binance.application.research.run_virtual_market_cycle",
        _fake_helper,
    )

    workflow = build_research_application_service(
        orchestrator=_Orchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_market_runtime=object(),
    ).run(public_snapshot())

    assert captured["runtime"] is not None
    request = cast(Any, captured["request"])
    assert request.candidate_id == "candidate-1"
    assert request.market == "SPOT"
    assert workflow.virtual_runtime_decision is not None
    assert workflow.stages[-2].status is ResearchStageStatus.COMPLETED


def test_research_service_virtual_runtime_surfaces_capacity_blockers() -> None:
    workflow = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        virtual_market_runtime=VirtualMarketRuntime(),
        virtual_portfolio_builder=lambda snapshot, candidate: VirtualPortfolioState(
            portfolio_id=f"virtual:{snapshot.snapshot_id}:{candidate.symbol}",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
            open_position_count=1,
            max_concurrent_positions=1,
        ),
    ).run(public_snapshot())

    assert workflow.virtual_runtime_decision is not None
    assert (
        workflow.virtual_runtime_decision.status
        is VirtualRuntimeDecisionStatus.NO_ACTION
    )
    assert "PORTFOLIO_CAPACITY_EXCEEDED" in (
        workflow.virtual_runtime_decision.eligibility.blockers
    )
    assert workflow.stages[-2].status is ResearchStageStatus.BLOCKED


def test_research_service_routes_virtual_halt_improvement_candidates_to_learning(
    tmp_path: Path,
) -> None:
    service = build_research_application_service(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        learning_loop=ControlledLearningLoop(
            LearningStore(tmp_path / "learning.json", tmp_path / "learning.jsonl"),
            ControlledLearningEngine(),
        ),
        virtual_market_runtime=VirtualMarketRuntime(),
        virtual_portfolio_builder=lambda snapshot, candidate: VirtualPortfolioState(
            portfolio_id=f"virtual:{snapshot.snapshot_id}:{candidate.symbol}",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
            consecutive_losses=3,
        ),
    )

    workflow = service.run(public_snapshot())

    assert workflow.virtual_runtime_decision is not None
    assert workflow.virtual_runtime_decision.halt_review is not None
    assert workflow.learning is not None
    by_code = {lesson.code: lesson for lesson in workflow.learning.summary.lessons}
    assert (
        by_code[
            "PERFORMANCE_IMPROVEMENT_VIRTUAL_MARKET_STRATEGY_RUNTIME"
        ].evidence_count
        == 3
    )
    assert by_code["ROOT_CAUSE_ENTRY_GATING_REVIEW"].evidence_count == 1
    assert by_code["ROOT_CAUSE_REGIME_FIT_REVIEW"].evidence_count == 1
    assert by_code["ROOT_CAUSE_EXIT_PROTECTION_REVIEW"].evidence_count == 1

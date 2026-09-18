"""Focused regression coverage for fail-closed boundary contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationStatus,
    evaluate_virtual_simulation_eligibility,
)
from ai4binance.application.virtual_runtime_eligibility import (
    _require_unique_nonblank as require_eligibility_values,
)
from ai4binance.domain import Action
from ai4binance.domain.research.canonical_cycle import (
    CanonicalCycleEnvelope,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
)
from ai4binance.domain.research.lifecycle import (
    CycleLifecycleReceipt,
    LearningValidationResult,
    MemoryDisposition,
)
from ai4binance.governance.authority import loader
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.infrastructure.filesystem.runtime_artifacts.layout import (
    RuntimeArtifactLayoutManifest,
    load_runtime_artifact_layout_manifest,
)
from ai4binance.research.virtual_runtime_portfolio_state import VirtualPortfolioState
from ai4binance.research.virtual_runtime_request import VirtualRuntimeRequest

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def _artifact(identifier: str, kind: CycleArtifactKind) -> CycleArtifactRef:
    return CycleArtifactRef(
        artifact_id=identifier,
        artifact_kind=kind,
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        payload_sha256=hashlib.sha256(identifier.encode("utf-8")).hexdigest(),
    )


def _cycle() -> CanonicalCycleEnvelope:
    return CanonicalCycleEnvelope(
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        created_at=NOW,
        execution_surface=CycleExecutionSurface.VIRTUAL_MARKET,
        governance_status=CycleGovernanceStatus.NO_TRADE,
        canonical_snapshot=_artifact("snapshot", CycleArtifactKind.CANONICAL_SNAPSHOT),
        shared_state=_artifact("state", CycleArtifactKind.SHARED_STATE),
        observations=(_artifact("observation", CycleArtifactKind.OBSERVATION),),
        decision=_artifact("decision", CycleArtifactKind.DECISION),
        risk_assessment=_artifact("risk", CycleArtifactKind.RISK_ASSESSMENT),
        governance_result=_artifact("governance", CycleArtifactKind.GOVERNANCE_RESULT),
        execution_plan=None,
        audit_trail=_artifact("audit", CycleArtifactKind.AUDIT_TRAIL),
        blockers=("NO_TRADE",),
    )


def _receipt() -> CycleLifecycleReceipt:
    return CycleLifecycleReceipt.bind(
        receipt_id="receipt-1",
        cycle=_cycle(),
        created_at=NOW + timedelta(seconds=1),
        outcome=_artifact("outcome", CycleArtifactKind.OUTCOME),
        learning_proposal=_artifact("proposal", CycleArtifactKind.LEARNING_PROPOSAL),
        validation_result=_artifact("validation", CycleArtifactKind.VALIDATION_RESULT),
        memory_disposition_artifact=_artifact(
            "memory", CycleArtifactKind.MEMORY_DISPOSITION
        ),
        validation_status=LearningValidationResult.PASS,
        memory_disposition=MemoryDisposition.ADMIT,
        learning_producer_id="learner",
        validator_id="validator",
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda value: replace(value, validation_status=cast(object, "PASS")),
            "status",
        ),
        (
            lambda value: replace(value, memory_disposition=cast(object, "ADMIT")),
            "disposition",
        ),
        (lambda value: replace(value, receipt_id=" "), "receipt_id"),
        (
            lambda value: replace(value, canonical_cycle_sha256="not-a-digest"),
            "SHA-256",
        ),
        (
            lambda value: replace(value, created_at=NOW - timedelta(seconds=1)),
            "precede",
        ),
        (lambda value: replace(value, validator_id="learner"), "independent"),
        (lambda value: replace(value, completed_steps=()), "step order"),
        (lambda value: replace(value, blockers=("",)), "blanks"),
        (lambda value: replace(value, blockers=("A", "A")), "unique"),
        (
            lambda value: replace(
                value,
                outcome=_artifact("proposal", CycleArtifactKind.OUTCOME),
            ),
            "identities",
        ),
        (
            lambda value: replace(value, validated_learning_sha256="a" * 64),
            "bind learning",
        ),
        (
            lambda value: replace(value, execution_allowed=True),
            "cannot grant authority",
        ),
    ],
)
def test_cycle_lifecycle_receipt_rejects_invalid_boundary_states(
    change: Callable[[CycleLifecycleReceipt], CycleLifecycleReceipt], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        change(_receipt())


def test_cycle_lifecycle_rejection_requires_blockers_and_serializes_hash() -> None:
    rejected = replace(
        _receipt(),
        validation_status=LearningValidationResult.REJECT,
        memory_disposition=MemoryDisposition.REJECT,
        blockers=("VALIDATION_REJECTED",),
    )

    assert rejected.to_payload()["semantic_sha256"] == rejected.semantic_sha256
    with pytest.raises(ValueError, match="requires rejected validation"):
        replace(rejected, blockers=())
    with pytest.raises(ValueError, match="created_at must be UTC"):
        replace(_receipt(), cycle_created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="artifact reference"):
        replace(_receipt(), outcome=cast(CycleArtifactRef, object()))
    with pytest.raises(ValueError, match="lineage"):
        replace(
            _receipt(),
            outcome=CycleArtifactRef(
                artifact_id="other-cycle",
                artifact_kind=CycleArtifactKind.OUTCOME,
                cycle_id="other-cycle",
                snapshot_id="snapshot-1",
                payload_sha256="a" * 64,
            ),
        )
    with pytest.raises(ValueError, match="kind must match"):
        replace(
            _receipt(),
            outcome=_artifact("wrong-kind", CycleArtifactKind.LEARNING_PROPOSAL),
        )
    with pytest.raises(ValueError, match="cannot contain blockers"):
        replace(_receipt(), blockers=("BLOCKED",))


def _request(**changes: object) -> VirtualRuntimeRequest:
    values: dict[str, object] = {
        "snapshot_id": "snapshot-1",
        "decision_id": "decision-1",
        "candidate_id": "candidate-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "action": Action.BUY,
        "quantity": Decimal("1"),
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("95"),
        "take_profit_levels": (Decimal("110"),),
        "portfolio": VirtualPortfolioState(
            portfolio_id="virtual:spot:1",
            market="SPOT",
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        ),
        "dge_decision": "APPROVED_PAPER_ONLY",
        "dge_simulation_allowed": True,
    }
    values.update(changes)
    return VirtualRuntimeRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"entry_reason": ("",)}, "blank"),
        ({"dge_blockers": ("A", "A")}, "unique"),
        ({"quantity": Decimal("0")}, "geometry"),
        ({"take_profit_levels": ()}, "take-profit"),
        ({"fee_ratio": Decimal("0.02")}, "fee ratio"),
        ({"slippage_ratio": Decimal("0.03")}, "slippage ratio"),
        ({"half_spread_ratio": Decimal("0.03")}, "half spread"),
        ({"tick_size": Decimal("0")}, "tick size"),
        ({"step_size": Decimal("0")}, "step size"),
        ({"minimum_notional": Decimal("0")}, "minimum notional"),
        ({"candle_volume": Decimal("-1")}, "candle volume"),
        ({"mark_price": Decimal("0")}, "mark price"),
        ({"funding_rate": Decimal("NaN")}, "funding rate"),
        ({"funding_payment_due": cast(object, 1)}, "payment due"),
        ({"leverage": 0}, "leverage"),
        ({"isolated_margin_usdt": Decimal("0")}, "isolated margin"),
        ({"maintenance_margin_ratio": Decimal("1")}, "maintenance margin"),
        ({"liquidation_fee_ratio": Decimal("0.03")}, "liquidation fee"),
        ({"market": "MARGIN"}, "market must"),
    ],
)
def test_virtual_runtime_request_rejects_invalid_execution_inputs(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _request(**changes)


def test_virtual_runtime_request_normalizes_market_and_fails_closed_dge() -> None:
    approved = _request(market=" spot ")
    blocked = _request(dge_decision="UNKNOWN", dge_simulation_allowed=False)

    assert approved.market == "SPOT"
    assert blocked.dge_blockers == ("DGE_SIMULATION_NOT_APPROVED",)


def test_runtime_artifact_layout_rejects_invalid_manifest_and_normalizes_values(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        RuntimeArtifactLayoutManifest(
            "runtime", "legacy", {"proof": ""}, {"old": "runtime"}
        )
    with pytest.raises(ValueError, match="unknown"):
        load_runtime_artifact_layout_manifest().root_for("missing")

    manifest = RuntimeArtifactLayoutManifest(
        canonical_root="runtime",
        legacy_root="legacy",
        roots={"proof": "runtime/proof"},
        legacy_roots={"old": "runtime/proof", "old/deep": "runtime/deep"},
    )
    assert manifest.aliases[0] == ("old/deep", "runtime/deep")
    assert (
        manifest.canonicalize_uri(" old\\record.json ") == "runtime/proof/record.json"
    )
    assert manifest.canonicalize_uri("unknown\\record.json") == "unknown/record.json"
    assert manifest.retention == {}

    from ai4binance.infrastructure.filesystem.runtime_artifacts import layout

    with pytest.raises(ValueError, match="non-empty string"):
        layout._text({}, "missing")
    with pytest.raises(ValueError, match="non-empty object"):
        layout._text_mapping([], "roots")
    with pytest.raises(ValueError, match="non-empty strings"):
        layout._text_mapping({"proof": " "}, "roots")
    with pytest.raises(ValueError, match="retention must be an object"):
        layout._retention_mapping([])

    for payload, message in (
        ([], "object"),
        ({"schema_version": "2.0"}, "schema version"),
        ({"schema_version": "1.0", "roots": {}}, "non-empty"),
    ):
        path = tmp_path / f"manifest-{len(str(payload))}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_runtime_artifact_layout_manifest(path)


def test_authority_loader_helpers_and_invalid_registry_fail_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="mapping"):
        loader._required_mapping([], "node")
    with pytest.raises(ValueError, match="list"):
        loader._required_list({}, "nodes")
    with pytest.raises(ValueError, match="required"):
        loader._required_string({}, "node_id")
    with pytest.raises(ValueError, match="boolean"):
        loader._required_bool({}, "source_of_truth")

    invalid = tmp_path / "authority.yaml"
    invalid.write_text("- not: a mapping", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        loader.load_authority_graph(invalid, schema_root=Path("schemas"))
    invalid.write_text("[", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be loaded"):
        loader.load_authority_graph(invalid, schema_root=Path("schemas"))
    invalid.write_text("graph_id: invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="schema validation failed"):
        loader.load_authority_graph(invalid, schema_root=Path("schemas"))


def test_virtual_simulation_eligibility_rejects_invalid_state_and_preserves_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="unique"):
        require_eligibility_values("reason", ("A", "A"))
    with pytest.raises(ValueError, match="blanks"):
        require_eligibility_values("reason", ("",))

    eligible = evaluate_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET
    )
    assert eligible.status is VirtualSimulationStatus.ELIGIBLE
    with pytest.raises(ValueError, match="live blocked"):
        replace(eligible, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="authorize orders"):
        replace(eligible, live_order_allowed=True)
    with pytest.raises(ValueError, match="requires autonomous"):
        replace(eligible, auto_simulation_allowed=False)

    blocked = evaluate_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        risk_blockers=("RISK_VETO",),
    )
    assert blocked.status is VirtualSimulationStatus.BLOCKED
    with pytest.raises(ValueError, match="requires blockers"):
        replace(blocked, blockers=(), blocker_reduction=None)
    with pytest.raises(ValueError, match="inconsistent"):
        replace(blocked, blockers=("OTHER",))
    with pytest.raises(ValueError, match="cannot carry"):
        replace(eligible, blocker_reduction=object())
    with pytest.raises(ValueError, match="target VIRTUAL_MARKET"):
        replace(eligible, execution_surface=ExecutionSurface.BINANCE_MARKET)
    with pytest.raises(ValueError, match="manual confirmation"):
        replace(eligible, requires_manual_confirmation=True)

    monkeypatch.setattr(
        "ai4binance.application.virtual_runtime_eligibility.execution_envelope_for_surface",
        lambda _surface: SimpleNamespace(
            virtual_simulation_allowed=True,
            auto_simulation_allowed=True,
            external_order_allowed=True,
            live_order_allowed=True,
            manual_confirmation_required=False,
            reason_codes=("TEST",),
        ),
    )
    leaked = evaluate_virtual_simulation_eligibility(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET
    )
    assert leaked.blockers == (
        "BINANCE_ORDER_AUTHORITY_LEAK",
        "LIVE_ORDER_AUTHORITY_LEAK",
    )

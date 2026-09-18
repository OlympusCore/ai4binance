"""Deterministic DGE decision replay from persisted records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ai4binance.governance.audit import dge_decision_log_path
from ai4binance.governance.dge_engine import DecisionGovernanceEngine
from ai4binance.governance.dge_models import (
    DgeGovernanceContext,
    DgeMarketAction,
    DgeMarketPlan,
    DgePolicyVersions,
    DgeSetupTier,
    DgeTradeCandidate,
)
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import read_bounded_jsonl_tail


@dataclass(frozen=True, slots=True)
class DgeReplayResult:
    decision_id: str
    status: str
    checked_fields: tuple[str, ...]
    mismatches: tuple[str, ...] = ()
    blocker: str = ""
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.status.strip():
            raise ValueError("DGE replay result identity is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE replay cannot authorize execution")


def replay_dge_decision(
    root: Path,
    decision_id: str,
    *,
    dge: DecisionGovernanceEngine | None = None,
) -> DgeReplayResult:
    """Replay a persisted DGE decision record and compare core fields."""

    normalized = decision_id.strip()
    if not normalized:
        raise ValueError("decision_id is required")
    record = _find_record(root, normalized)
    if record is None:
        return DgeReplayResult(
            decision_id=normalized,
            status="NON_REPRODUCIBLE",
            checked_fields=(),
            blocker="DGE_REPLAY_RECORD_NOT_FOUND",
        )
    candidate = _candidate_from_payload(_mapping(record.get("candidate")))
    context = _context_from_payload(_mapping(record.get("context")))
    expected = _mapping(record.get("decision"))
    observed = _mapping(
        to_primitive(
            (dge or DecisionGovernanceEngine()).evaluate(
                candidate,
                context,
            )
        )
    )
    checked = (
        "decision_id",
        "governance_status",
        "governed_action",
        "hard_blockers",
        "soft_blockers",
        "failed_rules",
    )
    mismatches = tuple(
        field for field in checked if expected.get(field) != observed.get(field)
    )
    return DgeReplayResult(
        decision_id=normalized,
        status="MATCH" if not mismatches else "MISMATCH",
        checked_fields=checked,
        mismatches=mismatches,
    )


def _find_record(root: Path, decision_id: str) -> Mapping[str, object] | None:
    path = dge_decision_log_path(root)
    if not path.exists():
        return None
    for line in reversed(read_bounded_jsonl_tail(path, max_lines=500)):
        payload = json.loads(line.decode("utf-8"))
        event_payload = _mapping(payload.get("payload"))
        decision = _mapping(event_payload.get("decision"))
        if decision.get("decision_id") == decision_id:
            return event_payload
    return None


def _candidate_from_payload(payload: Mapping[str, object]) -> DgeTradeCandidate:
    plan = _mapping(payload.get("market_plan"))
    return DgeTradeCandidate(
        candidate_id=str(payload.get("candidate_id", "")),
        symbol=str(payload.get("symbol", "")),
        market=str(payload.get("market", "SPOT")),
        requested_action=DgeMarketAction(str(payload.get("requested_action", "HOLD"))),
        setup_name=str(payload.get("setup_name", "UNKNOWN_SETUP")),
        score=_decimal(payload.get("score")),
        confidence=_decimal(payload.get("confidence")),
        risk_reward=_optional_decimal(payload.get("risk_reward")),
        capital_source=str(payload.get("capital_source", "UNKNOWN")),
        primary_timeframe=str(payload.get("primary_timeframe", "UNKNOWN")),
        setup_tier=DgeSetupTier(str(payload.get("setup_tier", "C"))),
        mtf_bias=str(payload.get("mtf_bias", "UNKNOWN")),
        regime=str(payload.get("regime", "UNKNOWN")),
        market_plan=DgeMarketPlan(
            entry=_optional_decimal(plan.get("entry")),
            stop_loss=_optional_decimal(plan.get("stop_loss")),
            invalidation_level=_optional_decimal(plan.get("invalidation_level")),
            take_profit_levels=tuple(
                _decimal(item) for item in _sequence(plan.get("take_profit_levels"))
            ),
            trailing_stop=_optional_decimal(plan.get("trailing_stop")),
            size_usdt=_optional_decimal(plan.get("size_usdt")),
        ),
        evidence_refs=_text_tuple(payload.get("evidence_refs")),
    )


def _context_from_payload(payload: Mapping[str, object]) -> DgeGovernanceContext:
    versions = _mapping(payload.get("policy_versions"))
    return DgeGovernanceContext(
        context_id=str(payload.get("context_id", "")),
        data_snapshot_id=str(payload.get("data_snapshot_id", "")),
        semantic_graph_id=str(payload.get("semantic_graph_id", "")),
        position_context_ref=str(payload.get("position_context_ref", "")),
        wallet_verified=bool(payload.get("wallet_verified", False)),
        snapshot_integrity_verified=bool(
            payload.get("snapshot_integrity_verified", True)
        ),
        data_quality_passed=bool(payload.get("data_quality_passed", True)),
        required_timeframes_present=bool(
            payload.get("required_timeframes_present", True)
        ),
        liquidity_approved=bool(payload.get("liquidity_approved", True)),
        regime_compatible=bool(payload.get("regime_compatible", True)),
        mtf_aligned=bool(payload.get("mtf_aligned", True)),
        structure_valid=bool(payload.get("structure_valid", True)),
        negative_evidence_clear=bool(payload.get("negative_evidence_clear", True)),
        oos_approved=bool(payload.get("oos_approved", False)),
        risk_approved=bool(payload.get("risk_approved", False)),
        validation_approved=bool(payload.get("validation_approved", False)),
        execution_feasible=bool(payload.get("execution_feasible", False)),
        human_approval_recorded=bool(payload.get("human_approval_recorded", False)),
        position_dependency_bias_detected=bool(
            payload.get("position_dependency_bias_detected", False)
        ),
        no_new_capital_required=bool(payload.get("no_new_capital_required", True)),
        execution_surface=ExecutionSurface(
            str(payload.get("execution_surface", ExecutionSurface.BINANCE_MARKET.value))
        ),
        blockers=_text_tuple(payload.get("blockers")),
        evidence_refs=_text_tuple(payload.get("evidence_refs")),
        rule_set_version=str(payload.get("rule_set_version", "dge-rules-v1")),
        config_hash=str(payload.get("config_hash", "unconfigured")),
        evaluation_timestamp_utc=str(
            payload.get("evaluation_timestamp_utc", "1970-01-01T00:00:00Z")
        ),
        policy_versions=DgePolicyVersions(
            policy_version=str(versions.get("policy_version", "dge-policy-v1")),
            config_version=str(versions.get("config_version", "unconfigured")),
            strategy_version=str(versions.get("strategy_version", "unknown")),
            parameter_version=str(versions.get("parameter_version", "unknown")),
            ontology_version=str(versions.get("ontology_version", "unknown")),
        ),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def _text_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value))


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)

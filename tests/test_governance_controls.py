from decimal import Decimal
from typing import Any

import pytest

from ai4binance.governance.controls import (
    ControlEligibility,
    ControlEvaluation,
    ControlResolution,
    ControlResolutionAuthority,
    ControlSeverity,
    ControlSource,
    HardBlocker,
    PenaltyGroupCap,
    SoftPenalty,
    SoftPenaltyPolicy,
    build_control_evaluation,
    resolve_hard_blockers,
    unknown_control_classification_blocker,
)


def hard_blocker(reason_code: str = "DATA_STALE") -> HardBlocker:
    return HardBlocker(
        blocker_id=f"hard:{reason_code}",
        blocker_type="DATA_FRESHNESS",
        source=ControlSource.DATA_QUALITY,
        severity=ControlSeverity.CRITICAL,
        reason_code=reason_code,
        evidence_refs=("snapshot:stale",),
        policy_ref="policy:dge:data-quality",
        resolution_authority=ControlResolutionAuthority.DATA_QUALITY_ENGINE,
    )


def soft_penalty(
    reason_code: str = "WEAK_RELATIVE_VOLUME",
    *,
    value: Decimal = Decimal("5"),
    penalty_group: str = "LIQUIDITY_QUALITY",
    metadata: dict[str, str] | None = None,
) -> SoftPenalty:
    return SoftPenalty(
        penalty_id=f"soft:{reason_code}",
        penalty_type="SCORE_ADJUSTMENT",
        source=ControlSource.LIQUIDITY,
        reason_code=reason_code,
        value=value,
        max_value=Decimal("20"),
        evidence_refs=("snapshot:liquidity",),
        policy_ref="policy:dge:liquidity",
        penalty_group=penalty_group,
        metadata=metadata or {},
    )


def test_hard_blocker_overrides_perfect_score() -> None:
    evaluation = build_control_evaluation(
        evaluation_id="control:test:data-stale",
        base_score=Decimal("100"),
        hard_blockers=(hard_blocker(),),
    )

    assert evaluation.hard_gate_passed is False
    assert evaluation.eligibility is ControlEligibility.NO_TRADE
    assert evaluation.active_hard_blocker_count == 1
    assert evaluation.adjusted_score == Decimal("100")


def test_soft_penalty_reduces_score_without_creating_blocker() -> None:
    evaluation = build_control_evaluation(
        evaluation_id="control:test:soft",
        base_score=Decimal("87"),
        soft_penalties=(
            soft_penalty(),
            soft_penalty(
                "MINOR_AGENT_DISAGREEMENT",
                value=Decimal("3"),
                penalty_group="GOVERNANCE_REVIEW",
            ),
        ),
        eligibility_when_clear=ControlEligibility.WATCH_ONLY,
    )

    assert evaluation.hard_gate_passed is True
    assert evaluation.active_hard_blocker_count == 0
    assert evaluation.total_penalty == Decimal("8")
    assert evaluation.adjusted_score == Decimal("79")
    assert evaluation.eligibility is ControlEligibility.WATCH_ONLY


def test_penalty_global_and_group_caps_are_enforced() -> None:
    policy = SoftPenaltyPolicy(
        global_cap=Decimal("10"),
        group_caps=(PenaltyGroupCap("LIQUIDITY_QUALITY", Decimal("7")),),
    )

    evaluation = build_control_evaluation(
        evaluation_id="control:test:caps",
        base_score=Decimal("80"),
        soft_penalties=(
            soft_penalty("WEAK_RELATIVE_VOLUME", value=Decimal("6")),
            soft_penalty("MINOR_SPREAD_DEGRADATION", value=Decimal("6")),
            soft_penalty(
                "REGIME_FIT_SUBOPTIMAL",
                value=Decimal("6"),
                penalty_group="REGIME_FIT",
            ),
        ),
        penalty_policy=policy,
    )

    assert evaluation.total_penalty == Decimal("10")
    assert evaluation.adjusted_score == Decimal("70")


def test_control_payloads_include_nested_veto_and_penalty_metadata() -> None:
    blocker = hard_blocker()
    penalty = soft_penalty(
        metadata={"source_snapshot": "snapshot:liquidity"},
    )
    evaluation = build_control_evaluation(
        evaluation_id="control:test:payload",
        base_score=Decimal("65"),
        hard_blockers=(blocker,),
        soft_penalties=(penalty,),
        eligibility_when_blocked=ControlEligibility.LIVE_ORDER_BLOCKED,
    )

    blocker_payload = blocker.to_payload()
    penalty_payload = penalty.to_payload()
    evaluation_payload = evaluation.to_payload()

    assert blocker_payload["blocker_id"] == "hard:DATA_STALE"
    assert blocker_payload["severity"] == "CRITICAL"
    assert blocker_payload["resolution_authority"] == "DATA_QUALITY_ENGINE"
    assert penalty_payload["penalty_id"] == "soft:WEAK_RELATIVE_VOLUME"
    assert penalty_payload["metadata"] == {"source_snapshot": "snapshot:liquidity"}
    assert evaluation_payload["active_hard_blocker_count"] == 1
    assert evaluation_payload["eligibility"] == "LIVE_ORDER_BLOCKED"
    assert evaluation_payload["hard_blockers"] == [blocker_payload]
    assert evaluation_payload["soft_penalties"] == [penalty_payload]


def test_unknown_control_classification_fails_closed() -> None:
    evaluation = build_control_evaluation(
        evaluation_id="control:test:unknown",
        base_score=Decimal("90"),
        hard_blockers=(
            unknown_control_classification_blocker(
                reason_code="UNKNOWN_CONTROL_CLASSIFICATION",
            ),
        ),
    )

    assert evaluation.eligibility is ControlEligibility.NO_TRADE
    assert evaluation.hard_blockers[0].reason_code == (
        "GOV.UNKNOWN_CONTROL_CLASSIFICATION"
    )
    assert evaluation.hard_blockers[0].metadata["original_reason_code"] == (
        "UNKNOWN_CONTROL_CLASSIFICATION"
    )
    assert evaluation.hard_blockers[0].resolution_authority is (
        ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE
    )


def test_blocker_requires_authorized_resolution() -> None:
    blocker = hard_blocker()
    with pytest.raises(ValueError, match="resolution authority"):
        resolve_hard_blockers(
            (blocker,),
            (
                ControlResolution(
                    blocker_id=blocker.blocker_id,
                    resolution_authority=ControlResolutionAuthority.RISK_ENGINE,
                    evidence_refs=("resolution:1",),
                ),
            ),
        )

    resolved = resolve_hard_blockers(
        (blocker,),
        (
            ControlResolution(
                blocker_id=blocker.blocker_id,
                resolution_authority=ControlResolutionAuthority.DATA_QUALITY_ENGINE,
                evidence_refs=("resolution:1",),
            ),
        ),
    )

    assert resolved[0].active is False


def test_resolver_preserves_unresolved_blockers_and_requires_evidence() -> None:
    stale = hard_blocker("DATA_STALE")
    missing = hard_blocker("RISK_VETO")

    unresolved = resolve_hard_blockers(
        (stale, missing),
        (
            ControlResolution(
                blocker_id=stale.blocker_id,
                resolution_authority=ControlResolutionAuthority.DATA_QUALITY_ENGINE,
                evidence_refs=("resolution:1",),
                resolved=False,
            ),
        ),
    )

    assert unresolved == (stale, missing)
    with pytest.raises(ValueError, match="requires evidence"):
        resolve_hard_blockers(
            (stale,),
            (
                ControlResolution(
                    blocker_id=stale.blocker_id,
                    resolution_authority=ControlResolutionAuthority.DATA_QUALITY_ENGINE,
                    evidence_refs=(),
                ),
            ),
        )


def test_deterministic_control_evaluation_replay() -> None:
    kwargs: dict[str, Any] = {
        "evaluation_id": "control:test:replay",
        "base_score": Decimal("75"),
        "hard_blockers": (),
        "soft_penalties": (soft_penalty(value=Decimal("4")),),
    }

    assert build_control_evaluation(**kwargs) == build_control_evaluation(**kwargs)


def test_control_value_objects_reject_invalid_contracts() -> None:
    with pytest.raises(ValueError, match="hard blocker identity"):
        HardBlocker(
            blocker_id=" ",
            blocker_type="DATA_FRESHNESS",
            source=ControlSource.DATA_QUALITY,
            severity=ControlSeverity.CRITICAL,
            reason_code="DATA_STALE",
            evidence_refs=("snapshot:stale",),
            policy_ref="policy:dge:data-quality",
        )
    with pytest.raises(ValueError, match="hard blocker evidence refs"):
        HardBlocker(
            blocker_id="hard:blank-evidence",
            blocker_type="DATA_FRESHNESS",
            source=ControlSource.DATA_QUALITY,
            severity=ControlSeverity.CRITICAL,
            reason_code="DATA_STALE",
            evidence_refs=("snapshot:stale", " "),
            policy_ref="policy:dge:data-quality",
        )
    with pytest.raises(ValueError, match="soft penalty value"):
        soft_penalty(value=Decimal("21"))
    with pytest.raises(ValueError, match="penalty group cap"):
        PenaltyGroupCap("LIQUIDITY_QUALITY", Decimal("-1"))
    with pytest.raises(ValueError, match="global cap"):
        SoftPenaltyPolicy(global_cap=Decimal("-1"))
    with pytest.raises(ValueError, match="group caps must be unique"):
        SoftPenaltyPolicy(
            group_caps=(
                PenaltyGroupCap("LIQUIDITY_QUALITY", Decimal("7")),
                PenaltyGroupCap("LIQUIDITY_QUALITY", Decimal("8")),
            ),
        )
    with pytest.raises(ValueError, match="base_score"):
        build_control_evaluation(
            evaluation_id="control:test:invalid-score",
            base_score=Decimal("101"),
        )
    with pytest.raises(ValueError, match="hard blocker ids"):
        ControlEvaluation(
            hard_blockers=(hard_blocker(), hard_blocker()),
            hard_gate_passed=False,
            eligibility=ControlEligibility.NO_TRADE,
        )
    with pytest.raises(ValueError, match="reason codes cannot contain blanks"):
        ControlEvaluation(reason_codes=(" ",))
    with pytest.raises(ValueError, match="must fail the hard gate"):
        ControlEvaluation(hard_blockers=(hard_blocker(),))
    with pytest.raises(ValueError, match="cannot be eligible"):
        ControlEvaluation(
            hard_blockers=(hard_blocker(),),
            hard_gate_passed=False,
            eligibility=ControlEligibility.ELIGIBLE,
        )
    with pytest.raises(ValueError, match="cannot fail without active hard blockers"):
        ControlEvaluation(hard_gate_passed=False)
    with pytest.raises(ValueError, match="adjusted score cannot exceed base score"):
        ControlEvaluation(base_score=Decimal("10"), adjusted_score=Decimal("11"))
    with pytest.raises(ValueError, match="control resolution identity"):
        ControlResolution(
            blocker_id=" ",
            resolution_authority=ControlResolutionAuthority.DATA_QUALITY_ENGINE,
            evidence_refs=("resolution:1",),
        )

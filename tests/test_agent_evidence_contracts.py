from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

import pytest

from ai4binance.agents import (
    AgentAnatomyPart,
    AgentAuthorityContract,
    AgentCapabilitiesContract,
    AgentContract,
    AgentEvidenceLayer,
    AgentEvidenceReference,
    AgentEvidenceStatus,
    AgentFailureContract,
    AgentIdentityContract,
    AgentInputsContract,
    AgentIntelligenceType,
    AgentObservation,
    AgentOutputsContract,
    AgentValidationContract,
    VerificationCheck,
    VerificationLayer,
    VerificationResult,
)

NOW = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
HASH = "a" * 64


def evidence(
    evidence_id: str,
    status: AgentEvidenceStatus = AgentEvidenceStatus.VERIFIED,
) -> AgentEvidenceReference:
    return AgentEvidenceReference(
        evidence_id=evidence_id,
        source_id="official-source",
        claim="validation evidence is locally available",
        status=status,
        observed_at=NOW,
        content_hash=HASH,
    )


def check(
    check_id: str,
    result: VerificationResult,
    evidence_ids: tuple[str, ...] = ("ev-1",),
) -> VerificationCheck:
    return VerificationCheck(
        check_id=check_id,
        description="independent validation check",
        result=result,
        evidence_ids=evidence_ids,
        reason_codes=("LOCAL_VALIDATION",),
    )


def observation(
    *,
    observation_id: str = "obs-1",
    agent_id: str = "research-agent",
    agent_version: str = "1.0.0",
    cycle_id: str = "cycle-1",
    snapshot_id: str = "snapshot-1",
    symbol: str = "HOTUSDT",
    timeframe: str = "1h",
    capability_ids: tuple[str, ...] = ("market-outlook",),
    assessment: str = "RESEARCH_ONLY",
    confidence: float = 0.5,
    uncertainty: float = 0.4,
    evidence_ids: tuple[str, ...] = ("ev-1",),
    conflicting_evidence_ids: tuple[str, ...] = (),
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",),
    data_quality_score: float = 0.8,
    execution_authority: Literal["NONE"] = "NONE",
) -> AgentObservation:
    return AgentObservation(
        observation_id=observation_id,
        agent_id=agent_id,
        agent_version=agent_version,
        cycle_id=cycle_id,
        snapshot_id=snapshot_id,
        symbol=symbol,
        timeframe=timeframe,
        capability_ids=capability_ids,
        assessment=assessment,
        confidence=confidence,
        uncertainty=uncertainty,
        evidence_ids=evidence_ids,
        conflicting_evidence_ids=conflicting_evidence_ids,
        blockers=blockers,
        data_quality_score=data_quality_score,
        execution_authority=execution_authority,
    )


def test_agent_observation_contract_rejects_invalid_identity_scores_and_authority() -> (
    None
):
    valid = observation()

    assert valid.execution_authority == "NONE"

    with pytest.raises(ValueError, match="observation_id cannot be empty"):
        observation(observation_id=" ")
    with pytest.raises(ValueError, match="requires capability_ids"):
        observation(capability_ids=())
    with pytest.raises(ValueError, match="evidence IDs must be unique"):
        observation(evidence_ids=("ev-1", "ev-1"))
    with pytest.raises(ValueError, match="blockers cannot contain empty values"):
        observation(blockers=(" ",))
    with pytest.raises(ValueError, match="confidence must be between zero and one"):
        observation(confidence=float("nan"))
    with pytest.raises(ValueError, match="must not carry execution authority"):
        observation(execution_authority=cast("Literal['NONE']", "LIVE"))


def test_agent_contract_anatomy_and_fail_closed_subcontracts_are_enforced() -> None:
    contract = AgentContract(
        identity=AgentIdentityContract("research-agent", "1.0.0", "research"),
        capabilities=AgentCapabilitiesContract(("market-outlook", "validation")),
        intelligence_type=AgentIntelligenceType.LLM_ADVISORY,
        tool_permissions=("read-local-evidence",),
    )

    assert contract.anatomy == tuple(AgentAnatomyPart)

    with pytest.raises(ValueError, match="agent_id cannot be empty"):
        AgentIdentityContract(" ", "1.0.0", "research")
    with pytest.raises(ValueError, match="capability IDs must be unique"):
        AgentCapabilitiesContract(("same", "same"))
    with pytest.raises(ValueError, match="canonical_only"):
        AgentInputsContract(canonical_only=False)
    with pytest.raises(ValueError, match="AgentObservation schema"):
        AgentOutputsContract(schema="RawLLMText")
    with pytest.raises(ValueError, match="advisory authorities"):
        AgentAuthorityContract(analyze=False)
    with pytest.raises(ValueError, match="final/risk/policy/live authority"):
        AgentAuthorityContract(live_execution=True)
    with pytest.raises(ValueError, match="validation is required"):
        AgentValidationContract(required=False)
    with pytest.raises(ValueError, match="AGENT_UNAVAILABLE"):
        AgentFailureContract(default="CONTINUE_ANYWAY")
    with pytest.raises(ValueError, match="canonical 10 parts"):
        AgentContract(
            identity=contract.identity,
            capabilities=contract.capabilities,
            intelligence_type=contract.intelligence_type,
            anatomy=tuple(AgentAnatomyPart)[:-1],
        )


def test_agent_evidence_layer_reports_incomplete_conflicted_and_unavailable_data() -> (
    None
):
    verified = evidence("ev-1")
    unavailable = evidence("ev-2", AgentEvidenceStatus.DATA_UNAVAILABLE)
    conflicted = AgentEvidenceLayer(
        agent_id="research-agent",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        layer_id="layer-1",
        evidence=(verified, unavailable),
        conflicting_evidence_ids=("ev-2",),
        minimum_required=2,
    )

    assert conflicted.verified_count == 1
    assert conflicted.evidence_complete is False
    assert conflicted.blockers == (
        "AGENT_EVIDENCE_INCOMPLETE",
        "AGENT_EVIDENCE_CONFLICTED",
        "AGENT_EVIDENCE_DATA_UNAVAILABLE",
    )
    assert (
        AgentEvidenceLayer(
            "layer-2",
            "research-agent",
            "cycle-1",
            "snapshot-1",
            (verified,),
        ).evidence_complete
        is True
    )

    with pytest.raises(ValueError, match="minimum_required must be positive"):
        AgentEvidenceLayer(
            "layer-3", "agent", "cycle", "snapshot", (), minimum_required=0
        )
    with pytest.raises(ValueError, match="reference local evidence"):
        AgentEvidenceLayer(
            "layer-4",
            "agent",
            "cycle",
            "snapshot",
            (verified,),
            conflicting_evidence_ids=("missing",),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        AgentEvidenceReference(
            "ev-3",
            "source",
            "claim",
            AgentEvidenceStatus.VERIFIED,
            datetime(2026, 8, 13),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        AgentEvidenceReference(
            "ev-4",
            "source",
            "claim",
            AgentEvidenceStatus.VERIFIED,
            NOW,
            content_hash="short",
        )


def test_verification_layer_result_and_authority_branches_are_fail_closed() -> None:
    assert (
        VerificationLayer(
            "vl-pass", "agent", "profile", (check("c1", VerificationResult.PASS),)
        ).result
        is VerificationResult.PASS
    )
    assert VerificationLayer(
        "vl-partial",
        "agent",
        "profile",
        (check("c1", VerificationResult.PASS), check("c2", VerificationResult.PARTIAL)),
        minimum_pass_ratio=1.0,
    ).blockers == ("AGENT_VERIFICATION_PARTIAL",)
    assert VerificationLayer(
        "vl-fail", "agent", "profile", (check("c1", VerificationResult.FAIL),)
    ).blockers == ("AGENT_VERIFICATION_FAILED",)
    assert VerificationLayer(
        "vl-unknown",
        "agent",
        "profile",
        (check("c1", VerificationResult.UNKNOWN),),
    ).blockers == ("AGENT_VERIFICATION_UNKNOWN",)

    with pytest.raises(ValueError, match="identity is required"):
        VerificationCheck(" ", "description", VerificationResult.PASS)
    with pytest.raises(ValueError, match="requires checks"):
        VerificationLayer("vl-empty", "agent", "profile", ())
    with pytest.raises(ValueError, match="check IDs must be unique"):
        VerificationLayer(
            "vl-dup",
            "agent",
            "profile",
            (
                check("c1", VerificationResult.PASS),
                check("c1", VerificationResult.PASS),
            ),
        )
    with pytest.raises(ValueError, match="between zero and one"):
        VerificationLayer(
            "vl-ratio",
            "agent",
            "profile",
            (check("c1", VerificationResult.PASS),),
            minimum_pass_ratio=2.0,
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        VerificationLayer(
            "vl-live",
            "agent",
            "profile",
            (check("c1", VerificationResult.PASS),),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        VerificationLayer(
            "vl-unblocked",
            "agent",
            "profile",
            (check("c1", VerificationResult.PASS),),
            live_eligibility_status="READY",
        )

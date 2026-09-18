from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from ai4binance.trust import (
    TrustPlaneAssessment,
    TrustPlaneCapability,
    TrustPlaneConditionalLayer,
    TrustPlaneControl,
    TrustPlaneControlId,
    TrustPlaneControlStatus,
    TrustPlaneLayerCreationStatus,
    TrustPlanePriority,
    TrustPlaneStandard,
    build_conditional_trust_plane_assessment,
    build_default_trust_plane_assessment,
)
from ai4binance.trust import plane as trust_plane


def _trust_plane_control(
    **overrides: object,
) -> TrustPlaneControl:
    values: dict[str, object] = {
        "control_id": TrustPlaneControlId.RAG_EVALUATION_ENGINE,
        "title": "RAG Evaluation Engine",
        "contribution": "Measures Graph RAG faithfulness with local evidence.",
        "priority": TrustPlanePriority.P1,
        "status": TrustPlaneControlStatus.STAGED_RESEARCH_ONLY,
        "capabilities": (TrustPlaneCapability.GRAPH_RAG,),
        "standards": (TrustPlaneStandard.NIST_AI_RMF,),
        "evidence_refs": ("rag-eval-fixture",),
    }
    values.update(overrides)
    return TrustPlaneControl(**cast(Any, values))


def _conditional_layer(
    **overrides: object,
) -> TrustPlaneConditionalLayer:
    values: dict[str, object] = {
        "control_id": TrustPlaneControlId.RAG_EVALUATION_ENGINE,
        "title": "RAG Evaluation Engine",
        "priority": TrustPlanePriority.P1,
        "requested": True,
        "created": False,
        "creation_status": TrustPlaneLayerCreationStatus.EVIDENCE_REQUIRED,
        "required_evidence_refs": (
            "rag-eval-fixture",
            "citation-faithfulness-report",
        ),
        "blockers": ("ADVANCED_TRUST_LAYER_EVIDENCE_REQUIRED",),
    }
    values.update(overrides)
    return TrustPlaneConditionalLayer(**cast(Any, values))


def test_trust_plane_catalog_covers_requested_controls_and_priorities() -> None:
    assessment = build_default_trust_plane_assessment(
        evidence_refs=("eaacie-trust-assurance",)
    )
    payload = assessment.to_payload()

    assert payload["framework"] == "AI4BINANCE_TRUST_ASSURANCE_GOVERNANCE_PLANE"
    assert set(assessment.priority_counts) == {"P0", "P1", "P2"}
    assert assessment.priority_counts == {"P0": 9, "P1": 9, "P2": 2}
    assert len(assessment.controls) == len(TrustPlaneControlId)
    assert set(assessment.p0_control_ids) == {
        TrustPlaneControlId.DECISION_PROVENANCE_LEDGER.value,
        TrustPlaneControlId.POLICY_AS_CODE_ENGINE.value,
        TrustPlaneControlId.UNCERTAINTY_ABSTENTION_ENGINE.value,
        TrustPlaneControlId.DATA_FEATURE_DECISION_LINEAGE.value,
        TrustPlaneControlId.SEMANTIC_CONTRACT_REGISTRY.value,
        TrustPlaneControlId.VALIDATION_PROMOTION_REGISTRY.value,
        TrustPlaneControlId.AI_OBSERVABILITY_OPENTELEMETRY.value,
        TrustPlaneControlId.SOURCE_TRUST_CLAIM_VERIFICATION.value,
        TrustPlaneControlId.DATA_EGRESS_DLP_GUARD.value,
    }
    assert assessment.external_services_enabled is False
    assert assessment.execution_allowed is False
    assert assessment.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert isinstance(payload["plane_hash"], str)
    assert isinstance(payload["plane_hash"], str)
    plane_hash = payload["plane_hash"]
    assert len(plane_hash) == 64


def test_trust_plane_maps_every_control_to_ai_risk_standards() -> None:
    assessment = build_default_trust_plane_assessment()

    for standard in TrustPlaneStandard:
        assert set(assessment.standard_coverage[standard.value]) == {
            control.control_id.value for control in assessment.controls
        }
    for control in assessment.controls:
        assert set(control.standards) == set(TrustPlaneStandard)


def test_trust_plane_covers_graph_rag_xai_ethics_and_security_capabilities() -> None:
    assessment = build_default_trust_plane_assessment()
    capabilities = {
        capability
        for control in assessment.controls
        for capability in control.capabilities
    }

    assert TrustPlaneCapability.GRAPH_RAG in capabilities
    assert TrustPlaneCapability.XAI_EVIDENCE_GRAPH in capabilities
    assert TrustPlaneCapability.AI_ETHICS in capabilities
    assert TrustPlaneCapability.POLICY_AS_CODE in capabilities
    assert TrustPlaneCapability.DLP in capabilities
    assert TrustPlaneCapability.SUPPLY_CHAIN in capabilities


def test_trust_plane_marks_p0_as_local_active_without_blockers() -> None:
    assessment = build_default_trust_plane_assessment()

    p0_controls = [
        control
        for control in assessment.controls
        if control.priority is TrustPlanePriority.P0
    ]

    assert p0_controls
    assert all(
        control.status is TrustPlaneControlStatus.ACTIVE_LOCAL
        for control in p0_controls
    )
    assert all(not control.blockers for control in p0_controls)


def test_trust_plane_rejects_external_service_or_trading_authority() -> None:
    assessment = build_default_trust_plane_assessment()
    control = assessment.controls[0]

    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(control, execution_allowed=True)
    with pytest.raises(ValueError, match="external services"):
        replace(assessment, external_services_enabled=True)
    with pytest.raises(ValueError, match="requires evidence"):
        build_default_trust_plane_assessment(evidence_refs=())


def test_trust_plane_payload_is_deterministic() -> None:
    first = build_default_trust_plane_assessment(
        evidence_refs=("eaacie-trust-assurance",)
    ).to_payload()
    second = build_default_trust_plane_assessment(
        evidence_refs=("eaacie-trust-assurance",)
    ).to_payload()

    assert first == second


def test_trust_plane_assessment_rejects_duplicate_controls() -> None:
    assessment = build_default_trust_plane_assessment()

    with pytest.raises(ValueError, match="controls must be unique"):
        TrustPlaneAssessment(
            plane_id="duplicate",
            controls=(assessment.controls[0], assessment.controls[0]),
        )


def test_conditional_trust_plane_builds_p0_and_defers_p1_p2_layers() -> None:
    assessment = build_conditional_trust_plane_assessment(
        evidence_refs=("eaacie-trust-assurance",)
    )
    payload = assessment.to_payload()

    assert assessment.priority_counts == {"P0": 9, "P1": 0, "P2": 0}
    assert len(assessment.controls) == 9
    assert len(assessment.conditional_layers) == 11
    assert assessment.conditional_layer_counts == {
        "NOT_REQUESTED": 11,
        "EVIDENCE_REQUIRED": 0,
        "STAGED_RESEARCH_ONLY": 0,
    }
    assert all(layer.created is False for layer in assessment.conditional_layers)
    assert all(
        layer.creation_status is TrustPlaneLayerCreationStatus.NOT_REQUESTED
        for layer in assessment.conditional_layers
    )
    plane_hash = payload["plane_hash"]
    assert isinstance(plane_hash, str)
    assert len(plane_hash) == 64
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_conditional_trust_plane_requires_evidence_for_requested_p1_layer() -> None:
    assessment = build_conditional_trust_plane_assessment(
        requested_layers=(TrustPlaneControlId.RAG_EVALUATION_ENGINE,),
    )
    layer = next(
        item
        for item in assessment.conditional_layers
        if item.control_id is TrustPlaneControlId.RAG_EVALUATION_ENGINE
    )

    assert layer.requested is True
    assert layer.created is False
    assert layer.creation_status is TrustPlaneLayerCreationStatus.EVIDENCE_REQUIRED
    assert "ADVANCED_TRUST_LAYER_EVIDENCE_REQUIRED" in layer.blockers
    assert "RAG_EVALUATION_FIXTURE_REQUIRED" in layer.blockers
    assert TrustPlaneControlId.RAG_EVALUATION_ENGINE not in {
        control.control_id for control in assessment.controls
    }


def test_conditional_trust_plane_creates_requested_layer_with_evidence() -> None:
    assessment = build_conditional_trust_plane_assessment(
        requested_layers=(TrustPlaneControlId.RAG_EVALUATION_ENGINE,),
        layer_evidence_refs={
            TrustPlaneControlId.RAG_EVALUATION_ENGINE: (
                "rag-eval-fixture:local",
                "citation-faithfulness-report:local",
            )
        },
    )
    layer = next(
        item
        for item in assessment.conditional_layers
        if item.control_id is TrustPlaneControlId.RAG_EVALUATION_ENGINE
    )
    control = next(
        item
        for item in assessment.controls
        if item.control_id is TrustPlaneControlId.RAG_EVALUATION_ENGINE
    )

    assert layer.requested is True
    assert layer.created is True
    assert layer.creation_status is TrustPlaneLayerCreationStatus.STAGED_RESEARCH_ONLY
    assert control.status is TrustPlaneControlStatus.STAGED_RESEARCH_ONLY
    assert "ADVANCED_TRUST_LAYER_RESEARCH_ONLY" in control.blockers
    assert "create:conditional-trust-layer" in control.action_refs
    assert control.execution_allowed is False
    assert control.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_conditional_trust_plane_rejects_p0_request_and_bad_layer_state() -> None:
    with pytest.raises(ValueError, match="P0 trust controls are always-on"):
        build_conditional_trust_plane_assessment(
            requested_layers=(TrustPlaneControlId.DECISION_PROVENANCE_LEDGER,),
        )
    with pytest.raises(ValueError, match="only for P1/P2"):
        TrustPlaneConditionalLayer(
            control_id=TrustPlaneControlId.DECISION_PROVENANCE_LEDGER,
            title="Decision Provenance Ledger",
            priority=TrustPlanePriority.P0,
            requested=False,
            created=False,
            creation_status=TrustPlaneLayerCreationStatus.NOT_REQUESTED,
            required_evidence_refs=("provenance",),
        )


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"title": ""}, "title"),
        ({"contribution": ""}, "contribution"),
        ({"capabilities": ()}, "requires capabilities"),
        ({"standards": ()}, "requires standards"),
        ({"evidence_refs": ()}, "requires evidence"),
        (
            {
                "status": TrustPlaneControlStatus.ACTIVE_LOCAL,
                "blockers": ("UNEXPECTED_BLOCKER",),
            },
            "active local",
        ),
        ({"execution_allowed": True}, "cannot authorize trading"),
    ],
)
def test_trust_plane_control_rejects_invalid_safety_states(
    overrides: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _trust_plane_control(**overrides)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"title": ""}, "title"),
        ({"required_evidence_refs": ()}, "requires evidence"),
        (
            {
                "created": True,
                "creation_status": TrustPlaneLayerCreationStatus.EVIDENCE_REQUIRED,
            },
            "must be staged",
        ),
        (
            {
                "requested": False,
                "created": True,
                "creation_status": TrustPlaneLayerCreationStatus.STAGED_RESEARCH_ONLY,
            },
            "cannot be created",
        ),
        ({"blockers": ()}, "must carry blockers"),
        ({"execution_allowed": True}, "cannot authorize trading"),
    ],
)
def test_conditional_layer_rejects_invalid_creation_states(
    overrides: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _conditional_layer(**overrides)


def test_trust_plane_assessment_rejects_invalid_conditional_relationships() -> None:
    with pytest.raises(ValueError, match="plane id"):
        TrustPlaneAssessment(plane_id="", controls=(_trust_plane_control(),))
    with pytest.raises(ValueError, match="requires controls"):
        TrustPlaneAssessment(plane_id="empty", controls=())

    created_layer = _conditional_layer(
        created=True,
        creation_status=TrustPlaneLayerCreationStatus.STAGED_RESEARCH_ONLY,
        provided_evidence_refs=("rag-eval-fixture",),
        blockers=(),
    )
    unrelated_control = _trust_plane_control(
        control_id=TrustPlaneControlId.DECISION_PROVENANCE_LEDGER,
        title="Decision Provenance Ledger",
        priority=TrustPlanePriority.P0,
        status=TrustPlaneControlStatus.ACTIVE_LOCAL,
        capabilities=(TrustPlaneCapability.XAI_EVIDENCE_GRAPH,),
    )
    with pytest.raises(ValueError, match="requires a control"):
        TrustPlaneAssessment(
            plane_id="missing-created-control",
            controls=(unrelated_control,),
            conditional_layers=(created_layer,),
        )

    not_requested_layer = _conditional_layer(
        requested=False,
        creation_status=TrustPlaneLayerCreationStatus.NOT_REQUESTED,
        blockers=(),
    )
    with pytest.raises(ValueError, match="uncreated conditional layer"):
        TrustPlaneAssessment(
            plane_id="uncreated-with-control",
            controls=(_trust_plane_control(),),
            conditional_layers=(not_requested_layer,),
        )


def test_conditional_trust_plane_rejects_missing_or_unknown_evidence_scope() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        build_conditional_trust_plane_assessment(evidence_refs=())
    with pytest.raises(ValueError, match="cannot contain blanks"):
        build_conditional_trust_plane_assessment(evidence_refs=(" ",))
    with pytest.raises(ValueError, match="requested trust layer is unknown"):
        trust_plane._validate_requested_layers(
            (TrustPlaneControlId.RAG_EVALUATION_ENGINE,),
            {},
        )

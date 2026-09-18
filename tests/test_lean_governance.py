from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.governance import (
    QAQC_AGENT_DISPLAY_NAME,
    QAQC_AGENT_ID,
    DmaicStage,
    FiveSWorkspaceEvidence,
    HoshinObjective,
    HoshinPlan,
    KaizenImprovementEvidence,
    KaizenStage,
    LeanGovernanceAssessment,
    LeanPillar,
    PokaYokeCheck,
    PokaYokeEvidence,
    QAQCAgentProfile,
    SixSigmaProcessEvidence,
    assess_five_s_workspace,
    assess_hoshin_plan,
    assess_kaizen_improvement,
    assess_poka_yoke_workflow,
    assess_six_sigma_process,
    build_qaqc_agent_profile,
)

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def clean_five_s() -> FiveSWorkspaceEvidence:
    return FiveSWorkspaceEvidence(
        workspace_id="ai4binance",
        observed_at=NOW,
        canonical_quality_command=(
            "powershell.exe -NoProfile -ExecutionPolicy Bypass "
            "-File .\\scripts\\quality.ps1"
        ),
        documentation_index_present=True,
        sustain_owner="platform-owner",
    )


def objective(
    *,
    objective_id: str = "oos-run-card",
    due_at: datetime = NOW + timedelta(days=30),
    current: float = 0.9,
    validation_artifact_ids: tuple[str, ...] = ("run-card:1",),
) -> HoshinObjective:
    return HoshinObjective(
        objective_id=objective_id,
        annual_priority="Improve validation evidence without widening authority",
        owner="validation-owner",
        metric_name="validated_artifact_ratio",
        baseline=0.0,
        target=1.0,
        current=current,
        due_at=due_at,
        linked_blockers=("WEAK_OOS_FOLD_CONSISTENCY",),
        validation_artifact_ids=validation_artifact_ids,
    )


def hoshin_plan() -> HoshinPlan:
    return HoshinPlan(
        plan_id="ai4binance-2026-validation",
        created_at=NOW,
        north_star="Increase reproducible OOS evidence while staying research-only",
        objectives=(objective(),),
        catchball_reviewed=True,
    )


def complete_poka_yoke() -> PokaYokeEvidence:
    return PokaYokeEvidence(
        workflow_id="validate-research",
        observed_at=NOW,
        passed_checks=tuple(PokaYokeCheck),
    )


def kaizen_improvement() -> KaizenImprovementEvidence:
    return KaizenImprovementEvidence(
        improvement_id="kaizen:oos-blocker-dashboard",
        observed_at=NOW,
        stage=KaizenStage.ACT,
        problem_statement="OOS blockers need actionable follow-up evidence.",
        hypothesis="Blocker dashboards reduce ambiguity without weakening gates.",
        owner="validation-owner",
        metric_name="blocker_actionability_ratio",
        baseline=0.0,
        target=1.0,
        current=1.0,
        linked_blockers=("WEAK_OOS_FOLD_CONSISTENCY",),
        experiment_artifact_ids=("blocker-dashboard.json",),
    )


def six_sigma_process() -> SixSigmaProcessEvidence:
    return SixSigmaProcessEvidence(
        process_id="six-sigma:validation",
        observed_at=NOW,
        stage=DmaicStage.CONTROL,
        defect_name="unactionable validation blocker",
        opportunities=100,
        defects=2,
        baseline_dpmo=250_000.0,
        current_dpmo=20_000.0,
        target_dpmo=50_000.0,
        sigma_level=3.5,
        linked_blockers=("VALIDATION_ACTION_TRACE_MISSING",),
        measurement_system_validated=True,
        control_plan_artifact_ids=("control-plan.json",),
    )


def test_5s_assessment_passes_clean_workspace_without_authority() -> None:
    result = assess_five_s_workspace(clean_five_s())

    assert result.pillar is LeanPillar.FIVE_S
    assert result.passed is True
    assert result.blockers == ()
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert result.promotion_status == "RESEARCH_ONLY"


def test_qaqc_agent_profile_names_governed_improvement_authority() -> None:
    profile = build_qaqc_agent_profile()

    assert profile.agent_id == QAQC_AGENT_ID
    assert profile.display_name == QAQC_AGENT_DISPLAY_NAME
    assert profile.methods == (
        LeanPillar.FIVE_S,
        LeanPillar.HOSHIN_KANRI,
        LeanPillar.KAIZEN,
        LeanPillar.SIX_SIGMA,
        LeanPillar.POKA_YOKE,
    )
    assert "SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL" in profile.capabilities
    assert profile.authority == "GOVERNED_EDITING_AND_IMPROVEMENT_REVIEW"
    assert profile.execution_allowed is False
    assert profile.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_qaqc_agent_profile_rejects_blank_and_duplicate_governance_shapes() -> None:
    with pytest.raises(ValueError, match="identity cannot be empty"):
        QAQCAgentProfile(
            agent_id=" ",
            display_name=QAQC_AGENT_DISPLAY_NAME,
            methods=(LeanPillar.FIVE_S,),
            capabilities=("SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",),
        )
    with pytest.raises(ValueError, match="methods cannot be empty"):
        QAQCAgentProfile(
            agent_id=QAQC_AGENT_ID,
            display_name=QAQC_AGENT_DISPLAY_NAME,
            methods=(),
            capabilities=("SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",),
        )
    with pytest.raises(ValueError, match="methods must be unique"):
        QAQCAgentProfile(
            agent_id=QAQC_AGENT_ID,
            display_name=QAQC_AGENT_DISPLAY_NAME,
            methods=(LeanPillar.FIVE_S, LeanPillar.FIVE_S),
            capabilities=("SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",),
        )
    with pytest.raises(ValueError, match="capabilities cannot be blank"):
        QAQCAgentProfile(
            agent_id=QAQC_AGENT_ID,
            display_name=QAQC_AGENT_DISPLAY_NAME,
            methods=(LeanPillar.FIVE_S,),
            capabilities=(" ",),
        )
    with pytest.raises(ValueError, match="capabilities must be unique"):
        QAQCAgentProfile(
            agent_id=QAQC_AGENT_ID,
            display_name=QAQC_AGENT_DISPLAY_NAME,
            methods=(LeanPillar.FIVE_S,),
            capabilities=(
                "SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",
                "SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",
            ),
        )
    with pytest.raises(ValueError, match="cannot promote research"):
        QAQCAgentProfile(
            agent_id=QAQC_AGENT_ID,
            display_name=QAQC_AGENT_DISPLAY_NAME,
            methods=(LeanPillar.FIVE_S,),
            capabilities=("SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",),
            promotion_status="LIVE_APPROVED",
        )


def test_5s_assessment_turns_workspace_debt_into_actions() -> None:
    result = assess_five_s_workspace(
        FiveSWorkspaceEvidence(
            workspace_id="ai4binance",
            observed_at=NOW,
            orphan_artifact_paths=("artifacts/old-report.json",),
            stale_temp_paths=("artifacts/test_temp/locked",),
            secret_like_paths=("secrets/bnc.env",),
        )
    )

    assert result.passed is False
    assert result.blockers == (
        "FIVE_S_SORT_ORPHAN_ARTIFACTS",
        "FIVE_S_SET_IN_ORDER_QUALITY_COMMAND_MISSING",
        "FIVE_S_SHINE_STALE_TEMP_REVIEW_REQUIRED",
        "FIVE_S_STANDARDIZE_DOC_INDEX_MISSING",
        "FIVE_S_SUSTAIN_OWNER_MISSING",
        "FIVE_S_SECRET_LIKE_PATH_REVIEW_REQUIRED",
    )
    assert "never print values" in result.kaizen_actions[-1]


def test_hoshin_plan_requires_catchball_and_validation_artifacts() -> None:
    result = assess_hoshin_plan(
        replace(
            hoshin_plan(),
            catchball_reviewed=False,
            objectives=(
                objective(
                    objective_id="late",
                    due_at=NOW - timedelta(days=1),
                    current=0.4,
                    validation_artifact_ids=(),
                ),
            ),
        ),
        as_of=NOW,
    )

    assert result.pillar is LeanPillar.HOSHIN_KANRI
    assert result.passed is False
    assert result.blockers == (
        "HOSHIN_CATCHBALL_REVIEW_MISSING",
        "HOSHIN_OBJECTIVE_OVERDUE:late",
        "HOSHIN_VALIDATION_ARTIFACT_MISSING:late",
    )
    assert result.execution_allowed is False


def test_hoshin_plan_passes_when_objectives_are_aligned() -> None:
    result = assess_hoshin_plan(hoshin_plan(), as_of=NOW)

    assert result.passed is True
    assert result.blockers == ()
    assert hoshin_plan().objectives[0].progress_ratio == 0.9


def test_poka_yoke_requires_all_mandatory_error_proofing_checks() -> None:
    result = assess_poka_yoke_workflow(
        PokaYokeEvidence(
            workflow_id="validate-research",
            observed_at=NOW,
            passed_checks=(PokaYokeCheck.LIVE_GATE_FAIL_CLOSED,),
            failed_checks=(PokaYokeCheck.REDACTION_GATE,),
        )
    )

    assert result.pillar is LeanPillar.POKA_YOKE
    assert result.passed is False
    assert "POKA_YOKE_CHECK_FAILED:REDACTION_GATE" in result.blockers
    assert "POKA_YOKE_CHECK_MISSING:TECHNICAL_QUALITY_PASS" in result.blockers
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_poka_yoke_passes_complete_workflow_without_trading_authority() -> None:
    result = assess_poka_yoke_workflow(complete_poka_yoke())

    assert result.passed is True
    assert result.blockers == ()
    assert result.execution_allowed is False


def test_kaizen_assessment_requires_reversible_pdca_evidence() -> None:
    result = assess_kaizen_improvement(
        replace(
            kaizen_improvement(),
            stage=KaizenStage.ACT,
            current=0.5,
            experiment_artifact_ids=(),
            reversible=False,
        )
    )

    assert result.pillar is LeanPillar.KAIZEN
    assert result.passed is False
    assert result.blockers == (
        "KAIZEN_REVERSIBILITY_MISSING",
        "KAIZEN_EXPERIMENT_ARTIFACT_MISSING",
        "KAIZEN_TARGET_NOT_REACHED",
    )
    assert result.execution_allowed is False


def test_kaizen_assessment_passes_completed_small_improvement() -> None:
    result = assess_kaizen_improvement(kaizen_improvement())

    assert result.passed is True
    assert result.blockers == ()
    assert result.promotion_status == "RESEARCH_ONLY"


def test_six_sigma_assessment_requires_measurement_target_and_control_plan() -> None:
    result = assess_six_sigma_process(
        replace(
            six_sigma_process(),
            measurement_system_validated=False,
            defects=30,
            current_dpmo=300_000.0,
            control_plan_artifact_ids=(),
        )
    )

    assert result.pillar is LeanPillar.SIX_SIGMA
    assert result.passed is False
    assert result.blockers == (
        "SIX_SIGMA_MEASUREMENT_SYSTEM_UNVALIDATED",
        "SIX_SIGMA_TARGET_DPMO_NOT_MET",
        "SIX_SIGMA_CONTROL_PLAN_MISSING",
        "SIX_SIGMA_DEFECT_REDUCTION_NOT_OBSERVED",
    )
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_six_sigma_assessment_passes_controlled_defect_reduction() -> None:
    result = assess_six_sigma_process(six_sigma_process())

    assert result.passed is True
    assert result.blockers == ()
    assert result.execution_allowed is False
    assert six_sigma_process().calculated_dpmo == 20_000.0


def test_six_sigma_evidence_rejects_dpmo_that_disagrees_with_counts() -> None:
    with pytest.raises(ValueError, match="current DPMO must match defect counts"):
        replace(six_sigma_process(), current_dpmo=19_999.0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(clean_five_s(), workspace_id=""),
        lambda: replace(clean_five_s(), observed_at=datetime(2026, 7, 17)),
        lambda: replace(clean_five_s(), audit_interval_days=0),
        lambda: replace(clean_five_s(), execution_allowed=True),
        lambda: replace(objective(), objective_id=""),
        lambda: replace(objective(), due_at=datetime(2026, 7, 17)),
        lambda: replace(objective(), target=0.0),
        lambda: replace(objective(), linked_blockers=()),
        lambda: replace(objective(), validation_artifact_ids=("a", "a")),
        lambda: replace(objective(), execution_allowed=True),
        lambda: replace(hoshin_plan(), plan_id=""),
        lambda: replace(hoshin_plan(), objectives=()),
        lambda: replace(hoshin_plan(), objectives=(objective(), objective())),
        lambda: replace(hoshin_plan(), execution_allowed=True),
        lambda: replace(complete_poka_yoke(), workflow_id=""),
        lambda: replace(complete_poka_yoke(), observed_at=datetime(2026, 7, 17)),
        lambda: PokaYokeEvidence(
            "workflow",
            NOW,
            (PokaYokeCheck.LIVE_GATE_FAIL_CLOSED,),
            (PokaYokeCheck.LIVE_GATE_FAIL_CLOSED,),
        ),
        lambda: replace(complete_poka_yoke(), execution_allowed=True),
        lambda: replace(kaizen_improvement(), improvement_id=""),
        lambda: replace(kaizen_improvement(), observed_at=datetime(2026, 7, 17)),
        lambda: replace(kaizen_improvement(), target=0.0),
        lambda: replace(kaizen_improvement(), linked_blockers=()),
        lambda: replace(kaizen_improvement(), experiment_artifact_ids=("a", "a")),
        lambda: replace(kaizen_improvement(), execution_allowed=True),
        lambda: replace(six_sigma_process(), process_id=""),
        lambda: replace(six_sigma_process(), observed_at=datetime(2026, 7, 17)),
        lambda: replace(six_sigma_process(), opportunities=0),
        lambda: replace(six_sigma_process(), defects=101),
        lambda: replace(six_sigma_process(), current_dpmo=-1.0),
        lambda: replace(six_sigma_process(), linked_blockers=()),
        lambda: replace(six_sigma_process(), control_plan_artifact_ids=("a", "a")),
        lambda: replace(six_sigma_process(), execution_allowed=True),
        lambda: LeanGovernanceAssessment(
            LeanPillar.FIVE_S,
            "subject",
            True,
            ("BLOCKER",),
            (),
        ),
        lambda: LeanGovernanceAssessment(
            LeanPillar.FIVE_S,
            "subject",
            True,
            (),
            (),
            execution_allowed=True,
        ),
        lambda: QAQCAgentProfile(
            QAQC_AGENT_ID,
            QAQC_AGENT_DISPLAY_NAME,
            (LeanPillar.FIVE_S,),
            ("SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",),
            execution_allowed=True,
        ),
    ],
)
def test_lean_governance_rejects_invalid_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()

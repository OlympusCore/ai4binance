from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.governance.development import (
    DevelopmentRunCard,
    DevelopmentStage,
    StageEvidence,
)
from ai4binance.governance.supply_chain import (
    ExternalCapability,
    ExternalComponentManifest,
    ExternalResearchIntake,
    ExternalSkillManifest,
    SupplyChainAssessment,
    assess_external_component,
    assess_external_skill,
)
from ai4binance.research_catalog import CatalogStatus, ResearchCatalogEntry

NOW = datetime(2026, 7, 13, tzinfo=UTC)
HASH = "a" * 64
REVISION = "b" * 40


def manifest(
    capabilities: tuple[ExternalCapability, ...] = (
        ExternalCapability.ADVISORY_READ_ONLY,
    ),
) -> ExternalComponentManifest:
    return ExternalComponentManifest(
        component_id="obra-superpowers-patterns",
        source_url="https://github.com/obra/superpowers",
        pinned_revision=REVISION,
        license_id="MIT",
        license_sha256=HASH,
        content_sha256=HASH,
        declared_capabilities=capabilities,
        reviewed_at=NOW,
    )


def catalog_entry(
    *,
    status: CatalogStatus = CatalogStatus.DISCOVERED,
    blockers: tuple[str, ...] = ("SOURCE_EVIDENCE_NOT_REPRODUCED",),
) -> ResearchCatalogEntry:
    item = manifest()
    return ResearchCatalogEntry(
        entry_id=item.component_id,
        title="Governed external research source",
        source_url=item.source_url,
        source_revision=item.pinned_revision,
        license_id=item.license_id,
        hypothesis="A reviewed source may inform an isolated experiment.",
        asset_classes=("CRYPTO_SPOT",),
        timeframes=("15m", "1h", "4h", "1d"),
        leakage_risks=("SOURCE_IMPLEMENTATION_BIAS",),
        data_requirements=("PINNED_SOURCE_EVIDENCE",),
        cost_assumptions=("NO_INSTALL_OR_EXECUTION",),
        discovered_at=NOW,
        updated_at=NOW,
        status=status,
        blockers=blockers,
    )


def evidence(stage: DevelopmentStage, index: int = 0) -> StageEvidence:
    return StageEvidence(
        stage=stage,
        recorded_at=NOW + timedelta(seconds=index),
        artifact_sha256=f"{index:x}".rjust(64, "0"),
        summary=f"Evidence for {stage}",
        passed=True,
    )


def test_supply_chain_allows_only_fully_reviewed_read_only_experiment() -> None:
    result = assess_external_component(
        manifest(),
        license_compatible=True,
        security_scan_passed=True,
        sandbox_review_passed=True,
        human_approved=True,
    )
    assert result.approved_for_isolated_experiment is True
    assert result.quarantine_required is False
    assert result.execution_allowed is False
    assert result.installation_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_supply_chain_quarantines_missing_review_and_risky_capabilities() -> None:
    result = assess_external_component(
        manifest((ExternalCapability.NETWORK, ExternalCapability.SUBPROCESS)),
        license_compatible=False,
        security_scan_passed=False,
        sandbox_review_passed=False,
        human_approved=False,
    )
    assert result.approved_for_isolated_experiment is False
    assert result.quarantine_required is True
    assert result.blockers == (
        "EXTERNAL_LICENSE_NOT_APPROVED",
        "EXTERNAL_SECURITY_SCAN_MISSING",
        "EXTERNAL_SANDBOX_REVIEW_MISSING",
        "EXTERNAL_HUMAN_APPROVAL_MISSING",
        "EXTERNAL_HIGH_RISK_CAPABILITY_DECLARED",
    )


def test_external_skill_manifest_keeps_allowed_tools_and_scripts_quarantined() -> None:
    skill = ExternalSkillManifest(
        component=manifest(),
        skill_name="agent-skills-example",
        allowed_tools_declared="Bash(git:*) Read",
        scripts_declared=True,
        references_declared=True,
    )
    result = assess_external_skill(
        skill,
        license_compatible=True,
        security_scan_passed=True,
        sandbox_review_passed=True,
        human_approved=True,
    )

    assert result.approved_for_isolated_experiment is False
    assert result.quarantine_required is True
    assert result.blockers == (
        "EXTERNAL_ALLOWED_TOOLS_UNENFORCED",
        "EXTERNAL_SKILL_SCRIPT_DECLARED",
    )
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(skill, installation_allowed=True)
    with pytest.raises(ValueError, match="skill name"):
        replace(skill, skill_name="Bad_Name")


def test_external_research_intake_binds_pinned_evidence_without_authority() -> None:
    reviewed = assess_external_component(
        manifest(),
        license_compatible=True,
        security_scan_passed=True,
        sandbox_review_passed=True,
        human_approved=True,
    )
    intake = ExternalResearchIntake(
        catalog_entry=catalog_entry(
            status=CatalogStatus.REPRODUCTION_PENDING,
            blockers=("REPRODUCTION_NOT_RUN",),
        ),
        manifest=manifest(),
        assessment=reviewed,
    )

    assert intake.reproduction_allowed is True
    assert intake.execution_allowed is False
    assert intake.installation_allowed is False
    assert intake.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(intake, execution_allowed=True)
    with pytest.raises(ValueError, match="live-order blocked"):
        replace(intake, live_eligibility_status="LIVE_READY")


def test_external_research_intake_keeps_quarantine_blockers_out_of_queue() -> None:
    quarantined = assess_external_component(
        manifest(),
        license_compatible=False,
        security_scan_passed=False,
        sandbox_review_passed=False,
        human_approved=False,
    )
    item = catalog_entry(blockers=quarantined.blockers)
    intake = ExternalResearchIntake(
        catalog_entry=item,
        manifest=manifest(),
        assessment=quarantined,
    )

    assert intake.reproduction_allowed is False
    with pytest.raises(ValueError, match="retain supply-chain blockers"):
        ExternalResearchIntake(
            catalog_entry=catalog_entry(),
            manifest=manifest(),
            assessment=quarantined,
        )
    with pytest.raises(ValueError, match="cannot enter reproduction queue"):
        ExternalResearchIntake(
            catalog_entry=replace(
                item,
                status=CatalogStatus.REPRODUCTION_PENDING,
            ),
            manifest=manifest(),
            assessment=quarantined,
        )


def _different_entry_url(entry: ResearchCatalogEntry) -> ResearchCatalogEntry:
    return replace(entry, source_url="https://github.com/example/other")


def _different_entry_revision(entry: ResearchCatalogEntry) -> ResearchCatalogEntry:
    return replace(entry, source_revision="c" * 40)


def _different_entry_license(entry: ResearchCatalogEntry) -> ResearchCatalogEntry:
    return replace(entry, license_id="Apache-2.0")


def _different_manifest_identity(
    item: ExternalComponentManifest,
) -> ExternalComponentManifest:
    return replace(item, component_id="different-component")


def _different_assessment_identity(
    item: SupplyChainAssessment,
) -> SupplyChainAssessment:
    return replace(item, component_id="different-component")


def _unchanged_entry(entry: ResearchCatalogEntry) -> ResearchCatalogEntry:
    return entry


def _unchanged_manifest(
    item: ExternalComponentManifest,
) -> ExternalComponentManifest:
    return item


def _unchanged_assessment(item: SupplyChainAssessment) -> SupplyChainAssessment:
    return item


@pytest.mark.parametrize(
    ("entry_mutator", "manifest_mutator", "assessment_mutator"),
    [
        (_different_entry_url, _unchanged_manifest, _unchanged_assessment),
        (_different_entry_revision, _unchanged_manifest, _unchanged_assessment),
        (_different_entry_license, _unchanged_manifest, _unchanged_assessment),
        (_unchanged_entry, _different_manifest_identity, _unchanged_assessment),
        (_unchanged_entry, _unchanged_manifest, _different_assessment_identity),
    ],
)
def test_external_research_intake_rejects_mismatched_provenance(
    entry_mutator: Callable[[ResearchCatalogEntry], ResearchCatalogEntry],
    manifest_mutator: Callable[[ExternalComponentManifest], ExternalComponentManifest],
    assessment_mutator: Callable[[SupplyChainAssessment], SupplyChainAssessment],
) -> None:
    reviewed = assess_external_component(
        manifest(),
        license_compatible=True,
        security_scan_passed=True,
        sandbox_review_passed=True,
        human_approved=True,
    )
    with pytest.raises(ValueError, match="external intake"):
        ExternalResearchIntake(
            catalog_entry=entry_mutator(catalog_entry()),
            manifest=manifest_mutator(manifest()),
            assessment=assessment_mutator(reviewed),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(manifest(), source_url="http://example.com/source"),
        lambda: replace(manifest(), pinned_revision="UNPINNED"),
        lambda: replace(manifest(), component_id=""),
        lambda: replace(manifest(), license_sha256="invalid"),
        lambda: replace(manifest(), declared_capabilities=()),
        lambda: replace(manifest(), reviewed_at=datetime(2026, 7, 13)),
        lambda: replace(manifest(), installation_allowed=True),
    ],
)
def test_supply_chain_manifest_rejects_untrusted_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"external component"):
        factory()


def test_development_run_requires_contiguous_evidence_and_human_completion() -> None:
    stages = tuple(DevelopmentStage)
    card = DevelopmentRunCard.start(
        run_id="run-1",
        objective="Add a fail-closed governance gate",
        evidence=evidence(stages[0]),
    )
    for index, stage in enumerate(stages[1:-1], start=1):
        card = card.advance(evidence(stage, index))
    with pytest.raises(ValueError, match="human approval"):
        card.advance(evidence(DevelopmentStage.COMPLETED, len(stages) - 1))
    completed = card.advance(
        evidence(DevelopmentStage.COMPLETED, len(stages) - 1),
        human_approved=True,
    )
    assert completed.stage is DevelopmentStage.COMPLETED
    assert completed.execution_allowed is False
    assert completed.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_development_run_blocks_skips_and_invalid_evidence() -> None:
    first = evidence(DevelopmentStage.SPEC_REGISTERED)
    card = DevelopmentRunCard.start(
        run_id="run-1", objective="Objective", evidence=first
    )
    with pytest.raises(ValueError, match="contiguous"):
        card.advance(evidence(DevelopmentStage.MINIMAL_IMPLEMENTATION, 1))
    with pytest.raises(ValueError, match="registered spec"):
        DevelopmentRunCard.start(
            run_id="run-2",
            objective="Objective",
            evidence=evidence(DevelopmentStage.TEST_RED_CONFIRMED),
        )
    with pytest.raises(ValueError, match="failed evidence"):
        replace(first, passed=False)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(
            evidence(DevelopmentStage.SPEC_REGISTERED),
            recorded_at=datetime(2026, 7, 13),
        ),
        lambda: replace(
            evidence(DevelopmentStage.SPEC_REGISTERED), artifact_sha256="bad"
        ),
        lambda: replace(evidence(DevelopmentStage.SPEC_REGISTERED), summary=""),
        lambda: DevelopmentRunCard(
            "",
            "objective",
            DevelopmentStage.SPEC_REGISTERED,
            (evidence(DevelopmentStage.SPEC_REGISTERED),),
        ),
        lambda: DevelopmentRunCard(
            "run",
            "x" * 2_001,
            DevelopmentStage.SPEC_REGISTERED,
            (evidence(DevelopmentStage.SPEC_REGISTERED),),
        ),
        lambda: DevelopmentRunCard(
            "run",
            "objective",
            DevelopmentStage.TEST_RED_CONFIRMED,
            (evidence(DevelopmentStage.SPEC_REGISTERED),),
        ),
        lambda: DevelopmentRunCard(
            "run",
            "objective",
            DevelopmentStage.MINIMAL_IMPLEMENTATION,
            (
                evidence(DevelopmentStage.SPEC_REGISTERED),
                evidence(DevelopmentStage.MINIMAL_IMPLEMENTATION),
            ),
        ),
        lambda: replace(
            DevelopmentRunCard.start(
                run_id="run",
                objective="objective",
                evidence=evidence(DevelopmentStage.SPEC_REGISTERED),
            ),
            execution_allowed=True,
        ),
        lambda: SupplyChainAssessment("item", True, False, ("BLOCKER",)),
        lambda: SupplyChainAssessment("item", False, False, ("BLOCKER",)),
        lambda: SupplyChainAssessment("item", True, False, (), execution_allowed=True),
    ],
)
def test_governance_contract_invariants(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()

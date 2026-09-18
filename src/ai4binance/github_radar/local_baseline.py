"""Map the research ontology to current AI4BINANCE local evidence."""

from __future__ import annotations

from pathlib import Path

from ai4binance.enterprise.vnext_gap_audit import (
    VnextEvidenceDepth,
    build_vnext_gap_audit,
)
from ai4binance.github_radar.models import (
    LocalCapabilityAssessment,
    LocalCapabilityStatus,
    ResearchOntology,
)
from ai4binance.github_radar.ontology import load_default_ontology


def build_local_capability_baseline(
    repository_root: Path | None = None,
    ontology: ResearchOntology | None = None,
) -> tuple[LocalCapabilityAssessment, ...]:
    """Build a deterministic, report-only local capability baseline."""
    root = (repository_root or Path.cwd()).resolve()
    active_ontology = ontology or load_default_ontology(root)
    gap_report = build_vnext_gap_audit(root)
    assessments: list[LocalCapabilityAssessment] = []
    for capability in active_ontology.capabilities:
        present = tuple(
            item for item in capability.local_evidence if (root / item).exists()
        )
        missing = tuple(
            item for item in capability.local_evidence if not (root / item).exists()
        )
        related = tuple(
            gap
            for gap in gap_report.capabilities
            if set(gap.evidence_files) & set(capability.local_evidence)
        )
        status = _status(present, related)
        blockers = tuple(
            dict.fromkeys(
                (
                    *(f"LOCAL_EVIDENCE_MISSING:{item}" for item in missing),
                    *(
                        f"LOCAL_GAP:{gap.capability_id}:{control}"
                        for gap in related
                        for control in gap.missing_controls[:2]
                    ),
                    *(
                        f"VALIDATION_PROFILE_PENDING:{profile}"
                        for profile in capability.verification_profiles
                    ),
                )
            )
        )
        assessments.append(
            LocalCapabilityAssessment(
                capability_id=capability.capability_id,
                status=status,
                present_evidence=present,
                missing_evidence=missing,
                target_agents=capability.target_agents,
                target_layers=capability.target_layers,
                related_gap_ids=tuple(gap.capability_id for gap in related),
                blockers=blockers,
            )
        )
    return tuple(assessments)


def _status(
    present: tuple[str, ...], related: tuple[object, ...]
) -> LocalCapabilityStatus:
    if not present:
        return LocalCapabilityStatus.RESEARCH_GAP
    depths = {
        getattr(item, "evidence_depth", VnextEvidenceDepth.CODE_ONLY)
        for item in related
    }
    if VnextEvidenceDepth.PRODUCTION_EVIDENCE in depths:
        return LocalCapabilityStatus.PRODUCTION_EVIDENCE
    if VnextEvidenceDepth.RUNTIME_WIRED in depths:
        return LocalCapabilityStatus.RUNTIME_WIRED
    if VnextEvidenceDepth.TESTED_CONTRACT in depths or any(
        item.startswith("tests/") for item in present
    ):
        return LocalCapabilityStatus.TESTED_CONTRACT
    return LocalCapabilityStatus.DECLARED

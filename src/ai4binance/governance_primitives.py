from __future__ import annotations

from enum import StrEnum


class TechnicalQualityStatus(StrEnum):
    TECHNICAL_QUALITY_PASS = "TECHNICAL_QUALITY_PASS"  # noqa: S105  # nosec B105
    LEGACY_QUALITY_GATE_GREEN = "QUALITY_GATE_GREEN"


class FullAssuranceStatus(StrEnum):
    FULL_ASSURANCE_GREEN = "FULL_ASSURANCE_GREEN"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


TECHNICAL_QUALITY_PRIMARY_STATUS = TechnicalQualityStatus.TECHNICAL_QUALITY_PASS.value
TECHNICAL_QUALITY_LEGACY_STATUS = TechnicalQualityStatus.LEGACY_QUALITY_GATE_GREEN.value
TECHNICAL_QUALITY_ACCEPTED_STATUSES = frozenset(
    {
        TECHNICAL_QUALITY_PRIMARY_STATUS,
        TECHNICAL_QUALITY_LEGACY_STATUS,
    }
)

AUTHORITY_BASIS_METADATA_MISSING = "validation:authority_metadata_missing"
AUTHORITY_BASIS_GOVERNED_METADATA_VALIDATED = "validation:governed_metadata_validated"
AUTHORITY_BASIS_PLACEMENT_HINT_ONLY = "validation:placement_hint_only"
PLACEMENT_HINT_PREFIX = "placement_hint:"


def is_technical_quality_pass(status: str) -> bool:
    return status in TECHNICAL_QUALITY_ACCEPTED_STATUSES


def normalize_technical_quality_status(status: str) -> str:
    if not is_technical_quality_pass(status):
        raise ValueError(
            "quality gate evidence must be TECHNICAL_QUALITY_PASS or the "
            "legacy QUALITY_GATE_GREEN alias"
        )
    return TECHNICAL_QUALITY_PRIMARY_STATUS

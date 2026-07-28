"""Default-deny admission policy for an optional visual workflow sidecar."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SidecarPilotEvidence:
    component_id: str
    image_digest: str
    localhost_bound: bool
    authentication_enabled: bool
    ssrf_protection_enabled: bool
    external_network_disabled: bool
    arbitrary_code_disabled: bool
    read_only_artifacts: bool
    resource_limits_enabled: bool
    secrets_mounted: bool
    exchange_adapter_present: bool

    def __post_init__(self) -> None:
        if not self.component_id.strip() or not _IMAGE_DIGEST.fullmatch(
            self.image_digest
        ):
            raise ValueError("sidecar identity or pinned image digest is invalid")


@dataclass(frozen=True, slots=True)
class SidecarPilotAssessment:
    component_id: str
    pilot_allowed: bool
    blockers: tuple[str, ...]
    read_only: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.pilot_allowed == bool(self.blockers):
            raise ValueError("sidecar assessment and blockers disagree")
        if not self.read_only or self.execution_allowed:
            raise ValueError("sidecar pilot must remain read-only")


def assess_sidecar_pilot(evidence: SidecarPilotEvidence) -> SidecarPilotAssessment:
    checks = (
        (evidence.localhost_bound, "SIDECAR_NOT_LOCALHOST_BOUND"),
        (evidence.authentication_enabled, "SIDECAR_AUTHENTICATION_MISSING"),
        (evidence.ssrf_protection_enabled, "SIDECAR_SSRF_PROTECTION_MISSING"),
        (evidence.external_network_disabled, "SIDECAR_EXTERNAL_NETWORK_ENABLED"),
        (evidence.arbitrary_code_disabled, "SIDECAR_ARBITRARY_CODE_ENABLED"),
        (evidence.read_only_artifacts, "SIDECAR_ARTIFACTS_NOT_READ_ONLY"),
        (evidence.resource_limits_enabled, "SIDECAR_RESOURCE_LIMITS_MISSING"),
        (not evidence.secrets_mounted, "SIDECAR_SECRETS_MOUNTED"),
        (not evidence.exchange_adapter_present, "SIDECAR_EXCHANGE_ADAPTER_PRESENT"),
    )
    blockers = tuple(code for passed, code in checks if not passed)
    return SidecarPilotAssessment(
        component_id=evidence.component_id,
        pilot_allowed=not blockers,
        blockers=blockers,
    )

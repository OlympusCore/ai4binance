"""Agent evidence and verification-layer contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Literal

from ai4binance.core.contracts.handoffs import HandoffEvidenceRef


class AgentEvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTED = "CONFLICTED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class VerificationResult(StrEnum):
    PASS = "PASS"  # nosec B105  # noqa: S105 - verification status, not a secret.
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class AgentIntelligenceType(StrEnum):
    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"
    LLM_ADVISORY = "llm_advisory"


class AgentAnatomyPart(StrEnum):
    IDENTITY_CAPABILITY = "Identity & Capability"
    INPUTS_CANONICAL_CONTEXT = "Inputs & Canonical Context"
    INTELLIGENCE_DOMAIN_LOGIC = "Intelligence / Domain Logic"
    EVIDENCE_PROVENANCE = "Evidence & Provenance"
    RUNTIME_STATE = "Runtime State"
    HISTORICAL_MEMORY = "Historical Memory"
    TOOLS_PERMISSIONS = "Tools & Permissions"
    POLICY_AUTHORITY_ESCALATION = "Policy, Authority & Escalation"
    VERIFICATION_FAILURE_HANDLING = "Verification & Failure Handling"
    OBSERVABILITY_LIFECYCLE = "Observability & Lifecycle"


@dataclass(frozen=True, slots=True)
class AgentObservation:
    observation_id: str
    agent_id: str
    agent_version: str
    cycle_id: str
    snapshot_id: str
    symbol: str
    timeframe: str
    capability_ids: tuple[str, ...]
    assessment: str
    confidence: float
    uncertainty: float
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    conflicting_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    data_quality_score: float = 0.0
    execution_authority: Literal["NONE"] = "NONE"

    def __post_init__(self) -> None:
        for field_name in (
            "observation_id",
            "agent_id",
            "agent_version",
            "cycle_id",
            "snapshot_id",
            "symbol",
            "timeframe",
            "assessment",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if not self.capability_ids:
            raise ValueError("agent observation requires capability_ids")
        _require_unique("agent observation capability IDs", self.capability_ids)
        _require_unique("agent observation evidence IDs", self.evidence_ids)
        _require_unique(
            "agent observation conflicting evidence IDs",
            self.conflicting_evidence_ids,
        )
        _require_unique("agent observation blockers", self.blockers)
        for field_name in ("confidence", "uncertainty", "data_quality_score"):
            value = getattr(self, field_name)
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between zero and one")
        if self.execution_authority != "NONE":
            raise ValueError("agent observations must not carry execution authority")


@dataclass(frozen=True, slots=True)
class AgentIdentityContract:
    agent_id: str
    version: str
    role: str

    def __post_init__(self) -> None:
        for field_name in ("agent_id", "version", "role"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")


@dataclass(frozen=True, slots=True)
class AgentCapabilitiesContract:
    capability_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.capability_ids:
            raise ValueError("agent contract requires capability_ids")
        _require_unique("agent contract capability IDs", self.capability_ids)


@dataclass(frozen=True, slots=True)
class AgentInputsContract:
    canonical_only: bool = True

    def __post_init__(self) -> None:
        if not self.canonical_only:
            raise ValueError("agent inputs must be canonical_only")


@dataclass(frozen=True, slots=True)
class AgentOutputsContract:
    schema: str = "AgentObservation"

    def __post_init__(self) -> None:
        if self.schema != "AgentObservation":
            raise ValueError("agent outputs must use AgentObservation schema")


@dataclass(frozen=True, slots=True)
class AgentAuthorityContract:
    analyze: bool = True
    generate_evidence: bool = True
    recommend: bool = True
    final_trade_decision: bool = False
    risk_override: bool = False
    policy_override: bool = False
    parameter_promotion: bool = False
    live_execution: bool = False

    def __post_init__(self) -> None:
        if not (self.analyze and self.generate_evidence and self.recommend):
            raise ValueError("agent advisory authorities must remain enabled")
        blocked = (
            self.final_trade_decision,
            self.risk_override,
            self.policy_override,
            self.parameter_promotion,
            self.live_execution,
        )
        if any(blocked):
            raise ValueError(
                "agent contract cannot grant final/risk/policy/live authority"
            )


@dataclass(frozen=True, slots=True)
class AgentValidationContract:
    required: bool = True

    def __post_init__(self) -> None:
        if not self.required:
            raise ValueError("agent validation is required")


@dataclass(frozen=True, slots=True)
class AgentFailureContract:
    default: str = "AGENT_UNAVAILABLE"

    def __post_init__(self) -> None:
        if self.default != "AGENT_UNAVAILABLE":
            raise ValueError("agent failure default must be AGENT_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class AgentContract:
    identity: AgentIdentityContract
    capabilities: AgentCapabilitiesContract
    intelligence_type: AgentIntelligenceType
    inputs: AgentInputsContract = field(default_factory=AgentInputsContract)
    outputs: AgentOutputsContract = field(default_factory=AgentOutputsContract)
    tool_permissions: tuple[str, ...] = field(default_factory=tuple)
    authority: AgentAuthorityContract = field(default_factory=AgentAuthorityContract)
    validation: AgentValidationContract = field(default_factory=AgentValidationContract)
    failure: AgentFailureContract = field(default_factory=AgentFailureContract)
    anatomy: tuple[AgentAnatomyPart, ...] = tuple(AgentAnatomyPart)

    def __post_init__(self) -> None:
        _require_unique("agent tool permissions", self.tool_permissions)
        if self.anatomy != tuple(AgentAnatomyPart):
            raise ValueError("agent contract anatomy must keep the canonical 10 parts")


@dataclass(frozen=True, slots=True)
class AgentEvidenceReference:
    evidence_id: str
    source_id: str
    claim: str
    status: AgentEvidenceStatus
    observed_at: datetime
    content_hash: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "source_id", "claim"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.content_hash is not None and len(self.content_hash) != 64:
            raise ValueError("content_hash must be a SHA-256 hex digest")


def build_handoff_evidence_ref(
    reference: AgentEvidenceReference,
    *,
    producer: str,
    snapshot_id: str,
    confidence: float,
    evidence_type: str = "AGENT_EVIDENCE",
    schema_version: str = "AgentEvidenceReference/v1",
) -> HandoffEvidenceRef:
    """Convert agent evidence into a handoff-safe provenance reference."""
    if reference.content_hash is None:
        raise ValueError("handoff evidence requires a content_hash")
    return HandoffEvidenceRef(
        evidence_id=reference.evidence_id,
        evidence_type=evidence_type,
        producer=producer,
        snapshot_id=snapshot_id,
        schema_version=schema_version,
        created_at=reference.observed_at,
        content_hash=reference.content_hash,
        confidence=confidence,
    )


@dataclass(frozen=True, slots=True)
class AgentEvidenceLayer:
    layer_id: str
    agent_id: str
    cycle_id: str
    snapshot_id: str
    evidence: tuple[AgentEvidenceReference, ...]
    conflicting_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    minimum_required: int = 1

    def __post_init__(self) -> None:
        for field_name in ("layer_id", "agent_id", "cycle_id", "snapshot_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.minimum_required < 1:
            raise ValueError("minimum_required must be positive")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        _require_unique("evidence IDs", evidence_ids)
        _require_unique("conflicting evidence IDs", self.conflicting_evidence_ids)
        unknown_conflicts = tuple(
            item
            for item in self.conflicting_evidence_ids
            if item not in set(evidence_ids)
        )
        if unknown_conflicts:
            raise ValueError("conflicting evidence must reference local evidence")

    @property
    def verified_count(self) -> int:
        return sum(
            item.status is AgentEvidenceStatus.VERIFIED for item in self.evidence
        )

    @property
    def evidence_complete(self) -> bool:
        return (
            self.verified_count >= self.minimum_required
            and not self.conflicting_evidence_ids
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.verified_count < self.minimum_required:
            blockers.append("AGENT_EVIDENCE_INCOMPLETE")
        if self.conflicting_evidence_ids:
            blockers.append("AGENT_EVIDENCE_CONFLICTED")
        if any(
            item.status is AgentEvidenceStatus.DATA_UNAVAILABLE
            for item in self.evidence
        ):
            blockers.append("AGENT_EVIDENCE_DATA_UNAVAILABLE")
        return tuple(dict.fromkeys(blockers))


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    check_id: str
    description: str
    result: VerificationResult
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.check_id.strip() or not self.description.strip():
            raise ValueError("verification check identity is required")
        _require_unique("verification evidence IDs", self.evidence_ids)
        _require_unique("verification reason codes", self.reason_codes)


@dataclass(frozen=True, slots=True)
class VerificationLayer:
    layer_id: str
    agent_id: str
    validation_profile_id: str
    checks: tuple[VerificationCheck, ...]
    minimum_pass_ratio: float = 1.0
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in ("layer_id", "agent_id", "validation_profile_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if not self.checks:
            raise ValueError("verification layer requires checks")
        check_ids = tuple(item.check_id for item in self.checks)
        _require_unique("verification check IDs", check_ids)
        if (
            not isfinite(self.minimum_pass_ratio)
            or not 0.0 <= self.minimum_pass_ratio <= 1.0
        ):
            raise ValueError("minimum_pass_ratio must be between zero and one")
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("verification layer cannot authorize trading")

    @property
    def pass_ratio(self) -> float:
        passed = sum(item.result is VerificationResult.PASS for item in self.checks)
        return passed / len(self.checks)

    @property
    def result(self) -> VerificationResult:
        if any(item.result is VerificationResult.FAIL for item in self.checks):
            return VerificationResult.FAIL
        if any(item.result is VerificationResult.UNKNOWN for item in self.checks):
            return VerificationResult.UNKNOWN
        if self.pass_ratio >= self.minimum_pass_ratio:
            return VerificationResult.PASS
        return VerificationResult.PARTIAL

    @property
    def blockers(self) -> tuple[str, ...]:
        result = self.result
        if result is VerificationResult.PASS:
            return ()
        if result is VerificationResult.FAIL:
            return ("AGENT_VERIFICATION_FAILED",)
        if result is VerificationResult.UNKNOWN:
            return ("AGENT_VERIFICATION_UNKNOWN",)
        return ("AGENT_VERIFICATION_PARTIAL",)


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain empty values")

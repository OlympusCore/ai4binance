"""Governed Memory Fabric contracts for cross-cycle advisory context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum


class MemoryType(StrEnum):
    WORKING_CONTEXT = "WORKING_CONTEXT"
    EPISODIC_MEMORY = "EPISODIC_MEMORY"
    SEMANTIC_MEMORY = "SEMANTIC_MEMORY"
    RESEARCH_MEMORY = "RESEARCH_MEMORY"
    GOVERNED_KNOWLEDGE_REF = "GOVERNED_KNOWLEDGE_REF"


class MemoryLifecycleStatus(StrEnum):
    CAPTURED = "CAPTURED"
    NORMALIZED = "NORMALIZED"
    PROVENANCE_VERIFIED = "PROVENANCE_VERIFIED"
    TEMPORALLY_VALIDATED = "TEMPORALLY_VALIDATED"
    DEDUPLICATED = "DEDUPLICATED"
    CONFLICT_CHECKED = "CONFLICT_CHECKED"
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    CONFLICTED = "CONFLICTED"


class MemoryProducerRole(StrEnum):
    SCOUT = "SCOUT"
    ANALYST = "ANALYST"
    STRATEGIST = "STRATEGIST"
    EXECUTOR = "EXECUTOR"
    GUARDIAN = "GUARDIAN"
    OBSERVER = "OBSERVER"
    ORCHESTRATOR = "ORCHESTRATOR"
    FEEDBACK_COMPILER = "FEEDBACK_COMPILER"


class MemoryTrustClass(StrEnum):
    VERIFIED_SYSTEM_EVIDENCE = "VERIFIED_SYSTEM_EVIDENCE"
    REVIEWED_RESEARCH = "REVIEWED_RESEARCH"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"
    LLM_NARRATIVE = "LLM_NARRATIVE"


class MemoryAuthorityCeiling(StrEnum):
    READ_ONLY_REFERENCE = "READ_ONLY_REFERENCE"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    ADVISORY = "ADVISORY"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class MemoryRetrievalPolicy(StrEnum):
    VALIDATED_ONLY = "VALIDATED_ONLY"
    ACTIVE_ONLY = "ACTIVE_ONLY"
    CANDIDATE_REVIEW = "CANDIDATE_REVIEW"


class MemoryConflictType(StrEnum):
    DUPLICATE = "DUPLICATE"
    CONTRADICTION = "CONTRADICTION"
    SUPERSESSION = "SUPERSESSION"


class MemoryConflictReviewStatus(StrEnum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class MemoryClassification(StrEnum):
    PUBLIC_RESEARCH = "PUBLIC_RESEARCH"
    INTERNAL = "INTERNAL"
    VERIFIED_MARKET_EVIDENCE = "VERIFIED_MARKET_EVIDENCE"
    SYSTEM_OPERATIONAL = "SYSTEM_OPERATIONAL"
    ACCOUNT_SENSITIVE = "ACCOUNT_SENSITIVE"
    RESTRICTED = "RESTRICTED"


class MemoryApplicabilityScope(StrEnum):
    GLOBAL = "GLOBAL"
    MARKET_TYPE = "MARKET_TYPE"
    ASSET = "ASSET"
    SYMBOL = "SYMBOL"
    STRATEGY = "STRATEGY"
    SETUP_TYPE = "SETUP_TYPE"
    REGIME = "REGIME"
    TIMEFRAME = "TIMEFRAME"
    SYMBOL_STRATEGY = "SYMBOL_STRATEGY"


class MemoryAdvisoryEffect(StrEnum):
    WARN = "WARN"
    COUNTER_EVIDENCE = "COUNTER_EVIDENCE"
    FAILURE_MODE_MATCH = "FAILURE_MODE_MATCH"
    REGIME_MISMATCH = "REGIME_MISMATCH"
    CONFIDENCE_DOWNGRADE = "CONFIDENCE_DOWNGRADE"
    WATCH_ONLY_HINT = "WATCH_ONLY_HINT"
    NO_TRADE_HINT = "NO_TRADE_HINT"


class CognitiveBrainRole(StrEnum):
    ONE_BRAIN_OPERATING_BRAIN = "ONE_BRAIN_OPERATING_BRAIN"
    GOVERNED_SECOND_BRAIN_MEMORY_BRAIN = "GOVERNED_SECOND_BRAIN_MEMORY_BRAIN"


class CognitiveArchitecturePrimitive(StrEnum):
    ONE_BRAIN = "ONE_BRAIN"
    GOVERNED_SECOND_BRAIN = "GOVERNED_SECOND_BRAIN"
    GUARDIAN_VETO = "GUARDIAN_VETO"
    CONTROLLED_FEEDBACK_LOOP = "CONTROLLED_FEEDBACK_LOOP"


@dataclass(frozen=True, slots=True)
class MemoryProducerRoleContract:
    """Display and authority contract for logical cognitive roles."""

    role: MemoryProducerRole
    display_name: str
    capability_mapping: str
    authority: str
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.role not in set(MemoryProducerRole):
            raise ValueError("memory producer role contract role is invalid")
        if not self.display_name.strip():
            raise ValueError("memory producer role display name is required")
        if not self.capability_mapping.strip():
            raise ValueError("memory producer role capability mapping is required")
        if not self.authority.strip():
            raise ValueError("memory producer role authority is required")
        if (
            self.execution_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory producer role contract cannot authorize trading")


MEMORY_PRODUCER_ROLE_CONTRACTS: tuple[MemoryProducerRoleContract, ...] = (
    MemoryProducerRoleContract(
        role=MemoryProducerRole.SCOUT,
        display_name="Scout",
        capability_mapping="Opportunity Radar, external intel, and scanners",
        authority="DISCOVERY_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.ANALYST,
        display_name="Analyst",
        capability_mapping="Specialist analysis and evidence production",
        authority="EVIDENCE_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.STRATEGIST,
        display_name="Strategist",
        capability_mapping="Strategy candidate synthesis and arbitration",
        authority="CANDIDATE_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.EXECUTOR,
        display_name="Action Executor",
        capability_mapping="Paper execution adapter",
        authority="PAPER_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.GUARDIAN,
        display_name="Guardian Veto Plane",
        capability_mapping="Governance, risk, validation, and assurance vetoes",
        authority="VETO_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.OBSERVER,
        display_name="Observer",
        capability_mapping="Telemetry, audit, closure review, and attribution",
        authority="OBSERVATION_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.ORCHESTRATOR,
        display_name="Orchestrator",
        capability_mapping="Routing, dependency coordination, and timeout handling",
        authority="COORDINATION_ONLY",
    ),
    MemoryProducerRoleContract(
        role=MemoryProducerRole.FEEDBACK_COMPILER,
        display_name="Feedback Compiler",
        capability_mapping="Outcome-to-memory-candidate compilation",
        authority="MEMORY_CANDIDATE_ONLY",
    ),
)


def memory_producer_role_contract(
    role: MemoryProducerRole,
) -> MemoryProducerRoleContract:
    for contract in MEMORY_PRODUCER_ROLE_CONTRACTS:
        if contract.role is role:
            return contract
    raise ValueError("memory producer role contract is not registered")


@dataclass(frozen=True, slots=True)
class CognitiveArchitecturePrimitiveContract:
    """Authority contract for governed cognitive-memory primitives."""

    primitive: CognitiveArchitecturePrimitive
    canonical_name: str
    responsibility: str
    authority_boundary: str
    may: tuple[str, ...]
    must_not: tuple[str, ...]
    execution_allowed: bool = False
    signal_authority: bool = False
    risk_change_allowed: bool = False
    parameter_change_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.primitive not in set(CognitiveArchitecturePrimitive):
            raise ValueError("cognitive primitive is invalid")
        for name, value in (
            ("cognitive primitive canonical name", self.canonical_name),
            ("cognitive primitive responsibility", self.responsibility),
            ("cognitive primitive authority boundary", self.authority_boundary),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if any(not item.strip() for item in self.may):
            raise ValueError("cognitive primitive permissions cannot contain blanks")
        if any(not item.strip() for item in self.must_not):
            raise ValueError("cognitive primitive prohibitions cannot contain blanks")
        if len(set(self.may)) != len(self.may):
            raise ValueError("cognitive primitive permissions must be unique")
        if len(set(self.must_not)) != len(self.must_not):
            raise ValueError("cognitive primitive prohibitions must be unique")
        if not self.may or not self.must_not:
            raise ValueError("cognitive primitive requires explicit boundaries")
        if (
            self.execution_allowed
            or self.signal_authority
            or self.risk_change_allowed
            or self.parameter_change_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("cognitive primitive cannot authorize trading")


GOVERNED_COGNITIVE_ARCHITECTURE_PRIMITIVES: tuple[
    CognitiveArchitecturePrimitiveContract, ...
] = (
    CognitiveArchitecturePrimitiveContract(
        primitive=CognitiveArchitecturePrimitive.ONE_BRAIN,
        canonical_name="One Canonical Decision System",
        responsibility=(
            "Current-cycle context, evidence synthesis, risk, validation, "
            "decision governance, and deterministic decision path."
        ),
        authority_boundary="DETERMINISTIC_DECISION_PATH_ONLY",
        may=(
            "coordinate_current_cycle",
            "bind_market_snapshot",
            "bind_memory_snapshot",
            "route_evidence_to_risk_validation_and_governance",
        ),
        must_not=(
            "become_single_giant_llm",
            "become_master_agent",
            "override_risk_validation_or_governance",
        ),
    ),
    CognitiveArchitecturePrimitiveContract(
        primitive=CognitiveArchitecturePrimitive.GOVERNED_SECOND_BRAIN,
        canonical_name="Governed Memory Fabric",
        responsibility=(
            "Past validated experience, lessons, failure modes, research "
            "evidence, historical context, and counter-evidence."
        ),
        authority_boundary="ADVISORY_CONTEXT_ONLY",
        may=(
            "inform",
            "warn",
            "provide_counter_evidence",
            "suggest_research",
        ),
        must_not=(
            "claim_truth_without_current_evidence",
            "authorize_trades",
            "override_risk_validation_or_governance",
            "change_strategy_parameters",
        ),
    ),
    CognitiveArchitecturePrimitiveContract(
        primitive=CognitiveArchitecturePrimitive.GUARDIAN_VETO,
        canonical_name="Guardian Veto Plane",
        responsibility=(
            "Cross-cutting memory, evidence, risk, validation, governance, "
            "and execution veto surface."
        ),
        authority_boundary="VETO_ONLY",
        may=("block_unsafe_context", "require_review", "surface_conflicts"),
        must_not=(
            "grant_execution_authority",
            "promote_memory",
            "resolve_conflict_by_opinion",
        ),
    ),
    CognitiveArchitecturePrimitiveContract(
        primitive=CognitiveArchitecturePrimitive.CONTROLLED_FEEDBACK_LOOP,
        canonical_name="Controlled Feedback Loop",
        responsibility=(
            "Outcome observation, evidence binding, provenance and temporal "
            "checks, conflict checks, and memory candidate staging."
        ),
        authority_boundary="MEMORY_CANDIDATE_ONLY",
        may=(
            "observe_outcomes",
            "compile_evidence",
            "stage_memory_candidates",
            "request_validation",
        ),
        must_not=(
            "write_outcome_directly_to_active_memory",
            "self_promote_lessons",
            "enable_live_execution",
        ),
    ),
)


def cognitive_architecture_primitive_contract(
    primitive: CognitiveArchitecturePrimitive,
) -> CognitiveArchitecturePrimitiveContract:
    for contract in GOVERNED_COGNITIVE_ARCHITECTURE_PRIMITIVES:
        if contract.primitive is primitive:
            return contract
    raise ValueError("cognitive primitive contract is not registered")


_ACTIVE_STATUSES = frozenset(
    {
        MemoryLifecycleStatus.VALIDATED,
        MemoryLifecycleStatus.ACTIVE,
    }
)
_INACTIVE_STATUSES = frozenset(
    {
        MemoryLifecycleStatus.STALE,
        MemoryLifecycleStatus.SUPERSEDED,
        MemoryLifecycleStatus.EXPIRED,
        MemoryLifecycleStatus.REVOKED,
        MemoryLifecycleStatus.QUARANTINED,
        MemoryLifecycleStatus.REJECTED,
        MemoryLifecycleStatus.CONFLICTED,
    }
)


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_aware_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


def _require_optional_text(name: str, value: str | None) -> None:
    if value is not None:
        _require_text(name, value)


def _normalized_utc(value: datetime) -> datetime:
    _require_aware_utc("memory timestamp", value)
    return value.astimezone(UTC)


def memory_canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def memory_snapshot_lineage_sha256(
    *,
    as_of_valid_time: datetime,
    as_of_system_time: datetime,
    policy_version: str,
    records: tuple[MemoryRecord, ...],
    conflicts: tuple[MemoryConflict, ...],
) -> str:
    """Hash deterministic replay lineage without granting memory authority."""
    return memory_canonical_sha256(
        {
            "as_of_system_time": _normalized_utc(as_of_system_time).isoformat(),
            "as_of_valid_time": _normalized_utc(as_of_valid_time).isoformat(),
            "conflict_ids": tuple(conflict.conflict_id for conflict in conflicts),
            "policy_version": policy_version,
            "records": tuple(
                {
                    "content_hash": record.content_hash,
                    "expired_at": (
                        record.expired_at.astimezone(UTC).isoformat()
                        if record.expired_at is not None
                        else None
                    ),
                    "memory_id": record.memory_id,
                    "recorded_at": record.effective_recorded_at.isoformat(),
                    "revoked_at": (
                        record.revoked_at.astimezone(UTC).isoformat()
                        if record.revoked_at is not None
                        else None
                    ),
                    "status": record.status.value,
                    "superseded_at": (
                        record.superseded_at.astimezone(UTC).isoformat()
                        if record.superseded_at is not None
                        else None
                    ),
                }
                for record in records
            ),
        }
    )


@dataclass(frozen=True, slots=True)
class MemoryWriteIntent:
    intent_id: str
    memory_type: MemoryType
    subject_key: str
    body: str
    event_time: datetime
    observed_at: datetime
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source_hashes: tuple[str, ...]
    producer_role: MemoryProducerRole
    trust_class: MemoryTrustClass
    authority_ceiling: MemoryAuthorityCeiling
    cycle_id: str | None = None
    snapshot_id: str | None = None
    decision_id: str | None = None
    applicability_scope: MemoryApplicabilityScope = MemoryApplicabilityScope.GLOBAL
    classification: MemoryClassification = MemoryClassification.PUBLIC_RESEARCH
    market_type: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    setup_type: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    regime_tags: tuple[str, ...] = ()
    timeframe_tags: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    retention_policy: str = "EVIDENCE_RETAINED"
    retrieval_policy: MemoryRetrievalPolicy = MemoryRetrievalPolicy.VALIDATED_ONLY
    advisory_effect: MemoryAdvisoryEffect = MemoryAdvisoryEffect.WARN
    failure_mode_code: str | None = None
    reason_codes: tuple[str, ...] = ()
    confidence: float = 0.0
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def content_hash(self) -> str:
        return memory_canonical_sha256(
            {
                "body": self.body,
                "advisory_effect": self.advisory_effect.value,
                "failure_mode_code": self.failure_mode_code,
                "memory_type": self.memory_type.value,
                "reason_codes": self.reason_codes,
                "subject_key": self.subject_key,
            }
        )

    def __post_init__(self) -> None:
        _require_text("memory intent id", self.intent_id)
        _require_text("memory subject key", self.subject_key)
        _require_text("memory body", self.body)
        if self.memory_type not in set(MemoryType):
            raise ValueError("memory type is invalid")
        if self.producer_role not in set(MemoryProducerRole):
            raise ValueError("memory producer role is invalid")
        if self.trust_class not in set(MemoryTrustClass):
            raise ValueError("memory trust class is invalid")
        if self.authority_ceiling not in set(MemoryAuthorityCeiling):
            raise ValueError("memory authority ceiling is invalid")
        if self.retrieval_policy not in set(MemoryRetrievalPolicy):
            raise ValueError("memory retrieval policy is invalid")
        if self.advisory_effect not in set(MemoryAdvisoryEffect):
            raise ValueError("memory advisory effect is invalid")
        if self.applicability_scope not in set(MemoryApplicabilityScope):
            raise ValueError("memory applicability scope is invalid")
        if self.classification not in set(MemoryClassification):
            raise ValueError("memory classification is invalid")
        _require_optional_text("memory market type", self.market_type)
        _require_optional_text("memory symbol", self.symbol)
        _require_optional_text("memory strategy id", self.strategy_id)
        _require_optional_text("memory setup type", self.setup_type)
        _require_optional_text("memory failure mode code", self.failure_mode_code)
        _require_aware_utc("memory event time", self.event_time)
        _require_aware_utc("memory observed time", self.observed_at)
        if self.observed_at < self.event_time:
            raise ValueError("memory observed time cannot precede event time")
        if self.valid_from is not None:
            _require_aware_utc("memory valid from", self.valid_from)
        if self.valid_until is not None:
            _require_aware_utc("memory valid until", self.valid_until)
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("memory valid until must be after valid from")
        _require_unique_text("memory source refs", self.source_refs)
        _require_unique_text("memory evidence refs", self.evidence_refs)
        _require_unique_text("memory source hashes", self.source_hashes)
        for source_hash in self.source_hashes:
            _require_sha256("memory source hash", source_hash)
        _require_unique_text("memory regime tags", self.regime_tags)
        _require_unique_text("memory timeframe tags", self.timeframe_tags)
        _require_unique_text("memory supersession refs", self.supersedes)
        _require_unique_text("memory contradiction refs", self.contradicts)
        _require_unique_text("memory reason codes", self.reason_codes)
        if (
            self.advisory_effect is MemoryAdvisoryEffect.FAILURE_MODE_MATCH
            and self.failure_mode_code is None
        ):
            raise ValueError("failure-mode advisory memory requires failure mode code")
        _require_text("memory retention policy", self.retention_policy)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("memory confidence must be between 0 and 1")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory write intent cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    memory_type: MemoryType
    subject_key: str
    body: str
    event_time: datetime
    observed_at: datetime
    valid_from: datetime
    valid_until: datetime | None
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source_hashes: tuple[str, ...]
    content_hash: str
    producer_role: MemoryProducerRole
    trust_class: MemoryTrustClass
    authority_ceiling: MemoryAuthorityCeiling
    status: MemoryLifecycleStatus
    recorded_at: datetime | None = None
    superseded_at: datetime | None = None
    revoked_at: datetime | None = None
    expired_at: datetime | None = None
    regime_tags: tuple[str, ...] = ()
    timeframe_tags: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    retention_policy: str = "EVIDENCE_RETAINED"
    retrieval_policy: MemoryRetrievalPolicy = MemoryRetrievalPolicy.VALIDATED_ONLY
    advisory_effect: MemoryAdvisoryEffect = MemoryAdvisoryEffect.WARN
    failure_mode_code: str | None = None
    reason_codes: tuple[str, ...] = ()
    confidence: float = 0.0
    cycle_id: str | None = None
    snapshot_id: str | None = None
    decision_id: str | None = None
    applicability_scope: MemoryApplicabilityScope = MemoryApplicabilityScope.GLOBAL
    classification: MemoryClassification = MemoryClassification.PUBLIC_RESEARCH
    market_type: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    setup_type: str | None = None
    approval_record_id: str | None = None
    verification_record_id: str | None = None
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def is_context_eligible(self) -> bool:
        return self.status in _ACTIVE_STATUSES

    @property
    def effective_recorded_at(self) -> datetime:
        """Return a backward-compatible system-time admission timestamp."""
        return _normalized_utc(self.recorded_at or self.observed_at)

    def is_context_eligible_at(self, as_of_system_time: datetime) -> bool:
        """Resolve lifecycle eligibility at a historical system-time boundary."""
        normalized_system_time = _normalized_utc(as_of_system_time)
        if self.status in _ACTIVE_STATUSES:
            return True
        transition_at = {
            MemoryLifecycleStatus.SUPERSEDED: self.superseded_at,
            MemoryLifecycleStatus.REVOKED: self.revoked_at,
            MemoryLifecycleStatus.EXPIRED: self.expired_at,
        }.get(self.status)
        return (
            transition_at is not None
            and normalized_system_time < _normalized_utc(transition_at)
            and bool(self.approval_record_id)
            and bool(self.verification_record_id)
            and bool(self.source_refs)
            and bool(self.evidence_refs)
            and bool(self.source_hashes)
            and self.trust_class is not MemoryTrustClass.LLM_NARRATIVE
        )

    def is_temporally_valid(
        self,
        as_of_valid_time: datetime,
        as_of_system_time: datetime | None = None,
    ) -> bool:
        normalized_valid_time = _normalized_utc(as_of_valid_time)
        normalized_system_time = _normalized_utc(as_of_system_time or as_of_valid_time)
        if (
            self.observed_at > normalized_system_time
            or self.effective_recorded_at > normalized_system_time
        ):
            return False
        if self.valid_from > normalized_valid_time:
            return False
        return self.valid_until is None or normalized_valid_time < self.valid_until

    def __post_init__(self) -> None:
        _require_text("memory id", self.memory_id)
        _require_text("memory subject key", self.subject_key)
        _require_text("memory body", self.body)
        _require_sha256("memory content hash", self.content_hash)
        if self.memory_type not in set(MemoryType):
            raise ValueError("memory type is invalid")
        if self.producer_role not in set(MemoryProducerRole):
            raise ValueError("memory producer role is invalid")
        if self.trust_class not in set(MemoryTrustClass):
            raise ValueError("memory trust class is invalid")
        if self.authority_ceiling not in set(MemoryAuthorityCeiling):
            raise ValueError("memory authority ceiling is invalid")
        if self.status not in set(MemoryLifecycleStatus):
            raise ValueError("memory lifecycle status is invalid")
        if self.retrieval_policy not in set(MemoryRetrievalPolicy):
            raise ValueError("memory retrieval policy is invalid")
        if self.advisory_effect not in set(MemoryAdvisoryEffect):
            raise ValueError("memory advisory effect is invalid")
        if self.applicability_scope not in set(MemoryApplicabilityScope):
            raise ValueError("memory applicability scope is invalid")
        if self.classification not in set(MemoryClassification):
            raise ValueError("memory classification is invalid")
        _require_optional_text("memory market type", self.market_type)
        _require_optional_text("memory symbol", self.symbol)
        _require_optional_text("memory strategy id", self.strategy_id)
        _require_optional_text("memory setup type", self.setup_type)
        _require_optional_text("memory failure mode code", self.failure_mode_code)
        _require_aware_utc("memory event time", self.event_time)
        _require_aware_utc("memory observed time", self.observed_at)
        if self.recorded_at is not None:
            _require_aware_utc("memory recorded time", self.recorded_at)
        _require_aware_utc("memory valid from", self.valid_from)
        if self.valid_until is not None:
            _require_aware_utc("memory valid until", self.valid_until)
            if self.valid_until <= self.valid_from:
                raise ValueError("memory valid until must be after valid from")
        for name, value in (
            ("memory superseded time", self.superseded_at),
            ("memory revoked time", self.revoked_at),
            ("memory expired time", self.expired_at),
        ):
            if value is not None:
                _require_aware_utc(name, value)
                if value < self.effective_recorded_at:
                    raise ValueError(f"{name} cannot precede memory recorded time")
        _require_unique_text("memory source refs", self.source_refs)
        _require_unique_text("memory evidence refs", self.evidence_refs)
        _require_unique_text("memory source hashes", self.source_hashes)
        for source_hash in self.source_hashes:
            _require_sha256("memory source hash", source_hash)
        _require_unique_text("memory blockers", self.blockers)
        _require_unique_text("memory reason codes", self.reason_codes)
        if (
            self.advisory_effect is MemoryAdvisoryEffect.FAILURE_MODE_MATCH
            and self.failure_mode_code is None
        ):
            raise ValueError("failure-mode advisory memory requires failure mode code")
        if self.status in _ACTIVE_STATUSES:
            if not self.approval_record_id or not self.verification_record_id:
                raise ValueError("active memory requires approval and verification")
            if not self.source_refs or not self.evidence_refs or not self.source_hashes:
                raise ValueError("active memory requires provenance and evidence")
            if self.trust_class is MemoryTrustClass.LLM_NARRATIVE:
                raise ValueError("LLM narrative cannot become active memory")
        if self.status in _INACTIVE_STATUSES and not self.blockers:
            raise ValueError("inactive memory requires blockers")
        if (
            self.execution_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory record cannot authorize trading")


MEMORY_CONTEXT_CONSUMER = "OPERATING_BRAIN"
MEMORY_CONTEXT_PURPOSE = "ADVISORY_CONTEXT"


@dataclass(frozen=True, slots=True)
class MemoryAccessPolicy:
    """Deterministic read boundary for a bounded memory consumer and purpose."""

    policy_id: str
    policy_version: str
    allowed_consumers: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    allowed_classifications: tuple[MemoryClassification, ...]
    allowed_market_types: tuple[str, ...] | None = None
    allowed_symbols: tuple[str, ...] | None = None
    allowed_strategy_ids: tuple[str, ...] | None = None
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("memory access policy id", self.policy_id)
        _require_text("memory access policy version", self.policy_version)
        for name, required_values in (
            ("memory access policy consumers", self.allowed_consumers),
            ("memory access policy purposes", self.allowed_purposes),
        ):
            _require_unique_text(name, required_values)
            if not required_values:
                raise ValueError(f"{name} cannot be empty")
        if not self.allowed_classifications:
            raise ValueError("memory access policy classifications cannot be empty")
        if len(set(self.allowed_classifications)) != len(self.allowed_classifications):
            raise ValueError("memory access policy classifications must be unique")
        if any(
            classification not in set(MemoryClassification)
            for classification in self.allowed_classifications
        ):
            raise ValueError("memory access policy classification is invalid")
        for name, namespace_values in (
            ("memory access policy market types", self.allowed_market_types),
            ("memory access policy symbols", self.allowed_symbols),
            ("memory access policy strategy ids", self.allowed_strategy_ids),
        ):
            if namespace_values is not None:
                _require_unique_text(name, namespace_values)
                if not namespace_values:
                    raise ValueError(f"{name} cannot be empty")
        if MEMORY_CONTEXT_PURPOSE in self.allowed_purposes and any(
            classification
            in {
                MemoryClassification.ACCOUNT_SENSITIVE,
                MemoryClassification.RESTRICTED,
            }
            for classification in self.allowed_classifications
        ):
            raise ValueError(
                "advisory context access policy cannot allow sensitive memory"
            )
        if (
            self.execution_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory access policy cannot authorize trading")


DEFAULT_ADVISORY_MEMORY_ACCESS_POLICY = MemoryAccessPolicy(
    policy_id="memory-access:operating-brain-advisory-context",
    policy_version="memory-access:v1",
    allowed_consumers=(MEMORY_CONTEXT_CONSUMER,),
    allowed_purposes=(MEMORY_CONTEXT_PURPOSE,),
    allowed_classifications=(
        MemoryClassification.PUBLIC_RESEARCH,
        MemoryClassification.INTERNAL,
        MemoryClassification.VERIFIED_MARKET_EVIDENCE,
        MemoryClassification.SYSTEM_OPERATIONAL,
    ),
)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    record: MemoryRecord
    intake_status: MemoryLifecycleStatus
    blockers: tuple[str, ...]
    promotion_status: str = "CANDIDATE_MEMORY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def binding_sha256(self) -> str:
        """Bind all candidate metadata as well as the semantic content hash."""
        encoded = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def __post_init__(self) -> None:
        if self.intake_status not in set(MemoryLifecycleStatus):
            raise ValueError("memory candidate intake status is invalid")
        _require_unique_text("memory candidate blockers", self.blockers)
        if self.record.status is not MemoryLifecycleStatus.CANDIDATE:
            raise ValueError("memory candidate record must remain candidate")
        if self.promotion_status != "CANDIDATE_MEMORY":
            raise ValueError("memory candidate cannot promote itself")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory candidate cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryConflict:
    conflict_id: str
    conflict_type: MemoryConflictType
    subject_key: str
    memory_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("memory conflict id", self.conflict_id)
        _require_text("memory conflict subject key", self.subject_key)
        if self.conflict_type not in set(MemoryConflictType):
            raise ValueError("memory conflict type is invalid")
        _require_unique_text("memory conflict ids", self.memory_ids)
        _require_unique_text("memory conflict reason codes", self.reason_codes)
        if len(self.memory_ids) < 2:
            raise ValueError("memory conflict requires at least two records")


@dataclass(frozen=True, slots=True)
class MemoryConflictRecord:
    conflict: MemoryConflict
    detected_at: datetime
    review_status: MemoryConflictReviewStatus = MemoryConflictReviewStatus.OPEN
    reviewer_ref: str | None = None
    resolution_ref: str | None = None
    blockers: tuple[str, ...] = ("MEMORY_CONFLICT_REVIEW_REQUIRED",)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_aware_utc("memory conflict detection time", self.detected_at)
        if self.review_status not in set(MemoryConflictReviewStatus):
            raise ValueError("memory conflict review status is invalid")
        if self.reviewer_ref is not None:
            _require_text("memory conflict reviewer ref", self.reviewer_ref)
        if self.resolution_ref is not None:
            _require_text("memory conflict resolution ref", self.resolution_ref)
        _require_unique_text("memory conflict blockers", self.blockers)
        if (
            self.review_status is not MemoryConflictReviewStatus.RESOLVED
            and "MEMORY_CONFLICT_REVIEW_REQUIRED" not in self.blockers
        ):
            raise ValueError("unresolved memory conflict requires review blocker")
        if (
            self.review_status is MemoryConflictReviewStatus.RESOLVED
            and self.resolution_ref is None
        ):
            raise ValueError("resolved memory conflict requires resolution ref")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory conflict record cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    memory_snapshot_id: str
    created_at: datetime
    as_of: datetime
    records: tuple[MemoryRecord, ...]
    conflicts: tuple[MemoryConflict, ...] = ()
    policy_version: str = "governed-memory-fabric:v1"
    as_of_system_time: datetime | None = None
    lineage_hash: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def record_ids(self) -> tuple[str, ...]:
        return tuple(record.memory_id for record in self.records)

    @property
    def effective_as_of_system_time(self) -> datetime:
        return _normalized_utc(self.as_of_system_time or self.as_of)

    def __post_init__(self) -> None:
        _require_text("memory snapshot id", self.memory_snapshot_id)
        _require_text("memory snapshot policy version", self.policy_version)
        _require_aware_utc("memory snapshot creation time", self.created_at)
        _require_aware_utc("memory snapshot as-of time", self.as_of)
        if self.as_of_system_time is not None:
            _require_aware_utc(
                "memory snapshot system as-of time", self.as_of_system_time
            )
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("memory snapshot records must be unique")
        if any(
            not record.is_context_eligible_at(self.effective_as_of_system_time)
            for record in self.records
        ):
            raise ValueError("memory snapshot can include only validated memory")
        if any(
            not record.is_temporally_valid(self.as_of, self.effective_as_of_system_time)
            for record in self.records
        ):
            raise ValueError("memory snapshot cannot include stale memory")
        expected_lineage_hash = memory_snapshot_lineage_sha256(
            as_of_valid_time=self.as_of,
            as_of_system_time=self.effective_as_of_system_time,
            policy_version=self.policy_version,
            records=self.records,
            conflicts=self.conflicts,
        )
        if self.lineage_hash is not None and self.lineage_hash != expected_lineage_hash:
            raise ValueError("memory snapshot lineage hash is invalid")
        object.__setattr__(self, "lineage_hash", expected_lineage_hash)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory snapshot cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryRetrievalRequest:
    subject_keys: tuple[str, ...]
    as_of: datetime
    as_of_system_time: datetime | None = None
    cycle_id: str | None = None
    consumer: str = MEMORY_CONTEXT_CONSUMER
    purpose: str = MEMORY_CONTEXT_PURPOSE
    access_policy: MemoryAccessPolicy = DEFAULT_ADVISORY_MEMORY_ACCESS_POLICY
    policy: MemoryRetrievalPolicy = MemoryRetrievalPolicy.VALIDATED_ONLY
    memory_types: tuple[MemoryType, ...] = ()
    regime_tags: tuple[str, ...] = ()
    timeframe_tags: tuple[str, ...] = ()
    market_type: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    setup_type: str | None = None
    max_records: int = 20

    @property
    def as_of_valid_time(self) -> datetime:
        """Return the legacy-compatible valid-time retrieval boundary."""
        return _normalized_utc(self.as_of)

    @property
    def effective_as_of_system_time(self) -> datetime:
        return _normalized_utc(self.as_of_system_time or self.as_of)

    def __post_init__(self) -> None:
        _require_unique_text("memory retrieval subjects", self.subject_keys)
        _require_aware_utc("memory retrieval as-of time", self.as_of)
        if self.as_of_system_time is not None:
            _require_aware_utc(
                "memory retrieval system as-of time", self.as_of_system_time
            )
        if self.cycle_id is not None:
            _require_text("memory retrieval cycle id", self.cycle_id)
        _require_text("memory retrieval consumer", self.consumer)
        _require_text("memory retrieval purpose", self.purpose)
        if not isinstance(self.access_policy, MemoryAccessPolicy):
            raise ValueError("memory retrieval access policy is invalid")
        if self.policy not in set(MemoryRetrievalPolicy):
            raise ValueError("memory retrieval policy is invalid")
        if any(memory_type not in set(MemoryType) for memory_type in self.memory_types):
            raise ValueError("memory retrieval type filter is invalid")
        _require_unique_text("memory retrieval regime tags", self.regime_tags)
        _require_unique_text("memory retrieval timeframe tags", self.timeframe_tags)
        _require_optional_text("memory retrieval market type", self.market_type)
        _require_optional_text("memory retrieval symbol", self.symbol)
        _require_optional_text("memory retrieval strategy id", self.strategy_id)
        _require_optional_text("memory retrieval setup type", self.setup_type)
        if self.max_records < 1:
            raise ValueError("memory retrieval max records must be positive")


@dataclass(frozen=True, slots=True)
class MemoryPromotionApprovalRecord:
    approval_record_id: str
    candidate_memory_id: str
    candidate_content_hash: str
    approver_ref: str
    approved_at: datetime
    policy_version: str
    status: str = "APPROVED"
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text("memory approval record id", self.approval_record_id)
        _require_text("memory approval candidate id", self.candidate_memory_id)
        _require_sha256("memory approval candidate hash", self.candidate_content_hash)
        _require_text("memory approval approver ref", self.approver_ref)
        _require_text("memory approval policy version", self.policy_version)
        _require_aware_utc("memory approval time", self.approved_at)
        if self.expires_at is not None:
            _require_aware_utc("memory approval expiry", self.expires_at)
        if self.revoked_at is not None:
            _require_aware_utc("memory approval revocation", self.revoked_at)
        if self.status not in {"APPROVED", "REJECTED", "REVOKED"}:
            raise ValueError("memory approval status is invalid")


@dataclass(frozen=True, slots=True)
class MemoryPromotionVerificationRecord:
    verification_record_id: str
    approval_record_id: str
    candidate_memory_id: str
    candidate_content_hash: str
    verifier_ref: str
    verified_at: datetime
    policy_version: str
    status: str = "VERIFIED"

    def __post_init__(self) -> None:
        _require_text("memory verification record id", self.verification_record_id)
        _require_text("memory verification approval id", self.approval_record_id)
        _require_text("memory verification candidate id", self.candidate_memory_id)
        _require_sha256(
            "memory verification candidate hash",
            self.candidate_content_hash,
        )
        _require_text("memory verification verifier ref", self.verifier_ref)
        _require_text("memory verification policy version", self.policy_version)
        _require_aware_utc("memory verification time", self.verified_at)
        if self.status not in {"VERIFIED", "REJECTED", "EXPIRED"}:
            raise ValueError("memory verification status is invalid")


@dataclass(frozen=True, slots=True)
class MemoryPromotionVerificationResult:
    approval_record_id: str
    verification_record_id: str
    verified: bool
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    candidate_memory_id: str | None = None
    candidate_content_hash: str | None = None
    policy_version: str | None = None
    checked_at: datetime | None = None
    expires_at: datetime | None = None
    candidate_binding_hash: str | None = None

    def __post_init__(self) -> None:
        _require_text("memory promotion approval id", self.approval_record_id)
        _require_text("memory promotion verification id", self.verification_record_id)
        _require_unique_text("memory promotion blockers", self.blockers)
        if self.candidate_memory_id is not None:
            _require_text("memory promotion candidate id", self.candidate_memory_id)
        if self.candidate_binding_hash is not None:
            _require_sha256(
                "memory promotion binding hash", self.candidate_binding_hash
            )
        if self.candidate_content_hash is not None:
            _require_sha256(
                "memory promotion candidate hash", self.candidate_content_hash
            )
        if self.policy_version is not None:
            _require_text("memory promotion policy version", self.policy_version)
        for timestamp in (self.checked_at, self.expires_at):
            if timestamp is not None:
                _require_aware_utc("memory promotion time", timestamp)
        if self.verified and self.blockers:
            raise ValueError("verified memory promotion cannot include blockers")
        if not self.verified and not self.blockers:
            raise ValueError("failed memory promotion requires blockers")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory promotion verification cannot authorize trading")


@dataclass(frozen=True, slots=True)
class HistoricalAdvisoryEvidence:
    memory_id: str
    subject_key: str
    applicability_scope: MemoryApplicabilityScope
    classification: MemoryClassification
    evidence_refs: tuple[str, ...]
    advisory_effect: MemoryAdvisoryEffect
    confidence: float
    failure_mode_code: str | None = None
    reason_codes: tuple[str, ...] = ()
    market_type: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    setup_type: str | None = None
    regime_tags: tuple[str, ...] = ()
    timeframe_tags: tuple[str, ...] = ()
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("historical advisory memory id", self.memory_id)
        _require_text("historical advisory subject key", self.subject_key)
        if self.applicability_scope not in set(MemoryApplicabilityScope):
            raise ValueError("historical advisory applicability scope is invalid")
        if self.classification not in set(MemoryClassification):
            raise ValueError("historical advisory classification is invalid")
        if self.advisory_effect not in set(MemoryAdvisoryEffect):
            raise ValueError("historical advisory effect is invalid")
        _require_optional_text(
            "historical advisory failure mode code", self.failure_mode_code
        )
        _require_unique_text("historical advisory evidence refs", self.evidence_refs)
        _require_unique_text("historical advisory regime tags", self.regime_tags)
        _require_unique_text("historical advisory timeframe tags", self.timeframe_tags)
        _require_unique_text("historical advisory reason codes", self.reason_codes)
        if (
            self.advisory_effect is MemoryAdvisoryEffect.FAILURE_MODE_MATCH
            and self.failure_mode_code is None
        ):
            raise ValueError(
                "failure-mode advisory evidence requires failure mode code"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("historical advisory confidence must be between 0 and 1")
        if (
            self.execution_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical advisory evidence cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryRetrievalResult:
    request: MemoryRetrievalRequest
    records: tuple[MemoryRecord, ...]
    dropped_record_ids: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_unique_text(
            "memory retrieval dropped record ids",
            self.dropped_record_ids,
        )
        _require_unique_text("memory retrieval blockers", self.blockers)
        if len({record.memory_id for record in self.records}) != len(self.records):
            raise ValueError("memory retrieval records must be unique")
        if any(
            not record.is_temporally_valid(
                self.request.as_of_valid_time,
                self.request.effective_as_of_system_time,
            )
            for record in self.records
        ):
            raise ValueError("memory retrieval cannot return stale memory")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory retrieval cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryGuardianVetoSurface:
    """Explicit governance control-plane surface for memory-aware vetoes."""

    surface_id: str
    cycle_id: str
    memory_snapshot_id: str
    blockers: tuple[str, ...]
    conflict_ids: tuple[str, ...] = ()
    dropped_memory_ids: tuple[str, ...] = ()
    review_required: bool = False
    status: str = "READY"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("memory guardian surface id", self.surface_id)
        _require_text("memory guardian cycle id", self.cycle_id)
        _require_text("memory guardian snapshot id", self.memory_snapshot_id)
        _require_unique_text("memory guardian blockers", self.blockers)
        _require_unique_text("memory guardian conflict ids", self.conflict_ids)
        _require_unique_text(
            "memory guardian dropped memory ids",
            self.dropped_memory_ids,
        )
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("memory guardian surface status is invalid")
        if self.review_required and "MEMORY_GUARDIAN_VETO" not in self.blockers:
            raise ValueError("memory guardian review requires veto blocker")
        if bool(self.blockers) != (self.status == "RUNNING_WITH_BLOCKERS"):
            raise ValueError("memory guardian status must reflect blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory guardian surface cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryContext:
    context_id: str
    memory_snapshot_id: str
    rendered_context: str
    source_memory_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    access_policy_id: str = DEFAULT_ADVISORY_MEMORY_ACCESS_POLICY.policy_id
    access_policy_version: str = DEFAULT_ADVISORY_MEMORY_ACCESS_POLICY.policy_version
    consumer: str = MEMORY_CONTEXT_CONSUMER
    purpose: str = MEMORY_CONTEXT_PURPOSE
    blockers: tuple[str, ...] = ()
    authority_ceiling: MemoryAuthorityCeiling = MemoryAuthorityCeiling.ADVISORY
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("memory context id", self.context_id)
        _require_text("memory context snapshot id", self.memory_snapshot_id)
        _require_text("memory context access policy id", self.access_policy_id)
        _require_text(
            "memory context access policy version", self.access_policy_version
        )
        _require_text("memory context consumer", self.consumer)
        _require_text("memory context purpose", self.purpose)
        _require_unique_text("memory context source ids", self.source_memory_ids)
        _require_unique_text("memory context evidence refs", self.evidence_refs)
        _require_unique_text("memory context blockers", self.blockers)
        if self.authority_ceiling not in set(MemoryAuthorityCeiling):
            raise ValueError("memory context authority ceiling is invalid")
        if (
            self.execution_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory context cannot authorize trading")


@dataclass(frozen=True, slots=True)
class CompiledCycleContext:
    """One-cycle envelope binding market truth to read-only memory context."""

    context_id: str
    cycle_id: str
    operating_brain: CognitiveBrainRole
    memory_brain: CognitiveBrainRole
    market_snapshot_id: str
    memory_snapshot_id: str
    policy_bundle_hash: str
    registry_revision: str
    symbol: str
    market_type: str
    timeframes: tuple[str, ...]
    memory_context: MemoryContext
    memory_record_ids: tuple[str, ...]
    memory_evidence_refs: tuple[str, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    truncation_status: str
    validated_context_flow: str
    created_at: datetime
    memory_advisory_evidence: tuple[HistoricalAdvisoryEvidence, ...] = ()
    authority_ceiling: MemoryAuthorityCeiling = MemoryAuthorityCeiling.ADVISORY
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("compiled cycle context id", self.context_id)
        _require_text("compiled cycle id", self.cycle_id)
        if self.operating_brain is not CognitiveBrainRole.ONE_BRAIN_OPERATING_BRAIN:
            raise ValueError("compiled operating brain must be One Brain")
        if (
            self.memory_brain
            is not CognitiveBrainRole.GOVERNED_SECOND_BRAIN_MEMORY_BRAIN
        ):
            raise ValueError("compiled memory brain must be governed Second Brain")
        _require_text("compiled market snapshot id", self.market_snapshot_id)
        _require_text("compiled memory snapshot id", self.memory_snapshot_id)
        _require_sha256("compiled policy bundle hash", self.policy_bundle_hash)
        _require_text("compiled registry revision", self.registry_revision)
        _require_text("compiled symbol", self.symbol)
        _require_text("compiled market type", self.market_type)
        _require_unique_text("compiled timeframes", self.timeframes)
        _require_unique_text("compiled memory record ids", self.memory_record_ids)
        _require_unique_text(
            "compiled memory evidence refs",
            self.memory_evidence_refs,
        )
        _require_unique_text("compiled warnings", self.warnings)
        _require_unique_text("compiled blockers", self.blockers)
        _require_text("compiled truncation status", self.truncation_status)
        if self.validated_context_flow != "SECOND_BRAIN_TO_ONE_BRAIN":
            raise ValueError("compiled cycle context flow is invalid")
        _require_aware_utc("compiled context creation time", self.created_at)
        if any(
            evidence.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or evidence.execution_allowed
            or evidence.signal_authority
            for evidence in self.memory_advisory_evidence
        ):
            raise ValueError(
                "compiled memory advisory evidence cannot authorize trading"
            )
        if self.memory_context.memory_snapshot_id != self.memory_snapshot_id:
            raise ValueError("compiled memory context snapshot must match")
        if self.memory_context.source_memory_ids != self.memory_record_ids:
            raise ValueError("compiled memory ids must match memory context")
        if self.memory_context.evidence_refs != self.memory_evidence_refs:
            raise ValueError("compiled evidence refs must match memory context")
        if self.authority_ceiling is not MemoryAuthorityCeiling.ADVISORY:
            raise ValueError("compiled cycle context must remain advisory")
        if (
            self.execution_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("compiled cycle context cannot authorize trading")

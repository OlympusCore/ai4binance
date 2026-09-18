"""Canonical blocker taxonomy, definition, and occurrence contracts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import yaml


class BlockerDomain(StrEnum):
    GOVERNANCE = "GOVERNANCE"
    SECURITY = "SECURITY"
    DATA = "DATA"
    EVIDENCE = "EVIDENCE"
    RISK = "RISK"
    VALIDATION = "VALIDATION"
    STRATEGY = "STRATEGY"
    MODEL = "MODEL"
    AGENT = "AGENT"
    EXECUTION = "EXECUTION"
    PORTFOLIO = "PORTFOLIO"
    MARKET = "MARKET"
    LIQUIDITY = "LIQUIDITY"
    OPERATIONS = "OPERATIONS"
    ARCHITECTURE = "ARCHITECTURE"
    CONTRACT = "CONTRACT"
    SCHEMA = "SCHEMA"
    REPOSITORY = "REPOSITORY"
    DEPENDENCY = "DEPENDENCY"
    TEST = "TEST"
    CONFIGURATION = "CONFIGURATION"
    COMPLIANCE = "COMPLIANCE"
    RESEARCH = "RESEARCH"
    PROMOTION = "PROMOTION"


class BlockerClass(StrEnum):
    HARD_BLOCKER = "HARD_BLOCKER"
    CONDITIONAL_BLOCKER = "CONDITIONAL_BLOCKER"
    ADVISORY_FINDING = "ADVISORY_FINDING"


class BlockerSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BlockerScope(StrEnum):
    OBJECT = "OBJECT"
    COMPONENT = "COMPONENT"
    PIPELINE_STAGE = "PIPELINE_STAGE"
    DECISION_CYCLE = "DECISION_CYCLE"
    SYMBOL = "SYMBOL"
    MARKET = "MARKET"
    STRATEGY = "STRATEGY"
    MODEL = "MODEL"
    AGENT = "AGENT"
    EXPERIMENT = "EXPERIMENT"
    REPOSITORY = "REPOSITORY"
    DEPLOYMENT = "DEPLOYMENT"
    EXECUTION_MODE = "EXECUTION_MODE"
    GLOBAL = "GLOBAL"


class BlockerAuthority(StrEnum):
    CORE_CONSTITUTION = "CORE_CONSTITUTION"
    GOVERNANCE_ENGINE = "GOVERNANCE_ENGINE"
    RISK_ENGINE = "RISK_ENGINE"
    VALIDATION_ENGINE = "VALIDATION_ENGINE"
    SECURITY_CONTROL = "SECURITY_CONTROL"
    COMPLIANCE_CONTROL = "COMPLIANCE_CONTROL"
    DATA_QUALITY_ENGINE = "DATA_QUALITY_ENGINE"
    REPOSITORY_VALIDATOR = "REPOSITORY_VALIDATOR"
    EXECUTION_GATE = "EXECUTION_GATE"
    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"


class BlockerEffect(StrEnum):
    QUALITY_GATE_BLOCKED = "QUALITY_GATE_BLOCKED"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    CANDIDATE_BLOCKED = "CANDIDATE_BLOCKED"
    DECISION_CYCLE_BLOCKED = "DECISION_CYCLE_BLOCKED"
    STRATEGY_BLOCKED = "STRATEGY_BLOCKED"
    SYMBOL_BLOCKED = "SYMBOL_BLOCKED"
    MARKET_BLOCKED = "MARKET_BLOCKED"
    EXPERIMENT_BLOCKED = "EXPERIMENT_BLOCKED"
    BACKTEST_BLOCKED = "BACKTEST_BLOCKED"
    PAPER_ORDER_BLOCKED = "PAPER_ORDER_BLOCKED"
    LIVE_ORDER_BLOCKED = "LIVE_ORDER_BLOCKED"
    PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
    DEPLOYMENT_BLOCKED = "DEPLOYMENT_BLOCKED"
    GOVERNANCE_REVIEW_REQUIRED = "GOVERNANCE_REVIEW_REQUIRED"
    EXECUTION_NOT_ALLOWED = "EXECUTION_NOT_ALLOWED"


class BlockerLifecycleState(StrEnum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    MITIGATED = "MITIGATED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"
    SUPERSEDED = "SUPERSEDED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


BLOCKER_REGISTRY_PATH = Path("config/governance/blocker_registry.yaml")
_BLOCKER_CODE_RE = re.compile(r"^[A-Z]+(?:_[A-Z]+)?\.[A-Z0-9_]+$")
_FORBIDDEN_BLOCKER_CODES = frozenset(
    {
        "RUNNING_WITH_BLOCKERS",
        "LIVE_ORDER_BLOCKED",
        "RESEARCH_ONLY",
        "NO_TRADE",
        "BLOCKED",
        "CRITICAL",
        "SECURITY_CRITICAL",
    }
)
_NOT_WAIVABLE_CODES = frozenset(
    {
        "GOV.BYPASS_ATTEMPT",
        "GOV.CORE_CONSTITUTION_CONFLICT",
        "SEC.SECRET_EXPOSURE",
        "EXEC.LIVE_EXECUTION_UNAUTHORIZED",
    }
)
_AUTHORITY_CONFLICT_CODES = frozenset(
    {
        "GOV.AUTHORITY_CONFLICT",
        "GOV.CORE_CONSTITUTION_CONFLICT",
        "GOV.POLICY_CONFLICT",
        "GOV.SOURCE_OF_TRUTH_CONFLICT",
    }
)
_ACTIVE_BLOCKING_STATES = frozenset(
    {
        BlockerLifecycleState.DETECTED,
        BlockerLifecycleState.CONFIRMED,
        BlockerLifecycleState.ACTIVE,
    }
)
_LIFECYCLE_TRANSITIONS: Mapping[
    BlockerLifecycleState,
    frozenset[BlockerLifecycleState],
] = {
    BlockerLifecycleState.DETECTED: frozenset(
        {BlockerLifecycleState.CONFIRMED, BlockerLifecycleState.FALSE_POSITIVE}
    ),
    BlockerLifecycleState.CONFIRMED: frozenset({BlockerLifecycleState.ACTIVE}),
    BlockerLifecycleState.ACTIVE: frozenset(
        {
            BlockerLifecycleState.MITIGATED,
            BlockerLifecycleState.WAIVED,
            BlockerLifecycleState.SUPERSEDED,
        }
    ),
    BlockerLifecycleState.MITIGATED: frozenset(
        {BlockerLifecycleState.PENDING_VERIFICATION}
    ),
    BlockerLifecycleState.PENDING_VERIFICATION: frozenset(
        {BlockerLifecycleState.RESOLVED, BlockerLifecycleState.ACTIVE}
    ),
    BlockerLifecycleState.WAIVED: frozenset(
        {BlockerLifecycleState.ACTIVE, BlockerLifecycleState.SUPERSEDED}
    ),
    BlockerLifecycleState.RESOLVED: frozenset(),
    BlockerLifecycleState.SUPERSEDED: frozenset(),
    BlockerLifecycleState.FALSE_POSITIVE: frozenset(),
}
_DOMAIN_PREFIXES: Mapping[str, BlockerDomain] = {
    "GOV": BlockerDomain.GOVERNANCE,
    "SEC": BlockerDomain.SECURITY,
    "DATA": BlockerDomain.DATA,
    "EVID": BlockerDomain.EVIDENCE,
    "RISK": BlockerDomain.RISK,
    "VAL": BlockerDomain.VALIDATION,
    "STRAT": BlockerDomain.STRATEGY,
    "MODEL": BlockerDomain.MODEL,
    "AGENT": BlockerDomain.AGENT,
    "EXEC": BlockerDomain.EXECUTION,
    "PORT": BlockerDomain.PORTFOLIO,
    "MARKET": BlockerDomain.MARKET,
    "LIQ": BlockerDomain.LIQUIDITY,
    "OPS": BlockerDomain.OPERATIONS,
    "ARCH": BlockerDomain.ARCHITECTURE,
    "CONTRACT": BlockerDomain.CONTRACT,
    "SCHEMA": BlockerDomain.SCHEMA,
    "REPO": BlockerDomain.REPOSITORY,
    "DEP": BlockerDomain.DEPENDENCY,
    "TEST": BlockerDomain.TEST,
    "CONFIG": BlockerDomain.CONFIGURATION,
    "COMPLIANCE": BlockerDomain.COMPLIANCE,
    "RESEARCH": BlockerDomain.RESEARCH,
    "PROMOTION": BlockerDomain.PROMOTION,
}


@dataclass(frozen=True, slots=True)
class WaiverRequirements:
    allowed: bool
    required_authorities: tuple[BlockerAuthority, ...] = ()
    requires_written_approval: bool = False
    requires_justification: bool = False
    requires_evidence: bool = False
    requires_expiry: bool = False
    max_duration_hours: int | None = None
    execution_scope_allowed: bool = False

    def __post_init__(self) -> None:
        _require_unique_nonblank(
            "waiver required authorities",
            tuple(authority.value for authority in self.required_authorities),
        )
        if not self.allowed:
            if self.required_authorities:
                raise ValueError("disallowed waivers cannot require authorities")
            if any(
                (
                    self.requires_written_approval,
                    self.requires_justification,
                    self.requires_evidence,
                    self.requires_expiry,
                    self.execution_scope_allowed,
                )
            ):
                raise ValueError("disallowed waivers cannot require waiver controls")
            if self.max_duration_hours is not None:
                raise ValueError("disallowed waivers cannot define a duration")
        elif self.max_duration_hours is not None and self.max_duration_hours <= 0:
            raise ValueError("waiver max_duration_hours must be positive")

    def to_payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "required_authorities": tuple(
                authority.value for authority in self.required_authorities
            ),
            "requires_written_approval": self.requires_written_approval,
            "requires_justification": self.requires_justification,
            "requires_evidence": self.requires_evidence,
            "requires_expiry": self.requires_expiry,
            "max_duration_hours": self.max_duration_hours,
            "execution_scope_allowed": self.execution_scope_allowed,
        }


@dataclass(frozen=True, slots=True)
class ClearanceRule:
    detect_authorities: tuple[BlockerAuthority, ...]
    clear_authorities: tuple[BlockerAuthority, ...]
    waive_authorities: tuple[BlockerAuthority, ...] = ()
    downgrade_authorities: tuple[BlockerAuthority, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_nonblank(
            "clearance detect authorities",
            tuple(authority.value for authority in self.detect_authorities),
        )
        _require_unique_nonblank(
            "clearance clear authorities",
            tuple(authority.value for authority in self.clear_authorities),
        )
        _require_unique_nonblank(
            "clearance waive authorities",
            tuple(authority.value for authority in self.waive_authorities),
        )
        _require_unique_nonblank(
            "clearance downgrade authorities",
            tuple(authority.value for authority in self.downgrade_authorities),
        )
        if not self.detect_authorities:
            raise ValueError("clearance requires at least one detect authority")
        if not self.clear_authorities:
            raise ValueError("clearance requires at least one clear authority")

    def to_payload(self) -> dict[str, object]:
        return {
            "detect_authorities": tuple(
                authority.value for authority in self.detect_authorities
            ),
            "clear_authorities": tuple(
                authority.value for authority in self.clear_authorities
            ),
            "waive_authorities": tuple(
                authority.value for authority in self.waive_authorities
            ),
            "downgrade_authorities": tuple(
                authority.value for authority in self.downgrade_authorities
            ),
        }


@dataclass(frozen=True, slots=True)
class BlockerDefinition:
    definition_id: str
    blocker_code: str
    domain: BlockerDomain
    blocker_class: BlockerClass
    severity: BlockerSeverity
    scope: BlockerScope
    authority: BlockerAuthority
    effects: tuple[BlockerEffect, ...]
    waiver: WaiverRequirements
    clearance: ClearanceRule
    semantic_key: str
    description: str
    policy_ref: str
    policy_version: str
    control_ref: str
    control_version: str
    producer: str
    source_component: str
    remediation: str
    precedence: int
    security_impact: bool = False

    def __post_init__(self) -> None:
        _require_nonblank("definition_id", self.definition_id)
        _validate_blocker_code(self.blocker_code, self.domain)
        _require_unique_nonblank(
            "definition effects", tuple(effect.value for effect in self.effects)
        )
        _require_nonblank("semantic_key", self.semantic_key)
        _require_nonblank("description", self.description)
        _require_nonblank("policy_ref", self.policy_ref)
        _require_nonblank("policy_version", self.policy_version)
        _require_nonblank("control_ref", self.control_ref)
        _require_nonblank("control_version", self.control_version)
        _require_nonblank("producer", self.producer)
        _require_nonblank("source_component", self.source_component)
        _require_nonblank("remediation", self.remediation)
        if self.precedence < 0:
            raise ValueError("blocker precedence must be non-negative")
        if self.blocker_class is not BlockerClass.ADVISORY_FINDING and not self.effects:
            raise ValueError("blocking definitions must declare effects")
        if (
            self.severity is BlockerSeverity.CRITICAL
            and self.blocker_class is BlockerClass.ADVISORY_FINDING
        ):
            raise ValueError("critical severity cannot be advisory-only")
        _validate_waiver_for_code(self.blocker_code, self.waiver)
        _validate_execution_authority_conflict_effect(
            self.blocker_code, self.scope, self.effects
        )


@dataclass(frozen=True, slots=True)
class BlockerOccurrence:
    occurrence_id: str
    definition_id: str
    blocker_code: str
    domain: BlockerDomain
    blocker_class: BlockerClass
    severity: BlockerSeverity
    scope: BlockerScope
    authority: BlockerAuthority
    effects: tuple[BlockerEffect, ...]
    lifecycle_state: BlockerLifecycleState
    evidence_refs: tuple[str, ...]
    detected_at: str
    policy_ref: str
    policy_version: str
    control_ref: str
    control_version: str
    producer: str
    source_component: str
    remediation: str
    scope_ref: str | None = None
    correlation_id: str | None = None
    cycle_id: str | None = None
    snapshot_id: str | None = None
    fingerprint: str = ""
    occurrence_count: int = 1
    first_seen_at: str = ""
    last_seen_at: str = ""
    root_cause_codes: tuple[str, ...] = ()
    resolution_evidence: tuple[str, ...] = ()
    waiver: WaiverRequirements | None = None

    def __post_init__(self) -> None:
        _require_nonblank("occurrence_id", self.occurrence_id)
        _require_nonblank("definition_id", self.definition_id)
        _require_nonblank("detected_at", self.detected_at)
        _validate_blocker_code(self.blocker_code, self.domain)
        _require_unique_nonblank(
            "occurrence effects", tuple(effect.value for effect in self.effects)
        )
        _require_unique_nonblank("evidence_refs", self.evidence_refs)
        _require_unique_nonblank("resolution_evidence", self.resolution_evidence)
        for value_name, value in (
            ("policy_ref", self.policy_ref),
            ("policy_version", self.policy_version),
            ("control_ref", self.control_ref),
            ("control_version", self.control_version),
            ("producer", self.producer),
            ("source_component", self.source_component),
            ("remediation", self.remediation),
        ):
            _require_nonblank(value_name, value)
        for optional_name, optional_value in (
            ("scope_ref", self.scope_ref),
            ("correlation_id", self.correlation_id),
            ("cycle_id", self.cycle_id),
            ("snapshot_id", self.snapshot_id),
        ):
            if optional_value is not None and not optional_value.strip():
                raise ValueError(f"{optional_name} cannot be blank when provided")
        if self.occurrence_count < 1:
            raise ValueError("occurrence_count must be positive")
        if self.blocker_class is not BlockerClass.ADVISORY_FINDING and not self.effects:
            raise ValueError("blocking occurrences must declare effects")
        if (
            self.severity is BlockerSeverity.CRITICAL
            and self.blocker_class is BlockerClass.ADVISORY_FINDING
        ):
            raise ValueError("critical severity cannot be advisory-only")
        if (
            self.lifecycle_state is BlockerLifecycleState.RESOLVED
            and not self.resolution_evidence
        ):
            raise ValueError("resolved blockers require resolution evidence")
        if self.lifecycle_state is BlockerLifecycleState.WAIVED:
            if self.waiver is None or not self.waiver.allowed:
                raise ValueError("waived blockers require an allowed waiver")
        if self.waiver is not None:
            _validate_waiver_for_code(self.blocker_code, self.waiver)
        _validate_execution_authority_conflict_effect(
            self.blocker_code, self.scope, self.effects
        )
        for root_code in self.root_cause_codes:
            _validate_blocker_code(root_code, _domain_from_code(root_code))
        if not self.first_seen_at:
            object.__setattr__(self, "first_seen_at", self.detected_at)
        if not self.last_seen_at:
            object.__setattr__(self, "last_seen_at", self.detected_at)
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", self.derived_fingerprint())

    @property
    def is_blocking(self) -> bool:
        return (
            self.blocker_class
            in {
                BlockerClass.HARD_BLOCKER,
                BlockerClass.CONDITIONAL_BLOCKER,
            }
            and self.lifecycle_state in _ACTIVE_BLOCKING_STATES
        )

    @property
    def hard_gate(self) -> bool:
        return self.blocker_class in {
            BlockerClass.HARD_BLOCKER,
            BlockerClass.CONDITIONAL_BLOCKER,
        }

    @property
    def hard_gate_active(self) -> bool:
        return self.is_blocking

    def derived_fingerprint(self) -> str:
        material = "\x1f".join(
            (
                self.blocker_code,
                self.scope.value,
                self.scope_ref or "",
                self.policy_version,
                self.control_version,
                "\x1e".join(self.evidence_refs),
            )
        )
        return "blkfp:" + hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "occurrence_id": self.occurrence_id,
            "definition_id": self.definition_id,
            "blocker_code": self.blocker_code,
            "domain": self.domain.value,
            "blocker_class": self.blocker_class.value,
            "severity": self.severity.value,
            "scope": self.scope.value,
            "scope_ref": self.scope_ref,
            "authority": self.authority.value,
            "effects": tuple(effect.value for effect in self.effects),
            "lifecycle_state": self.lifecycle_state.value,
            "evidence_refs": self.evidence_refs,
            "detected_at": self.detected_at,
            "policy_ref": self.policy_ref,
            "policy_version": self.policy_version,
            "control_ref": self.control_ref,
            "control_version": self.control_version,
            "producer": self.producer,
            "source_component": self.source_component,
            "remediation": self.remediation,
            "correlation_id": self.correlation_id,
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "fingerprint": self.fingerprint,
            "occurrence_count": self.occurrence_count,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "root_cause_codes": self.root_cause_codes,
            "resolution_evidence": self.resolution_evidence,
            "waiver": self.waiver.to_payload() if self.waiver is not None else None,
        }


Blocker = BlockerOccurrence
BlockerRegistryEntry = BlockerDefinition


@dataclass(frozen=True, slots=True)
class BlockerRegistry:
    version: str
    definitions: tuple[BlockerDefinition, ...]
    aliases: Mapping[str, str]

    @property
    def entries(self) -> tuple[BlockerDefinition, ...]:
        return self.definitions

    def __post_init__(self) -> None:
        _require_nonblank("registry version", self.version)
        codes = tuple(definition.blocker_code for definition in self.definitions)
        definition_ids = tuple(
            definition.definition_id for definition in self.definitions
        )
        semantic_keys = tuple(
            definition.semantic_key for definition in self.definitions
        )
        _require_unique_nonblank("blocker registry codes", codes)
        _require_unique_nonblank("blocker registry definition ids", definition_ids)
        _require_unique_nonblank("blocker registry semantic keys", semantic_keys)
        indexed_codes = set(codes)
        for alias, target in self.aliases.items():
            _validate_alias(alias)
            if target not in indexed_codes:
                raise ValueError(f"blocker alias target is unknown: {target}")

    def require_known_code(self, blocker_code: str) -> BlockerDefinition:
        canonical_code = self.aliases.get(blocker_code, blocker_code)
        for definition in self.definitions:
            if definition.blocker_code == canonical_code:
                return definition
        raise ValueError(f"unknown blocker code: {blocker_code}")

    def require_canonical_code(self, blocker_code: str) -> BlockerDefinition:
        if blocker_code in self.aliases:
            raise ValueError(f"legacy blocker alias is not canonical: {blocker_code}")
        return self.require_known_code(blocker_code)

    def validate_occurrence(self, occurrence: BlockerOccurrence) -> None:
        definition = self.require_canonical_code(occurrence.blocker_code)
        mismatches = []
        if occurrence.definition_id != definition.definition_id:
            mismatches.append("definition_id")
        if occurrence.domain is not definition.domain:
            mismatches.append("domain")
        if occurrence.blocker_class is not definition.blocker_class:
            mismatches.append("blocker_class")
        if occurrence.severity is not definition.severity:
            mismatches.append("severity")
        if occurrence.scope is not definition.scope:
            mismatches.append("scope")
        if occurrence.authority is not definition.authority:
            mismatches.append("authority")
        if occurrence.policy_ref != definition.policy_ref:
            mismatches.append("policy_ref")
        if occurrence.policy_version != definition.policy_version:
            mismatches.append("policy_version")
        if occurrence.control_ref != definition.control_ref:
            mismatches.append("control_ref")
        if occurrence.control_version != definition.control_version:
            mismatches.append("control_version")
        if occurrence.producer != definition.producer:
            mismatches.append("producer")
        if occurrence.source_component != definition.source_component:
            mismatches.append("source_component")
        missing_effects = tuple(
            effect for effect in definition.effects if effect not in occurrence.effects
        )
        if missing_effects:
            mismatches.append("effects")
        if mismatches:
            fields = ", ".join(mismatches)
            raise ValueError(f"blocker does not match canonical registry: {fields}")

    def validate_blocker(self, blocker: BlockerOccurrence) -> None:
        self.validate_occurrence(blocker)


def load_blocker_registry(path: Path) -> BlockerRegistry:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("blocker registry must be a mapping")
    return blocker_registry_from_payload(cast(Mapping[str, Any], payload))


def blocker_registry_from_payload(payload: Mapping[str, Any]) -> BlockerRegistry:
    version = _required_string(payload, "version")
    raw_definitions = payload.get("blocker_definitions", payload.get("blocker_codes"))
    if not isinstance(raw_definitions, list):
        raise ValueError("blocker registry requires blocker_definitions")
    definitions = tuple(
        _definition_from_payload(cast(Mapping[str, Any], item))
        for item in raw_definitions
        if isinstance(item, Mapping)
    )
    if len(definitions) != len(raw_definitions):
        raise ValueError("blocker registry definitions must be mappings")
    aliases_payload = payload.get("aliases", {})
    if not isinstance(aliases_payload, Mapping):
        raise ValueError("blocker aliases must be a mapping")
    aliases = {
        _string_key(alias): _string_value(target)
        for alias, target in aliases_payload.items()
    }
    return BlockerRegistry(version=version, definitions=definitions, aliases=aliases)


def blocker_from_payload(
    payload: Mapping[str, Any],
    *,
    registry: BlockerRegistry | None = None,
    allow_migration_alias: bool = False,
) -> BlockerOccurrence:
    blocker_code = _required_string(payload, "blocker_code")
    definition: BlockerDefinition | None = None
    if registry is not None:
        definition = (
            registry.require_known_code(blocker_code)
            if allow_migration_alias
            else registry.require_canonical_code(blocker_code)
        )
        blocker_code = definition.blocker_code
    occurrence_count = _optional_int(payload, "occurrence_count")
    occurrence = BlockerOccurrence(
        occurrence_id=_required_string(payload, "occurrence_id"),
        definition_id=_required_string(payload, "definition_id"),
        blocker_code=blocker_code,
        domain=BlockerDomain(_required_string(payload, "domain")),
        blocker_class=BlockerClass(_required_string(payload, "blocker_class")),
        severity=BlockerSeverity(_required_string(payload, "severity")),
        scope=BlockerScope(_required_string(payload, "scope")),
        scope_ref=_optional_string(payload, "scope_ref"),
        authority=BlockerAuthority(_required_string(payload, "authority")),
        effects=tuple(
            BlockerEffect(value) for value in _required_string_list(payload, "effects")
        ),
        lifecycle_state=BlockerLifecycleState(
            _required_string(payload, "lifecycle_state")
        ),
        evidence_refs=_required_string_list(payload, "evidence_refs"),
        detected_at=_required_string(payload, "detected_at"),
        policy_ref=_required_string(payload, "policy_ref"),
        policy_version=_required_string(payload, "policy_version"),
        control_ref=_required_string(payload, "control_ref"),
        control_version=_required_string(payload, "control_version"),
        producer=_required_string(payload, "producer"),
        source_component=_required_string(payload, "source_component"),
        remediation=_required_string(payload, "remediation"),
        correlation_id=_optional_string(payload, "correlation_id"),
        cycle_id=_optional_string(payload, "cycle_id"),
        snapshot_id=_optional_string(payload, "snapshot_id"),
        fingerprint=_optional_string(payload, "fingerprint") or "",
        occurrence_count=occurrence_count if occurrence_count is not None else 1,
        first_seen_at=_optional_string(payload, "first_seen_at") or "",
        last_seen_at=_optional_string(payload, "last_seen_at") or "",
        root_cause_codes=_optional_string_list(payload, "root_cause_codes"),
        resolution_evidence=_optional_string_list(payload, "resolution_evidence"),
        waiver=_optional_waiver(payload),
    )
    if definition is not None and registry is not None:
        registry.validate_occurrence(occurrence)
    return occurrence


def validate_lifecycle_transition(
    current: BlockerLifecycleState,
    target: BlockerLifecycleState,
    *,
    waiver: WaiverRequirements | None = None,
    resolution_evidence: tuple[str, ...] = (),
) -> None:
    if target not in _LIFECYCLE_TRANSITIONS[current]:
        raise ValueError(f"invalid blocker lifecycle transition: {current}->{target}")
    if target is BlockerLifecycleState.WAIVED and (
        waiver is None or not waiver.allowed
    ):
        raise ValueError("waiver transition requires an allowed waiver")
    if target is BlockerLifecycleState.RESOLVED and not resolution_evidence:
        raise ValueError("resolved transition requires resolution evidence")


def _definition_from_payload(payload: Mapping[str, Any]) -> BlockerDefinition:
    return BlockerDefinition(
        definition_id=_required_string(payload, "definition_id"),
        blocker_code=_required_string(payload, "blocker_code"),
        domain=BlockerDomain(_required_string(payload, "domain")),
        blocker_class=BlockerClass(_required_string(payload, "blocker_class")),
        severity=BlockerSeverity(_required_string(payload, "severity")),
        scope=BlockerScope(_required_string(payload, "scope")),
        authority=BlockerAuthority(_required_string(payload, "authority")),
        effects=tuple(
            BlockerEffect(value) for value in _required_string_list(payload, "effects")
        ),
        waiver=_required_waiver(payload),
        clearance=_required_clearance(payload),
        semantic_key=_required_string(payload, "semantic_key"),
        description=_required_string(payload, "description"),
        policy_ref=_required_string(payload, "policy_ref"),
        policy_version=_required_string(payload, "policy_version"),
        control_ref=_required_string(payload, "control_ref"),
        control_version=_required_string(payload, "control_version"),
        producer=_required_string(payload, "producer"),
        source_component=_required_string(payload, "source_component"),
        remediation=_required_string(payload, "remediation"),
        precedence=_required_int(payload, "precedence"),
        security_impact=_optional_bool(payload, "security_impact"),
    )


def _required_waiver(payload: Mapping[str, Any]) -> WaiverRequirements:
    waiver_payload = payload.get("waiver")
    if not isinstance(waiver_payload, Mapping):
        raise ValueError("blocker definition requires waiver")
    return _waiver_from_payload(cast(Mapping[str, Any], waiver_payload))


def _optional_waiver(payload: Mapping[str, Any]) -> WaiverRequirements | None:
    waiver_payload = payload.get("waiver")
    if waiver_payload is None:
        return None
    if not isinstance(waiver_payload, Mapping):
        raise ValueError("waiver must be a mapping")
    return _waiver_from_payload(cast(Mapping[str, Any], waiver_payload))


def _waiver_from_payload(payload: Mapping[str, Any]) -> WaiverRequirements:
    return WaiverRequirements(
        allowed=_required_bool(payload, "allowed"),
        required_authorities=tuple(
            BlockerAuthority(value)
            for value in _optional_string_list(payload, "required_authorities")
        ),
        requires_written_approval=_optional_bool(payload, "requires_written_approval"),
        requires_justification=_optional_bool(payload, "requires_justification"),
        requires_evidence=_optional_bool(payload, "requires_evidence"),
        requires_expiry=_optional_bool(payload, "requires_expiry"),
        max_duration_hours=_optional_int(payload, "max_duration_hours"),
        execution_scope_allowed=_optional_bool(payload, "execution_scope_allowed"),
    )


def _required_clearance(payload: Mapping[str, Any]) -> ClearanceRule:
    clearance_payload = payload.get("clearance")
    if not isinstance(clearance_payload, Mapping):
        raise ValueError("blocker definition requires clearance")
    typed = cast(Mapping[str, Any], clearance_payload)
    return ClearanceRule(
        detect_authorities=tuple(
            BlockerAuthority(value)
            for value in _required_string_list(typed, "detect_authorities")
        ),
        clear_authorities=tuple(
            BlockerAuthority(value)
            for value in _required_string_list(typed, "clear_authorities")
        ),
        waive_authorities=tuple(
            BlockerAuthority(value)
            for value in _optional_string_list(typed, "waive_authorities")
        ),
        downgrade_authorities=tuple(
            BlockerAuthority(value)
            for value in _optional_string_list(typed, "downgrade_authorities")
        ),
    )


def _validate_blocker_code(blocker_code: str, domain: BlockerDomain) -> None:
    _require_nonblank("blocker_code", blocker_code)
    if blocker_code in _FORBIDDEN_BLOCKER_CODES:
        raise ValueError(f"blocker_code is not a cause code: {blocker_code}")
    if not _BLOCKER_CODE_RE.match(blocker_code):
        raise ValueError("blocker_code must use DOMAIN.CAUSE format")
    prefix = blocker_code.split(".", maxsplit=1)[0]
    if _DOMAIN_PREFIXES.get(prefix) is not domain:
        raise ValueError("blocker_code prefix does not match domain")


def _domain_from_code(blocker_code: str) -> BlockerDomain:
    prefix = blocker_code.split(".", maxsplit=1)[0]
    domain = _DOMAIN_PREFIXES.get(prefix)
    if domain is None:
        raise ValueError("blocker_code prefix is unknown")
    return domain


def _validate_waiver_for_code(
    blocker_code: str,
    waiver: WaiverRequirements,
) -> None:
    if blocker_code in _NOT_WAIVABLE_CODES and waiver.allowed:
        raise ValueError("this blocker code is not waivable")


def _validate_execution_authority_conflict_effect(
    blocker_code: str,
    scope: BlockerScope,
    effects: tuple[BlockerEffect, ...],
) -> None:
    if (
        blocker_code in _AUTHORITY_CONFLICT_CODES
        and scope in {BlockerScope.EXECUTION_MODE, BlockerScope.GLOBAL}
        and BlockerEffect.LIVE_ORDER_BLOCKED not in effects
    ):
        raise ValueError("execution-impacting governance conflicts block live orders")


def _validate_alias(alias: str) -> None:
    _require_nonblank("blocker alias", alias)
    if "." in alias:
        raise ValueError("blocker aliases are for legacy non-canonical codes only")
    if alias not in _FORBIDDEN_BLOCKER_CODES and not re.match(r"^[A-Z0-9_]+$", alias):
        raise ValueError("blocker alias must be a legacy upper-snake code")


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def _required_string_list(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    values = tuple(item for item in value if isinstance(item, str))
    if len(values) != len(value):
        raise ValueError(f"{key} must contain only strings")
    _require_unique_nonblank(key, values)
    return values


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonblank string or null")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer or null")
    return value


def _optional_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def _optional_string_list(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    values = tuple(item for item in value if isinstance(item, str))
    if len(values) != len(value):
        raise ValueError(f"{key} must contain only strings")
    _require_unique_nonblank(key, values)
    return values


def _string_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("blocker alias keys must be strings")
    return value


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("blocker alias targets must be strings")
    return value


def _require_nonblank(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be blank")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

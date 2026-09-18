"""Machine-readable inventory of current enforcement producers and chokepoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

import yaml

from ai4binance.governance.enforcement.registry import EnforcementProfileRegistry

DEFAULT_ENFORCEMENT_INVENTORY_PATH = Path(
    "config/governance/enforcement_inventory.yaml"
)


class EnforcementCoverageState(StrEnum):
    ROUTED = "ROUTED"
    ADAPTER_REQUIRED = "ADAPTER_REQUIRED"
    REPORT_ONLY = "REPORT_ONLY"
    PURE_DETERMINISTIC = "PURE_DETERMINISTIC"
    EXEMPT_WITH_JUSTIFICATION = "EXEMPT_WITH_JUSTIFICATION"
    BLOCKED = "BLOCKED"


class RequirementTraceStatus(StrEnum):
    DOCUMENTED_ONLY = "DOCUMENTED_ONLY"
    MACHINE_READABLE = "MACHINE_READABLE"
    IMPLEMENTED = "IMPLEMENTED"
    TESTED = "TESTED"
    RUNTIME_ENFORCED = "RUNTIME_ENFORCED"
    AUDIT_VERIFIED = "AUDIT_VERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"


class RequirementAssuranceDecision(StrEnum):
    """Non-authoritative conclusion from a requirement traceability chain."""

    ASSURED = "ASSURED"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class RequirementAssuranceChain:
    """A deterministic, non-authoritative requirement-to-assurance projection."""

    requirement_id: str
    authority_clause_ref: str
    contract_or_policy_projection_ref: str
    capability: str
    implementing_components: tuple[str, ...]
    enforcement_points: tuple[str, ...]
    executed_behavioral_tests: tuple[str, ...]
    snapshot_evidence_ref: str
    snapshot_evidence_sha256: str
    snapshot_bound: bool
    assurance_decision: RequirementAssuranceDecision
    blockers: tuple[str, ...]
    authority_inherited: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.requirement_id.strip():
            raise ValueError("requirement assurance chain requires requirement_id")
        if self.authority_inherited:
            raise ValueError("requirement assurance chain cannot inherit authority")
        if self.execution_allowed:
            raise ValueError("requirement assurance chain cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("requirement assurance chain must remain research-only")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError(
                "requirement assurance chain must keep live orders blocked"
            )
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("requirement assurance chain blockers must be unique")
        if self.assurance_decision is RequirementAssuranceDecision.ASSURED:
            if self.blockers:
                raise ValueError("assured requirement chain cannot contain blockers")
            if not self.snapshot_bound:
                raise ValueError("assured requirement chain requires snapshot evidence")
            _require_sha256("snapshot_evidence_sha256", self.snapshot_evidence_sha256)

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(f"{self.requirement_id}:{blocker}" for blocker in self.blockers)


_ROUTED_OR_EXPLICITLY_BLOCKED_STATES = frozenset(
    {
        EnforcementCoverageState.ROUTED,
        EnforcementCoverageState.BLOCKED,
    }
)
_REQUIRED_SCOPE_FAMILIES: tuple[str, ...] = (
    "registry_mutations",
    "strategy_promotion",
    "parameter_promotion",
    "model_adaptation",
    "workflow_admission",
    "lesson_promotion",
    "unattended_jobs",
    "provider_tool_side_effects",
    "execution_intents",
    "governance_changes",
    "approval_state_changes",
)


@dataclass(frozen=True, slots=True)
class RequirementTraceabilityInvariants:
    execution_allowed: bool
    promotion_status: str
    live_eligibility_status: str

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("requirement traceability cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("requirement traceability must remain research-only")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("requirement traceability must keep live orders blocked")


@dataclass(frozen=True, slots=True)
class RequirementTraceabilityEntry:
    requirement_id: str
    source_documents: tuple[str, ...]
    canonical_meaning: str
    canonical_owner: str
    authority_ref: str
    machine_readable_ref: str
    implementation_refs: tuple[str, ...]
    enforcement_entrypoints: tuple[str, ...]
    test_refs: tuple[str, ...]
    evidence_ref: str
    evidence_sha256: str
    trace_status: RequirementTraceStatus
    convergence_state: str

    def __post_init__(self) -> None:
        for field_name in (
            "requirement_id",
            "canonical_meaning",
            "canonical_owner",
            "authority_ref",
            "machine_readable_ref",
            "evidence_ref",
            "evidence_sha256",
            "convergence_state",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        _require_sha256("evidence_sha256", self.evidence_sha256)
        if (
            len(self.requirement_id) != 6
            or not self.requirement_id.startswith("RQ-")
            or not self.requirement_id[3:].isdigit()
        ):
            raise ValueError("requirement_id must use the RQ-NNN format")
        for name, values in (
            ("source_documents", self.source_documents),
            ("implementation_refs", self.implementation_refs),
            ("enforcement_entrypoints", self.enforcement_entrypoints),
            ("test_refs", self.test_refs),
        ):
            _require_unique_nonblank(
                name, values, allow_empty=name == "enforcement_entrypoints"
            )

    @property
    def is_converged(self) -> bool:
        if self.trace_status is RequirementTraceStatus.NOT_APPLICABLE:
            return self.convergence_state == "NOT_APPLICABLE"
        return (
            self.trace_status is RequirementTraceStatus.AUDIT_VERIFIED
            and self.convergence_state.startswith("SATISFIED")
        )

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        if self.is_converged:
            return ()
        blockers: list[str] = []
        if self.trace_status not in {
            RequirementTraceStatus.AUDIT_VERIFIED,
            RequirementTraceStatus.NOT_APPLICABLE,
        }:
            blockers.append(
                f"{self.requirement_id}:TRACE_STATUS_{self.trace_status.value}"
            )
        if not self.convergence_state.startswith("SATISFIED"):
            blockers.append(
                f"{self.requirement_id}:CONVERGENCE_{self.convergence_state}"
            )
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class RequirementTraceabilityRegistry:
    canonical_owner: str
    source_class: str
    source_corpus_sha256: str
    manifest_id: str
    invariants: RequirementTraceabilityInvariants
    allowed_trace_statuses: tuple[RequirementTraceStatus, ...]
    entries: tuple[RequirementTraceabilityEntry, ...]

    def __post_init__(self) -> None:
        for field_name in ("canonical_owner", "source_class"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"requirement traceability {field_name} is required")
        _require_sha256(
            "requirement traceability source_corpus_sha256",
            self.source_corpus_sha256,
        )
        _require_sha256("requirement traceability manifest_id", self.manifest_id)
        if not self.allowed_trace_statuses:
            raise ValueError("allowed_trace_statuses cannot be empty")
        if len(set(self.allowed_trace_statuses)) != len(self.allowed_trace_statuses):
            raise ValueError("allowed_trace_statuses must be unique")
        if not self.entries:
            raise ValueError("requirement traceability entries cannot be empty")
        requirement_ids = tuple(entry.requirement_id for entry in self.entries)
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("requirement traceability IDs must be unique")
        unexpected_statuses = sorted(
            {
                entry.trace_status.value
                for entry in self.entries
                if entry.trace_status not in self.allowed_trace_statuses
            }
        )
        if unexpected_statuses:
            raise ValueError(
                "requirement traceability contains disallowed statuses: "
                + ", ".join(unexpected_statuses)
            )

    @property
    def blocking_entries(self) -> tuple[RequirementTraceabilityEntry, ...]:
        return tuple(entry for entry in self.entries if not entry.is_converged)

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(
            blocker
            for entry in self.blocking_entries
            for blocker in entry.blocker_codes
        )

    @property
    def converged_count(self) -> int:
        return len(self.entries) - len(self.blocking_entries)

    def assert_enforcement_entrypoints_registered(
        self,
        entrypoint_ids: tuple[str, ...],
    ) -> None:
        registered = set(entrypoint_ids)
        unknown = sorted(
            {
                entrypoint
                for entry in self.entries
                for entrypoint in entry.enforcement_entrypoints
                if entrypoint not in registered
            }
        )
        if unknown:
            raise ValueError(
                "requirement traceability references unknown enforcement entrypoints: "
                + ", ".join(unknown)
            )

    def assurance_chains(
        self,
        repository_root: Path,
    ) -> tuple[RequirementAssuranceChain, ...]:
        """Evaluate requirement links without granting authority from evidence."""
        return tuple(
            _requirement_assurance_chain(repository_root, entry)
            for entry in self.entries
        )


def _requirement_assurance_chain(
    repository_root: Path,
    entry: RequirementTraceabilityEntry,
) -> RequirementAssuranceChain:
    root = repository_root.resolve()
    blockers: list[str] = []
    for blocker, references in (
        ("AUTHORITY_CLAUSE_MISSING", (entry.authority_ref,)),
        ("CONTRACT_POLICY_PROJECTION_MISSING", (entry.machine_readable_ref,)),
        ("IMPLEMENTING_COMPONENT_MISSING", entry.implementation_refs),
        ("BEHAVIORAL_TEST_MISSING", entry.test_refs),
    ):
        if any(_repository_file(root, reference) is None for reference in references):
            blockers.append(blocker)
    if not entry.enforcement_entrypoints:
        blockers.append("ENFORCEMENT_POINT_MISSING")
    if entry.trace_status is not RequirementTraceStatus.AUDIT_VERIFIED:
        blockers.append("BEHAVIORAL_TEST_EXECUTION_UNPROVEN")

    evidence_path = _repository_file(root, entry.evidence_ref)
    evidence_sha256 = ""
    snapshot_bound = not _is_mutable_evidence_reference(entry.evidence_ref)
    if not snapshot_bound:
        blockers.append("SNAPSHOT_EVIDENCE_MUTABLE")
    if evidence_path is None:
        blockers.append("SNAPSHOT_EVIDENCE_MISSING")
    else:
        try:
            evidence_sha256 = sha256(evidence_path.read_bytes()).hexdigest()
        except OSError:
            blockers.append("SNAPSHOT_EVIDENCE_UNREADABLE")
        else:
            if evidence_sha256 != entry.evidence_sha256:
                blockers.append("SNAPSHOT_EVIDENCE_HASH_MISMATCH")

    blockers.extend(
        blocker.split(":", maxsplit=1)[1] for blocker in entry.blocker_codes
    )
    unique_blockers = tuple(dict.fromkeys(blockers))
    if (
        entry.trace_status is RequirementTraceStatus.NOT_APPLICABLE
        and not unique_blockers
    ):
        decision = RequirementAssuranceDecision.NOT_APPLICABLE
    elif entry.is_converged and not unique_blockers:
        decision = RequirementAssuranceDecision.ASSURED
    else:
        decision = RequirementAssuranceDecision.BLOCKED
    return RequirementAssuranceChain(
        requirement_id=entry.requirement_id,
        authority_clause_ref=entry.authority_ref,
        contract_or_policy_projection_ref=entry.machine_readable_ref,
        capability=entry.canonical_meaning,
        implementing_components=entry.implementation_refs,
        enforcement_points=entry.enforcement_entrypoints,
        executed_behavioral_tests=entry.test_refs,
        snapshot_evidence_ref=entry.evidence_ref,
        snapshot_evidence_sha256=evidence_sha256,
        snapshot_bound=snapshot_bound,
        assurance_decision=decision,
        blockers=unique_blockers,
    )


@dataclass(frozen=True, slots=True)
class EnforcementInventoryEntry:
    entrypoint_id: str
    scope_family: str
    object_type: str
    action: str
    integration_surface: str
    current_enforcer: str
    coverage_state: EnforcementCoverageState
    status_rationale: str
    authority_source: str
    policy_source: str
    blocker_source: str
    tests: tuple[str, ...]
    bypass_possible: bool
    consequential: bool

    def __post_init__(self) -> None:
        for field_name in (
            "entrypoint_id",
            "scope_family",
            "object_type",
            "action",
            "integration_surface",
            "current_enforcer",
            "status_rationale",
            "authority_source",
            "policy_source",
            "blocker_source",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if not self.tests:
            raise ValueError("inventory entry tests are required")
        if any(not item.strip() for item in self.tests):
            raise ValueError("inventory entry tests cannot contain blanks")
        if len(set(self.tests)) != len(self.tests):
            raise ValueError("inventory entry tests must be unique")


@dataclass(frozen=True, slots=True)
class EnforcementInventory:
    version: str
    entries: tuple[EnforcementInventoryEntry, ...]
    non_consequential_examples: tuple[str, ...] = ()
    requirement_traceability: RequirementTraceabilityRegistry | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("enforcement inventory version is required")
        if not self.entries:
            raise ValueError("enforcement inventory requires entries")
        entrypoint_ids = tuple(item.entrypoint_id for item in self.entries)
        if len(set(entrypoint_ids)) != len(entrypoint_ids):
            raise ValueError("enforcement inventory entrypoint IDs must be unique")
        if any(not example.strip() for example in self.non_consequential_examples):
            raise ValueError("non-consequential examples cannot contain blanks")
        if len(set(self.non_consequential_examples)) != len(
            self.non_consequential_examples
        ):
            raise ValueError("non-consequential examples must be unique")

    def entry_for(
        self, object_type: str, action: str
    ) -> EnforcementInventoryEntry | None:
        matches = self.entries_for_object_type_action(object_type, action)
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(
                "enforcement inventory has multiple entrypoints for "
                f"{object_type}:{action}"
            )
        return matches[0]

    def entry_for_entrypoint(
        self,
        entrypoint_id: str,
    ) -> EnforcementInventoryEntry | None:
        for entry in self.entries:
            if entry.entrypoint_id == entrypoint_id:
                return entry
        return None

    def entries_for_object_type_action(
        self,
        object_type: str,
        action: str,
    ) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.object_type == object_type and entry.action == action
        )

    def entries_for_coverage_state(
        self,
        coverage_state: EnforcementCoverageState,
    ) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(
            entry for entry in self.entries if entry.coverage_state is coverage_state
        )

    def entries_for_scope_family(
        self,
        scope_family: str,
    ) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(
            entry for entry in self.entries if entry.scope_family == scope_family
        )

    def consequential_entries(self) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(entry for entry in self.entries if entry.consequential)

    def routed_or_explicitly_blocked_entries(
        self,
    ) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.coverage_state in _ROUTED_OR_EXPLICITLY_BLOCKED_STATES
        )

    def uncovered_consequential_entries(self) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.consequential_entries()
            if entry.coverage_state not in _ROUTED_OR_EXPLICITLY_BLOCKED_STATES
        )

    def bypassable_consequential_entries(
        self,
    ) -> tuple[EnforcementInventoryEntry, ...]:
        return tuple(
            entry for entry in self.consequential_entries() if entry.bypass_possible
        )

    def assert_exit_invariant(self) -> None:
        unresolved = tuple(
            entry.entrypoint_id for entry in self.uncovered_consequential_entries()
        )
        if unresolved:
            raise ValueError(
                "universal enforcement inventory has unresolved consequential "
                "entrypoints: " + ", ".join(unresolved)
            )
        bypassable = tuple(
            entry.entrypoint_id for entry in self.bypassable_consequential_entries()
        )
        if bypassable:
            raise ValueError(
                "universal enforcement inventory still permits bypass on "
                "consequential entrypoints: " + ", ".join(bypassable)
            )

    def assert_required_scope_families_covered(self) -> None:
        covered = {entry.scope_family for entry in self.consequential_entries()}
        missing = tuple(
            family for family in _REQUIRED_SCOPE_FAMILIES if family not in covered
        )
        if missing:
            raise ValueError(
                "enforcement inventory is missing required scope families: "
                + ", ".join(missing)
            )

    def assert_non_consequential_examples_excluded(self) -> None:
        consequential_ids = {
            entry.entrypoint_id for entry in self.consequential_entries()
        }
        included = tuple(
            example
            for example in self.non_consequential_examples
            if example in consequential_ids
        )
        if included:
            raise ValueError(
                "non-consequential examples cannot be tracked as consequential "
                "entrypoints: " + ", ".join(included)
            )

    def assert_profile_registry_alignment(
        self, profile_registry: EnforcementProfileRegistry
    ) -> None:
        missing = sorted(
            {
                entry.object_type
                for entry in self.consequential_entries()
                if profile_registry.profile_for_object_type(entry.object_type) is None
            }
        )
        if missing:
            raise ValueError(
                "enforcement inventory references unmanaged object types: "
                + ", ".join(missing)
            )


def load_enforcement_inventory(
    path: Path = DEFAULT_ENFORCEMENT_INVENTORY_PATH,
) -> EnforcementInventory:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError("enforcement inventory could not be loaded") from error
    if not isinstance(payload, Mapping):
        raise ValueError("enforcement inventory must be a mapping")
    version = str(payload.get("version", "")).strip()
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("enforcement inventory entries must be a list")
    raw_non_consequential_examples = payload.get("non_consequential_examples", [])
    if not isinstance(raw_non_consequential_examples, list):
        raise ValueError("non-consequential examples must be a list")
    entries = tuple(_entry_from_payload(entry) for entry in raw_entries)
    traceability = _traceability_from_payload(payload.get("requirement_traceability"))
    inventory = EnforcementInventory(
        version=version,
        entries=entries,
        non_consequential_examples=tuple(
            str(item).strip() for item in raw_non_consequential_examples
        ),
        requirement_traceability=traceability,
    )
    if traceability is not None:
        traceability.assert_enforcement_entrypoints_registered(
            tuple(entry.entrypoint_id for entry in entries)
        )
    return inventory


def _entry_from_payload(payload: object) -> EnforcementInventoryEntry:
    if not isinstance(payload, Mapping):
        raise ValueError("enforcement inventory entry must be a mapping")
    raw_tests = payload.get("tests")
    if not isinstance(raw_tests, list):
        raise ValueError("enforcement inventory entry tests must be a list")
    return EnforcementInventoryEntry(
        entrypoint_id=str(payload.get("entrypoint_id", "")).strip(),
        scope_family=str(payload.get("scope_family", "")).strip(),
        object_type=str(payload.get("object_type", "")).strip(),
        action=str(payload.get("action", "")).strip(),
        integration_surface=str(payload.get("integration_surface", "")).strip(),
        current_enforcer=str(payload.get("current_enforcer", "")).strip(),
        coverage_state=EnforcementCoverageState(
            str(payload.get("coverage_state", "")).strip()
        ),
        status_rationale=str(payload.get("status_rationale", "")).strip(),
        authority_source=str(payload.get("authority_source", "")).strip(),
        policy_source=str(payload.get("policy_source", "")).strip(),
        blocker_source=str(payload.get("blocker_source", "")).strip(),
        tests=tuple(str(item).strip() for item in raw_tests),
        bypass_possible=bool(payload.get("bypass_possible", False)),
        consequential=bool(payload.get("consequential", True)),
    )


def _traceability_from_payload(
    payload: object,
) -> RequirementTraceabilityRegistry | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("requirement_traceability must be a mapping")
    raw_invariants = payload.get("invariants")
    if not isinstance(raw_invariants, Mapping):
        raise ValueError("requirement traceability invariants must be a mapping")
    raw_allowed_statuses = payload.get("allowed_trace_statuses")
    if not isinstance(raw_allowed_statuses, list):
        raise ValueError("allowed_trace_statuses must be a list")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("requirement traceability entries must be a list")
    return RequirementTraceabilityRegistry(
        canonical_owner=str(payload.get("canonical_owner", "")).strip(),
        source_class=str(payload.get("source_class", "")).strip(),
        source_corpus_sha256=str(payload.get("source_corpus_sha256", "")).strip(),
        manifest_id=str(payload.get("manifest_id", "")).strip(),
        invariants=RequirementTraceabilityInvariants(
            execution_allowed=_required_bool(raw_invariants, "execution_allowed"),
            promotion_status=str(raw_invariants.get("promotion_status", "")).strip(),
            live_eligibility_status=str(
                raw_invariants.get("live_eligibility_status", "")
            ).strip(),
        ),
        allowed_trace_statuses=tuple(
            RequirementTraceStatus(str(status).strip())
            for status in raw_allowed_statuses
        ),
        entries=tuple(_traceability_entry_from_payload(entry) for entry in raw_entries),
    )


def _traceability_entry_from_payload(payload: object) -> RequirementTraceabilityEntry:
    if not isinstance(payload, Mapping):
        raise ValueError("requirement traceability entry must be a mapping")
    return RequirementTraceabilityEntry(
        requirement_id=str(payload.get("requirement_id", "")).strip(),
        source_documents=_string_tuple(payload, "source_documents"),
        canonical_meaning=str(payload.get("canonical_meaning", "")).strip(),
        canonical_owner=str(payload.get("canonical_owner", "")).strip(),
        authority_ref=str(payload.get("authority_ref", "")).strip(),
        machine_readable_ref=str(payload.get("machine_readable_ref", "")).strip(),
        implementation_refs=_string_tuple(payload, "implementation_refs"),
        enforcement_entrypoints=_string_tuple(
            payload,
            "enforcement_entrypoints",
            allow_empty=True,
        ),
        test_refs=_string_tuple(payload, "test_refs"),
        evidence_ref=str(payload.get("evidence_ref", "")).strip(),
        evidence_sha256=str(payload.get("evidence_sha256", "")).strip(),
        trace_status=RequirementTraceStatus(
            str(payload.get("trace_status", "")).strip()
        ),
        convergence_state=str(payload.get("convergence_state", "")).strip(),
    )


def _string_tuple(
    payload: Mapping[object, object],
    key: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    raw_values = payload.get(key)
    if not isinstance(raw_values, list):
        raise ValueError(f"{key} must be a list")
    values = tuple(str(value).strip() for value in raw_values)
    _require_unique_nonblank(key, values, allow_empty=allow_empty)
    return values


def _required_bool(payload: Mapping[object, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _repository_file(repository_root: Path, reference: str) -> Path | None:
    candidate = (repository_root / reference).resolve()
    try:
        candidate.relative_to(repository_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _is_mutable_evidence_reference(reference: str) -> bool:
    return any(part.casefold() == "latest.json" for part in Path(reference).parts)


def _require_unique_nonblank(
    name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool = False,
) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{name} cannot be empty")
    if any(not value for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 value")


def inventory_object_types(inventory: EnforcementInventory) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.object_type for item in inventory.entries))


def inventory_actions_for_object_type(
    inventory: EnforcementInventory,
    object_type: str,
) -> tuple[str, ...]:
    return tuple(
        entry.action for entry in inventory.entries if entry.object_type == object_type
    )


def inventory_entrypoint_ids(inventory: EnforcementInventory) -> tuple[str, ...]:
    return tuple(entry.entrypoint_id for entry in inventory.entries)


def inventory_scope_families(inventory: EnforcementInventory) -> tuple[str, ...]:
    return tuple(dict.fromkeys(entry.scope_family for entry in inventory.entries))


def consequential_entrypoint_ids(inventory: EnforcementInventory) -> tuple[str, ...]:
    return tuple(entry.entrypoint_id for entry in inventory.consequential_entries())


def routed_or_explicitly_blocked_entrypoint_ids(
    inventory: EnforcementInventory,
) -> tuple[str, ...]:
    return tuple(
        entry.entrypoint_id
        for entry in inventory.routed_or_explicitly_blocked_entries()
    )


def uncovered_consequential_entrypoint_ids(
    inventory: EnforcementInventory,
) -> tuple[str, ...]:
    return tuple(
        entry.entrypoint_id for entry in inventory.uncovered_consequential_entries()
    )


def bypassable_consequential_entrypoint_ids(
    inventory: EnforcementInventory,
) -> tuple[str, ...]:
    return tuple(
        entry.entrypoint_id for entry in inventory.bypassable_consequential_entries()
    )


def required_scope_families() -> tuple[str, ...]:
    return _REQUIRED_SCOPE_FAMILIES

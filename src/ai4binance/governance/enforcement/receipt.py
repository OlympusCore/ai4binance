"""PDP-to-PEP consumption receipt for an already evaluated policy decision."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    canonical_trace_sha256,
)
from ai4binance.governance.capability_store import CapabilityLease, CapabilityStore
from ai4binance.governance.enforcement.contracts import (
    CoreConsumptionReceipt,
    EnforcementDecision,
    EnforcementOutcome,
)
from ai4binance.storage import write_json_object_verified

if TYPE_CHECKING:
    from ai4binance.governance.architecture.model import (
        CoreModule,
        LogicalArchitectureRegistry,
    )


def core_consumption_subject_sha256(repository_root: Path) -> str:
    """Fingerprint the same exact workspace subject as canonical quality evidence."""
    from ai4binance.governance.constitution_sync import (
        build_quality_gate_workspace_attestation,
    )

    return canonical_trace_sha256(
        build_quality_gate_workspace_attestation(repository_root).to_payload()
    )


def _core_related_component_ids(
    module: CoreModule, registry: LogicalArchitectureRegistry
) -> set[str]:
    ids = set(module.component_ids)
    pending = list(ids)
    while pending:
        current = pending.pop()
        for relation in registry.relations:
            if (
                relation.from_component_id == current
                and relation.to_component_id not in ids
            ):
                ids.add(relation.to_component_id)
                pending.append(relation.to_component_id)
    return ids


def _core_source_hashes(
    root: Path,
    module: CoreModule,
    registry: LogicalArchitectureRegistry,
    *,
    workspace_subject_sha256: str | None = None,
) -> dict[str, str]:
    """Bind declarations, policy, contracts and relevant dependency sources."""
    ids = _core_related_component_ids(module, registry)
    paths = {
        "docs/registries/registry_logical_architecture.yaml",
        "schemas/architecture/logical_architecture.schema.json",
        "config/governance/enforcement_profiles.yaml",
        "config/governance/enforcement_inventory.yaml",
        "config/governance/governance_enforcement_fabric.yaml",
        "schemas/governance/governed_object_enforcement.schema.json",
        "src/ai4binance/governance/architecture/assurance.py",
        "src/ai4binance/governance/architecture/observation.py",
        "src/ai4binance/core/contracts/core_observation.py",
        "src/ai4binance/governance/enforcement/receipt.py",
        *module.accountability_refs.values(),
    }
    for component in registry.components:
        if component.component_id in ids:
            paths.update((*component.source_paths, *component.contract_refs))
    if module.assurance is not None:
        paths.update(module.assurance.veto_boundary_refs)
        for binding in module.assurance.interfaces:
            paths.update(
                (
                    binding.contract_ref,
                    binding.producer_ref.partition("::")[0],
                    binding.consumer_ref.partition("::")[0],
                )
            )
        if module.assurance.resource_budget_ref is not None:
            paths.add(module.assurance.resource_budget_ref)
    hashes = {}
    for reference in sorted(paths):
        path = (root / reference).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("CORE_CONSUMPTION_SOURCE_UNAVAILABLE")
        hashes[reference] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes["workspace_subject_sha256"] = (
        core_consumption_subject_sha256(root)
        if workspace_subject_sha256 is None
        else workspace_subject_sha256
    )
    return hashes


def persist_core_consumption_receipt(
    *,
    repository_root: Path,
    registry: LogicalArchitectureRegistry,
    core_id: str,
    interface_id: str,
    cycle_id: str,
    source_subject_sha256: str,
    input_sha256: str,
    output_sha256: str | None,
    outcome_sha256: str | None,
    resources: dict[str, object],
    operation_status: str = "SUCCESS",
    journal: CanonicalTraceJournal | None = None,
) -> Path:
    """Record a completed caller handoff, storing hashes rather than input data."""
    root = repository_root.resolve()
    module = next(item for item in registry.core_modules if item.core_id == core_id)
    if module.assurance is None:
        raise ValueError("CORE_ASSURANCE_CONTRACT_MISSING")
    binding = next(
        item
        for item in module.assurance.interfaces
        if item.interface_id == interface_id
    )
    observed = datetime.now(UTC)
    source_hashes = _core_source_hashes(root, module, registry)
    if source_hashes["workspace_subject_sha256"] != source_subject_sha256:
        raise ValueError("CORE_CONSUMPTION_SUBJECT_CHANGED_DURING_OPERATION")
    receipt = CoreConsumptionReceipt(
        core_id=core_id,
        interface_id=interface_id,
        component_id=binding.component_id,
        cycle_id=cycle_id,
        producer_ref=binding.producer_ref,
        consumer_ref=binding.consumer_ref,
        contract_ref=binding.contract_ref,
        observed_at=observed.isoformat(),
        observation_class="TEST_ONLY"
        if os.environ.get("PYTEST_CURRENT_TEST")
        else "OBSERVED_LOCAL_CALL",
        operation_status=operation_status,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        outcome_sha256=outcome_sha256,
        source_hashes=source_hashes,
        resources=resources,
    )
    return _persist_core_receipt(root, receipt, journal)


def persist_core_consumption_batch(
    repository_root: Path,
    registry: LogicalArchitectureRegistry,
    receipts: Sequence[CoreConsumptionReceipt],
    *,
    source_subject_sha256: str,
    journal: CanonicalTraceJournal | None = None,
) -> tuple[Path, ...]:
    """Verify one completed cycle before persisting its actual handoffs."""
    from ai4binance.schema_validation import validate_local_definition

    root = repository_root.resolve()
    if core_consumption_subject_sha256(root) != source_subject_sha256:
        raise ValueError("CORE_CONSUMPTION_SUBJECT_CHANGED_DURING_OPERATION")
    modules = {item.core_id: item for item in registry.core_modules}
    fingerprints: dict[str, dict[str, str]] = {}
    # Verify the complete batch before writing the first observation.
    for receipt in receipts:
        payload = receipt.to_payload()
        validate_local_definition(
            root / "schemas/governance/governed_object_enforcement.schema.json",
            "CoreConsumptionReceipt",
            payload,
        )
        _validate_core_resource_status(payload)
        module = modules.get(receipt.core_id)
        if module is None or module.assurance is None:
            raise ValueError("CORE_ASSURANCE_CONTRACT_MISSING")
        binding = next(
            (
                item
                for item in module.assurance.interfaces
                if item.interface_id == receipt.interface_id
            ),
            None,
        )
        if binding is None or any(
            receipt.to_payload()[key] != value
            for key, value in binding.to_payload().items()
        ):
            raise ValueError("CORE_RECEIPT_BINDING_INVALID")
        if module.core_id not in fingerprints:
            fingerprints[module.core_id] = _core_source_hashes(
                root, module, registry, workspace_subject_sha256=source_subject_sha256
            )
        if dict(receipt.source_hashes) != fingerprints[module.core_id]:
            raise ValueError("CORE_CONSUMPTION_SOURCE_CHANGED_DURING_OPERATION")
    paths = tuple(_persist_core_receipt(root, receipt, journal) for receipt in receipts)
    if core_consumption_subject_sha256(root) != source_subject_sha256:
        raise ValueError("CORE_CONSUMPTION_SUBJECT_CHANGED_DURING_PERSISTENCE")
    return paths


def _persist_core_receipt(
    root: Path,
    receipt: CoreConsumptionReceipt,
    journal: CanonicalTraceJournal | None,
) -> Path:
    from ai4binance.events.traceability import canonical_trace_journal_path
    from ai4binance.schema_validation import validate_local_definition

    payload = receipt.to_payload()
    validate_local_definition(
        root / "schemas/governance/governed_object_enforcement.schema.json",
        "CoreConsumptionReceipt",
        payload,
    )
    _validate_core_resource_status(payload)
    selected = journal or CanonicalTraceJournal(
        canonical_trace_journal_path(root), durable=True
    )
    digest = canonical_trace_sha256(payload)
    path = selected.path.parent / "core_consumption_receipts" / f"{digest}.json"
    write_json_object_verified(
        path,
        payload,
        blocker="CORE_RECEIPT_PERSISTENCE_FAILED",
        subject_id=receipt.cycle_id,
        durable=True,
    )
    selected.append(
        CanonicalTraceRecord.create(
            trace_id=f"trace:core-consumption:{digest}",
            trace_kind=ConsequentialTraceKind.GATE,
            subject_ref=receipt.core_id,
            subject_type="CORE_INTERFACE",
            # The journal records when this fact is persisted. The immutable
            # receipt retains the actual, possibly earlier, consumption time.
            occurred_at=datetime.now(UTC),
            event_name="CORE_OUTPUT_CONSUMED",
            event_status=receipt.operation_status,
            evidence_refs=(str(path.resolve()),),
            related_refs=(receipt.interface_id, receipt.cycle_id),
            subject_sha256=digest,
        )
    )
    return path


def load_core_consumption_batch(
    journal: CanonicalTraceJournal,
    repository_root: Path,
    registry: LogicalArchitectureRegistry,
) -> tuple[dict[str, object], ...]:
    """Verify canonical membership, schema, current sources and exact handoffs."""
    root = repository_root.resolve()
    modules = {item.core_id: item for item in registry.core_modules}
    fingerprints: dict[str, dict[str, str]] = {}
    result = []
    for record in journal.records():
        if record.event_name != "CORE_OUTPUT_CONSUMED":
            continue
        if (
            record.subject_ref not in modules
            or record.subject_type != "CORE_INTERFACE"
            or record.trace_kind is not ConsequentialTraceKind.GATE
            or len(record.evidence_refs) != 1
        ):
            raise ValueError("CORE_RECEIPT_TRACE_INVALID")
        module = modules[record.subject_ref]
        if module.assurance is None:
            raise ValueError("CORE_ASSURANCE_CONTRACT_MISSING")
        payload = _read_core_consumption_record(root, journal, record)
        if module.core_id not in fingerprints:
            fingerprints[module.core_id] = _core_source_hashes(root, module, registry)
        current = fingerprints[module.core_id]
        if payload["source_hashes"] != current:
            continue
        _validate_core_consumption_binding(module, record, payload)
        age = (
            datetime.now(UTC) - datetime.fromisoformat(str(payload["observed_at"]))
        ).total_seconds()
        if age < 0 or age > module.assurance.evidence_max_age_seconds:
            continue
        result.append(payload)
    for core_id, previous in fingerprints.items():
        if previous != _core_source_hashes(root, modules[core_id], registry):
            raise ValueError("CORE_RECEIPT_SOURCE_CHANGED_DURING_READ")
    return tuple(result)


def _read_core_consumption_record(
    root: Path,
    journal: CanonicalTraceJournal,
    record: CanonicalTraceRecord,
) -> dict[str, object]:
    from ai4binance.schema_validation import validate_local_definition

    path = Path(record.evidence_refs[0]).resolve()
    directory = (journal.path.parent / "core_consumption_receipts").resolve()
    if (
        path.parent != directory
        or path.stem != record.subject_sha256
        or path.stat().st_size > 65_536
    ):
        raise ValueError("CORE_RECEIPT_PATH_INVALID")
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_local_definition(
        root / "schemas/governance/governed_object_enforcement.schema.json",
        "CoreConsumptionReceipt",
        payload,
    )
    if canonical_trace_sha256(payload) != record.subject_sha256:
        raise ValueError("CORE_RECEIPT_HASH_MISMATCH")
    _validate_core_resource_status(payload)
    return cast(dict[str, object], payload)


def _validate_core_resource_status(payload: dict[str, object]) -> None:
    from ai4binance.ops.performance import OperationResourceMeasurement

    measured = OperationResourceMeasurement(
        **cast(dict[str, Any], payload["resources"])
    )
    if (
        payload["operation_status"] != "DENIED"
        and measured.operation_status != payload["operation_status"]
    ):
        raise ValueError("CORE_RECEIPT_RESOURCE_STATUS_MISMATCH")


def _validate_core_consumption_binding(
    module: CoreModule,
    record: CanonicalTraceRecord,
    payload: dict[str, object],
) -> None:
    if module.assurance is None:
        raise ValueError("CORE_ASSURANCE_CONTRACT_MISSING")
    binding = next(
        (
            item
            for item in module.assurance.interfaces
            if item.interface_id == payload["interface_id"]
        ),
        None,
    )
    if (
        binding is None
        or payload["core_id"] != record.subject_ref
        or payload["operation_status"] != record.event_status
        or (payload["interface_id"], payload["cycle_id"]) != record.related_refs
        or datetime.fromisoformat(str(payload["observed_at"])) > record.occurred_at
        or any(payload[key] != value for key, value in binding.to_payload().items())
    ):
        raise ValueError("CORE_RECEIPT_BINDING_INVALID")


class PolicyEnforcementStatus(StrEnum):
    ENFORCED = "ENFORCED"
    DENIED = "DENIED"


class StaleEnforcementEvidenceError(ValueError):
    """Intact historical evidence cannot attest to the currently loaded sources."""


@dataclass(frozen=True, slots=True)
class PolicyEnforcementReceipt:
    receipt_id: str
    decision_id: str
    decision_sha256: str
    subject_hash: str
    scope_hash: str
    approval_set_hash: str
    pep_id: str
    enforcement_id: str
    enforced_at: datetime
    status: PolicyEnforcementStatus
    blockers: tuple[str, ...]
    capability_lease_id: str | None = None
    capability_policy_hash: str | None = None
    capability_scope_hash: str | None = None
    capability_run_id: str | None = None
    capability_project: str | None = None
    capability_tool_name: str | None = None
    outcome_sha256: str | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not isinstance(self.status, PolicyEnforcementStatus):
            raise ValueError("policy enforcement status is invalid")
        for name in (
            "receipt_id",
            "decision_id",
            "pep_id",
            "enforcement_id",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"policy enforcement {name} is required")
        for name in (
            "decision_sha256",
            "subject_hash",
            "scope_hash",
            "approval_set_hash",
        ):
            _require_sha256(name, str(getattr(self, name)))
        if (
            self.enforced_at.tzinfo is None
            or self.enforced_at.utcoffset() != UTC.utcoffset(self.enforced_at)
        ):
            raise ValueError("policy enforcement enforced_at must be UTC")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("policy enforcement blockers cannot contain blanks")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("policy enforcement blockers must be unique")
        capability_fields = (
            self.capability_lease_id,
            self.capability_policy_hash,
            self.capability_scope_hash,
            self.capability_run_id,
            self.capability_project,
            self.capability_tool_name,
        )
        if any(value is None for value in capability_fields) != all(
            value is None for value in capability_fields
        ):
            raise ValueError("policy enforcement capability binding must be complete")
        if self.capability_policy_hash is not None:
            _require_sha256("capability_policy_hash", self.capability_policy_hash)
            _require_sha256("capability_scope_hash", str(self.capability_scope_hash))
            if self.capability_lease_id is None or not self.capability_lease_id.strip():
                raise ValueError("policy enforcement capability lease_id is required")
        if self.outcome_sha256 is not None:
            _require_sha256("outcome_sha256", self.outcome_sha256)
        if self.status is PolicyEnforcementStatus.ENFORCED:
            if self.blockers:
                raise ValueError("enforced policy receipt cannot contain blockers")
            if self.capability_lease_id is None or self.outcome_sha256 is None:
                raise ValueError(
                    "enforced policy receipt requires capability and outcome"
                )
        elif not self.blockers:
            raise ValueError("denied policy receipt requires blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("policy enforcement receipt cannot grant live authority")

    @property
    def semantic_sha256(self) -> str:
        payload = json.dumps(
            self.to_payload(include_semantic_hash=False),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_payload(self, *, include_semantic_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "receipt_id": self.receipt_id,
            "decision_id": self.decision_id,
            "decision_sha256": self.decision_sha256,
            "subject_hash": self.subject_hash,
            "scope_hash": self.scope_hash,
            "approval_set_hash": self.approval_set_hash,
            "pep_id": self.pep_id,
            "enforcement_id": self.enforcement_id,
            "enforced_at": self.enforced_at.isoformat().replace("+00:00", "Z"),
            "status": self.status.value,
            "blockers": list(self.blockers),
            "capability_lease_id": self.capability_lease_id,
            "capability_policy_hash": self.capability_policy_hash,
            "capability_scope_hash": self.capability_scope_hash,
            "capability_run_id": self.capability_run_id,
            "capability_project": self.capability_project,
            "capability_tool_name": self.capability_tool_name,
            "outcome_sha256": self.outcome_sha256,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        if include_semantic_hash:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload


def build_policy_enforcement_receipt(
    *,
    receipt_id: str,
    decision: EnforcementDecision,
    pep_id: str,
    enforcement_id: str,
    enforced_at: datetime,
    capability_lease: CapabilityLease | None = None,
    capability_store: CapabilityStore | None = None,
    outcome_sha256: str | None = None,
) -> PolicyEnforcementReceipt:
    """Bind an ALLOW decision to a consumed capability, or record a denial."""
    if not decision.scope_hash:
        raise ValueError("PEP decision scope_hash is required")
    decision_sha256 = _decision_sha256(decision)
    if decision.outcome is EnforcementOutcome.ALLOW:
        if capability_lease is None:
            raise PermissionError("PEP_CAPABILITY_REQUIRED")
        if capability_store is None:
            raise PermissionError("PEP_CAPABILITY_STORE_REQUIRED")
        if (
            capability_lease.consumed_at is None
            or capability_lease.execution_id != enforcement_id
        ):
            raise PermissionError("PEP_CAPABILITY_NOT_CONSUMED")
        if (
            not capability_lease.scope_hash
            or capability_lease.scope_hash != decision.scope_hash
        ):
            raise PermissionError("PEP_CAPABILITY_SCOPE_MISMATCH")
        if capability_lease.policy_hash != decision.enforcement_profile_hash:
            raise PermissionError("PEP_CAPABILITY_POLICY_MISMATCH")
        capability_store.verify_consumed(
            capability_lease,
            execution_id=enforcement_id,
            enforced_at=enforced_at,
        )
        if outcome_sha256 is None:
            raise ValueError("PEP outcome_sha256 is required")
        return PolicyEnforcementReceipt(
            receipt_id=receipt_id,
            decision_id=decision.decision_id,
            decision_sha256=decision_sha256,
            subject_hash=decision.object_hash,
            scope_hash=decision.scope_hash,
            approval_set_hash=decision.approval_set_hash,
            pep_id=pep_id,
            enforcement_id=enforcement_id,
            enforced_at=enforced_at,
            status=PolicyEnforcementStatus.ENFORCED,
            blockers=(),
            capability_lease_id=capability_lease.lease_id,
            capability_policy_hash=capability_lease.policy_hash,
            capability_scope_hash=capability_lease.scope_hash,
            capability_run_id=capability_lease.run_id,
            capability_project=capability_lease.project,
            capability_tool_name=capability_lease.tool_name,
            outcome_sha256=outcome_sha256,
        )
    blockers = decision.blockers or decision.reason_codes
    return PolicyEnforcementReceipt(
        receipt_id=receipt_id,
        decision_id=decision.decision_id,
        decision_sha256=decision_sha256,
        subject_hash=decision.object_hash,
        scope_hash=decision.scope_hash,
        approval_set_hash=decision.approval_set_hash,
        pep_id=pep_id,
        enforcement_id=enforcement_id,
        enforced_at=enforced_at,
        status=PolicyEnforcementStatus.DENIED,
        blockers=blockers,
    )


def _decision_payload(decision: EnforcementDecision) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "outcome": decision.outcome.value,
        "evaluated_controls": tuple(
            {
                "gate": control.gate.value,
                "outcome": control.outcome.value,
                "reason_codes": control.reason_codes,
                "blockers": control.blockers,
                "details": dict(control.details),
            }
            for control in decision.evaluated_controls
        ),
        "blockers": decision.blockers,
        "reason_codes": decision.reason_codes,
        "policy_versions": decision.policy_versions,
        "object_hash": decision.object_hash,
        "evidence_hash": decision.evidence_hash,
        "authority_snapshot_hash": decision.authority_snapshot_hash,
        "enforcement_profile_version": decision.enforcement_profile_version,
        "enforcement_profile_hash": decision.enforcement_profile_hash,
        "approval_set_hash": decision.approval_set_hash,
        "blocker_snapshot_hash": decision.blocker_snapshot_hash,
        "audit_receipt_hash": decision.audit_receipt_hash,
        "consequence": decision.consequence,
        "replay_fingerprint": decision.replay_fingerprint,
        "scope_hash": decision.scope_hash,
        "execution_allowed": decision.execution_allowed,
        "promotion_status": decision.promotion_status,
        "live_eligibility_status": decision.live_eligibility_status,
    }


def _decision_sha256(decision: EnforcementDecision) -> str:
    canonical = json.dumps(
        _decision_payload(decision),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def persist_denied_enforcement_receipt(
    *,
    receipt: PolicyEnforcementReceipt,
    decision: EnforcementDecision,
    entrypoint_id: str,
    journal: CanonicalTraceJournal,
    resources: dict[str, object] | None = None,
) -> Path:
    """Persist actual rejection consumption; never attest to an allowed effect."""
    if (
        receipt.status is not PolicyEnforcementStatus.DENIED
        or decision.outcome is EnforcementOutcome.ALLOW
        or receipt.decision_sha256 != _decision_sha256(decision)
        or receipt.subject_hash != decision.object_hash
        or receipt.scope_hash != decision.scope_hash
        or receipt.decision_id != decision.decision_id
        or not entrypoint_id.strip()
    ):
        raise ValueError("DENIAL_RECEIPT_DECISION_MISMATCH")
    payload: dict[str, object] = {
        "entrypoint_id": entrypoint_id,
        "receipt": receipt.to_payload(),
        "decision": _decision_payload(decision),
        "resources": resources,
        "observation_class": "TEST_ONLY"
        if os.environ.get("PYTEST_CURRENT_TEST")
        else "OBSERVED_LOCAL_CALL",
        "producer_ref": (
            "ai4binance.governance.enforcement.engine."
            "DeterministicEnforcementEngine.evaluate_entrypoint"
        ),
        "consumer_ref": (
            "ai4binance.governance.enforcement.adapters.require_registered_entrypoint"
        ),
        "source_hashes": _enforcement_source_hashes(),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    digest = canonical_trace_sha256(payload)
    path = journal.path.parent / "enforcement_receipts" / f"{digest}.json"
    write_json_object_verified(
        path,
        payload,
        blocker="DENIAL_RECEIPT_PERSISTENCE_FAILED",
        subject_id=receipt.receipt_id,
        durable=True,
    )
    journal.append(
        CanonicalTraceRecord.create(
            trace_id=f"trace:enforcement-denied:{receipt.receipt_id}",
            trace_kind=ConsequentialTraceKind.GATE,
            subject_ref=entrypoint_id,
            subject_type="ENFORCEMENT_ENTRYPOINT",
            occurred_at=receipt.enforced_at,
            event_name="POLICY_ENFORCEMENT_DENIED",
            event_status=PolicyEnforcementStatus.DENIED.value,
            evidence_refs=(str(path.resolve()),),
            related_refs=(decision.decision_id, receipt.receipt_id),
            blockers=receipt.blockers,
            subject_sha256=digest,
        )
    )
    return path


def load_denied_enforcement_evidence(
    record: CanonicalTraceRecord,
    journal: CanonicalTraceJournal,
) -> dict[str, object]:
    """Resolve receipt bytes only from an exact canonical rejection trace."""
    if record not in journal.records():
        raise ValueError("DENIAL_RECEIPT_TRACE_INVALID")
    return _load_denial_payload(record, journal, _enforcement_source_hashes())


def load_denied_enforcement_batch(
    journal: CanonicalTraceJournal,
) -> tuple[tuple[CanonicalTraceRecord, dict[str, object]], ...]:
    """Verify all bytes and bindings; exclude intact historical source versions."""
    records = journal.records()
    sources = _enforcement_source_hashes()
    result = []
    for record in records:
        if record.event_name != "POLICY_ENFORCEMENT_DENIED":
            continue
        try:
            payload = _load_denial_payload(record, journal, sources)
        except StaleEnforcementEvidenceError:
            continue
        result.append((record, payload))
    if sources != _enforcement_source_hashes():
        raise ValueError("DENIAL_RECEIPT_SOURCE_CHANGED_DURING_READ")
    return tuple(result)


def _load_denial_payload(
    record: CanonicalTraceRecord,
    journal: CanonicalTraceJournal,
    sources: dict[str, str],
) -> dict[str, object]:
    if (
        record.event_name != "POLICY_ENFORCEMENT_DENIED"
        or record.trace_kind is not ConsequentialTraceKind.GATE
        or record.subject_type != "ENFORCEMENT_ENTRYPOINT"
        or len(record.evidence_refs) != 1
    ):
        raise ValueError("DENIAL_RECEIPT_TRACE_INVALID")
    directory = (journal.path.parent / "enforcement_receipts").resolve()
    path = Path(record.evidence_refs[0]).resolve()
    if path.parent != directory or path.stem != record.subject_sha256:
        raise ValueError("DENIAL_RECEIPT_PATH_INVALID")
    if path.stat().st_size > 65_536:
        raise ValueError("DENIAL_RECEIPT_TOO_LARGE")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or canonical_trace_sha256(payload) != record.subject_sha256
    ):
        raise ValueError("DENIAL_RECEIPT_HASH_MISMATCH")
    receipt = payload.get("receipt", {})
    decision = payload.get("decision", {})
    if (
        payload.get("entrypoint_id") != record.subject_ref
        or not isinstance(receipt, dict)
        or not isinstance(decision, dict)
        or receipt.get("status") != "DENIED"
        or receipt.get("execution_allowed") is not False
        or receipt.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        or receipt.get("decision_id") not in record.related_refs
        or receipt.get("receipt_id") not in record.related_refs
        or canonical_trace_sha256(decision) != receipt.get("decision_sha256")
        or decision.get("scope_hash") != receipt.get("scope_hash")
        or decision.get("object_hash") != receipt.get("subject_hash")
        or decision.get("decision_id") != receipt.get("decision_id")
        or decision.get("outcome") not in {"DENY", "REQUIRE_APPROVAL", "QUARANTINE"}
        or record.event_status != "DENIED"
        or payload.get("execution_allowed") is not False
        or payload.get("promotion_status") != "RESEARCH_ONLY"
        or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("DENIAL_RECEIPT_BINDING_INVALID")
    fingerprints = payload.get("source_hashes")
    if not isinstance(fingerprints, dict) or set(fingerprints) != set(sources):
        raise ValueError("DENIAL_RECEIPT_BINDING_INVALID")
    for digest in fingerprints.values():
        if not isinstance(digest, str):
            raise ValueError("DENIAL_RECEIPT_BINDING_INVALID")
        _require_sha256("source fingerprint", digest)
    if fingerprints != sources:
        raise StaleEnforcementEvidenceError("DENIAL_RECEIPT_SOURCE_STALE")
    return payload


def _enforcement_source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[4]
    paths = (
        "src/ai4binance/governance/enforcement/adapters.py",
        "src/ai4binance/governance/enforcement/engine.py",
        "src/ai4binance/governance/enforcement/contracts.py",
        "src/ai4binance/governance/enforcement/receipt.py",
        "config/governance/enforcement_inventory.yaml",
        "config/governance/enforcement_profiles.yaml",
    )
    return {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths
    }


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


__all__ = (
    "PolicyEnforcementReceipt",
    "PolicyEnforcementStatus",
    "build_policy_enforcement_receipt",
)

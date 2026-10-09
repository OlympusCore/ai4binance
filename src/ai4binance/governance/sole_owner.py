"""Prospective C3 sole-owner selection; no approval or activation writer."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from ai4binance.enterprise.contracts import (
    SoleOwnerConfirmation as SoleOwnerConfirmation,
)
from ai4binance.schema_validation import (
    validate_local_definition,
    validate_schema_definition,
)

if TYPE_CHECKING:
    from ai4binance.enterprise.contracts import ApprovalRecord

POLICY_PATH = "config/governance/sole_owner_policy.yaml"
SCHEMA_PATH = "schemas/governance/sole_owner.schema.json"
MODEL_CONTROL_PATHS = frozenset(
    {
        POLICY_PATH,
        SCHEMA_PATH,
        "src/ai4binance/governance/sole_owner.py",
        "src/ai4binance/governance/gate.py",
        "src/ai4binance/enterprise/contracts.py",
        "docs/governance/framework_core_vnext_governance.md",
        "docs/governance/instruction_core_custom_instructions.md",
    }
)
_REQUIRED_ADOPTION_PATHS = MODEL_CONTROL_PATHS
_ROLES = frozenset({"GovernanceOwner", "ConstitutionOwner"})
CORE_PATH = "docs/governance/framework_core_vnext_governance.md"
INITIAL_AMENDMENT_PATH = (
    "runtime/artifacts/governance/sole-owner/initial-amendment-context.json"
)
INITIAL_AMENDMENT_CLAUSE = "initial_owner_amendment_contract=InitialOwnerAmendment/v1"
RECONCILIATION_PATHS = frozenset(
    {
        "GEMINI.md",
        "docs/governance/instruction_core_custom_instructions.md",
        "docs/governance/policy_manifest_governance.md",
        "docs/governance/policy_organization_constitution_handbook.md",
        "docs/governance/policy_organization_foundation_operating_model.md",
        "docs/governance/policy_organization_incident_change_appendices.md",
    }
)
INITIAL_ADOPTION_PATHS = (
    MODEL_CONTROL_PATHS
    | RECONCILIATION_PATHS
    | {
        "src/ai4binance/schema_validation.py",
        "src/ai4binance/governance/framework.py",
        "docs/compliance/registry_compliance_matrix.md",
        "config/governance/governed_document_lock_manifest.json",
        "scripts/prepare_c3_human_governance_closure_request.py",
        "tests/test_sole_owner_governance.py",
        "config/governance/governance_enforcement_fabric.yaml",
        "docs/architecture/framework_architecture_overview.md",
        "docs/contracts/interface_contract_cli_command.md",
        "tests/test_artifact_hygiene_scripts.py",
    }
)
INITIAL_DECISION_FIELDS = (
    "decision_id",
    "owner_person_id",
    "owner_principal_id",
    "repository_root",
    "phase",
    "baseline_commit",
    "governing_core_version",
    "governing_core_sha256",
    "subject_sha256",
    "patch_sha256",
    "candidate_files",
    "protected_review",
    "issued_at_utc",
    "not_before_utc",
    "expires_at_utc",
    "scope",
    "excluded_effects",
    "quality_gate_evidence_sha256",
    "governance_gate_evidence_sha256",
    "evidence_hash",
    "authority_family_sha256",
    "lifecycle_definition_sha256",
)
INITIAL_EVIDENCE_FIELDS = INITIAL_DECISION_FIELDS[-5:]


def initial_decision_binding(value: dict[str, object]) -> str:
    """Bind the primary human wording to the entire proposed decision scope."""
    return _sha(
        json.dumps(
            {key: value[key] for key in INITIAL_DECISION_FIELDS},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


@dataclass(frozen=True, slots=True)
class InitialOwnerAmendment:
    """A conditional founding decision, never proof of its own operative rule."""

    owner_person_id: str
    owner_principal_id: str
    phase: str
    subject_id: str
    source_ref: str
    issued_at: datetime
    expires_at: datetime
    evidence_bindings: tuple[tuple[str, str], ...]

    def record_blockers(self, record: ApprovalRecord) -> tuple[str, ...]:
        from ai4binance.enterprise.contracts import ApprovalStatus

        role = "ConstitutionOwner" if self.phase == "ADOPTION" else "GovernanceOwner"
        if (
            record.principal_id != self.owner_principal_id
            or record.approver_id != self.owner_principal_id
            or record.approver_role != role
            or record.status is not ApprovalStatus.APPROVED_FOR_IMPLEMENTATION
            or record.subject_sha256 != self.subject_id
            or self.source_ref not in record.evidence_refs
            or record.research_confirmation is not None
            or record.sole_owner_confirmation is not None
            or record.revoked_at is not None
            or record.approved_at is None
            or record.expires_at is None
            or not self.issued_at <= record.approved_at < record.expires_at
            or record.expires_at > self.expires_at
            or any(
                getattr(record, key) != digest for key, digest in self.evidence_bindings
            )
        ):
            return ("INITIAL_OWNER_DECISION_BINDING_INVALID",)
        return ()


def verify_initial_owner_amendment(
    root: Path,
    reference: dict[str, str],
    *,
    base: str,
    subject_id: str,
    patch_sha256: str,
    candidate_files: dict[str, str],
    phase: str,
    now: datetime,
    accepted: str | None = None,
) -> InitialOwnerAmendment:
    """Reuse lock-review bindings; require a preceding operative Core clause.

    No candidate, fixture, source hash, or custody assertion creates that clause.
    Any preceding baseline without the recognized founding contract is rejected.
    Candidate bytes and successful fixtures cannot create that recognition.
    """
    from ai4binance.governance import document_lock_review as review

    root = root.resolve(strict=True)
    value = review._decode(review._bound_bytes(root, reference))
    validate_local_definition(root / SCHEMA_PATH, "initial_amendment", value)
    # Read the preceding accepted rule, never the proposed output at HEAD.
    governing = _git(root, "show", f"{base}:{CORE_PATH}")
    if INITIAL_AMENDMENT_CLAUSE.encode() not in governing.splitlines():
        raise ValueError("SOLE_OWNER_FOUNDING_AUTHORITY_NOT_OPERATIVE")
    if (
        value["repository_root"] != root.as_posix()
        or value["baseline_commit"] != base
        or value["governing_core_sha256"] != _sha(governing)
        or f"version: {value['governing_core_version']}".encode()
        not in governing.splitlines()
        or value["subject_sha256"] != subject_id
        or value["patch_sha256"] != patch_sha256
        or value["candidate_files"] != candidate_files
        or value["phase"] != phase
    ):
        raise ValueError("SOLE_OWNER_INITIAL_AMENDMENT_SUBJECT_DRIFT")
    review._period(value, now)
    issued, expires = (
        _time(str(value[k])) for k in ("issued_at_utc", "expires_at_utc")
    )
    if expires - issued > timedelta(hours=24) or value["revoked_at_utc"] is not None:
        raise ValueError("SOLE_OWNER_INITIAL_AMENDMENT_REVOKED_OR_UNBOUNDED")
    _verify_initial_source(root, value, subject_id, now, issued)
    _verify_initial_scope(root, value, candidate_files, phase)
    _verify_initial_outputs(root, candidate_files, accepted)
    _verify_initial_protected_review(root, value, governing, phase, accepted)
    return InitialOwnerAmendment(
        str(value["owner_person_id"]),
        str(value["owner_principal_id"]),
        phase,
        subject_id,
        str(value["decision_source"]["path"]),
        issued,
        expires,
        tuple((key, str(value[key])) for key in INITIAL_EVIDENCE_FIELDS),
    )


def _verify_initial_source(
    root: Path,
    value: dict[str, Any],
    subject_id: str,
    now: datetime,
    issued: datetime,
) -> None:
    from ai4binance.governance import document_lock_review as review

    source = review._decode(review._bound_bytes(root, value["decision_source"]))
    validate_local_definition(root / SCHEMA_PATH, "initial_owner_decision", source)
    if (
        any(
            source.get(k) != value.get(k)
            for k in (
                "owner_person_id",
                "owner_principal_id",
                "subject_sha256",
                "phase",
                "baseline_commit",
                "patch_sha256",
                "decision_id",
            )
        )
        or source["decision"] != "ADOPT_EXACT_INITIAL_OWNER_AMENDMENT"
    ):
        raise ValueError("SOLE_OWNER_INITIAL_OWNER_SOURCE_MISMATCH")
    primary = review._bound_bytes(root, source["primary_owner_source"])
    binding = initial_decision_binding(value)
    if (
        source["decision_binding_sha256"] != binding
        or f"INITIAL_OWNER_DECISION {binding}".encode() not in primary.splitlines()
    ):
        raise ValueError("SOLE_OWNER_INITIAL_PRIMARY_DECISION_BINDING")
    custody = value["custody"]
    checked = _time(custody["checked_at_utc"])
    if (
        not primary
        or custody["custodian_person_id"] != value["owner_person_id"]
        or custody["primary_owner_source"] != source["primary_owner_source"]
        or not issued <= checked <= now < checked + timedelta(hours=24)
    ):
        raise ValueError("SOLE_OWNER_INITIAL_OWNER_CUSTODY_INVALID")
    # This validates an operator's custody assertion; it does not authenticate
    # the human channel. A real decision must be captured outside the candidate.
    revocations = review._decode(review._bound_bytes(root, value["revocations"]))
    validate_local_definition(review.SCHEMA, "revocations", revocations)
    review._period(revocations, now)
    if (
        revocations["repository_root"] != root.as_posix()
        or not checked <= _time(revocations["issued_at_utc"]) <= now
        or value["decision_id"] in revocations["revoked_decision_ids"]
        or value["owner_person_id"] in revocations["revoked_owner_ids"]
        or subject_id in revocations["revoked_subjects"]
    ):
        raise ValueError("SOLE_OWNER_INITIAL_REVOCATION_OR_FRESHNESS")


def _verify_initial_scope(
    root: Path,
    value: dict[str, Any],
    candidate_files: dict[str, str],
    phase: str,
) -> None:
    from ai4binance.governance import document_lock_review as review

    base = str(value["baseline_commit"])
    if phase == "ADOPTION":
        if (
            not _REQUIRED_ADOPTION_PATHS
            <= candidate_files.keys()
            <= INITIAL_ADOPTION_PATHS
        ):
            raise ValueError("SOLE_OWNER_INITIAL_ADOPTION_SCOPE_INELIGIBLE")
    elif phase == "ACTIVATION":
        if set(candidate_files) != {POLICY_PATH}:
            raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_SCOPE_INELIGIBLE")
        prior = value.get("adoption_completion")
        if not isinstance(prior, dict):
            raise ValueError("SOLE_OWNER_INITIAL_ADOPTION_COMPLETION_REQUIRED")
        receipt = review._decode(review._bound_bytes(root, prior))
        validate_local_definition(root / SCHEMA_PATH, "initial_completion", receipt)
        if (
            receipt["accepted_commit"] != base
            or receipt["owner_principal_id"] != value["owner_principal_id"]
            or receipt["phase"] != "ADOPTION"
            or receipt["protected_review"] != value["protected_review"]
        ):
            raise ValueError("SOLE_OWNER_INITIAL_ADOPTION_COMPLETION_DRIFT")
        preceding = verify_initial_owner_amendment(
            root,
            receipt["amendment"],
            base=receipt["baseline_commit"],
            subject_id=receipt["subject_sha256"],
            patch_sha256=receipt["patch_sha256"],
            candidate_files=receipt["candidate_files"],
            phase="ADOPTION",
            now=_time(receipt["completed_at_utc"]),
            accepted=base,
        )
        if preceding.owner_principal_id != value["owner_principal_id"]:
            raise ValueError("SOLE_OWNER_INITIAL_OWNER_CHANGED")
    else:
        raise ValueError("SOLE_OWNER_INITIAL_PHASE_INVALID")


def _verify_initial_outputs(
    root: Path,
    candidate_files: dict[str, str],
    accepted: str | None,
) -> None:
    for path, digest in candidate_files.items():
        observed = (
            _git(root, "show", f"{accepted}:{path}")
            if accepted
            else (root / path).read_bytes()
        )
        if _sha(observed) != digest:
            raise ValueError("SOLE_OWNER_INITIAL_OUTPUT_DRIFT")


def _verify_initial_protected_review(
    root: Path,
    value: dict[str, Any],
    governing: bytes,
    phase: str,
    accepted: str | None,
) -> None:
    from ai4binance.governance import document_lock_review as review

    reviewed = review._decode(review._bound_bytes(root, value["protected_review"]))
    validate_local_definition(root / SCHEMA_PATH, "protected_review", reviewed)
    rows = {row["path"]: row for row in reviewed["documents"]}
    if (
        len(rows) != len(reviewed["documents"])
        or not RECONCILIATION_PATHS <= rows.keys()
        or not rows.keys()
        <= RECONCILIATION_PATHS
        | {CORE_PATH, "docs/compliance/registry_compliance_matrix.md"}
    ):
        raise ValueError("SOLE_OWNER_INITIAL_UNREVIEWED_DOCUMENTS")
    for path, row in rows.items():
        observed = (
            _git(root, "show", f"{accepted}:{path}")
            if accepted
            else (root / path).read_bytes()
        )
        if (
            _sha(observed) != row["sha256"]
            or not row["reviewed_current_content"]
            or row["historical_integrity_proved"]
        ):
            raise ValueError("SOLE_OWNER_INITIAL_PROTECTED_REVIEW_DRIFT")
        review._bound_bytes(root, row["content_review"])
    review._bound_bytes(root, reviewed["superior_authority"])
    if phase == "ADOPTION" and reviewed["superior_authority"]["sha256"] != _sha(
        governing
    ):
        raise ValueError("SOLE_OWNER_INITIAL_REVIEW_AUTHORITY_DRIFT")
    if phase == "ADOPTION":
        review._documents(root, reviewed, artifacts_root=root)


def load_initial_owner_amendment(
    root: Path,
    *,
    base: str,
    subject_id: str,
    patch_sha256: str,
    candidate_files: dict[str, str],
    now: datetime,
) -> InitialOwnerAmendment | None:
    path = root / INITIAL_AMENDMENT_PATH
    if not path.is_file():
        return None
    record = _object(path)
    return verify_initial_owner_amendment(
        root,
        {"path": INITIAL_AMENDMENT_PATH, "sha256": _sha(path.read_bytes())},
        base=base,
        subject_id=subject_id,
        patch_sha256=patch_sha256,
        candidate_files=candidate_files,
        phase=str(record.get("phase", "")),
        now=now,
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bound_path(root: Path, relative: str, *, quality_run: bool = False) -> Path:
    prefix = (
        "runtime/artifacts/quality/gate/runs/"
        if quality_run
        else "runtime/artifacts/governance/"
    )
    if not relative.startswith(prefix):
        raise ValueError("SOLE_OWNER_EVIDENCE_LOCATION")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError("SOLE_OWNER_EVIDENCE_PATH")
    return target


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("SOLE_OWNER_RECORD_OBJECT_REQUIRED")
    return cast("dict[str, object]", value)


def _git(root: Path, *args: str) -> bytes:
    reader = importlib.import_module("ai4binance.governance.document_lock_review")

    # Reuse the canonical bounded Git reader instead of a second process runner.
    try:
        return cast("bytes", reader._git_bytes(root, *args))
    except reader.subprocess.CalledProcessError as exc:
        raise ValueError("SOLE_OWNER_ADOPTION_GIT_BINDING") from exc
    except ValueError as exc:
        raise ValueError("SOLE_OWNER_GIT_UNAVAILABLE") from exc


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("SOLE_OWNER_TIMEZONE_REQUIRED")
    return parsed


def parse_confirmation(value: object) -> SoleOwnerConfirmation | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(
        SoleOwnerConfirmation.__dataclass_fields__
    ):
        raise ValueError("SOLE_OWNER_CONFIRMATION_INVALID")
    return SoleOwnerConfirmation(**value)


@dataclass(frozen=True, slots=True)
class SoleOwnerPolicy:
    owner_person_id: str
    owner_principal_id: str
    roles: frozenset[str]
    policy_sha256: str
    activation_sha256: str
    issued_at: datetime

    def check_scope(self, paths: tuple[str, ...], change_class: str) -> None:
        if change_class != "C3_GOVERNED" or not paths:
            raise ValueError("SOLE_OWNER_SCOPE_INELIGIBLE")

    def record_blockers(
        self,
        record: ApprovalRecord,
        paths: tuple[str, ...],
    ) -> tuple[str, ...]:
        from ai4binance.enterprise.contracts import ApprovalStatus

        blockers: list[str] = []
        expected = SoleOwnerConfirmation(
            self.owner_person_id,
            self.owner_principal_id,
            self.policy_sha256,
            self.activation_sha256,
        )
        if record.sole_owner_confirmation != expected:
            blockers.append("SOLE_OWNER_CONFIRMATION_MISMATCH")
        if record.status is not ApprovalStatus.APPROVED_FOR_IMPLEMENTATION:
            blockers.append("SOLE_OWNER_IMPLEMENTATION_APPROVAL_REQUIRED")
        if (
            record.principal_id != self.owner_principal_id
            or record.approver_id != self.owner_principal_id
            or record.approver_role not in self.roles
        ):
            blockers.append("SOLE_OWNER_PRINCIPAL_OR_ROLE_MISMATCH")
        required_role = (
            "ConstitutionOwner"
            if any(path.startswith("docs/governance/") for path in paths)
            else "GovernanceOwner"
        )
        if record.approver_role != required_role:
            blockers.append("SOLE_OWNER_REQUIRED_ROLE_MISSING")
        if record.approved_at is None or record.expires_at is None:
            blockers.append("SOLE_OWNER_DECISION_PERIOD_REQUIRED")
        elif (
            record.approved_at < self.issued_at
            or record.approved_at > datetime.now(UTC)
            or record.expires_at <= record.approved_at
        ):
            blockers.append("SOLE_OWNER_DECISION_PERIOD_MISMATCH")
        return tuple(blockers)


def _verify_adoption_files(
    root: Path, activation: dict[str, object]
) -> tuple[str, str, dict[str, str]]:
    base = str(activation["adoption_base_commit"])
    adopted = str(activation["adoption_commit"])
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    _git(root, "merge-base", "--is-ancestor", base, adopted)
    _git(root, "merge-base", "--is-ancestor", adopted, head)
    changed = set(
        _git(root, "diff", "--name-only", "--no-renames", base, adopted)
        .decode("utf-8")
        .splitlines()
    )
    files = cast("dict[str, str]", activation["candidate_files"])
    if changed != set(files) or not _REQUIRED_ADOPTION_PATHS.issubset(changed):
        raise ValueError("SOLE_OWNER_ADOPTION_SCOPE_DRIFT")
    for path, expected in files.items():
        if path.startswith("/") or ".." in Path(path).parts or "\\" in path:
            raise ValueError("SOLE_OWNER_ADOPTION_PATH_INVALID")
        if _sha(_git(root, "show", f"{adopted}:{path}")) != expected:
            raise ValueError("SOLE_OWNER_ADOPTION_BYTES_DRIFT")
    adopted_policy = yaml.safe_load(_git(root, "show", f"{adopted}:{POLICY_PATH}"))
    if (
        not isinstance(adopted_policy, dict)
        or adopted_policy.get("activation_status") != "INACTIVE"
    ):
        raise ValueError("SOLE_OWNER_ADOPTION_MUST_BE_INACTIVE")
    return base, adopted, files


def _verify_transition_participants(
    records: tuple[ApprovalRecord, ...], count: int, roles: frozenset[str] | set[str]
) -> None:
    if len(records) != count:
        raise ValueError("SOLE_OWNER_TRANSITION_REQUIRES_TWO_APPROVALS")
    if len({record.principal_id for record in records}) != count:
        raise ValueError("SOLE_OWNER_TRANSITION_REQUIRES_TWO_PEOPLE")
    if {record.approver_role for record in records} != roles:
        raise ValueError("SOLE_OWNER_TRANSITION_ROLES")


def _verify_adoption(root: Path, activation: dict[str, object], now: datetime) -> None:
    from ai4binance.enterprise.contracts import ApprovalStatus
    from ai4binance.governance.framework import ChangeApprovalClass

    approval_consumer = importlib.import_module("ai4binance.governance.gate")

    base, adopted, files = _verify_adoption_files(root, activation)
    patch = _bound_path(root, str(activation["adoption_patch_ref"]))
    if _sha(patch.read_bytes()) != activation["adoption_patch_sha256"]:
        raise ValueError("SOLE_OWNER_ADOPTION_PATCH_DRIFT")
    frozen_path = _bound_path(
        root, str(activation["frozen_gate_ref"]), quality_run=True
    )
    if _sha(frozen_path.read_bytes()) != activation["frozen_gate_sha256"]:
        raise ValueError("SOLE_OWNER_FROZEN_GATE_DRIFT")
    frozen = _object(frozen_path)
    approval_consumer.verify_historical_committed_review(
        root,
        frozen,
        base=base,
        accepted=adopted,
        patch_sha256=str(activation["adoption_patch_sha256"]),
    )
    verification = cast("dict[str, object]", frozen.get("approval_verification"))
    subject = cast("dict[str, object]", frozen.get("subject_digest"))
    amendment_ref = activation.get("initial_amendment")
    initial_owner = (
        verify_initial_owner_amendment(
            root,
            cast("dict[str, str]", amendment_ref),
            base=base,
            subject_id=str(activation["adoption_subject_id"]),
            patch_sha256=str(activation["adoption_patch_sha256"]),
            candidate_files=files,
            phase="ADOPTION",
            now=now,
            accepted=adopted,
        )
        if isinstance(amendment_ref, dict)
        else None
    )
    count = 1 if initial_owner is not None else 2
    profile = "INITIAL_OWNER_AMENDMENT" if initial_owner is not None else "LEGACY_C3"
    if (
        frozen.get("status") != "RUNNING_WITH_BLOCKERS"
        or frozen.get("blockers") != ["APPROVAL_REQUIRED"]
        or verification.get("required_approval_count") != count
        or verification.get("approval_profile") != profile
        or set(
            cast(
                "list[str]",
                cast("dict[str, object]", frozen.get("change_set")).get(
                    "changed_paths"
                ),
            )
        )
        != set(files)
        or cast("dict[str, object]", frozen.get("change_set")).get("git_commit")
        != adopted
        or subject.get("subject_id") != activation["adoption_subject_id"]
        or subject.get("change_set_sha256") != activation["adoption_scope_hash"]
        or frozen.get("gate_evidence_sha256")
        != activation["adoption_governance_sha256"]
        or cast("dict[str, object]", frozen.get("deterministic_quality_gate")).get(
            "gate_evidence_sha256"
        )
        != activation["adoption_quality_sha256"]
        or any(
            cast("dict[str, object]", frozen.get(key)).get("status") != "PASS"
            for key in (
                "deterministic_quality_gate",
                "repository_hygiene",
                "constitution_sync",
                "repository_conformance",
                "repository_validator_gate",
            )
        )
    ):
        raise ValueError("SOLE_OWNER_FROZEN_GATE_NOT_APPROVAL_ONLY")
    approvals = _bound_path(root, str(activation["approval_records_ref"]))
    if _sha(approvals.read_bytes()) != activation["approval_records_sha256"]:
        raise ValueError("SOLE_OWNER_TRANSITION_APPROVAL_DRIFT")
    records = approval_consumer.load_approval_records(approvals)
    roles = {"ConstitutionOwner"} if initial_owner is not None else _ROLES
    _verify_transition_participants(records, count, roles)
    for record in records:
        if initial_owner is not None and initial_owner.record_blockers(record):
            raise ValueError("SOLE_OWNER_INITIAL_DECISION_INVALID")
        if (
            record.status is not ApprovalStatus.APPROVED_FOR_IMPLEMENTATION
            or record.principal_id != record.approver_id
            or record.subject_ref != activation["frozen_gate_ref"]
            or record.change_class is not ChangeApprovalClass.C3_GOVERNED
            or record.subject_sha256 != activation["adoption_subject_id"]
            or record.scope_hash != activation["adoption_scope_hash"]
            or record.quality_gate_evidence_sha256
            != activation["adoption_quality_sha256"]
            or record.governance_gate_evidence_sha256
            != activation["adoption_governance_sha256"]
            or record.evidence_hash != activation["adoption_evidence_hash"]
            or record.authority_family_sha256
            != activation["adoption_authority_family_sha256"]
            or record.lifecycle_definition_sha256
            != activation["adoption_lifecycle_sha256"]
            or record.research_confirmation is not None
            or record.sole_owner_confirmation is not None
            or record.approved_at is None
            or record.approved_at > now
            or record.expires_at is None
            or record.expires_at <= now
            or record.revoked_at is not None
        ):
            raise ValueError("SOLE_OWNER_TRANSITION_APPROVAL_INVALID")


def _verify_initial_activation_files(
    root: Path,
    activation: dict[str, object],
    receipt: dict[str, object],
    policy_bytes: bytes,
    policy_commit: str,
) -> tuple[str, str, dict[str, str]]:
    base = str(receipt["base_commit"])
    accepted = str(receipt["accepted_commit"])
    _git(root, "merge-base", "--is-ancestor", str(activation["adoption_commit"]), base)
    baseline_policy = yaml.safe_load(_git(root, "show", f"{base}:{POLICY_PATH}"))
    if baseline_policy["activation_status"] != "INACTIVE":
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_BASELINE")
    _git(root, "merge-base", "--is-ancestor", base, accepted)
    _git(root, "merge-base", "--is-ancestor", accepted, policy_commit)
    paths = cast("dict[str, str]", receipt["candidate_files"])
    changed = set(
        _git(root, "diff", "--name-only", "--no-renames", base, accepted)
        .decode("utf-8")
        .splitlines()
    )
    if changed != set(paths) or POLICY_PATH not in paths:
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_SCOPE_DRIFT")
    for path, expected in paths.items():
        if path.startswith("/") or ".." in Path(path).parts or "\\" in path:
            raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_PATH_INVALID")
        if _sha(_git(root, "show", f"{accepted}:{path}")) != expected:
            raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_BYTES_DRIFT")
    if paths[POLICY_PATH] != _sha(policy_bytes):
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_POLICY_DRIFT")
    return base, accepted, paths


def _verify_initial_activation(
    root: Path,
    activation: dict[str, object],
    policy_bytes: bytes,
    policy_commit: str | None,
    now: datetime,
) -> None:
    """Bind the first ACTIVE configuration to its separate exact owner decision."""
    from ai4binance.enterprise.contracts import ApprovalStatus
    from ai4binance.governance.framework import ChangeApprovalClass

    approval_consumer = importlib.import_module("ai4binance.governance.gate")

    receipt = activation.get("activation_acceptance")
    if not isinstance(receipt, dict) or policy_commit is None:
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_ACCEPTANCE_REQUIRED")
    base, accepted, paths = _verify_initial_activation_files(
        root, activation, receipt, policy_bytes, policy_commit
    )
    frozen_path = _bound_path(root, str(receipt["frozen_gate_ref"]), quality_run=True)
    if _sha(frozen_path.read_bytes()) != receipt["frozen_gate_sha256"]:
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_GATE_DRIFT")
    frozen = _object(frozen_path)
    verification = cast("dict[str, object]", frozen.get("approval_verification"))
    subject = cast("dict[str, object]", frozen.get("subject_digest"))
    change = cast("dict[str, object]", frozen.get("change_set"))
    approval_consumer.verify_historical_committed_review(
        root,
        frozen,
        base=base,
        accepted=accepted,
        patch_sha256=str(change.get("review_patch_sha256", ""))
        if isinstance(change, dict)
        else "",
    )
    amendment_ref = receipt.get("initial_amendment")
    initial_owner = (
        verify_initial_owner_amendment(
            root,
            cast("dict[str, str]", amendment_ref),
            base=base,
            subject_id=str(receipt["subject_id"]),
            patch_sha256=str(change.get("review_patch_sha256", "")),
            candidate_files=paths,
            phase="ACTIVATION",
            now=now,
            accepted=accepted,
        )
        if isinstance(amendment_ref, dict)
        else None
    )
    count = 1 if initial_owner is not None else 2
    profile = "INITIAL_OWNER_AMENDMENT" if initial_owner is not None else "LEGACY_C3"
    if (
        frozen.get("status") != "RUNNING_WITH_BLOCKERS"
        or frozen.get("blockers") != ["APPROVAL_REQUIRED"]
        or verification.get("required_approval_count") != count
        or verification.get("approval_profile") != profile
        or change.get("review_base_commit") != base
        or change.get("review_head_commit") != accepted
        or set(cast("list[str]", change.get("changed_paths"))) != set(paths)
        or subject.get("subject_id") != receipt["subject_id"]
        or subject.get("change_set_sha256") != receipt["scope_hash"]
        or frozen.get("gate_evidence_sha256") != receipt["governance_sha256"]
        or cast("dict[str, object]", frozen.get("deterministic_quality_gate")).get(
            "gate_evidence_sha256"
        )
        != receipt["quality_sha256"]
        or any(
            cast("dict[str, object]", frozen.get(key)).get("status") != "PASS"
            for key in (
                "deterministic_quality_gate",
                "repository_hygiene",
                "constitution_sync",
                "repository_conformance",
                "repository_validator_gate",
            )
        )
    ):
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_GATE_NOT_APPROVAL_ONLY")
    approval_path = _bound_path(root, str(receipt["approval_records_ref"]))
    if _sha(approval_path.read_bytes()) != receipt["approval_records_sha256"]:
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_APPROVAL_DRIFT")
    records = approval_consumer.load_approval_records(approval_path)
    if (
        len(records) != count
        or len({record.principal_id for record in records}) != count
        or {record.approver_role for record in records}
        != ({"GovernanceOwner"} if initial_owner is not None else _ROLES)
        or str(activation["owner_principal_id"])
        not in {record.principal_id for record in records}
    ):
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_TWO_PEOPLE_REQUIRED")
    for record in records:
        if initial_owner is not None and initial_owner.record_blockers(record):
            raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_DECISION_INVALID")
        if (
            record.status is not ApprovalStatus.APPROVED_FOR_IMPLEMENTATION
            or record.principal_id != record.approver_id
            or record.subject_ref != receipt["frozen_gate_ref"]
            or record.change_class is not ChangeApprovalClass.C3_GOVERNED
            or record.subject_sha256 != receipt["subject_id"]
            or record.scope_hash != receipt["scope_hash"]
            or record.quality_gate_evidence_sha256 != receipt["quality_sha256"]
            or record.governance_gate_evidence_sha256 != receipt["governance_sha256"]
            or record.evidence_hash != receipt["evidence_hash"]
            or record.authority_family_sha256 != receipt["authority_family_sha256"]
            or record.lifecycle_definition_sha256
            != receipt["lifecycle_definition_sha256"]
            or record.sole_owner_confirmation is not None
            or record.approved_at is None
            or record.approved_at > now
            or record.approved_at > _time(str(activation["issued_at_utc"]))
            or record.expires_at is None
            or record.expires_at <= now
            or record.revoked_at is not None
        ):
            raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_APPROVAL_INVALID")


def _verify_successor(
    root: Path,
    activation: dict[str, object],
    policy_bytes: bytes,
    policy_commit: str | None,
    now: datetime,
) -> None:
    """Require an accepted predecessor-policy review for changed policy bytes."""

    original = cast("dict[str, str]", activation["candidate_files"])[POLICY_PATH]
    if _sha(policy_bytes) == original:
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_ACCEPTANCE_REQUIRED")
    initial = activation.get("activation_acceptance")
    if not isinstance(initial, dict):
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_ACCEPTANCE_REQUIRED")
    initial_commit = str(initial["accepted_commit"])
    initial_bytes = _git(root, "show", f"{initial_commit}:{POLICY_PATH}")
    initial_time = _time(str(initial.get("accepted_at_utc", "")))
    if not _time(str(activation["adoption_accepted_at_utc"])) <= initial_time <= now:
        raise ValueError("SOLE_OWNER_INITIAL_ACTIVATION_TIME_INVALID")
    _verify_initial_activation(
        root, activation, initial_bytes, policy_commit, initial_time
    )
    if activation.get("successor_acceptance") is None and _sha(policy_bytes) == _sha(
        initial_bytes
    ):
        return
    _verify_successor_receipt(root, activation, policy_bytes, policy_commit, now)


def _verify_successor_files(
    root: Path,
    successor: dict[str, object],
    policy_bytes: bytes,
    policy_commit: str,
) -> tuple[str, str, dict[str, str]]:
    base = str(successor["base_commit"])
    accepted = str(successor["accepted_commit"])
    _git(root, "merge-base", "--is-ancestor", base, accepted)
    _git(root, "merge-base", "--is-ancestor", accepted, policy_commit)
    paths = cast("dict[str, str]", successor["candidate_files"])
    changed = set(
        _git(root, "diff", "--name-only", "--no-renames", base, accepted)
        .decode("utf-8")
        .splitlines()
    )
    if changed != set(paths) or POLICY_PATH not in paths:
        raise ValueError("SOLE_OWNER_SUCCESSOR_SCOPE_DRIFT")
    for path, expected in paths.items():
        if path.startswith("/") or ".." in Path(path).parts or "\\" in path:
            raise ValueError("SOLE_OWNER_SUCCESSOR_PATH_INVALID")
        if _sha(_git(root, "show", f"{accepted}:{path}")) != expected:
            raise ValueError("SOLE_OWNER_SUCCESSOR_BYTES_DRIFT")
    if paths[POLICY_PATH] != _sha(policy_bytes):
        raise ValueError("SOLE_OWNER_SUCCESSOR_POLICY_DRIFT")
    return base, accepted, paths


def _verify_successor_receipt(
    root: Path,
    activation: dict[str, object],
    policy_bytes: bytes,
    policy_commit: str | None,
    now: datetime,
) -> None:
    from ai4binance.enterprise.contracts import ApprovalStatus
    from ai4binance.governance.framework import ChangeApprovalClass

    approval_consumer = importlib.import_module("ai4binance.governance.gate")

    successor = activation.get("successor_acceptance")
    if not isinstance(successor, dict) or policy_commit is None:
        raise ValueError("SOLE_OWNER_SUCCESSOR_ACCEPTANCE_REQUIRED")
    base, accepted, paths = _verify_successor_files(
        root, successor, policy_bytes, policy_commit
    )
    frozen_path = _bound_path(root, str(successor["frozen_gate_ref"]), quality_run=True)
    if _sha(frozen_path.read_bytes()) != successor["frozen_gate_sha256"]:
        raise ValueError("SOLE_OWNER_SUCCESSOR_GATE_DRIFT")
    frozen = _object(frozen_path)
    verification = cast("dict[str, object]", frozen.get("approval_verification"))
    subject = cast("dict[str, object]", frozen.get("subject_digest"))
    change = cast("dict[str, object]", frozen.get("change_set"))
    approval_consumer.verify_historical_committed_review(
        root,
        frozen,
        base=base,
        accepted=accepted,
        patch_sha256=str(change.get("review_patch_sha256", ""))
        if isinstance(change, dict)
        else "",
    )
    if (
        frozen.get("status") != "RUNNING_WITH_BLOCKERS"
        or frozen.get("blockers") != ["APPROVAL_REQUIRED"]
        or verification.get("required_approval_count") != 1
        or verification.get("approval_profile") != "SOLE_HUMAN_OWNER"
        or change.get("review_base_commit") != base
        or change.get("review_head_commit") != accepted
        or set(cast("list[str]", change.get("changed_paths"))) != set(paths)
        or subject.get("subject_id") != successor["subject_id"]
        or subject.get("change_set_sha256") != successor["scope_hash"]
        or frozen.get("gate_evidence_sha256") != successor["governance_sha256"]
        or cast("dict[str, object]", frozen.get("deterministic_quality_gate")).get(
            "gate_evidence_sha256"
        )
        != successor["quality_sha256"]
        or any(
            cast("dict[str, object]", frozen.get(key)).get("status") != "PASS"
            for key in (
                "deterministic_quality_gate",
                "repository_hygiene",
                "constitution_sync",
                "repository_conformance",
                "repository_validator_gate",
            )
        )
    ):
        raise ValueError("SOLE_OWNER_SUCCESSOR_GATE_NOT_APPROVAL_ONLY")
    approvals = _bound_path(root, str(successor["approval_records_ref"]))
    if _sha(approvals.read_bytes()) != successor["approval_records_sha256"]:
        raise ValueError("SOLE_OWNER_SUCCESSOR_APPROVAL_DRIFT")
    records = approval_consumer.load_approval_records(approvals)
    if len(records) != 1:
        raise ValueError("SOLE_OWNER_SUCCESSOR_REQUIRES_ONE_OWNER")
    record = records[0]
    if record.approved_at is None:
        raise ValueError("SOLE_OWNER_SUCCESSOR_APPROVAL_TIME")
    prior = load_sole_owner_policy(root, now=record.approved_at, policy_commit=base)
    if prior is None:
        raise ValueError("SOLE_OWNER_PREDECESSOR_INACTIVE")
    if (
        record.status is not ApprovalStatus.APPROVED_FOR_IMPLEMENTATION
        or prior.record_blockers(record, tuple(paths))
        or record.approver_id != prior.owner_principal_id
        or record.principal_id != prior.owner_principal_id
        or record.sole_owner_confirmation
        != SoleOwnerConfirmation(
            prior.owner_person_id,
            prior.owner_principal_id,
            prior.policy_sha256,
            prior.activation_sha256,
        )
        or record.change_class is not ChangeApprovalClass.C3_GOVERNED
        or record.subject_ref != successor["frozen_gate_ref"]
        or record.subject_sha256 != successor["subject_id"]
        or record.scope_hash != successor["scope_hash"]
        or record.quality_gate_evidence_sha256 != successor["quality_sha256"]
        or record.governance_gate_evidence_sha256 != successor["governance_sha256"]
        or record.evidence_hash != successor["evidence_hash"]
        or record.authority_family_sha256 != successor["authority_family_sha256"]
        or record.lifecycle_definition_sha256
        != successor["lifecycle_definition_sha256"]
        or record.approved_at > now
        or record.approved_at > _time(str(activation["issued_at_utc"]))
        or record.expires_at is None
        or record.expires_at <= now
        or record.revoked_at is not None
    ):
        raise ValueError("SOLE_OWNER_SUCCESSOR_APPROVAL_INVALID")


def _read_accepted_policy(
    root: Path,
    policy_commit: str,
) -> tuple[bytes, dict[str, Any], dict[str, Any]] | None:
    if len(policy_commit) != 40 or any(
        c not in "0123456789abcdef" for c in policy_commit
    ):
        raise ValueError("SOLE_OWNER_BASELINE_COMMIT_INVALID")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    _git(root, "merge-base", "--is-ancestor", policy_commit, head)
    listed = _git(root, "ls-tree", "--name-only", policy_commit, "--", POLICY_PATH)
    if listed.decode().strip() != POLICY_PATH:
        return None
    policy_bytes = _git(root, "show", f"{policy_commit}:{POLICY_PATH}")
    schema_bytes = _git(root, "show", f"{policy_commit}:{SCHEMA_PATH}")
    raw = yaml.safe_load(policy_bytes.decode("utf-8-sig"))
    schema = json.loads(schema_bytes.decode("utf-8-sig"))
    validate_schema_definition(schema, "policy", raw, source_path=root / SCHEMA_PATH)
    return policy_bytes, raw, schema


def load_sole_owner_policy(
    root: Path, *, now: datetime | None = None, policy_commit: str | None = None
) -> SoleOwnerPolicy | None:
    """Select the accepted baseline policy, never the proposed successor bytes."""
    root = root.resolve(strict=True)
    path = root / POLICY_PATH
    if not path.exists() and not (root / ".git").exists():
        # A nested non-repository fixture must not inherit a parent's Git authority.
        # No registered model means the stricter legacy C3 requirement remains.
        return None
    if policy_commit is not None:
        selected = _read_accepted_policy(root, policy_commit)
        if selected is None:
            return None
        policy_bytes, raw, schema = selected
    else:
        if not path.is_file():
            return None
        policy_bytes = path.read_bytes()
        raw = yaml.safe_load(policy_bytes.decode("utf-8-sig"))
        validate_local_definition(root / SCHEMA_PATH, "policy", raw)
    if raw["activation_status"] == "INACTIVE":
        return None
    instant = now or datetime.now(UTC)
    activation_path = _bound_path(root, str(raw["activation_record"]))
    activation = _object(activation_path)
    if policy_commit is None:
        validate_local_definition(root / SCHEMA_PATH, "activation", activation)
    else:
        validate_schema_definition(
            schema, "activation", activation, source_path=root / SCHEMA_PATH
        )
    if (
        activation["repository_root"] != root.as_posix()
        or activation["policy_sha256"] != _sha(policy_bytes)
        or not str(raw["owner_principal_id"]).strip()
        or activation["owner_person_id"] != raw["owner_person_id"]
        or activation["owner_principal_id"] != raw["owner_principal_id"]
        or activation["owner_roles"] != raw["owner_roles"]
        or set(cast("list[str]", activation["owner_roles"])) != _ROLES
    ):
        raise ValueError("SOLE_OWNER_ACTIVATION_BINDING")
    issued = _time(str(activation["issued_at_utc"]))
    adopted_at = _time(str(activation["adoption_accepted_at_utc"]))
    if not adopted_at <= issued <= instant:
        raise ValueError("SOLE_OWNER_ACCEPTANCE_TIME_INVALID")
    if activation["revoked_at_utc"] is not None:
        raise ValueError("SOLE_OWNER_AUTHORITY_REVOKED")
    # Completed adoption is evaluated when accepted, not as a new approval.
    # New changes still require a fresh, expiring exact-subject owner decision.
    _verify_adoption(root, activation, adopted_at)
    selected_commit = policy_commit or _git(root, "rev-parse", "HEAD").decode().strip()
    _verify_successor(root, activation, policy_bytes, selected_commit, issued)
    return SoleOwnerPolicy(
        owner_person_id=str(activation["owner_person_id"]),
        owner_principal_id=str(activation["owner_principal_id"]),
        roles=_ROLES,
        policy_sha256=_sha(policy_bytes),
        activation_sha256=_sha(activation_path.read_bytes()),
        issued_at=issued,
    )

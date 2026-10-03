"""Prospective personal research contracts; no activation or approval writer."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import yaml

from ai4binance.schema_validation import validate_local_definition

POLICY_PATH = "config/governance/personal_research_policy.yaml"
SCHEMA_PATH = "schemas/governance/personal_research.schema.json"
PROFILE = "PERSONAL_RESEARCH"
BASELINE_ADOPTION_ORIGIN = "OWNER_ISSUED"
FROZEN_REPAIR_PATCH_SHA256 = (
    "fe84cbe1f194a085f4435159835771961a72790fce4be2591e5e753b4335f4a7"
)
FROZEN_REPAIR_BASELINE = "bc0286893a1073d44290b35521520989ac09dc8a"
FROZEN_REPAIR_TREE = "5113189796f76fde7b2e5b55ed164792f7e724f9"
FROZEN_REPAIR_OUTPUTS = {
    "src/ai4binance/governance/repository_validator.py": (
        "42c4d14bcd794a0a983040741be80831d72784810afe67e99d37e12b6df6d47c"
    ),
    "scripts/quality.ps1": (
        "20f7b7312820360c6db7f0e1d74732d4946414353caa45d8822c88f6735b06cc"
    ),
    "tests/test_codex_governance_hook.py": (
        "edd36066271689868ff33a315a81ed1b52fb0c4591a71dfed6ba77f985c80056"
    ),
    "tests/test_artifact_hygiene_scripts.py": (
        "f4c9dc178bde1b17278fabf64a8eee224987362933190d01458906a5f9d3285c"
    ),
}
AUTHORITY_PATHS = (
    "docs/governance/framework_core_vnext_governance.md",
    "docs/governance/policy_organization_constitution_handbook.md",
    "docs/governance/policy_organization_incident_change_appendices.md",
    "docs/governance/policy_organization_foundation_operating_model.md",
    "docs/compliance/registry_compliance_matrix.md",
    "AGENTS.md",
    "docs/governance/instruction_core_custom_instructions.md",
    "docs/providers/instruction_codex_provider.md",
    "docs/providers/instruction_claude_provider.md",
    "GEMINI.md",
    "src/ai4binance/governance/gate.py",
    "src/ai4binance/governance/personal_research.py",
    "src/ai4binance/enterprise/contracts.py",
    "src/ai4binance/enterprise/oek_compliance.py",
    "src/ai4binance/governance/repository_validator.py",
    "src/ai4binance/governance/document_lock_review.py",
    "schemas/governance/document_lock_review.schema.json",
    "src/ai4binance/governance/document_lock_grant_review.py",
    "schemas/governance/document_lock_grant_review.schema.json",
    "docs/governance/policy_manifest_governance.md",
    "src/ai4binance/governance/document_lock_authority.py",
    "schemas/governance/document_lock_authority.schema.json",
    SCHEMA_PATH,
)
PROTECTED_PREFIXES = (
    "src/ai4binance/governance/",
    "src/ai4binance/enterprise/",
    "src/ai4binance/execution/",
    "src/ai4binance/risk/",
    "config/governance/",
    "docs/governance/",
    "docs/compliance/",
    "docs/providers/",
    "schemas/governance/",
    "policies/",
    "docs/controls/",
    "config/quality/",
    "config/risk/",
    "schemas/risk/",
    "schemas/execution/",
    "src/ai4binance/domain/",
    "src/ai4binance/governance_primitives.py",
    "src/ai4binance/schema_validation.py",
    ".agents/",
    ".codex/",
    "scripts/quality.ps1",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(value: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("PERSONAL_RESEARCH_HASH_INVALID")


def _valid_period(start: str, end: str, now: datetime) -> None:
    issued, expires = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if issued.tzinfo is None or expires.tzinfo is None or not issued <= now < expires:
        raise ValueError("PERSONAL_RESEARCH_DECISION_STALE")


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("PERSONAL_RESEARCH_OBJECT_REQUIRED")
    return cast("dict[str, object]", value)


def _contained(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if Path(relative).is_absolute() or not candidate.is_relative_to(root.resolve()):
        raise ValueError("PERSONAL_RESEARCH_PATH_ESCAPE")
    return candidate


def _validate(root: Path, kind: str, data: dict[str, object]) -> None:
    validate_local_definition(root / SCHEMA_PATH, kind, data)


def verify_baseline_adoption(
    root: Path,
    record: dict[str, object],
    *,
    now: datetime,
    artifact_root: Path | None = None,
) -> dict[str, object]:
    """Check a separately issued owner decision without activating the profile."""
    from ai4binance.governance import document_lock_review as review

    root = root.resolve(strict=True)
    version = record.get("contract_version")
    artifacts_root = (
        artifact_root.resolve(strict=True) if artifact_root is not None else root
    )
    _validate(
        artifacts_root if version == "ProspectiveBaselineAdoption/v2" else root,
        "baseline_adoption",
        record,
    )
    if record["record_origin"] != BASELINE_ADOPTION_ORIGIN:
        raise ValueError("BASELINE_ADOPTION_ORIGIN")
    if record["repository_root"] != root.as_posix():
        raise ValueError("BASELINE_ADOPTION_ROOT")
    _valid_period(str(record["issued_at_utc"]), str(record["expires_at_utc"]), now)
    issued = review._time(str(record["issued_at_utc"]))
    start = review._time(str(record["not_before_utc"]))
    expires = review._time(str(record["expires_at_utc"]))
    if not issued <= start <= now < expires or expires - issued > timedelta(hours=24):
        raise ValueError("BASELINE_ADOPTION_PERIOD")
    source = cast("dict[str, str]", record["source"])
    if not source["path"].startswith("runtime/artifacts/governance/"):
        raise ValueError("BASELINE_ADOPTION_SOURCE_LOCATION")
    review._bound_bytes(artifacts_root, source)
    patch_subject = _adoption_subject(artifacts_root, record)
    artifacts = {
        name: review._bound_bytes(artifacts_root, cast("dict[str, str]", record[name]))
        for name in ("patch", "evidence", "rollback", "authority")
    }
    review._baseline(root, patch_subject.baseline_commit)
    patch_subject.verify(
        artifacts["patch"],
        baseline_commit=patch_subject.baseline_commit,
        now=now,
        evidence=artifacts["evidence"],
        rollback=artifacts["rollback"],
        authority=artifacts["authority"],
        repository_root=root.as_posix(),
        expected_tree=patch_subject.expected_tree,
    )
    scope = cast("list[dict[str, str]]", record["scope"])
    _verify_adoption_scope(artifacts_root, artifacts["patch"], record, scope)
    _verify_adoption_authority(root, artifacts_root, record, scope, version)
    _verify_adoption_repair(root, artifacts_root, record)
    return {
        "status": "BASELINE_ADOPTION_BINDINGS_VALID",
        "application_allowed": False,
        "activation_allowed": False,
        "owner_identity_authenticated": False,
        "independent_human_review": False,
    }


def _adoption_subject(
    artifacts_root: Path, record: dict[str, object]
) -> UnappliedPatchSubject:
    from ai4binance.governance import document_lock_review as review

    subject = review._decode(
        review._bound_bytes(
            artifacts_root, cast("dict[str, str]", record["review_subject"])
        )
    )
    _validate(artifacts_root, "unapplied_patch_subject", subject)
    subject["permitted_operations"] = tuple(subject["permitted_operations"])
    patch_subject = UnappliedPatchSubject(**subject)
    if (
        record["subject_sha256"] != patch_subject.subject_sha256
        or record["baseline_commit"] != patch_subject.baseline_commit
        or record["expected_tree"] != patch_subject.expected_tree
        or record["epoch_id"] != patch_subject.epoch_id
        or record["repository_root"] != patch_subject.repository_root
    ):
        raise ValueError("BASELINE_ADOPTION_SUBJECT")
    return patch_subject


def _verify_adoption_authority(
    root: Path,
    artifacts_root: Path,
    record: dict[str, object],
    scope: list[dict[str, str]],
    version: object,
) -> None:
    from ai4binance.governance import document_lock_review as review

    bindings = cast("dict[str, str]", record["authority_bindings"])
    if set(bindings) != set(AUTHORITY_PATHS):
        raise ValueError("BASELINE_ADOPTION_AUTHORITY_DRIFT")
    if version != "ProspectiveBaselineAdoption/v2":
        if any(
            _digest((root / path).read_bytes()) != bindings[path]
            for path in AUTHORITY_PATHS
        ):
            raise ValueError("BASELINE_ADOPTION_AUTHORITY_DRIFT")
        return
    output_hashes = {item["path"]: item["output_sha256"] for item in scope}
    if any(output_hashes.get(path) != bindings[path] for path in AUTHORITY_PATHS):
        raise ValueError("BASELINE_ADOPTION_AUTHORITY_DRIFT")
    payload_inventory = review._decode(
        review._bound_bytes(
            artifacts_root, cast("dict[str, str]", record["payload_inventory"])
        )
    )
    _verify_adoption_payloads(artifacts_root, payload_inventory, scope, output_hashes)
    projection = cast("dict[str, str]", record["registration_projection"])
    manifest_path = "config/governance/governed_document_lock_manifest.json"
    if (
        projection["sha256"] != output_hashes.get(manifest_path)
        or _digest(review._bound_bytes(artifacts_root, projection))
        != projection["sha256"]
    ):
        raise ValueError("BASELINE_ADOPTION_PROJECTION_DRIFT")


def _verify_adoption_payloads(
    artifacts_root: Path,
    inventory: dict[str, object],
    scope: list[dict[str, str]],
    output_hashes: dict[str, str],
) -> None:
    from ai4binance.governance import document_lock_review as review

    payloads = inventory.get("payloads")
    if not isinstance(payloads, list) or len(payloads) != len(scope):
        raise ValueError("BASELINE_ADOPTION_PAYLOAD_INVENTORY")
    observed: dict[str, str] = {}
    for item in payloads:
        if not isinstance(item, dict) or set(item) != {"path", "payload"}:
            raise ValueError("BASELINE_ADOPTION_PAYLOAD_INVENTORY")
        path = item["path"]
        reference = item["payload"]
        if not isinstance(path, str) or not isinstance(reference, dict):
            raise ValueError("BASELINE_ADOPTION_PAYLOAD_INVENTORY")
        if path in observed or path not in output_hashes:
            raise ValueError("BASELINE_ADOPTION_PAYLOAD_INVENTORY")
        observed[path] = _digest(review._bound_bytes(artifacts_root, reference))
    if observed != output_hashes:
        raise ValueError("BASELINE_ADOPTION_PAYLOAD_DRIFT")


def _verify_adoption_repair(
    root: Path, artifacts_root: Path, record: dict[str, object]
) -> None:
    from ai4binance.governance import document_lock_review as review

    repair = cast("dict[str, object]", record["initial_repair"])
    repair_patch = review._bound_bytes(
        artifacts_root, cast("dict[str, str]", repair["patch"])
    )
    repair_inventory = review._decode(
        review._bound_bytes(artifacts_root, cast("dict[str, str]", repair["inventory"]))
    )
    output_entries = repair_inventory.get("source_inventory")
    if not isinstance(output_entries, list) or any(
        not isinstance(entry, dict)
        or not isinstance(entry.get("path"), str)
        or not isinstance(entry.get("output_sha256"), str)
        for entry in output_entries
    ):
        raise ValueError("INITIAL_REPAIR_INVENTORY")
    outputs = {entry["path"]: entry["output_sha256"] for entry in output_entries}
    if len(outputs) != len(output_entries):
        raise ValueError("INITIAL_REPAIR_INVENTORY")
    verify_frozen_initial_repair(
        root,
        repair_patch,
        expected_root=str(record["repository_root"]),
        baseline_commit=str(repair["baseline_commit"]),
        expected_tree=str(repair["expected_tree"]),
        outputs=outputs,
        change_class=str(repair["change_class"]),
    )


def _verify_adoption_scope(
    artifacts_root: Path,
    patch: bytes,
    record: dict[str, object],
    scope: list[dict[str, str]],
) -> None:
    from ai4binance.governance import document_lock_review as review

    paths = re.findall(rb"^diff --git a/(.+) b/(.+)$", patch, re.MULTILINE)
    inventory = review._decode(
        review._bound_bytes(
            artifacts_root, cast("dict[str, str]", record["source_inventory"])
        )
    )
    patch_paths = {left.decode("utf-8") for left, _ in paths}
    scope_paths = {item["path"] for item in scope}
    valid = (
        paths
        and all(left == right for left, right in paths)
        and patch_paths == scope_paths
        and len(paths) == len(scope)
        and len(patch_paths) == len(paths)
        and len(scope_paths) == len(scope)
        and inventory.get("source_inventory") == scope
    )
    if not valid:
        raise ValueError("BASELINE_ADOPTION_SCOPE")


def verify_frozen_initial_repair(
    root: Path,
    patch: bytes,
    *,
    expected_root: str,
    baseline_commit: str,
    expected_tree: str,
    outputs: dict[str, str],
    change_class: str,
) -> None:
    """Recognize only the separately reviewed four-path initial repair subject."""
    if (
        change_class != "C3_GOVERNED"
        or baseline_commit != FROZEN_REPAIR_BASELINE
        or expected_tree != FROZEN_REPAIR_TREE
        or _digest(patch) != FROZEN_REPAIR_PATCH_SHA256
        or outputs != FROZEN_REPAIR_OUTPUTS
        or root.resolve(strict=True).as_posix() != expected_root
    ):
        raise ValueError("INITIAL_REPAIR_NOT_EXACT_SUBJECT")


@dataclass(frozen=True, slots=True)
class PersonalResearchConfirmation:
    """Supplement to existing exact-subject approval, never a legacy approval."""

    epoch_id: str
    owner_person_id: str
    policy_sha256: str
    activation_sha256: str
    independent_human_review: bool = False
    human_person_count: int = 1

    def __post_init__(self) -> None:
        if not self.epoch_id.strip() or not self.owner_person_id.strip():
            raise ValueError("PERSONAL_RESEARCH_IDENTITY_REQUIRED")
        _sha(self.policy_sha256)
        _sha(self.activation_sha256)
        if (
            self.independent_human_review is not False
            or type(self.human_person_count) is not int
            or self.human_person_count != 1
        ):
            raise ValueError("PERSONAL_RESEARCH_ONE_HUMAN_REQUIRED")


def parse_confirmation(value: object) -> PersonalResearchConfirmation | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(
        PersonalResearchConfirmation.__dataclass_fields__
    ):
        raise ValueError("PERSONAL_RESEARCH_CONFIRMATION_INVALID")
    return PersonalResearchConfirmation(**value)


@dataclass(frozen=True, slots=True)
class PersonalResearchPolicy:
    epoch_id: str
    owner_person_id: str
    policy_sha256: str
    activation_sha256: str
    allowed_paths: tuple[str, ...]
    issued_at_utc: str
    expires_at_utc: str

    def confirmation_matches(
        self, confirmation: PersonalResearchConfirmation | None
    ) -> bool:
        if confirmation is None:
            return False
        expected = PersonalResearchConfirmation(
            self.epoch_id,
            self.owner_person_id,
            self.policy_sha256,
            self.activation_sha256,
        )
        return confirmation == expected

    def check_scope(self, paths: tuple[str, ...], change_class: str) -> None:
        if change_class not in {"C2_BEHAVIORAL", "C3_GOVERNED"} or not paths:
            raise ValueError("PERSONAL_RESEARCH_SCOPE_INELIGIBLE")
        if any(
            p.startswith(PROTECTED_PREFIXES) or p not in self.allowed_paths
            for p in paths
        ):
            raise ValueError("PERSONAL_RESEARCH_SCOPE_INELIGIBLE")


def _activation(
    root: Path, policy: dict[str, object], policy_hash: str, now: datetime
) -> tuple[dict[str, object], str]:
    ref = str(policy["activation_record"])
    if not ref.startswith("runtime/artifacts/governance/"):
        raise ValueError("PERSONAL_RESEARCH_ACTIVATION_LOCATION")
    path = _contained(root, ref)
    record = _object(path)
    version = policy["schema_version"]
    _validate(root, "activation_v2" if version == 2 else "activation", record)
    if record["policy_sha256"] != policy_hash or record["repository_root"] != str(
        root.resolve()
    ):
        raise ValueError("PERSONAL_RESEARCH_ACTIVATION_BINDING")
    if record["epoch_id"] != policy["epoch_id"]:
        raise ValueError("PERSONAL_RESEARCH_EPOCH_MISMATCH")
    _activation_inputs(root, record)
    if version == 2:
        _baseline_installation(root, record)
    _valid_period(str(record["issued_at_utc"]), str(record["expires_at_utc"]), now)
    return record, _digest(path.read_bytes())


def _baseline_installation(root: Path, activation: dict[str, object]) -> None:
    from ai4binance.governance import document_lock_review as review

    adoption_ref = cast("dict[str, str]", activation["baseline_adoption"])
    adoption = review._decode(review._bound_bytes(root, adoption_ref))
    receipt = review._decode(
        review._bound_bytes(
            root, cast("dict[str, str]", activation["installation_receipt"])
        )
    )
    _validate(root, "baseline_installation", receipt)
    review._bound_bytes(root, receipt["application_instruction"])
    operation = review._decode(review._bound_bytes(root, receipt["operation_receipt"]))
    _validate(root, "baseline_operation_receipt", operation)
    revised = receipt["contract_version"] == "ProspectiveBaselineInstallation/v2"
    if revised != (
        adoption["contract_version"] == "ProspectiveBaselineAdoption/v2"
        and operation["contract_version"] == "ProspectiveBaselineOperationReceipt/v2"
    ):
        raise ValueError("PERSONAL_RESEARCH_INSTALLATION_VERSION")
    completed_at = review._time(receipt["completed_at_utc"])
    verify_baseline_adoption(root, adoption, now=completed_at)
    if not (
        completed_at <= review._time(str(activation["issued_at_utc"]))
        and receipt["repository_root"] == root.as_posix()
        and receipt["epoch_id"] == activation["epoch_id"]
        and receipt["adoption"] == adoption_ref
        and receipt["subject_sha256"] == adoption["subject_sha256"]
        and receipt["patch_sha256"] == activation["reviewed_candidate_sha256"]
        and receipt["patch_sha256"]
        == cast("dict[str, str]", adoption["patch"])["sha256"]
        and (
            receipt["reviewed_tree"] == adoption["expected_tree"]
            if revised
            else receipt["expected_tree"] == adoption["expected_tree"]
        )
        and activation["prior_baseline_commit"] == adoption["baseline_commit"]
        and operation["repository_root"] == receipt["repository_root"]
        and operation["subject_sha256"] == receipt["subject_sha256"]
        and operation["patch_sha256"] == receipt["patch_sha256"]
        and operation["expected_tree"] == receipt["expected_tree"]
        and (
            operation["reviewed_tree"] == receipt["reviewed_tree"] if revised else True
        )
        and operation["completed_at_utc"] == receipt["completed_at_utc"]
    ):
        raise ValueError("PERSONAL_RESEARCH_INSTALLATION_BINDING")


def _activation_inputs(root: Path, record: dict[str, object]) -> None:
    bindings = record["authority_bindings"]
    if not isinstance(bindings, dict) or set(bindings) != set(AUTHORITY_PATHS):
        raise ValueError("PERSONAL_RESEARCH_AUTHORITY_BINDINGS_REQUIRED")
    if any(_digest((root / p).read_bytes()) != bindings[p] for p in AUTHORITY_PATHS):
        raise ValueError("PERSONAL_RESEARCH_AUTHORITY_DRIFT")
    receipt = str(record["owner_confirmation_ref"])
    if not receipt.startswith("runtime/artifacts/governance/"):
        raise ValueError("PERSONAL_RESEARCH_RECEIPT_LOCATION")
    if (
        _digest(_contained(root, receipt).read_bytes())
        != record["owner_confirmation_sha256"]
    ):
        raise ValueError("PERSONAL_RESEARCH_RECEIPT_DRIFT")


def load_personal_research_policy(
    root: Path, *, now: datetime | None = None
) -> PersonalResearchPolicy | None:
    """Absent/inactive policy keeps legacy rules; malformed/unsupported input blocks."""
    path = root / POLICY_PATH
    if not path.exists():
        return None
    policy = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(policy, dict):
        raise ValueError("PERSONAL_RESEARCH_OBJECT_REQUIRED")
    _validate(
        root, "policy_v2" if policy.get("schema_version") == 2 else "policy", policy
    )
    if policy["activation_status"] == "INACTIVE":
        return None
    policy_hash = _digest(path.read_bytes())
    record, activation_hash = _activation(
        root, policy, policy_hash, now or datetime.now(UTC)
    )
    return PersonalResearchPolicy(
        str(policy["epoch_id"]),
        str(record["owner_person_id"]),
        policy_hash,
        activation_hash,
        tuple(cast("list[str]", policy["allowed_paths"])),
        str(record["issued_at_utc"]),
        str(record["expires_at_utc"]),
    )


def personal_record_blockers(
    policy: PersonalResearchPolicy,
    confirmation: PersonalResearchConfirmation | None,
    principal_id: str,
    role: str,
    approved_at: datetime | None,
    expires_at: datetime | None,
) -> tuple[str, ...]:
    """Additional restrictions; existing subject/evidence/status vetoes still run."""
    blockers: list[str] = []
    if not policy.confirmation_matches(confirmation):
        blockers.append("PERSONAL_RESEARCH_CONFIRMATION_MISMATCH")
    if principal_id != policy.owner_person_id or role != "PersonalResearchOwner":
        blockers.append("PERSONAL_RESEARCH_OWNER_MISMATCH")
    if approved_at is None or expires_at is None:
        blockers.append("PERSONAL_RESEARCH_EXPIRY_REQUIRED")
    elif approved_at > datetime.now(UTC):
        blockers.append("PERSONAL_RESEARCH_FUTURE_CONFIRMATION")
    elif approved_at < datetime.fromisoformat(
        policy.issued_at_utc
    ) or expires_at > datetime.fromisoformat(policy.expires_at_utc):
        blockers.append("PERSONAL_RESEARCH_DECISION_PERIOD_MISMATCH")
    return tuple(blockers)


@dataclass(frozen=True, slots=True)
class UnappliedPatchSubject:
    """Artifact review binding only; construction never permits APPLY/COMMIT."""

    repository_root: str
    baseline_commit: str
    patch_sha256: str
    evidence_sha256: str
    rollback_sha256: str
    authority_sha256: str
    epoch_id: str
    expires_at_utc: str
    expected_tree: str
    permitted_operations: tuple[str, ...] = ("REVIEW_ONLY",)
    phase: str = "UNAPPLIED_PATCH_REVIEW"

    def __post_init__(self) -> None:
        for value in (
            self.patch_sha256,
            self.evidence_sha256,
            self.rollback_sha256,
            self.authority_sha256,
        ):
            _sha(value)
        for value in (self.baseline_commit, self.expected_tree):
            if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("PATCH_SUBJECT_GIT_ID_INVALID")
        if not Path(self.repository_root).is_absolute() or not self.epoch_id.strip():
            raise ValueError("PATCH_SUBJECT_IDENTITY_REQUIRED")
        if self.phase != "UNAPPLIED_PATCH_REVIEW" or self.permitted_operations != (
            "REVIEW_ONLY",
        ):
            raise ValueError("PATCH_SUBJECT_NOT_EXECUTION_AUTHORITY")

    @property
    def subject_sha256(self) -> str:
        return _digest(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        )

    def verify(
        self,
        patch: bytes,
        *,
        baseline_commit: str,
        now: datetime,
        evidence: bytes,
        rollback: bytes,
        authority: bytes,
        repository_root: str,
        expected_tree: str,
    ) -> None:
        if (
            _digest(patch) != self.patch_sha256
            or baseline_commit != self.baseline_commit
        ):
            raise ValueError("PATCH_SUBJECT_DRIFT")
        observed = (
            _digest(evidence),
            _digest(rollback),
            _digest(authority),
            repository_root,
            expected_tree,
        )
        expected = (
            self.evidence_sha256,
            self.rollback_sha256,
            self.authority_sha256,
            self.repository_root,
            self.expected_tree,
        )
        if observed != expected:
            raise ValueError("PATCH_SUBJECT_EVIDENCE_DRIFT")
        expires = datetime.fromisoformat(self.expires_at_utc)
        if expires.tzinfo is None or now.tzinfo is None or now >= expires:
            raise ValueError("PATCH_SUBJECT_EXPIRED")

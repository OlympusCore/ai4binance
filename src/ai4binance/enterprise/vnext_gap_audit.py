"""Deterministic vNext v1.2 gap audit mapped to local repository evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from ai4binance.governance.constitution_sync import load_current_quality_gate_evidence
from ai4binance.governance.enforcement.inventory import (
    RequirementAssuranceDecision,
    RequirementTraceabilityRegistry,
    bypassable_consequential_entrypoint_ids,
    load_enforcement_inventory,
    uncovered_consequential_entrypoint_ids,
)


class VnextGapStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    MISSING = "MISSING"


class VnextEvidenceDepth(StrEnum):
    CODE_ONLY = "CODE_ONLY"
    TESTED_CONTRACT = "TESTED_CONTRACT"
    RUNTIME_WIRED = "RUNTIME_WIRED"
    PRODUCTION_EVIDENCE = "PRODUCTION_EVIDENCE"


class VnextClaimStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class VnextCapabilityGap:
    capability_id: str
    title: str
    phase: str
    priority: str
    status: VnextGapStatus
    evidence_files: tuple[str, ...]
    missing_controls: tuple[str, ...]
    proposed_diff: tuple[str, ...]
    risk: str
    evidence_depth: VnextEvidenceDepth = VnextEvidenceDepth.CODE_ONLY
    claim_status: VnextClaimStatus = VnextClaimStatus.MISSING
    claim_verifier: str = "FILE_PRESENCE"
    runtime_wiring: str = "NOT_VERIFIED"
    production_artifact_status: str = "NOT_REQUIRED"
    eval_status: str = "NOT_EVALUATED"

    def __post_init__(self) -> None:
        required = (
            self.capability_id,
            self.title,
            self.phase,
            self.priority,
            self.risk,
            self.claim_verifier,
            self.runtime_wiring,
            self.production_artifact_status,
            self.eval_status,
        )
        if any(not value.strip() for value in required):
            raise ValueError("vNext capability gap identity is required")
        for values in (
            self.evidence_files,
            self.missing_controls,
            self.proposed_diff,
        ):
            _require_unique_nonblank("vNext gap list", values)


@dataclass(frozen=True, slots=True)
class VnextGapAuditReport:
    status: str
    repository_root: Path
    capabilities: tuple[VnextCapabilityGap, ...]
    top_gaps: tuple[str, ...]
    next_phase: str
    blockers: tuple[str, ...]
    requirement_traceability_status: str
    requirement_traceability_entry_count: int
    requirement_traceability_converged_count: int
    requirement_traceability_blockers: tuple[str, ...]
    command: str = "vnext-gap-audit"
    source_profile: str = "AI4BINANCE_ENTERPRISEAI_VNEXT_V1_2"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("vNext gap audit status is invalid")
        if not self.capabilities:
            raise ValueError("vNext gap audit requires capability coverage")
        _require_unique_nonblank("vNext top gaps", self.top_gaps)
        _require_unique_nonblank("vNext blockers", self.blockers)
        _require_unique_nonblank(
            "vNext requirement traceability blockers",
            self.requirement_traceability_blockers,
        )
        if self.requirement_traceability_status not in {
            "PASS",
            "RUNNING_WITH_BLOCKERS",
            "MISSING",
            "INVALID",
        }:
            raise ValueError("vNext requirement traceability status is invalid")
        if self.requirement_traceability_entry_count < 0:
            raise ValueError("requirement traceability entry count cannot be negative")
        if (
            not 0
            <= self.requirement_traceability_converged_count
            <= (self.requirement_traceability_entry_count)
        ):
            raise ValueError("requirement traceability converged count is invalid")
        if (
            self.requirement_traceability_status == "PASS"
            and self.requirement_traceability_blockers
        ):
            raise ValueError("passing requirement traceability cannot have blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("vNext gap audit cannot authorize execution")

    @property
    def summary_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in VnextGapStatus}
        for item in self.capabilities:
            counts[item.status.value] += 1
        return counts

    def to_payload(self) -> dict[str, object]:
        return {
            "command": self.command,
            "source_profile": self.source_profile,
            "status": self.status,
            "repository_root": str(self.repository_root),
            "summary_counts": self.summary_counts,
            "top_gaps": list(self.top_gaps),
            "next_phase": self.next_phase,
            "requirement_traceability": {
                "status": self.requirement_traceability_status,
                "entry_count": self.requirement_traceability_entry_count,
                "converged_count": self.requirement_traceability_converged_count,
                "blockers": list(self.requirement_traceability_blockers),
            },
            "capabilities": [
                {
                    "capability_id": item.capability_id,
                    "title": item.title,
                    "phase": item.phase,
                    "priority": item.priority,
                    "status": item.status.value,
                    "evidence_files": list(item.evidence_files),
                    "missing_controls": list(item.missing_controls),
                    "proposed_diff": list(item.proposed_diff),
                    "risk": item.risk,
                    "evidence_depth": item.evidence_depth.value,
                    "claim_status": item.claim_status.value,
                    "claim_verifier": item.claim_verifier,
                    "runtime_wiring": item.runtime_wiring,
                    "production_artifact_status": item.production_artifact_status,
                    "eval_status": item.eval_status,
                }
                for item in self.capabilities
            ],
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_vnext_gap_audit(
    repository_root: Path | None = None,
    *,
    observed_at: datetime | None = None,
) -> VnextGapAuditReport:
    """Build a report-only vNext v1.2 gap matrix from local repository evidence."""
    root = (repository_root or _repository_root()).resolve()
    now = observed_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("vNext gap audit observation time must be timezone-aware")
    now = now.astimezone(UTC)
    capabilities = tuple(
        _capability_from_definition(root, item, observed_at=now)
        for item in _CAPABILITY_MATRIX
    )
    requirement_traceability = _audit_requirement_traceability(root)
    top_gaps = tuple(
        item.capability_id
        for item in capabilities
        if item.priority in {"P0", "P1"}
        and item.status in {VnextGapStatus.PARTIAL, VnextGapStatus.MISSING}
    )[:8]
    blockers = tuple(
        dict.fromkeys(
            (
                *(
                    f"{item.capability_id}:{control}"
                    for item in capabilities
                    for control in item.missing_controls[:2]
                    if item.priority in {"P0", "P1"}
                ),
                *(
                    f"{item.capability_id}:CLAIM_NOT_VERIFIED"
                    for item in capabilities
                    if item.priority in {"P0", "P1"}
                    and item.claim_status is not VnextClaimStatus.VERIFIED
                ),
                *(
                    f"{item.capability_id}:PRODUCTION_EVIDENCE_INCOMPLETE"
                    for item in capabilities
                    if item.priority in {"P0", "P1"}
                    and item.production_artifact_status == "MISSING"
                ),
                *requirement_traceability.blockers,
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    closure_blockers = tuple(
        blocker for blocker in blockers if blocker != "LIVE_ORDER_BLOCKED"
    )
    return VnextGapAuditReport(
        status="READY" if not closure_blockers else "RUNNING_WITH_BLOCKERS",
        repository_root=root,
        capabilities=capabilities,
        top_gaps=top_gaps,
        next_phase=_next_phase(capabilities, requirement_traceability),
        blockers=blockers,
        requirement_traceability_status=requirement_traceability.status,
        requirement_traceability_entry_count=requirement_traceability.entry_count,
        requirement_traceability_converged_count=(
            requirement_traceability.converged_count
        ),
        requirement_traceability_blockers=requirement_traceability.blockers,
    )


@dataclass(frozen=True, slots=True)
class _RequirementTraceabilityAudit:
    status: str
    entry_count: int
    converged_count: int
    blockers: tuple[str, ...]


def _audit_requirement_traceability(root: Path) -> _RequirementTraceabilityAudit:
    inventory_path = root / "config/governance/enforcement_inventory.yaml"
    if not inventory_path.is_file():
        return _RequirementTraceabilityAudit(
            status="MISSING",
            entry_count=0,
            converged_count=0,
            blockers=("REQUIREMENT_TRACEABILITY_MISSING",),
        )
    try:
        inventory = load_enforcement_inventory(inventory_path)
    except (OSError, ValueError):
        return _RequirementTraceabilityAudit(
            status="INVALID",
            entry_count=0,
            converged_count=0,
            blockers=("REQUIREMENT_TRACEABILITY_INVALID",),
        )
    traceability = inventory.requirement_traceability
    if traceability is None:
        return _RequirementTraceabilityAudit(
            status="MISSING",
            entry_count=0,
            converged_count=0,
            blockers=("REQUIREMENT_TRACEABILITY_MISSING",),
        )
    assurance_chains = traceability.assurance_chains(root)
    blockers = tuple(
        dict.fromkeys(
            (
                *(
                    blocker
                    for chain in assurance_chains
                    for blocker in chain.blocker_codes
                ),
            )
        )
    )
    return _RequirementTraceabilityAudit(
        status="PASS" if not blockers else "RUNNING_WITH_BLOCKERS",
        entry_count=len(traceability.entries),
        converged_count=sum(
            chain.assurance_decision is not RequirementAssuranceDecision.BLOCKED
            for chain in assurance_chains
        ),
        blockers=blockers,
    )


def _requirement_reference_blockers(
    root: Path,
    traceability: RequirementTraceabilityRegistry,
) -> tuple[str, ...]:
    blockers: list[str] = []
    for entry in traceability.entries:
        required_references = (
            ("AUTHORITY_REF_MISSING", (entry.authority_ref,)),
            ("MACHINE_READABLE_REF_MISSING", (entry.machine_readable_ref,)),
            ("IMPLEMENTATION_REF_MISSING", entry.implementation_refs),
            ("TEST_REF_MISSING", entry.test_refs),
        )
        for blocker_kind, references in required_references:
            if any(
                _repository_file(root, reference) is None for reference in references
            ):
                blockers.append(f"{entry.requirement_id}:{blocker_kind}")
        evidence_path = _repository_file(root, entry.evidence_ref)
        if evidence_path is None:
            blockers.append(f"{entry.requirement_id}:EVIDENCE_REF_MISSING")
            continue
        try:
            payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            blockers.append(f"{entry.requirement_id}:EVIDENCE_REF_INVALID")
            continue
        if not isinstance(payload, Mapping):
            blockers.append(f"{entry.requirement_id}:EVIDENCE_REF_INVALID")
    return tuple(blockers)


def _repository_file(root: Path, reference: str) -> Path | None:
    resolved_root = root.resolve()
    candidate = (resolved_root / reference).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _capability(
    root: Path,
    *,
    capability_id: str,
    title: str,
    phase: str,
    priority: str,
    evidence_files: tuple[str, ...],
    complete_when: tuple[str, ...],
    runtime_wiring_files: tuple[str, ...],
    production_evidence_files: tuple[str, ...],
    missing_controls: tuple[str, ...],
    proposed_diff: tuple[str, ...],
    risk: str,
    research_only: bool = False,
    claim_verifier: str = "FILE_PRESENCE",
    observed_at: datetime,
) -> VnextCapabilityGap:
    existing = tuple(path for path in evidence_files if (root / path).exists())
    required_existing = tuple(path for path in complete_when if (root / path).exists())
    runtime_existing = tuple(
        path for path in runtime_wiring_files if (root / path).exists()
    )
    production_existing = tuple(
        path for path in production_evidence_files if (root / path).exists()
    )
    code_complete = len(required_existing) == len(complete_when)
    runtime_complete = len(runtime_existing) == len(runtime_wiring_files)
    production_required = bool(production_evidence_files)
    artifact_blockers = _production_evidence_blockers(
        root,
        capability_id=capability_id,
        evidence_files=production_evidence_files,
        observed_at=observed_at,
    )
    production_complete = (
        len(production_existing) == len(production_evidence_files)
        and not artifact_blockers
    )
    production_gap = (
        ("PRODUCTION_EVIDENCE_INCOMPLETE",)
        if production_required
        and len(production_existing) != len(production_evidence_files)
        else ()
    )
    evidence_depth = _evidence_depth(
        code_complete=code_complete,
        has_tests=any(path.startswith("tests/") for path in existing),
        runtime_complete=runtime_complete,
        production_complete=production_complete and production_required,
    )
    runtime_wiring = (
        "NOT_REQUIRED"
        if not runtime_wiring_files
        else "VERIFIED"
        if runtime_complete
        else "MISSING"
    )
    production_status = (
        "NOT_REQUIRED"
        if not production_required
        else "VERIFIED"
        if production_complete
        else "MISSING"
    )
    if code_complete and (not production_required or production_complete):
        status = (
            VnextGapStatus.RESEARCH_ONLY if research_only else VnextGapStatus.COMPLETE
        )
        remaining: tuple[str, ...] = ()
    elif code_complete:
        status = (
            VnextGapStatus.RESEARCH_ONLY if research_only else VnextGapStatus.PARTIAL
        )
        remaining = tuple(
            dict.fromkeys((*missing_controls, *production_gap, *artifact_blockers))
        )
    elif existing:
        status = VnextGapStatus.PARTIAL
        remaining = tuple(
            dict.fromkeys((*missing_controls, *production_gap, *artifact_blockers))
        )
    else:
        status = VnextGapStatus.MISSING
        remaining = tuple(
            dict.fromkeys((*missing_controls, *production_gap, *artifact_blockers))
        )
    claim_status = (
        VnextClaimStatus.VERIFIED
        if not remaining
        else VnextClaimStatus.PARTIAL
        if existing
        else VnextClaimStatus.MISSING
    )
    return VnextCapabilityGap(
        capability_id=capability_id,
        title=title,
        phase=phase,
        priority=priority,
        status=status,
        evidence_files=existing,
        missing_controls=remaining,
        proposed_diff=proposed_diff if remaining else (),
        risk=risk,
        evidence_depth=evidence_depth,
        claim_status=claim_status,
        claim_verifier=claim_verifier,
        runtime_wiring=runtime_wiring,
        production_artifact_status=production_status,
        eval_status=(
            "RESEARCH_ONLY"
            if research_only
            else "PRODUCTION_EVIDENCE_VERIFIED"
            if production_complete and production_required
            else "EVIDENCE_GAP"
            if production_required
            else "CONTRACT_EVALUATED"
        ),
    )


def _capability_from_definition(
    root: Path,
    definition: Mapping[str, object],
    *,
    observed_at: datetime,
) -> VnextCapabilityGap:
    verifier = str(definition.get("claim_verifier", "FILE_PRESENCE"))
    if verifier == "QUALITY_BASELINE":
        return _quality_baseline_capability(root, definition)
    if verifier == "ENFORCEMENT_CLOSURE":
        return _enforcement_closure_capability(root, definition)
    return _capability(
        root,
        capability_id=str(definition["capability_id"]),
        title=str(definition["title"]),
        phase=str(definition["phase"]),
        priority=str(definition["priority"]),
        evidence_files=cast(tuple[str, ...], definition["evidence_files"]),
        complete_when=cast(tuple[str, ...], definition["complete_when"]),
        runtime_wiring_files=cast(
            tuple[str, ...], definition.get("runtime_wiring_files", ())
        ),
        production_evidence_files=cast(
            tuple[str, ...], definition.get("production_evidence_files", ())
        ),
        missing_controls=cast(tuple[str, ...], definition["missing_controls"]),
        proposed_diff=cast(tuple[str, ...], definition["proposed_diff"]),
        risk=str(definition["risk"]),
        research_only=bool(definition.get("research_only", False)),
        claim_verifier=verifier,
        observed_at=observed_at,
    )


def _quality_baseline_capability(
    root: Path,
    definition: Mapping[str, object],
) -> VnextCapabilityGap:
    quality_evidence = load_current_quality_gate_evidence(root)
    coverage_policy_result = _load_coverage_policy_result(root)
    is_verified = quality_evidence is not None and coverage_policy_result == "PASS"
    missing_controls: tuple[str, ...]
    if quality_evidence is None:
        eval_status = "MISSING_OR_STALE"
        missing_controls = ("CURRENT_QUALITY_BASELINE_FAILED",)
    elif coverage_policy_result != "PASS":
        eval_status = f"COVERAGE_POLICY_{coverage_policy_result or 'STATUS_MISSING'}"
        missing_controls = ("CURRENT_QUALITY_COVERAGE_POLICY_NOT_PASS",)
    else:
        eval_status = quality_evidence.status
        missing_controls = ()
    return VnextCapabilityGap(
        capability_id=str(definition["capability_id"]),
        title=str(definition["title"]),
        phase=str(definition["phase"]),
        priority=str(definition["priority"]),
        status=VnextGapStatus.COMPLETE if is_verified else VnextGapStatus.PARTIAL,
        evidence_files=tuple(
            path
            for path in cast(tuple[str, ...], definition["evidence_files"])
            if (root / path).exists()
        ),
        missing_controls=missing_controls,
        proposed_diff=(
            cast(tuple[str, ...], definition["proposed_diff"])
            if not is_verified
            else ()
        ),
        risk=str(definition["risk"]),
        evidence_depth=(
            VnextEvidenceDepth.PRODUCTION_EVIDENCE
            if quality_evidence is not None
            else VnextEvidenceDepth.CODE_ONLY
        ),
        claim_status=(
            VnextClaimStatus.VERIFIED if is_verified else VnextClaimStatus.PARTIAL
        ),
        claim_verifier="QUALITY_BASELINE",
        runtime_wiring="VERIFIED" if quality_evidence is not None else "MISSING",
        production_artifact_status=(
            "VERIFIED" if quality_evidence is not None else "MISSING"
        ),
        eval_status=eval_status,
    )


def _load_coverage_policy_result(root: Path) -> str | None:
    evidence_path = root / "runtime/artifacts/quality/gate/latest.json"
    if not evidence_path.is_file():
        return None
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    coverage_policy = payload.get("coverage_policy_summary")
    if not isinstance(coverage_policy, Mapping):
        return None
    result = coverage_policy.get("policy_result")
    if not isinstance(result, str) or not result.strip():
        return None
    return result.strip()


def _enforcement_closure_capability(
    root: Path,
    definition: Mapping[str, object],
) -> VnextCapabilityGap:
    inventory_path = root / "config/governance/enforcement_inventory.yaml"
    if not inventory_path.is_file():
        return VnextCapabilityGap(
            capability_id=str(definition["capability_id"]),
            title=str(definition["title"]),
            phase=str(definition["phase"]),
            priority=str(definition["priority"]),
            status=VnextGapStatus.MISSING,
            evidence_files=(),
            missing_controls=("UNREGISTERED_MUTATION_ENTRYPOINTS_PRESENT",),
            proposed_diff=cast(tuple[str, ...], definition["proposed_diff"]),
            risk=str(definition["risk"]),
            evidence_depth=VnextEvidenceDepth.CODE_ONLY,
            claim_status=VnextClaimStatus.MISSING,
            claim_verifier="ENFORCEMENT_CLOSURE",
            runtime_wiring="MISSING",
            production_artifact_status="NOT_REQUIRED",
            eval_status="ENFORCEMENT_INVENTORY_MISSING",
        )
    try:
        inventory = load_enforcement_inventory(inventory_path)
    except (OSError, ValueError):
        return VnextCapabilityGap(
            capability_id=str(definition["capability_id"]),
            title=str(definition["title"]),
            phase=str(definition["phase"]),
            priority=str(definition["priority"]),
            status=VnextGapStatus.PARTIAL,
            evidence_files=tuple(
                path
                for path in cast(tuple[str, ...], definition["evidence_files"])
                if (root / path).exists()
            ),
            missing_controls=("ENFORCEMENT_INVENTORY_INVALID",),
            proposed_diff=cast(tuple[str, ...], definition["proposed_diff"]),
            risk=str(definition["risk"]),
            evidence_depth=VnextEvidenceDepth.CODE_ONLY,
            claim_status=VnextClaimStatus.PARTIAL,
            claim_verifier="ENFORCEMENT_CLOSURE",
            runtime_wiring="NOT_VERIFIED",
            production_artifact_status="NOT_REQUIRED",
            eval_status="ENFORCEMENT_INVENTORY_INVALID",
        )
    uncovered = uncovered_consequential_entrypoint_ids(inventory)
    bypassable = bypassable_consequential_entrypoint_ids(inventory)
    missing_controls = tuple(
        dict.fromkeys(
            (
                *(
                    ()
                    if not uncovered
                    else ("UNREGISTERED_MUTATION_ENTRYPOINTS_PRESENT",)
                ),
                *(() if not bypassable else ("BYPASS_POSSIBLE_ON_ROUTED_PATHS",)),
            )
        )
    )
    complete = not missing_controls
    return VnextCapabilityGap(
        capability_id=str(definition["capability_id"]),
        title=str(definition["title"]),
        phase=str(definition["phase"]),
        priority=str(definition["priority"]),
        status=VnextGapStatus.COMPLETE if complete else VnextGapStatus.PARTIAL,
        evidence_files=tuple(
            path
            for path in cast(tuple[str, ...], definition["evidence_files"])
            if (root / path).exists()
        ),
        missing_controls=missing_controls,
        proposed_diff=(
            cast(tuple[str, ...], definition["proposed_diff"]) if not complete else ()
        ),
        risk=str(definition["risk"]),
        evidence_depth=VnextEvidenceDepth.TESTED_CONTRACT,
        claim_status=(
            VnextClaimStatus.VERIFIED if complete else VnextClaimStatus.PARTIAL
        ),
        claim_verifier="ENFORCEMENT_CLOSURE",
        runtime_wiring="VERIFIED",
        production_artifact_status="NOT_REQUIRED",
        eval_status=(
            "ENFORCEMENT_CLOSURE_VERIFIED"
            if complete
            else "ENFORCEMENT_CLOSURE_BLOCKED"
        ),
    )


def _evidence_depth(
    *,
    code_complete: bool,
    has_tests: bool,
    runtime_complete: bool,
    production_complete: bool,
) -> VnextEvidenceDepth:
    if production_complete:
        return VnextEvidenceDepth.PRODUCTION_EVIDENCE
    if runtime_complete:
        return VnextEvidenceDepth.RUNTIME_WIRED
    if code_complete and has_tests:
        return VnextEvidenceDepth.TESTED_CONTRACT
    return VnextEvidenceDepth.CODE_ONLY


def _next_phase(
    capabilities: tuple[VnextCapabilityGap, ...],
    traceability: _RequirementTraceabilityAudit,
) -> str:
    for priority in ("P0", "P1"):
        for capability in capabilities:
            if capability.priority == priority and capability.status in {
                VnextGapStatus.PARTIAL,
                VnextGapStatus.MISSING,
            }:
                return f"{capability.capability_id}_EVIDENCE_CLOSURE"
    if traceability.status != "PASS":
        return "REQUIREMENT_TRACEABILITY_CLOSURE"
    return "VNEXT_EVIDENCE_CLOSURE_COMPLETE"


def _repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "config").is_dir() and (candidate / "src").is_dir():
            return candidate
    raise ValueError("repository root could not be determined from module path")


_CAPABILITY_MATRIX: tuple[dict[str, object], ...] = (
    {
        "capability_id": "VNEXT-00-AUDIT-BASELINE",
        "title": "vNext v1.2 repository gap audit",
        "phase": "Faz 0",
        "priority": "P0",
        "evidence_files": (
            "src/ai4binance/enterprise/vnext_gap_audit.py",
            "tests/test_vnext_gap_audit.py",
        ),
        "complete_when": (
            "src/ai4binance/enterprise/vnext_gap_audit.py",
            "tests/test_vnext_gap_audit.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/cli.py",),
        "production_evidence_files": (),
        "missing_controls": ("AUTOMATED_VNEXT_GAP_MATRIX_MISSING",),
        "proposed_diff": (
            "CREATE src/ai4binance/enterprise/vnext_gap_audit.py",
            "ADD CLI command vnext-gap-audit",
        ),
        "risk": "LOW",
    },
    {
        "capability_id": "VNEXT-00A-QUALITY-BASELINE",
        "title": "Current quality baseline recovery",
        "phase": "Faz 0",
        "priority": "P0",
        "evidence_files": (
            "scripts/quality.ps1",
            "runtime/artifacts/quality/gate/latest.json",
        ),
        "complete_when": ("scripts/quality.ps1",),
        "runtime_wiring_files": ("runtime/artifacts/quality/gate/latest.json",),
        "production_evidence_files": ("runtime/artifacts/quality/gate/latest.json",),
        "missing_controls": ("CURRENT_QUALITY_BASELINE_FAILED",),
        "proposed_diff": (
            "ISOLATE current quality gate failure",
            "RESTORE machine-readable passing latest.json",
        ),
        "risk": "HIGH",
        "claim_verifier": "QUALITY_BASELINE",
    },
    {
        "capability_id": "VNEXT-00B-UNIVERSAL-ENFORCEMENT",
        "title": "Universal consequential enforcement closure",
        "phase": "Faz 1-10",
        "priority": "P0",
        "evidence_files": (
            "src/ai4binance/governance/enforcement/engine.py",
            "src/ai4binance/governance/enforcement/inventory.py",
            "config/governance/enforcement_inventory.yaml",
            "tests/test_governed_object_enforcement.py",
        ),
        "complete_when": (
            "src/ai4binance/governance/enforcement/engine.py",
            "src/ai4binance/governance/enforcement/inventory.py",
            "config/governance/enforcement_inventory.yaml",
            "tests/test_governed_object_enforcement.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/governance/enforcement/engine.py",),
        "production_evidence_files": (),
        "missing_controls": (
            "UNREGISTERED_MUTATION_ENTRYPOINTS_PRESENT",
            "BYPASS_POSSIBLE_ON_ROUTED_PATHS",
        ),
        "proposed_diff": (
            "ROUTE every consequential entrypoint through the universal gateway",
            "ELIMINATE bypass_possible on routed consequential paths",
        ),
        "risk": "HIGH",
        "claim_verifier": "ENFORCEMENT_CLOSURE",
    },
    {
        "capability_id": "VNEXT-01-LOCAL-QWEN",
        "title": "Local Ollama qwen3:8b advisory workbench",
        "phase": "Faz 10",
        "priority": "P1",
        "evidence_files": (
            "src/ai4binance/local_agent/workbench.py",
            "scripts/start_qwen_prompter.ps1",
            "scripts/ollama_advisory_common.ps1",
            "tests/test_local_qwen_workbench.py",
        ),
        "complete_when": (
            "src/ai4binance/local_agent/workbench.py",
            "tests/test_local_qwen_workbench.py",
        ),
        "runtime_wiring_files": ("runtime/state/qwen-prompter-health.json",),
        "production_evidence_files": ("runtime/state/qwen-prompter-health.json",),
        "missing_controls": (
            "APPROVED_PATCH_PROPOSAL_GATE_MISSING",
            "STRUCTURED_TOOL_POLICY_MATRIX_INCOMPLETE",
        ),
        "proposed_diff": (
            "CREATE local_agent/tool_policy.py",
            "CREATE local_agent/patch_proposal.py",
        ),
        "risk": "MEDIUM",
    },
    {
        "capability_id": "VNEXT-02-RECOVERY-RADAR",
        "title": "HOT inventory recovery candidate ladder",
        "phase": "Faz 7",
        "priority": "P0",
        "evidence_files": (
            "src/ai4binance/portfolio/opportunity_recovery.py",
            "src/ai4binance/governance/adapters.py",
            "tests/test_opportunity_recovery_radar.py",
            "tests/test_dge_recovery_replay_shadow.py",
        ),
        "complete_when": (
            "src/ai4binance/portfolio/opportunity_recovery.py",
            "tests/test_opportunity_recovery_radar.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/enterprise/ykb_report.py",),
        "production_evidence_files": (
            "runtime/artifacts/user_reports/ykb/latest.json",
        ),
        "missing_controls": (
            "MSPACIS_LENS_CONTRACT_INCOMPLETE",
            "RELATIVE_STRENGTH_AND_DERIVATIVES_CONTEXT_MISSING",
        ),
        "proposed_diff": (
            "MODIFY portfolio/opportunity_recovery.py",
            "MODIFY enterprise/ykb_report.py",
        ),
        "risk": "MEDIUM",
    },
    {
        "capability_id": "VNEXT-03-ONTOLOGY",
        "title": "Enterprise ontology and semantic graph",
        "phase": "Faz 5",
        "priority": "P1",
        "evidence_files": (
            "src/ai4binance/ontology/contracts.py",
            "src/ai4binance/ontology/semantic_graph.py",
            "tests/test_semantic_graph_contracts.py",
        ),
        "complete_when": (
            "src/ai4binance/ontology/contracts.py",
            "tests/test_semantic_graph_contracts.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/ontology/semantic_graph.py",),
        "production_evidence_files": (),
        "missing_controls": (
            "FULL_VNEXT_ENTITY_CATALOG_NOT_MAPPED",
            "SETUP_EVIDENCE_RISK_DGE_GRAPH_LINKS_INCOMPLETE",
        ),
        "proposed_diff": (
            "MODIFY ontology/contracts.py",
            "CREATE ontology/evidence_graph.py",
        ),
        "risk": "MEDIUM",
    },
    {
        "capability_id": "VNEXT-04-RAG-GOVERNANCE",
        "title": "Multi-agent RAG namespace and freshness governance",
        "phase": "Faz 10",
        "priority": "P1",
        "evidence_files": (
            "src/ai4binance/rag.py",
            "src/ai4binance/multiops/ragops/__init__.py",
            "tests/test_rag_second_brain.py",
        ),
        "complete_when": ("src/ai4binance/rag.py", "tests/test_rag_second_brain.py"),
        "runtime_wiring_files": ("src/ai4binance/local_agent/workbench.py",),
        "production_evidence_files": (),
        "missing_controls": ("RAG_NAMESPACE_INVALIDATION_INCOMPLETE",),
        "proposed_diff": (
            "MODIFY rag.py",
            "ADD retrieval namespace metadata tests",
        ),
        "risk": "MEDIUM",
    },
    {
        "capability_id": "VNEXT-05-REALTIME-DATA-PLANE",
        "title": "WebSocket, backfill and latency-instrumented data plane",
        "phase": "Faz 4",
        "priority": "P1",
        "evidence_files": (
            "src/ai4binance/exchange/continuity.py",
            "src/ai4binance/exchange/public_stream.py",
            "src/ai4binance/exchange/stream_state.py",
            "src/ai4binance/ops/performance.py",
            "tests/test_connector_stream_readiness.py",
            "tests/test_provider_continuity.py",
            "tests/test_performance_guard.py",
        ),
        "complete_when": (
            "src/ai4binance/exchange/continuity.py",
            "src/ai4binance/exchange/public_stream.py",
            "src/ai4binance/exchange/stream_state.py",
            "tests/test_connector_stream_readiness.py",
            "tests/test_provider_continuity.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/ops/system_report.py",),
        "production_evidence_files": (
            "runtime/artifacts/benchmarks/latency/latency-latest.json",
        ),
        "missing_controls": (
            "EVENT_LEVEL_LATENCY_CHAIN_MISSING",
            "WEBSOCKET_RUNTIME_SOAK_EVIDENCE_MISSING",
        ),
        "proposed_diff": (
            "CREATE marketdata/latency.py",
            "MODIFY exchange/public_stream.py",
        ),
        "risk": "HIGH",
    },
    {
        "capability_id": "VNEXT-06-RISK-CAPITAL",
        "title": "Wallet-first risk and capital controls",
        "phase": "Faz 3",
        "priority": "P0",
        "evidence_files": (
            "src/ai4binance/risk.py",
            "src/ai4binance/portfolio/risk_budget.py",
            "src/ai4binance/portfolio/reconciliation.py",
            "tests/test_strategy_risk.py",
        ),
        "complete_when": (
            "src/ai4binance/risk.py",
            "src/ai4binance/portfolio/risk_budget.py",
            "tests/test_strategy_risk.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/enterprise/ykb_report.py",),
        "production_evidence_files": (
            "runtime/artifacts/user_reports/ykb/latest.json",
        ),
        "missing_controls": (
            "ACCOUNT_WIDE_REAL_RECONCILIATION_EVIDENCE_MISSING",
            "FUTURES_MARGIN_AND_LIQUIDATION_DISTANCE_GATE_INCOMPLETE",
        ),
        "proposed_diff": (
            "MODIFY risk.py",
            "ADD account-wide portfolio heat report",
        ),
        "risk": "MEDIUM",
    },
    {
        "capability_id": "VNEXT-07-OOS-AUTOML",
        "title": "Backtest, walk-forward, OOS and AutoML governance",
        "phase": "Faz 8-9",
        "priority": "P0",
        "evidence_files": (
            "src/ai4binance/research/backtesting/engine.py",
            "src/ai4binance/validation/walk_forward.py",
            "src/ai4binance/validation/recovery_queue.py",
            "src/ai4binance/tuning/engine.py",
            "tests/test_recovery_validation_queue.py",
            "tests/test_walk_forward.py",
            "tests/test_tuning_governance.py",
        ),
        "complete_when": (
            "src/ai4binance/research/backtesting/engine.py",
            "src/ai4binance/validation/walk_forward.py",
            "src/ai4binance/tuning/engine.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/validation/recovery_queue.py",),
        "production_evidence_files": (
            "runtime/artifacts/validation/recovery-queue-latest.json",
        ),
        "missing_controls": (
            "REAL_MULTI_REGIME_HOTUSDT_OOS_ARTIFACT_MISSING",
            "PAPER_TRADING_PROMOTION_EVIDENCE_MISSING",
        ),
        "proposed_diff": (
            "ADD validation run queue for recovery candidates",
            "ADD YKB OOS evidence summary",
        ),
        "risk": "HIGH",
    },
    {
        "capability_id": "VNEXT-08-SPOT-FUTURES-SCANNER",
        "title": "Spot/Futures opportunity scanner and candidate ranking",
        "phase": "Faz 6",
        "priority": "P1",
        "evidence_files": (
            "src/ai4binance/cli/status.py",
            "src/ai4binance/opportunity_scanner.py",
            "src/ai4binance/universe/token_risk.py",
            "src/ai4binance/whale_fusion/fusion.py",
            "src/ai4binance/opportunities.py",
            "tests/test_opportunity_scanner.py",
        ),
        "complete_when": (
            "src/ai4binance/opportunity_scanner.py",
            "src/ai4binance/universe/token_risk.py",
            "tests/test_opportunity_scanner.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/cli/status.py",),
        "production_evidence_files": (
            "runtime/artifacts/decisions/scanner/scan-latest.json",
        ),
        "missing_controls": (),
        "proposed_diff": (
            "CREATE opportunity_scanner.py",
            "ADD scan ranking tests",
        ),
        "risk": "MEDIUM",
    },
    {
        "capability_id": "VNEXT-09-MULTIOPS-RUNNER-ADMISSION",
        "title": "MultiOps runner admission and persistent evidence chain",
        "phase": "Faz 10",
        "priority": "P1",
        "evidence_files": (
            "src/ai4binance/ops/jobs.py",
            "src/ai4binance/enterprise/multiops_control.py",
            "tests/test_agent_runtime_governance.py",
            "tests/test_enterprise_multiops_control.py",
        ),
        "complete_when": (
            "src/ai4binance/ops/jobs.py",
            "src/ai4binance/enterprise/multiops_control.py",
            "tests/test_agent_runtime_governance.py",
            "tests/test_enterprise_multiops_control.py",
        ),
        "runtime_wiring_files": ("src/ai4binance/enterprise/multiops_control.py",),
        "production_evidence_files": (),
        "missing_controls": (),
        "proposed_diff": (
            "MODIFY ops/jobs.py",
            "MODIFY enterprise/multiops_control.py",
        ),
        "risk": "MEDIUM",
    },
)


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


_PRODUCTION_EVIDENCE_MAXIMUM_BYTES = 500_000
_PRODUCTION_EVIDENCE_RULES: dict[str, tuple[str, timedelta]] = {
    "VNEXT-01-LOCAL-QWEN": ("updated_at", timedelta(minutes=10)),
    "VNEXT-02-RECOVERY-RADAR": ("observed_at", timedelta(hours=24)),
    "VNEXT-05-REALTIME-DATA-PLANE": (
        "measurement.measured_at",
        timedelta(hours=24),
    ),
    "VNEXT-06-RISK-CAPITAL": ("observed_at", timedelta(hours=24)),
    "VNEXT-07-OOS-AUTOML": ("generated_at_utc", timedelta(hours=24)),
    "VNEXT-08-SPOT-FUTURES-SCANNER": (
        "observed_at",
        timedelta(minutes=30),
    ),
}


def _production_evidence_blockers(
    root: Path,
    *,
    capability_id: str,
    evidence_files: tuple[str, ...],
    observed_at: datetime,
) -> tuple[str, ...]:
    if not evidence_files:
        return ()
    blockers: list[str] = []
    for relative_path in evidence_files:
        payload, load_blocker = _load_production_evidence(root, relative_path)
        if load_blocker is not None:
            blockers.append(load_blocker)
            continue
        if payload is None:
            blockers.append("PRODUCTION_EVIDENCE_INVALID")
            continue
        if (
            payload.get("execution_allowed") is not False
            or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            blockers.append("PRODUCTION_EVIDENCE_UNSAFE_AUTHORITY")
            continue
        rule = _PRODUCTION_EVIDENCE_RULES.get(capability_id)
        if rule is not None:
            timestamp_field, maximum_age = rule
            timestamp = _nested_value(payload, timestamp_field)
            parsed_timestamp = _parse_evidence_timestamp(timestamp)
            if parsed_timestamp is None:
                blockers.append("PRODUCTION_EVIDENCE_TIMESTAMP_INVALID")
            else:
                age = observed_at - parsed_timestamp
                if age < timedelta(minutes=-5) or age > maximum_age:
                    blockers.append("PRODUCTION_EVIDENCE_STALE")
        blockers.extend(_semantic_production_evidence_blockers(capability_id, payload))
    return tuple(dict.fromkeys(blockers))


def _load_production_evidence(
    root: Path,
    relative_path: str,
) -> tuple[Mapping[str, object] | None, str | None]:
    source = root / relative_path
    if source.is_symlink():
        return None, "PRODUCTION_EVIDENCE_SYMLINK_REJECTED"
    resolved_root = root.resolve()
    try:
        resolved_source = source.resolve(strict=True)
        resolved_source.relative_to(resolved_root)
    except FileNotFoundError:
        return None, "PRODUCTION_EVIDENCE_INCOMPLETE"
    except ValueError:
        return None, "PRODUCTION_EVIDENCE_OUTSIDE_ROOT"
    if not resolved_source.is_file():
        return None, "PRODUCTION_EVIDENCE_NOT_FILE"
    if resolved_source.stat().st_size > _PRODUCTION_EVIDENCE_MAXIMUM_BYTES:
        return None, "PRODUCTION_EVIDENCE_TOO_LARGE"
    try:
        payload = json.loads(resolved_source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "PRODUCTION_EVIDENCE_INVALID_JSON"
    if not isinstance(payload, Mapping):
        return None, "PRODUCTION_EVIDENCE_SCHEMA_INVALID"
    return payload, None


def _nested_value(payload: Mapping[str, object], dotted_path: str) -> object:
    value: object = payload
    for segment in dotted_path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(segment)
    return value


def _parse_evidence_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _semantic_production_evidence_blockers(
    capability_id: str,
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    validators = {
        "VNEXT-01-LOCAL-QWEN": _local_qwen_evidence_blockers,
        "VNEXT-02-RECOVERY-RADAR": _recovery_radar_evidence_blockers,
        "VNEXT-05-REALTIME-DATA-PLANE": _realtime_data_plane_evidence_blockers,
        "VNEXT-06-RISK-CAPITAL": _risk_capital_evidence_blockers,
        "VNEXT-07-OOS-AUTOML": _oos_automl_evidence_blockers,
        "VNEXT-08-SPOT-FUTURES-SCANNER": _scanner_evidence_blockers,
    }
    validator = validators.get(capability_id)
    return () if validator is None else validator(payload)


def _local_qwen_evidence_blockers(payload: Mapping[str, object]) -> tuple[str, ...]:
    endpoint = payload.get("endpoint")
    listener_pids = payload.get("listener_pids")
    provider_pid = payload.get("provider_pid")
    blockers: list[str] = []
    if payload.get("status") != "RUNNING" or payload.get("blockers") not in ([], ()):
        blockers.append("QWEN_RUNTIME_NOT_HEALTHY")
    if not isinstance(endpoint, str) or not _is_loopback_endpoint(endpoint):
        blockers.append("QWEN_LOOPBACK_ENDPOINT_NOT_VERIFIED")
    if not isinstance(listener_pids, list) or not listener_pids:
        blockers.append("QWEN_LISTENER_NOT_VERIFIED")
    if (
        not isinstance(provider_pid, int)
        or isinstance(provider_pid, bool)
        or provider_pid <= 0
    ):
        blockers.append("QWEN_PROVIDER_PROCESS_NOT_VERIFIED")
    return tuple(blockers)


def _is_loopback_endpoint(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    except ValueError:
        return False


def _recovery_radar_evidence_blockers(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    status = payload.get("recovery_radar_status")
    reference = payload.get("recovery_radar_ref")
    if status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
        return ("RECOVERY_RADAR_NOT_EXECUTED",)
    if not isinstance(reference, str) or not reference.strip():
        return ("RECOVERY_RADAR_REFERENCE_MISSING",)
    return ()


def _realtime_data_plane_evidence_blockers(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    measurement = payload.get("measurement")
    if not isinstance(measurement, Mapping):
        return ("EVENT_LEVEL_LATENCY_EVIDENCE_INVALID",)
    samples = measurement.get("samples_ns_per_operation")
    if measurement.get("benchmark_name") not in {
        "market-data-event-latency",
        "public-stream-event-latency",
    }:
        return ("EVENT_LEVEL_LATENCY_DOMAIN_MISMATCH",)
    if not isinstance(samples, list) or not samples:
        return ("EVENT_LEVEL_LATENCY_SAMPLES_MISSING",)
    revision = measurement.get("code_revision")
    if not isinstance(revision, str) or revision in {"", "workspace-local"}:
        return ("EVENT_LEVEL_LATENCY_SUBJECT_UNBOUND",)
    return ()


def _risk_capital_evidence_blockers(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    financial = payload.get("financial_situation")
    wallet = payload.get("wallet_position_management")
    if not isinstance(financial, Mapping) or financial.get("status") != "READY":
        return ("ACCOUNT_WIDE_RECONCILIATION_NOT_READY",)
    if not isinstance(wallet, Mapping) or wallet.get("status") not in {
        "READY",
        "READY_FOR_REVIEW",
    }:
        return ("WALLET_POSITION_MANAGEMENT_NOT_READY",)
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        return ("RISK_CAPITAL_BLOCKERS_INVALID",)
    unsafe_prefixes = (
        "accounting:",
        "runtime:PORTFOLIO_",
        "runtime:SYMBOL_EXPOSURE_",
        "runtime:CORRELATION_GROUP_",
        "runtime:STRATEGY_EXPOSURE_",
        "WALLET_POSITION_",
    )
    if any(
        isinstance(blocker, str) and blocker.startswith(unsafe_prefixes)
        for blocker in blockers
    ):
        return ("RISK_CAPITAL_RUNTIME_BLOCKERS_PRESENT",)
    return ()


def _oos_automl_evidence_blockers(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    blockers = payload.get("blockers")
    items = payload.get("items")
    if payload.get("status") not in {"READY", "COMPLETE", "QUEUED"}:
        return ("OOS_AUTOML_RUNTIME_BLOCKED",)
    if not isinstance(blockers, list) or any(
        blocker != "LIVE_ORDER_BLOCKED" for blocker in blockers
    ):
        return ("OOS_AUTOML_EVIDENCE_BLOCKERS_PRESENT",)
    if not isinstance(items, list):
        return ("OOS_AUTOML_QUEUE_INVALID",)
    return ()


def _scanner_evidence_blockers(payload: Mapping[str, object]) -> tuple[str, ...]:
    blockers = payload.get("blockers")
    funnel = payload.get("funnel")
    if payload.get("status") not in {"READY", "COMPLETE"}:
        return ("SCANNER_RUNTIME_BLOCKED",)
    if not isinstance(blockers, list) or any(
        blocker != "LIVE_ORDER_BLOCKED" for blocker in blockers
    ):
        return ("SCANNER_EVIDENCE_BLOCKERS_PRESENT",)
    if not isinstance(funnel, Mapping):
        return ("SCANNER_FUNNEL_INVALID",)
    scanned = funnel.get("symbols_scanned")
    if not isinstance(scanned, int) or isinstance(scanned, bool) or scanned <= 0:
        return ("SCANNER_SYMBOL_COVERAGE_EMPTY",)
    return ()

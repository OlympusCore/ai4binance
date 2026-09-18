"""Registry-derived architecture and critical-behavior coverage evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from ai4binance.governance.architecture import (
    LogicalArchitectureComponent,
    LogicalArchitectureRegistry,
)
from ai4binance.reporting import to_primitive

_ARCHITECTURE_STATES = frozenset(
    {
        "IMPLEMENTED_AND_COVERED",
        "IMPLEMENTED_TEST_GAP",
        "DECLARED_IMPLEMENTATION_GAP",
        "TEST_WITHOUT_DECLARED_OWNER",
        "NOT_MEASURED",
        "RUNTIME_UNKNOWN",
        "STALE_EVIDENCE",
    }
)
_BEHAVIOR_STATES = frozenset(
    {
        "RESOLVED",
        "ASSERTION_GAP",
        "IMPLEMENTED_TEST_GAP",
        "DECLARED_IMPLEMENTATION_GAP",
        "NOT_MEASURED",
        "RELATION_PROOF_GAP",
        "RUNTIME_EVIDENCE_UNKNOWN",
        "STALE_EVIDENCE",
    }
)
_RELATION_STATES = frozenset(
    {
        "NOT_REQUIRED",
        "DECLARATION_MISSING",
        "TEST_PROOF_MISSING",
        "RUNTIME_HANDOFF_UNKNOWN",
        "PROVEN",
    }
)
_RUNTIME_EVIDENCE_STATES = frozenset({"NOT_REQUIRED", "UNKNOWN", "PROVEN"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceCoverage(Protocol):
    """Minimal file-coverage contract consumed by the resolver."""

    @property
    def path(self) -> str: ...

    @property
    def statements(self) -> int: ...

    @property
    def covered_lines(self) -> int: ...

    @property
    def branches(self) -> int: ...

    @property
    def covered_branches(self) -> int: ...


@dataclass(frozen=True, slots=True)
class ArchitectureTargetConfig:
    """One critical target selected from canonical registry metadata."""

    name: str
    tier: str
    canonical_domains: tuple[str, ...]
    component_ids: tuple[str, ...] = ()
    required_relation_ids: tuple[str, ...] = ()
    requires_runtime_evidence: bool = False
    evidence_refs: tuple[str, ...] = ()
    priority: str = "P2"
    authority_class: str = "EVIDENCE"
    economic_impact: str = "LOW"
    execution_impact: str = "LOW"
    blast_radius: str = "LOW"

    def __post_init__(self) -> None:
        _require_identifier("architecture target", self.name)
        if self.tier not in {"T0", "T1", "T2", "T3", "T4"}:
            raise ValueError("architecture target tier is invalid")
        _require_unique_texts(
            "architecture target canonical_domains", self.canonical_domains
        )
        _require_unique_texts(
            "architecture target component_ids", self.component_ids, allow_empty=True
        )
        _require_unique_texts(
            "architecture target required_relation_ids",
            self.required_relation_ids,
            allow_empty=True,
        )
        _require_unique_texts(
            "architecture target evidence_refs", self.evidence_refs, allow_empty=True
        )
        for component_id in self.component_ids:
            _require_identifier("architecture target component_id", component_id)
        for relation_id in self.required_relation_ids:
            _require_identifier("architecture target relation_id", relation_id)
        for evidence_ref in self.evidence_refs:
            _require_repository_path("architecture target evidence_ref", evidence_ref)
        if self.priority not in {"P0", "P1", "P2", "P3"}:
            raise ValueError("architecture target priority is invalid")
        for label, value in (
            ("architecture target authority_class", self.authority_class),
            ("architecture target economic_impact", self.economic_impact),
            ("architecture target execution_impact", self.execution_impact),
            ("architecture target blast_radius", self.blast_radius),
        ):
            _require_text(label, value)


@dataclass(frozen=True, slots=True)
class RelationProofConfig:
    """Behavioral proof mapping for one canonical registry relation."""

    relation_id: str
    test_assertion_refs: tuple[str, ...]
    expected_outcome: str
    requires_runtime_evidence: bool = False
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier("relation proof relation_id", self.relation_id)
        _require_text("relation proof expected_outcome", self.expected_outcome)
        _require_unique_texts(
            "relation proof test_assertion_refs", self.test_assertion_refs
        )
        _require_unique_texts(
            "relation proof evidence_refs", self.evidence_refs, allow_empty=True
        )
        for assertion_ref in self.test_assertion_refs:
            _require_assertion_ref("relation proof test_assertion_ref", assertion_ref)
        for evidence_ref in self.evidence_refs:
            _require_repository_path("relation proof evidence_ref", evidence_ref)


@dataclass(frozen=True, slots=True)
class CriticalBehaviorObligationConfig:
    """A fail-closed behavioral proof obligation owned by a registry component."""

    obligation_id: str
    category: str
    component_id: str
    requirement_ref: str
    expected_outcome: str
    test_assertion_refs: tuple[str, ...] = ()
    required_relation_ids: tuple[str, ...] = ()
    requires_runtime_evidence: bool = True
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("critical behavior obligation", self.obligation_id),
            ("critical behavior category", self.category),
            ("critical behavior component_id", self.component_id),
            ("critical behavior requirement_ref", self.requirement_ref),
            ("critical behavior expected_outcome", self.expected_outcome),
        ):
            _require_text(label, value)
        _require_unique_texts(
            "critical behavior evidence_refs", self.evidence_refs, allow_empty=True
        )
        _require_unique_texts(
            "critical behavior test_assertion_refs",
            self.test_assertion_refs,
            allow_empty=True,
        )
        _require_unique_texts(
            "critical behavior required_relation_ids",
            self.required_relation_ids,
            allow_empty=True,
        )
        _require_repository_path(
            "critical behavior requirement_ref", self.requirement_ref
        )
        for evidence_ref in self.evidence_refs:
            _require_repository_path("critical behavior evidence_ref", evidence_ref)
        for assertion_ref in self.test_assertion_refs:
            _require_assertion_ref(
                "critical behavior test_assertion_ref", assertion_ref
            )
        for relation_id in self.required_relation_ids:
            _require_identifier("critical behavior relation_id", relation_id)


@dataclass(frozen=True, slots=True)
class CoverageArchitectureConfig:
    """Executable architecture-assurance selectors and thresholds."""

    registry_path: str
    statement_minimum: float
    branch_minimum: float
    targets: tuple[ArchitectureTargetConfig, ...]
    obligations: tuple[CriticalBehaviorObligationConfig, ...]
    relation_proofs: tuple[RelationProofConfig, ...] = ()

    def __post_init__(self) -> None:
        _require_repository_path("architecture registry_path", self.registry_path)
        _require_percent("architecture statement_minimum", self.statement_minimum)
        _require_percent("architecture branch_minimum", self.branch_minimum)
        if not self.targets:
            raise ValueError("architecture assurance requires critical targets")
        if not self.obligations:
            raise ValueError("architecture assurance requires behavior obligations")
        _require_unique(
            "architecture target names", tuple(target.name for target in self.targets)
        )
        domains = tuple(
            domain for target in self.targets for domain in target.canonical_domains
        )
        _require_unique("architecture target canonical domains", domains)
        _require_unique(
            "critical behavior obligation IDs",
            tuple(obligation.obligation_id for obligation in self.obligations),
        )
        _require_unique(
            "relation proof IDs",
            tuple(proof.relation_id for proof in self.relation_proofs),
        )
        declared_proofs = {proof.relation_id for proof in self.relation_proofs}
        required_relations = {
            relation_id
            for target in self.targets
            for relation_id in target.required_relation_ids
        } | {
            relation_id
            for obligation in self.obligations
            for relation_id in obligation.required_relation_ids
        }
        missing_proofs = sorted(required_relations - declared_proofs)
        if missing_proofs:
            raise ValueError(
                "architecture assurance relation proofs are missing: "
                + ", ".join(missing_proofs)
            )


@dataclass(frozen=True, slots=True)
class ArchitectureCoverageRow:
    """Coverage and traceability status for one registry-derived component."""

    target: str
    tier: str
    component_id: str | None
    canonical_domain: str
    logical_plane: str
    source_refs: tuple[str, ...]
    contract_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    statement_coverage: float | None
    branch_coverage: float | None
    relation_ids: tuple[str, ...]
    relation_status: str
    runtime_evidence: str
    state: str

    def __post_init__(self) -> None:
        if self.state not in _ARCHITECTURE_STATES:
            raise ValueError("architecture coverage state is invalid")
        if self.relation_status not in _RELATION_STATES:
            raise ValueError("architecture relation proof state is invalid")
        if self.runtime_evidence not in _RUNTIME_EVIDENCE_STATES:
            raise ValueError("architecture runtime evidence state is invalid")


@dataclass(frozen=True, slots=True)
class CriticalBehaviorCoverageRow:
    """Resolved evidence for one canonical negative-behavior obligation."""

    obligation_id: str
    category: str
    component_id: str
    owner: str
    requirement_ref: str
    source_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    assertion_refs: tuple[str, ...]
    relation_ids: tuple[str, ...]
    relation_status: str
    evidence_refs: tuple[str, ...]
    expected_outcome: str
    covered: bool
    asserted: bool
    runtime_required: bool
    runtime_proven: bool
    state: str

    def __post_init__(self) -> None:
        if self.state not in _BEHAVIOR_STATES:
            raise ValueError("critical behavior coverage state is invalid")
        if self.relation_status not in _RELATION_STATES:
            raise ValueError("critical behavior relation proof state is invalid")


@dataclass(frozen=True, slots=True)
class CoverageArchitectureReport:
    """Unified, non-authoritative architecture-assurance evidence."""

    registry_id: str
    registry_version: str
    registry_path: str
    generated_at_utc: datetime
    architecture_view: tuple[ArchitectureCoverageRow, ...]
    critical_behavior_view: tuple[CriticalBehaviorCoverageRow, ...]
    architecture_failures: tuple[str, ...]
    critical_behavior_failures: tuple[str, ...]
    result: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.result not in {"PASS", "BASELINE_DEBT"}:
            raise ValueError("architecture assurance result is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("architecture assurance cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


def load_coverage_architecture_config(
    payload: object,
) -> CoverageArchitectureConfig | None:
    """Load the optional architecture-assurance section from coverage config."""
    if payload is None:
        return None
    root = _mapping(payload, "architecture_assurance")
    targets_payload = _mapping(
        root.get("critical_target_groups"),
        "architecture_assurance.critical_target_groups",
    )
    obligations_payload = root.get("critical_behavior_obligations")
    if not isinstance(obligations_payload, list):
        raise ValueError(
            "architecture_assurance.critical_behavior_obligations must be a list"
        )
    targets = tuple(
        ArchitectureTargetConfig(
            name=str(name),
            tier=str(_mapping(raw, f"critical_target_groups.{name}").get("tier", "")),
            canonical_domains=_strings(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "canonical_domains"
                ),
                f"critical_target_groups.{name}.canonical_domains",
            ),
            component_ids=_optional_strings(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "component_ids", ()
                ),
                f"critical_target_groups.{name}.component_ids",
            ),
            required_relation_ids=_optional_strings(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "required_relation_ids", ()
                ),
                f"critical_target_groups.{name}.required_relation_ids",
            ),
            requires_runtime_evidence=_optional_bool(
                _mapping(raw, f"critical_target_groups.{name}"),
                "requires_runtime_evidence",
                False,
                f"critical_target_groups.{name}",
            ),
            evidence_refs=_optional_strings(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "evidence_refs", ()
                ),
                f"critical_target_groups.{name}.evidence_refs",
            ),
            priority=str(
                _mapping(raw, f"critical_target_groups.{name}").get("priority", "P2")
            ),
            authority_class=str(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "authority_class", "EVIDENCE"
                )
            ),
            economic_impact=str(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "economic_impact", "LOW"
                )
            ),
            execution_impact=str(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "execution_impact", "LOW"
                )
            ),
            blast_radius=str(
                _mapping(raw, f"critical_target_groups.{name}").get(
                    "blast_radius", "LOW"
                )
            ),
        )
        for name, raw in targets_payload.items()
    )
    relation_proofs_payload = root.get("relation_proofs", [])
    if not isinstance(relation_proofs_payload, list):
        raise ValueError("architecture_assurance.relation_proofs must be a list")
    relation_proofs = tuple(
        _relation_proof(raw, index) for index, raw in enumerate(relation_proofs_payload)
    )
    obligations = tuple(
        _behavior_obligation(raw, index)
        for index, raw in enumerate(obligations_payload)
    )
    return CoverageArchitectureConfig(
        registry_path=str(root.get("registry_path", "")),
        statement_minimum=float(root.get("statement_minimum", -1.0)),
        branch_minimum=float(root.get("branch_minimum", -1.0)),
        targets=targets,
        obligations=obligations,
        relation_proofs=relation_proofs,
    )


def evaluate_coverage_architecture(
    config: CoverageArchitectureConfig,
    registry: LogicalArchitectureRegistry,
    file_coverage: Sequence[SourceCoverage],
    *,
    repository_root: Path,
    coverage_generated_at: datetime | None = None,
    generated_at: datetime | None = None,
) -> CoverageArchitectureReport:
    """Resolve registry references into deterministic coverage-assurance views."""
    root = repository_root.resolve()
    coverage_by_path = {_normalize_path(row.path): row for row in file_coverage}
    component_by_id = {
        component.component_id: component for component in registry.components
    }
    target_by_name = {target.name: target for target in config.targets}
    relation_proof_by_id = {
        proof.relation_id: proof for proof in config.relation_proofs
    }
    architecture_rows: list[ArchitectureCoverageRow] = []
    row_by_component: dict[str, ArchitectureCoverageRow] = {}
    for target in config.targets:
        components = (
            tuple(
                component_by_id[component_id]
                for component_id in target.component_ids
                if component_id in component_by_id
            )
            if target.component_ids
            else tuple(
                component
                for component in registry.components
                if component.canonical_domain in target.canonical_domains
            )
        )
        missing_component_ids = tuple(
            component_id
            for component_id in target.component_ids
            if component_id not in component_by_id
        )
        for component_id in missing_component_ids:
            architecture_rows.append(
                ArchitectureCoverageRow(
                    target=target.name,
                    tier=target.tier,
                    component_id=component_id,
                    canonical_domain=",".join(target.canonical_domains),
                    logical_plane="NOT_DECLARED",
                    source_refs=(),
                    contract_refs=(),
                    test_refs=(),
                    statement_coverage=None,
                    branch_coverage=None,
                    relation_ids=target.required_relation_ids,
                    relation_status="DECLARATION_MISSING",
                    runtime_evidence=(
                        "UNKNOWN"
                        if target.requires_runtime_evidence
                        else "NOT_REQUIRED"
                    ),
                    state="DECLARED_IMPLEMENTATION_GAP",
                )
            )
        if not components:
            if not missing_component_ids:
                architecture_rows.append(
                    ArchitectureCoverageRow(
                        target=target.name,
                        tier=target.tier,
                        component_id=None,
                        canonical_domain=",".join(target.canonical_domains),
                        logical_plane="NOT_DECLARED",
                        source_refs=(),
                        contract_refs=(),
                        test_refs=(),
                        statement_coverage=None,
                        branch_coverage=None,
                        relation_ids=target.required_relation_ids,
                        relation_status=(
                            "DECLARATION_MISSING"
                            if target.required_relation_ids
                            else "NOT_REQUIRED"
                        ),
                        runtime_evidence=(
                            "UNKNOWN"
                            if target.requires_runtime_evidence
                            else "NOT_REQUIRED"
                        ),
                        state="NOT_MEASURED",
                    )
                )
            continue
        for component in components:
            row = _architecture_row(
                config,
                registry,
                target,
                component,
                coverage_by_path,
                root,
                coverage_generated_at,
            )
            architecture_rows.append(row)
            row_by_component[component.component_id] = row

    relation_resolved_rows: list[ArchitectureCoverageRow] = []
    for row in architecture_rows:
        relation_status = _relation_status(
            target_by_name[row.target],
            registry,
            relation_proof_by_id,
            root,
            coverage_generated_at,
        )
        relation_resolved_rows.append(
            replace(
                row,
                relation_status=relation_status,
                state=_architecture_state_with_relation(row.state, relation_status),
            )
        )
    architecture_rows = relation_resolved_rows
    row_by_component = {
        row.component_id: row
        for row in architecture_rows
        if row.component_id is not None
    }

    behavior_rows = tuple(
        _critical_behavior_row(
            obligation,
            component_by_id,
            row_by_component,
            registry,
            relation_proof_by_id,
            root,
            coverage_generated_at,
        )
        for obligation in config.obligations
    )
    ordered_architecture = tuple(
        sorted(
            architecture_rows,
            key=lambda row: (row.tier, row.target, row.component_id or ""),
        )
    )
    architecture_failures = tuple(
        f"{row.target}:{row.component_id or 'NOT_DECLARED'}:{row.state}"
        for row in ordered_architecture
        if row.state != "IMPLEMENTED_AND_COVERED"
    )
    critical_behavior_failures = tuple(
        f"{row.obligation_id}:{row.state}"
        for row in behavior_rows
        if row.state != "RESOLVED"
    )
    return CoverageArchitectureReport(
        registry_id=registry.registry_id,
        registry_version=registry.version,
        registry_path=config.registry_path,
        generated_at_utc=generated_at or datetime.now(UTC),
        architecture_view=ordered_architecture,
        critical_behavior_view=behavior_rows,
        architecture_failures=architecture_failures,
        critical_behavior_failures=critical_behavior_failures,
        result=(
            "PASS"
            if not architecture_failures and not critical_behavior_failures
            else "BASELINE_DEBT"
        ),
    )


def _architecture_row(
    config: CoverageArchitectureConfig,
    registry: LogicalArchitectureRegistry,
    target: ArchitectureTargetConfig,
    component: LogicalArchitectureComponent,
    coverage_by_path: dict[str, SourceCoverage],
    root: Path,
    coverage_generated_at: datetime | None,
) -> ArchitectureCoverageRow:
    source_refs = tuple(_normalize_path(path) for path in component.source_paths)
    contract_refs = tuple(_normalize_path(path) for path in component.contract_refs)
    test_refs = tuple(_normalize_path(path) for path in component.test_refs)
    missing_sources = _missing_paths(root, source_refs)
    missing_contracts = _missing_paths(root, contract_refs)
    missing_tests = _missing_paths(root, test_refs)
    measured = tuple(
        coverage_by_path[path] for path in source_refs if path in coverage_by_path
    )
    statement_coverage, branch_coverage = _aggregate_coverage(measured)
    stale = _has_newer_reference(
        root,
        (*source_refs, *contract_refs, *test_refs),
        coverage_generated_at,
    )
    domain_matches = component.canonical_domain in target.canonical_domains
    runtime_evidence = _runtime_evidence_status(
        required=target.requires_runtime_evidence,
        evidence_refs=target.evidence_refs,
        evidence_kind="component",
        evidence_id=component.component_id,
        component_id=component.component_id,
        root=root,
        coverage_generated_at=coverage_generated_at,
        reference_paths=(*source_refs, *test_refs),
    )
    if not domain_matches or missing_sources or missing_contracts:
        state = "DECLARED_IMPLEMENTATION_GAP"
    elif missing_tests:
        state = "IMPLEMENTED_TEST_GAP"
    elif len(measured) != len(source_refs):
        state = "NOT_MEASURED"
    elif stale:
        state = "STALE_EVIDENCE"
    elif _below_minimum(config, statement_coverage, branch_coverage):
        state = "IMPLEMENTED_TEST_GAP"
    elif runtime_evidence == "UNKNOWN":
        state = "RUNTIME_UNKNOWN"
    else:
        state = "IMPLEMENTED_AND_COVERED"
    return ArchitectureCoverageRow(
        target=target.name,
        tier=target.tier,
        component_id=component.component_id,
        canonical_domain=component.canonical_domain,
        logical_plane=component.logical_plane,
        source_refs=source_refs,
        contract_refs=contract_refs,
        test_refs=test_refs,
        statement_coverage=statement_coverage,
        branch_coverage=branch_coverage,
        relation_ids=target.required_relation_ids,
        relation_status=(
            "TEST_PROOF_MISSING" if target.required_relation_ids else "NOT_REQUIRED"
        ),
        runtime_evidence=runtime_evidence,
        state=state,
    )


def _critical_behavior_row(
    obligation: CriticalBehaviorObligationConfig,
    component_by_id: dict[str, Any],
    row_by_component: dict[str, ArchitectureCoverageRow],
    registry: LogicalArchitectureRegistry,
    relation_proof_by_id: dict[str, RelationProofConfig],
    root: Path,
    coverage_generated_at: datetime | None,
) -> CriticalBehaviorCoverageRow:
    component = component_by_id.get(obligation.component_id)
    architecture_row = row_by_component.get(obligation.component_id)
    if component is None or architecture_row is None:
        return CriticalBehaviorCoverageRow(
            obligation_id=obligation.obligation_id,
            category=obligation.category,
            component_id=obligation.component_id,
            owner="NOT_DECLARED",
            requirement_ref=_normalize_path(obligation.requirement_ref),
            source_refs=(),
            test_refs=(),
            assertion_refs=obligation.test_assertion_refs,
            relation_ids=obligation.required_relation_ids,
            relation_status=(
                "DECLARATION_MISSING"
                if obligation.required_relation_ids
                else "NOT_REQUIRED"
            ),
            evidence_refs=tuple(map(_normalize_path, obligation.evidence_refs)),
            expected_outcome=obligation.expected_outcome,
            covered=False,
            asserted=False,
            runtime_required=obligation.requires_runtime_evidence,
            runtime_proven=False,
            state="DECLARED_IMPLEMENTATION_GAP",
        )
    requirement_ref = _normalize_path(obligation.requirement_ref)
    evidence_refs = tuple(map(_normalize_path, obligation.evidence_refs))
    assertion_refs = tuple(
        map(_normalize_assertion_ref, obligation.test_assertion_refs)
    )
    assertion_paths = tuple(ref.split("::", 1)[0] for ref in assertion_refs)
    tests_exist = bool(assertion_refs) and not _missing_paths(root, assertion_paths)
    requirement_exists = not _missing_paths(root, (requirement_ref,))
    asserted = tests_exist and all(
        _test_assertion_proven(root, assertion_ref, obligation.expected_outcome)
        for assertion_ref in assertion_refs
    )
    relation_status = _relation_proof_status(
        obligation.required_relation_ids,
        registry,
        relation_proof_by_id,
        root,
        coverage_generated_at,
    )
    runtime_status = _runtime_evidence_status(
        required=obligation.requires_runtime_evidence,
        evidence_refs=evidence_refs,
        evidence_kind="obligation",
        evidence_id=obligation.obligation_id,
        component_id=obligation.component_id,
        root=root,
        coverage_generated_at=coverage_generated_at,
        reference_paths=(*architecture_row.source_refs, *assertion_paths),
    )
    runtime_proven = runtime_status == "PROVEN"
    covered = architecture_row.state == "IMPLEMENTED_AND_COVERED"
    if not requirement_exists:
        state = "DECLARED_IMPLEMENTATION_GAP"
    elif architecture_row.state == "DECLARED_IMPLEMENTATION_GAP":
        state = "DECLARED_IMPLEMENTATION_GAP"
    elif architecture_row.state == "STALE_EVIDENCE":
        state = "STALE_EVIDENCE"
    elif architecture_row.state == "NOT_MEASURED":
        state = "NOT_MEASURED"
    elif not tests_exist or not covered:
        state = "IMPLEMENTED_TEST_GAP"
    elif not asserted:
        state = "ASSERTION_GAP"
    elif relation_status not in {"NOT_REQUIRED", "PROVEN"}:
        state = "RELATION_PROOF_GAP"
    elif obligation.requires_runtime_evidence and not runtime_proven:
        state = "RUNTIME_EVIDENCE_UNKNOWN"
    else:
        state = "RESOLVED"
    return CriticalBehaviorCoverageRow(
        obligation_id=obligation.obligation_id,
        category=obligation.category,
        component_id=obligation.component_id,
        owner=component.owner,
        requirement_ref=requirement_ref,
        source_refs=architecture_row.source_refs,
        test_refs=assertion_paths,
        assertion_refs=assertion_refs,
        relation_ids=obligation.required_relation_ids,
        relation_status=relation_status,
        evidence_refs=evidence_refs,
        expected_outcome=obligation.expected_outcome,
        covered=covered,
        asserted=asserted,
        runtime_required=obligation.requires_runtime_evidence,
        runtime_proven=runtime_proven,
        state=state,
    )


def _aggregate_coverage(
    rows: Sequence[SourceCoverage],
) -> tuple[float | None, float | None]:
    if not rows:
        return None, None
    statements = sum(row.statements for row in rows)
    covered_lines = sum(row.covered_lines for row in rows)
    branches = sum(row.branches for row in rows)
    covered_branches = sum(row.covered_branches for row in rows)
    statement_coverage = (
        round(covered_lines / statements * 100, 2) if statements else 100.0
    )
    branch_coverage = round(covered_branches / branches * 100, 2) if branches else None
    return statement_coverage, branch_coverage


def _relation_status(
    target: ArchitectureTargetConfig,
    registry: LogicalArchitectureRegistry,
    relation_proof_by_id: dict[str, RelationProofConfig],
    root: Path,
    coverage_generated_at: datetime | None,
) -> str:
    return _relation_proof_status(
        target.required_relation_ids,
        registry,
        relation_proof_by_id,
        root,
        coverage_generated_at,
    )


def _architecture_state_with_relation(state: str, relation_status: str) -> str:
    if state != "IMPLEMENTED_AND_COVERED":
        return state
    if relation_status == "DECLARATION_MISSING":
        return "DECLARED_IMPLEMENTATION_GAP"
    if relation_status == "TEST_PROOF_MISSING":
        return "IMPLEMENTED_TEST_GAP"
    if relation_status == "RUNTIME_HANDOFF_UNKNOWN":
        return "RUNTIME_UNKNOWN"
    return state


def _relation_proof_status(
    relation_ids: tuple[str, ...],
    registry: LogicalArchitectureRegistry,
    relation_proof_by_id: dict[str, RelationProofConfig],
    root: Path,
    coverage_generated_at: datetime | None,
) -> str:
    if not relation_ids:
        return "NOT_REQUIRED"
    declared = {relation.relation_id for relation in registry.relations}
    if any(relation_id not in declared for relation_id in relation_ids):
        return "DECLARATION_MISSING"
    proofs = tuple(
        relation_proof_by_id.get(relation_id) for relation_id in relation_ids
    )
    if any(proof is None for proof in proofs):
        return "TEST_PROOF_MISSING"
    resolved_proofs = cast(tuple[RelationProofConfig, ...], proofs)
    if any(
        not all(
            _test_assertion_proven(root, ref, proof.expected_outcome)
            for ref in proof.test_assertion_refs
        )
        for proof in resolved_proofs
    ):
        return "TEST_PROOF_MISSING"
    if any(
        _runtime_evidence_status(
            required=proof.requires_runtime_evidence,
            evidence_refs=proof.evidence_refs,
            evidence_kind="relation",
            evidence_id=proof.relation_id,
            component_id="",
            root=root,
            coverage_generated_at=coverage_generated_at,
            reference_paths=tuple(
                ref.split("::", 1)[0] for ref in proof.test_assertion_refs
            ),
        )
        == "UNKNOWN"
        for proof in resolved_proofs
    ):
        return "RUNTIME_HANDOFF_UNKNOWN"
    return "PROVEN"


def _test_assertion_proven(
    root: Path, assertion_ref: str, expected_outcome: str
) -> bool:
    normalized = _normalize_assertion_ref(assertion_ref)
    path_text, function_name = normalized.split("::", 1)
    try:
        source = (root / path_text).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeError):
        return False
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ),
        None,
    )
    if function is None:
        return False
    return any(
        isinstance(node, ast.Assert)
        and expected_outcome in ast.dump(node.test, include_attributes=False)
        for node in ast.walk(function)
    )


def _runtime_evidence_status(
    *,
    required: bool,
    evidence_refs: tuple[str, ...],
    evidence_kind: str,
    evidence_id: str,
    component_id: str,
    root: Path,
    coverage_generated_at: datetime | None,
    reference_paths: tuple[str, ...],
) -> str:
    if not required:
        return "NOT_REQUIRED"
    for evidence_ref in evidence_refs:
        if _valid_runtime_evidence(
            root / _normalize_path(evidence_ref),
            evidence_kind=evidence_kind,
            evidence_id=evidence_id,
            component_id=component_id,
            coverage_generated_at=coverage_generated_at,
            reference_paths=reference_paths,
            root=root,
        ):
            return "PROVEN"
    return "UNKNOWN"


def _valid_runtime_evidence(
    path: Path,
    *,
    evidence_kind: str,
    evidence_id: str,
    component_id: str,
    coverage_generated_at: datetime | None,
    reference_paths: tuple[str, ...],
    root: Path,
) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            return False
        generated_at = datetime.fromisoformat(str(raw.get("generated_at_utc", "")))
        if generated_at.tzinfo is None:
            return False
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload_hash = str(raw.get("payload_hash", ""))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return False
    if (
        raw.get("evidence_type") != "COVERAGE_ASSURANCE_RUNTIME_PROOF"
        or raw.get("evidence_kind") != evidence_kind
        or raw.get("evidence_id") != evidence_id
        or (component_id and raw.get("component_id") != component_id)
        or raw.get("proof_state") != "PROVEN"
        or raw.get("execution_allowed") is not False
        or raw.get("promotion_status") != "RESEARCH_ONLY"
        or raw.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        or not _SHA256_RE.fullmatch(payload_hash)
        or hashlib.sha256(canonical_payload).hexdigest() != payload_hash
        or not any(
            isinstance(payload.get(identifier), str)
            and bool(str(payload[identifier]).strip())
            for identifier in (
                "run_id",
                "correlation_id",
                "cycle_id",
                "snapshot_id",
                "decision_id",
                "event_id",
            )
        )
    ):
        return False
    if coverage_generated_at is not None and generated_at > coverage_generated_at:
        return False
    return not _has_newer_reference(root, reference_paths, generated_at)


def _below_minimum(
    config: CoverageArchitectureConfig,
    statement_coverage: float | None,
    branch_coverage: float | None,
) -> bool:
    return (
        statement_coverage is None
        or statement_coverage < config.statement_minimum
        or (branch_coverage is not None and branch_coverage < config.branch_minimum)
    )


def _missing_paths(root: Path, paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path for path in paths if not (root / path).is_file())


def _has_newer_reference(
    root: Path,
    paths: tuple[str, ...],
    evidence_generated_at: datetime | None,
) -> bool:
    if evidence_generated_at is None:
        return False
    timestamp = evidence_generated_at.astimezone(UTC).timestamp()
    return any(
        (root / path).is_file() and (root / path).stat().st_mtime > timestamp
        for path in paths
    )


def _behavior_obligation(raw: object, index: int) -> CriticalBehaviorObligationConfig:
    payload = _mapping(raw, f"critical_behavior_obligations[{index}]")
    return CriticalBehaviorObligationConfig(
        obligation_id=str(payload.get("obligation_id", "")),
        category=str(payload.get("category", "")),
        component_id=str(payload.get("component_id", "")),
        requirement_ref=str(payload.get("requirement_ref", "")),
        expected_outcome=str(payload.get("expected_outcome", "")),
        test_assertion_refs=_optional_strings(
            payload.get("test_assertion_refs", ()),
            f"critical_behavior_obligations[{index}].test_assertion_refs",
        ),
        required_relation_ids=_optional_strings(
            payload.get("required_relation_ids", ()),
            f"critical_behavior_obligations[{index}].required_relation_ids",
        ),
        requires_runtime_evidence=_optional_bool(
            payload,
            "requires_runtime_evidence",
            True,
            f"critical_behavior_obligations[{index}]",
        ),
        evidence_refs=_optional_strings(
            payload.get("evidence_refs", ()),
            f"critical_behavior_obligations[{index}].evidence_refs",
        ),
    )


def _relation_proof(raw: object, index: int) -> RelationProofConfig:
    payload = _mapping(raw, f"relation_proofs[{index}]")
    return RelationProofConfig(
        relation_id=str(payload.get("relation_id", "")),
        test_assertion_refs=_strings(
            payload.get("test_assertion_refs"),
            f"relation_proofs[{index}].test_assertion_refs",
        ),
        expected_outcome=str(payload.get("expected_outcome", "")),
        requires_runtime_evidence=_optional_bool(
            payload,
            "requires_runtime_evidence",
            False,
            f"relation_proofs[{index}]",
        ),
        evidence_refs=_optional_strings(
            payload.get("evidence_refs", ()),
            f"relation_proofs[{index}].evidence_refs",
        ),
    )


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    result = tuple(str(item) for item in value)
    _require_unique_texts(label, result)
    return result


def _optional_strings(value: object, label: str) -> tuple[str, ...]:
    if value == ():
        return ()
    return _strings(value, label)


def _optional_bool(
    payload: dict[str, Any], key: str, default: bool, label: str
) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be a boolean")
    return value


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("/")


def _normalize_assertion_ref(value: str) -> str:
    path, separator, function_name = value.replace("\\", "/").strip().partition("::")
    if not separator:
        return value.replace("\\", "/").strip()
    return f"{_normalize_path(path)}::{function_name.strip()}"


def _require_assertion_ref(label: str, value: str) -> None:
    normalized = _normalize_assertion_ref(value)
    path, separator, function_name = normalized.partition("::")
    if not separator or not function_name.isidentifier():
        raise ValueError(f"{label} must use repository/path.py::test_function")
    _require_repository_path(label, path)


def _require_repository_path(label: str, value: str) -> None:
    _require_text(label, value)
    normalized = _normalize_path(value)
    if normalized != value.replace("\\", "/").strip() or ".." in normalized.split("/"):
        raise ValueError(f"{label} must be repository-relative")


def _require_identifier(label: str, value: str) -> None:
    _require_text(label, value)
    if not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"{label} must be a simple identifier")


def _require_text(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required")


def _require_percent(label: str, value: float) -> None:
    if value < 0.0 or value > 100.0:
        raise ValueError(f"{label} must be between 0 and 100")


def _require_unique_texts(
    label: str, values: tuple[str, ...], *, allow_empty: bool = False
) -> None:
    if (not values and not allow_empty) or any(not value.strip() for value in values):
        raise ValueError(f"{label} cannot be empty")
    _require_unique(label, values)


def _require_unique(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")

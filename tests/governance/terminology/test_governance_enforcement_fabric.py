"""Integration tests for the unified terminology, naming, and language fabric."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from ai4binance.governance import governance_enforcement_fabric as fabric_module
from ai4binance.governance import repository_validator
from ai4binance.governance.authority import (
    analyze_authority_impact,
    load_authority_graph,
)
from ai4binance.governance.governance_enforcement_fabric import (
    evaluate_governance_enforcement_fabric,
    load_governance_enforcement_fabric,
)
from ai4binance.governance.repository_validator import (
    RepositoryFindingKind,
    _document_lock_manifest,
)

ROOT = Path(__file__).parents[3]


@pytest.mark.parametrize("input_kind", ["list", "tuple", "generator"])
@pytest.mark.parametrize(
    ("raw_paths", "expected_codes"),
    [
        ((), set()),
        (("scripts/quality.ps1",), set()),
        (
            (
                "src\\unapproved_guard.ps1",
                "",
                "./src/unapproved_guard.ps1",
                " \t",
            ),
            {"LANGUAGE_PLACEMENT_VIOLATION", "TECHNOLOGY_SOURCE_UNREADABLE"},
        ),
    ],
    ids=("empty", "valid", "violations"),
)
def test_fabric_results_are_equivalent_for_all_iterable_inputs(
    input_kind: str,
    raw_paths: tuple[str, ...],
    expected_codes: set[str],
) -> None:
    entries, _, error = _document_lock_manifest(ROOT)
    assert error is None
    fabric = load_governance_enforcement_fabric(ROOT)
    locks = {path: entry.expected_hash for path, entry in entries.items()}
    paths: Iterable[str]
    if input_kind == "list":
        paths = list(raw_paths)
    elif input_kind == "tuple":
        paths = raw_paths
    else:
        paths = (path for path in raw_paths)

    expected = evaluate_governance_enforcement_fabric(ROOT, fabric, raw_paths, locks)
    actual = evaluate_governance_enforcement_fabric(ROOT, fabric, paths, locks)

    assert {violation.code for violation in actual} == expected_codes
    assert actual == expected
    assert len(actual) == len(expected_codes)
    assert all(violation.blocker for violation in actual)


def test_fabric_shares_one_normalized_immutable_snapshot_between_domains() -> None:
    entries, _, error = _document_lock_manifest(ROOT)
    assert error is None
    fabric = load_governance_enforcement_fabric(ROOT)
    iterations = 0

    class SinglePassPaths:
        def __iter__(self) -> Iterator[str]:
            nonlocal iterations
            iterations += 1
            assert iterations == 1
            return iter(("src\\z.py", "", "./src/a.py", "src/z.py", " \t"))

    with (
        patch.object(
            fabric_module, "evaluate_terminology_policy", return_value=()
        ) as terminology,
        patch.object(
            fabric_module, "evaluate_technology_language_policy", return_value=()
        ) as technology,
    ):
        violations = evaluate_governance_enforcement_fabric(
            ROOT,
            fabric,
            SinglePassPaths(),
            {path: entry.expected_hash for path, entry in entries.items()},
        )

    terminology.assert_called_once()
    technology.assert_called_once()
    snapshot = terminology.call_args.args[2]
    assert isinstance(snapshot, tuple)
    assert snapshot == ("src/a.py", "src/z.py")
    assert technology.call_args.args[2] is snapshot
    assert iterations == 1
    assert violations == ()


def test_repository_validator_generator_preserves_technology_blockers() -> None:
    relative = "src/unapproved_guard.ps1"
    artifact = repository_validator.RepositoryArtifact(
        artifact_id="fabric-regression",
        artifact_type=repository_validator.RepositoryArtifactType.SOURCE_CODE,
        artifact_class=repository_validator.RepositoryArtifactClass.SOURCE,
        domain="governance",
        owner="Quality Governance",
        canonical_path=relative,
        path=relative,
        filename="unapproved_guard.ps1",
        schema_version=None,
        lifecycle_status=repository_validator.RepositoryArtifactLifecycle.ACTIVE,
        generated=False,
        immutable=False,
        sensitive=False,
        git_tracked=False,
        checksum=None,
    )
    policy = repository_validator.load_repository_policy(
        ROOT / "policies/repository-validator/manifest-policy.json"
    )

    findings = tuple(
        repository_validator._governance_enforcement_fabric_findings(
            ROOT, policy, (artifact,)
        )
    )
    technology_findings = tuple(
        finding
        for finding in findings
        if finding.kind is RepositoryFindingKind.TECHNOLOGY_LANGUAGE_POLICY_VIOLATION
    )

    assert {finding.detail.split(":", 1)[0] for finding in technology_findings} == {
        "LANGUAGE_PLACEMENT_VIOLATION",
        "TECHNOLOGY_SOURCE_UNREADABLE",
    }
    assert all(finding.blocker for finding in technology_findings)
    assert all(finding.path == relative for finding in technology_findings)


def test_fabric_binds_three_distinct_scopes_to_one_orchestrator() -> None:
    entries, _, error = _document_lock_manifest(ROOT)
    fabric = load_governance_enforcement_fabric(ROOT)

    assert error is None
    assert {family.name for family in fabric.families} == {
        "terminology",
        "repository_naming",
        "technology_language",
    }
    assert len({family.authority_scope for family in fabric.families}) == 3
    assert fabric.authority_scope == "governance_enforcement_fabric"
    assert (
        evaluate_governance_enforcement_fabric(
            ROOT,
            fabric,
            (),
            {path: entry.expected_hash for path, entry in entries.items()},
        )
        == ()
    )


def test_codex_instruction_chain_routes_three_scopes_to_the_single_fabric() -> None:
    required_references = (
        "config/governance/governance_enforcement_fabric.yaml",
        "AI4B-GOV-FABRIC-001",
        "terminology",
        "repository-naming",
        "technology-language",
        "canonical repository validator",
    )
    for relative_path in (
        "AGENTS.md",
        "docs/providers/instruction_codex_provider.md",
    ):
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert all(reference in content for reference in required_references)


def test_fabric_binds_quality_semantics_axes_and_authority_separation() -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    quality_gate = fabric.quality_gate

    assert {pillar.name: pillar.semantic_role for pillar in quality_gate.pillars} == {
        "kaizen": "CULTURE",
        "lean": "PROCESS",
        "six_sigma": "PERFORMANCE",
    }
    assert {axis.name for axis in quality_gate.evaluation_axes} == {
        "layer",
        "capability",
        "component",
        "guardrail",
        "eval",
        "assurance",
    }
    assert quality_gate.minimum_profile == "standard"
    assert quality_gate.deterministic_quality_gate == "TECHNICAL_TRUTH"
    assert quality_gate.deterministic_governance_gate == "POLICY_ELIGIBILITY"
    assert quality_gate.human_governance == "CONSEQUENTIAL_AUTHORITY"


def test_fabric_fails_closed_when_quality_axis_evidence_is_missing() -> None:
    entries, _, error = _document_lock_manifest(ROOT)
    fabric = load_governance_enforcement_fabric(ROOT)
    layer_axis = next(
        axis for axis in fabric.quality_gate.evaluation_axes if axis.name == "layer"
    )
    altered_axis = replace(layer_axis, required_paths=("missing/layer.json",))
    altered_gate = replace(
        fabric.quality_gate,
        evaluation_axes=tuple(
            altered_axis if axis.name == "layer" else axis
            for axis in fabric.quality_gate.evaluation_axes
        ),
    )

    assert error is None
    violations = evaluate_governance_enforcement_fabric(
        ROOT,
        replace(fabric, quality_gate=altered_gate),
        (),
        {path: entry.expected_hash for path, entry in entries.items()},
    )

    assert any(
        violation.family == "quality_gate"
        and violation.code == "QUALITY_GATE_REQUIRED_PATH_MISSING"
        and violation.path == "missing/layer.json"
        and violation.blocker
        for violation in violations
    )


def test_fabric_fails_closed_when_authority_pyramid_binding_is_removed() -> None:
    entries, _, error = _document_lock_manifest(ROOT)
    fabric = load_governance_enforcement_fabric(ROOT)
    graph = load_authority_graph(schema_root=ROOT / "schemas")
    altered_graph = replace(
        graph,
        edges=tuple(
            edge
            for edge in graph.edges
            if edge.edge_id != "core-governs-authority-layer-development-matrix"
        ),
    )

    assert error is None
    with patch.object(
        fabric_module, "load_authority_graph", return_value=altered_graph
    ):
        violations = evaluate_governance_enforcement_fabric(
            ROOT,
            fabric,
            (),
            {path: entry.expected_hash for path, entry in entries.items()},
        )

    assert any(
        violation.family == "quality_gate"
        and violation.code == "AUTHORITY_BINDING_EDGE_MISSING"
        and "core -> authority-layer-development-matrix" in violation.detail
        and violation.blocker
        for violation in violations
    )


def test_fabric_fails_closed_when_its_standard_lock_binding_drifts() -> None:
    entries, _, error = _document_lock_manifest(ROOT)
    fabric = load_governance_enforcement_fabric(ROOT)
    terminology = next(
        family for family in fabric.families if family.name == "terminology"
    )
    drifted = replace(terminology, standard_content_sha256="0" * 64)
    altered = replace(
        fabric,
        families=tuple(
            drifted if family.name == "terminology" else family
            for family in fabric.families
        ),
    )

    assert error is None
    violations = evaluate_governance_enforcement_fabric(
        ROOT,
        altered,
        (),
        {path: entry.expected_hash for path, entry in entries.items()},
    )

    assert any(
        violation.family == "terminology"
        and violation.code == "STANDARD_HASH_MISMATCH"
        and violation.blocker
        for violation in violations
    )


def test_authority_graph_closes_all_fabric_family_paths() -> None:
    graph = load_authority_graph(schema_root=ROOT / "schemas")
    node_ids = {node.node_id for node in graph.nodes}
    impact = analyze_authority_impact(
        graph,
        ("terminology-standard", "repository-naming-standard"),
    )

    assert {
        "terminology-standard",
        "repository-naming-standard",
        "technology-language-standard",
        "terminology-policy",
        "governance-enforcement-fabric",
    } <= node_ids
    assert set(impact.direct_impacted_node_ids) == {
        "governance-enforcement-fabric",
        "terminology-policy",
    }
    assert (
        "config/governance/governance_enforcement_fabric.yaml"
        in impact.required_sync_paths
    )

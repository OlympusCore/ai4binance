"""Integration tests for the unified terminology, naming, and language fabric."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
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


def test_fabric_contract_helpers_reject_untrusted_shapes(tmp_path: Path) -> None:
    invalid_mappings: tuple[object, ...] = (None, [], "text")
    for value in invalid_mappings:
        with pytest.raises(ValueError, match="mapping"):
            fabric_module._mapping(value, "value")
    for value in (None, "", "   "):
        with pytest.raises(ValueError, match="non-empty"):
            fabric_module._string(value, "value")
    for value in ("/absolute", "folder\\file", "folder/../file"):
        with pytest.raises(ValueError, match="POSIX"):
            fabric_module._safe_path(value, "path")
    for value in (None, [], ["x", "x"]):
        with pytest.raises(ValueError, match=r"non-empty list|must be unique"):
            fabric_module._safe_paths(value, "paths")
    for value in ("bad", "A" * 64, "a" * 63):
        with pytest.raises(ValueError, match="SHA-256"):
            fabric_module._sha256_text(value)
    plain = tmp_path / "plain.md"
    plain.write_text("no metadata", encoding="utf-8")
    assert fabric_module._frontmatter(plain) == {}
    with pytest.raises(ValueError, match="standard_impact_tests"):
        fabric_module._quality_standard_mappings({})


def test_fabric_translates_policy_failures_to_blocking_evidence() -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    with (
        patch.object(fabric_module, "_family_integrity_violations", return_value=()),
        patch.object(fabric_module, "_quality_gate_violations", return_value=()),
        patch.object(
            fabric_module, "load_terminology_policy", side_effect=ValueError("bad")
        ),
        patch.object(
            fabric_module,
            "load_technology_language_policy",
            side_effect=ValueError("bad"),
        ),
    ):
        violations = fabric_module.evaluate_governance_enforcement_fabric(
            ROOT, fabric, ("./src/example.py", ""), {}
        )
    assert {item.code for item in violations} == {
        "TERMINOLOGY_POLICY_INVALID",
        "TECHNOLOGY_LANGUAGE_POLICY_INVALID",
    }

    terminology_finding = SimpleNamespace(
        code="TERM", path="src/example.py", detail="detail", blocker=True
    )
    technology_finding = SimpleNamespace(
        code="TECH", path="src/example.py", detail="detail", blocker=False
    )
    with (
        patch.object(fabric_module, "_family_integrity_violations", return_value=()),
        patch.object(fabric_module, "_quality_gate_violations", return_value=()),
        patch.object(fabric_module, "load_terminology_policy", return_value=object()),
        patch.object(
            fabric_module,
            "evaluate_terminology_policy",
            return_value=(terminology_finding,),
        ),
        patch.object(
            fabric_module, "load_technology_language_policy", return_value=object()
        ),
        patch.object(
            fabric_module,
            "evaluate_technology_language_policy",
            return_value=(technology_finding,),
        ),
    ):
        translated = fabric_module.evaluate_governance_enforcement_fabric(
            ROOT, fabric, ("src/example.py",), {}
        )
    assert [(item.family, item.code, item.blocker) for item in translated] == [
        ("terminology", "TERM", True),
        ("technology_language", "TECH", True),
    ]


def test_quality_gate_reports_invalid_policy_and_missing_routed_mapping(
    tmp_path: Path,
) -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    invalid_gate = replace(fabric.quality_gate, quality_policy_path="missing.yaml")
    invalid = tuple(
        fabric_module._quality_gate_violations(
            tmp_path, replace(fabric, quality_gate=invalid_gate)
        )
    )
    assert any(item.code == "QUALITY_GATE_POLICY_INVALID" for item in invalid)

    pillar = fabric.quality_gate.pillars[0]
    altered_pillar = replace(pillar, standard_mapping_names=("missing-mapping",))
    altered_gate = replace(
        fabric.quality_gate,
        pillars=(altered_pillar, *fabric.quality_gate.pillars[1:]),
    )
    violations = tuple(
        fabric_module._quality_gate_violations(
            ROOT, replace(fabric, quality_gate=altered_gate)
        )
    )
    assert any(item.code == "QUALITY_GATE_MAPPING_MISSING" for item in violations)
    assert any(item.code == "QUALITY_GATE_TEST_NOT_ROUTED" for item in violations)


def test_family_integrity_reports_missing_standard_projection_and_schema(
    tmp_path: Path,
) -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    missing = tuple(fabric_module._family_integrity_violations(tmp_path, fabric, {}))
    assert {item.code for item in missing} == {"STANDARD_MISSING"}

    family = fabric.families[0]
    standard = tmp_path / family.standard_path
    standard.parent.mkdir(parents=True)
    standard.write_text("---\ndocument_id: wrong\n---\n", encoding="utf-8")
    details = tuple(fabric_module._family_integrity_violations(tmp_path, fabric, {}))
    assert {item.code for item in details} >= {
        "STANDARD_VERSION_MISMATCH",
        "STANDARD_HASH_MISMATCH",
        "UNREGISTERED_POLICY_PROJECTION",
        "POLICY_MISSING",
    }


def test_quality_mapping_parser_rejects_malformed_and_duplicate_entries() -> None:
    invalid_payloads: tuple[dict[str, object], ...] = (
        {"standard_impact_tests": {}},
        {"standard_impact_tests": {"mappings": [{"name": "x", "tests": "bad"}]}},
        {
            "standard_impact_tests": {
                "mappings": [
                    {"name": "x", "tests": ["tests/a.py"]},
                    {"name": "x", "tests": ["tests/b.py"]},
                ]
            }
        },
    )
    for payload in invalid_payloads:
        with pytest.raises(
            ValueError,
            match=r"mappings must be a list|mapping tests must be a list|duplicate",
        ):
            fabric_module._quality_standard_mappings(payload)
    assert fabric_module._quality_standard_mappings(
        {
            "standard_impact_tests": {
                "mappings": [{"name": "x", "tests": ["tests/a.py"]}]
            }
        }
    ) == {"x": ("tests/a.py",)}


def test_fabric_models_reject_invalid_semantics() -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    with pytest.raises(ValueError, match="scope"):
        replace(fabric, authority_scope="wrong")
    with pytest.raises(ValueError, match="pillar semantics"):
        replace(fabric.quality_gate, pillars=())
    with pytest.raises(ValueError, match="evaluation axes"):
        replace(fabric.quality_gate, evaluation_axes=())
    with pytest.raises(ValueError, match="standard profile"):
        replace(fabric.quality_gate, minimum_profile="fast")


def test_fabric_low_level_contracts_cover_metadata_and_duplicate_paths(
    tmp_path: Path,
) -> None:
    frontmatter = tmp_path / "standard.md"
    frontmatter.write_text("---\ndocument_id: TEST\n---\n", encoding="utf-8")
    assert fabric_module._frontmatter(frontmatter)["document_id"] == "TEST"
    with pytest.raises(ValueError, match="must be unique"):
        fabric_module._safe_paths(["tests/a.py", "tests/a.py"], "paths")
    with pytest.raises(ValueError, match="POSIX path"):
        fabric_module._safe_path("../escape", "path")
    with pytest.raises(ValueError, match="SHA-256"):
        fabric_module._sha256_text("A" * 64)


def test_fabric_loader_and_authority_gate_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fabric validation failed"):
        fabric_module.load_governance_enforcement_fabric(tmp_path)
    fabric = load_governance_enforcement_fabric(ROOT)
    with patch.object(
        fabric_module,
        "load_authority_layer_development_matrix",
        side_effect=ValueError("bad"),
    ):
        violations = tuple(fabric_module._quality_gate_violations(ROOT, fabric))
    assert any(item.code == "AUTHORITY_DEVELOPMENT_GATE_INVALID" for item in violations)


def test_family_integrity_requires_declared_schema(tmp_path: Path) -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    family = next(item for item in fabric.families if item.schema_path is not None)
    standard = tmp_path / family.standard_path
    standard.parent.mkdir(parents=True)
    standard.write_text(
        "---\n"
        f"document_id: {family.standard_id}\n"
        f"version: {family.standard_version}\n"
        f"canonical_path: {family.standard_path}\n"
        f"authority_scope: {family.authority_scope}\n"
        "---\n",
        encoding="utf-8",
    )
    assert any(
        item.code == "SCHEMA_MISSING"
        for item in fabric_module._family_integrity_violations(tmp_path, fabric, {})
    )


def test_authority_binding_and_development_findings_are_projected() -> None:
    fabric = load_governance_enforcement_fabric(ROOT)
    graph = load_authority_graph(
        ROOT / fabric.quality_gate.authority_graph_path, schema_root=ROOT / "schemas"
    )
    required_path = fabric.quality_gate.authority_pyramid_ref
    replacement_nodes = tuple(
        replace(node, canonical_path="docs/governance/missing.md")
        if node.canonical_path == required_path
        else node
        for node in graph.nodes
    )
    altered_graph = replace(graph, nodes=replacement_nodes)
    assert any(
        item.code == "AUTHORITY_BINDING_NODE_MISSING"
        for item in fabric_module._authority_binding_violations(altered_graph, fabric)
    )
    finding = SimpleNamespace(
        code="AUTHORITY_TEST", path="authority/path", detail="test"
    )
    with patch.object(
        fabric_module,
        "validate_authority_graph_layer_development",
        return_value=(finding,),
    ):
        violations = tuple(fabric_module._quality_gate_violations(ROOT, fabric))
    assert any(item.code == "AUTHORITY_TEST" for item in violations)

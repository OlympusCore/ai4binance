"""Branch coverage closure for fail-closed repository governance helpers."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ai4binance.governance import repository_validator as validator
from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.model import AuthorityNode

pytestmark = [
    pytest.mark.governance,
    pytest.mark.validator,
    pytest.mark.runtime_io,
    pytest.mark.slow,
]


def test_authority_graph_conflict_path_is_fail_closed_and_deterministic() -> None:
    assert (
        validator._authority_graph_conflict_path(object(), ("undeclared",))
        == validator.AUTHORITY_GRAPH_REGISTRY_PATH
    )

    node = AuthorityNode(
        node_id="governance-node",
        document_id="AI4B-GOV-TEST-001",
        canonical_path="docs/governance/test.md",
        authority_layer="L2_GOVERNANCE_COMPLIANCE",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="repository_validation",
        lifecycle_status="ACTIVE",
        content_role="AUTHORITATIVE",
        source_of_truth=True,
        source_of_truth_scope="repository_validation",
    )
    graph = AuthorityGraph(
        graph_id="AI4B-AUTHORITY-GRAPH-TEST",
        version="1.0.0",
        status="ACTIVE",
        source_of_truth=False,
        execution_allowed=False,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
        nodes=(node,),
        edges=(),
    )

    assert (
        validator._authority_graph_conflict_path(graph, ())
        == validator.AUTHORITY_GRAPH_REGISTRY_PATH
    )
    assert (
        validator._authority_graph_conflict_path(
            graph,
            ("missing-node", "governance-node"),
        )
        == "docs/governance/test.md"
    )


def test_import_target_resolution_covers_absolute_relative_and_invalid_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert tuple(
        validator._import_targets_for_module(
            "import os, json",
            "ai4binance.example.module",
            "src/ai4binance/example/module.py",
        )
    ) == ("os", "json")

    with pytest.raises(ValueError, match="without a containing package"):
        tuple(
            validator._import_targets_for_module(
                "from .dependency import value",
                "standalone",
                "standalone.py",
            )
        )

    assert tuple(
        validator._import_targets_for_module(
            "from ..shared import value",
            "ai4binance.example.module",
            "src/ai4binance/example/module.py",
        )
    ) == ("ai4binance.shared",)

    module_without_name = ast.Module(
        body=[ast.ImportFrom(module=None, names=[], level=0)],
        type_ignores=[],
    )
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(ast, "parse", lambda _text: module_without_name)
        assert (
            tuple(
                validator._import_targets_for_module(
                    "synthetic import-from node",
                    "ai4binance.example.module",
                    "src/ai4binance/example/module.py",
                )
            )
            == ()
        )


def test_noncanonical_operational_markdown_paths_fail_closed_and_fall_through(
    tmp_path: Path,
) -> None:
    factory = tmp_path / "factory"
    factory.mkdir()
    (factory / "log.md").write_bytes(b"\xff")
    (factory / "progress.md").write_text(
        "---\n"
        "document_id: AI4B-FACTORY-PROGRESS-001\n"
        "title: Factory Progress\n"
        "document_type: STATE\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Factory\n"
        "authority_level: REFERENCE\n"
        "content_role: INFORMATIONAL\n"
        "source_of_truth: false\n"
        "machine_enforceable: false\n"
        "audit_required: false\n"
        "classification: INTERNAL\n"
        "canonical_path: factory/progress.md\n"
        "---\n\n"
        "# Factory Progress\n\n"
        "Operational note only.\n",
        encoding="utf-8",
    )

    findings = tuple(
        validator._noncanonical_operational_markdown_authority_findings(tmp_path)
    )

    assert len(findings) == 1
    assert (
        findings[0].kind
        is validator.RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION
    )
    assert findings[0].path == "factory/log.md"
    assert findings[0].blocker is True


def test_operational_source_of_truth_scope_covers_all_guard_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_without_scope = {"source_of_truth": "true"}
    assert (
        validator._expected_operational_source_of_truth_scope(
            "docs/workflows/test.md",
            metadata_without_scope,
        )
        is None
    )

    metadata = {
        "source_of_truth": "true",
        "authority_scope": "repository_validation",
    }
    assert (
        validator._expected_operational_source_of_truth_scope(
            "docs/workflows/test.md",
            metadata,
        )
        == "repository_validation_workflow"
    )
    assert (
        validator._expected_operational_source_of_truth_scope(
            "docs/procedures/test.md",
            metadata,
        )
        == "repository_validation_procedure"
    )

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            validator,
            "_requires_explicit_operational_authority_metadata",
            lambda _relative, _metadata: True,
        )
        assert (
            validator._expected_operational_source_of_truth_scope(
                "docs/other/test.md",
                metadata,
            )
            is None
        )


def test_written_owner_approval_mirrors_reject_every_invalid_shape() -> None:
    assert validator._document_lock_written_owner_approvals(None, []) is None
    assert validator._document_lock_written_owner_approvals(object(), []) == (
        "written_owner_approvals must be a JSON array when present."
    )
    assert validator._document_lock_written_owner_approvals([], object()) == (
        "approval_records must be a JSON array."
    )
    assert validator._document_lock_written_owner_approvals([], [object()]) == (
        "Each approval record must be a JSON object."
    )
    assert validator._document_lock_written_owner_approvals([], [{}]) == (
        "Approved document lock record approval_id is invalid."
    )
    assert validator._document_lock_written_owner_approvals([], []) is None
    assert validator._document_lock_written_owner_approvals([object()], []) == (
        "Each written owner approval must be a JSON object."
    )
    assert validator._document_lock_written_owner_approvals([{}], []) == (
        "Written owner approval approval_id is invalid."
    )

    canonical_record: dict[str, object] = {"approval_id": "approval-1"}
    assert (
        validator._document_lock_written_owner_approvals(
            [canonical_record.copy()],
            [canonical_record],
        )
        is None
    )


def test_document_lock_approval_evidence_rejects_each_untrusted_boundary(
    tmp_path: Path,
) -> None:
    evidence_relative = "runtime/artifacts/approval-evidence.json"
    evidence_path = tmp_path / evidence_relative
    evidence_path.parent.mkdir(parents=True)
    approved_sha256 = {"AGENTS.md": "a" * 64}
    base_item: dict[str, object] = {
        "approval_id": "AI4B-GOV-DOCLOCK-COVERAGE-001",
        "approval_scope": "REPOSITORY_VALIDATION_COVERAGE",
        "approval_status": "APPROVED",
        "approved_by": "Governance Owner",
        "approved_at_utc": "2026-09-08T00:00:00Z",
        "written_owner_approval": True,
        "approved_sha256": approved_sha256,
        "approval_evidence_path": evidence_relative,
        "approval_evidence_sha256": "a" * 64,
    }

    assert validator._document_lock_approval_evidence(base_item, None) == (
        "Approved document lock evidence requires repository root."
    )
    assert (
        validator._document_lock_approval_evidence(
            base_item | {"approval_evidence_path": "../outside.json"},
            tmp_path,
        )
        == "Approved document lock evidence path is invalid."
    )
    assert (
        validator._document_lock_approval_evidence(
            base_item | {"approval_evidence_sha256": "invalid"},
            tmp_path,
        )
        == "Approved document lock evidence sha256 is invalid."
    )
    assert validator._document_lock_approval_evidence(base_item, tmp_path) == (
        f"Approved document lock evidence file is missing: {evidence_relative}."
    )

    evidence_path.write_text("{", encoding="utf-8")
    invalid_json_item = base_item | {
        "approval_evidence_sha256": validator._sha256(evidence_path)
    }
    invalid_json_error = validator._document_lock_approval_evidence(
        invalid_json_item,
        tmp_path,
    )
    assert invalid_json_error is not None
    assert invalid_json_error.startswith("Approved document lock evidence is invalid:")

    evidence_path.write_text("[]\n", encoding="utf-8")
    list_item = base_item | {
        "approval_evidence_sha256": validator._sha256(evidence_path)
    }
    assert validator._document_lock_approval_evidence(list_item, tmp_path) == (
        "Approved document lock evidence must be a JSON object."
    )

    valid_payload: dict[str, object] = {
        "artifact_origin": "governed_document_lock_written_owner_approval",
        "approval_id": base_item["approval_id"],
        "approval_scope": base_item["approval_scope"],
        "approval_status": base_item["approval_status"],
        "approved_by": base_item["approved_by"],
        "approved_at_utc": base_item["approved_at_utc"],
        "written_owner_approval": True,
        "verification_status": "VERIFIED",
        "approved_sha256": approved_sha256,
    }

    def validate_payload(payload: dict[str, object]) -> str | None:
        evidence_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        item = base_item | {
            "approval_evidence_sha256": validator._sha256(evidence_path)
        }
        return validator._document_lock_approval_evidence(item, tmp_path)

    assert validate_payload(valid_payload | {"artifact_origin": "untrusted"}) == (
        "Approved document lock evidence artifact_origin is invalid."
    )
    assert validate_payload(valid_payload | {"approval_id": "mismatch"}) == (
        "Approved document lock evidence approval_id does not match manifest."
    )
    assert validate_payload(valid_payload | {"written_owner_approval": False}) == (
        "Approved document lock evidence must confirm written owner approval."
    )
    assert validate_payload(valid_payload | {"verification_status": "PENDING"}) == (
        "Approved document lock evidence must be VERIFIED."
    )
    assert validate_payload(valid_payload | {"approved_sha256": {}}) == (
        "Approved document lock evidence approved_sha256 does not match manifest."
    )

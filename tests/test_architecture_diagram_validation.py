from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from ai4binance.ops import architecture_diagram_validation as diagram_validation
from ai4binance.ops.architecture_diagram_validation import (
    validate_architecture_diagrams,
)

ROOT = Path(__file__).parents[1]
DIAGRAM_ROOT = ROOT / "docs" / "architecture" / "diagrams"
KNOWLEDGE_ID_PATTERN = re.compile(r"^AI4B(?:-[A-Z0-9]+){2,}-\d{3}$")


def _document_id(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("document_id:"):
            return line.partition(":")[2].strip()
    raise AssertionError(f"document_id is missing: {path}")


def test_governed_diagram_document_ids_follow_repository_policy() -> None:
    documents = tuple(sorted(DIAGRAM_ROOT.rglob("*.md")))

    assert documents
    assert all(KNOWLEDGE_ID_PATTERN.fullmatch(_document_id(path)) for path in documents)


def _diagram_text(diagram_id: str) -> str:
    return f"""---
document_id: AI4B-ARCH-DIAG-{diagram_id[1:]}
title: Test Diagram
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Architecture
authority_level: SUPPORTING
authority_layer: L6_ARCHITECTURE_ONTOLOGY_ADR
authority_scope: architecture_diagram_projection
authority_effect: INFORMATIONAL
content_role: EXPLANATORY
source_of_truth: false
source_of_truth_scope: reference
canonical_path: docs/architecture/diagrams/00_main/d001_test_diagram.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---

# Test Diagram

## ELI10

Test-only diagram fixture.

Diagram ID: `{diagram_id}`

```mermaid
flowchart LR
    A[Input] --> B[Output]
```
"""


def _write_registry(root: Path, diagrams: list[dict[str, object]]) -> Path:
    diagram_root = root / "docs" / "architecture" / "diagrams"
    diagram_root.mkdir(parents=True, exist_ok=True)
    registry = diagram_root / "diagram_registry.yaml"
    registry.write_text(
        yaml.safe_dump(
            {"registry_version": "1.0.0", "diagrams": diagrams},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return registry


def _entry(
    *,
    diagram_id: str = "D001",
    status: str = "CURRENT_PARTIAL",
    path: str | None = "docs/architecture/diagrams/00_main/d001_test_diagram.md",
    related_diagrams: list[str] | None = None,
) -> dict[str, object]:
    return {
        "diagram_id": diagram_id,
        "title": "Test Diagram",
        "family": "D000",
        "level": "L0",
        "path": path,
        "status": status,
        "authority": "SUPPORTING",
        "current_or_target": "CURRENT",
        "canonical": True,
        "repository_evidence": [],
        "contracts": [],
        "schemas": [],
        "policies": [],
        "tests": [],
        "related_diagrams": related_diagrams or [],
        "owner": "Enterprise Architecture",
        "last_verified": "2026-09-17",
        "validation_status": "PARTIALLY_VERIFIED",
    }


def _write_document(root: Path, relative_path: str, diagram_id: str = "D001") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_diagram_text(diagram_id), encoding="utf-8")


def _finding_codes(root: Path) -> set[str]:
    return {finding.code for finding in validate_architecture_diagrams(root).findings}


def test_rejects_duplicate_diagram_ids(tmp_path: Path) -> None:
    _write_registry(tmp_path, [_entry(), _entry()])

    assert "DUPLICATE_DIAGRAM_ID" in _finding_codes(tmp_path)


def test_rejects_invalid_status(tmp_path: Path) -> None:
    _write_registry(tmp_path, [_entry(status="UNCONTROLLED")])

    assert "INVALID_STATUS" in _finding_codes(tmp_path)


def test_detects_missing_path(tmp_path: Path) -> None:
    _write_registry(tmp_path, [_entry(path=None)])

    assert "MISSING_PATH" in _finding_codes(tmp_path)


def test_detects_missing_registered_diagram(tmp_path: Path) -> None:
    _write_registry(tmp_path, [_entry()])

    assert "MISSING_REGISTERED_DIAGRAM" in _finding_codes(tmp_path)


def test_detects_unregistered_diagram_file(tmp_path: Path) -> None:
    _write_registry(tmp_path, [])
    _write_document(
        tmp_path,
        "docs/architecture/diagrams/00_main/d001_test_diagram.md",
    )

    assert "UNREGISTERED_DIAGRAM_FILE" in _finding_codes(tmp_path)


def test_detects_broken_relation(tmp_path: Path) -> None:
    path = "docs/architecture/diagrams/00_main/d001_test_diagram.md"
    _write_registry(tmp_path, [_entry(related_diagrams=["D999"])])
    _write_document(tmp_path, path)

    assert "BROKEN_RELATION" in _finding_codes(tmp_path)


def test_diagram_helper_contracts_reject_malformed_inputs(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text("[]", encoding="utf-8")
    assert diagram_validation._load_registry(registry)[1] == [
        "registry root must be a mapping"
    ]
    registry.write_text("diagrams: invalid", encoding="utf-8")
    assert diagram_validation._load_registry(registry)[1] == [
        "registry diagrams must be a list"
    ]
    registry.write_text(
        "diagrams:\n  - invalid\n  - diagram_id: D001\n", encoding="utf-8"
    )
    entries, errors = diagram_validation._load_registry(registry)
    assert entries == [{"diagram_id": "D001"}]
    assert errors == ["diagrams[0] must be a mapping"]
    assert diagram_validation._normalize_repository_path(tmp_path, "../escape") is None
    assert (
        diagram_validation._normalize_repository_path(tmp_path, "safe")
        == (tmp_path / "safe").resolve()
    )

    document = tmp_path / "docs" / "diagram.md"
    document.parent.mkdir(parents=True)
    assert (
        diagram_validation._validate_mermaid(document, "# no block")[0].code
        == "MISSING_MERMAID"
    )
    assert (
        diagram_validation._validate_mermaid(document, "```mermaid\npie\n```")[0].code
        == "INVALID_MERMAID_TYPE"
    )
    assert (
        diagram_validation._validate_mermaid(document, "```mermaid\nflowchart LR\n```")
        == []
    )
    links = diagram_validation._validate_local_links(
        tmp_path,
        document,
        "[outside](../../escape) [missing](missing.md) [web](https://example.test)",
    )
    assert {item.code for item in links} == {
        "LINK_OUTSIDE_REPOSITORY",
        "BROKEN_LOCAL_LINK",
    }


def test_validator_reports_all_registry_document_and_relation_failures(
    tmp_path: Path,
) -> None:
    path = "docs/architecture/diagrams/00_main/d001_test_diagram.md"
    _write_document(tmp_path, path, "D999")
    entries = [
        _entry(diagram_id="wrong"),
        _entry(diagram_id="D001", path=123),  # type: ignore[arg-type]
        _entry(diagram_id="D002", path="../escape"),
        _entry(diagram_id="D003", path=path),
        _entry(diagram_id="D004", path=path),
        _entry(diagram_id="D005", related_diagrams=[1]),  # type: ignore[list-item]
    ]
    _write_registry(tmp_path, entries)
    codes = _finding_codes(tmp_path)
    assert {
        "INVALID_DIAGRAM_ID",
        "INVALID_PATH",
        "PATH_OUTSIDE_REPOSITORY",
        "DIAGRAM_ID_MISMATCH",
        "DUPLICATE_DIAGRAM_PATH",
        "INVALID_RELATION_LIST",
    } <= codes


def test_validator_handles_missing_registry_and_cli_statuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        validate_architecture_diagrams(tmp_path).findings[0].code == "REGISTRY_MISSING"
    )
    _write_registry(tmp_path, [])
    assert diagram_validation.main([str(tmp_path)]) == 0
    assert '"status": "PASS"' in capsys.readouterr().out
    _write_registry(tmp_path, [_entry()])
    assert diagram_validation.main([str(tmp_path)]) == 1

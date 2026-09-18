"""Fail-closed validation of graph declarations against source metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

from ai4binance.governance.authority.graph import AuthorityGraph

_GRAPH_METADATA_FIELDS = (
    "document_id",
    "canonical_path",
    "authority_layer",
    "authority_effect",
    "authority_scope",
    "status",
    "content_role",
    "source_of_truth",
    "source_of_truth_scope",
)
_PROVIDER_ADAPTER_PATHS = (
    "CLAUDE.md",
    "GEMINI.md",
    "docs/providers/instruction_codex_provider.md",
    "docs/providers/instruction_claude_provider.md",
)


class AuthorityMetadataFindingKind(StrEnum):
    """Fail-closed graph/source and provider adapter metadata findings."""

    AUTHORITY_METADATA_MISSING = "AUTHORITY_METADATA_MISSING"
    AUTHORITY_METADATA_DRIFT = "AUTHORITY_METADATA_DRIFT"
    PROVIDER_AUTHORITY_DRIFT = "PROVIDER_AUTHORITY_DRIFT"


@dataclass(frozen=True, slots=True)
class AuthorityMetadataFinding:
    """One non-authoritative metadata mismatch with a deterministic blocker."""

    kind: AuthorityMetadataFindingKind
    path: str
    field: str
    detail: str
    blockers: tuple[str, ...] = ("GOVERNANCE_CONFLICT", "LIVE_ORDER_BLOCKED")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.path.strip() or not self.field.strip() or not self.detail.strip():
            raise ValueError("authority metadata finding details are required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "authority metadata findings cannot authorize live execution"
            )


def validate_authority_graph_metadata(
    graph: AuthorityGraph,
    repository_root: Path,
    *,
    provider_adapter_paths: tuple[str, ...] = _PROVIDER_ADAPTER_PATHS,
) -> tuple[AuthorityMetadataFinding, ...]:
    """Compare graph nodes and provider adapters with declared source metadata."""
    if any(not path.strip() for path in provider_adapter_paths):
        raise ValueError("provider adapter paths cannot contain blanks")
    if len(set(provider_adapter_paths)) != len(provider_adapter_paths):
        raise ValueError("provider adapter paths must be unique")
    findings: list[AuthorityMetadataFinding] = []
    for node in graph.nodes:
        metadata = _read_source_metadata(repository_root / node.canonical_path)
        expected = {
            "document_id": node.document_id,
            "canonical_path": node.canonical_path,
            "authority_layer": node.authority_layer,
            "authority_effect": node.authority_effect,
            "authority_scope": node.authority_scope,
            "status": node.lifecycle_status,
            "content_role": node.content_role,
            "source_of_truth": node.source_of_truth,
            "source_of_truth_scope": node.source_of_truth_scope,
        }
        findings.extend(_compare_metadata(node.canonical_path, metadata, expected))
    graph_paths = {node.canonical_path for node in graph.nodes}
    for path in provider_adapter_paths:
        metadata = _read_source_metadata(repository_root / path)
        findings.extend(_provider_adapter_findings(path, metadata))
        if path not in graph_paths and metadata:
            findings.append(
                AuthorityMetadataFinding(
                    kind=AuthorityMetadataFindingKind.PROVIDER_AUTHORITY_DRIFT,
                    path=path,
                    field="authority_graph_coverage",
                    detail="provider adapter is not represented in the authority graph",
                )
            )
    return tuple(
        sorted(
            findings,
            key=lambda finding: (finding.kind.value, finding.path, finding.field),
        )
    )


def _compare_metadata(
    path: str,
    metadata: Mapping[str, object],
    expected: Mapping[str, object],
) -> tuple[AuthorityMetadataFinding, ...]:
    findings: list[AuthorityMetadataFinding] = []
    for field in _GRAPH_METADATA_FIELDS:
        observed = metadata.get(field)
        if observed is None:
            findings.append(
                AuthorityMetadataFinding(
                    kind=AuthorityMetadataFindingKind.AUTHORITY_METADATA_MISSING,
                    path=path,
                    field=field,
                    detail=(
                        "graph node source frontmatter omits a required authority field"
                    ),
                )
            )
        elif observed != expected[field]:
            findings.append(
                AuthorityMetadataFinding(
                    kind=AuthorityMetadataFindingKind.AUTHORITY_METADATA_DRIFT,
                    path=path,
                    field=field,
                    detail="graph node value differs from its source frontmatter",
                )
            )
    return tuple(findings)


def _provider_adapter_findings(
    path: str,
    metadata: Mapping[str, object],
) -> tuple[AuthorityMetadataFinding, ...]:
    if not metadata:
        return (
            AuthorityMetadataFinding(
                kind=AuthorityMetadataFindingKind.PROVIDER_AUTHORITY_DRIFT,
                path=path,
                field="frontmatter",
                detail="provider adapter has no readable governed frontmatter",
            ),
        )
    expected = {
        "authority_layer": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "authority_effect": "OPERATIONAL_SPECIALIZATION",
        "source_of_truth": False,
    }
    findings: list[AuthorityMetadataFinding] = []
    for field, value in expected.items():
        observed = metadata.get(field)
        if observed != value:
            findings.append(
                AuthorityMetadataFinding(
                    kind=AuthorityMetadataFindingKind.PROVIDER_AUTHORITY_DRIFT,
                    path=path,
                    field=field,
                    detail=(
                        "provider adapter metadata conflicts with canonical adapter "
                        "limits"
                    ),
                )
            )
    return tuple(findings)


def _read_source_metadata(path: Path) -> Mapping[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError:
            return {}
        if not isinstance(payload, Mapping):
            return {}
        return cast(Mapping[str, object], payload)
    if not text.startswith("---\n"):
        return {}
    closing = text.find("\n---", len("---\n"))
    if closing < 0:
        return {}
    try:
        payload = yaml.safe_load(text[len("---\n") : closing])
    except yaml.YAMLError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return cast(Mapping[str, object], payload)

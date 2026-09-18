"""Extract bounded, hash-linked evidence without importing repository code."""

from __future__ import annotations

from hashlib import sha256
from urllib.parse import quote

from ai4binance.github_radar.models import (
    EvidenceFragment,
    FetchedDocument,
    RepositorySource,
)


def extract_evidence(
    source: RepositorySource,
    documents: tuple[FetchedDocument, ...],
) -> tuple[EvidenceFragment, ...]:
    fragments: list[EvidenceFragment] = []
    for document in documents:
        evidence_type = _evidence_type(document.path)
        url_path = quote(document.path, safe="/")
        fragments.append(
            EvidenceFragment(
                evidence_type=evidence_type,
                reference=(f"{source.url}/blob/{source.pinned_revision}/{url_path}"),
                claim=f"Pinned {evidence_type.lower()} surface: {document.path}",
                content_sha256=sha256(document.content.encode("utf-8")).hexdigest(),
            )
        )
    return tuple(fragments)


def _evidence_type(path: str) -> str:
    lowered = path.lower()
    if lowered.startswith("tests/") or "/test_" in lowered:
        return "TEST"
    if "benchmark" in lowered:
        return "BENCHMARK"
    if lowered.startswith("license"):
        return "LICENSE"
    if lowered == "pyproject.toml" or lowered.endswith("requirements.txt"):
        return "DEPENDENCY_MANIFEST"
    return "DOCUMENTATION"

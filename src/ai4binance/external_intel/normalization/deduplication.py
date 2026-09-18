"""Text canonicalization and duplicate clustering."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai4binance.external_intel.core.validation import require_text, require_unique_text

_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True, slots=True)
class DuplicateCluster:
    canonical_text: str
    raw_count: int
    unique_author_count: int
    evidence_ids: tuple[str, ...]
    copy_ratio: float

    def __post_init__(self) -> None:
        require_text("duplicate cluster text", self.canonical_text)
        if self.raw_count < 1 or self.unique_author_count < 1:
            raise ValueError("duplicate cluster counts must be positive")
        if self.unique_author_count > self.raw_count:
            raise ValueError("unique author count cannot exceed raw count")
        if not 0.0 <= self.copy_ratio <= 1.0:
            raise ValueError("copy ratio must be within zero and one")
        require_unique_text("duplicate cluster evidence ids", self.evidence_ids)


def canonicalize_text(value: str) -> str:
    cleaned = _URL_RE.sub(" URL ", value.casefold())
    return _SPACE_RE.sub(" ", cleaned).strip()


def cluster_duplicates(
    items: tuple[tuple[str, str, str], ...],
) -> tuple[DuplicateCluster, ...]:
    """Cluster `(evidence_id, author, text)` tuples by canonical text."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for evidence_id, author, text in items:
        grouped.setdefault(canonicalize_text(text), []).append((evidence_id, author))
    clusters = []
    for canonical, members in sorted(grouped.items()):
        authors = tuple(dict.fromkeys(author for _evidence_id, author in members))
        raw_count = len(members)
        unique_author_count = len(authors)
        copy_ratio = 1.0 - (unique_author_count / raw_count)
        clusters.append(
            DuplicateCluster(
                canonical,
                raw_count,
                unique_author_count,
                tuple(evidence_id for evidence_id, _author in members),
                copy_ratio,
            )
        )
    return tuple(clusters)

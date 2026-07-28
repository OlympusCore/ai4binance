"""Governed technology and strategy research radar with no install authority."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore


class CatalogStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    HYPOTHESIS_REGISTERED = "HYPOTHESIS_REGISTERED"
    REPRODUCTION_PENDING = "REPRODUCTION_PENDING"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    OOS_REJECTED = "OOS_REJECTED"
    STAGED_CANDIDATE = "STAGED_CANDIDATE"
    PAPER_APPROVED = "PAPER_APPROVED"


_TRANSITIONS = {
    CatalogStatus.DISCOVERED: frozenset({CatalogStatus.HYPOTHESIS_REGISTERED}),
    CatalogStatus.HYPOTHESIS_REGISTERED: frozenset(
        {CatalogStatus.REPRODUCTION_PENDING}
    ),
    CatalogStatus.REPRODUCTION_PENDING: frozenset(
        {CatalogStatus.RESEARCH_ONLY, CatalogStatus.OOS_REJECTED}
    ),
    CatalogStatus.RESEARCH_ONLY: frozenset(
        {CatalogStatus.STAGED_CANDIDATE, CatalogStatus.OOS_REJECTED}
    ),
    CatalogStatus.STAGED_CANDIDATE: frozenset(
        {CatalogStatus.PAPER_APPROVED, CatalogStatus.OOS_REJECTED}
    ),
    CatalogStatus.OOS_REJECTED: frozenset(),
    CatalogStatus.PAPER_APPROVED: frozenset(),
}


def _require_text(**values: str) -> None:
    if any(not value.strip() or len(value) > 2_000 for value in values.values()):
        raise ValueError("catalog text fields must be non-empty and bounded")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("catalog timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ResearchCatalogEntry:
    """One provenance-bound idea or dependency candidate."""

    entry_id: str
    title: str
    source_url: str
    source_revision: str
    license_id: str
    hypothesis: str
    asset_classes: tuple[str, ...]
    timeframes: tuple[str, ...]
    leakage_risks: tuple[str, ...]
    data_requirements: tuple[str, ...]
    cost_assumptions: tuple[str, ...]
    discovered_at: datetime
    updated_at: datetime
    status: CatalogStatus = CatalogStatus.DISCOVERED
    artifact_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ("SOURCE_EVIDENCE_NOT_REPRODUCED",)
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_text(
            entry_id=self.entry_id,
            title=self.title,
            source_url=self.source_url,
            source_revision=self.source_revision,
            license_id=self.license_id,
            hypothesis=self.hypothesis,
        )
        _require_aware(self.discovered_at)
        _require_aware(self.updated_at)
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError("catalog source URL must be credential-free HTTPS")
        required_groups = (
            self.asset_classes,
            self.timeframes,
            self.leakage_risks,
            self.data_requirements,
            self.cost_assumptions,
        )
        if any(
            not group or any(not item.strip() for item in group)
            for group in required_groups
        ):
            raise ValueError("catalog evidence groups must be non-empty")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("catalog artifact identities must be unique")
        if self.status is CatalogStatus.STAGED_CANDIDATE and self.blockers:
            raise ValueError("staged catalog candidate cannot contain blockers")
        if self.status is CatalogStatus.PAPER_APPROVED and not self.artifact_ids:
            raise ValueError("paper approval requires immutable artifacts")
        if self.execution_allowed:
            raise ValueError("research catalog cannot authorize execution")

    def transition(
        self,
        status: CatalogStatus,
        *,
        updated_at: datetime,
        artifact_ids: tuple[str, ...] = (),
        blockers: tuple[str, ...] = (),
        human_approved: bool = False,
    ) -> ResearchCatalogEntry:
        """Apply an explicit lifecycle transition; paper approval is human-only."""
        if status not in _TRANSITIONS[self.status]:
            raise ValueError(f"invalid catalog transition: {self.status}->{status}")
        _require_aware(updated_at)
        if status is CatalogStatus.PAPER_APPROVED and not human_approved:
            raise ValueError("paper approval requires explicit human approval")
        merged = tuple(dict.fromkeys((*self.artifact_ids, *artifact_ids)))
        return replace(
            self,
            status=status,
            updated_at=updated_at,
            artifact_ids=merged,
            blockers=blockers,
        )


@dataclass(frozen=True, slots=True)
class TechnologyAssessment:
    """Pre-install evaluation; approval still creates no installation authority."""

    entry_id: str
    license_compatible: bool
    actively_maintained: bool
    python_312_supported: bool
    deterministic_or_seeded: bool
    lookahead_reviewed: bool
    security_reviewed: bool
    benchmark_gain_percent: float | None
    removal_cost_documented: bool
    blockers: tuple[str, ...]
    approved_for_experiment: bool
    installation_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise ValueError("technology assessment identity is required")
        if self.benchmark_gain_percent is not None and not (
            -100.0 <= self.benchmark_gain_percent <= 100_000.0
        ):
            raise ValueError("technology benchmark gain is invalid")
        if self.approved_for_experiment == bool(self.blockers):
            raise ValueError("technology assessment and blockers disagree")
        if self.installation_allowed:
            raise ValueError("technology assessment cannot install dependencies")


def assess_technology_candidate(
    *,
    entry_id: str,
    license_compatible: bool,
    actively_maintained: bool,
    python_312_supported: bool,
    deterministic_or_seeded: bool,
    lookahead_reviewed: bool,
    security_reviewed: bool,
    benchmark_gain_percent: float | None,
    removal_cost_documented: bool,
) -> TechnologyAssessment:
    checks = (
        (license_compatible, "LICENSE_INCOMPATIBLE_OR_UNKNOWN"),
        (actively_maintained, "MAINTENANCE_STATUS_WEAK"),
        (python_312_supported, "PYTHON_312_UNSUPPORTED"),
        (deterministic_or_seeded, "DETERMINISM_NOT_PROVEN"),
        (lookahead_reviewed, "LOOKAHEAD_RISK_NOT_REVIEWED"),
        (security_reviewed, "SECURITY_REVIEW_MISSING"),
        (benchmark_gain_percent is not None, "BENCHMARK_EVIDENCE_MISSING"),
        (removal_cost_documented, "REMOVAL_COST_UNDOCUMENTED"),
    )
    blockers = tuple(code for passed, code in checks if not passed)
    return TechnologyAssessment(
        entry_id,
        license_compatible,
        actively_maintained,
        python_312_supported,
        deterministic_or_seeded,
        lookahead_reviewed,
        security_reviewed,
        benchmark_gain_percent,
        removal_cost_documented,
        blockers,
        not blockers,
    )


@dataclass(frozen=True, slots=True)
class ResearchCatalog:
    entries: tuple[ResearchCatalogEntry, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(self, entry: ResearchCatalogEntry) -> ResearchCatalog:
        if any(item.entry_id == entry.entry_id for item in self.entries):
            raise ValueError("catalog entry identity already exists")
        self._record("RESEARCH_CATALOG_ENTRY_ADDED", entry)
        return ResearchCatalog((*self.entries, entry), self.ledger)

    def update(self, entry: ResearchCatalogEntry) -> ResearchCatalog:
        matches = tuple(
            index
            for index, item in enumerate(self.entries)
            if item.entry_id == entry.entry_id
        )
        if len(matches) != 1:
            raise KeyError(entry.entry_id)
        items = list(self.entries)
        items[matches[0]] = entry
        self._record("RESEARCH_CATALOG_ENTRY_TRANSITIONED", entry)
        return ResearchCatalog(tuple(items), self.ledger)

    def _record(self, event_type: str, entry: ResearchCatalogEntry) -> None:
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type=event_type,
                    timestamp=entry.updated_at,
                    snapshot_id=entry.entry_id,
                    payload={"entry": entry},
                )
            )


@dataclass(frozen=True, slots=True)
class ReproductionQueueWriter:
    """Atomically persist only human-governed pending reproduction work."""

    path: Path

    def write(self, catalog: ResearchCatalog) -> None:
        pending = tuple(
            sorted(
                (
                    entry
                    for entry in catalog.entries
                    if entry.status is CatalogStatus.REPRODUCTION_PENDING
                ),
                key=lambda entry: entry.entry_id,
            )
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "entries": to_primitive(pending),
                    "execution_allowed": False,
                    "schema_version": "1.0",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

"""Governed research radar lifecycle, assessment, and persistence tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.research_catalog import (
    CatalogStatus,
    ReproductionQueueWriter,
    ResearchCatalog,
    ResearchCatalogEntry,
    assess_technology_candidate,
)
from ai4binance.storage import JsonlAuditStore

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def entry(entry_id: str = "vnpy-patterns") -> ResearchCatalogEntry:
    return ResearchCatalogEntry(
        entry_id=entry_id,
        title="Event lifecycle patterns",
        source_url="https://github.com/vnpy/vnpy",
        source_revision="UNPINNED_REVIEW_2026-07-13",
        license_id="MIT",
        hypothesis="Persistent event recovery reduces restart ambiguity.",
        asset_classes=("CRYPTO_SPOT",),
        timeframes=("15m", "1h", "4h", "1d"),
        leakage_risks=("EVENT_TIME_CONTAMINATION",),
        data_requirements=("ORDER_EVENTS",),
        cost_assumptions=("NO_LIVE_EXECUTION",),
        discovered_at=NOW,
        updated_at=NOW,
    )


def test_catalog_lifecycle_is_append_only_and_human_governed(tmp_path: Path) -> None:
    ledger_path = tmp_path / "catalog.jsonl"
    catalog = ResearchCatalog(ledger=JsonlAuditStore(ledger_path)).add(entry())
    registered = catalog.entries[0].transition(
        CatalogStatus.HYPOTHESIS_REGISTERED,
        updated_at=NOW + timedelta(seconds=1),
        blockers=("REPRODUCTION_NOT_RUN",),
    )
    catalog = catalog.update(registered)
    pending = registered.transition(
        CatalogStatus.REPRODUCTION_PENDING,
        updated_at=NOW + timedelta(seconds=2),
        blockers=("REPRODUCTION_NOT_RUN",),
    )
    catalog = catalog.update(pending)
    ReproductionQueueWriter(tmp_path / "queue.json").write(catalog)

    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 3
    queue = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert queue["entries"][0]["entry_id"] == "vnpy-patterns"
    assert queue["execution_allowed"] is False


def test_catalog_blocks_skipped_and_automatic_paper_transitions() -> None:
    item = entry()
    with pytest.raises(ValueError, match="invalid catalog transition"):
        item.transition(CatalogStatus.STAGED_CANDIDATE, updated_at=NOW)
    staged = replace(
        item,
        status=CatalogStatus.STAGED_CANDIDATE,
        blockers=(),
        artifact_ids=("oos-report",),
    )
    with pytest.raises(ValueError, match="human approval"):
        staged.transition(
            CatalogStatus.PAPER_APPROVED,
            updated_at=NOW + timedelta(seconds=1),
        )
    approved = staged.transition(
        CatalogStatus.PAPER_APPROVED,
        updated_at=NOW + timedelta(seconds=1),
        human_approved=True,
    )
    assert approved.execution_allowed is False


def test_technology_assessment_requires_all_evidence_and_never_installs() -> None:
    blocked = assess_technology_candidate(
        entry_id="polars-benchmark",
        license_compatible=True,
        actively_maintained=True,
        python_312_supported=True,
        deterministic_or_seeded=True,
        lookahead_reviewed=False,
        security_reviewed=False,
        benchmark_gain_percent=None,
        removal_cost_documented=True,
    )
    assert blocked.approved_for_experiment is False
    assert blocked.installation_allowed is False
    assert blocked.blockers == (
        "LOOKAHEAD_RISK_NOT_REVIEWED",
        "SECURITY_REVIEW_MISSING",
        "BENCHMARK_EVIDENCE_MISSING",
    )

    approved = assess_technology_candidate(
        entry_id="polars-benchmark",
        license_compatible=True,
        actively_maintained=True,
        python_312_supported=True,
        deterministic_or_seeded=True,
        lookahead_reviewed=True,
        security_reviewed=True,
        benchmark_gain_percent=20.0,
        removal_cost_documented=True,
    )
    assert approved.approved_for_experiment is True
    assert approved.installation_allowed is False


def test_catalog_rejects_unsafe_sources_duplicates_and_invalid_shapes() -> None:
    item = entry()
    with pytest.raises(ValueError, match="HTTPS"):
        replace(item, source_url="http://user:pass@example.com")
    catalog = ResearchCatalog().add(item)
    with pytest.raises(ValueError, match="already exists"):
        catalog.add(item)
    with pytest.raises(KeyError):
        catalog.update(entry("missing"))


def test_catalog_entry_preserves_evidence_integrity_and_no_authority() -> None:
    item = entry()
    with pytest.raises(ValueError, match="text fields"):
        replace(item, title="")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(item, discovered_at=datetime(2026, 7, 13))
    with pytest.raises(ValueError, match="artifact identities"):
        replace(item, artifact_ids=("same", "same"))
    with pytest.raises(ValueError, match="staged catalog candidate"):
        replace(item, status=CatalogStatus.STAGED_CANDIDATE)
    with pytest.raises(ValueError, match="paper approval requires"):
        replace(item, status=CatalogStatus.PAPER_APPROVED)
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(item, execution_allowed=True)

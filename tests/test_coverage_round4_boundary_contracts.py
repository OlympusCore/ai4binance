"""Fail-closed boundary coverage for the fourth audit selection."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity
from ai4binance.enterprise.reviews import (
    PeriodicReviewRecord,
    ReviewCadence,
    ReviewOutcome,
)
from ai4binance.governance.blocker_reduction import VirtualBlockerReduction

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _identity() -> WorkflowIdentity:
    return WorkflowIdentity("workflow", "run", "trace", NOW, snapshot_id="snapshot")


def _review() -> PeriodicReviewRecord:
    return PeriodicReviewRecord(
        _identity(),
        "review",
        ReviewCadence.MONTHLY,
        DepartmentId.QUALITY_AUDIT,
        "subject",
        ReviewOutcome.NO_CHANGE,
        ("evidence:one",),
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"review_id": " "}, "identity"),
        ({"evidence_refs": (" ",)}, "blanks"),
        ({"blockers": ("same", "same")}, "unique"),
        ({"promotion_status": "PROMOTED"}, "promote"),
        ({"execution_allowed": True}, "authorize"),
    ],
)
def test_periodic_review_rejects_degraded_or_unsafe_contracts(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_review(), **cast(Any, change))


def _reduction(**change: object) -> VirtualBlockerReduction:
    fields: dict[str, object] = {
        "analysis_blockers": ("ANALYSIS",),
        "candidate_blockers": (),
        "risk_blockers": (),
        "validation_blockers": (),
        "dge_blockers": (),
        "portfolio_blockers": (),
        "feasibility_blockers": (),
        "authority_blockers": (),
        "root_cause_codes": ("ANALYSIS",),
        "known_blockers": (),
        "unknown_blockers": ("ANALYSIS",),
        "blocker_count": 1,
    }
    fields.update(change)
    return VirtualBlockerReduction(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"analysis_blockers": ("same", "same")}, "unique"),
        ({"root_cause_codes": ()}, "stage order"),
        ({"blocker_count": 2}, "count"),
        ({"known_blockers": ("OTHER",), "unknown_blockers": ()}, "cover"),
    ],
)
def test_virtual_blocker_reduction_rejects_inconsistent_classification(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _reduction(**change)

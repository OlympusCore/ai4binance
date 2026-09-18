"""Focused tests for canonical virtual blocker reduction."""

from dataclasses import replace

import pytest

from ai4binance.governance.blocker_reduction import (
    _require_unique_nonblank,
    reduce_virtual_blockers,
)


def test_virtual_blocker_reduction_orders_and_classifies_unknowns() -> None:
    reduction = reduce_virtual_blockers(
        analysis_blockers=("ANALYSIS_ROOT_CAUSE",),
        candidate_blockers=("CANDIDATE_ROOT_CAUSE",),
        risk_blockers=("RISK_ROOT_CAUSE",),
        validation_blockers=("VALIDATION_ROOT_CAUSE",),
        dge_blockers=("DGE_ROOT_CAUSE",),
        portfolio_blockers=("PORTFOLIO_ROOT_CAUSE",),
        feasibility_blockers=("FEASIBILITY_ROOT_CAUSE",),
        authority_blockers=("GOV.AUTHORITY_CONFLICT",),
    )

    assert reduction.blocker_count == 8
    assert reduction.root_cause_codes == (
        "ANALYSIS_ROOT_CAUSE",
        "CANDIDATE_ROOT_CAUSE",
        "RISK_ROOT_CAUSE",
        "VALIDATION_ROOT_CAUSE",
        "DGE_ROOT_CAUSE",
        "PORTFOLIO_ROOT_CAUSE",
        "FEASIBILITY_ROOT_CAUSE",
        "GOV.AUTHORITY_CONFLICT",
    )
    assert reduction.known_blockers == ("GOV.AUTHORITY_CONFLICT",)
    assert reduction.unknown_blockers == (
        "ANALYSIS_ROOT_CAUSE",
        "CANDIDATE_ROOT_CAUSE",
        "RISK_ROOT_CAUSE",
        "VALIDATION_ROOT_CAUSE",
        "DGE_ROOT_CAUSE",
        "PORTFOLIO_ROOT_CAUSE",
        "FEASIBILITY_ROOT_CAUSE",
    )
    assert reduction.has_unknown_classifications is True


def test_virtual_blocker_reduction_deduplicates_blockers_without_reordering() -> None:
    reduction = reduce_virtual_blockers(
        analysis_blockers=("DUPLICATE_BLOCKER", "ANALYSIS_ONLY"),
        candidate_blockers=("DUPLICATE_BLOCKER",),
        risk_blockers=(),
        validation_blockers=(),
        dge_blockers=(),
        portfolio_blockers=(),
        feasibility_blockers=(),
        authority_blockers=(),
    )

    assert reduction.root_cause_codes == ("DUPLICATE_BLOCKER", "ANALYSIS_ONLY")
    assert reduction.blocker_count == 2
    assert reduction.unknown_blockers == ("DUPLICATE_BLOCKER", "ANALYSIS_ONLY")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (("same", "same"), "must be unique"),
        (("known", " "), "cannot contain blanks"),
    ],
)
def test_virtual_blocker_reduction_rejects_invalid_stage_values(
    values: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _require_unique_nonblank("test blockers", values)


def test_virtual_blocker_reduction_rejects_inconsistent_classification_state() -> None:
    reduction = reduce_virtual_blockers(analysis_blockers=("UNKNOWN_CODE",))

    assert reduction.to_payload()["root_cause_codes"] == ["UNKNOWN_CODE"]
    with pytest.raises(ValueError, match="preserve stage order"):
        replace(reduction, root_cause_codes=())
    with pytest.raises(ValueError, match="blocker count is inconsistent"):
        replace(reduction, blocker_count=2)
    with pytest.raises(ValueError, match="classifications must cover"):
        replace(reduction, unknown_blockers=())

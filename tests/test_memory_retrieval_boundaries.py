"""Governed retrieval applies every requested evidence and temporal filter."""

from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import pytest

from ai4binance.core.contracts.memory import (
    MemoryRetrievalPolicy,
    MemoryRetrievalRequest,
    MemoryType,
)
from ai4binance.domain.memory import GovernedMemoryFabric, detect_memory_conflicts
from tests.test_governed_memory_fabric import (
    NOW,
    _active_memory,
    _intent,
    _promotion_verification,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject_keys", ("strategy:unrelated",)),
        ("memory_types", (MemoryType.EPISODIC_MEMORY,)),
        ("market_type", "FUTURES_USDM"),
        ("symbol", "ETHUSDT"),
        ("strategy_id", "another-strategy"),
        ("setup_type", "another-setup"),
        ("regime_tags", ("range",)),
        ("timeframe_tags", ("4h",)),
    ],
)
def test_memory_retrieval_drops_records_outside_requested_scope(
    field: str, value: object
) -> None:
    record = _active_memory()
    request = MemoryRetrievalRequest(
        subject_keys=(record.subject_key,), as_of=NOW + timedelta(minutes=5)
    )
    fabric = GovernedMemoryFabric()
    assert fabric.retrieve((record,), request).records == (record,)
    result = fabric.retrieve((record,), replace(request, **{field: cast(Any, value)}))
    assert result.records == ()
    assert result.dropped_record_ids == (record.memory_id,)
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_memory_activation_requires_aware_time_after_verification() -> None:
    fabric = GovernedMemoryFabric()
    candidate = fabric.compile_candidate(_intent())
    verification = _promotion_verification(candidate)
    for at, message in (
        (NOW.replace(tzinfo=None), "timezone-aware"),
        (NOW, "precede verification"),
    ):
        with pytest.raises(ValueError, match=message):
            fabric.validate_candidate(
                candidate, promotion_verification=verification, at=at
            )


def test_memory_retrieval_ranks_records_and_separates_candidate_policy() -> None:
    fabric = GovernedMemoryFabric()
    active = _active_memory()
    other = replace(active, memory_id="memory-lower-confidence", confidence=0.1)
    request = MemoryRetrievalRequest(
        subject_keys=(active.subject_key,),
        as_of=NOW + timedelta(minutes=5),
        max_records=1,
    )
    result = fabric.retrieve((other, active), request)
    assert result.records == (active,)
    assert result.dropped_record_ids == (other.memory_id,)
    candidate = fabric.compile_candidate(_intent("candidate-2")).record
    candidate_request = replace(request, policy=MemoryRetrievalPolicy.CANDIDATE_REVIEW)
    result = fabric.retrieve((active, candidate), candidate_request)
    assert result.records == (candidate,)
    assert active.memory_id in result.dropped_record_ids


def test_memory_valid_time_cannot_be_replaced_by_later_system_time() -> None:
    record = _active_memory()
    request = MemoryRetrievalRequest(
        subject_keys=(record.subject_key,),
        as_of=NOW - timedelta(seconds=1),
        as_of_system_time=NOW + timedelta(minutes=5),
    )
    result = GovernedMemoryFabric().retrieve((record,), request)
    assert result.records == ()
    assert result.dropped_record_ids == (record.memory_id,)
    assert result.blockers == ("MEMORY_TEMPORAL_INCONSISTENCY",)


def test_memory_supersession_requires_conflict_review() -> None:
    record = _active_memory()
    intent = replace(
        _intent("new-version"), body="Updated evidence", supersedes=(record.memory_id,)
    )
    candidate = GovernedMemoryFabric().compile_candidate(intent, (record,))
    assert "MEMORY_CONFLICT_REVIEW_REQUIRED" in candidate.blockers
    assert any(
        "MEMORY_SUPERSESSION_DECLARED" in conflict.reason_codes
        for conflict in detect_memory_conflicts(intent, (record,))
    )

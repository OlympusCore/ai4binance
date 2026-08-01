from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai4binance.enterprise.contracts import DepartmentId, Priority, WorkflowIdentity
from ai4binance.enterprise.data_supply import (
    DataProduct,
    DataProductRequest,
    DataProductType,
    DataQualityStatus,
    assess_data_product_request,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def request() -> DataProductRequest:
    return DataProductRequest(
        identity(),
        "data-request-1",
        DepartmentId.MARKET_INTELLIGENCE,
        DataProductType.MARKET_SNAPSHOT,
        "Build a market intelligence brief from a shared snapshot.",
        Priority.P1,
        ("artifact:source-registry",),
    )


def test_data_supply_request_is_allowed_only_through_central_source_registry() -> None:
    assessment = assess_data_product_request(request())

    assert assessment.allowed is True
    assert assessment.reason_codes == ()
    assert assessment.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_data_supply_blocks_consumer_direct_fetch_and_missing_source_registry() -> None:
    assessment = assess_data_product_request(
        request(),
        direct_fetch_attempted_by_consumer=True,
        source_registered=False,
    )

    assert assessment.allowed is False
    assert assessment.reason_codes == (
        "CONSUMER_DIRECT_FETCH_BLOCKED",
        "SOURCE_REGISTRY_REQUIRED",
    )


def test_data_product_is_immutable_fail_closed_and_data_supply_published() -> None:
    product = DataProduct(
        identity(),
        "product-1",
        "snapshot-1",
        DataProductType.MARKET_SNAPSHOT,
        "binance-spot-public",
        "EXCHANGE_PRIMARY",
        30,
        HASH,
        DataQualityStatus.FRESH,
        (DepartmentId.MARKET_INTELLIGENCE, DepartmentId.TRADER),
    )

    assert product.publisher_department_id is DepartmentId.DATA_SUPPLY
    assert product.execution_allowed is False
    with pytest.raises(ValueError, match="published by data supply"):
        replace(product, publisher_department_id=DepartmentId.TRADER)
    with pytest.raises(ValueError, match="content hash"):
        replace(product, content_hash="bad")
    with pytest.raises(ValueError, match="consumers must be unique"):
        replace(
            product,
            consumer_departments=(DepartmentId.TRADER, DepartmentId.TRADER),
        )
    with pytest.raises(ValueError, match="authorize execution"):
        replace(product, execution_allowed=True)


def test_data_request_rejects_self_request_and_blank_evidence() -> None:
    with pytest.raises(ValueError, match="cannot request from itself"):
        replace(request(), requester_department_id=DepartmentId.DATA_SUPPLY)
    with pytest.raises(ValueError, match="cannot contain blanks"):
        replace(request(), evidence_refs=("",))

"""Central data-supply contracts for immutable evidence products."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise.contracts import DepartmentId, Priority, WorkflowIdentity

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DataProductType(StrEnum):
    MARKET_SNAPSHOT = "MarketSnapshot"
    ACCOUNT_SNAPSHOT = "AccountSnapshot"
    NEWS_EVIDENCE_PACK = "NewsEvidencePack"
    SOCIAL_EVIDENCE_PACK = "SocialEvidencePack"
    ONCHAIN_EVIDENCE_PACK = "OnChainEvidencePack"
    DERIVATIVES_SNAPSHOT = "DerivativesSnapshot"
    EXCHANGE_RULES_SNAPSHOT = "ExchangeRulesSnapshot"
    RESEARCH_EVIDENCE_PACK = "ResearchEvidencePack"


class DataQualityStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    INVALID = "INVALID"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class DataProductRequest:
    identity: WorkflowIdentity
    request_id: str
    requester_department_id: DepartmentId
    product_type: DataProductType
    purpose: str
    priority: Priority
    evidence_refs: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.purpose.strip():
            raise ValueError("data product request identity is required")
        if self.requester_department_id is DepartmentId.DATA_SUPPLY:
            raise ValueError("data supply cannot request from itself")
        _require_unique_text("data request evidence refs", self.evidence_refs)
        _require_fail_closed(self.execution_allowed, self.live_eligibility_status)


@dataclass(frozen=True, slots=True)
class DataProduct:
    identity: WorkflowIdentity
    data_product_id: str
    snapshot_id: str
    product_type: DataProductType
    source_id: str
    source_authority: str
    freshness_seconds: int
    content_hash: str
    quality_status: DataQualityStatus
    consumer_departments: tuple[DepartmentId, ...]
    publisher_department_id: DepartmentId = DepartmentId.DATA_SUPPLY
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for name, value in (
            ("data_product_id", self.data_product_id),
            ("snapshot_id", self.snapshot_id),
            ("source_id", self.source_id),
            ("source_authority", self.source_authority),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if self.publisher_department_id is not DepartmentId.DATA_SUPPLY:
            raise ValueError("data products must be published by data supply")
        if self.freshness_seconds < 0:
            raise ValueError("freshness seconds cannot be negative")
        if not _SHA256.fullmatch(self.content_hash):
            raise ValueError("data product content hash is invalid")
        if not self.consumer_departments:
            raise ValueError("data product requires consumer departments")
        if len(set(self.consumer_departments)) != len(self.consumer_departments):
            raise ValueError("data product consumers must be unique")
        _require_fail_closed(self.execution_allowed, self.live_eligibility_status)


@dataclass(frozen=True, slots=True)
class DataSupplyAssessment:
    request_id: str
    allowed: bool
    reason_codes: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("data supply assessment identity is required")
        if self.allowed == bool(self.reason_codes):
            raise ValueError("data supply assessment and reasons disagree")
        _require_fail_closed(self.execution_allowed, self.live_eligibility_status)


def assess_data_product_request(
    request: DataProductRequest,
    *,
    direct_fetch_attempted_by_consumer: bool = False,
    source_registered: bool = True,
) -> DataSupplyAssessment:
    reasons: list[str] = []
    if direct_fetch_attempted_by_consumer:
        reasons.append("CONSUMER_DIRECT_FETCH_BLOCKED")
    if not source_registered:
        reasons.append("SOURCE_REGISTRY_REQUIRED")
    if not request.evidence_refs:
        reasons.append("DATA_REQUEST_EVIDENCE_REQUIRED")
    return DataSupplyAssessment(
        request_id=request.request_id,
        allowed=not reasons,
        reason_codes=tuple(reasons),
    )


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_fail_closed(
    execution_allowed: bool,
    live_eligibility_status: str,
) -> None:
    if execution_allowed or live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError("data supply contract cannot authorize execution")

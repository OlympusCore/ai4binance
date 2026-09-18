"""Projection and funding evidence reject invalid values and authority claims."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai4binance.funding.liquidity_conversion_advisor import (
    ConversionAdvisorPolicy,
    ConversionCandidate,
    ConversionDecision,
    ConversionSource,
    LiquidityConversionPlan,
)
from ai4binance.infrastructure.persistence.memory_projection import (
    MemoryProjectionAudit,
    MemoryProjectionRebuildResult,
    SqliteMemoryProjection,
)
from ai4binance.portfolio import AssetClassifier, SpotBalance


@pytest.mark.parametrize(
    ("kind", "changes", "message"),
    [
        ("rebuild", {"projection_hash": "short"}, "hash"),
        ("rebuild", {"record_count": -1}, "count"),
        ("rebuild", {"status": "UNKNOWN"}, "status"),
        ("rebuild", {"execution_allowed": True}, "authorize"),
        ("rebuild", {"live_eligibility_status": "LIVE"}, "authorize"),
        ("audit", {"expected_hash": "short"}, "expected hash"),
        ("audit", {"actual_hash": "short"}, "actual hash"),
        ("audit", {"record_count": -1}, "count"),
        ("audit", {"blockers": ("DRIFT",)}, "reflect blockers"),
        ("audit", {"status": "RUNNING_WITH_BLOCKERS"}, "reflect blockers"),
        ("audit", {"execution_allowed": True}, "authorize"),
        ("audit", {"live_eligibility_status": "LIVE"}, "authorize"),
    ],
)
def test_projection_evidence_rejects_inconsistent_contracts(
    kind: str, changes: dict[str, Any], message: str
) -> None:
    subject = (
        MemoryProjectionRebuildResult("a" * 64, 0)
        if kind == "rebuild"
        else MemoryProjectionAudit("a" * 64, None, 0)
    )
    with pytest.raises(ValueError, match=message):
        replace(subject, **changes)


@pytest.mark.parametrize(("query", "limit"), [(" ", 20), ("evidence", 0)])
def test_projection_search_validates_before_opening_database(
    tmp_path: Path, query: str, limit: int
) -> None:
    projection = SqliteMemoryProjection(tmp_path / "absent.sqlite3")
    with pytest.raises(ValueError, match=r"query is required|limit must be positive"):
        projection.search_body(query, limit=limit)
    assert not projection.path.exists()


@pytest.mark.parametrize(
    ("kind", "changes", "message"),
    [
        ("policy", {"minimum_liquidity_score": Decimal("NaN")}, "non-negative"),
        ("policy", {"minimum_conversion_usdt": Decimal("-1")}, "non-negative"),
        ("source", {"exit_slippage_bps": Decimal("Infinity")}, "non-negative"),
        ("source", {"blockers": (" ",)}, "cannot be empty"),
        ("candidate", {"asset": ""}, "asset is required"),
        ("candidate", {"opportunity_gap": Decimal("-1")}, "non-negative"),
        ("candidate", {"reason_codes": ("",)}, "cannot be empty"),
        ("candidate", {"execution_allowed": True}, "authorize execution"),
        ("plan", {"free_quote_capital_usdt": Decimal("NaN")}, "non-negative"),
        ("plan", {"blockers": ("",)}, "cannot be empty"),
        ("plan", {"execution_allowed": True}, "authority"),
        ("plan", {"live_eligibility_status": "LIVE"}, "authority"),
    ],
)
def test_conversion_evidence_rejects_invalid_values_and_authority(
    kind: str, changes: dict[str, Any], message: str
) -> None:
    record = AssetClassifier().classify_spot_balances(
        (SpotBalance("HOT", Decimal("10000"), Decimal("0")),),
        prices_usdt={"HOT": Decimal("0.002")},
    )[0]
    subjects: dict[str, Any] = {
        "policy": ConversionAdvisorPolicy(),
        "source": ConversionSource(record, Decimal("80"), Decimal("20")),
        "candidate": ConversionCandidate(
            "HOT",
            ConversionDecision.CONVERSION_CANDIDATE,
            Decimal("20"),
            Decimal("80"),
            Decimal("20"),
            Decimal("0"),
            ("MANUAL_CONVERSION_REVIEW",),
        ),
        "plan": LiquidityConversionPlan(Decimal("0"), (), ()),
    }
    with pytest.raises(ValueError, match=message):
        replace(subjects[kind], **changes)

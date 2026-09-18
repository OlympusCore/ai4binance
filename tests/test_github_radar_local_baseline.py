"""Local capability-gap baseline tests."""

from __future__ import annotations

from ai4binance.github_radar.local_baseline import build_local_capability_baseline
from ai4binance.github_radar.models import LocalCapabilityStatus


def test_local_baseline_maps_every_capability_and_remains_report_only() -> None:
    baseline = build_local_capability_baseline()

    assert len(baseline) == 76
    assert len({item.capability_id for item in baseline}) == 76
    assert any(item.status is LocalCapabilityStatus.RESEARCH_GAP for item in baseline)
    assert any(item.present_evidence for item in baseline)
    assert all(item.execution_allowed is False for item in baseline)
    assert all(item.promotion_status == "RESEARCH_ONLY" for item in baseline)
    assert all(
        item.live_eligibility_status == "LIVE_ORDER_BLOCKED" for item in baseline
    )
    assert all(
        any(
            blocker.startswith("VALIDATION_PROFILE_PENDING:")
            for blocker in item.blockers
        )
        for item in baseline
    )

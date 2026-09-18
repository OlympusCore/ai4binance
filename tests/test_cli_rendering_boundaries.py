"""CLI summaries preserve blockers and bounded legacy opportunity displays."""

import pytest

from ai4binance.cli.presentation.output import render_payload


def test_legacy_opportunity_summary_preserves_evidence_and_caps_visible_rows() -> None:
    payload = {
        "inbox": {
            "symbol": "BTCUSDT",
            "generation_status": "DEGRADED",
            "research_blockers": ["HISTORY_MISSING"],
            "execution_blockers": "LIVE_ORDER_BLOCKED",
            "next_safe_actions": ["REFRESH_HISTORY"],
            "funnel_counts": [["DISCOVERED", 7], [], ["incomplete"], "invalid", 123],
            "items": [
                {
                    "market": "SPOT",
                    "timeframe": "1h",
                    "setup_name": f"setup-{index}",
                    "status": "WATCH_ONLY",
                    "promotion_status": "RESEARCH_ONLY",
                }
                for index in range(7)
            ],
        }
    }
    text = render_payload(payload, output_format="text", command="opportunities")
    for expected in (
        "Opportunities: BTCUSDT",
        "visible_items: 7",
        "HISTORY_MISSING",
        "LIVE_ORDER_BLOCKED",
        "REFRESH_HISTORY",
        "funnel: DISCOVERED=7",
        "setup-4",
        "promotion=RESEARCH_ONLY",
    ):
        assert expected in text
    assert "setup-5" not in text
    assert "incomplete=" not in text


def test_empty_legacy_opportunity_summary_does_not_invent_blockers() -> None:
    text = render_payload(
        {"inbox": {"research_blockers": 123}},
        output_format="text",
        command="opportunities",
    )
    assert "visible_items: 0" in text
    assert "LIVE_ORDER_BLOCKED" in text
    assert "- research_blockers:" not in text
    assert "- funnel:" not in text


@pytest.mark.parametrize(
    ("command", "payload", "expected"),
    [
        (
            "backtest-runtime-economics",
            {"measured_power_watts": 42, "claimed_monthly_cost_usd": 10},
            ("measured_power_watts: 42", "claimed_monthly_cost_usd: 10"),
        ),
        (
            "virtual-improvement-research-queue",
            {
                "blockers": ["MISSING_EVIDENCE"],
                "items": [{"candidate_id": "candidate-1"}],
            },
            ("MISSING_EVIDENCE", "candidate=candidate-1"),
        ),
        (
            "research-public",
            {"virtual_runtime_decision": {"blockers": ["MISSING_EVIDENCE"]}},
            ("virtual_runtime_blockers: MISSING_EVIDENCE", "LIVE_ORDER_BLOCKED"),
        ),
        (
            "agent-stack-audit",
            {
                "report": {"layers": [{"layer_id": "RISK", "passed": False}]},
                "blockers": ["RISK_INCOMPLETE"],
            },
            ("RISK_INCOMPLETE", "RISK: REVISION_REQUIRED"),
        ),
        (
            "opportunities",
            {"inbox": {}, "opportunity_report_v2": {"report_id": "report-1"}},
            ("Validation Ladder:\n- none", "Live: LIVE_ORDER_BLOCKED"),
        ),
    ],
)
def test_text_renderers_surface_optional_evidence(
    command: str, payload: dict[str, object], expected: tuple[str, ...]
) -> None:
    text = render_payload(payload, output_format="text", command=command)
    for fragment in expected:
        assert fragment in text

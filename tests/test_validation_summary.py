"""Validation summary and opportunity inbox visibility tests."""

from __future__ import annotations

import json
from pathlib import Path

from ai4binance.opportunities import OpportunityInboxBuilder
from ai4binance.validation.summary import ValidationSummaryReader


def write_run_card(root: Path, *, symbol: str = "HOTUSDT") -> Path:
    path = root / symbol / "15m" / "trend_continuation.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        f"Backtest/validation/{symbol}/15m/trend_continuation.jsonl",
                        "abc",
                    ],
                ],
                "blockers": ["LOW_OOS_TRADE_COUNT"],
                "created_at": "2026-07-28T00:00:00+00:00",
                "execution_allowed": False,
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [
                    ["net_return", 0.12],
                    ["trade_count", 7.0],
                    ["bootstrap_probability_of_loss", 0.25],
                ],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:test",
                "symbol": symbol,
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def test_validation_summary_reads_run_cards_without_large_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "validation"
    write_run_card(root)

    summary = ValidationSummaryReader(root).summarize("hotusdt")

    assert summary.run_count == 1
    assert summary.research_only_count == 1
    assert summary.top_blockers == (("LOW_OOS_TRADE_COUNT", 1),)
    assert summary.runs[0].artifact_paths == (
        "Backtest/validation/HOTUSDT/15m/trend_continuation.jsonl",
    )
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_validation_summary_fails_closed_when_missing(tmp_path: Path) -> None:
    summary = ValidationSummaryReader(tmp_path / "missing").summarize("HOTUSDT")

    assert summary.run_count == 0
    assert summary.blockers == ("VALIDATION_ARTIFACTS_UNAVAILABLE",)


def test_opportunity_inbox_merges_market_and_validation_evidence(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    write_run_card(validation_root)
    outlook = tmp_path / "runtime-state.json"
    outlook.write_text(
        json.dumps(
            {
                "blockers": ["NO_READY_CANDIDATE"],
                "pro_trend_direction": "BULLISH",
                "setups_on_radar": ["breakout_retest"],
                "status": "PARTIAL",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(validation_root),
        outlook,
    ).build("HOTUSDT")

    subjects = tuple(item.setup_name for item in inbox.items)
    assert "breakout_retest" in subjects
    assert "trend_continuation" in subjects
    assert "NO_READY_CANDIDATE" in inbox.blockers
    assert inbox.generation_status == "ACTIVE"
    assert inbox.research_blockers == ()
    assert "NO_READY_CANDIDATE" in inbox.execution_blockers
    assert "KEEP_WATCHLIST_AND_WAIT_FOR_READY_SETUP" in inbox.next_safe_actions
    assert inbox.research_loop_allowed is True
    assert inbox.opportunity_generation_allowed is True
    assert all(item.execution_allowed is False for item in inbox.items)
    assert inbox.live_eligibility_status == "LIVE_ORDER_BLOCKED"

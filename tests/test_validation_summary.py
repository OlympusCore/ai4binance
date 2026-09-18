"""Validation summary and opportunity inbox visibility tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.opportunities import OpportunityInboxBuilder
from ai4binance.validation import summary as validation_summary
from ai4binance.validation.artifacts import (
    StrategyApprovalArtifact,
    ValidationArtifactRegistry,
)
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    StatisticalEvidenceAssessment,
    assess_statistical_evidence,
)
from ai4binance.validation.summary import (
    ValidationRunSummary,
    ValidationSummary,
    ValidationSummaryReader,
)

NOW = datetime(2026, 7, 28, tzinfo=UTC)


def write_run_card(root: Path, *, symbol: str = "HOTUSDT") -> Path:
    path = root / symbol / "15m" / "trend_continuation.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        f"runtime/artifacts/research/backtest/validation/{symbol}/15m/trend_continuation.jsonl",
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
        "runtime/artifacts/research/backtest/validation/HOTUSDT/15m/trend_continuation.jsonl",
    )
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_validation_summary_fails_closed_when_missing(tmp_path: Path) -> None:
    summary = ValidationSummaryReader(tmp_path / "missing").summarize("HOTUSDT")

    assert summary.run_count == 0
    assert summary.blockers == ("VALIDATION_ARTIFACTS_UNAVAILABLE",)


def test_validation_summary_reports_unavailable_when_symbol_folder_has_no_cards(
    tmp_path: Path,
) -> None:
    root = tmp_path / "validation"
    (root / "HOTUSDT").mkdir(parents=True)

    summary = ValidationSummaryReader(root).summarize("HOTUSDT")

    assert summary.run_count == 0
    assert summary.blockers == ("VALIDATION_RUN_CARDS_UNAVAILABLE",)


def test_validation_summary_marks_unreadable_run_cards(tmp_path: Path) -> None:
    root = tmp_path / "validation"
    bad = root / "HOTUSDT" / "15m" / "broken.run-card.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{bad-json", encoding="utf-8")

    summary = ValidationSummaryReader(root).summarize("HOTUSDT")

    assert summary.run_count == 0
    assert summary.blockers == (f"RUN_CARD_UNREADABLE:{bad.as_posix()}",)


def test_validation_summary_supports_playbook_fallback_and_contract_guards(
    tmp_path: Path,
) -> None:
    root = tmp_path / "validation"
    path = root / "HOTUSDT" / "1h" / "fallback.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        "runtime/artifacts/research/backtest/validation/HOTUSDT/1h/fallback.jsonl",
                        "sha",
                    ]
                ],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "metrics": [["net_return", 0.10]],
                "promotion_status": "STAGED_CANDIDATE",
                "run_id": "run:fallback",
                "strategy_sha256": "strategy:abc",
                "symbol": "HOTUSDT",
                "timeframe": "1h",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    summary = ValidationSummaryReader(root).summarize("HOTUSDT")
    assert summary.run_count == 1
    assert summary.staged_candidate_count == 1
    assert summary.runs[0].playbook == "UNKNOWN_PLAYBOOK"

    assert validation_summary._sequence(("a", "b")) == ("a", "b")
    assert validation_summary._sequence(["a", "b"]) == ("a", "b")
    assert validation_summary._sequence("not-a-sequence") == ()

    with pytest.raises(ValueError, match="identity is required"):
        ValidationRunSummary(
            symbol="",
            timeframe="1h",
            playbook="pb",
            run_id="run",
            promotion_status="RESEARCH_ONLY",
            metrics=(),
            blockers=(),
            artifact_paths=(),
            created_at="2026-07-28T00:00:00+00:00",
        )

    with pytest.raises(ValueError, match="cannot grant execution authority"):
        ValidationRunSummary(
            symbol="HOTUSDT",
            timeframe="1h",
            playbook="pb",
            run_id="run",
            promotion_status="RESEARCH_ONLY",
            metrics=(),
            blockers=(),
            artifact_paths=(),
            created_at="2026-07-28T00:00:00+00:00",
            execution_allowed=True,
        )

    with pytest.raises(ValueError, match="identity is required"):
        ValidationSummary(
            symbol="",
            artifact_directory="",
            run_count=0,
            staged_candidate_count=0,
            research_only_count=0,
            top_blockers=(),
            runs=(),
            blockers=(),
        )

    with pytest.raises(ValueError, match="cannot grant execution authority"):
        ValidationSummary(
            symbol="HOTUSDT",
            artifact_directory="validation/HOTUSDT",
            run_count=0,
            staged_candidate_count=0,
            research_only_count=0,
            top_blockers=(),
            runs=(),
            blockers=(),
            execution_allowed=True,
        )

    with pytest.raises(ValueError, match="bounds must be positive"):
        ValidationSummaryReader(root, max_runs=0)


def test_run_summary_rejects_non_object_payload_and_missing_playbook(
    tmp_path: Path,
) -> None:
    array_path = tmp_path / "array.run-card.json"
    array_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="run card must be an object"):
        validation_summary._run_summary(array_path)

    missing_playbook_path = tmp_path / "missing-playbook.run-card.json"
    missing_playbook_path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        "runtime/artifacts/research/backtest/validation/HOTUSDT/1h/run.jsonl",
                        "sha",
                    ]
                ],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "metrics": [["net_return", 0.1]],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:missing-playbook",
                "symbol": "HOTUSDT",
                "timeframe": "1h",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="run card playbook is unavailable"):
        validation_summary._run_summary(missing_playbook_path)


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
    assert "PLAN_NEXT_EVIDENCE_REFRESH" in inbox.next_safe_actions
    assert inbox.research_loop_allowed is True
    assert inbox.opportunity_generation_allowed is True
    assert all(item.execution_allowed is False for item in inbox.items)
    assert inbox.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_inbox_blocks_stale_market_outlook_symbol_mismatch(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    write_run_card(validation_root, symbol="BTCUSDT")
    outlook = tmp_path / "runtime-state.json"
    outlook.write_text(
        json.dumps(
            {
                "blockers": [],
                "pro_trend_direction": "BULLISH",
                "setups_on_radar": ["golden_cross"],
                "status": "SUCCESS",
                "symbol": "HOTUSDT",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(validation_root),
        outlook,
    ).build("BTCUSDT")

    assert "golden_cross" not in tuple(item.setup_name for item in inbox.items)
    assert "trend_continuation" in tuple(item.setup_name for item in inbox.items)
    assert "MARKET_OUTLOOK_SYMBOL_MISMATCH:HOTUSDT!=BTCUSDT" in inbox.blockers
    assert "MARKET_OUTLOOK_SYMBOL_MISMATCH:HOTUSDT!=BTCUSDT" in (
        inbox.execution_blockers
    )
    assert "RUN_SYMBOL_SCOPED_ANALYZE_PUBLIC" in inbox.next_safe_actions
    assert inbox.execution_allowed is False
    assert inbox.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_statistical_evidence_rejects_invalid_thresholds_and_values() -> None:
    with pytest.raises(ValueError, match="sample and hypothesis"):
        StatisticalEvidenceAssessment(
            -1,
            1,
            0.95,
            0.05,
            0.1,
            None,
            MultipleTestingCorrection.NONE,
            True,
            (),
        )
    with pytest.raises(ValueError, match="finite"):
        StatisticalEvidenceAssessment(
            10,
            1,
            float("nan"),
            0.05,
            0.1,
            None,
            MultipleTestingCorrection.NONE,
            True,
            (),
        )
    with pytest.raises(ValueError, match="confidence level"):
        StatisticalEvidenceAssessment(
            10,
            1,
            1.0,
            0.05,
            0.1,
            None,
            MultipleTestingCorrection.NONE,
            True,
            (),
        )
    with pytest.raises(ValueError, match="adjusted alpha"):
        StatisticalEvidenceAssessment(
            10,
            1,
            0.95,
            1.0,
            0.1,
            None,
            MultipleTestingCorrection.NONE,
            True,
            (),
        )
    with pytest.raises(ValueError, match="confidence interval"):
        StatisticalEvidenceAssessment(
            10,
            1,
            0.95,
            0.05,
            0.1,
            (1.0, 0.0),
            MultipleTestingCorrection.NONE,
            True,
            (),
        )
    with pytest.raises(ValueError, match="positive hypotheses"):
        assess_statistical_evidence(
            (0.1,),
            hypothesis_count=0,
            min_effective_sample_size=2,
            minimum_return=0.0,
            confidence_level=0.95,
            correction=MultipleTestingCorrection.NONE,
            confirmatory=True,
        )
    with pytest.raises(ValueError, match="one of"):
        assess_statistical_evidence(
            (0.1, 0.2),
            hypothesis_count=1,
            min_effective_sample_size=2,
            minimum_return=0.0,
            confidence_level=0.80,
            correction=MultipleTestingCorrection.NONE,
            confirmatory=True,
        )
    with pytest.raises(ValueError, match="returns must be finite"):
        assess_statistical_evidence(
            (float("inf"),),
            hypothesis_count=1,
            min_effective_sample_size=2,
            minimum_return=0.0,
            confidence_level=0.95,
            correction=MultipleTestingCorrection.NONE,
            confirmatory=True,
        )


def test_validation_artifact_registry_is_paper_only_and_exact_match() -> None:
    artifact = StrategyApprovalArtifact(
        "approval-1",
        NOW,
        "HOTUSDT",
        "15m",
        "trend",
        "v1",
        "hash",
    )

    assert (
        ValidationArtifactRegistry((artifact,)).resolve(
            symbol="hotusdt",
            timeframe="15m",
            playbook="trend",
            strategy_version="v1",
            config_hash="hash",
        )
        is ValidationStatus.PAPER_APPROVED
    )
    assert (
        ValidationArtifactRegistry((artifact, artifact)).resolve(
            symbol="HOTUSDT",
            timeframe="15m",
            playbook="trend",
            strategy_version="v1",
            config_hash="hash",
        )
        is ValidationStatus.RESEARCH_ONLY
    )
    with pytest.raises(ValueError, match="timezone"):
        StrategyApprovalArtifact(
            "approval-1",
            NOW.replace(tzinfo=None),
            "HOTUSDT",
            "15m",
            "trend",
            "v1",
            "hash",
        )
    with pytest.raises(ValueError, match="identity"):
        StrategyApprovalArtifact(" ", NOW, "HOTUSDT", "15m", "trend", "v1", "hash")
    with pytest.raises(ValueError, match="live eligibility"):
        StrategyApprovalArtifact(
            "approval-1",
            NOW,
            "HOTUSDT",
            "15m",
            "trend",
            "v1",
            "hash",
            status=ValidationStatus.LIVE_ELIGIBLE,
        )

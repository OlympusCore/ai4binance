import pytest

from ai4binance.validation.multiple_comparison import (
    CandidatePerformance,
    assess_multiple_comparisons,
)


def test_spa_and_confidence_set_are_seeded_and_fail_closed() -> None:
    benchmark = tuple(0.0 for _item in range(80))
    candidates = (
        CandidatePerformance("strong", tuple(0.02 for _item in range(80))),
        CandidatePerformance("weak", tuple(-0.01 for _item in range(80))),
    )

    first = assess_multiple_comparisons(
        benchmark_returns=benchmark,
        candidates=candidates,
        bootstrap_samples=199,
        block_length=5,
    )
    second = assess_multiple_comparisons(
        benchmark_returns=benchmark,
        candidates=candidates,
        bootstrap_samples=199,
        block_length=5,
    )

    assert first == second
    assert first.best_candidate == "strong"
    assert first.spa_p_value <= 0.05
    assert first.model_confidence_set == ("strong",)
    assert first.status == "STAGED_CANDIDATE"
    assert first.promotion_allowed is False
    assert first.execution_allowed is False


def test_spa_blocks_indistinguishable_candidates() -> None:
    benchmark = tuple((index % 3 - 1) * 0.001 for index in range(60))
    candidates = (
        CandidatePerformance("same-a", benchmark),
        CandidatePerformance("same-b", benchmark),
    )

    report = assess_multiple_comparisons(
        benchmark_returns=benchmark,
        candidates=candidates,
        bootstrap_samples=199,
    )

    assert "NO_CANDIDATE_BEATS_BENCHMARK" in report.blockers
    assert "SPA_NOT_SIGNIFICANT" in report.blockers
    assert report.status == "RESEARCH_ONLY"


def test_multiple_comparison_rejects_unaligned_or_small_evidence() -> None:
    with pytest.raises(ValueError, match="20 finite"):
        assess_multiple_comparisons(
            benchmark_returns=(0.0,) * 10,
            candidates=(CandidatePerformance("x", (0.1,) * 10),),
        )
    with pytest.raises(ValueError, match="aligned"):
        assess_multiple_comparisons(
            benchmark_returns=(0.0,) * 20,
            candidates=(CandidatePerformance("x", (0.1,) * 19),),
        )
    with pytest.raises(ValueError, match="unique"):
        assess_multiple_comparisons(
            benchmark_returns=(0.0,) * 20,
            candidates=(
                CandidatePerformance("x", (0.1,) * 20),
                CandidatePerformance("x", (0.2,) * 20),
            ),
        )
    with pytest.raises(ValueError, match="dimensions"):
        assess_multiple_comparisons(
            benchmark_returns=(0.0,) * 20,
            candidates=(CandidatePerformance("x", (0.1,) * 20),),
            bootstrap_samples=10,
        )
    with pytest.raises(ValueError, match="identity"):
        CandidatePerformance(" ", (0.1,))

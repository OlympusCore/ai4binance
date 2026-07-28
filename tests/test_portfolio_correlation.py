import pytest

from ai4binance.portfolio.correlation import (
    SymbolReturnSeries,
    assess_portfolio_correlation,
)


def test_portfolio_correlation_blocks_concentrated_aligned_assets() -> None:
    base = tuple((index % 5 - 2) / 100 for index in range(60))
    report = assess_portfolio_correlation(
        (
            SymbolReturnSeries("HOTUSDT", base, 0.6),
            SymbolReturnSeries("BTCUSDT", base, 0.4),
        )
    )

    assert report.maximum_absolute_correlation == pytest.approx(1.0)
    assert report.correlated_exposure_weight == pytest.approx(1.0)
    assert set(report.blockers) == {
        "PORTFOLIO_CORRELATION_CAP_EXCEEDED",
        "CORRELATED_EXPOSURE_CAP_EXCEEDED",
    }
    assert report.execution_allowed is False


def test_portfolio_correlation_accepts_diversified_research_evidence() -> None:
    left = tuple((index % 7 - 3) / 100 for index in range(70))
    right = tuple(((index * index) % 11 - 5) / 100 for index in range(70))
    report = assess_portfolio_correlation(
        (
            SymbolReturnSeries("HOTUSDT", left, 0.5),
            SymbolReturnSeries("BTCUSDT", right, 0.5),
        )
    )

    assert report.blockers == ()
    assert report.effective_asset_count == pytest.approx(2.0)
    assert report.status == "RESEARCH_ONLY"


def test_portfolio_correlation_rejects_misaligned_or_invalid_weights() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        assess_portfolio_correlation(
            (
                SymbolReturnSeries("HOTUSDT", (0.0,) * 30, 0.7),
                SymbolReturnSeries("BTCUSDT", (0.0,) * 30, 0.4),
            )
        )
    with pytest.raises(ValueError, match="30 aligned"):
        assess_portfolio_correlation((SymbolReturnSeries("HOTUSDT", (0.0,) * 20, 1.0),))


def test_portfolio_correlation_handles_zero_variance_and_invalid_contracts() -> None:
    report = assess_portfolio_correlation(
        (
            SymbolReturnSeries("HOTUSDT", (0.0,) * 30, 0.5),
            SymbolReturnSeries("BTCUSDT", (0.0,) * 30, 0.5),
        )
    )
    assert report.maximum_absolute_correlation == 0
    with pytest.raises(ValueError, match="symbol"):
        SymbolReturnSeries("bad-symbol", (0.0,), 1.0)
    with pytest.raises(ValueError, match="weight"):
        SymbolReturnSeries("HOTUSDT", (0.0,), 2.0)
    with pytest.raises(ValueError, match="policy"):
        assess_portfolio_correlation(
            (SymbolReturnSeries("HOTUSDT", (0.0,) * 30, 1.0),),
            maximum_correlation=1.0,
        )

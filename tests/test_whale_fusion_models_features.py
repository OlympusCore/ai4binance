"""WHALE-FUSION contracts and deterministic feature tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.whale_fusion import (
    DerivativesDataset,
    DerivativesFeatureEngine,
    DerivativesMetric,
    MetricPoint,
    PriceOiRegime,
    Provenance,
    SocialEventType,
    WhaleEventType,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def point(metric: DerivativesMetric, index: int, value: str) -> MetricPoint:
    provenance = Provenance("binance-usdm", NOW, "https://fapi.binance.com")
    return MetricPoint(
        metric,
        NOW + timedelta(hours=index),
        Decimal(value),
        provenance,
    )


def dataset(
    oi: tuple[str, ...],
    *,
    funding: tuple[str, ...] = ("0.001", "0.002"),
) -> DerivativesDataset:
    def series(
        metric: DerivativesMetric, values: tuple[str, ...]
    ) -> tuple[MetricPoint, ...]:
        return tuple(point(metric, index, value) for index, value in enumerate(values))

    return DerivativesDataset(
        "hotusdt",
        NOW,
        {
            DerivativesMetric.OPEN_INTEREST: series(
                DerivativesMetric.OPEN_INTEREST, oi
            ),
            DerivativesMetric.FUNDING_RATE: series(
                DerivativesMetric.FUNDING_RATE, funding
            ),
            DerivativesMetric.BASIS_RATE: series(
                DerivativesMetric.BASIS_RATE, ("0.01", "0.03")
            ),
            DerivativesMetric.TAKER_BUY_SELL_RATIO: series(
                DerivativesMetric.TAKER_BUY_SELL_RATIO, ("1", "1.5")
            ),
            DerivativesMetric.TOP_POSITION_RATIO: series(
                DerivativesMetric.TOP_POSITION_RATIO, ("1.4",)
            ),
            DerivativesMetric.GLOBAL_ACCOUNT_RATIO: series(
                DerivativesMetric.GLOBAL_ACCOUNT_RATIO, ("1.1",)
            ),
            DerivativesMetric.MARK_PRICE: series(
                DerivativesMetric.MARK_PRICE, ("101",)
            ),
            DerivativesMetric.INDEX_PRICE: series(
                DerivativesMetric.INDEX_PRICE, ("100",)
            ),
        },
    )


def test_taxonomy_contains_required_event_families() -> None:
    assert WhaleEventType.WHALE_TO_BINANCE.value == "WHALE_TO_BINANCE"
    assert WhaleEventType.TOKEN_UNLOCK_MOVEMENT.value == "TOKEN_UNLOCK_MOVEMENT"
    assert SocialEventType.SECURITY_INCIDENT.value == "SECURITY_INCIDENT"
    assert DerivativesMetric.ADL_RISK.value == "ADL_RISK"


def test_provenance_and_dataset_fail_closed() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        Provenance("source", NOW, "http://unsafe.example")
    with pytest.raises(ValueError, match="timezone-aware"):
        Provenance("source", datetime(2026, 7, 13), "https://example.com")
    original = point(DerivativesMetric.OPEN_INTEREST, 0, "100")
    mismatch = replace(original, metric=DerivativesMetric.FUNDING_RATE)
    with pytest.raises(ValueError, match="mismatched"):
        DerivativesDataset(
            "HOTUSDT", NOW, {DerivativesMetric.OPEN_INTEREST: (mismatch,)}
        )
    with pytest.raises(ValueError, match="chronological"):
        DerivativesDataset(
            "HOTUSDT",
            NOW,
            {DerivativesMetric.OPEN_INTEREST: (original, original)},
        )


@pytest.mark.parametrize(
    ("prices", "oi", "expected"),
    [
        (
            ("100", "101", "102", "103", "104"),
            ("100", "101", "102", "103", "104"),
            PriceOiRegime.NEW_LONG_PARTICIPATION,
        ),
        (
            ("100", "101", "102", "103", "104"),
            ("104", "103", "102", "101", "100"),
            PriceOiRegime.SHORT_COVERING,
        ),
        (
            ("104", "103", "102", "101", "100"),
            ("100", "101", "102", "103", "104"),
            PriceOiRegime.NEW_SHORT_PRESSURE,
        ),
        (
            ("104", "103", "102", "101", "100"),
            ("104", "103", "102", "101", "100"),
            PriceOiRegime.DELEVERAGING,
        ),
    ],
)
def test_price_oi_regime_matrix(
    prices: tuple[str, ...], oi: tuple[str, ...], expected: PriceOiRegime
) -> None:
    features = DerivativesFeatureEngine().compute(
        dataset(oi), tuple(Decimal(value) for value in prices)
    )
    assert features.price_oi_regime is expected
    assert features.execution_allowed is False
    assert features.promotion_status == "RESEARCH_ONLY"


def test_feature_engine_computes_bounded_context_metrics() -> None:
    features = DerivativesFeatureEngine().compute(
        dataset(("100", "105", "110", "115", "120")),
        tuple(Decimal(value) for value in ("100", "101", "102", "103", "104")),
    )
    assert features.oi_change_short == Decimal("120") / Decimal("115") - 1
    assert features.oi_change_medium == Decimal("0.2")
    assert features.oi_zscore is not None
    assert features.oi_zscore > 0
    assert features.oi_percentile == Decimal("1")
    assert features.funding_percentile == Decimal("1")
    assert features.basis_zscore == Decimal("1")
    assert features.taker_imbalance == Decimal("0.2")
    assert features.top_vs_global_divergence == Decimal("0.3")
    assert features.mark_index_deviation == Decimal("0.01")
    assert not features.blockers


def test_feature_engine_marks_missing_history_and_rejects_bad_config() -> None:
    features = DerivativesFeatureEngine().compute(dataset(()), ())
    assert "OI_OR_PRICE_HISTORY_INSUFFICIENT" in features.blockers
    assert "OPEN_INTEREST_MISSING" in features.blockers
    assert features.price_oi_regime is PriceOiRegime.FLAT_OR_MIXED
    with pytest.raises(ValueError, match="lookbacks"):
        DerivativesFeatureEngine(short_lookback=2, medium_lookback=1)
    with pytest.raises(ValueError, match="execution authority"):
        replace(features, execution_allowed=True)

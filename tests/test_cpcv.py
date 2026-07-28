import pytest

from ai4binance.validation.cpcv import (
    CPCVConfig,
    CPCVDiagnosticReport,
    build_cpcv_diagnostic,
)


def test_cpcv_builds_purged_embargoed_combinations() -> None:
    label_ends = tuple(min(23, index + 2) for index in range(24))

    report = build_cpcv_diagnostic(
        label_ends,
        config=CPCVConfig(group_count=6, test_group_count=2, embargo_samples=3),
    )

    assert report.split_count == 15
    assert report.test_coverage_count == 24
    assert report.diagnostic_passed is True
    assert any(split.purged_count > 0 for split in report.splits)
    assert any(split.embargoed_count > 0 for split in report.splits)
    assert report.execution_allowed is False


def test_cpcv_reports_insufficient_split_design() -> None:
    report = build_cpcv_diagnostic(
        tuple(range(12)),
        config=CPCVConfig(group_count=4, test_group_count=1, minimum_splits=5),
    )

    assert report.diagnostic_passed is False
    assert report.blockers == ("CPCV_SPLIT_COUNT_INSUFFICIENT",)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"group_count": 2}, "group count"),
        ({"group_count": 3, "test_group_count": 3}, "test groups"),
        ({"embargo_samples": -1}, "embargo"),
    ],
)
def test_cpcv_config_rejects_invalid_designs(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CPCVConfig(**kwargs)


def test_cpcv_rejects_invalid_samples_and_reports_small_train_set() -> None:
    with pytest.raises(ValueError, match="one sample"):
        build_cpcv_diagnostic((0, 1), config=CPCVConfig(group_count=3))
    with pytest.raises(ValueError, match="causal"):
        build_cpcv_diagnostic((0, 0, 2), config=CPCVConfig(group_count=3))

    report = build_cpcv_diagnostic(
        (0, 1, 2),
        config=CPCVConfig(
            group_count=3,
            test_group_count=2,
            minimum_splits=1,
            embargo_samples=0,
        ),
    )
    assert report.blockers == ("CPCV_TRAIN_SAMPLE_INSUFFICIENT",)

    with pytest.raises(ValueError, match="promotion"):
        CPCVDiagnosticReport(3, 0, 0, 0, (), (), True, "STAGED", False)
    with pytest.raises(ValueError, match="status"):
        CPCVDiagnosticReport(3, 0, 0, 0, (), ("BLOCKED",), True)

"""Combinatorial purged cross-validation split diagnostics."""

from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True, slots=True)
class CPCVConfig:
    group_count: int = 6
    test_group_count: int = 2
    embargo_samples: int = 1
    minimum_splits: int = 10

    def __post_init__(self) -> None:
        if not 3 <= self.group_count <= 20:
            raise ValueError("CPCV group count must be between 3 and 20")
        if not 1 <= self.test_group_count < self.group_count:
            raise ValueError("CPCV test groups must be fewer than all groups")
        if self.embargo_samples < 0 or self.minimum_splits < 1:
            raise ValueError("CPCV embargo and minimum splits are invalid")


@dataclass(frozen=True, slots=True)
class CPCVSplit:
    split_id: str
    test_groups: tuple[int, ...]
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    purged_count: int
    embargoed_count: int


@dataclass(frozen=True, slots=True)
class CPCVDiagnosticReport:
    sample_count: int
    split_count: int
    test_coverage_count: int
    minimum_train_size: int
    splits: tuple[CPCVSplit, ...]
    blockers: tuple[str, ...]
    diagnostic_passed: bool
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("CPCV diagnostic cannot grant promotion or execution")
        if self.diagnostic_passed == bool(self.blockers):
            raise ValueError("CPCV diagnostic status must match blockers")


def build_cpcv_diagnostic(
    label_end_indices: tuple[int, ...],
    *,
    config: CPCVConfig | None = None,
) -> CPCVDiagnosticReport:
    """Build deterministic combinatorial splits with purge and embargo."""
    selected_config = config or CPCVConfig()
    sample_count = len(label_end_indices)
    if sample_count < selected_config.group_count:
        raise ValueError("CPCV requires at least one sample per group")
    if any(
        end < index or end >= sample_count
        for index, end in enumerate(label_end_indices)
    ):
        raise ValueError("CPCV label end indices must be causal and bounded")
    groups = _groups(sample_count, selected_config.group_count)
    splits: list[CPCVSplit] = []
    for split_index, test_group_ids in enumerate(
        combinations(
            range(selected_config.group_count), selected_config.test_group_count
        ),
        start=1,
    ):
        test_indices = tuple(
            index for group_id in test_group_ids for index in groups[group_id]
        )
        test_intervals = tuple(
            (index, label_end_indices[index]) for index in test_indices
        )
        raw_train = tuple(
            index
            for group_id, group in enumerate(groups)
            if group_id not in test_group_ids
            for index in group
        )
        purged = tuple(
            index
            for index in raw_train
            if any(
                _overlaps(
                    (index, label_end_indices[index]),
                    test_interval,
                )
                for test_interval in test_intervals
            )
        )
        embargoed = tuple(
            index
            for index in raw_train
            if index not in purged
            and any(
                group[-1] < index <= group[-1] + selected_config.embargo_samples
                for group_id, group in enumerate(groups)
                if group_id in test_group_ids
            )
        )
        excluded = frozenset((*purged, *embargoed))
        train = tuple(index for index in raw_train if index not in excluded)
        splits.append(
            CPCVSplit(
                split_id=f"cpcv:{split_index:03d}",
                test_groups=test_group_ids,
                train_indices=train,
                test_indices=test_indices,
                purged_count=len(purged),
                embargoed_count=len(embargoed),
            )
        )
    coverage = len({index for split in splits for index in split.test_indices})
    minimum_train = min((len(split.train_indices) for split in splits), default=0)
    blockers: list[str] = []
    if len(splits) < selected_config.minimum_splits:
        blockers.append("CPCV_SPLIT_COUNT_INSUFFICIENT")
    if coverage != sample_count:
        blockers.append("CPCV_TEST_COVERAGE_INCOMPLETE")
    if minimum_train < 2:
        blockers.append("CPCV_TRAIN_SAMPLE_INSUFFICIENT")
    unique = tuple(dict.fromkeys(blockers))
    return CPCVDiagnosticReport(
        sample_count=sample_count,
        split_count=len(splits),
        test_coverage_count=coverage,
        minimum_train_size=minimum_train,
        splits=tuple(splits),
        blockers=unique,
        diagnostic_passed=not unique,
    )


def _groups(sample_count: int, group_count: int) -> tuple[tuple[int, ...], ...]:
    base, remainder = divmod(sample_count, group_count)
    groups: list[tuple[int, ...]] = []
    start = 0
    for group_id in range(group_count):
        size = base + (1 if group_id < remainder else 0)
        groups.append(tuple(range(start, start + size)))
        start += size
    return tuple(groups)


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] <= right[1] and right[0] <= left[1]

"""Canonical root-cause reduction for virtual blocker tuples."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ai4binance.governance.blockers import (
    BLOCKER_REGISTRY_PATH,
    BlockerRegistry,
    load_blocker_registry,
)

_STAGE_NAMES = (
    "analysis",
    "candidate",
    "risk",
    "validation",
    "dge",
    "portfolio",
    "feasibility",
    "authority",
)


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _unique_sequence(*groups: tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    for group in groups:
        for item in group:
            if item not in ordered:
                ordered.append(item)
    return tuple(ordered)


@lru_cache(maxsize=1)
def _blocker_registry() -> BlockerRegistry:
    repo_root = Path(__file__).resolve().parents[3]
    return load_blocker_registry(repo_root / BLOCKER_REGISTRY_PATH)


def _is_known_blocker_code(blocker_code: str) -> bool:
    try:
        _blocker_registry().require_known_code(blocker_code)
    except Exception:
        return False
    return True


@dataclass(frozen=True, slots=True)
class VirtualBlockerReduction:
    """Stable canonical blocker reduction for one virtual decision cycle."""

    analysis_blockers: tuple[str, ...]
    candidate_blockers: tuple[str, ...]
    risk_blockers: tuple[str, ...]
    validation_blockers: tuple[str, ...]
    dge_blockers: tuple[str, ...]
    portfolio_blockers: tuple[str, ...]
    feasibility_blockers: tuple[str, ...]
    authority_blockers: tuple[str, ...]
    root_cause_codes: tuple[str, ...]
    known_blockers: tuple[str, ...]
    unknown_blockers: tuple[str, ...]
    blocker_count: int

    @property
    def has_unknown_classifications(self) -> bool:
        return bool(self.unknown_blockers)

    def __post_init__(self) -> None:
        for name, values in (
            ("analysis blockers", self.analysis_blockers),
            ("candidate blockers", self.candidate_blockers),
            ("risk blockers", self.risk_blockers),
            ("validation blockers", self.validation_blockers),
            ("dge blockers", self.dge_blockers),
            ("portfolio blockers", self.portfolio_blockers),
            ("feasibility blockers", self.feasibility_blockers),
            ("authority blockers", self.authority_blockers),
            ("root cause codes", self.root_cause_codes),
            ("known blockers", self.known_blockers),
            ("unknown blockers", self.unknown_blockers),
        ):
            _require_unique_nonblank(name, values)
        expected_root_cause_codes = _unique_sequence(
            self.analysis_blockers,
            self.candidate_blockers,
            self.risk_blockers,
            self.validation_blockers,
            self.dge_blockers,
            self.portfolio_blockers,
            self.feasibility_blockers,
            self.authority_blockers,
        )
        if self.root_cause_codes != expected_root_cause_codes:
            raise ValueError(
                "virtual blocker reduction root cause codes must preserve stage order"
            )
        if self.blocker_count != len(self.root_cause_codes):
            raise ValueError("virtual blocker reduction blocker count is inconsistent")
        classified_codes = set(self.known_blockers) | set(self.unknown_blockers)
        if classified_codes != set(self.root_cause_codes):
            raise ValueError(
                "virtual blocker reduction classifications must cover every root cause"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "analysis_blockers": list(self.analysis_blockers),
            "candidate_blockers": list(self.candidate_blockers),
            "risk_blockers": list(self.risk_blockers),
            "validation_blockers": list(self.validation_blockers),
            "dge_blockers": list(self.dge_blockers),
            "portfolio_blockers": list(self.portfolio_blockers),
            "feasibility_blockers": list(self.feasibility_blockers),
            "authority_blockers": list(self.authority_blockers),
            "root_cause_codes": list(self.root_cause_codes),
            "known_blockers": list(self.known_blockers),
            "unknown_blockers": list(self.unknown_blockers),
            "blocker_count": self.blocker_count,
            "has_unknown_classifications": self.has_unknown_classifications,
        }


def reduce_virtual_blockers(
    *,
    analysis_blockers: tuple[str, ...] = (),
    candidate_blockers: tuple[str, ...] = (),
    risk_blockers: tuple[str, ...] = (),
    validation_blockers: tuple[str, ...] = (),
    dge_blockers: tuple[str, ...] = (),
    portfolio_blockers: tuple[str, ...] = (),
    feasibility_blockers: tuple[str, ...] = (),
    authority_blockers: tuple[str, ...] = (),
) -> VirtualBlockerReduction:
    """Reduce virtual blocker tuples into one ordered root-cause set."""

    root_cause_codes = _unique_sequence(
        analysis_blockers,
        candidate_blockers,
        risk_blockers,
        validation_blockers,
        dge_blockers,
        portfolio_blockers,
        feasibility_blockers,
        authority_blockers,
    )
    known_blockers = tuple(
        blocker_code
        for blocker_code in root_cause_codes
        if _is_known_blocker_code(blocker_code)
    )
    unknown_blockers = tuple(
        blocker_code
        for blocker_code in root_cause_codes
        if blocker_code not in known_blockers
    )
    return VirtualBlockerReduction(
        analysis_blockers=analysis_blockers,
        candidate_blockers=candidate_blockers,
        risk_blockers=risk_blockers,
        validation_blockers=validation_blockers,
        dge_blockers=dge_blockers,
        portfolio_blockers=portfolio_blockers,
        feasibility_blockers=feasibility_blockers,
        authority_blockers=authority_blockers,
        root_cause_codes=root_cause_codes,
        known_blockers=known_blockers,
        unknown_blockers=unknown_blockers,
        blocker_count=len(root_cause_codes),
    )

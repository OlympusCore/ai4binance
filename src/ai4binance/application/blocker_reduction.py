"""Classify virtual blockers using the governed application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ai4binance.application.blocker_registry import load_blocker_registry
from ai4binance.domain.blocker_reduction import VirtualBlockerReduction
from ai4binance.domain.blocker_reduction import (
    reduce_virtual_blockers as reduce_blocker_groups,
)
from ai4binance.domain.blockers import BLOCKER_REGISTRY_PATH, BlockerRegistry


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
    """Resolve governed classifications and delegate to the pure reducer."""

    return reduce_blocker_groups(
        is_known_blocker=_is_known_blocker_code,
        analysis_blockers=analysis_blockers,
        candidate_blockers=candidate_blockers,
        risk_blockers=risk_blockers,
        validation_blockers=validation_blockers,
        dge_blockers=dge_blockers,
        portfolio_blockers=portfolio_blockers,
        feasibility_blockers=feasibility_blockers,
        authority_blockers=authority_blockers,
    )

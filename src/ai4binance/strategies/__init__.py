"""Governed strategy playbooks and candidate generation."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai4binance.strategies.engine import StrategyEngine
from ai4binance.strategies.registry import (
    build_governed_strategy_registry,
    build_playbook_registry,
)

__all__ = (
    "StrategyEngine",
    "build_governed_strategy_registry",
    "build_playbook_registry",
)


def __getattr__(name: str) -> object:
    """Keep registry/rule imports independent of the runtime risk graph."""
    if name != "StrategyEngine":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from ai4binance.strategies.engine import StrategyEngine

    return StrategyEngine

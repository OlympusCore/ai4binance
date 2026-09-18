"""Compatibility bridge for live-readiness contracts."""

from __future__ import annotations

from importlib import import_module

_live_readiness = import_module("ai4binance.execution.live_readiness")
LiveReadinessBuilder = _live_readiness.LiveReadinessBuilder
LiveReadinessEvidence = _live_readiness.LiveReadinessEvidence

__all__ = (
    "LiveReadinessBuilder",
    "LiveReadinessEvidence",
)


def __getattr__(name: str) -> object:
    if name in __all__:
        value = getattr(_live_readiness, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)

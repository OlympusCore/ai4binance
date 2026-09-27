"""Application services with explicit domain and adapter boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai4binance.application.services.virtual_runtime import (
        VirtualMarketCycleResult as VirtualMarketCycleResult,
    )
    from ai4binance.application.services.virtual_runtime import (
        evaluate_virtual_market_runtime as evaluate_virtual_market_runtime,
    )
    from ai4binance.application.services.virtual_runtime import (
        run_virtual_market_cycle as run_virtual_market_cycle,
    )

__all__ = (
    "VirtualMarketCycleResult",
    "evaluate_virtual_market_runtime",
    "run_virtual_market_cycle",
)


def __getattr__(name: str) -> object:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import ai4binance.application.services.virtual_runtime as virtual_runtime

    value = getattr(virtual_runtime, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

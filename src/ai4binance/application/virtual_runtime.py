"""Compatibility facade for the canonical virtual-market runtime service."""

from importlib import import_module

from ai4binance.application.services.virtual_runtime import (
    VirtualMarketCycleResult as VirtualMarketCycleResult,
)
from ai4binance.application.services.virtual_runtime import (
    VirtualSimulationEligibility as VirtualSimulationEligibility,
)
from ai4binance.application.services.virtual_runtime import (
    VirtualSimulationStatus as VirtualSimulationStatus,
)
from ai4binance.application.services.virtual_runtime import (
    evaluate_virtual_market_runtime as evaluate_virtual_market_runtime,
)
from ai4binance.application.services.virtual_runtime import (
    evaluate_virtual_simulation_eligibility as evaluate_virtual_simulation_eligibility,
)
from ai4binance.application.services.virtual_runtime import (
    run_virtual_market_cycle as run_virtual_market_cycle,
)

_canonical_virtual_runtime = import_module(
    "ai4binance.application.services.virtual_runtime"
)

__all__ = _canonical_virtual_runtime.__all__


def __getattr__(name: str) -> object:
    if name in __all__:
        value = getattr(_canonical_virtual_runtime, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)

"""Compatibility facade for canonical shared CLI services."""

from ai4binance.cli.bootstrap.shared import (
    __dir__ as __dir__,
)
from ai4binance.cli.bootstrap.shared import (
    build_public_acquisition as build_public_acquisition,
)
from ai4binance.cli.bootstrap.shared import (
    virtual_market_gate_payload as virtual_market_gate_payload,
)
from ai4binance.cli.bootstrap.shared import (
    virtual_runtime_decision_payload as virtual_runtime_decision_payload,
)

__all__ = (
    "virtual_market_gate_payload",
    "virtual_runtime_decision_payload",
)

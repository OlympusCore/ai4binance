"""Fail-closed boundary coverage for capability bundle execution."""

import pytest

from ai4binance.agents.bundles import CapabilityBundleExecutor
from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.registry import CapabilityBundleDefinition
from tests.test_agents import ReadyResultAgent, snapshot


def bundle() -> CapabilityBundleDefinition:
    """Create the smallest valid research-only bundle definition."""
    return CapabilityBundleDefinition("test-bundle", ("data_quality",))


def test_bundle_executor_rejects_invalid_membership_and_ready_sets() -> None:
    """Only declared, uniquely scheduled capability identities can run."""
    registry = build_default_registry()
    agent = ReadyResultAgent(registry.get("data_quality"))

    with pytest.raises(ValueError, match="requires scheduled agents"):
        CapabilityBundleExecutor(bundle(), {})
    with pytest.raises(ValueError, match="outside its bundle"):
        CapabilityBundleExecutor(bundle(), {"risk": agent})
    with pytest.raises(ValueError, match="identities must match"):
        CapabilityBundleExecutor(
            bundle(),
            {"data_quality": ReadyResultAgent(registry.get("risk"))},
        )

    executor = CapabilityBundleExecutor(bundle(), {"data_quality": agent})
    with pytest.raises(ValueError, match="unique and non-empty"):
        executor.run_ready(snapshot(), {}, ())
    with pytest.raises(ValueError, match="unavailable capabilities"):
        executor.run_ready(snapshot(), {}, ("risk",))

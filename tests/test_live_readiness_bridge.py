"""Live-readiness compatibility bridge contract tests."""

from __future__ import annotations

import pytest

import ai4binance.application as application_package
import ai4binance.application.live_readiness as live_readiness_bridge
from ai4binance.execution.live_readiness import (
    LiveReadinessBuilder,
    LiveReadinessEvidence,
)


def test_live_readiness_bridge_exports_are_resolvable() -> None:
    assert live_readiness_bridge.__all__ == (
        "LiveReadinessBuilder",
        "LiveReadinessEvidence",
    )
    assert live_readiness_bridge.__dir__() == list(live_readiness_bridge.__all__)
    assert live_readiness_bridge.LiveReadinessBuilder is LiveReadinessBuilder
    assert live_readiness_bridge.LiveReadinessEvidence is LiveReadinessEvidence


def test_live_readiness_application_exports_are_resolvable() -> None:
    assert application_package.LiveReadinessBuilder is LiveReadinessBuilder
    assert application_package.LiveReadinessEvidence is LiveReadinessEvidence
    assert "LiveReadinessBuilder" in application_package.__dir__()
    assert "LiveReadinessEvidence" in application_package.__dir__()
    assert vars(application_package)["LiveReadinessBuilder"] is LiveReadinessBuilder
    assert vars(application_package)["LiveReadinessEvidence"] is LiveReadinessEvidence


def test_live_readiness_bridge_getattr_falls_back_and_rejects_unknown_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(
        live_readiness_bridge,
        "LiveReadinessBuilder",
        raising=False,
    )

    assert live_readiness_bridge.LiveReadinessBuilder is LiveReadinessBuilder

    with pytest.raises(AttributeError, match="has no attribute 'missing_symbol'"):
        live_readiness_bridge.__getattr__("missing_symbol")

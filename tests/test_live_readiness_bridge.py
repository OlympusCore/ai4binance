"""Live-readiness compatibility bridge contract tests."""

from __future__ import annotations

import subprocess
import sys

import pytest

import ai4binance.application as application_package
import ai4binance.application.live_readiness as live_readiness_bridge
from ai4binance.execution.live_readiness import (
    LiveReadinessBuilder,
    LiveReadinessEvidence,
)


def test_readiness_cold_import_does_not_load_concrete_execution_adapters() -> None:
    result = subprocess.run(  # noqa: S603 -- Fixed interpreter and local import probe.
        [
            sys.executable,
            "-B",
            "-c",
            "import sys; import ai4binance.application.live_readiness; "
            "forbidden = ('ai4binance.execution', 'ai4binance.validation', "
            "'ai4binance.config', 'ai4binance.storage', "
            "'ai4binance.application.virtual_runtime_engine', "
            "'ai4binance.application.services.virtual_runtime'); "
            "loaded = [name for name in sys.modules if any("
            "name == prefix or name.startswith(prefix + '.') "
            "for prefix in forbidden)]; assert not loaded, loaded",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_services_package_lazy_exports_preserve_runtime_identity() -> None:
    from ai4binance.application import services
    from ai4binance.application.services import virtual_runtime

    for name in services.__all__:
        assert getattr(services, name) is getattr(virtual_runtime, name)
        assert name in dir(services)
    with pytest.raises(AttributeError, match="has no attribute 'missing_symbol'"):
        services.__getattr__("missing_symbol")


def test_readiness_pure_contracts_preserve_legacy_object_identity() -> None:
    from ai4binance.domain import live_gate, live_gate_evidence, order_command
    from ai4binance.domain import promotion_evidence as domain_promotion
    from ai4binance.execution import order_command as legacy_order
    from ai4binance.safety import evaluate_live_gate
    from ai4binance.validation import live_gate_evidence as legacy_evidence
    from ai4binance.validation import promotion_evidence as legacy_promotion

    assert evaluate_live_gate is live_gate.evaluate_live_gate
    assert legacy_order.SpotOrderCommand is order_command.SpotOrderCommand
    assert (
        legacy_evidence.LiveGateEvidenceKind is live_gate_evidence.LiveGateEvidenceKind
    )
    assert (
        legacy_evidence.LiveGateEvidenceResolution
        is live_gate_evidence.LiveGateEvidenceResolution
    )
    assert (
        legacy_promotion.PromotionEvidenceQuery
        is domain_promotion.PromotionEvidenceQuery
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


@pytest.mark.parametrize("name", application_package.__all__)
def test_application_lazy_exports_preserve_canonical_identity(name: str) -> None:
    exported = application_package.__getattr__(name)
    assert getattr(application_package, name) is exported


def test_application_exports_reject_unregistered_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(application_package._EXPORTS, "TestOnly", "unregistered")
    with pytest.raises(AttributeError, match="unregistered application export"):
        application_package.__getattr__("TestOnly")


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

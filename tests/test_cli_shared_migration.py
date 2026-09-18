from __future__ import annotations

import ai4binance.cli.bootstrap.shared as canonical_shared
import ai4binance.cli.shared as legacy_shared


def test_cli_shared_legacy_import_preserves_canonical_symbol_identity() -> None:
    assert (
        legacy_shared.build_public_acquisition
        is canonical_shared.build_public_acquisition
    )
    assert (
        legacy_shared.virtual_market_gate_payload
        is canonical_shared.virtual_market_gate_payload
    )
    assert (
        legacy_shared.virtual_runtime_decision_payload
        is canonical_shared.virtual_runtime_decision_payload
    )
    assert legacy_shared.__all__ == canonical_shared.__all__
    assert legacy_shared.__dir__ is canonical_shared.__dir__
    assert legacy_shared.__dir__() == list(legacy_shared.__all__)
    assert (
        canonical_shared.virtual_market_gate_payload.__module__
        == "ai4binance.cli.bootstrap.shared"
    )

from __future__ import annotations

import ai4binance.cli.bootstrap.skill_discovery as canonical_skill_discovery
import ai4binance.cli.skill_discovery as legacy_skill_discovery


def test_cli_skill_discovery_legacy_import_preserves_public_symbol_identity() -> None:
    assert (
        legacy_skill_discovery.run_skill_discovery_command
        is canonical_skill_discovery.run_skill_discovery_command
    )
    assert (
        canonical_skill_discovery.run_skill_discovery_command.__module__
        == "ai4binance.cli.bootstrap.skill_discovery"
    )

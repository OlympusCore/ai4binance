from __future__ import annotations

from ai4binance.cli.output import GROUP_ORDER as LEGACY_GROUP_ORDER
from ai4binance.cli.output import render_payload as legacy_render_payload
from ai4binance.cli.output import render_text as legacy_render_text
from ai4binance.cli.presentation import GROUP_ORDER, render_payload, render_text
from ai4binance.cli.presentation.output import (
    render_payload as canonical_render_payload,
)


def test_cli_output_legacy_import_preserves_canonical_symbol_identity() -> None:
    assert GROUP_ORDER is LEGACY_GROUP_ORDER
    assert render_payload is canonical_render_payload
    assert legacy_render_payload is canonical_render_payload
    assert render_text is legacy_render_text
    assert canonical_render_payload.__module__ == "ai4binance.cli.presentation.output"

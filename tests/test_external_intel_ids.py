"""Deterministic identifier contract tests for external intelligence evidence."""

from __future__ import annotations

import pytest

from ai4binance.external_intel.core.ids import eief_id


def test_eief_id_is_lowercase_prefixed_and_length_bounded() -> None:
    identifier = eief_id("Run", "BTCUSDT", "github", length=8)

    assert identifier.startswith("run_")
    assert len(identifier.removeprefix("run_")) == 8
    assert identifier == eief_id("Run", "BTCUSDT", "github", length=8)


@pytest.mark.parametrize("prefix", ["", " ", "run-id"])
def test_eief_id_rejects_invalid_prefix(prefix: str) -> None:
    with pytest.raises(ValueError, match="prefix must be alphanumeric"):
        eief_id(prefix, "material")


@pytest.mark.parametrize("parts", [(), (" ",), ("valid", "")])
def test_eief_id_rejects_missing_material(parts: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="id material is required"):
        eief_id("run", *parts)

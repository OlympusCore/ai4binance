"""Enterprise package export contract tests."""

from __future__ import annotations

from types import ModuleType

import pytest

import ai4binance.enterprise as enterprise


def test_enterprise_lazy_ykb_export_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = ModuleType("ai4binance.enterprise.ykb_report")
    sentinel = object()
    fake_module.__dict__["YkbExecutiveBrief"] = sentinel

    monkeypatch.delattr(enterprise, "YkbExecutiveBrief", raising=False)
    monkeypatch.setattr(enterprise, "import_module", lambda _: fake_module)

    assert enterprise.__getattr__("YkbExecutiveBrief") is sentinel
    assert vars(enterprise)["YkbExecutiveBrief"] is sentinel


def test_enterprise_unknown_export_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute"):
        enterprise.__getattr__("UnknownEnterpriseExport")

"""Entry-point coverage for the local agent workbench wrapper."""

from __future__ import annotations

import runpy

import pytest

from ai4binance.local_agent import workbench


def test_local_agent_main_uses_workbench_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workbench, "main", lambda: 7)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("ai4binance.local_agent.__main__", run_name="__main__")

    assert exc_info.value.code == 7

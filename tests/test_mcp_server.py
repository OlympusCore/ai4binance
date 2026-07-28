"""Optional FastMCP adapter tests without installing or starting a service."""

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.mcp import server


class FakeServer:
    def __init__(self) -> None:
        self.tools: dict[str, server.ToolFunction] = {}
        self.transport = ""

    def tool(
        self, *, name: str, description: str
    ) -> Callable[[server.ToolFunction], server.ToolFunction]:
        assert description

        def register(function: server.ToolFunction) -> server.ToolFunction:
            self.tools[name] = function
            return function

        return register

    def run(self, *, transport: str) -> None:
        self.transport = transport


def test_tool_registry_has_fixed_read_only_surface(tmp_path: Path) -> None:
    tools = server.build_tool_functions(tmp_path)

    assert tuple(tools) == (
        "health_check",
        "get_quality_triage",
        "get_market_outlook",
        "get_research_blockers",
    )
    health = json.loads(tools["health_check"]())
    assert health["execution_allowed"] is False
    assert health["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_create_server_registers_tools_and_runs_stdio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeServer()

    module = SimpleNamespace(FastMCP=lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(
        server,
        "load_fastmcp_factory",
        lambda: module.FastMCP,
    )

    created = server.create_server(tmp_path)
    created.run(transport="stdio")

    assert created is fake
    assert fake.transport == "stdio"
    assert set(fake.tools) == {
        "health_check",
        "get_quality_triage",
        "get_market_outlook",
        "get_research_blockers",
    }


def test_create_server_reports_missing_optional_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing() -> object:
        raise RuntimeError("MCP SDK is not installed; install the optional 'mcp' extra")

    monkeypatch.setattr(server, "load_fastmcp_factory", missing)

    with pytest.raises(RuntimeError, match="optional 'mcp' extra"):
        server.create_server(tmp_path)

"""Optional FastMCP adapter tests without installing or starting a service."""

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.mcp import WolframMcpRegistration, server


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
        "market.get_snapshot",
        "market.get_data_quality",
        "market.get_provenance",
        "evidence.get",
        "evidence.verify",
        "evidence.get_provenance",
        "evidence.find_conflicts",
        "evidence.build_bundle",
        "governance.get_policy",
        "governance.get_authority",
        "governance.check_action",
        "governance.check_contract",
        "governance.get_blockers",
        "quant_research.get_capabilities",
        "quant_research.verify_formula",
        "quant_research.assess_statistics",
        "quant_research.wolfram_status",
    )
    health = json.loads(tools["health_check"]())
    assert health["execution_allowed"] is False
    assert health["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_tool_registry_accepts_wolfram_registration_state(tmp_path: Path) -> None:
    tools = server.build_tool_functions(
        tmp_path,
        wolfram_registration=WolframMcpRegistration(
            enabled=True,
            endpoint_ref="local-wolfram-mcp",
            credential_configured=True,
            invocation_allowed=True,
        ),
    )

    status = json.loads(tools["quant_research.wolfram_status"]())
    verification = json.loads(tools["quant_research.verify_formula"]())

    assert status["blockers"] == []
    assert status["data"]["invocation_allowed"] is True
    assert verification["blockers"] == ["WOLFRAM_VERIFICATION_NOT_EXECUTED"]


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
        "market.get_snapshot",
        "market.get_data_quality",
        "market.get_provenance",
        "evidence.get",
        "evidence.verify",
        "evidence.get_provenance",
        "evidence.find_conflicts",
        "evidence.build_bundle",
        "governance.get_policy",
        "governance.get_authority",
        "governance.check_action",
        "governance.check_contract",
        "governance.get_blockers",
        "quant_research.get_capabilities",
        "quant_research.verify_formula",
        "quant_research.assess_statistics",
        "quant_research.wolfram_status",
    }


def test_create_server_reports_missing_optional_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing() -> object:
        raise RuntimeError("MCP SDK is not installed; install the optional 'mcp' extra")

    monkeypatch.setattr(server, "load_fastmcp_factory", missing)

    with pytest.raises(RuntimeError, match="optional 'mcp' extra"):
        server.create_server(tmp_path)

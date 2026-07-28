"""Optional FastMCP STDIO adapter for the read-only evidence gateway."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from ai4binance.mcp.evidence import EvidenceEnvelope, EvidenceGateway
from ai4binance.reporting import to_primitive

ToolFunction = Callable[[], str]


class _FastMCPServer(Protocol):
    def tool(
        self, *, name: str, description: str
    ) -> Callable[[ToolFunction], ToolFunction]: ...

    def run(self, *, transport: str) -> None: ...


class _FastMCPFactory(Protocol):
    def __call__(
        self, name: str, *, instructions: str, json_response: bool
    ) -> _FastMCPServer: ...


def _encode(envelope: EvidenceEnvelope) -> str:
    return json.dumps(to_primitive(envelope), ensure_ascii=False, sort_keys=True)


def build_tool_functions(artifact_root: Path) -> Mapping[str, ToolFunction]:
    """Build a fixed tool registry with no caller-controlled path access."""
    gateway = EvidenceGateway(artifact_root)
    return {
        "health_check": lambda: _encode(gateway.health_check()),
        "get_quality_triage": lambda: _encode(gateway.get_quality_triage()),
        "get_market_outlook": lambda: _encode(gateway.get_market_outlook()),
        "get_research_blockers": lambda: _encode(gateway.get_research_blockers()),
    }


def load_fastmcp_factory() -> _FastMCPFactory:
    """Load the optional SDK factory with an actionable bounded failure."""
    try:
        module = importlib.import_module("mcp.server.fastmcp")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "MCP SDK is not installed; install the optional 'mcp' extra"
        ) from error
    return cast(_FastMCPFactory, vars(module)["FastMCP"])


def create_server(artifact_root: Path) -> _FastMCPServer:
    """Create the optional SDK adapter without making MCP a core dependency."""
    factory = load_fastmcp_factory()
    server = factory(
        "AI4BINANCE Read-Only Evidence",
        instructions=(
            "Read advisory research evidence only. Never infer execution authority, "
            "change risk, promote parameters, or place orders."
        ),
        json_response=True,
    )
    descriptions = {
        "health_check": "Return read-only MCP capability and safety status.",
        "get_quality_triage": "Read the latest bounded nightly quality report.",
        "get_market_outlook": "Read the latest deterministic market outlook artifact.",
        "get_research_blockers": "Aggregate current evidence and research blockers.",
    }
    for name, function in build_tool_functions(artifact_root).items():
        server.tool(name=name, description=descriptions[name])(function)
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI4BINANCE read-only evidence MCP server"
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("Artifacts"),
        help="Allowlisted evidence root; arbitrary tool paths are not supported.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run only the local STDIO transport; remote exposure is out of scope."""
    parsed = build_parser().parse_args(arguments)
    create_server(parsed.artifact_root).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

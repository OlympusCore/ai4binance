"""Optional FastMCP STDIO adapter for the read-only evidence gateway."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from ai4binance.mcp.evidence import EvidenceEnvelope, EvidenceGateway
from ai4binance.mcp.governance import GovernanceMcpGateway
from ai4binance.mcp.market_data import MarketDataGateway
from ai4binance.mcp.quant_research import QuantResearchGateway, WolframMcpRegistration
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


def build_tool_functions(
    artifact_root: Path,
    *,
    wolfram_registration: WolframMcpRegistration | None = None,
) -> Mapping[str, ToolFunction]:
    """Build a fixed tool registry with no caller-controlled path access."""
    evidence = EvidenceGateway(artifact_root)
    market = MarketDataGateway(artifact_root)
    governance = GovernanceMcpGateway()
    quant = QuantResearchGateway(
        wolfram_registration=wolfram_registration or WolframMcpRegistration()
    )
    return {
        "health_check": lambda: _encode(evidence.health_check()),
        "get_quality_triage": lambda: _encode(evidence.get_quality_triage()),
        "get_market_outlook": lambda: _encode(evidence.get_market_outlook()),
        "get_research_blockers": lambda: _encode(evidence.get_research_blockers()),
        "market.get_snapshot": lambda: _encode(market.get_snapshot()),
        "market.get_data_quality": lambda: _encode(market.get_data_quality()),
        "market.get_provenance": lambda: _encode(market.get_provenance()),
        "evidence.get": lambda: _encode(evidence.get_evidence()),
        "evidence.verify": lambda: _encode(evidence.verify_evidence()),
        "evidence.get_provenance": lambda: _encode(evidence.get_provenance()),
        "evidence.find_conflicts": lambda: _encode(evidence.find_conflicts()),
        "evidence.build_bundle": lambda: _encode(evidence.build_bundle()),
        "governance.get_policy": lambda: _encode(governance.get_policy()),
        "governance.get_authority": lambda: _encode(governance.get_authority()),
        "governance.check_action": lambda: _encode(governance.check_action()),
        "governance.check_contract": lambda: _encode(governance.check_contract()),
        "governance.get_blockers": lambda: _encode(governance.get_blockers()),
        "quant_research.get_capabilities": lambda: _encode(quant.get_capabilities()),
        "quant_research.verify_formula": lambda: _encode(quant.verify_formula()),
        "quant_research.assess_statistics": lambda: _encode(quant.assess_statistics()),
        "quant_research.wolfram_status": lambda: _encode(quant.wolfram_status()),
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


def create_server(
    artifact_root: Path,
    *,
    wolfram_registration: WolframMcpRegistration | None = None,
) -> _FastMCPServer:
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
        "market.get_snapshot": "Read the latest canonical market snapshot artifact.",
        "market.get_data_quality": "Read the latest market data quality artifact.",
        "market.get_provenance": "Read the latest market provenance artifact.",
        "evidence.get": "Read the bounded local evidence index.",
        "evidence.verify": "Verify bounded evidence without granting authority.",
        "evidence.get_provenance": "Read source hashes for bounded evidence.",
        "evidence.find_conflicts": "Find blockers across bounded evidence.",
        "evidence.build_bundle": "Build a bounded evidence bundle.",
        "governance.get_policy": "Read MCP policy metadata.",
        "governance.get_authority": "Read MCP authority classes.",
        "governance.check_action": "Check representative MCP action authority.",
        "governance.check_contract": "Validate MCP gateway invariants.",
        "governance.get_blockers": "Read hard MCP authority blockers.",
        "quant_research.get_capabilities": (
            "Read cold-path Quant Research MCP capabilities."
        ),
        "quant_research.verify_formula": (
            "Run bounded formula verification with Wolfram provider gating."
        ),
        "quant_research.assess_statistics": (
            "Run deterministic reference statistical assessment."
        ),
        "quant_research.wolfram_status": (
            "Read external Wolfram MCP registration status without secrets."
        ),
    }
    for name, function in build_tool_functions(
        artifact_root,
        wolfram_registration=wolfram_registration,
    ).items():
        server.tool(name=name, description=descriptions[name])(function)
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI4BINANCE read-only evidence MCP server"
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("runtime/artifacts"),
        help="Allowlisted evidence root; arbitrary tool paths are not supported.",
    )
    parser.add_argument(
        "--wolfram-mcp-enabled",
        action="store_true",
        help="Mark the external Wolfram MCP provider as enabled.",
    )
    parser.add_argument(
        "--wolfram-mcp-endpoint-ref",
        default=None,
        help="Redaction-safe Wolfram MCP endpoint reference; secrets are not accepted.",
    )
    parser.add_argument(
        "--wolfram-mcp-credential-configured",
        action="store_true",
        help="Mark that Wolfram MCP credentials are configured outside this process.",
    )
    parser.add_argument(
        "--wolfram-mcp-invocation-allowed",
        action="store_true",
        help=(
            "Allow registered Wolfram MCP invocation gating; live trading "
            "remains blocked."
        ),
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run only the local STDIO transport; remote exposure is out of scope."""
    parsed = build_parser().parse_args(arguments)
    wolfram_registration = WolframMcpRegistration(
        enabled=parsed.wolfram_mcp_enabled,
        endpoint_ref=parsed.wolfram_mcp_endpoint_ref,
        credential_configured=parsed.wolfram_mcp_credential_configured,
        invocation_allowed=parsed.wolfram_mcp_invocation_allowed,
    )
    create_server(
        parsed.artifact_root,
        wolfram_registration=wolfram_registration,
    ).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

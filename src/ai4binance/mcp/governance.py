"""Read-only Governance MCP contracts for policy and blocker checks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai4binance.governance import (
    DEFAULT_DENIED_MCP_TOOLS,
    EXECUTION_SENSITIVE_MCP_TOOLS,
    McpAuthorityClass,
    build_ai4binance_mcp_gateway_contract,
    classify_mcp_tool_authority,
)
from ai4binance.mcp.evidence import EvidenceEnvelope, FreshnessStatus


def _hash_payload(data: Mapping[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class GovernanceMcpGateway:
    """Expose read-only governance checks without policy mutation authority."""

    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def get_policy(self) -> EvidenceEnvelope:
        """Return default-deny MCP policy metadata."""
        contract = build_ai4binance_mcp_gateway_contract()
        data: Mapping[str, object] = {
            "gateway_id": contract.gateway_id,
            "version": contract.version,
            "route": tuple(step.value for step in contract.route),
            "default_denied_tools": DEFAULT_DENIED_MCP_TOOLS,
            "execution_sensitive_tools": EXECUTION_SENSITIVE_MCP_TOOLS,
        }
        return self._envelope("governance_policy", data)

    def get_authority(self) -> EvidenceEnvelope:
        """Return MCP authority class definitions."""
        data: Mapping[str, object] = {
            "classes": tuple(item.value for item in McpAuthorityClass),
            "initial_posture": {
                "MCP_R0_READ_ONLY": "BROADLY_ALLOWED",
                "MCP_R1_ANALYZE_COMPUTE": "ALLOWED",
                "MCP_R2_CREATE_RESEARCH_ARTIFACTS": "GOVERNED",
                "MCP_R3_CONTROLLED_STATE_MUTATION": "EXCEPTIONAL",
                "MCP_X_EXECUTION_SENSITIVE": "BLOCKED",
            },
        }
        return self._envelope("governance_authority", data)

    def check_action(self) -> EvidenceEnvelope:
        """Check representative MCP actions against the authority matrix."""
        tools = (
            "market.get_snapshot",
            "quant_research.verify_formula",
            "evidence.build_bundle",
            "order.live.submit",
        )
        data: Mapping[str, object] = {
            tool: classify_mcp_tool_authority(tool).value for tool in tools
        }
        blockers = ("MCP_X_BLOCKED",)
        return self._envelope("governance_action_check", data, blockers=blockers)

    def check_contract(self) -> EvidenceEnvelope:
        """Validate core MCP gateway invariants without mutating policy."""
        contract = build_ai4binance_mcp_gateway_contract()
        data: Mapping[str, object] = {
            "direct_agent_to_mcp_allowed": contract.direct_agent_to_mcp_allowed,
            "execution_allowed": contract.execution_allowed,
            "live_eligibility_status": contract.live_eligibility_status,
            "blockers_cannot_be_compensated": True,
        }
        return self._envelope("governance_contract_check", data)

    def get_blockers(self) -> EvidenceEnvelope:
        """Return hard MCP authority blockers."""
        data: Mapping[str, object] = {
            "blockers": (
                "MCP_X_BLOCKED",
                "LIVE_ORDER_BLOCKED",
                "DIRECT_AGENT_TO_MCP_BLOCKED",
            )
        }
        return self._envelope(
            "governance_blockers",
            data,
            blockers=("MCP_X_BLOCKED", "LIVE_ORDER_BLOCKED"),
        )

    def _envelope(
        self,
        artifact_type: str,
        data: Mapping[str, object],
        *,
        blockers: tuple[str, ...] = (),
    ) -> EvidenceEnvelope:
        return EvidenceEnvelope(
            artifact_type=artifact_type,
            generated_at=self._now(),
            source_artifact=f"embedded://mcp/{artifact_type}",
            source_sha256=_hash_payload(data),
            freshness_status=FreshnessStatus.FRESH,
            blockers=blockers,
            data=data,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("governance MCP clock must be timezone-aware")
        return value

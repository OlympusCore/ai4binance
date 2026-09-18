"""Cold-path Quant Research MCP contracts with Wolfram provider gating."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai4binance.mcp.evidence import EvidenceEnvelope, FreshnessStatus

_REFERENCE_RETURNS = (0.01, -0.005, 0.02, -0.01, 0.015)


def _hash_payload(data: Mapping[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class WolframMcpRegistration:
    """Registration state for an optional external Wolfram MCP provider."""

    provider_name: str = "Wolfram MCP"
    enabled: bool = False
    endpoint_ref: str | None = None
    credential_configured: bool = False
    invocation_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("Wolfram MCP provider name cannot be empty")
        if self.endpoint_ref is not None and not self.endpoint_ref.strip():
            raise ValueError("Wolfram MCP endpoint reference cannot be empty")
        if self.invocation_allowed and (
            not self.enabled
            or self.endpoint_ref is None
            or not self.credential_configured
        ):
            raise ValueError("Wolfram MCP invocation requires complete registration")

    @property
    def blockers(self) -> tuple[str, ...]:
        if self.invocation_allowed:
            return ()
        blockers = ["WOLFRAM_MCP_INVOCATION_BLOCKED"]
        if not self.enabled:
            blockers.append("WOLFRAM_MCP_DISABLED")
        if self.endpoint_ref is None:
            blockers.append("WOLFRAM_MCP_ENDPOINT_MISSING")
        if not self.credential_configured:
            blockers.append("WOLFRAM_MCP_CREDENTIAL_MISSING")
        return tuple(blockers)

    def to_public_data(self) -> Mapping[str, object]:
        """Return redaction-safe registration metadata."""
        return {
            "provider_name": self.provider_name,
            "enabled": self.enabled,
            "endpoint_configured": self.endpoint_ref is not None,
            "credential_configured": self.credential_configured,
            "invocation_allowed": self.invocation_allowed,
        }


@dataclass(slots=True)
class QuantResearchGateway:
    """Expose deterministic research computations without trading authority."""

    wolfram_registration: WolframMcpRegistration = WolframMcpRegistration()
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def get_capabilities(self) -> EvidenceEnvelope:
        """Return the Quant Research MCP capability surface."""
        data: Mapping[str, object] = {
            "service": "ai4binance-quant-research-mcp",
            "cold_path_only": True,
            "tool_groups": (
                "quant_math",
                "quant_statistics",
                "quant_timeseries",
                "quant_optimization",
                "quant_signal",
                "quant_validation",
            ),
            "tools": (
                "quant_research.get_capabilities",
                "quant_research.verify_formula",
                "quant_research.assess_statistics",
                "quant_research.wolfram_status",
            ),
            "providers": {
                "internal_deterministic": "AVAILABLE",
                "wolfram": (
                    "AVAILABLE"
                    if self.wolfram_registration.invocation_allowed
                    else "UNAVAILABLE"
                ),
            },
        }
        return self._envelope("quant_research_capabilities", data)

    def verify_formula(self) -> EvidenceEnvelope:
        """Verify a bounded reference formula with internal and Wolfram gates."""
        formula = "sum(reference_returns) == reference_mean * n"
        reference_sum = math.fsum(_REFERENCE_RETURNS)
        reference_mean = reference_sum / len(_REFERENCE_RETURNS)
        reconstructed_sum = reference_mean * len(_REFERENCE_RETURNS)
        internal_verified = math.isclose(
            reference_sum,
            reconstructed_sum,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        data: Mapping[str, object] = {
            "formula": formula,
            "internal_verification": ("VERIFIED" if internal_verified else "FAILED"),
            "wolfram_verification": (
                "REGISTERED_NOT_EXECUTED"
                if self.wolfram_registration.invocation_allowed
                else "UNAVAILABLE"
            ),
            "wolfram_registration": self.wolfram_registration.to_public_data(),
        }
        blockers = tuple(
            dict.fromkeys(
                (
                    *self.wolfram_registration.blockers,
                    *(
                        ("WOLFRAM_VERIFICATION_NOT_EXECUTED",)
                        if self.wolfram_registration.invocation_allowed
                        else ()
                    ),
                    *(() if internal_verified else ("FORMULA_VERIFICATION_FAILED",)),
                )
            )
        )
        return self._envelope("quant_formula_verification", data, blockers=blockers)

    def assess_statistics(self) -> EvidenceEnvelope:
        """Assess a bounded reference sample for deterministic research checks."""
        count = len(_REFERENCE_RETURNS)
        mean = math.fsum(_REFERENCE_RETURNS) / count
        variance = math.fsum((value - mean) ** 2 for value in _REFERENCE_RETURNS) / (
            count - 1
        )
        data: Mapping[str, object] = {
            "sample_id": "embedded_reference_returns_v1",
            "n": count,
            "mean": mean,
            "sample_variance": variance,
            "sample_standard_deviation": math.sqrt(variance),
            "multiple_testing_control_required": True,
            "tradability_inferred": False,
        }
        return self._envelope("quant_statistics_assessment", data)

    def wolfram_status(self) -> EvidenceEnvelope:
        """Return external Wolfram MCP registration status without secret exposure."""
        data = self.wolfram_registration.to_public_data()
        return self._envelope(
            "wolfram_mcp_registration",
            data,
            blockers=self.wolfram_registration.blockers,
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
            raise ValueError("quant research MCP clock must be timezone-aware")
        return value

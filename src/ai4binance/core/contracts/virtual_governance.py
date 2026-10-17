"""Dependency-neutral contracts for governed virtual-market evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

DGE_APPROVED_PAPER_ONLY = "APPROVED_PAPER_ONLY"
DGE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
DGE_EVALUATION_FAILED = "DGE_EVALUATION_FAILED"
DGE_EVALUATION_UNAVAILABLE = "DGE_EVALUATION_UNAVAILABLE"
DGE_SIMULATION_NOT_APPROVED = "DGE_SIMULATION_NOT_APPROVED"


@dataclass(frozen=True, slots=True)
class VirtualGovernanceResult:
    """Application-facing result from one deterministic governance evaluation."""

    decision_id: str
    status: str
    blockers: tuple[str, ...]
    simulation_allowed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    evaluation_record_json: str | None = None

    @property
    def evaluation_record_sha256(self) -> str | None:
        """Bind the exact immutable evaluation body without granting authority."""
        if self.evaluation_record_json is None:
            return None
        return hashlib.sha256(self.evaluation_record_json.encode("utf-8")).hexdigest()

    def validate_evaluation_subject(
        self,
        *,
        snapshot_id: str,
        candidate_id: str,
        symbol: str,
        market: str,
        timestamp: str,
    ) -> None:
        """Reject missing or contradictory evidence before paper execution."""
        if self.evaluation_record_json is None:
            if self.simulation_allowed:
                raise ValueError("DGE_EVALUATION_EVIDENCE_MISSING")
            return
        if (
            len(
                json.dumps(self.evaluation_record_json, ensure_ascii=False).encode(
                    "utf-8"
                )
            )
            > 10_000
        ):
            raise ValueError("DGE_EVALUATION_EVIDENCE_TOO_LARGE")
        record = json.loads(self.evaluation_record_json)
        if not isinstance(record, dict) or any(
            not isinstance(record.get(key), dict)
            for key in ("candidate", "context", "decision")
        ):
            raise ValueError("DGE_EVALUATION_EVIDENCE_INVALID")
        candidate, context, decision = (
            record["candidate"],
            record["context"],
            record["decision"],
        )
        expected = {
            "candidate_id": candidate_id,
            "symbol": symbol,
            "market_type": market,
            "data_snapshot_id": snapshot_id,
            "decision_id": self.decision_id,
            "governance_status": self.status,
            "execution_surface": "VIRTUAL_MARKET",
            "timestamp_utc": timestamp,
            "execution_allowed": False,
            "live_execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        blockers = tuple(
            dict.fromkeys(
                (*decision.get("hard_blockers", ()), *decision.get("soft_blockers", ()))
            )
        )
        market_flag = (
            "simulated_spot_allowed"
            if market == "SPOT"
            else "simulated_futures_allowed"
        )
        if (
            any(decision.get(key) != value for key, value in expected.items())
            or candidate.get("candidate_id") != candidate_id
            or candidate.get("symbol") != symbol
            or candidate.get("market") != market
            or context.get("data_snapshot_id") != snapshot_id
            or context.get("execution_surface") != "VIRTUAL_MARKET"
            or context.get("evaluation_timestamp_utc") != timestamp
            or any(
                context.get(key) != decision.get(key)
                for key in ("config_hash", "rule_set_version", "semantic_graph_id")
            )
            or blockers != self.blockers
            or self.simulation_allowed
            != (
                decision.get("simulated_execution_allowed") is True
                and decision.get(market_flag) is True
            )
        ):
            raise ValueError("DGE_EVALUATION_SUBJECT_MISMATCH")

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.status.strip():
            raise ValueError("virtual governance result identity is required")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("virtual governance result blockers cannot be blank")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("virtual governance result blockers must be unique")
        if not isinstance(self.simulation_allowed, bool):
            raise ValueError("virtual governance simulation allowance must be boolean")
        if self.simulation_allowed and self.status != DGE_APPROVED_PAPER_ONLY:
            raise ValueError(
                "virtual governance simulation requires approved paper-only status"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual governance result cannot authorize live execution"
            )

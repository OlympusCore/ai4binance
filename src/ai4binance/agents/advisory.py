"""Structured advisory-agent evidence, critique and checkpoint boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from ai4binance.agents.context_budget import (
    BoundedContextAssembler,
    ContextFragment,
    TokenUsage,
)
from ai4binance.schemas import AnalysisState


class AdvisoryRole(StrEnum):
    BULL = "BULL"
    BEAR = "BEAR"
    RISK = "RISK"
    DATA_QUALITY = "DATA_QUALITY"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    source: str
    as_of: datetime
    summary: str
    content_hash: str

    @classmethod
    def create(
        cls, evidence_id: str, source: str, as_of: datetime, summary: str
    ) -> EvidenceItem:
        digest = sha256(summary.encode("utf-8")).hexdigest()
        return cls(evidence_id, source, as_of, summary, digest)

    def __post_init__(self) -> None:
        if any(
            not value.strip() for value in (self.evidence_id, self.source, self.summary)
        ):
            raise ValueError("advisory evidence identity and summary are required")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("advisory evidence timestamp must be timezone-aware")
        if self.content_hash != sha256(self.summary.encode("utf-8")).hexdigest():
            raise ValueError("advisory evidence hash is invalid")


@dataclass(frozen=True, slots=True)
class AdvisoryEvidencePacket:
    snapshot_id: str
    symbol: str
    as_of: datetime
    evidence: tuple[EvidenceItem, ...]
    deterministic_blockers: tuple[str, ...]
    packet_hash: str

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        symbol: str,
        as_of: datetime,
        evidence: tuple[EvidenceItem, ...],
        deterministic_blockers: tuple[str, ...] = (),
    ) -> AdvisoryEvidencePacket:
        ordered = tuple(sorted(evidence, key=lambda item: item.evidence_id))
        digest = cls.compute_hash(
            snapshot_id, symbol, as_of, ordered, deterministic_blockers
        )
        return cls(
            snapshot_id,
            symbol.strip().upper(),
            as_of,
            ordered,
            tuple(dict.fromkeys(deterministic_blockers)),
            digest,
        )

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.symbol.strip() or not self.evidence:
            raise ValueError("advisory packet identity and evidence are required")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("advisory packet timestamp must be timezone-aware")
        ids = tuple(item.evidence_id for item in self.evidence)
        if len(ids) != len(set(ids)) or tuple(sorted(ids)) != ids:
            raise ValueError("advisory evidence must be unique and sorted")
        if any(item.as_of > self.as_of for item in self.evidence):
            raise ValueError("advisory evidence cannot come from the future")
        expected = self.compute_hash(
            self.snapshot_id,
            self.symbol,
            self.as_of,
            self.evidence,
            self.deterministic_blockers,
        )
        if self.packet_hash != expected:
            raise ValueError("advisory packet hash is invalid")

    @staticmethod
    def compute_hash(
        snapshot_id: str,
        symbol: str,
        as_of: datetime,
        evidence: tuple[EvidenceItem, ...],
        blockers: tuple[str, ...],
    ) -> str:
        payload = json.dumps(
            {
                "as_of": as_of.isoformat(),
                "blockers": blockers,
                "evidence": tuple(
                    (item.evidence_id, item.content_hash) for item in evidence
                ),
                "snapshot_id": snapshot_id,
                "symbol": symbol.strip().upper(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalAnalysisEnvelope:
    snapshot_id: str
    symbol: str
    as_of: datetime
    evidence_packet: AdvisoryEvidencePacket
    deterministic_summary: str
    final_action: str
    decision_state: str
    blockers: tuple[str, ...]
    kept_sources: tuple[str, ...] = ()
    truncated_sources: tuple[str, ...] = ()
    dropped_sources: tuple[str, ...] = ()
    token_usage: TokenUsage | None = None
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @classmethod
    def from_analysis_state(
        cls,
        analysis: AnalysisState,
        *,
        max_agent_evidence: int = 16,
    ) -> CanonicalAnalysisEnvelope:
        if not 1 <= max_agent_evidence <= 64:
            raise ValueError("max_agent_evidence is invalid")
        decision = analysis.final_decision
        final_action = decision.action.value if decision is not None else "NO_TRADE"
        decision_state = (
            decision.decision_state.value if decision is not None else "NO_TRADE"
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *analysis.blockers,
                    *(decision.blockers if decision is not None else ()),
                )
            )
        )
        evidence_items = [
            EvidenceItem.create(
                "deterministic_decision",
                "AnalysisState.final_decision",
                analysis.timestamp,
                (
                    f"action={final_action}; decision_state={decision_state}; "
                    f"blockers={','.join(blockers) or 'NONE'}"
                ),
            )
        ]
        for name, result in sorted(analysis.agent_results.items())[:max_agent_evidence]:
            evidence_items.append(
                EvidenceItem.create(
                    f"agent:{name}",
                    "AnalysisState.agent_results",
                    result.timestamp,
                    (
                        f"{name}: status={result.status.value}; "
                        f"score={result.score:.2f}; "
                        f"confidence={result.confidence:.3f}; "
                        f"blockers={','.join(result.blockers) or 'NONE'}; "
                        f"reasons={','.join(result.reason_codes)}"
                    ),
                )
            )
        packet = AdvisoryEvidencePacket.create(
            snapshot_id=analysis.snapshot_id,
            symbol=analysis.symbol,
            as_of=analysis.timestamp,
            evidence=tuple(evidence_items),
            deterministic_blockers=blockers,
        )
        summary = (
            f"{analysis.symbol} {analysis.snapshot_id}: {final_action}/"
            f"{decision_state}; evidence_items={len(evidence_items)}; "
            f"execution_allowed=false; LIVE_ORDER_BLOCKED"
        )
        context_assembly = BoundedContextAssembler().assemble(
            system="AI4BINANCE advisory evidence summary",
            current_input=summary,
            fragments=tuple(
                ContextFragment(
                    source=item.evidence_id,
                    content=item.summary,
                    priority=(
                        100 if item.evidence_id == "deterministic_decision" else 10
                    ),
                )
                for item in evidence_items
            ),
        )
        return cls(
            snapshot_id=analysis.snapshot_id,
            symbol=analysis.symbol,
            as_of=analysis.timestamp,
            evidence_packet=packet,
            deterministic_summary=summary,
            final_action=final_action,
            decision_state=decision_state,
            blockers=blockers,
            kept_sources=context_assembly.kept_sources,
            truncated_sources=context_assembly.truncated_sources,
            dropped_sources=context_assembly.dropped_sources,
            token_usage=context_assembly.usage,
        )

    def __post_init__(self) -> None:
        if (
            self.snapshot_id != self.evidence_packet.snapshot_id
            or self.symbol.strip().upper() != self.evidence_packet.symbol
        ):
            raise ValueError("canonical analysis envelope packet mismatch")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("canonical analysis envelope timestamp must be aware")
        if not self.deterministic_summary.strip():
            raise ValueError("canonical analysis envelope summary is required")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("canonical analysis envelope cannot promote or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("canonical analysis envelope must remain live blocked")


@dataclass(frozen=True, slots=True)
class AdvisoryOpinion:
    role: AdvisoryRole
    packet_hash: str
    summary: str
    confidence: float
    cited_evidence_ids: tuple[str, ...]
    proposed_experiments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.packet_hash.strip() or not self.summary.strip():
            raise ValueError("advisory opinion identity and summary are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("advisory confidence must be bounded")
        if not self.cited_evidence_ids:
            raise ValueError("advisory opinion requires citations")


@dataclass(frozen=True, slots=True)
class AdvisorySynthesis:
    snapshot_id: str
    summaries: tuple[tuple[AdvisoryRole, str], ...]
    proposed_experiments: tuple[str, ...]
    disagreements: tuple[str, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError(
                "advisory synthesis has no promotion or execution authority"
            )


@dataclass(frozen=True, slots=True)
class AdvisoryEngine:
    """Validate opinions and expose critique without producing trade actions."""

    required_roles: tuple[AdvisoryRole, ...] = tuple(AdvisoryRole)

    def synthesize(
        self,
        packet: AdvisoryEvidencePacket,
        opinions: tuple[AdvisoryOpinion, ...],
    ) -> AdvisorySynthesis:
        evidence_ids = {item.evidence_id for item in packet.evidence}
        roles = {item.role for item in opinions}
        blockers = list(packet.deterministic_blockers)
        if len(roles) != len(opinions):
            blockers.append("ADVISORY_DUPLICATE_ROLE")
        if not set(self.required_roles).issubset(roles):
            blockers.append("ADVISORY_ROLE_MISSING")
        if any(item.packet_hash != packet.packet_hash for item in opinions):
            blockers.append("ADVISORY_PACKET_MISMATCH")
        if any(
            not set(item.cited_evidence_ids).issubset(evidence_ids) for item in opinions
        ):
            blockers.append("ADVISORY_CITATION_INVALID")
        by_role = {item.role: item for item in opinions}
        disagreements: list[str] = []
        bull = by_role.get(AdvisoryRole.BULL)
        bear = by_role.get(AdvisoryRole.BEAR)
        if (
            bull is not None
            and bear is not None
            and min(bull.confidence, bear.confidence) >= 0.5
        ):
            disagreements.append("BULL_BEAR_CONFLICT")
        experiments = tuple(
            dict.fromkeys(
                experiment
                for item in sorted(opinions, key=lambda value: value.role.value)
                for experiment in item.proposed_experiments
                if experiment.strip()
            )
        )
        summaries = tuple(
            (item.role, item.summary)
            for item in sorted(opinions, key=lambda value: value.role.value)
        )
        return AdvisorySynthesis(
            snapshot_id=packet.snapshot_id,
            summaries=summaries,
            proposed_experiments=experiments,
            disagreements=tuple(disagreements),
            blockers=tuple(dict.fromkeys(blockers)),
        )


@dataclass(frozen=True, slots=True)
class AdvisoryCheckpoint:
    request_id: str
    packet_hash: str
    completed_roles: tuple[AdvisoryRole, ...]
    attempts: int

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.packet_hash.strip():
            raise ValueError("advisory checkpoint identity is required")
        if self.attempts < 0:
            raise ValueError("advisory checkpoint attempts cannot be negative")
        if len(self.completed_roles) != len(set(self.completed_roles)):
            raise ValueError("advisory checkpoint roles must be unique")


@dataclass(slots=True)
class InMemoryAdvisoryCheckpointStore:
    retry_budget: int = 2
    _checkpoints: dict[str, AdvisoryCheckpoint] | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.retry_budget <= 10:
            raise ValueError("advisory retry budget must be between zero and ten")
        self._checkpoints = {}

    def save(self, checkpoint: AdvisoryCheckpoint) -> None:
        if checkpoint.attempts > self.retry_budget:
            raise ValueError("advisory retry budget exceeded")
        if self._checkpoints is None:
            raise RuntimeError("advisory checkpoint store is not initialized")
        previous = self._checkpoints.get(checkpoint.request_id)
        if previous is not None and previous.packet_hash != checkpoint.packet_hash:
            raise ValueError("advisory checkpoint packet mismatch")
        if previous is not None and checkpoint.attempts < previous.attempts:
            raise ValueError("advisory checkpoint attempts cannot move backwards")
        self._checkpoints[checkpoint.request_id] = checkpoint

    def load(self, request_id: str) -> AdvisoryCheckpoint | None:
        if self._checkpoints is None:
            raise RuntimeError("advisory checkpoint store is not initialized")
        return self._checkpoints.get(request_id)

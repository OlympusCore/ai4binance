"""End-to-end Evidence MCP to local approval queue workflow."""

from dataclasses import dataclass

from ai4binance.content.engine import ContentDraftEngine
from ai4binance.content.models import ContentDraft
from ai4binance.content.queue import LocalApprovalQueue
from ai4binance.mcp.evidence import EvidenceGateway


@dataclass(frozen=True, slots=True)
class DraftQueueReceipt:
    """Machine-verifiable outcome of one draft ingestion attempt."""

    draft: ContentDraft
    enqueued: bool
    publish_attempted: bool = False

    def __post_init__(self) -> None:
        if self.publish_attempted:
            raise ValueError("draft-only workflow cannot attempt publishing")


@dataclass(frozen=True, slots=True)
class EvidenceBackedDraftQueue:
    """Wire read-only evidence to deterministic drafting and local review."""

    evidence_gateway: EvidenceGateway
    draft_engine: ContentDraftEngine
    approval_queue: LocalApprovalQueue

    def ingest_market_outlook(self) -> DraftQueueReceipt:
        """Read, verify, draft and enqueue without network or publish authority."""
        evidence = self.evidence_gateway.get_market_outlook()
        draft = self.draft_engine.create_market_outlook_draft(evidence)
        enqueued = self.approval_queue.enqueue(draft)
        return DraftQueueReceipt(draft=draft, enqueued=enqueued)

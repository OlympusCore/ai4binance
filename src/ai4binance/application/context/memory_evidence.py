"""Transform governed memory records into bounded advisory evidence."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.core.contracts.memory import (
    MEMORY_CONTEXT_CONSUMER,
    MEMORY_CONTEXT_PURPOSE,
    HistoricalAdvisoryEvidence,
    MemoryRecord,
    MemoryRetrievalResult,
    MemorySnapshot,
)
from ai4binance.domain.memory_access import (
    memory_access_record_blockers,
    memory_access_request_blockers,
)


@dataclass(frozen=True, slots=True)
class MemoryEvidenceAdapter:
    """Expose historical memory as current-cycle advisory evidence only."""

    def transform(
        self,
        snapshot: MemorySnapshot,
        retrieval: MemoryRetrievalResult,
    ) -> tuple[HistoricalAdvisoryEvidence, ...]:
        request = retrieval.request
        if request.consumer != MEMORY_CONTEXT_CONSUMER:
            return ()
        if request.purpose != MEMORY_CONTEXT_PURPOSE:
            return ()
        if memory_access_request_blockers(
            request.access_policy,
            consumer=MEMORY_CONTEXT_CONSUMER,
            purpose=MEMORY_CONTEXT_PURPOSE,
            market_type=request.market_type,
            symbol=request.symbol,
            strategy_id=request.strategy_id,
        ):
            return ()
        return tuple(
            evidence
            for record in snapshot.records
            if not memory_access_record_blockers(request.access_policy, record)
            for evidence in (self._transform_record(record),)
            if evidence is not None
        )

    def _transform_record(
        self,
        record: MemoryRecord,
    ) -> HistoricalAdvisoryEvidence | None:
        return HistoricalAdvisoryEvidence(
            memory_id=record.memory_id,
            subject_key=record.subject_key,
            applicability_scope=record.applicability_scope,
            classification=record.classification,
            evidence_refs=record.evidence_refs,
            advisory_effect=record.advisory_effect,
            confidence=min(record.confidence, 0.75),
            failure_mode_code=record.failure_mode_code,
            reason_codes=record.reason_codes,
            market_type=record.market_type,
            symbol=record.symbol,
            strategy_id=record.strategy_id,
            setup_type=record.setup_type,
            regime_tags=record.regime_tags,
            timeframe_tags=record.timeframe_tags,
        )

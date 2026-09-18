"""Read-only context compiler for Governed Memory Fabric snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from time import perf_counter_ns
from typing import Any, Protocol, cast

from ai4binance.application.context.budget import (
    BoundedContextAssembler,
    ContextFragment,
    TokenBudget,
    TokenBudgetGuard,
)
from ai4binance.application.context.memory_evidence import MemoryEvidenceAdapter
from ai4binance.core.contracts.memory import (
    DEFAULT_ADVISORY_MEMORY_ACCESS_POLICY,
    MEMORY_CONTEXT_CONSUMER,
    MEMORY_CONTEXT_PURPOSE,
    MEMORY_PRODUCER_ROLE_CONTRACTS,
    CognitiveBrainRole,
    CompiledCycleContext,
    MemoryApplicabilityScope,
    MemoryAuthorityCeiling,
    MemoryClassification,
    MemoryContext,
    MemoryProducerRole,
    MemoryRecord,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemorySnapshot,
    MemoryTrustClass,
    MemoryType,
    MemoryWriteIntent,
    memory_canonical_sha256,
)
from ai4binance.domain.memory import GovernedMemoryFabric
from ai4binance.domain.memory_access import (
    memory_access_record_blockers,
    memory_access_request_blockers,
)
from ai4binance.domain.memory_metrics import (
    MemoryRuntimeMetricEvent,
    MemoryRuntimeMetricsRecorder,
    MemoryRuntimeOperation,
)


class MarketSnapshotLike(Protocol):
    @property
    def created_at(self) -> datetime: ...

    @property
    def snapshot_id(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def market_type(self) -> str: ...

    @property
    def timeframes(self) -> tuple[str, ...]: ...


class LearningLessonLike(Protocol):
    """Minimum read-only lesson shape required for governed memory staging."""

    @property
    def code(self) -> str: ...

    @property
    def rationale(self) -> str: ...


class LearningSummaryLike(Protocol):
    """Stable application contract for research-only learning summaries."""

    @property
    def summary_id(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def lessons(self) -> tuple[LearningLessonLike, ...]: ...


@dataclass(frozen=True, slots=True)
class GovernedMemoryContextCompiler:
    token_budget: TokenBudget = field(default_factory=TokenBudget)
    metrics_recorder: MemoryRuntimeMetricsRecorder | None = None
    evidence_adapter: MemoryEvidenceAdapter = field(
        default_factory=MemoryEvidenceAdapter
    )

    def compile(
        self,
        snapshot: MemorySnapshot,
        retrieval: MemoryRetrievalResult,
        *,
        system: str = "AI4BINANCE governed memory context is advisory only.",
        current_input: str = "Compile read-only memory context.",
    ) -> MemoryContext:
        started = perf_counter_ns()
        assembler = BoundedContextAssembler(TokenBudgetGuard(budget=self.token_budget))
        access_policy = retrieval.request.access_policy
        request_access_blockers = list(
            memory_access_request_blockers(
                access_policy,
                consumer=MEMORY_CONTEXT_CONSUMER,
                purpose=MEMORY_CONTEXT_PURPOSE,
                market_type=retrieval.request.market_type,
                symbol=retrieval.request.symbol,
                strategy_id=retrieval.request.strategy_id,
            )
        )
        if retrieval.request.consumer != MEMORY_CONTEXT_CONSUMER:
            request_access_blockers.append("MEMORY_ACCESS_CONSUMER_DENIED")
        if retrieval.request.purpose != MEMORY_CONTEXT_PURPOSE:
            request_access_blockers.append("MEMORY_ACCESS_PURPOSE_DENIED")
        record_access_results = tuple(
            (record, memory_access_record_blockers(access_policy, record))
            for record in snapshot.records
        )
        record_access_blockers = tuple(
            blocker
            for _, record_blockers in record_access_results
            for blocker in record_blockers
        )
        allowed_records = tuple(
            record
            for record, record_blockers in record_access_results
            if not request_access_blockers and not record_blockers
        )
        fragments = tuple(
            ContextFragment(
                source=record.memory_id,
                content=record.body,
                priority=_priority(record.authority_ceiling),
                classification=record.classification.value,
                evidence_status=record.status.value,
                authority=record.authority_ceiling.value,
                expires_at=record.valid_until,
            )
            for record in allowed_records
        )
        assembly = assembler.assemble(
            system=system,
            current_input=current_input,
            fragments=fragments,
        )
        evidence_refs = tuple(
            dict.fromkeys(
                evidence_ref
                for record in allowed_records
                for evidence_ref in record.evidence_refs
            )
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *retrieval.blockers,
                    *request_access_blockers,
                    *record_access_blockers,
                    *(
                        ("MEMORY_CONTEXT_TRUNCATED",)
                        if assembly.truncated_sources
                        else ()
                    ),
                    *(
                        ("MEMORY_CONTEXT_DROPPED_RECORDS",)
                        if assembly.dropped_sources
                        else ()
                    ),
                )
            )
        )
        context = MemoryContext(
            context_id="memory-context:"
            + memory_canonical_sha256(
                {
                    "kept_sources": assembly.kept_sources,
                    "snapshot": snapshot.memory_snapshot_id,
                    "access_policy_id": access_policy.policy_id,
                    "access_policy_version": access_policy.policy_version,
                    "consumer": MEMORY_CONTEXT_CONSUMER,
                    "purpose": MEMORY_CONTEXT_PURPOSE,
                }
            )[:24],
            memory_snapshot_id=snapshot.memory_snapshot_id,
            rendered_context=assembly.rendered_context,
            source_memory_ids=assembly.kept_sources,
            evidence_refs=evidence_refs,
            access_policy_id=access_policy.policy_id,
            access_policy_version=access_policy.policy_version,
            consumer=MEMORY_CONTEXT_CONSUMER,
            purpose=MEMORY_CONTEXT_PURPOSE,
            blockers=blockers,
            authority_ceiling=MemoryAuthorityCeiling.ADVISORY,
        )
        if self.metrics_recorder is not None:
            self.metrics_recorder.record(
                MemoryRuntimeMetricEvent(
                    operation=MemoryRuntimeOperation.CONTEXT_COMPILE,
                    latency_ms=(perf_counter_ns() - started) / 1_000_000.0,
                    compiled_context_bytes=len(
                        context.rendered_context.encode("utf-8")
                    ),
                    compiled_context_token_estimate=assembly.usage.context,
                    active_memory_count=len(snapshot.records),
                    stale_memory_count=len(retrieval.dropped_record_ids),
                    conflict_count=len(snapshot.conflicts),
                )
            )
        return context

    def compile_cycle_context(
        self,
        *,
        market_snapshot: MarketSnapshotLike,
        memory_snapshot: MemorySnapshot,
        retrieval: MemoryRetrievalResult,
        cycle_id: str,
        policy_bundle_hash: str,
        registry_revision: str,
    ) -> CompiledCycleContext:
        memory_context = self.compile(memory_snapshot, retrieval)
        return CompiledCycleContext(
            context_id="compiled-cycle-context:"
            + memory_canonical_sha256(
                {
                    "cycle_id": cycle_id,
                    "market_snapshot_id": market_snapshot.snapshot_id,
                    "memory_snapshot_id": memory_snapshot.memory_snapshot_id,
                    "policy_bundle_hash": policy_bundle_hash,
                    "registry_revision": registry_revision,
                    "memory_context_id": memory_context.context_id,
                }
            )[:24],
            cycle_id=cycle_id,
            operating_brain=CognitiveBrainRole.ONE_BRAIN_OPERATING_BRAIN,
            memory_brain=CognitiveBrainRole.GOVERNED_SECOND_BRAIN_MEMORY_BRAIN,
            market_snapshot_id=market_snapshot.snapshot_id,
            memory_snapshot_id=memory_snapshot.memory_snapshot_id,
            policy_bundle_hash=policy_bundle_hash,
            registry_revision=registry_revision,
            symbol=market_snapshot.symbol,
            market_type=market_snapshot.market_type,
            timeframes=market_snapshot.timeframes,
            memory_context=memory_context,
            memory_record_ids=memory_context.source_memory_ids,
            memory_evidence_refs=memory_context.evidence_refs,
            warnings=(),
            blockers=memory_context.blockers,
            truncation_status=(
                "TRUNCATED_OR_DROPPED" if memory_context.blockers else "COMPLETE"
            ),
            validated_context_flow="SECOND_BRAIN_TO_ONE_BRAIN",
            created_at=memory_snapshot.created_at,
            memory_advisory_evidence=self.evidence_adapter.transform(
                memory_snapshot,
                retrieval,
            ),
        )


class MemoryRecordStore(Protocol):
    def load_recent(
        self, *, as_of_system_time: datetime | None = None
    ) -> tuple[MemoryRecord, ...]: ...

    def append(self, record: MemoryRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class GovernedMemoryCycleBridge:
    """Connect candidate intake and validated retrieval without self-approval."""

    store: MemoryRecordStore
    fabric: GovernedMemoryFabric = field(default_factory=GovernedMemoryFabric)
    compiler: GovernedMemoryContextCompiler = field(
        default_factory=GovernedMemoryContextCompiler
    )

    def compile(self, snapshot: MarketSnapshotLike) -> CompiledCycleContext:
        records = self.store.load_recent(as_of_system_time=snapshot.created_at)
        request = MemoryRetrievalRequest(
            subject_keys=tuple(sorted({record.subject_key for record in records})),
            as_of=snapshot.created_at,
            as_of_system_time=snapshot.created_at,
            cycle_id=f"research:{snapshot.snapshot_id}",
            market_type=snapshot.market_type,
            symbol=snapshot.symbol,
        )
        retrieval = self.fabric.retrieve(records, request)
        memory_snapshot = self.fabric.build_snapshot(
            retrieval, created_at=snapshot.created_at
        )
        return self.compiler.compile_cycle_context(
            market_snapshot=snapshot,
            memory_snapshot=memory_snapshot,
            retrieval=retrieval,
            cycle_id=f"research:{snapshot.snapshot_id}",
            policy_bundle_hash=memory_canonical_sha256(
                {
                    "access_policy": asdict(DEFAULT_ADVISORY_MEMORY_ACCESS_POLICY),
                    "retrieval_policy": request.policy.value,
                    "memory_policy_version": memory_snapshot.policy_version,
                }
            ),
            registry_revision=memory_canonical_sha256(
                [asdict(role) for role in MEMORY_PRODUCER_ROLE_CONTRACTS]
            ),
        )

    def stage(
        self, summary: LearningSummaryLike, snapshot: MarketSnapshotLike
    ) -> tuple[str, ...]:
        """Persist deterministic learning proposals; none becomes trusted memory."""
        existing = self.store.load_recent()
        ids: list[str] = []
        for lesson in summary.lessons:
            intent = MemoryWriteIntent(
                intent_id=f"{summary.summary_id}:{snapshot.market_type}:{snapshot.symbol}:{lesson.code}",
                memory_type=MemoryType.SEMANTIC_MEMORY,
                subject_key=f"learning:{lesson.code}",
                body=lesson.rationale,
                event_time=summary.created_at,
                observed_at=summary.created_at,
                source_refs=(summary.summary_id,),
                evidence_refs=(f"learning-summary:{summary.summary_id}",),
                source_hashes=(memory_canonical_sha256(asdict(cast(Any, lesson))),),
                producer_role=MemoryProducerRole.OBSERVER,
                trust_class=MemoryTrustClass.VERIFIED_SYSTEM_EVIDENCE,
                authority_ceiling=MemoryAuthorityCeiling.ADVISORY,
                applicability_scope=MemoryApplicabilityScope.SYMBOL,
                classification=MemoryClassification.SYSTEM_OPERATIONAL,
                market_type=snapshot.market_type,
                symbol=snapshot.symbol,
                valid_until=summary.created_at + timedelta(days=30),
                cycle_id=f"research:{snapshot.snapshot_id}",
                snapshot_id=snapshot.snapshot_id,
                reason_codes=(lesson.code,),
            )
            candidate = self.fabric.compile_candidate(
                intent,
                tuple(
                    record
                    for record in existing
                    if record.memory_id != f"mem:{intent.intent_id}"
                ),
            )
            previous = next(
                (
                    record
                    for record in existing
                    if record.memory_id == candidate.record.memory_id
                ),
                None,
            )
            if previous is not None:
                if previous.content_hash != candidate.record.content_hash:
                    raise ValueError("learning memory candidate content changed")
            else:
                self.store.append(candidate.record)
            ids.append(candidate.record.memory_id)
        return tuple(ids)


def _priority(authority: MemoryAuthorityCeiling) -> int:
    if authority is MemoryAuthorityCeiling.READ_ONLY_REFERENCE:
        return 30
    if authority is MemoryAuthorityCeiling.EVIDENCE_ONLY:
        return 20
    if authority is MemoryAuthorityCeiling.ADVISORY:
        return 10
    return 0

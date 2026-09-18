"""Deterministic domain services for governed cross-cycle memory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import perf_counter_ns
from typing import Protocol

from ai4binance.core.contracts.memory import (
    MemoryAdvisoryEffect,
    MemoryAuthorityCeiling,
    MemoryCandidate,
    MemoryConflict,
    MemoryConflictType,
    MemoryGuardianVetoSurface,
    MemoryLifecycleStatus,
    MemoryProducerRole,
    MemoryPromotionVerificationResult,
    MemoryRecord,
    MemoryRetrievalPolicy,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemorySnapshot,
    MemoryTrustClass,
    MemoryType,
    MemoryWriteIntent,
    memory_canonical_sha256,
    memory_snapshot_lineage_sha256,
)
from ai4binance.domain.memory_access import (
    memory_access_record_blockers,
    memory_access_request_blockers,
)
from ai4binance.domain.memory_metrics import (
    MemoryRuntimeMetricEvent,
    MemoryRuntimeMetricsRecorder,
    MemoryRuntimeOperation,
)


class _DecisionStateLike(Protocol):
    @property
    def value(self) -> str: ...


class _FinalDecisionLike(Protocol):
    @property
    def decision_state(self) -> _DecisionStateLike: ...

    @property
    def reason_codes(self) -> tuple[str, ...]: ...

    @property
    def trade_id(self) -> str: ...


class _CompiledCycleContextLike(Protocol):
    @property
    def context_id(self) -> str: ...

    @property
    def cycle_id(self) -> str: ...

    @property
    def memory_snapshot_id(self) -> str: ...


class AnalysisStateLike(Protocol):
    @property
    def final_decision(self) -> _FinalDecisionLike | None: ...

    @property
    def compiled_cycle_context(self) -> _CompiledCycleContextLike | None: ...

    @property
    def blockers(self) -> tuple[str, ...]: ...

    @property
    def warnings(self) -> tuple[str, ...]: ...

    @property
    def snapshot_id(self) -> str: ...

    @property
    def agent_results(self) -> Mapping[str, object]: ...

    @property
    def symbol(self) -> str: ...

    @property
    def timestamp(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class GovernedMemoryFabric:
    """Fail-closed intake, promotion, retrieval, and snapshot assembly."""

    metrics_recorder: MemoryRuntimeMetricsRecorder | None = None

    def compile_candidate(
        self,
        intent: MemoryWriteIntent,
        existing_records: tuple[MemoryRecord, ...] = (),
    ) -> MemoryCandidate:
        blockers = list(_intent_blockers(intent))
        conflicts = detect_memory_conflicts(intent, existing_records)
        if conflicts:
            blockers.append("MEMORY_CONFLICT_REVIEW_REQUIRED")
        status = (
            MemoryLifecycleStatus.CONFLICT_CHECKED
            if not blockers
            else MemoryLifecycleStatus.CANDIDATE
        )
        candidate = MemoryCandidate(
            record=MemoryRecord(
                memory_id=f"mem:{intent.intent_id}",
                memory_type=intent.memory_type,
                subject_key=intent.subject_key,
                body=intent.body,
                event_time=intent.event_time.astimezone(UTC),
                observed_at=intent.observed_at.astimezone(UTC),
                valid_from=(intent.valid_from or intent.event_time).astimezone(UTC),
                valid_until=(
                    intent.valid_until.astimezone(UTC)
                    if intent.valid_until is not None
                    else None
                ),
                source_refs=intent.source_refs,
                evidence_refs=intent.evidence_refs,
                source_hashes=intent.source_hashes,
                content_hash=intent.content_hash,
                producer_role=intent.producer_role,
                trust_class=intent.trust_class,
                authority_ceiling=intent.authority_ceiling,
                status=MemoryLifecycleStatus.CANDIDATE,
                recorded_at=intent.observed_at.astimezone(UTC),
                applicability_scope=intent.applicability_scope,
                classification=intent.classification,
                market_type=intent.market_type,
                symbol=intent.symbol,
                strategy_id=intent.strategy_id,
                setup_type=intent.setup_type,
                regime_tags=intent.regime_tags,
                timeframe_tags=intent.timeframe_tags,
                supersedes=intent.supersedes,
                contradicts=intent.contradicts,
                retention_policy=intent.retention_policy,
                retrieval_policy=intent.retrieval_policy,
                advisory_effect=intent.advisory_effect,
                failure_mode_code=intent.failure_mode_code,
                reason_codes=intent.reason_codes,
                confidence=intent.confidence,
                cycle_id=intent.cycle_id,
                snapshot_id=intent.snapshot_id,
                decision_id=intent.decision_id,
                blockers=tuple(dict.fromkeys(blockers)),
            ),
            intake_status=status,
            blockers=tuple(dict.fromkeys(blockers)),
        )
        self._record_metrics(
            MemoryRuntimeMetricEvent(
                operation=MemoryRuntimeOperation.CANDIDATE_INTAKE,
                candidate_memory_count=1,
                conflict_count=len(conflicts),
                promotion_rejection_count=int(bool(candidate.blockers)),
            )
        )
        return candidate

    def validate_candidate(
        self,
        candidate: MemoryCandidate,
        *,
        promotion_verification: MemoryPromotionVerificationResult,
        at: datetime | None = None,
        policy_version: str | None = None,
    ) -> MemoryRecord:
        if candidate.blockers:
            raise ValueError("blocked memory candidate cannot become active")
        if not promotion_verification.verified:
            raise ValueError("memory promotion requires verified approval")
        record = candidate.record
        if (
            promotion_verification.candidate_memory_id != record.memory_id
            or promotion_verification.candidate_binding_hash != candidate.binding_sha256
            or promotion_verification.candidate_content_hash != record.content_hash
            or promotion_verification.policy_version is None
            or promotion_verification.checked_at is None
        ):
            raise ValueError("memory promotion requires candidate-bound verification")
        if (
            policy_version is not None
            and promotion_verification.policy_version != policy_version
        ):
            raise ValueError("memory promotion policy version mismatch")
        if at is None and promotion_verification.expires_at is not None:
            raise ValueError(
                "expiring memory approval requires explicit activation time"
            )
        activation_at = at or promotion_verification.checked_at
        if activation_at.tzinfo is None or activation_at.utcoffset() is None:
            raise ValueError("memory activation time must be timezone-aware")
        if activation_at < promotion_verification.checked_at:
            raise ValueError("memory activation cannot precede verification")
        if (
            promotion_verification.expires_at is not None
            and activation_at >= promotion_verification.expires_at
        ):
            raise ValueError("memory promotion approval expired")
        if record.trust_class is MemoryTrustClass.LLM_NARRATIVE:
            raise ValueError("LLM narrative cannot become active memory")
        return replace(
            record,
            status=MemoryLifecycleStatus.ACTIVE,
            recorded_at=activation_at,
            approval_record_id=promotion_verification.approval_record_id,
            verification_record_id=promotion_verification.verification_record_id,
            blockers=(),
        )

    def retrieve(
        self,
        records: tuple[MemoryRecord, ...],
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        started = perf_counter_ns()
        selected: list[MemoryRecord] = []
        dropped: list[str] = []
        request_access_blockers = memory_access_request_blockers(
            request.access_policy,
            consumer=request.consumer,
            purpose=request.purpose,
            market_type=request.market_type,
            symbol=request.symbol,
            strategy_id=request.strategy_id,
        )
        blockers: list[str] = list(request_access_blockers)
        for record in sorted(records, key=_record_sort_key):
            if request_access_blockers:
                dropped.append(record.memory_id)
                continue
            if record.subject_key not in request.subject_keys:
                dropped.append(record.memory_id)
                continue
            if request.memory_types and record.memory_type not in request.memory_types:
                dropped.append(record.memory_id)
                continue
            if (
                request.market_type is not None
                and record.market_type != request.market_type
            ):
                dropped.append(record.memory_id)
                continue
            if request.symbol is not None and record.symbol != request.symbol:
                dropped.append(record.memory_id)
                continue
            if (
                request.strategy_id is not None
                and record.strategy_id != request.strategy_id
            ):
                dropped.append(record.memory_id)
                continue
            if (
                request.setup_type is not None
                and record.setup_type != request.setup_type
            ):
                dropped.append(record.memory_id)
                continue
            if request.regime_tags and not set(request.regime_tags).issubset(
                record.regime_tags
            ):
                dropped.append(record.memory_id)
                continue
            if request.timeframe_tags and not set(request.timeframe_tags).issubset(
                record.timeframe_tags
            ):
                dropped.append(record.memory_id)
                continue
            record_access_blockers = memory_access_record_blockers(
                request.access_policy,
                record,
            )
            if record_access_blockers:
                dropped.append(record.memory_id)
                blockers.extend(record_access_blockers)
                continue
            if not _policy_allows(
                record,
                request.policy,
                request.effective_as_of_system_time,
            ):
                dropped.append(record.memory_id)
                continue
            if (
                record.observed_at > request.effective_as_of_system_time
                or record.effective_recorded_at > request.effective_as_of_system_time
            ):
                dropped.append(record.memory_id)
                blockers.append("MEMORY_FUTURE_LEAKAGE")
                continue
            if request.cycle_id is not None and record.cycle_id == request.cycle_id:
                dropped.append(record.memory_id)
                blockers.append("MEMORY_TEMPORAL_INCONSISTENCY")
                continue
            if not record.is_temporally_valid(
                request.as_of_valid_time,
                request.effective_as_of_system_time,
            ):
                dropped.append(record.memory_id)
                blockers.append("MEMORY_TEMPORAL_INCONSISTENCY")
                continue
            selected.append(record)
        ranked_records = sorted(selected, key=_record_sort_key)
        selected = ranked_records[: request.max_records]
        dropped.extend(
            record.memory_id for record in ranked_records[request.max_records :]
        )
        result = MemoryRetrievalResult(
            request=request,
            records=tuple(selected),
            dropped_record_ids=tuple(dict.fromkeys(dropped)),
            blockers=tuple(dict.fromkeys(blockers)),
        )
        active_count, candidate_count, stale_count = _memory_status_counts(records)
        self._record_metrics(
            MemoryRuntimeMetricEvent(
                operation=MemoryRuntimeOperation.RETRIEVAL,
                latency_ms=_elapsed_ms(started),
                active_memory_count=active_count,
                candidate_memory_count=candidate_count,
                stale_memory_count=stale_count,
            )
        )
        return result

    def build_snapshot(
        self,
        result: MemoryRetrievalResult,
        *,
        created_at: datetime | None = None,
        conflicts: tuple[MemoryConflict, ...] = (),
    ) -> MemorySnapshot:
        timestamp = created_at or datetime.now(UTC)
        snapshot_id = (
            "memory-snapshot:"
            + memory_canonical_sha256(
                {
                    "lineage_hash": memory_snapshot_lineage_sha256(
                        as_of_valid_time=result.request.as_of_valid_time,
                        as_of_system_time=result.request.effective_as_of_system_time,
                        policy_version="governed-memory-fabric:v1",
                        records=result.records,
                        conflicts=conflicts,
                    ),
                }
            )[:24]
        )
        return MemorySnapshot(
            memory_snapshot_id=snapshot_id,
            created_at=timestamp,
            as_of=result.request.as_of,
            records=result.records,
            conflicts=conflicts,
            as_of_system_time=result.request.effective_as_of_system_time,
        )

    def _record_metrics(self, event: MemoryRuntimeMetricEvent) -> None:
        if self.metrics_recorder is not None:
            self.metrics_recorder.record(event)


def detect_memory_conflicts(
    intent: MemoryWriteIntent,
    records: tuple[MemoryRecord, ...],
) -> tuple[MemoryConflict, ...]:
    conflicts: list[MemoryConflict] = []
    for record in records:
        if record.subject_key != intent.subject_key:
            continue
        if record.content_hash == intent.content_hash:
            conflicts.append(
                _conflict(
                    MemoryConflictType.DUPLICATE,
                    intent,
                    record,
                    "MEMORY_DUPLICATE_CONTENT",
                )
            )
        if (
            record.memory_id in intent.contradicts
            or intent.intent_id in record.contradicts
        ):
            conflicts.append(
                _conflict(
                    MemoryConflictType.CONTRADICTION,
                    intent,
                    record,
                    "MEMORY_CONTRADICTION_DECLARED",
                )
            )
        if record.memory_id in intent.supersedes:
            conflicts.append(
                _conflict(
                    MemoryConflictType.SUPERSESSION,
                    intent,
                    record,
                    "MEMORY_SUPERSESSION_DECLARED",
                )
            )
    return tuple(conflicts)


def compile_observer_memory_intent(
    *,
    intent_id: str,
    subject_key: str,
    body: str,
    event_time: datetime,
    observed_at: datetime,
    source_refs: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    source_hashes: tuple[str, ...],
    cycle_id: str | None = None,
    snapshot_id: str | None = None,
    decision_id: str | None = None,
) -> MemoryWriteIntent:
    from ai4binance.core.contracts.memory import (
        MemoryProducerRole,
        MemoryType,
    )

    return MemoryWriteIntent(
        intent_id=intent_id,
        memory_type=MemoryType.EPISODIC_MEMORY,
        subject_key=subject_key,
        body=body,
        event_time=event_time,
        observed_at=observed_at,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        source_hashes=source_hashes,
        producer_role=MemoryProducerRole.OBSERVER,
        trust_class=MemoryTrustClass.VERIFIED_SYSTEM_EVIDENCE,
        authority_ceiling=MemoryAuthorityCeiling.EVIDENCE_ONLY,
        cycle_id=cycle_id,
        snapshot_id=snapshot_id,
        decision_id=decision_id,
        confidence=0.0,
    )


def compile_analysis_observer_memory_candidate(
    state: AnalysisStateLike,
    *,
    source_refs: tuple[str, ...],
    source_hashes: tuple[str, ...],
    observed_at: datetime | None = None,
    fabric: GovernedMemoryFabric | None = None,
) -> MemoryCandidate:
    final_decision = state.final_decision
    compiled_context = state.compiled_cycle_context
    decision_state = (
        final_decision.decision_state.value
        if final_decision is not None
        else "NO_DECISION"
    )
    reason_codes = (
        final_decision.reason_codes if final_decision is not None else state.blockers
    )
    memory_snapshot_id = (
        compiled_context.memory_snapshot_id if compiled_context is not None else "NONE"
    )
    evidence_refs = tuple(
        dict.fromkeys(
            (
                f"market_snapshot:{state.snapshot_id}",
                *(
                    (f"compiled_cycle_context:{compiled_context.context_id}",)
                    if compiled_context is not None
                    else ()
                ),
                *(
                    (f"memory_snapshot:{compiled_context.memory_snapshot_id}",)
                    if compiled_context is not None
                    else ()
                ),
                *(
                    (f"final_decision:{final_decision.trade_id}",)
                    if final_decision is not None
                    else ()
                ),
                *(f"agent_result:{name}" for name in sorted(state.agent_results)),
            )
        )
    )
    body = "\n".join(
        (
            f"symbol={state.symbol}",
            f"market_snapshot_id={state.snapshot_id}",
            f"memory_snapshot_id={memory_snapshot_id}",
            f"decision_state={decision_state}",
            f"blockers={','.join(state.blockers) if state.blockers else 'NONE'}",
            f"warnings={','.join(state.warnings) if state.warnings else 'NONE'}",
            f"reason_codes={','.join(reason_codes) if reason_codes else 'NONE'}",
        )
    )
    intent_id = (
        "observer:"
        + memory_canonical_sha256(
            {
                "decision_state": decision_state,
                "market_snapshot_id": state.snapshot_id,
                "memory_snapshot_id": memory_snapshot_id,
                "reason_codes": reason_codes,
            }
        )[:24]
    )
    intent = MemoryWriteIntent(
        intent_id=intent_id,
        memory_type=MemoryType.EPISODIC_MEMORY,
        subject_key=f"cycle:{state.snapshot_id}",
        body=body,
        event_time=state.timestamp,
        observed_at=observed_at or state.timestamp,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        source_hashes=source_hashes,
        producer_role=MemoryProducerRole.FEEDBACK_COMPILER,
        trust_class=MemoryTrustClass.VERIFIED_SYSTEM_EVIDENCE,
        authority_ceiling=MemoryAuthorityCeiling.EVIDENCE_ONLY,
        advisory_effect=(
            MemoryAdvisoryEffect.NO_TRADE_HINT
            if decision_state == "NO_TRADE"
            else MemoryAdvisoryEffect.WARN
        ),
        reason_codes=reason_codes,
        cycle_id=compiled_context.cycle_id if compiled_context else state.snapshot_id,
        snapshot_id=state.snapshot_id,
        decision_id=final_decision.trade_id if final_decision is not None else None,
        confidence=0.0,
    )
    return (fabric or GovernedMemoryFabric()).compile_candidate(intent)


def compile_memory_guardian_veto_surface(
    *,
    cycle_id: str,
    snapshot: MemorySnapshot,
    retrieval: MemoryRetrievalResult,
) -> MemoryGuardianVetoSurface:
    """Expose memory blockers as a governance control-plane veto surface."""
    blockers = list(retrieval.blockers)
    conflict_ids = tuple(conflict.conflict_id for conflict in snapshot.conflicts)
    if conflict_ids:
        blockers.append("GOVERNANCE_CONFLICT")
        blockers.append("MEMORY_CONFLICT_REVIEW_REQUIRED")
    if blockers:
        blockers.append("MEMORY_GUARDIAN_VETO")
    unique_blockers = tuple(dict.fromkeys(blockers))
    return MemoryGuardianVetoSurface(
        surface_id="memory-guardian-surface:"
        + memory_canonical_sha256(
            {
                "blockers": unique_blockers,
                "conflict_ids": conflict_ids,
                "cycle_id": cycle_id,
                "dropped_memory_ids": retrieval.dropped_record_ids,
                "memory_snapshot_id": snapshot.memory_snapshot_id,
            }
        )[:24],
        cycle_id=cycle_id,
        memory_snapshot_id=snapshot.memory_snapshot_id,
        blockers=unique_blockers,
        conflict_ids=conflict_ids,
        dropped_memory_ids=retrieval.dropped_record_ids,
        review_required=bool(unique_blockers),
        status="RUNNING_WITH_BLOCKERS" if unique_blockers else "READY",
    )


def _intent_blockers(intent: MemoryWriteIntent) -> tuple[str, ...]:
    blockers: list[str] = []
    if not intent.source_refs:
        blockers.append("MEMORY_SOURCE_REQUIRED")
    if not intent.evidence_refs:
        blockers.append("MEMORY_EVIDENCE_REQUIRED")
    if not intent.source_hashes:
        blockers.append("MEMORY_SOURCE_HASH_REQUIRED")
    if intent.trust_class is MemoryTrustClass.LLM_NARRATIVE:
        blockers.append("LLM_NARRATIVE_REQUIRES_INDEPENDENT_VERIFICATION")
    if intent.trust_class is MemoryTrustClass.UNTRUSTED_EXTERNAL:
        blockers.append("UNTRUSTED_EXTERNAL_REQUIRES_REVIEW")
    if intent.authority_ceiling not in {
        MemoryAuthorityCeiling.READ_ONLY_REFERENCE,
        MemoryAuthorityCeiling.EVIDENCE_ONLY,
        MemoryAuthorityCeiling.ADVISORY,
        MemoryAuthorityCeiling.RESEARCH_ONLY,
    }:
        blockers.append("MEMORY_AUTHORITY_CEILING_INVALID")
    return tuple(dict.fromkeys(blockers))


def _policy_allows(
    record: MemoryRecord,
    policy: MemoryRetrievalPolicy,
    as_of_system_time: datetime,
) -> bool:
    if policy is MemoryRetrievalPolicy.ACTIVE_ONLY:
        return record.is_context_eligible_at(as_of_system_time)
    if policy is MemoryRetrievalPolicy.VALIDATED_ONLY:
        return record.is_context_eligible_at(as_of_system_time)
    return record.status is MemoryLifecycleStatus.CANDIDATE


def _record_sort_key(record: MemoryRecord) -> tuple[float, float, str]:
    """Rank validated advisory evidence deterministically by quality then recency."""
    return (-record.confidence, -record.observed_at.timestamp(), record.memory_id)


def _memory_status_counts(records: tuple[MemoryRecord, ...]) -> tuple[int, int, int]:
    active_count = sum(
        record.status in {MemoryLifecycleStatus.VALIDATED, MemoryLifecycleStatus.ACTIVE}
        for record in records
    )
    candidate_count = sum(
        record.status is MemoryLifecycleStatus.CANDIDATE for record in records
    )
    stale_count = sum(
        record.status
        in {
            MemoryLifecycleStatus.STALE,
            MemoryLifecycleStatus.SUPERSEDED,
            MemoryLifecycleStatus.EXPIRED,
            MemoryLifecycleStatus.REVOKED,
            MemoryLifecycleStatus.QUARANTINED,
            MemoryLifecycleStatus.REJECTED,
            MemoryLifecycleStatus.CONFLICTED,
        }
        for record in records
    )
    return active_count, candidate_count, stale_count


def _elapsed_ms(started: int) -> float:
    return (perf_counter_ns() - started) / 1_000_000.0


def _conflict(
    conflict_type: MemoryConflictType,
    intent: MemoryWriteIntent,
    record: MemoryRecord,
    reason_code: str,
) -> MemoryConflict:
    return MemoryConflict(
        conflict_id="memory-conflict:"
        + memory_canonical_sha256(
            {
                "conflict_type": conflict_type.value,
                "intent_id": intent.intent_id,
                "memory_id": record.memory_id,
            }
        )[:24],
        conflict_type=conflict_type,
        subject_key=intent.subject_key,
        memory_ids=(record.memory_id, f"mem:{intent.intent_id}"),
        reason_codes=(reason_code,),
    )

"""Fail-closed runtime/provider continuity assessment across stream and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from ai4binance.portfolio.bucket_state import PortfolioBucketPersistenceEvidence

if TYPE_CHECKING:
    from ai4binance.exchange.public_stream import KlineIngestResult
    from ai4binance.exchange.readiness import ConnectorReadinessAssessment
    from ai4binance.execution.recovery import PaperOrderRecoveryReport
    from ai4binance.portfolio.reconciliation import ReconciliationReport


@dataclass(frozen=True, slots=True)
class ProviderFreshnessContract:
    """Bounded provider freshness and latency evidence without live authority."""

    provider_id: str
    observed_at: datetime
    source_published_at: datetime
    maximum_age: timedelta
    measured_latency_ms: float | None = None
    maximum_latency_ms: float | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider freshness identity is required")
        for value in (self.observed_at, self.source_published_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("provider freshness timestamps must be timezone-aware")
        if self.maximum_age <= timedelta(0):
            raise ValueError("provider freshness maximum_age must be positive")
        if self.source_published_at > self.observed_at:
            raise ValueError("provider freshness chronology is invalid")
        if self.measured_latency_ms is not None and self.measured_latency_ms < 0.0:
            raise ValueError("provider freshness measured latency cannot be negative")
        if self.maximum_latency_ms is not None and self.maximum_latency_ms <= 0.0:
            raise ValueError("provider freshness maximum latency must be positive")
        if (self.measured_latency_ms is None) != (self.maximum_latency_ms is None):
            raise ValueError(
                "provider freshness latency evidence must bind measurement and budget"
            )
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("provider freshness cannot authorize execution")

    @property
    def age(self) -> timedelta:
        return self.observed_at - self.source_published_at

    @property
    def age_ok(self) -> bool:
        return self.age <= self.maximum_age

    @property
    def latency_ok(self) -> bool:
        if self.measured_latency_ms is None or self.maximum_latency_ms is None:
            return True
        return self.measured_latency_ms <= self.maximum_latency_ms

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.age_ok:
            blockers.append("PROVIDER_DATA_STALE")
        if not self.latency_ok:
            blockers.append("PROVIDER_LATENCY_BUDGET_EXCEEDED")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class ProviderFixtureEvaluation:
    """Bounded provider-backed fixture verdict for adapter continuity."""

    fixture_id: str
    provider_id: str
    observed_at: datetime
    passed: bool
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.fixture_id.strip() or not self.provider_id.strip():
            raise ValueError("provider fixture identity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("provider fixture timestamp must be timezone-aware")
        if self.passed and self.blockers:
            raise ValueError("passing provider fixture cannot contain blockers")
        if not self.passed and not self.blockers:
            raise ValueError("failed provider fixture must declare blockers")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("provider fixture evaluation cannot authorize execution")


@dataclass(frozen=True, slots=True)
class RuntimeProviderContinuityInput:
    """Canonical continuity inputs for runtime/provider/adaptor fail-closed review."""

    readiness: ConnectorReadinessAssessment
    freshness: ProviderFreshnessContract
    latest_ingest: KlineIngestResult | None = None
    paper_recovery: PaperOrderRecoveryReport | None = None
    open_order_reconciliation: ReconciliationReport | None = None
    portfolio_bucket_persistence: PortfolioBucketPersistenceEvidence | None = None
    portfolio_bucket_persisted: bool = False
    provider_fixture: ProviderFixtureEvaluation | None = None


@dataclass(frozen=True, slots=True)
class RuntimeProviderContinuityAssessment:
    """Aggregated continuity verdict that never enables live execution."""

    continuity_ready: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.continuity_ready == bool(self.blockers):
            raise ValueError("provider continuity readiness and blockers disagree")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("provider continuity cannot authorize execution")


def assess_runtime_provider_continuity(
    evidence: RuntimeProviderContinuityInput,
) -> RuntimeProviderContinuityAssessment:
    """Combine provider freshness, stream continuity, and recovery evidence."""
    blockers: list[str] = [*evidence.readiness.blockers, *evidence.freshness.blockers]
    if evidence.latest_ingest is None:
        blockers.append("PUBLIC_STREAM_EVIDENCE_NOT_AVAILABLE")
    else:
        blockers.extend(evidence.latest_ingest.blockers)
        if not evidence.latest_ingest.transition.accepted:
            blockers.extend(evidence.latest_ingest.transition.blockers)
    if evidence.paper_recovery is None:
        blockers.append("PAPER_RESTART_RECOVERY_NOT_EVALUATED")
    else:
        blockers.extend(evidence.paper_recovery.blockers)
        if (
            not evidence.paper_recovery.recovery_complete
            and not evidence.paper_recovery.blockers
        ):
            blockers.append("PAPER_RESTART_RECOVERY_INCOMPLETE")
    if evidence.open_order_reconciliation is None:
        blockers.append("OPEN_ORDER_RECONCILIATION_NOT_EVALUATED")
    else:
        blockers.extend(evidence.open_order_reconciliation.blockers)
    if evidence.portfolio_bucket_persistence is None:
        if not evidence.portfolio_bucket_persisted:
            blockers.append("PORTFOLIO_BUCKET_STATE_NOT_PERSISTED")
    else:
        blockers.extend(evidence.portfolio_bucket_persistence.blockers)
        if not evidence.portfolio_bucket_persistence.persisted:
            blockers.append("PORTFOLIO_BUCKET_STATE_NOT_PERSISTED")
    if evidence.provider_fixture is None:
        blockers.append("PROVIDER_FIXTURE_EVALUATION_MISSING")
    else:
        blockers.extend(evidence.provider_fixture.blockers)
    unique_blockers = tuple(dict.fromkeys(blockers))
    return RuntimeProviderContinuityAssessment(
        continuity_ready=not unique_blockers,
        blockers=unique_blockers,
    )

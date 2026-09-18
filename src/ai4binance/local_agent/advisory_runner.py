"""Manually admitted runner for bounded local advisory fixture batches."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ai4binance.agents.evaluation import AdvisoryFixture
from ai4binance.local_agent.advisory_fixture import LoopbackAdvisoryFixtureProvider
from ai4binance.local_agent.advisory_harness import (
    LocalAdvisoryFixtureHarness,
    LocalAdvisoryFixtureHarnessReport,
)
from ai4binance.ops.jobs import (
    JobAuthorityCeiling,
    JobRequest,
    RunnerAdmissionReport,
    RunnerAdmissionStatus,
    RunnerManifest,
    assess_runner_admission,
)

_RUNNER_ID = "runner:local-advisory-fixture-evaluation"
_JOB_ID = "local-advisory-fixture-evaluation"


@dataclass(frozen=True, slots=True)
class LocalAdvisoryFixtureRunnerResult:
    """Admission and batch outcome without promotion or execution authority."""

    admission: RunnerAdmissionReport
    harness_report: LocalAdvisoryFixtureHarnessReport | None
    status: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_evidence: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        admitted = self.admission.status is RunnerAdmissionStatus.ADMITTED_RESEARCH_ONLY
        if self.status not in {"PASS", "BLOCKED"}:
            raise ValueError("local advisory fixture runner result status is invalid")
        if admitted != (self.harness_report is not None):
            raise ValueError(
                "local advisory fixture runner result admission is invalid"
            )
        expected_blockers = (
            self.harness_report.blockers
            if self.harness_report is not None
            else self.admission.blockers
        )
        expected_status = (
            self.harness_report.status if self.harness_report is not None else "BLOCKED"
        )
        if self.blockers != expected_blockers or self.status != expected_status:
            raise ValueError("local advisory fixture runner result outcome is invalid")
        if (
            self.execution_allowed
            or self.promotion_evidence
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("local advisory fixture runner cannot promote or execute")


class LocalAdvisoryFixtureEvidenceWriter(Protocol):
    """Persist a redacted result without granting any execution authority."""

    def save(
        self,
        result: LocalAdvisoryFixtureRunnerResult,
        *,
        recorded_at: datetime,
    ) -> None:
        """Persist a completed or admission-blocked fixture result."""


@dataclass(frozen=True, slots=True)
class LocalAdvisoryFixtureRunner:
    """Bind the approved local runner manifest to an injected loopback provider."""

    manifest: RunnerManifest
    harness: LocalAdvisoryFixtureHarness = field(
        default_factory=LocalAdvisoryFixtureHarness
    )
    evidence_writer: LocalAdvisoryFixtureEvidenceWriter | None = None

    def __post_init__(self) -> None:
        if (
            self.manifest.runner_id != _RUNNER_ID
            or self.manifest.job_manifest.job_id != _JOB_ID
            or self.manifest.capability_manifest.authority_ceiling
            is not JobAuthorityCeiling.RESEARCH_ONLY
        ):
            raise ValueError("local advisory fixture runner manifest is invalid")

    def run(
        self,
        request: JobRequest,
        fixtures: tuple[AdvisoryFixture, ...],
        provider: LoopbackAdvisoryFixtureProvider,
        *,
        observed_at: datetime,
    ) -> LocalAdvisoryFixtureRunnerResult:
        """Run only an admitted fixture batch through the injected loopback provider."""
        admission = assess_runner_admission(
            self.manifest,
            request,
            observed_at=observed_at,
        )
        if admission.status is not RunnerAdmissionStatus.ADMITTED_RESEARCH_ONLY:
            return self._persist_if_configured(
                LocalAdvisoryFixtureRunnerResult(
                    admission=admission,
                    harness_report=None,
                    status="BLOCKED",
                    blockers=admission.blockers,
                ),
                recorded_at=observed_at,
            )
        harness_report = self.harness.run(
            fixtures,
            provider,
            started_at=observed_at,
        )
        return self._persist_if_configured(
            LocalAdvisoryFixtureRunnerResult(
                admission=admission,
                harness_report=harness_report,
                status=harness_report.status,
                blockers=harness_report.blockers,
            ),
            recorded_at=observed_at,
        )

    def _persist_if_configured(
        self,
        result: LocalAdvisoryFixtureRunnerResult,
        *,
        recorded_at: datetime,
    ) -> LocalAdvisoryFixtureRunnerResult:
        if self.evidence_writer is not None:
            self.evidence_writer.save(result, recorded_at=recorded_at)
        return result

"""Fail-closed runtime economics reviews for backtest workloads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BacktestRuntimeReviewerResult(StrEnum):
    """Source review result for backtest runtime evidence."""

    PASSED = "PASSED"
    WATCHLIST = "WATCHLIST"
    REJECTED = "REJECTED"
    CONFLICTING = "CONFLICTING"


class BacktestRuntimeEconomicsReviewStatus(StrEnum):
    """Machine-readable review state for backtest runtime claims."""

    BLOCKED = "BLOCKED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_BACKTEST_RUNTIME = "RESEARCH_ONLY_BACKTEST_RUNTIME"


@dataclass(frozen=True, slots=True)
class BacktestRuntimeEconomicsEvidence:
    """Measured backtest runtime evidence with no execution authority."""

    artifact_id: str
    title: str
    source_url: str
    source_sha256: str
    hardware_profile: str
    runtime_stack: str
    reviewer_result: BacktestRuntimeReviewerResult
    claimed_monthly_cost_usd: float | None = None
    measured_latency_ms: float | None = None
    measured_simulations_per_second: float | None = None
    measured_power_watts: float | None = None
    benchmark_citations: tuple[str, ...] = ()
    privacy_controls: tuple[str, ...] = ()
    operational_controls: tuple[str, ...] = ()
    rejection_reason: str = ""
    source_available: bool = True
    credential_free_source: bool = True
    gpu_available: bool = False
    gpu_requested: bool = False
    gpu_used: bool = False
    execution_allowed: bool = False
    installation_allowed: bool = False
    provider_switch_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            artifact_id=self.artifact_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            hardware_profile=self.hardware_profile,
            runtime_stack=self.runtime_stack,
        )
        if not self.source_url.startswith("https://") or "@" in self.source_url:
            raise ValueError(
                "backtest runtime source URL must be credential-free HTTPS"
            )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("backtest runtime source hash must be lowercase SHA-256")
        _require_unique_nonblank(
            "backtest runtime benchmark citations",
            self.benchmark_citations,
        )
        _require_unique_nonblank(
            "backtest runtime privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "backtest runtime operational controls",
            self.operational_controls,
        )
        _require_bounded_optional_text(rejection_reason=self.rejection_reason)
        numeric_values = tuple(
            value
            for value in (
                self.claimed_monthly_cost_usd,
                self.measured_latency_ms,
                self.measured_simulations_per_second,
                self.measured_power_watts,
            )
            if value is not None
        )
        if any(not isfinite(value) or value < 0.0 for value in numeric_values):
            raise ValueError(
                "backtest runtime measurements must be finite and non-negative"
            )
        if (
            self.execution_allowed
            or self.installation_allowed
            or self.provider_switch_allowed
            or self.signal_authority
            or self.live_order_authority
        ):
            raise ValueError("backtest runtime evidence cannot grant authority")
        if self.gpu_used and not self.gpu_available:
            raise ValueError("gpu_used cannot be true when GPU availability is false")


@dataclass(frozen=True, slots=True)
class BacktestRuntimeEconomicsReview:
    """Fail-closed review for local backtest runtime economics claims."""

    artifact_id: str
    title: str
    source_url: str
    source_sha256: str
    hardware_profile: str
    runtime_stack: str
    status: BacktestRuntimeEconomicsReviewStatus
    reviewer_result: BacktestRuntimeReviewerResult
    blockers: tuple[str, ...]
    benchmark_citations: tuple[str, ...]
    privacy_controls: tuple[str, ...]
    operational_controls: tuple[str, ...]
    claimed_monthly_cost_usd: float | None = None
    measured_latency_ms: float | None = None
    measured_simulations_per_second: float | None = None
    measured_power_watts: float | None = None
    rejection_reason: str = ""
    gpu_available: bool = False
    gpu_requested: bool = False
    gpu_used: bool = False
    promotion_status: str = "RESEARCH_ONLY_BACKTEST_RUNTIME"
    execution_allowed: bool = False
    installation_allowed: bool = False
    provider_switch_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            artifact_id=self.artifact_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            hardware_profile=self.hardware_profile,
            runtime_stack=self.runtime_stack,
        )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("backtest runtime review hash must be lowercase SHA-256")
        if self.status not in set(BacktestRuntimeEconomicsReviewStatus):
            raise ValueError("backtest runtime review status is invalid")
        if self.reviewer_result not in set(BacktestRuntimeReviewerResult):
            raise ValueError("backtest runtime reviewer result is invalid")
        _require_unique_nonblank("backtest runtime blockers", self.blockers)
        _require_unique_nonblank(
            "backtest runtime benchmark citations",
            self.benchmark_citations,
        )
        _require_unique_nonblank(
            "backtest runtime privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "backtest runtime operational controls",
            self.operational_controls,
        )
        _require_bounded_optional_text(rejection_reason=self.rejection_reason)
        numeric_values = tuple(
            value
            for value in (
                self.claimed_monthly_cost_usd,
                self.measured_latency_ms,
                self.measured_simulations_per_second,
                self.measured_power_watts,
            )
            if value is not None
        )
        if any(not isfinite(value) or value < 0.0 for value in numeric_values):
            raise ValueError(
                "backtest runtime measurements must be finite and non-negative"
            )
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("backtest runtime review cannot become a signal")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("backtest runtime review must require human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("backtest runtime review must keep live blocked")
        if self.promotion_status != "RESEARCH_ONLY_BACKTEST_RUNTIME":
            raise ValueError("backtest runtime review must remain research-only")
        if (
            self.execution_allowed
            or self.installation_allowed
            or self.provider_switch_allowed
            or self.signal_authority
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("backtest runtime review cannot grant authority")


def review_backtest_runtime_economics(
    evidence: BacktestRuntimeEconomicsEvidence,
) -> BacktestRuntimeEconomicsReview:
    """Review backtest runtime claims with fail-closed GPU visibility."""

    blockers: list[str] = []
    if not evidence.source_available:
        blockers.append("BACKTEST_RUNTIME_SOURCE_UNAVAILABLE")
    if not evidence.credential_free_source:
        blockers.append("BACKTEST_RUNTIME_CREDENTIAL_BOUNDARY_REQUIRED")
    if not evidence.benchmark_citations:
        blockers.append("BACKTEST_RUNTIME_BENCHMARK_CITATION_REQUIRED")
    if evidence.claimed_monthly_cost_usd is None:
        blockers.append("BACKTEST_RUNTIME_COST_MEASUREMENT_REQUIRED")
    if evidence.measured_latency_ms is None:
        blockers.append("BACKTEST_RUNTIME_LATENCY_MEASUREMENT_REQUIRED")
    if evidence.measured_simulations_per_second is None:
        blockers.append("BACKTEST_RUNTIME_THROUGHPUT_MEASUREMENT_REQUIRED")
    if evidence.measured_power_watts is None:
        blockers.append("POWER_THERMAL_REVIEW_REQUIRED")
    if not evidence.privacy_controls:
        blockers.append("BACKTEST_RUNTIME_PRIVACY_CONTROL_REQUIRED")
    if not evidence.operational_controls:
        blockers.append("BACKTEST_RUNTIME_OPERATIONAL_CONTROL_REQUIRED")
    if evidence.gpu_requested and not evidence.gpu_available:
        blockers.append("BACKTEST_GPU_UNAVAILABLE")
    if evidence.gpu_requested and evidence.gpu_available and not evidence.gpu_used:
        blockers.append("BACKTEST_GPU_ACCELERATION_NOT_SELECTED")
    if evidence.gpu_used and not evidence.gpu_available:
        blockers.append("BACKTEST_GPU_USAGE_UNSUPPORTED")
    if evidence.reviewer_result is BacktestRuntimeReviewerResult.WATCHLIST:
        blockers.append("BACKTEST_RUNTIME_REVIEWER_WATCHLIST")
    elif evidence.reviewer_result is BacktestRuntimeReviewerResult.REJECTED:
        blockers.append("BACKTEST_RUNTIME_REVIEWER_REJECTED")
    elif evidence.reviewer_result is BacktestRuntimeReviewerResult.CONFLICTING:
        blockers.append("BACKTEST_RUNTIME_REVIEWER_CONFLICTING")
    if (
        evidence.reviewer_result is not BacktestRuntimeReviewerResult.PASSED
        and not evidence.rejection_reason.strip()
    ):
        blockers.append("REJECTION_REASON_REQUIRED")

    hard_blockers = {
        "BACKTEST_RUNTIME_SOURCE_UNAVAILABLE",
        "BACKTEST_RUNTIME_CREDENTIAL_BOUNDARY_REQUIRED",
        "BACKTEST_RUNTIME_BENCHMARK_CITATION_REQUIRED",
        "BACKTEST_RUNTIME_REVIEWER_REJECTED",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        status = BacktestRuntimeEconomicsReviewStatus.BLOCKED
    elif blockers:
        status = BacktestRuntimeEconomicsReviewStatus.WATCHLIST
    else:
        status = BacktestRuntimeEconomicsReviewStatus.RESEARCH_ONLY_BACKTEST_RUNTIME

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "BACKTEST_RUNTIME_REVIEW_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return BacktestRuntimeEconomicsReview(
        artifact_id=evidence.artifact_id,
        title=evidence.title,
        source_url=evidence.source_url,
        source_sha256=evidence.source_sha256,
        hardware_profile=evidence.hardware_profile,
        runtime_stack=evidence.runtime_stack,
        status=status,
        reviewer_result=evidence.reviewer_result,
        blockers=tuple(dict.fromkeys(blockers)),
        benchmark_citations=evidence.benchmark_citations,
        privacy_controls=evidence.privacy_controls,
        operational_controls=evidence.operational_controls,
        claimed_monthly_cost_usd=evidence.claimed_monthly_cost_usd,
        measured_latency_ms=evidence.measured_latency_ms,
        measured_simulations_per_second=evidence.measured_simulations_per_second,
        measured_power_watts=evidence.measured_power_watts,
        rejection_reason=evidence.rejection_reason,
        gpu_available=evidence.gpu_available,
        gpu_requested=evidence.gpu_requested,
        gpu_used=evidence.gpu_used,
    )


def _require_text(**values: str) -> None:
    if any(not value.strip() or len(value) > 2_000 for value in values.values()):
        raise ValueError("backtest runtime text fields must be non-empty and bounded")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values) or any(not value.strip() for value in values):
        raise ValueError(f"{name} must be unique and non-empty")


def _require_bounded_optional_text(**values: str) -> None:
    if any(len(value) > 2_000 for value in values.values()):
        raise ValueError("backtest runtime text fields must be bounded")

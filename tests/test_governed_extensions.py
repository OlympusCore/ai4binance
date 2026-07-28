"""Governed telemetry, context, sandbox, statistics and security contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_agents import snapshot

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.agents.telemetry import (
    AgentExecutionMetric,
    InMemoryAgentTelemetry,
)
from ai4binance.application.research import ResearchApplicationService
from ai4binance.market_context import (
    MarketContextEvent,
    MarketContextProvider,
    MarketContextRegistry,
    MarketContextRequest,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
)
from ai4binance.sandbox import (
    ExperimentManifest,
    ExperimentSandbox,
    ExperimentSandboxPolicy,
    SandboxBackendOutput,
    SandboxCapabilities,
    SandboxRunStatus,
    validate_experiment_source,
)
from ai4binance.schemas import AgentStatus
from ai4binance.security_scan import (
    SecurityFinding,
    SecurityScanArtifact,
    SecurityScanRequest,
    SecurityScanService,
    SecurityScanStatus,
    SecuritySeverity,
)
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    assess_statistical_evidence,
)

NOW = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)


def test_orchestrator_emits_bounded_low_cardinality_metrics() -> None:
    telemetry = InMemoryAgentTelemetry(capacity=128)
    state = EnterpriseOrchestrator(
        telemetry_sink=telemetry,
        agent_latency_budget_ms=60_000,
    ).analyze(snapshot())

    metrics = telemetry.snapshot()
    assert metrics
    assert {item.agent_name for item in metrics} == set(state.agent_results)
    assert {item.cycle_id for item in metrics} == {state.snapshot_id}
    assert all(item.elapsed_ms >= 0.0 for item in metrics)
    assert not any(item.latency_budget_exceeded for item in metrics)


def test_telemetry_capacity_and_contract_validation() -> None:
    telemetry = InMemoryAgentTelemetry(capacity=1)
    for name in ("first", "second"):
        telemetry.record(
            AgentExecutionMetric(
                cycle_id="cycle",
                snapshot_id="snapshot",
                agent_name=name,
                elapsed_ms=1.0,
                status=AgentStatus.SUCCESS,
                blocker_count=0,
                latency_budget_exceeded=False,
            )
        )
    assert [item.agent_name for item in telemetry.snapshot()] == ["second"]
    with pytest.raises(ValueError, match="capacity"):
        InMemoryAgentTelemetry(capacity=0)
    with pytest.raises(ValueError, match="blocker"):
        AgentExecutionMetric(
            "cycle", "snapshot", "agent", 1.0, AgentStatus.SUCCESS, -1, False
        )
    with pytest.raises(ValueError, match="identity"):
        AgentExecutionMetric(
            " ", "snapshot", "agent", 1.0, AgentStatus.SUCCESS, 0, False
        )
    with pytest.raises(ValueError, match="elapsed"):
        AgentExecutionMetric(
            "cycle", "snapshot", "agent", -1.0, AgentStatus.SUCCESS, 0, False
        )
    with pytest.raises(ValueError, match="latency budget"):
        EnterpriseOrchestrator(agent_latency_budget_ms=0.0)


@dataclass(frozen=True, slots=True)
class _ContextProvider:
    capability: ProviderCapability
    health_status: ProviderHealthStatus = ProviderHealthStatus.AVAILABLE
    fail_fetch: bool = False
    mismatched_event: bool = False
    retrieved_offset: timedelta = timedelta(0)
    event_category: str = "macro_calendar"
    source_url: str = "https://official.example/events/1"
    tamper_hash: bool = False

    def health(self, checked_at: datetime) -> ProviderHealth:
        blockers = (
            ()
            if self.health_status is ProviderHealthStatus.AVAILABLE
            else (f"PROVIDER_UNAVAILABLE:{self.capability.provider_id}",)
        )
        return ProviderHealth(
            provider_id=self.capability.provider_id,
            checked_at=checked_at,
            status=self.health_status,
            active_backend="official-rest",
            blockers=blockers,
        )

    def fetch(self, request: MarketContextRequest) -> tuple[MarketContextEvent, ...]:
        if self.fail_fetch:
            raise RuntimeError("private provider detail")
        event = MarketContextEvent.create(
            event_id="macro-1",
            provider_id=(
                "wrong" if self.mismatched_event else self.capability.provider_id
            ),
            title="Scheduled macro release",
            scheduled_at=request.requested_at + timedelta(hours=1),
            retrieved_at=request.requested_at + self.retrieved_offset,
            impact="HIGH",
            category=self.event_category,
            source_url=self.source_url,
        )
        if self.tamper_hash:
            event = replace(event, content_hash="0" * 64)
        return (event,)


def _context_provider(
    *,
    health_status: ProviderHealthStatus = ProviderHealthStatus.AVAILABLE,
    fail_fetch: bool = False,
    mismatched_event: bool = False,
    retrieved_offset: timedelta = timedelta(0),
    event_category: str = "macro_calendar",
    source_url: str = "https://official.example/events/1",
    tamper_hash: bool = False,
) -> _ContextProvider:
    return _ContextProvider(
        ProviderCapability(
            provider_id="official-macro",
            categories=("macro_calendar",),
            allowed_hosts=("official.example",),
            provider_revision="2026-07-13",
            license_id="PROPRIETARY-READ-ONLY",
            max_event_age=timedelta(minutes=15),
            official_source=True,
        ),
        health_status=health_status,
        fail_fetch=fail_fetch,
        mismatched_event=mismatched_event,
        retrieved_offset=retrieved_offset,
        event_category=event_category,
        source_url=source_url,
        tamper_hash=tamper_hash,
    )


def test_market_context_is_explicit_sourced_and_research_only() -> None:
    provider: MarketContextProvider = _context_provider()
    registry = MarketContextRegistry((provider,))
    request = MarketContextRequest("snapshot-1", "HOTUSDT", NOW)
    batch = registry.collect(request, ("official-macro",))

    assert batch.blockers == ()
    assert batch.execution_allowed is False
    assert batch.events[0].content_hash
    assert batch.as_news_snapshot()["provider_blockers"] == ()
    assert batch.as_news_snapshot()["provider_provenance"] == (
        {
            "provider_id": "official-macro",
            "provider_revision": "2026-07-13",
            "license_id": "PROPRIETARY-READ-ONLY",
            "official_source": True,
        },
    )

    workflow = ResearchApplicationService(
        market_context_registry=registry,
        market_context_provider_ids=("official-macro",),
    ).run(snapshot())
    assert workflow.market_context is not None
    assert [event.title for event in workflow.market_outlook.high_impact_data] == [
        "Scheduled macro release"
    ]


def test_market_context_provider_failures_are_isolated_and_visible() -> None:
    request = MarketContextRequest("snapshot-1", "HOTUSDT", NOW)
    unavailable = MarketContextRegistry(
        (_context_provider(health_status=ProviderHealthStatus.UNAVAILABLE),)
    ).collect(request, ("official-macro", "missing"))
    assert "PROVIDER_UNAVAILABLE:official-macro" in unavailable.blockers
    assert "MARKET_CONTEXT_PROVIDER_UNKNOWN:missing" in unavailable.blockers

    failed = MarketContextRegistry((_context_provider(fail_fetch=True),)).collect(
        request, ("official-macro",)
    )
    assert failed.blockers == ("MARKET_CONTEXT_FETCH_FAILED:official-macro",)

    mismatched = MarketContextRegistry(
        (_context_provider(mismatched_event=True),)
    ).collect(request, ("official-macro",))
    assert mismatched.events == ()
    assert mismatched.blockers == (
        "MARKET_CONTEXT_EVENT_PROVIDER_MISMATCH:official-macro",
    )

    with pytest.raises(ValueError, match="explicit unique"):
        MarketContextRegistry((_context_provider(),)).collect(request, ())
    with pytest.raises(ValueError, match="explicit registry"):
        ResearchApplicationService(market_context_provider_ids=("official-macro",))


@pytest.mark.parametrize(
    ("provider", "categories", "blocker"),
    [
        (
            _context_provider(retrieved_offset=timedelta(minutes=-16)),
            ("macro_calendar",),
            "MARKET_CONTEXT_EVENT_STALE:official-macro",
        ),
        (
            _context_provider(retrieved_offset=timedelta(seconds=1)),
            ("macro_calendar",),
            "MARKET_CONTEXT_EVENT_TIMESTAMP_INVALID:official-macro",
        ),
        (
            _context_provider(tamper_hash=True),
            ("macro_calendar",),
            "MARKET_CONTEXT_CONTENT_HASH_INVALID:official-macro",
        ),
        (
            _context_provider(),
            ("exchange_announcement",),
            "MARKET_CONTEXT_CATEGORY_NOT_REQUESTED:official-macro",
        ),
        (
            _context_provider(source_url="https://untrusted.example/events/1"),
            ("macro_calendar",),
            "MARKET_CONTEXT_SOURCE_NOT_ALLOWED:official-macro",
        ),
        (
            _context_provider(event_category="exchange_announcement"),
            ("exchange_announcement",),
            "MARKET_CONTEXT_CATEGORY_NOT_ALLOWED:official-macro",
        ),
    ],
)
def test_market_context_rejects_invalid_or_unrequested_evidence(
    provider: _ContextProvider,
    categories: tuple[str, ...],
    blocker: str,
) -> None:
    request = MarketContextRequest("snapshot-1", "HOTUSDT", NOW, categories=categories)
    batch = MarketContextRegistry((provider,)).collect(request, ("official-macro",))
    assert batch.events == ()
    assert batch.blockers == (blocker,)


def test_provider_capability_requires_bounded_provenance() -> None:
    capability = _context_provider().capability
    with pytest.raises(ValueError, match="identity and categories"):
        replace(capability, provider_revision=" ")
    with pytest.raises(ValueError, match="identity and categories"):
        replace(capability, license_id=" ")
    with pytest.raises(ValueError, match="maximum event age"):
        replace(capability, max_event_age=timedelta(0))
    with pytest.raises(ValueError, match="normalized hostnames"):
        replace(capability, allowed_hosts=("Official.Example",))
    with pytest.raises(ValueError, match="hosts must be unique"):
        replace(
            capability,
            allowed_hosts=("official.example", "official.example"),
        )


def test_statistical_evidence_blocks_exploration_and_uncorrected_search() -> None:
    assessment = assess_statistical_evidence(
        (0.02, 0.03, -0.01),
        hypothesis_count=4,
        min_effective_sample_size=4,
        minimum_return=0.0,
        confidence_level=0.95,
        correction=MultipleTestingCorrection.NONE,
        confirmatory=False,
    )
    assert assessment.adjusted_alpha == pytest.approx(0.05)
    assert "INSUFFICIENT_EFFECTIVE_SAMPLE_SIZE" in assessment.blockers
    assert "MULTIPLE_TESTING_CORRECTION_MISSING" in assessment.blockers
    assert "EXPLORATORY_EVIDENCE_NOT_PROMOTABLE" in assessment.blockers
    assert "OOS_RETURN_CONFIDENCE_INTERVAL_INSUFFICIENT" in assessment.blockers

    corrected = assess_statistical_evidence(
        (0.03, 0.03, 0.03),
        hypothesis_count=5,
        min_effective_sample_size=2,
        minimum_return=0.0,
        confidence_level=0.95,
        correction=MultipleTestingCorrection.BONFERRONI,
        confirmatory=True,
    )
    assert corrected.adjusted_alpha == pytest.approx(0.01)
    assert corrected.blockers == ()


@dataclass(frozen=True, slots=True)
class _SandboxBackend:
    capabilities: SandboxCapabilities
    name: str = "test-isolated"
    fail: bool = False

    def execute(
        self, manifest: ExperimentManifest, source: str
    ) -> SandboxBackendOutput:
        assert manifest.network_allowed is False
        if self.fail:
            raise RuntimeError("backend detail")
        return SandboxBackendOutput(stdout=source, exit_code=0)


def test_sandbox_rejects_unsafe_code_and_unproven_backends() -> None:
    policy = ExperimentSandboxPolicy(max_output_bytes=1_024)
    assert validate_experiment_source("import socket", policy) == (
        "SANDBOX_IMPORT_NOT_ALLOWED",
    )
    assert validate_experiment_source("open('secret')", policy) == (
        "SANDBOX_CALL_NOT_ALLOWED",
    )
    assert validate_experiment_source("x.__class__", policy) == (
        "SANDBOX_DUNDER_ACCESS_NOT_ALLOWED",
    )
    assert validate_experiment_source("global x", policy) == (
        "SANDBOX_SCOPE_MUTATION_NOT_ALLOWED",
    )
    assert validate_experiment_source("def broken(:", policy) == (
        "SANDBOX_SOURCE_SYNTAX_ERROR",
    )

    missing = ExperimentSandbox(policy=policy).run(
        experiment_id="exp-1", source="result = 1", created_at=NOW
    )
    assert missing.status is SandboxRunStatus.BLOCKED
    assert missing.blockers == ("SANDBOX_BACKEND_NOT_CONFIGURED",)

    weak_backend = _SandboxBackend(SandboxCapabilities(False, True, True, True))
    weak = ExperimentSandbox(policy=policy, backend=weak_backend).run(
        experiment_id="exp-2", source="result = 1", created_at=NOW
    )
    assert weak.blockers == ("SANDBOX_BACKEND_ISOLATION_INSUFFICIENT",)


def test_sandbox_executes_only_through_explicit_capable_backend() -> None:
    capable = _SandboxBackend(SandboxCapabilities(True, True, True, True))
    result = ExperimentSandbox(backend=capable).run(
        experiment_id="exp-3",
        source="import math\nresult = math.sqrt(4)",
        created_at=NOW,
    )
    assert result.status is SandboxRunStatus.COMPLETED
    assert result.backend_name == "test-isolated"
    assert result.execution_allowed is False
    assert result.promotion_status == "RESEARCH_ONLY"

    failed = ExperimentSandbox(backend=replace(capable, fail=True)).run(
        experiment_id="exp-4", source="result = 1", created_at=NOW
    )
    assert failed.blockers == ("SANDBOX_BACKEND_FAILED",)


@dataclass(frozen=True, slots=True)
class _Scanner:
    name: str = "strix-pinned-test"
    mismatched: bool = False
    fail: bool = False

    def scan(self, request: SecurityScanRequest) -> SecurityScanArtifact:
        if self.fail:
            raise RuntimeError("scanner detail")
        finding = SecurityFinding(
            finding_id="finding-1",
            title="Validated test finding",
            severity=SecuritySeverity.HIGH,
            evidence="reproduction evidence",
            remediation="apply bounded fix",
            file_path="src/example.py",
            cwe="CWE-20",
        )
        return SecurityScanArtifact(
            scan_id="wrong" if self.mismatched else request.scan_id,
            scanner_name=self.name,
            status=SecurityScanStatus.COMPLETED,
            findings=(finding,),
            blockers=(),
        )


def test_security_scanner_is_optional_evidence_only(tmp_path: Path) -> None:
    request = SecurityScanRequest("scan-1", tmp_path.resolve(), NOW)
    blocked = SecurityScanService().run(request)
    assert blocked.blockers == ("SECURITY_SCANNER_NOT_CONFIGURED",)

    completed = SecurityScanService(_Scanner()).run(request)
    assert completed.status is SecurityScanStatus.COMPLETED
    assert completed.findings[0].severity is SecuritySeverity.HIGH
    assert completed.auto_fix_allowed is False

    mismatch = SecurityScanService(_Scanner(mismatched=True)).run(request)
    assert mismatch.blockers == ("SECURITY_SCAN_IDENTITY_MISMATCH",)
    failed = SecurityScanService(_Scanner(fail=True)).run(request)
    assert failed.blockers == ("SECURITY_SCANNER_FAILED",)

    with pytest.raises(ValueError, match="repository-relative"):
        replace(completed.findings[0], file_path=str(tmp_path.resolve()))


def test_security_scan_contracts_fail_closed(tmp_path: Path) -> None:
    request = SecurityScanRequest("scan-2", tmp_path.resolve(), NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(request, created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="identity"):
        replace(request, scan_id=" ")

    finding = SecurityFinding(
        finding_id="finding-2",
        title="Evidence-backed finding",
        severity=SecuritySeverity.MEDIUM,
        evidence="bounded evidence",
        remediation="human-reviewed remediation",
    )
    with pytest.raises(ValueError, match="evidence"):
        replace(finding, evidence=" ")
    with pytest.raises(ValueError, match="requires blockers"):
        SecurityScanArtifact(
            scan_id="scan-2",
            scanner_name=None,
            status=SecurityScanStatus.BLOCKED,
            findings=(),
            blockers=(),
        )
    with pytest.raises(ValueError, match="cannot contain blockers"):
        SecurityScanArtifact(
            scan_id="scan-2",
            scanner_name="scanner",
            status=SecurityScanStatus.COMPLETED,
            findings=(finding,),
            blockers=("UNEXPECTED",),
        )
    with pytest.raises(ValueError, match="cannot auto-fix"):
        replace(SecurityScanService().run(request), auto_fix_allowed=True)

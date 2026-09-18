"""Coverage recovery tests for split CLI and advisory portfolio branches."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.account.account_snapshot import (
    AccountSnapshot,
    AccountSnapshotBuilder,
    FuturesCapitalSnapshot,
    SpotAssetSnapshot,
)
from ai4binance.accounting import FileReconciliationSummary
from ai4binance.accounting.collectors import BinanceAccountingRestSource
from ai4binance.accounting.records import BinanceAccountLedger, ProductType
from ai4binance.accounting.user_stream import (
    AccountingUserStreamCollectorService,
    BinanceUsdMListenKeyManager,
    FuturesUsdMUserDataStreamSession,
    HmacSpotUserDataStreamSession,
)
from ai4binance.agents.advanced import AdvancedTechnicalAgent, build_advanced_agent
from ai4binance.agents.catalog import build_default_registry
from ai4binance.cli import accounting as cli_accounting
from ai4binance.cli import parser as cli_parser
from ai4binance.cli import research as cli_research
from ai4binance.cli import runtime as cli_runtime
from ai4binance.cli import status as cli_status
from ai4binance.cli import voice as cli_voice
from ai4binance.config import Settings
from ai4binance.content.models import (
    ComplianceStatus,
    ContentClaim,
    ContentDraft,
    ContentSource,
    DraftQueueStatus,
)
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.enterprise import (
    GpuResourceGovernor,
    GpuTelemetryAssessment,
    GpuTelemetrySnapshot,
)
from ai4binance.exchange.filters import (
    LotSizeFilter,
    NotionalFilter,
    PriceFilter,
    SymbolFilters,
)
from ai4binance.exchange.private import PrivateCredentials
from ai4binance.funding.funding_plan import (
    FundingAction,
    FundingActionDecision,
    FundingPlanEngine,
)
from ai4binance.funding.liquidity_conversion_advisor import (
    ConversionDecision,
    ConversionSource,
    LiquidityAndConversionAdvisor,
)
from ai4binance.market_context import (
    MarketContextEvent,
    MarketContextRegistry,
    MarketContextRequest,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
)
from ai4binance.markets import CapitalMarket
from ai4binance.mcp import server as mcp_server
from ai4binance.ops.quality_triage import (
    CheckStatus,
    QualityCheck,
    QualityTriageConfig,
    _run_check,
    run_quality_triage,
)
from ai4binance.ops.quality_triage import (
    build_parser as build_quality_parser,
)
from ai4binance.ops.quality_triage import (
    main as quality_main,
)
from ai4binance.portfolio.analytics import PortfolioAnalytics, ValuedSpotAsset
from ai4binance.portfolio.asset_policy import (
    AssetClassification,
    AssetClassificationRecord,
    AssetPolicy,
)
from ai4binance.portfolio.cost_basis import CostBasisService
from ai4binance.portfolio.current_holding_review import (
    CurrentHoldingInput,
    CurrentHoldingReviewEngine,
    HoldingDecision,
    RecoveryState,
)
from ai4binance.portfolio.futures import (
    FuturesAccountSnapshot,
    FuturesAccountSnapshotService,
    FuturesPosition,
)
from ai4binance.portfolio.holding_opportunity import (
    HoldingOpportunity,
    HoldingOpportunityAction,
    HoldingOpportunityAdvice,
    HoldingOpportunityReport,
    HoldingsOpportunityReviewEngine,
    PortfolioOpportunity,
    RiskRewardProfile,
)
from ai4binance.portfolio.inventory_rotation import (
    InventoryRotationAction,
    InventoryRotationPhase,
    InventoryRotationProposal,
    InventoryRotationState,
)
from ai4binance.portfolio.investment import (
    InvestmentManagementAssistant,
    ManagementAction,
    MarketManagementContext,
    OpportunityReviewItem,
)
from ai4binance.portfolio.orders import AccountOpenOrder, normalize_open_order
from ai4binance.portfolio.rebalancing import RebalanceAction, RebalanceProposal
from ai4binance.portfolio.risk_reward_gate import (
    RiskRewardGate,
    RiskRewardGateInput,
    RiskRewardGatePolicy,
)
from ai4binance.portfolio.wallet import (
    SpotBalance,
    WalletSnapshot,
    WalletSnapshotService,
)
from ai4binance.research.backtesting.metrics import calculate_metrics
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    ClosureReview,
    TradeRecord,
)
from ai4binance.risk import RiskConfig, RiskContext, RiskEngine
from ai4binance.sandbox import (
    ExperimentSandbox,
    ExperimentSandboxPolicy,
    SandboxBackendOutput,
    SandboxCapabilities,
    SandboxRunStatus,
    validate_experiment_source,
)
from ai4binance.scanners.orchestrator import MultiSymbolScanReport, ScannerOrchestrator
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.universe import (
    FuturesUniverseBuilder,
    SpotUniverseBuilder,
    UniverseFilterPolicy,
    UniverseFilterResult,
    UniverseMarket,
    UniverseSymbol,
)

NOW = datetime(2026, 7, 19, 12, tzinfo=UTC)


def profile(
    quality: str = "70",
    rr: str = "2",
    risk: str = "30",
    confidence: str = "0.8",
) -> RiskRewardProfile:
    return RiskRewardProfile(
        Decimal(quality),
        Decimal(rr),
        Decimal(risk),
        Decimal(confidence),
    )


def test_cli_parser_helpers_cover_slash_and_symbol_branches() -> None:
    assert cli_parser.normalize_slash_command("/portfolio", None) == "portfolio"
    assert (
        cli_parser.normalize_slash_command("/manual-actions", None) == "manual-actions"
    )
    assert cli_parser.normalize_slash_command("/approvals", None) == "approvals"
    assert cli_parser.normalize_slash_command("/scan", "spot") == "scan-spot"
    assert cli_parser.normalize_slash_command("/scan", " futures ") == "scan-futures"
    assert cli_parser.normalize_slash_command("/scan", "all") == "scan-all"
    assert cli_parser.normalize_slash_command("/scan", "margin") == "scan-unknown"
    assert cli_parser.normalize_slash_command("status", None) == "status"

    assert cli_parser.normalize_cli_symbol(None) is None
    assert cli_parser.normalize_cli_symbol(" btcusdt ") == "BTCUSDT"
    with pytest.raises(ValueError, match="alphanumeric"):
        cli_parser.normalize_cli_symbol("BTC/USDT")

    assert cli_parser.parse_as_of("2026-07-19").isoformat() == "2026-07-19"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        cli_parser.parse_as_of("19-07-2026")
    assert cli_parser.safe_validation_symbol("bad!", Settings()) == "BTCUSDT"


def test_cli_status_helpers_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".tmp").mkdir()
    (tmp_path / ".tmp-alias-check").mkdir()
    (tmp_path / "runtime" / "tmp" / "pytest" / "vscode-pytest").mkdir(parents=True)
    settings = Settings(manual_approval_queue_path=tmp_path / "approvals.jsonl")
    snapshot = MarketSnapshot(
        snapshot_id="snap-1",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="ETHUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": ()},
        latest_price=Decimal("3000"),
        bid=Decimal("2999"),
        ask=Decimal("3001"),
        spread=Decimal("2"),
        exchange_filters={},
        data_freshness={},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={"base_asset": " eth "},
    )
    fallback = MarketSnapshot(
        snapshot_id="snap-2",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="BTCUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": ()},
        latest_price=Decimal("60000"),
        bid=Decimal("59990"),
        ask=Decimal("60010"),
        spread=Decimal("20"),
        exchange_filters={},
        data_freshness={},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={},
    )

    assert cli_status.fusion_asset(snapshot) == "ETH"
    assert cli_status.fusion_asset(fallback) == "BTC"
    assert cli_status.known_stale_temp_paths(tmp_path) == (
        ".tmp",
        ".tmp-alias-check",
        "runtime/tmp/pytest/vscode-pytest",
    )
    assert cli_status.blockers_exit_code({"blockers": ()}) == 0
    assert cli_status.blockers_exit_code({"blockers": ("BLOCKED",)}) == 2

    manual_payload = cli_status.manual_actions_payload(settings)
    approvals_payload = cli_status.approvals_payload(settings)
    assert manual_payload["blockers"] == ("NO_PENDING_MANUAL_ACTIONS",)
    assert manual_payload["execution_allowed"] is False
    assert approvals_payload["approvals"] == ()

    for command in ("scan-spot", "scan-futures", "scan-all", "scan-unknown"):
        payload = cli_status.scan_command_payload(command)
        assert payload["command"] == command
        assert payload["execution_allowed"] is False
        assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_quality_triage_runs_redacts_persists_and_blocks_overlap(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    ticks = iter((0.0, 0.2, 0.2, 0.5, 0.5, 0.7))

    def runner(
        arguments: Sequence[str],
        *,
        cwd: Path,
        stdout: int,
        stderr: int,
        text: bool,
        errors: str,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, stdout, stderr, text, errors, timeout, check
        name = arguments[-1]
        calls.append(name)
        return subprocess.CompletedProcess(
            list(arguments),
            0 if name == "pass" else 1,
            stdout=f"{'x' * 40}\napi_key=value\n{name}",
        )

    config = QualityTriageConfig(
        repository_root=tmp_path,
        output_directory=tmp_path / "quality",
        command_timeout_seconds=1,
        max_output_characters=30,
    )
    report = run_quality_triage(
        config,
        revision="abc123",
        checks=(
            QualityCheck("pass", ("python", "pass")),
            QualityCheck("fail", ("python", "fail")),
        ),
        runner=runner,
        clock=lambda: NOW,
        monotonic=lambda: next(ticks),
    )

    assert calls == ["pass", "fail"]
    assert report.status == "FAILED"
    assert report.checks[0].status is CheckStatus.PASSED
    assert report.checks[1].status is CheckStatus.FAILED
    assert report.checks[1].output_truncated is True
    assert "[REDACTED]" in (tmp_path / "quality" / "state.json").read_text(
        encoding="utf-8"
    )
    assert (tmp_path / "quality" / "runs.jsonl").exists()

    timeout = _run_check(
        QualityCheck("timeout", ("python", "timeout")),
        config,
        tmp_path,
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("cmd", 1, output=b"secret=value")
        ),
        monotonic=lambda: 1.0,
    )
    assert timeout.status is CheckStatus.TIMED_OUT

    os_error = _run_check(
        QualityCheck("oserror", ("python", "oserror")),
        config,
        tmp_path,
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")),
        monotonic=lambda: 1.0,
    )
    assert os_error.status is CheckStatus.ERROR

    with pytest.raises(ValueError, match="positive"):
        QualityTriageConfig(tmp_path, tmp_path / "out", command_timeout_seconds=0)
    with pytest.raises(ValueError, match="existing directory"):
        run_quality_triage(
            QualityTriageConfig(tmp_path / "missing", tmp_path / "out"),
            revision="x",
        )

    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "quality_triage.lock").write_text("", encoding="utf-8")
    assert (
        quality_main(
            [
                "--repository-root",
                str(tmp_path),
                "--output-directory",
                str(blocked_dir),
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    parsed = build_quality_parser().parse_args(["--revision", "LOCAL"])
    assert parsed.revision == "LOCAL"


def test_sandbox_policy_validation_and_backend_paths() -> None:
    policy = ExperimentSandboxPolicy(max_output_bytes=1024)
    assert SandboxCapabilities(True, True, True, True).ready is True
    assert SandboxCapabilities(True, False, True, True).ready is False
    assert validate_experiment_source("import math\nx = math.sqrt(4)", policy) == ()
    assert validate_experiment_source("import os\nopen('x')", policy) == (
        "SANDBOX_IMPORT_NOT_ALLOWED",
        "SANDBOX_CALL_NOT_ALLOWED",
    )
    assert validate_experiment_source("global x", policy) == (
        "SANDBOX_SCOPE_MUTATION_NOT_ALLOWED",
    )
    assert validate_experiment_source("x = obj.__dict__", policy) == (
        "SANDBOX_DUNDER_ACCESS_NOT_ALLOWED",
    )
    assert validate_experiment_source("if", policy) == ("SANDBOX_SOURCE_SYNTAX_ERROR",)
    assert validate_experiment_source("x" * 70_000, policy) == (
        "SANDBOX_SOURCE_TOO_LARGE",
    )

    blocked = ExperimentSandbox(policy=policy).run(
        experiment_id="exp-1",
        source="print(1)",
        created_at=NOW,
    )
    assert blocked.status is SandboxRunStatus.BLOCKED
    assert blocked.blockers == ("SANDBOX_BACKEND_NOT_CONFIGURED",)

    class Backend:
        name = "safe-backend"
        capabilities = SandboxCapabilities(True, True, True, True)

        def execute(self, manifest: object, source: str) -> SandboxBackendOutput:
            del manifest, source
            return SandboxBackendOutput(stdout="x" * 2048, stderr="ok", exit_code=0)

    completed = ExperimentSandbox(policy=policy, backend=Backend()).run(
        experiment_id="exp-2",
        source="print(1)",
        created_at=NOW,
    )
    assert completed.status is SandboxRunStatus.COMPLETED
    assert len(completed.stdout.encode("utf-8")) == policy.max_output_bytes
    assert completed.execution_allowed is False

    class UnsafeBackend(Backend):
        capabilities = SandboxCapabilities(True, False, True, True)

    unsafe = ExperimentSandbox(policy=policy, backend=UnsafeBackend()).run(
        experiment_id="exp-3",
        source="print(1)",
        created_at=NOW,
    )
    assert unsafe.blockers == ("SANDBOX_BACKEND_ISOLATION_INSUFFICIENT",)

    class FailingBackend(Backend):
        def execute(self, manifest: object, source: str) -> SandboxBackendOutput:
            del manifest, source
            raise RuntimeError("backend failed")

    failed = ExperimentSandbox(policy=policy, backend=FailingBackend()).run(
        experiment_id="exp-4",
        source="print(1)",
        created_at=NOW,
    )
    assert failed.blockers == ("SANDBOX_BACKEND_FAILED",)
    with pytest.raises(ValueError, match="allowlist"):
        ExperimentSandboxPolicy(allowed_imports=("math", "math"))


def test_mcp_server_registers_fixed_tools_and_reports_missing_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tools = mcp_server.build_tool_functions(tmp_path)
    assert set(tools) == {
        "health_check",
        "get_quality_triage",
        "get_market_outlook",
        "get_research_blockers",
        "market.get_snapshot",
        "market.get_data_quality",
        "market.get_provenance",
        "evidence.get",
        "evidence.verify",
        "evidence.get_provenance",
        "evidence.find_conflicts",
        "evidence.build_bundle",
        "governance.get_policy",
        "governance.get_authority",
        "governance.check_action",
        "governance.check_contract",
        "governance.get_blockers",
        "quant_research.get_capabilities",
        "quant_research.verify_formula",
        "quant_research.assess_statistics",
        "quant_research.wolfram_status",
    }
    assert json.loads(tools["health_check"]())["execution_allowed"] is False

    registered: list[tuple[str, str]] = []
    real_loader = mcp_server.load_fastmcp_factory

    class ServerStub:
        def tool(self, *, name: str, description: str) -> object:
            registered.append((name, description))

            def decorator(function: object) -> object:
                return function

            return decorator

        def run(self, *, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setattr(
        mcp_server,
        "load_fastmcp_factory",
        lambda: lambda *args, **kwargs: ServerStub(),
    )
    server = mcp_server.create_server(tmp_path)
    assert isinstance(server, ServerStub)
    assert [item[0] for item in registered] == list(tools)
    assert mcp_server.main(["--artifact-root", str(tmp_path)]) == 0

    monkeypatch.setattr(
        cast(Any, mcp_server).importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("mcp")),
    )
    with pytest.raises(RuntimeError, match="MCP SDK"):
        real_loader()


def test_market_context_registry_validates_provider_evidence() -> None:
    capability = ProviderCapability(
        provider_id="calendar",
        categories=("macro_calendar",),
        allowed_hosts=("example.com",),
        provider_revision="v1",
        license_id="public",
        max_event_age=timedelta(days=1),
        official_source=True,
    )
    request = MarketContextRequest(
        snapshot_id="snapshot-1",
        symbol="BTCUSDT",
        requested_at=NOW,
    )
    event = MarketContextEvent.create(
        event_id="event-1",
        provider_id="calendar",
        title="High impact event",
        scheduled_at=NOW + timedelta(hours=1),
        retrieved_at=NOW - timedelta(minutes=1),
        impact="high",
        category="macro_calendar",
        source_url="https://example.com/event",
    )

    class Provider:
        def __init__(
            self,
            health: ProviderHealth,
            events: tuple[MarketContextEvent, ...],
        ) -> None:
            self.capability = capability
            self._health = health
            self._events = events

        def health(self, checked_at: datetime) -> ProviderHealth:
            assert checked_at == NOW
            return self._health

        def fetch(
            self,
            request: MarketContextRequest,
        ) -> tuple[MarketContextEvent, ...]:
            assert request.symbol == "BTCUSDT"
            return self._events

    registry = MarketContextRegistry(
        (
            Provider(
                ProviderHealth("calendar", NOW, ProviderHealthStatus.AVAILABLE),
                (event, event),
            ),
        )
    )
    batch = registry.collect(request, ("calendar",))
    assert len(batch.events) == 1
    assert batch.blockers == ()
    news = batch.as_news_snapshot()
    assert news["provider_blockers"] == ()

    mismatched = MarketContextRegistry(
        (
            Provider(
                ProviderHealth("other", NOW, ProviderHealthStatus.AVAILABLE),
                (),
            ),
        )
    ).collect(request, ("calendar",))
    assert mismatched.blockers == ("MARKET_CONTEXT_PROVIDER_IDENTITY_MISMATCH",)

    stale_event = MarketContextEvent.create(
        event_id="event-2",
        provider_id="calendar",
        title="Stale event",
        scheduled_at=NOW,
        retrieved_at=NOW - timedelta(days=3),
        impact="CRITICAL",
        category="macro_calendar",
        source_url="https://example.com/stale",
    )
    stale = MarketContextRegistry(
        (
            Provider(
                ProviderHealth("calendar", NOW, ProviderHealthStatus.AVAILABLE),
                (stale_event,),
            ),
        )
    ).collect(request, ("calendar", "missing"))
    assert "MARKET_CONTEXT_EVENT_STALE:calendar" in stale.blockers
    assert "MARKET_CONTEXT_PROVIDER_UNKNOWN:missing" in stale.blockers

    with pytest.raises(ValueError, match="unique"):
        MarketContextRegistry(
            (
                Provider(
                    ProviderHealth("calendar", NOW, ProviderHealthStatus.AVAILABLE),
                    (),
                ),
            )
            * 2
        )
    with pytest.raises(ValueError, match="normalized"):
        ProviderCapability(
            "bad",
            ("macro",),
            ("Example.com",),
            "v1",
            "lic",
            timedelta(days=1),
        )


def candle_series(closes_: Sequence[str]) -> tuple[OHLCVCandle, ...]:
    candles: list[OHLCVCandle] = []
    for index, close_text in enumerate(closes_):
        close = Decimal(close_text)
        candles.append(
            OHLCVCandle(
                timestamp=NOW + timedelta(minutes=index),
                open=close - Decimal("0.2"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=Decimal("100") + Decimal(index),
            )
        )
    return tuple(candles)


def advanced_agent(name: str) -> AdvancedTechnicalAgent:
    agent = build_advanced_agent(build_default_registry().get(name))
    assert isinstance(agent, AdvancedTechnicalAgent)
    return agent


def test_advanced_agent_private_feature_branches_are_deterministic() -> None:
    agent = advanced_agent("fibonacci")
    base = replace(risk_snapshot(), created_at=NOW + timedelta(hours=2))
    rising = candle_series(
        tuple(str(Decimal("100") + Decimal(index)) for index in range(60))
    )
    flat_top = candle_series(["100"] * 60)
    flat_bottom = candle_series(
        ["150"] * 10 + ["100", *(["110"] * 24)] + ["100", *(["210"] * 24)]
    )
    harmonic = candle_series(
        [
            *("100" for _ in range(19)),
            "105",
            *("105" for _ in range(9)),
            "101",
            *("101" for _ in range(9)),
            "106",
            *("106" for _ in range(9)),
            "102",
            *("102" for _ in range(9)),
            "107",
        ]
    )
    elliott = candle_series(
        [
            *("100" for _ in range(10)),
            *("100" for _ in range(9)),
            "110",
            *("110" for _ in range(9)),
            "105",
            *("105" for _ in range(9)),
            "115",
            *("115" for _ in range(9)),
            "108",
            *("108" for _ in range(9)),
            "120",
        ]
    )

    trend_channel_feature = agent._trend_channel(rising, base)
    assert trend_channel_feature.evidence == ("LINEAR_CHANNEL_SLOPE",)
    assert trend_channel_feature.metadata == {
        "method": "TREND_CHANNEL",
        "window_bars": 30,
        "start_close": "130",
        "end_close": "159",
        "slope": "1",
        "atr_14": "2",
        "channel_width": "2",
        "direction": "UPTREND",
    }
    bullish = list(rising)
    bullish[-2] = replace(
        bullish[-2],
        open=Decimal("110"),
        close=Decimal("100"),
        high=Decimal("111"),
        low=Decimal("99"),
    )
    bullish[-1] = replace(
        bullish[-1],
        open=Decimal("99"),
        close=Decimal("111"),
        high=Decimal("112"),
        low=Decimal("98"),
    )
    candlestick = agent._candlestick(tuple(bullish), base)
    assert candlestick is not None
    assert candlestick.setups == ("BULLISH_ENGULFING",)
    top_pattern = agent._chart_pattern(flat_top, base)
    assert top_pattern is not None
    assert top_pattern.setups == ("DOUBLE_TOP",)
    bottom_pattern = agent._chart_pattern(flat_bottom, base)
    assert bottom_pattern is not None
    assert bottom_pattern.setups == ("DOUBLE_BOTTOM",)
    fibonacci_feature = agent._fibonacci(rising, base)
    assert fibonacci_feature.metadata is not None
    assert fibonacci_feature.metadata["method"] == "FIBONACCI_RETRACEMENT"
    assert fibonacci_feature.metadata["window_bars"] == 55
    assert fibonacci_feature.metadata["swing_low"] == "104"
    assert fibonacci_feature.metadata["swing_high"] == "160"
    assert fibonacci_feature.metadata["current_close"] == "159"
    assert fibonacci_feature.metadata["nearest_level"] == "0.618"
    assert fibonacci_feature.metadata["retracement_zone"] == "UPPER_RETRACEMENT_ZONE"
    assert fibonacci_feature.metadata["reference_levels"] == (
        "0.236",
        "0.382",
        "0.500",
        "0.618",
        "0.786",
    )
    harmonic_feature = agent._harmonic(harmonic, base)
    assert harmonic_feature is not None
    assert harmonic_feature.evidence == ("BOUNDED_ABCD_GEOMETRY",)
    elliott_feature = agent._elliott(elliott, base)
    assert elliott_feature is not None
    assert elliott_feature.evidence == ("RULE_BASED_ELLIOTT_WAVE_PROXY",)
    assert elliott_feature.metadata == {
        "theory": "ELLIOTT_WAVE_PRINCIPLE",
        "heuristic": "ALTERNATING_SWINGS_PROXY",
    }
    assert agent._ichimoku(rising, base).evidence == ("ICHIMOKU_CLOUD_LOCATION",)
    assert agent._volume_profile(rising, base).evidence == (
        "VOLUME_WEIGHTED_POC_PROXY",
    )

    sweep = list(rising)
    sweep[-1] = replace(
        sweep[-1],
        open=Decimal("140"),
        low=Decimal("80"),
        close=Decimal("150"),
        high=Decimal("160"),
        volume=Decimal("10000"),
    )
    smc_feature = agent._smc(tuple(sweep), base)
    assert smc_feature is not None
    assert smc_feature.setups == ("BULLISH_SWEEP",)
    wyckoff_feature = agent._wyckoff(tuple(sweep), base)
    assert wyckoff_feature is not None
    assert wyckoff_feature.setups == ("SPRING_PROXY",)

    breakout = list(rising)
    for index in range(-22, -2):
        breakout[index] = replace(
            breakout[index],
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
        )
    breakout[-2] = replace(
        breakout[-2],
        open=Decimal("100"),
        low=Decimal("90"),
        close=Decimal("111"),
        high=Decimal("112"),
    )
    breakout[-1] = replace(
        breakout[-1],
        open=Decimal("112"),
        low=Decimal("109"),
        close=Decimal("113"),
        high=Decimal("114"),
    )
    breakout_feature = agent._breakout_retest(tuple(breakout), base)
    assert breakout_feature is not None
    assert breakout_feature.setups == ("BULLISH_BREAKOUT_RETEST",)
    assert agent._mean_reversion(rising, base).evidence == ("CLOSE_ZSCORE",)
    assert agent._statistics(rising, base).evidence == ("RETURN_DISTRIBUTION",)
    correlated = replace(
        base,
        market_metadata={"benchmark_closes": [str(100 + index) for index in range(60)]},
    )
    correlation_feature = agent._correlation(rising, correlated)
    assert correlation_feature is not None
    assert correlation_feature.evidence == ("BENCHMARK_RETURN_CORRELATION",)
    assert AdvancedTechnicalAgent._number(True) is None
    assert AdvancedTechnicalAgent._number("nan") is None
    assert AdvancedTechnicalAgent._timestamp("not-a-date") is None
    assert AdvancedTechnicalAgent._decimal_sequence(["1", object()]) == ()


def test_accounting_status_latest_reconciliation_branches(tmp_path: Path) -> None:
    missing = cli_accounting.latest_reconciliation_status(tmp_path / "missing.jsonl")
    assert missing["blockers"] == ("RECONCILIATION_RESULTS_MISSING",)

    malformed_path = tmp_path / "malformed.jsonl"
    malformed_path.write_text("not-json\n{}\n", encoding="utf-8")
    malformed = cli_accounting.latest_reconciliation_status(malformed_path)
    assert malformed["blockers"] == ("RECONCILIATION_RESULT_MALFORMED",)

    warning_path = tmp_path / "warning.jsonl"
    warning_path.write_text(
        json.dumps({"payload": {"severity": "WARNING"}}) + "\n",
        encoding="utf-8",
    )
    warning = cli_accounting.latest_reconciliation_status(warning_path)
    assert warning["status"] == "DEGRADED"
    assert warning["blockers"] == ("RECONCILIATION_NOT_CLEAN:WARNING",)

    mixed_path = tmp_path / "mixed.jsonl"
    mixed_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "payload": {
                            "severity": "OK",
                            "envelope": {"endpoint": "accounting:reconciliation"},
                        }
                    }
                ),
                json.dumps(
                    {
                        "payload": {
                            "severity": "BLOCKED",
                            "envelope": {"endpoint": "runtime:read_only_cycle"},
                        }
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    mixed = cli_accounting.latest_reconciliation_status(mixed_path)
    assert mixed["status"] == "CLEAN"
    assert mixed["blockers"] == ()


def test_accounting_daemons_validate_cycles_and_print(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(runtime_cycle_interval_seconds=5)
    with pytest.raises(ValueError, match="positive"):
        cli_accounting.accounting_collect_daemon(settings, max_cycles=0)
    with pytest.raises(ValueError, match="positive"):
        cli_accounting.accounting_ws_daemon(settings, max_cycles=0)

    monkeypatch.setattr(
        cli_accounting,
        "accounting_collect_once",
        lambda _settings: (
            {
                "status": "BLOCKED",
                "blockers": ("NO_CREDS",),
                "execution_allowed": False,
            },
            2,
        ),
    )
    assert cli_accounting.accounting_collect_daemon(settings, max_cycles=1) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"

    monkeypatch.setattr(
        cli_accounting,
        "accounting_ws_once",
        lambda _settings: (
            {
                "status": "COLLECTED",
                "blockers": (),
                "execution_allowed": False,
            },
            0,
        ),
    )
    assert cli_accounting.accounting_ws_daemon(settings, max_cycles=1) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COLLECTED"


def test_accounting_collect_and_ws_success_paths_are_serialized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    class CredentialsStub:
        @classmethod
        def from_environment_or_file(cls, path: Path) -> CredentialsStub:
            assert path == Path("secrets/bnc.env")
            return cls()

    class TransportStub:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class RequestFactoryStub:
        def __init__(self, credentials: object) -> None:
            self.credentials = credentials

    class ReaderStub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class RestSourceStub:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class LedgerStub:
        def __init__(self, root: Path) -> None:
            self.root = root

    class CollectorResult:
        blockers: tuple[str, ...] = ()
        rejected_count = 0

    class CollectorStub:
        def __init__(self, ledger: object) -> None:
            self.ledger = ledger

        def ingest_snapshot(self, *args: object, **kwargs: object) -> CollectorResult:
            assert args
            snapshot_id = kwargs["snapshot_id"]
            assert isinstance(snapshot_id, str)
            assert snapshot_id.startswith("accounting-BTCUSDT-")
            return CollectorResult()

    class ReconciliationStub:
        status = "CLEAN"
        blockers: tuple[str, ...] = ()

    class ReconcilerStub:
        def __init__(self, ledger: object, freshness_seconds: int) -> None:
            self.ledger = ledger
            self.freshness_seconds = freshness_seconds

        def reconcile_latest(self, **kwargs: object) -> ReconciliationStub:
            assert kwargs["sync_run_id"]
            return ReconciliationStub()

    class ReportBuilderStub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

        def write(self, observed_at: datetime) -> dict[str, object]:
            assert observed_at.tzinfo is not None
            return {"status": "CLEAN", "html_path": str(tmp_path / "report.html")}

    class SessionStub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class ListenKeyManagerStub:
        def __init__(self, credentials: object) -> None:
            self.credentials = credentials

    class WsResult:
        status = "COLLECTED"

    class WsCollectorStub:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def collect_once(self, *, sync_run_id: str) -> WsResult:
            assert sync_run_id.startswith("accounting-ws-BTCUSDT-")
            return WsResult()

    replacements = {
        "PrivateCredentials": CredentialsStub,
        "UrllibPrivateJsonTransport": TransportStub,
        "SignedReadOnlyRequestFactory": RequestFactoryStub,
        "SignedUsdMReadOnlyRequestFactory": RequestFactoryStub,
        "BinancePrivateAccountReader": ReaderStub,
        "BinanceUsdMPrivateAccountReader": ReaderStub,
        "BinanceAccountingRestSource": RestSourceStub,
        "BinanceAccountLedger": LedgerStub,
        "AccountingRestCollector": CollectorStub,
        "AccountingFileReconciler": ReconcilerStub,
        "AccountingUiReportBuilder": ReportBuilderStub,
        "HmacSpotUserDataStreamSession": SessionStub,
        "FuturesUsdMUserDataStreamSession": SessionStub,
        "BinanceUsdMListenKeyManager": ListenKeyManagerStub,
        "AccountingUserStreamCollectorService": WsCollectorStub,
    }
    for name, value in replacements.items():
        monkeypatch.setattr(cli_accounting, name, value)

    settings = Settings(
        symbol="BTCUSDT",
        binance_accounting_directory=tmp_path / "ledger",
        accounting_report_directory=tmp_path / "reports",
    )
    collect_payload, collect_exit = cli_accounting.accounting_collect_once(settings)
    ws_payload, ws_exit = cli_accounting.accounting_ws_once(settings)

    assert collect_exit == 0
    assert collect_payload["status"] == "COLLECTED"
    assert collect_payload["execution_allowed"] is False
    assert ws_exit == 0
    assert ws_payload["status"] == "COLLECTED"
    assert ws_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_accounting_dispatch_prints_ui_report_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    settings = Settings(accounting_report_directory=tmp_path)
    monkeypatch.setattr(
        cli_accounting,
        "accounting_ui_report",
        lambda _settings: {
            "status": "DEGRADED",
            "html_path": str(tmp_path / "report.html"),
            "execution_allowed": False,
        },
    )
    assert (
        cli_accounting.run_accounting_command(
            "accounting-ui-report",
            settings,
            max_cycles=None,
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "DEGRADED"

    with pytest.raises(ValueError, match="unsupported accounting command"):
        cli_accounting.run_accounting_command("unknown", settings, max_cycles=None)


def test_binance_accounting_rest_source_safe_wrappers_and_configuration() -> None:
    class SpotReader:
        def all_orders(self, symbol: str, *, limit: int) -> object:
            assert symbol == "BTCUSDT"
            assert limit == 2
            return "not-a-sequence"

        def trades(self, symbol: str, *, limit: int) -> object:
            del symbol, limit
            raise RuntimeError("offline")

        def universal_transfers(self, transfer_type: str, *, limit: int) -> object:
            assert limit == 2
            if transfer_type == "MAIN_UMFUTURE":
                return {
                    "rows": [
                        {
                            "asset": "USDT",
                            "amount": "10",
                            "timestamp": 1_784_367_000_000,
                            "tranId": "transfer-1",
                            "status": "CONFIRMED",
                        }
                    ]
                }
            return "bad"

    class FuturesReader:
        def positions(self, symbol: str) -> object:
            assert symbol == "BTCUSDT"
            return ()

        def all_orders(self, symbol: str, *, limit: int) -> object:
            del symbol, limit
            return []

        def algo_open_orders(self, symbol: str) -> object:
            del symbol
            return []

        def trades(self, symbol: str, *, limit: int) -> object:
            del symbol, limit
            return []

        def income(self, symbol: str, *, limit: int) -> object:
            del symbol, limit
            return []

        def leverage_bracket(self, symbol: str) -> object:
            assert symbol == "BTCUSDT"
            return [{"brackets": [{"bracket": "1", "notionalCap": "50000"}]}]

    with pytest.raises(ValueError, match="between 1 and 1000"):
        BinanceAccountingRestSource(
            cast(Any, SpotReader()),
            cast(Any, FuturesReader()),
            "BTCUSDT",
            limit=0,
        )

    source = BinanceAccountingRestSource(
        cast(Any, SpotReader()),
        cast(Any, FuturesReader()),
        "btcusdt",
        limit=2,
    )
    assert source.spot_orders() == ()
    assert source.spot_trades() == ()
    flows = cast(list[dict[str, object]], source.spot_capital_flows())
    assert flows[0]["flowType"] == "SPOT_FUTURES_TRANSFER"
    assert source.futures_positions() == ()
    configurations = cast(list[dict[str, object]], source.futures_configurations())
    assert configurations[0]["notionalBracket"] == "1"
    assert source.blockers == [
        "SPOT_ORDER_HISTORY_UNAVAILABLE",
        "SPOT_TRADE_HISTORY_UNAVAILABLE",
        "SPOT_TRANSFER_HISTORY_UNAVAILABLE:UMFUTURE_MAIN",
    ]


def test_user_stream_sessions_and_service_failure_edges(tmp_path: Path) -> None:
    credentials = PrivateCredentials("api-key", "api-secret")

    with pytest.raises(ValueError, match="allowlisted"):
        HmacSpotUserDataStreamSession(credentials, url="wss://example.com/ws")
    with pytest.raises(ValueError, match="recvWindow"):
        HmacSpotUserDataStreamSession(credentials, receive_window_ms=999)

    class BadJsonConnection:
        def send(self, payload: str) -> None:
            self.payload = payload

        def recv(self, *, timeout: float) -> str:
            del timeout
            return "{bad"

        def close(self) -> None:
            self.closed = True

    spot = HmacSpotUserDataStreamSession(
        credentials,
        connection_factory=lambda *args, **kwargs: BadJsonConnection(),
    )
    with pytest.raises(RuntimeError, match="invalid JSON"):
        spot.open()
    spot.close()

    class RejectingConnection:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def send(self, payload: str) -> None:
            self.sent.append(payload)

        def recv(self, *, timeout: float) -> str:
            del timeout
            return json.dumps({"id": json.loads(self.sent[-1])["id"], "status": 400})

        def close(self) -> None:
            pass

    rejecting = HmacSpotUserDataStreamSession(
        credentials,
        connection_factory=lambda *args, **kwargs: RejectingConnection(),
    )
    with pytest.raises(RuntimeError, match="rejected"):
        rejecting.open()

    manager = BinanceUsdMListenKeyManager(
        credentials,
        opener=lambda request, timeout: b"[]",
    )
    with pytest.raises(RuntimeError, match="not an object"):
        manager.start()
    with pytest.raises(ValueError, match="allowlisted"):
        manager._request("PATCH")
    with pytest.raises(ValueError, match="allowlisted"):
        FuturesUsdMUserDataStreamSession(manager, base_url="wss://example.com")

    class FailingSession:
        product_type = ProductType.SPOT

        def open(self) -> None:
            raise RuntimeError("cannot open")

        def receive_event(self, *, timeout_seconds: float) -> dict[str, object]:
            del timeout_seconds
            return {}

        def close(self) -> None:
            raise RuntimeError("cannot close")

    class EventFailSession:
        product_type = ProductType.FUTURES_USDM

        def open(self) -> None:
            return None

        def receive_event(self, *, timeout_seconds: float) -> dict[str, object]:
            del timeout_seconds
            raise ValueError("bad event")

        def close(self) -> None:
            raise RuntimeError("close failed")

    service = AccountingUserStreamCollectorService(
        ledger=BinanceAccountLedger(tmp_path),
        sessions=(FailingSession(), EventFailSession()),
        event_limit=2,
        collect_seconds=1.0,
        receive_timeout_seconds=0.1,
    )
    summary = service.collect_once(sync_run_id="ws-fail")
    assert summary.status == "DEGRADED"
    assert "SPOT_WEBSOCKET_OPEN_FAILED:RuntimeError" in summary.blockers
    assert "FUTURES_USDM_WEBSOCKET_EVENT_FAILED:ValueError" in summary.blockers
    assert "FUTURES_USDM_WEBSOCKET_CLOSE_FAILED" in summary.blockers
    with pytest.raises(ValueError, match="at least one"):
        AccountingUserStreamCollectorService(
            ledger=BinanceAccountLedger(tmp_path),
            sessions=(),
            event_limit=1,
            collect_seconds=1.0,
            receive_timeout_seconds=1.0,
        )


def test_portfolio_payload_success_and_runtime_failure_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spot = WalletSnapshot(
        captured_at=NOW,
        account_status="SPOT",
        can_trade=True,
        balances=(SpotBalance("USDT", Decimal("25"), Decimal("0")),),
        symbol="BTCUSDT",
    )

    class AssetValue:
        asset = "USDT"
        price_usdt = Decimal("1")

    class Analytics:
        valued_assets = (AssetValue(),)

    class RuntimeReport:
        cycle_id = "cycle-1"
        created_at = NOW
        portfolio_analytics = Analytics()
        spot_wallet = spot
        futures_account = None
        state = "READY"
        blockers: tuple[str, ...] = ()

    class RuntimeStub:
        def run(self, now: datetime) -> RuntimeReport:
            assert now.tzinfo is not None
            return RuntimeReport()

    monkeypatch.setattr(
        cli_runtime,
        "build_read_only_runtime",
        lambda _settings: RuntimeStub(),
    )
    settings = Settings(
        symbol="BTCUSDT",
        preferred_quote_assets=("USDT",),
        runtime_state_path=tmp_path / "runtime.json",
        paper_ledger_path=tmp_path / "paper-ledger.jsonl",
    )
    success = cli_status.portfolio_command_payload(settings)
    assert success["status"] == "READY"
    assert success["execution_allowed"] is False
    assert success["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert success["blockers"] == ()
    virtual_portfolio = cast(dict[str, object], success["virtual_portfolio"])
    assert virtual_portfolio["position_count"] == 0
    account_runtime = cast(dict[str, object], success["account_runtime"])
    assert account_runtime["status"] == "BLOCKED"
    assert "FUTURES_ACCOUNT_UNAVAILABLE" in cast(
        tuple[str, ...], account_runtime["blockers"]
    )
    assert "RECONCILIATION_REQUIRED" in cast(
        tuple[str, ...], account_runtime["blockers"]
    )
    success_report_paths = success["user_report_paths"]
    assert isinstance(success_report_paths, dict)
    assert Path(success_report_paths["latest_json_path"]) == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_portfolio"
        / "latest.json"
    )
    assert Path(success_report_paths["latest_markdown_path"]).is_file()

    monkeypatch.setattr(
        cli_runtime,
        "build_read_only_runtime",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    failure = cli_status.portfolio_command_payload(settings)
    assert failure["status"] == "READY"
    assert failure["blockers"] == ()
    failure_runtime = cast(dict[str, object], failure["account_runtime"])
    assert failure_runtime["status"] == "UNAVAILABLE"
    assert failure_runtime["blockers"] == ("PORTFOLIO_RUNTIME_UNAVAILABLE",)
    failure_report_paths = failure["user_report_paths"]
    assert isinstance(failure_report_paths, dict)
    assert Path(failure_report_paths["latest_markdown_path"]).is_file()


def test_portfolio_command_payload_surfaces_user_report_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RuntimeStub:
        def run(self, now: datetime) -> object:
            del now
            raise RuntimeError("offline")

    monkeypatch.setattr(
        cli_runtime,
        "build_read_only_runtime",
        lambda _settings: RuntimeStub(),
    )
    monkeypatch.setattr(
        cli_runtime,
        "_write_virtual_portfolio_user_report",
        lambda _settings, _payload: (_ for _ in ()).throw(
            RuntimeError("report write failed")
        ),
    )
    settings = Settings(
        symbol="BTCUSDT",
        preferred_quote_assets=("USDT",),
        runtime_state_path=tmp_path / "runtime.json",
        paper_ledger_path=tmp_path / "paper-ledger.jsonl",
    )

    payload = cli_status.portfolio_command_payload(settings)

    assert payload["status"] == "BLOCKED"
    assert payload["state"] == "BLOCKED"
    assert payload["blockers"] == ("VIRTUAL_PORTFOLIO_USER_REPORT_WRITE_FAILED",)
    account_runtime = cast(dict[str, object], payload["account_runtime"])
    assert account_runtime["status"] == "UNAVAILABLE"
    assert account_runtime["blockers"] == ("PORTFOLIO_RUNTIME_UNAVAILABLE",)


def test_build_voice_runtime_uses_local_components_when_session_accepted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Session:
        accepted = True

    class Component:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class ResponderStub(Component):
        def respond(self, intent: object) -> str:
            return f"response:{intent}"

    captured: dict[str, object] = {}

    def runtime_factory(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(cli_voice, "microphone_available", lambda: True)
    monkeypatch.setattr(cli_voice, "interactive_windows_user", lambda: "user")
    monkeypatch.setattr(
        cli_voice,
        "assess_local_session",
        lambda *, interactive_user, microphone_available: Session(),
    )
    monkeypatch.setattr(cli_voice, "PrivateAccountStateReader", Component)
    monkeypatch.setattr(cli_voice, "VoiceResponseBuilder", ResponderStub)
    monkeypatch.setattr(cli_voice, "EdgeTtsSpeaker", Component)
    monkeypatch.setattr(cli_voice, "WindowsSapiSpeaker", Component)
    monkeypatch.setattr(cli_voice, "FallbackSpeechOutput", Component)
    monkeypatch.setattr(cli_voice, "SoundDeviceRecorder", Component)
    monkeypatch.setattr(cli_voice, "FasterWhisperTranscriber", Component)
    monkeypatch.setattr(cli_voice, "VoiceCommandGateway", Component)
    monkeypatch.setattr(cli_voice, "VoiceReportScheduler", Component)
    monkeypatch.setattr(cli_voice, "VoiceAssistantRuntime", runtime_factory)

    class GovernorStub:
        def __init__(self) -> None:
            self.last_telemetry_assessment = GpuTelemetryAssessment(
                observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                source_label="unit-test",
                cuda_available=True,
                device_name="NVIDIA GeForce RTX 4090",
                driver_version="555.85",
                total_vram_bytes=24_064_000_000,
                free_vram_bytes=18_048_000_000,
                gpu_utilization_pct=19,
                active_gpu_processes=1,
                headroom_percent=30,
                healthy=True,
                blockers=(),
            )

        def select_voice_runtime(self, preferred_device: str) -> SimpleNamespace:
            assert preferred_device == "cpu"
            return SimpleNamespace(selected_device="cpu")

    monkeypatch.setattr(cli_voice, "GpuResourceGovernor", GovernorStub)

    runtime = cli_voice.build_voice_runtime(
        Settings(private_runtime_state_path=tmp_path / "private.json")
    )

    assert runtime is not None
    assert "recorder" in captured
    transcriber = captured["transcriber"]
    assert isinstance(transcriber, Component)
    assert transcriber.kwargs["device"] == "cpu"
    assert transcriber.kwargs["compute_type"] == "int8"
    telemetry_assessment = captured["telemetry_assessment"]
    assert isinstance(telemetry_assessment, GpuTelemetryAssessment)
    assert telemetry_assessment.source_label == "unit-test"
    assert "status_responder" in captured
    assert callable(captured["status_responder"])


def test_portfolio_user_report_includes_gpu_telemetry_assessment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _offline_urlopen(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("network disabled for telemetry-only unit test")

    # This test verifies report telemetry, not external feed availability.
    monkeypatch.setattr("urllib.request.urlopen", _offline_urlopen)
    for target in (
        "ai4binance.exchange.transport.urlopen",
        "ai4binance.exchange.private.urlopen",
        "ai4binance.whale_fusion.derivatives.binance_client.urlopen",
    ):
        monkeypatch.setattr(target, _offline_urlopen)
    monkeypatch.setattr(
        GpuResourceGovernor,
        "collect_telemetry",
        lambda self: GpuTelemetrySnapshot.unavailable(source="unit-test"),
    )
    settings = Settings(
        preferred_quote_assets=("USDT",),
        runtime_state_path=tmp_path / "runtime.json",
        paper_ledger_path=tmp_path / "paper-ledger.jsonl",
    )

    payload = cli_status.portfolio_command_payload(settings)
    report_paths = payload["user_report_paths"]
    assert isinstance(report_paths, dict)
    report_json = json.loads(
        Path(report_paths["latest_json_path"]).read_text(encoding="utf-8")
    )
    markdown = Path(report_paths["latest_markdown_path"]).read_text(encoding="utf-8")

    assessment = cast(dict[str, object], report_json["runtime"]["telemetry_assessment"])
    assert assessment["source_label"] == "unit-test"
    assert assessment["healthy"] is False
    assert assessment["blockers"] == ["CUDA_UNAVAILABLE"]
    assert "- GPU telemetry assessment: `False` unit-test" in markdown


def test_voice_command_blocks_and_handles_runtime_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    settings = Settings(
        private_runtime_state_path=tmp_path / "private.json",
        runtime_state_path=tmp_path / "runtime.json",
    )
    monkeypatch.setattr(cli_voice, "wait_for_private_state", lambda _path: False)
    assert cli_voice.run_voice_command("voice-once", settings, max_cycles=None) == 2

    monkeypatch.setattr(cli_voice, "wait_for_private_state", lambda _path: True)
    monkeypatch.setattr(
        cli_voice,
        "build_voice_runtime",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("no mic")),
    )
    assert cli_voice.run_voice_command("voice-once", settings, max_cycles=None) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "VOICE_RUNTIME_FAILED"

    runs: list[int | None] = []

    class RuntimeStub:
        def run(self, *, max_cycles: int | None) -> None:
            runs.append(max_cycles)

    class LeaseStub:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> LeaseStub:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        cli_voice, "build_voice_runtime", lambda _settings: RuntimeStub()
    )
    monkeypatch.setattr(cli_voice, "SingleInstanceLease", LeaseStub)
    assert cli_voice.run_voice_command("voice-once", settings, max_cycles=9) == 0
    assert cli_voice.run_voice_command("voice-daemon", settings, max_cycles=3) == 0
    assert runs == [1, 3]


def test_current_holding_review_covers_all_decision_branches() -> None:
    engine = CurrentHoldingReviewEngine()
    holdings = (
        CurrentHoldingInput(
            "bad",
            "BADUSDT",
            AssetClassification.UNSUPPORTED,
            Decimal("100"),
            Decimal("0.1"),
            profile(),
            Decimal("80"),
        ),
        CurrentHoldingInput(
            "USDT",
            "USDTUSDT",
            AssetClassification.CASH_EQUIVALENT,
            Decimal("100"),
            Decimal("0.1"),
            profile(),
            Decimal("80"),
        ),
        CurrentHoldingInput(
            "DUST",
            "DUSTUSDT",
            AssetClassification.DUST,
            Decimal("1"),
            Decimal("0.01"),
            profile(),
            Decimal("80"),
        ),
        CurrentHoldingInput(
            "RISK",
            "RISKUSDT",
            AssetClassification.CONVERTIBLE,
            Decimal("100"),
            Decimal("0.1"),
            profile(risk="90"),
            Decimal("80"),
        ),
        CurrentHoldingInput(
            "RR",
            "RRUSDT",
            AssetClassification.CONVERTIBLE,
            Decimal("100"),
            Decimal("0.1"),
            profile(rr="1.1"),
            Decimal("80"),
        ),
        CurrentHoldingInput(
            "GOOD",
            "GOODUSDT",
            AssetClassification.CONVERTIBLE,
            Decimal("100"),
            Decimal("0.1"),
            profile(quality="90"),
            Decimal("80"),
        ),
        CurrentHoldingInput(
            "MID",
            "MIDUSDT",
            AssetClassification.CONVERTIBLE,
            Decimal("100"),
            Decimal("0.1"),
            profile(quality="60"),
            Decimal("80"),
        ),
    )

    report = engine.review(holdings)
    actions = [item.recommended_action for item in report.assessments]
    assert actions == [
        HoldingDecision.RESEARCH_ONLY,
        HoldingDecision.NO_ACTION,
        HoldingDecision.NO_ACTION,
        HoldingDecision.EXIT_CANDIDATE,
        HoldingDecision.CONVERSION_CANDIDATE,
        HoldingDecision.HOLD_OPPORTUNITY,
        HoldingDecision.RECOVERY_WATCH,
    ]
    assert report.assessments[0].recovery_state is RecoveryState.UNDETERMINED
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def holding(
    asset: str,
    *,
    quality: str = "50",
    rr: str = "1.0",
    risk: str = "40",
    value: str = "200",
    liquid: str = "100",
    blockers: tuple[str, ...] = (),
) -> HoldingOpportunity:
    return HoldingOpportunity(
        asset,
        f"{asset}USDT",
        Decimal(value),
        Decimal(liquid),
        profile(quality, rr, risk),
        blockers,
    )


def opportunity(
    symbol: str,
    *,
    market: CapitalMarket = CapitalMarket.SPOT,
    quality: str = "80",
    rr: str = "2.2",
    risk: str = "25",
    required: str = "100",
    blockers: tuple[str, ...] = (),
) -> PortfolioOpportunity:
    return PortfolioOpportunity(
        market,
        symbol,
        Decimal(required),
        profile(quality, rr, risk),
        blockers,
    )


def universe_symbol(
    symbol: str,
    *,
    market: UniverseMarket = UniverseMarket.SPOT,
    quote: str = "USDT",
    status: str = "TRADING",
    volume: str = "2000000",
    spread: str = "10",
    depth: str = "50000",
    quality: bool = True,
    contract_type: str | None = None,
    margin_asset: str | None = None,
    open_interest: str | None = None,
    funding_rate: str | None = None,
) -> UniverseSymbol:
    return UniverseSymbol(
        symbol=symbol,
        market=market,
        base_asset=symbol.removesuffix(quote) or "BASE",
        quote_asset=quote,
        status=status,
        min_notional_usdt=Decimal("5"),
        quote_volume_24h_usdt=Decimal(volume),
        spread_bps=Decimal(spread),
        depth_0_5_pct_usdt=Decimal(depth),
        data_quality_ok=quality,
        contract_type=contract_type,
        margin_asset=margin_asset,
        open_interest_usdt=(None if open_interest is None else Decimal(open_interest)),
        funding_rate=None if funding_rate is None else Decimal(funding_rate),
    )


def test_universe_filters_and_scanner_orchestrator_cover_rejections() -> None:
    with pytest.raises(ValueError, match="quote assets"):
        UniverseFilterPolicy(quote_assets=("",))
    with pytest.raises(ValueError, match="non-negative"):
        UniverseFilterPolicy(minimum_open_interest_usdt=Decimal("-1"))
    with pytest.raises(ValueError, match="identity"):
        universe_symbol("bad/usdt")
    with pytest.raises(ValueError, match="funding rate"):
        universe_symbol(
            "BTCUSDT",
            market=UniverseMarket.USD_M_FUTURES,
            contract_type="PERPETUAL",
            margin_asset="USDT",
            open_interest="1000000",
            funding_rate="NaN",
        )

    spot_ok = universe_symbol("BTCUSDT")
    spot_bad = universe_symbol(
        "ETHBTC",
        market=UniverseMarket.USD_M_FUTURES,
        quote="BTC",
        status="BREAK",
        volume="10",
        spread="100",
        depth="1",
        quality=False,
    )
    spot_results = SpotUniverseBuilder().filter((spot_ok, spot_bad))
    assert SpotUniverseBuilder().accepted((spot_ok, spot_bad)) == (spot_ok,)
    assert spot_results[0].accepted is True
    assert set(spot_results[1].blockers) == {
        "MARKET_NOT_SPOT",
        "SYMBOL_NOT_TRADING",
        "QUOTE_ASSET_NOT_ALLOWED",
        "INSUFFICIENT_24H_VOLUME",
        "SPREAD_EXCEEDS_LIMIT",
        "INSUFFICIENT_ORDER_BOOK_DEPTH",
        "DATA_INCOMPLETE",
    }

    futures_ok = universe_symbol(
        "BTCUSDT",
        market=UniverseMarket.USD_M_FUTURES,
        contract_type="perpetual",
        margin_asset="usdt",
        open_interest="2000000",
        funding_rate="0.001",
    )
    futures_bad = universe_symbol(
        "ETHUSDT",
        market=UniverseMarket.SPOT,
        contract_type="CURRENT_QUARTER",
        margin_asset="BUSD",
        open_interest="100",
        funding_rate="0.02",
        quality=False,
    )
    futures_results = FuturesUniverseBuilder().filter((futures_ok, futures_bad))
    assert FuturesUniverseBuilder().accepted((futures_ok, futures_bad)) == (futures_ok,)
    assert "MARKET_NOT_USD_M_FUTURES" in futures_results[1].blockers
    assert "FUNDING_RATE_OUT_OF_POLICY" in futures_results[1].blockers

    orchestrator = ScannerOrchestrator()
    all_report = orchestrator.scan_all(
        spot_symbols=(spot_ok, spot_bad),
        futures_symbols=(futures_ok, futures_bad),
    )
    assert all_report.accepted_symbols == ("BTCUSDT", "BTCUSDT")
    assert "ETHBTC" in all_report.rejected_symbols
    assert all_report.execution_allowed is False
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        MultiSymbolScanReport("ALL", (), ("",))
    with pytest.raises(ValueError, match="acceptance"):
        UniverseFilterResult(spot_ok, True, ("BLOCKED",))


def risk_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id="risk-snapshot",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="BTCUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": ()},
        latest_price=Decimal("100"),
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        spread=Decimal("0.2"),
        exchange_filters={},
        data_freshness={},
        data_quality=DataQuality.DATA_VALID,
    )


def trade_candidate(
    *,
    action: Action = Action.BUY,
    status: CandidateStatus = CandidateStatus.READY_FOR_RISK,
    promotion: ValidationStatus = ValidationStatus.PAPER_APPROVED,
    rr: str = "2.5",
    blockers: tuple[str, ...] = (),
    inventory_action: str = "NONE",
) -> TradeCandidate:
    if action is Action.BUY:
        entry_zone = PriceZone(Decimal("99"), Decimal("101"))
        stop = Decimal("95")
        targets = (Decimal("110"),)
        trailing = Decimal("96")
    else:
        entry_zone = PriceZone(Decimal("99"), Decimal("101"))
        stop = Decimal("105")
        targets = (Decimal("90"),)
        trailing = Decimal("104")
        inventory_action = inventory_action if inventory_action != "NONE" else "SELL"
    return TradeCandidate(
        candidate_id="candidate-1",
        snapshot_id="risk-snapshot",
        timestamp=NOW,
        symbol="btcusdt",
        timeframe="1h",
        action=action,
        setup_name="breakout",
        status=status,
        entry_zone=entry_zone,
        invalidation_level=stop,
        stop_loss=stop,
        take_profit_levels=targets,
        trailing_stop=trailing,
        atr=Decimal("2"),
        risk_reward=Decimal(rr),
        score=80.0,
        confidence=0.8,
        promotion_status=promotion,
        inventory_action=inventory_action,
        blockers=blockers,
    )


def test_risk_engine_approves_caps_and_blocks_bad_contexts() -> None:
    filters = SymbolFilters(
        PriceFilter(Decimal("1"), Decimal("1000000"), Decimal("0.01")),
        LotSizeFilter(Decimal("0.001"), Decimal("100"), Decimal("0.001")),
        NotionalFilter(Decimal("5"), Decimal("100000")),
    )
    engine = RiskEngine(
        RiskConfig(
            max_trade_usdt=Decimal("1000"),
            max_open_position_size_usdt=Decimal("1000"),
        )
    )
    approved = engine.evaluate(
        trade_candidate(),
        risk_snapshot(),
        RiskContext(equity_usdt=Decimal("10000")),
        filters,
    )
    assert approved.approved is True
    assert approved.quantity > Decimal("0")

    blocked = engine.evaluate(
        trade_candidate(
            action=Action.SELL,
            status=CandidateStatus.RESEARCH_ONLY,
            promotion=ValidationStatus.RESEARCH_ONLY,
            rr="1",
            blockers=("UPSTREAM_BLOCKER",),
        ),
        replace(risk_snapshot(), latest_price=Decimal("0"), spread=None),
        RiskContext(
            equity_usdt=Decimal("100"),
            daily_loss_usdt=Decimal("3"),
            estimated_slippage_ratio=Decimal("0.01"),
            consecutive_losses=3,
            cooldown_active=True,
        ),
        filters,
    )
    assert {
        "CANDIDATE_NOT_READY_FOR_RISK",
        "STRATEGY_NOT_PROMOTED",
        "STOP_LOSS_COOLDOWN_ACTIVE",
        "REPEATED_LOSS_CIRCUIT_BREAKER",
        "DAILY_LOSS_LIMIT_REACHED",
        "SLIPPAGE_EXCEEDS_LIMIT",
        "LATEST_PRICE_INVALID",
        "RISK_REWARD_BELOW_MINIMUM",
        "INVENTORY_UNKNOWN_FOR_SPOT_SELL",
    } <= set(blocked.blockers)

    many = engine.evaluate_many(
        (trade_candidate(),),
        risk_snapshot(),
        RiskContext(equity_usdt=Decimal("1000")),
        filters,
    )
    assert len(many) == 1
    with pytest.raises(ValueError, match="between one and five"):
        engine.evaluate_many((), risk_snapshot(), RiskContext(), filters, limit=0)
    with pytest.raises(ValueError, match="risk ratios"):
        RiskConfig(max_risk_per_trade=Decimal("2"))
    with pytest.raises(ValueError, match="cannot be negative"):
        RiskContext(current_exposure_usdt=Decimal("-1"))


def asset_record(
    asset: str,
    classification: AssetClassification,
    value: str,
    *,
    funding_eligible: bool = False,
) -> AssetClassificationRecord:
    return AssetClassificationRecord(
        asset=asset,
        classification=classification,
        classification_reason="TEST",
        free=Decimal("1"),
        locked=Decimal("0"),
        estimated_value_usdt=Decimal(value),
        funding_eligible=funding_eligible,
    )


def test_liquidity_conversion_advisor_ranks_and_rejects_sources() -> None:
    advisor = LiquidityAndConversionAdvisor()
    plan = advisor.review(
        free_quote_capital_usdt=Decimal("0"),
        sources=(
            ConversionSource(
                asset_record("ETH", AssetClassification.CONVERTIBLE, "50"),
                Decimal("80"),
                Decimal("20"),
                Decimal("5"),
            ),
            ConversionSource(
                asset_record("USDT", AssetClassification.CASH_EQUIVALENT, "100"),
                Decimal("90"),
                Decimal("5"),
            ),
            ConversionSource(
                asset_record("LOW", AssetClassification.CONVERTIBLE, "5"),
                Decimal("10"),
                Decimal("100"),
                blockers=("MANUAL_REVIEW",),
            ),
        ),
    )
    assert plan.candidates[0].decision is ConversionDecision.CONVERSION_CANDIDATE
    assert plan.candidates[0].asset == "ETH"
    assert "CASH_EQUIVALENT_NOT_CONVERSION_SOURCE" in plan.candidates[1].blockers
    assert "MIN_CONVERSION_NOTIONAL_FAILED" in plan.candidates[2].blockers
    assert "MANUAL_REVIEW" in plan.blockers
    assert plan.execution_allowed is False

    empty = advisor.review(free_quote_capital_usdt=Decimal("0"), sources=())
    assert empty.candidates[0].decision is ConversionDecision.NO_AVAILABLE_FUNDING
    with pytest.raises(ValueError, match="non-negative"):
        advisor.review(free_quote_capital_usdt=Decimal("-1"), sources=())


def test_risk_reward_gate_spot_accepts_and_futures_blocks() -> None:
    gate = RiskRewardGate()
    accepted = gate.evaluate(
        RiskRewardGateInput(
            market=CapitalMarket.SPOT,
            symbol="btcusdt",
            risk_reward=Decimal("2"),
            opportunity_pct=Decimal("0.1"),
            spot_liquid_quote_reserve_pct=Decimal("0.2"),
            oos_confidence=Decimal("0.8"),
            data_quality_ok=True,
            stop_valid=True,
        )
    )
    assert accepted.accepted is True
    assert accepted.symbol == "BTCUSDT"

    blocked = gate.evaluate(
        RiskRewardGateInput(
            market=CapitalMarket.USD_M_FUTURES,
            symbol="ethusdt",
            risk_reward=Decimal("1"),
            opportunity_pct=Decimal("0.5"),
            spot_liquid_quote_reserve_pct=Decimal("0"),
            futures_capital_pct=Decimal("0.2"),
            futures_available_margin_pct=None,
            liquidation_distance_pct=Decimal("0.05"),
            daily_loss_limit_clear=False,
            weekly_loss_limit_clear=False,
            oos_confidence=Decimal("0.1"),
            data_quality_ok=False,
            stop_valid=False,
            same_direction_spot_futures=True,
        )
    )
    assert {
        "DATA_INCOMPLETE",
        "NO_VALID_STOP",
        "INSUFFICIENT_RR",
        "MAXIMUM_SINGLE_OPPORTUNITY_EXCEEDED",
        "LIQUID_RESERVE_DEFICIT",
        "OOS_CONFIDENCE_LOW",
        "DAILY_LOSS_LIMIT",
        "WEEKLY_LOSS_LIMIT",
        "SAME_DIRECTION_SPOT_FUTURES_EXPOSURE",
        "FUTURES_CAPITAL_LIMIT",
        "MARGIN_RESERVE_DEFICIT",
        "LIQUIDATION_RISK",
    } == set(blocked.blockers)
    with pytest.raises(ValueError, match="ratios"):
        RiskRewardGatePolicy(maximum_single_opportunity_pct=Decimal("2"))


def test_content_models_validate_provenance_and_stay_unpublished() -> None:
    source = ContentSource(
        artifact_type="market_outlook",
        source_artifact="artifacts/outlook.json",
        source_sha256="a" * 64,
        evidence_timestamp=NOW,
        freshness_status="FRESH",
    )
    claim = ContentClaim("BTCUSDT remains research-only.", "decision.status")
    draft = ContentDraft(
        draft_id="b" * 64,
        created_at=NOW,
        content="BTCUSDT setup is research-only; live execution is blocked.",
        source=source,
        claims=(claim,),
        compliance_status=ComplianceStatus.PASSED,
    )
    assert draft.queue_status is DraftQueueStatus.REVIEW_REQUIRED
    assert draft.publish_allowed is False
    assert draft.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="hash"):
        ContentSource("type", "artifact", "bad", NOW, "FRESH")
    with pytest.raises(ValueError, match="fresh"):
        ContentSource("type", "artifact", "a" * 64, NOW, "STALE")
    with pytest.raises(ValueError, match="bounded size"):
        ContentClaim("x" * 161, "field")
    with pytest.raises(ValueError, match="only compliant"):
        ContentDraft(
            draft_id="b" * 64,
            created_at=NOW,
            content="blocked",
            source=source,
            claims=(claim,),
            compliance_status=ComplianceStatus.BLOCKED,
        )
    with pytest.raises(ValueError, match="publish"):
        ContentDraft(
            draft_id="b" * 64,
            created_at=NOW,
            content="publish blocked",
            source=source,
            claims=(claim,),
            compliance_status=ComplianceStatus.PASSED,
            publish_allowed=True,
        )


def trade_record(net_pnl: str) -> TradeRecord:
    review = ClosureReview(
        exit_reason=BacktestExitReason.END_OF_DATA,
        lifecycle_error=None,
        stop_quality="OK",
        trailing_quality="OK",
        ignored_signals=0,
        htf_weakness=False,
        volatility_expansion=False,
        level_break=False,
        staged_exit_alternative="NONE",
        lesson_candidate="NO_LESSON",
    )
    return TradeRecord(
        trade_id=f"trade-{net_pnl}",
        signal_id=f"signal-{net_pnl}",
        entry_timestamp=NOW,
        exit_timestamp=NOW,
        entry_price=Decimal("100"),
        exit_price=Decimal("101"),
        quantity=Decimal("1"),
        entry_fee_usdt=Decimal("0.1"),
        exit_fee_usdt=Decimal("0.1"),
        net_pnl_usdt=Decimal(net_pnl),
        return_ratio=Decimal("0.01"),
        exit_reason=BacktestExitReason.END_OF_DATA,
        closure_review=review,
    )


def test_backtest_metrics_empty_profit_loss_and_drawdown_paths() -> None:
    empty = calculate_metrics((), 1000.0, 0.1)
    assert empty.trade_count == 0
    assert empty.profit_factor is None
    assert empty.sharpe is None

    metrics = calculate_metrics(
        (trade_record("10"), trade_record("-5"), trade_record("15")),
        1000.0,
        0.05,
        equity_observations=(1000.0, 1100.0, 900.0, 1200.0),
    )
    assert metrics.net_return == 0.02
    assert metrics.max_drawdown > 0
    assert metrics.profit_factor == 5.0
    assert metrics.sharpe is not None


def test_holding_opportunity_review_covers_funding_and_rotation_branches() -> None:
    engine = HoldingsOpportunityReviewEngine()

    weak_report = engine.review(
        holdings=(holding("ALT"),),
        opportunities=(),
        liquid_capital_usdt=Decimal("5"),
        total_portfolio_value_usdt=Decimal("1000"),
    )
    assert (
        weak_report.advice[0].action
        is HoldingOpportunityAction.REDUCE_TO_LIQUIDITY_REVIEW
    )

    blocked_report = engine.review(
        holdings=(holding("ALT", blockers=("STALE_PRICE",)),),
        opportunities=(opportunity("NEWUSDT", blockers=("OOS_WEAK",)),),
        liquid_capital_usdt=Decimal("200"),
        total_portfolio_value_usdt=Decimal("1000"),
    )
    assert blocked_report.advice[-1].action is HoldingOpportunityAction.BLOCKED
    assert blocked_report.blockers == ("STALE_PRICE", "OOS_WEAK")

    liquid_report = engine.review(
        holdings=(holding("ALT"),),
        opportunities=(opportunity("BTCUSDT"),),
        liquid_capital_usdt=Decimal("200"),
        total_portfolio_value_usdt=Decimal("1000"),
    )
    assert (
        liquid_report.advice[0].action
        is HoldingOpportunityAction.USE_LIQUID_CAPITAL_REVIEW
    )

    spot_rotation = engine.review(
        holdings=(holding("ALT", quality="40", rr="1.0", liquid="200"),),
        opportunities=(opportunity("BTCUSDT", required="150"),),
        liquid_capital_usdt=Decimal("0"),
        total_portfolio_value_usdt=Decimal("1000"),
    )
    assert (
        spot_rotation.advice[0].action is HoldingOpportunityAction.ROTATE_TO_SPOT_REVIEW
    )

    futures_block = engine.review(
        holdings=(holding("ALT"),),
        opportunities=(
            opportunity("BTCUSDT", market=CapitalMarket.USD_M_FUTURES, required="100"),
        ),
        liquid_capital_usdt=Decimal("0"),
        total_portfolio_value_usdt=Decimal("1000"),
        current_futures_capital_usdt=Decimal("100"),
    )
    assert futures_block.advice[0].blockers == ("FUTURES_CAPITAL_TARGET_REACHED",)

    no_source = engine.review(
        holdings=(holding("ALT", quality="79", rr="2.0", liquid="100"),),
        opportunities=(opportunity("BTCUSDT", required="150"),),
        liquid_capital_usdt=Decimal("0"),
        total_portfolio_value_usdt=Decimal("1000"),
    )
    assert no_source.advice[0].blockers == ("NO_SUITABLE_ROTATION_SOURCE",)


class TradeReader:
    def __init__(self, rows: object) -> None:
        self.rows = rows

    def trades(
        self,
        symbol: str,
        *,
        from_id: int | None = None,
        limit: int = 1_000,
    ) -> object:
        del symbol, from_id, limit
        return self.rows


def test_cost_basis_reconstructs_and_reports_blockers() -> None:
    rows = [
        {
            "id": 1,
            "price": "10",
            "qty": "2",
            "quoteQty": "20",
            "commission": "1",
            "commissionAsset": "USDT",
            "isBuyer": True,
            "time": 1,
        },
        {
            "id": 1,
            "price": "10",
            "qty": "2",
            "quoteQty": "20",
            "commission": "1",
            "commissionAsset": "USDT",
            "isBuyer": True,
            "time": 1,
        },
        {
            "id": 2,
            "price": "12",
            "qty": "0.5",
            "quoteQty": "6",
            "commission": "0.1",
            "commissionAsset": "BNB",
            "isBuyer": False,
            "time": 2,
        },
        {
            "id": 3,
            "price": "12",
            "qty": "5",
            "quoteQty": "60",
            "commission": "0",
            "commissionAsset": "USDT",
            "isBuyer": False,
            "time": 3,
        },
    ]

    report = CostBasisService(TradeReader(rows)).evaluate(
        "btcusdt",
        Decimal("0"),
    )

    assert report.symbol == "BTCUSDT"
    assert report.quantity == Decimal("0")
    assert report.average_cost_quote is None
    assert report.trade_count == 4
    assert report.execution_allowed is False
    assert {
        "DUPLICATE_TRADE_ID",
        "TRADE_FEE_CONVERSION_UNAVAILABLE",
        "SELL_EXCEEDS_RECONSTRUCTED_INVENTORY",
    } <= set(report.blockers)

    empty = CostBasisService(TradeReader([])).evaluate("ETHUSDT", Decimal("0"))
    assert empty.blockers == ("TRADE_HISTORY_UNAVAILABLE",)
    with pytest.raises(ValueError, match="array"):
        CostBasisService(TradeReader({})).evaluate("ETHUSDT", Decimal("0"))
    with pytest.raises(ValueError, match="rows"):
        CostBasisService(TradeReader([object()])).evaluate("ETHUSDT", Decimal("0"))


class FuturesReader:
    def __init__(self) -> None:
        self.requested: list[str | None] = []

    def account(self) -> object:
        return {
            "canTrade": True,
            "totalWalletBalance": "1000",
            "availableBalance": "800",
        }

    def positions(self, symbol: str | None = None) -> object:
        self.requested.append(symbol)
        return [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.1",
                "entryPrice": "50000",
                "unRealizedProfit": "10",
                "markPrice": "50100",
                "liquidationPrice": "",
                "leverage": "5",
                "marginType": "cross",
                "notional": "5010",
                "isolatedMargin": "",
            },
            {
                "symbol": "ETHUSDT",
                "positionAmt": "0",
                "entryPrice": "3000",
                "unRealizedProfit": "0",
                "markPrice": "3000",
                "liquidationPrice": "",
                "leverage": "",
                "marginType": "",
                "notional": "",
                "isolatedMargin": "",
            },
        ]

    def open_orders(self, symbol: str | None = None) -> object:
        self.requested.append(symbol)
        return [
            {
                "orderId": 7,
                "clientOrderId": "client-7",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "49000",
                "origQty": "0.1",
                "executedQty": "0",
            }
        ]


def test_futures_snapshot_service_filters_and_handles_delivery_symbols() -> None:
    reader = FuturesReader()
    snapshot = FuturesAccountSnapshotService(reader).capture("btcusdt", NOW)
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.positions[0].margin_type == "CROSS"
    assert snapshot.open_orders[0].remaining_quantity == Decimal("0.1")
    assert reader.requested == ["BTCUSDT", "BTCUSDT"]

    delivery_reader = FuturesReader()
    delivery = FuturesAccountSnapshotService(delivery_reader).capture(
        "btcusdt_260925", NOW
    )
    assert delivery.symbol == "BTCUSDT_260925"
    assert delivery.positions == ()
    assert delivery_reader.requested == [None, None]

    with pytest.raises(ValueError, match="optional underscores"):
        FuturesAccountSnapshotService(FuturesReader()).capture("BTC/USDT", NOW)


class BadFuturesReader:
    def __init__(
        self,
        account: object,
        positions: object,
        orders: object = (),
    ) -> None:
        self.account_payload = account
        self.positions_payload = positions
        self.orders_payload = orders

    def account(self) -> object:
        return self.account_payload

    def positions(self, symbol: str | None = None) -> object:
        del symbol
        return self.positions_payload

    def open_orders(self, symbol: str | None = None) -> object:
        del symbol
        return self.orders_payload


def valid_futures_account() -> dict[str, object]:
    return {
        "canTrade": True,
        "totalWalletBalance": "100",
        "availableBalance": "50",
    }


def valid_futures_position() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "positionAmt": "0.1",
        "entryPrice": "50000",
        "unRealizedProfit": "1",
        "markPrice": "50100",
        "liquidationPrice": "25000",
        "leverage": "5",
        "marginType": "cross",
        "notional": "5010",
        "isolatedMargin": "",
    }


def test_futures_snapshot_validation_edges_are_read_only() -> None:
    with pytest.raises(ValueError, match="symbol is required"):
        FuturesPosition("", Decimal("0"), Decimal("1"), Decimal("0"))
    with pytest.raises(ValueError, match="non-negative"):
        FuturesPosition(
            "BTCUSDT",
            Decimal("0"),
            Decimal("1"),
            Decimal("0"),
            mark_price=Decimal("-1"),
        )
    with pytest.raises(ValueError, match="finite"):
        FuturesPosition("BTCUSDT", Decimal("NaN"), Decimal("1"), Decimal("0"))
    with pytest.raises(ValueError, match="leverage must be positive"):
        FuturesPosition("BTCUSDT", Decimal("0"), Decimal("1"), Decimal("0"), leverage=0)
    with pytest.raises(ValueError, match="margin type cannot be empty"):
        FuturesPosition(
            "BTCUSDT",
            Decimal("0"),
            Decimal("1"),
            Decimal("0"),
            margin_type=" ",
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        FuturesAccountSnapshot(
            datetime(2026, 7, 19, 12),
            "BTCUSDT",
            True,
            Decimal("0"),
            Decimal("0"),
            (),
        )
    with pytest.raises(ValueError, match="identity"):
        FuturesAccountSnapshot(NOW, "", True, Decimal("0"), Decimal("0"), ())
    with pytest.raises(ValueError, match="negative"):
        FuturesAccountSnapshot(NOW, "BTCUSDT", True, Decimal("-1"), Decimal("0"), ())
    with pytest.raises(ValueError, match="non-Futures"):
        FuturesAccountSnapshot(
            NOW,
            "BTCUSDT",
            True,
            Decimal("0"),
            Decimal("0"),
            (),
            (
                AccountOpenOrder(
                    "SPOT",
                    "1",
                    "client",
                    "BTCUSDT",
                    "BUY",
                    "LIMIT",
                    "NEW",
                    Decimal("1"),
                    Decimal("1"),
                    Decimal("0"),
                ),
            ),
        )

    service = FuturesAccountSnapshotService
    with pytest.raises(ValueError, match="futuresAccount must be an object"):
        service(BadFuturesReader([], (), ())).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="positions must be an array"):
        service(BadFuturesReader(valid_futures_account(), {})).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="position must be an object"):
        service(BadFuturesReader(valid_futures_account(), (1,))).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="canTrade must be boolean"):
        service(
            BadFuturesReader(
                {**valid_futures_account(), "canTrade": "yes"},
                (),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="totalWalletBalance must be non-negative"):
        service(
            BadFuturesReader(
                {**valid_futures_account(), "totalWalletBalance": "-1"},
                (),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="entryPrice must be non-negative"):
        service(
            BadFuturesReader(
                valid_futures_account(),
                ({**valid_futures_position(), "entryPrice": "-1"},),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="unRealizedProfit must be decimal-compatible"):
        service(
            BadFuturesReader(
                valid_futures_account(),
                ({**valid_futures_position(), "unRealizedProfit": object()},),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="markPrice must be non-negative"):
        service(
            BadFuturesReader(
                valid_futures_account(),
                ({**valid_futures_position(), "markPrice": "-1"},),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="leverage must be integer-compatible"):
        service(
            BadFuturesReader(
                valid_futures_account(),
                ({**valid_futures_position(), "leverage": True},),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="leverage must be a positive integer"):
        service(
            BadFuturesReader(
                valid_futures_account(),
                ({**valid_futures_position(), "leverage": "0"},),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="marginType must be text"):
        service(
            BadFuturesReader(
                valid_futures_account(),
                ({**valid_futures_position(), "marginType": 1},),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="openOrders must be an array"):
        service(BadFuturesReader(valid_futures_account(), (), {})).capture(
            "BTCUSDT", NOW
        )


def test_account_snapshot_builder_values_blockers_and_ratios() -> None:
    spot = WalletSnapshot(
        captured_at=NOW,
        account_status="SPOT",
        can_trade=True,
        balances=(
            SpotBalance("USDT", Decimal("100"), Decimal("10")),
            SpotBalance("BTC", Decimal("0.01"), Decimal("0")),
            SpotBalance("ALT", Decimal("5"), Decimal("0")),
        ),
        symbol="BTCUSDT",
    )
    futures = FuturesAccountSnapshot(
        captured_at=NOW,
        symbol="BTCUSDT",
        can_trade=True,
        total_wallet_balance=Decimal("50"),
        available_balance=Decimal("25"),
        positions=(
            FuturesPosition(
                symbol="BTCUSDT",
                quantity=Decimal("0.1"),
                entry_price=Decimal("50000"),
                unrealized_pnl=Decimal("10"),
            ),
        ),
        open_orders=(
            AccountOpenOrder(
                "USD_M_FUTURES",
                "1",
                "client",
                "BTCUSDT",
                "BUY",
                "LIMIT",
                "NEW",
                Decimal("49000"),
                Decimal("0.1"),
                Decimal("0"),
            ),
        ),
    )

    snapshot = AccountSnapshotBuilder().build(
        snapshot_id="snapshot-1",
        data_as_of=NOW,
        spot_wallet=spot,
        futures_account=futures,
        prices_usdt={"BTC": Decimal("60000")},
        reconciliation=FileReconciliationSummary(1, 0, ("REPLAY_REQUIRED",)),
    )

    assert snapshot.spot_value_usdt == Decimal("710.00")
    assert snapshot.futures_equity_usdt == Decimal("50")
    assert snapshot.total_value_usdt == Decimal("760.00")
    assert snapshot.futures.position_count == 1 if snapshot.futures else False
    assert "VALUATION_PRICE_UNAVAILABLE" in snapshot.blockers
    assert "REPLAY_REQUIRED" in snapshot.blockers
    assert snapshot.execution_allowed is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    blocked = AccountSnapshotBuilder().build(
        snapshot_id="snapshot-2",
        data_as_of=NOW,
        spot_wallet=None,
        futures_account=None,
        prices_usdt={},
        reconciliation=None,
    )
    assert blocked.spot_ratio == Decimal("0")
    assert blocked.futures_ratio == Decimal("0")
    assert blocked.blockers == (
        "SPOT_WALLET_UNAVAILABLE",
        "FUTURES_ACCOUNT_UNAVAILABLE",
        "RECONCILIATION_REQUIRED",
    )


def test_account_snapshot_validation_edges_remain_fail_closed() -> None:
    spot = SpotAssetSnapshot(
        "BTC",
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("60000"),
        Decimal("18000"),
        Decimal("6000"),
        Decimal("12000"),
        NOW,
    )
    assert spot.total_qty == Decimal("0.3")

    with pytest.raises(ValueError, match="identity"):
        SpotAssetSnapshot("", Decimal("0"), Decimal("0"), None, None, None, None, NOW)
    with pytest.raises(ValueError, match="non-negative"):
        SpotAssetSnapshot(
            "BTC",
            Decimal("-1"),
            Decimal("0"),
            None,
            None,
            None,
            None,
            NOW,
        )
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        SpotAssetSnapshot(
            "BTC",
            Decimal("0"),
            Decimal("0"),
            None,
            None,
            None,
            None,
            NOW,
            (" ",),
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        FuturesCapitalSnapshot(
            Decimal("0"),
            Decimal("0"),
            None,
            None,
            0,
            datetime(2026, 7, 19, 12),
        )
    with pytest.raises(ValueError, match="non-negative"):
        FuturesCapitalSnapshot(
            Decimal("-1"),
            Decimal("0"),
            None,
            None,
            0,
            NOW,
        )
    with pytest.raises(ValueError, match="position count"):
        FuturesCapitalSnapshot(
            Decimal("0"),
            Decimal("0"),
            None,
            None,
            -1,
            NOW,
        )
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        FuturesCapitalSnapshot(
            Decimal("0"),
            Decimal("0"),
            None,
            None,
            0,
            NOW,
            (" ",),
        )

    zero = AccountSnapshot(
        "snapshot-zero",
        NOW,
        (),
        None,
        "UNKNOWN",
        (),
    )
    assert zero.spot_ratio == Decimal("0")
    assert zero.futures_ratio == Decimal("0")

    with pytest.raises(ValueError, match="identity"):
        AccountSnapshot("", NOW, (), None, "UNKNOWN", ())
    with pytest.raises(ValueError, match="timezone-aware"):
        AccountSnapshot(
            "snapshot-1", datetime(2026, 7, 19, 12), (), None, "UNKNOWN", ()
        )
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        AccountSnapshot("snapshot-1", NOW, (), None, "UNKNOWN", (" ",))
    with pytest.raises(ValueError, match="cannot grant execution authority"):
        AccountSnapshot("snapshot-1", NOW, (), None, "UNKNOWN", (), True)

    empty_futures = FuturesAccountSnapshot(
        captured_at=NOW,
        symbol="BTCUSDT",
        can_trade=True,
        total_wallet_balance=Decimal("0"),
        available_balance=Decimal("0"),
        positions=(),
    )
    futures = AccountSnapshotBuilder._futures(empty_futures, NOW)
    assert futures.available_margin_ratio is None
    assert futures.blockers == ("FUTURES_WALLET_EQUITY_UNAVAILABLE",)


def test_investment_management_assistant_keeps_everything_advisory_only() -> None:
    wallet = WalletSnapshot(
        captured_at=NOW,
        account_status="SPOT",
        can_trade=True,
        balances=(
            SpotBalance("USDT", Decimal("20"), Decimal("0")),
            SpotBalance("BTC", Decimal("0.02"), Decimal("0")),
            SpotBalance("ETH", Decimal("1"), Decimal("0")),
        ),
        symbol="BTCUSDT",
        open_orders=(
            AccountOpenOrder(
                "SPOT",
                "11",
                "spot-client",
                "ETHUSDT",
                "SELL",
                "LIMIT",
                "NEW",
                Decimal("3500"),
                Decimal("1"),
                Decimal("0"),
            ),
        ),
    )
    futures = FuturesAccountSnapshot(
        captured_at=NOW,
        symbol="BTCUSDT",
        can_trade=True,
        total_wallet_balance=Decimal("500"),
        available_balance=Decimal("250"),
        positions=(
            FuturesPosition(
                symbol="BTCUSDT",
                quantity=Decimal("-0.05"),
                entry_price=Decimal("65000"),
                unrealized_pnl=Decimal("-25"),
                mark_price=None,
                liquidation_price=Decimal("0"),
                leverage=None,
                margin_type="ISOLATED",
                notional=None,
                isolated_margin=None,
            ),
            FuturesPosition(
                symbol="ETHUSDT",
                quantity=Decimal("1"),
                entry_price=Decimal("3000"),
                unrealized_pnl=Decimal("10"),
                mark_price=Decimal("3010"),
                liquidation_price=Decimal("1500"),
                leverage=3,
                margin_type="CROSS",
                notional=Decimal("3010"),
            ),
        ),
        open_orders=(
            AccountOpenOrder(
                "USD_M_FUTURES",
                "12",
                "futures-client",
                "BTCUSDT",
                "BUY",
                "LIMIT",
                "NEW",
                Decimal("60000"),
                Decimal("0.05"),
                Decimal("0"),
            ),
        ),
    )
    spot_context = MarketManagementContext(
        "SPOT",
        "SELL",
        "BEARISH_REVERSAL",
        ("breakout-retest",),
        ("SPOT_BLOCKED",),
        (
            OpportunityReviewItem(
                "support-reclaim",
                timeframe="1h",
                direction="LONG",
                status="CANDIDATE",
                setup_tier="B",
                score=72.5,
                confidence=0.7,
                blockers=("OOS_REQUIRED",),
            ),
        ),
    )
    futures_context = MarketManagementContext(
        "USD_M_FUTURES",
        "HOLD",
        "BULLISH_CONTINUATION",
        ("basis-watch",),
        ("FUTURES_BLOCKED",),
    )
    analytics = PortfolioAnalytics(
        total_value_usdt=Decimal("1000"),
        valued_assets=(
            ValuedSpotAsset(
                "BTC",
                Decimal("0.02"),
                Decimal("60000"),
                Decimal("1200"),
                Decimal("0.90"),
            ),
            ValuedSpotAsset(
                "USDT",
                Decimal("20"),
                Decimal("1"),
                Decimal("20"),
                Decimal("0.02"),
            ),
        ),
        unpriced_assets=(),
        largest_asset="BTC",
        largest_weight=Decimal("0.90"),
        unrealized_pnl_usdt=None,
        blockers=("PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED",),
    )
    rotation_state = InventoryRotationState(
        "cycle-1",
        InventoryRotationPhase.AWAITING_REBUY,
        NOW,
    )
    rotation = InventoryRotationProposal(
        InventoryRotationAction.REBUY,
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        rotation_state,
        rotation_state,
        (),
    )
    rebalance = RebalanceProposal(
        RebalanceAction.SELL,
        Decimal("0.80"),
        Decimal("0.50"),
        Decimal("0.01"),
        Decimal("600"),
        Decimal("0.6"),
        2,
        ("REBALANCE_REVIEW",),
    )
    holding_report = HoldingOpportunityReport(
        total_portfolio_value_usdt=Decimal("1000"),
        liquid_capital_usdt=Decimal("50"),
        liquid_ratio=Decimal("0.05"),
        advice=(
            HoldingOpportunityAdvice(
                HoldingOpportunityAction.USE_LIQUID_CAPITAL_REVIEW,
                "USDT",
                "BTCUSDT",
                CapitalMarket.SPOT,
                Decimal("25"),
                "Liquid capital can be reviewed for a research-only setup.",
            ),
            HoldingOpportunityAdvice(
                HoldingOpportunityAction.ROTATE_TO_FUTURES_REVIEW,
                "ETH",
                "BTCUSDT",
                CapitalMarket.USD_M_FUTURES,
                Decimal("50"),
                "Futures context is supplementary and proposal-only.",
                ("FUTURES_ADVISORY_ONLY",),
            ),
        ),
        blockers=("HOLDING_REVIEW_REQUIRED",),
    )

    report = InvestmentManagementAssistant().review(
        symbol="btcusdt",
        spot_wallet=wallet,
        futures_account=futures,
        spot=spot_context,
        futures=futures_context,
        portfolio_analytics=analytics,
        rebalance_proposal=rebalance,
        inventory_rotation_proposal=rotation,
        holding_opportunity_report=holding_report,
    )

    assert report.symbol == "BTCUSDT"
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "SPOT_BLOCKED" in report.blockers
    assert "HOLDING_REVIEW_REQUIRED" in report.blockers
    categories = {item.category for item in report.recommendations}
    assert {
        "EXISTING_POSITION",
        "OPEN_ORDER",
        "NEW_OPPORTUNITY",
        "OPPORTUNITY_LIQUIDITY",
        "PORTFOLIO_RISK",
        "PORTFOLIO_REBALANCE",
        "INVENTORY_ROTATION",
        "HOLDING_OPPORTUNITY_REVIEW",
    } <= categories
    assert any(
        item.action is ManagementAction.REDUCE_RISK_REVIEW
        and item.subject == "BTC_INVENTORY"
        for item in report.recommendations
    )
    assert any(
        item.category == "OPPORTUNITY_LIQUIDITY"
        and item.subject == "BTC->USDT_RESERVE"
        and "QUOTE_RESERVE_BELOW_TARGET" in item.blockers
        for item in report.recommendations
    )
    assert any(
        item.subject == "BTCUSDT_SHORT"
        and {
            "MARK_PRICE_UNAVAILABLE",
            "LIQUIDATION_PRICE_UNAVAILABLE",
            "LEVERAGE_UNAVAILABLE",
            "NOTIONAL_UNAVAILABLE",
            "ISOLATED_MARGIN_UNAVAILABLE",
            "FUNDING_DATA_UNAVAILABLE",
        }
        <= set(item.blockers)
        for item in report.recommendations
    )
    assert all(not item.execution_allowed for item in report.recommendations)

    blocked = InvestmentManagementAssistant().review(
        symbol="BTCUSDT",
        spot_wallet=None,
        futures_account=None,
        spot=spot_context,
        futures=futures_context,
    )
    assert blocked.recommendations == ()
    assert "SPOT_WALLET_UNAVAILABLE_FOR_MANAGEMENT" in blocked.blockers
    assert "FUTURES_ACCOUNT_UNAVAILABLE_FOR_MANAGEMENT" in blocked.blockers

    with pytest.raises(ValueError, match="between zero and 100"):
        OpportunityReviewItem("bad", score=101)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        OpportunityReviewItem("bad", execution_allowed=True)


def test_investment_management_liquidity_fallback_uses_wallet_only() -> None:
    wallet = WalletSnapshot(
        captured_at=NOW,
        account_status="SPOT",
        can_trade=True,
        balances=(
            SpotBalance("ETH", Decimal("2"), Decimal("0")),
            SpotBalance("BTC", Decimal("0.01"), Decimal("0")),
        ),
        symbol="BTCUSDT",
    )
    spot_context = MarketManagementContext(
        "SPOT",
        "HOLD",
        "BULLISH_CONTINUATION",
        ("pullback-continuation",),
        (),
    )
    futures_context = MarketManagementContext(
        "USD_M_FUTURES",
        "HOLD",
        "NEUTRAL",
        (),
        (),
    )

    report = InvestmentManagementAssistant().review(
        symbol="BTCUSDT",
        spot_wallet=wallet,
        futures_account=None,
        spot=spot_context,
        futures=futures_context,
        portfolio_analytics=None,
    )

    assert "FUTURES_ACCOUNT_UNAVAILABLE_FOR_MANAGEMENT" in report.blockers
    assert any(
        item.category == "OPPORTUNITY_LIQUIDITY"
        and item.subject == "ETH->USDT_RESERVE"
        and "QUOTE_RESERVE_BELOW_TARGET" in item.blockers
        for item in report.recommendations
    )


class WalletReader:
    def __init__(self, account: object, orders: object) -> None:
        self.account_payload = account
        self.orders_payload = orders
        self.requested_symbols: list[str | None] = []

    def account(self) -> object:
        return self.account_payload

    def open_orders(self, symbol: str | None = None) -> object:
        self.requested_symbols.append(symbol)
        return self.orders_payload


def valid_wallet_account() -> dict[str, object]:
    return {
        "accountType": "SPOT",
        "canTrade": True,
        "balances": (
            {"asset": "USDT", "free": "10", "locked": "0"},
            {"asset": "BTC", "free": "0.01", "locked": "0"},
        ),
    }


def valid_open_order_payload() -> dict[str, object]:
    return {
        "orderId": 99,
        "clientOrderId": "client-99",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "status": "NEW",
        "price": "50000",
        "origQty": "0.01",
        "executedQty": "0.002",
    }


def test_wallet_and_open_order_validation_edges() -> None:
    reader = WalletReader(valid_wallet_account(), (valid_open_order_payload(),))
    snapshot = WalletSnapshotService(reader).capture(
        "btcusdt",
        NOW,
        account_wide=True,
    )
    assert snapshot.balance("usdt") == SpotBalance("USDT", Decimal("10"), Decimal("0"))
    assert snapshot.open_order_count == 1
    assert snapshot.open_orders[0].remaining_quantity == Decimal("0.008")
    assert reader.requested_symbols == [None]

    with pytest.raises(ValueError, match="Spot balance"):
        SpotBalance("", Decimal("0"), Decimal("0"))
    with pytest.raises(ValueError, match="Spot balance"):
        SpotBalance("BTC", Decimal("-1"), Decimal("0"))
    with pytest.raises(ValueError, match="timezone-aware"):
        WalletSnapshot(
            captured_at=datetime(2026, 7, 19, 12),
            account_status="SPOT",
            can_trade=True,
            balances=(),
            symbol="BTCUSDT",
        )
    with pytest.raises(ValueError, match="wallet identity"):
        WalletSnapshot(NOW, "", True, (), "BTCUSDT")
    with pytest.raises(ValueError, match="non-Spot order"):
        WalletSnapshot(
            NOW,
            "SPOT",
            True,
            (),
            "BTCUSDT",
            (
                AccountOpenOrder(
                    "USD_M_FUTURES",
                    "1",
                    "client",
                    "BTCUSDT",
                    "BUY",
                    "LIMIT",
                    "NEW",
                    Decimal("1"),
                    Decimal("1"),
                    Decimal("0"),
                ),
            ),
        )

    with pytest.raises(ValueError, match="symbol is required"):
        WalletSnapshotService(reader).capture(" ", NOW)
    with pytest.raises(ValueError, match="account must be an object"):
        WalletSnapshotService(WalletReader([], ())).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="balances must be an array"):
        WalletSnapshotService(
            WalletReader({"accountType": "SPOT", "canTrade": True, "balances": {}}, ())
        ).capture("BTCUSDT", NOW)
    duplicate = {
        "accountType": "SPOT",
        "canTrade": True,
        "balances": (
            {"asset": "BTC", "free": "0", "locked": "0"},
            {"asset": "BTC", "free": "1", "locked": "0"},
        ),
    }
    with pytest.raises(ValueError, match="unique assets"):
        WalletSnapshotService(WalletReader(duplicate, ())).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="balance must be an object"):
        WalletSnapshotService(
            WalletReader(
                {"accountType": "SPOT", "canTrade": True, "balances": (1,)},
                (),
            )
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="accountType must be text"):
        WalletSnapshotService(
            WalletReader({"accountType": "", "canTrade": True, "balances": ()}, ())
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="canTrade must be boolean"):
        WalletSnapshotService(
            WalletReader({"accountType": "SPOT", "canTrade": "yes", "balances": ()}, ())
        ).capture("BTCUSDT", NOW)
    with pytest.raises(ValueError, match="openOrders must be an array"):
        WalletSnapshotService(WalletReader(valid_wallet_account(), {})).capture(
            "BTCUSDT", NOW
        )
    with pytest.raises(ValueError, match="openOrder must be an object"):
        WalletSnapshotService(WalletReader(valid_wallet_account(), (1,))).capture(
            "BTCUSDT", NOW
        )

    with pytest.raises(ValueError, match="market is invalid"):
        AccountOpenOrder(
            "MARGIN",
            "1",
            "client",
            "BTCUSDT",
            "BUY",
            "LIMIT",
            "NEW",
            Decimal("1"),
            Decimal("1"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="identity is required"):
        AccountOpenOrder(
            "SPOT",
            "1",
            "",
            "BTCUSDT",
            "BUY",
            "LIMIT",
            "NEW",
            Decimal("1"),
            Decimal("1"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="side is invalid"):
        AccountOpenOrder(
            "SPOT",
            "1",
            "client",
            "BTCUSDT",
            "HOLD",
            "LIMIT",
            "NEW",
            Decimal("1"),
            Decimal("1"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="quantities are invalid"):
        AccountOpenOrder(
            "SPOT",
            "1",
            "client",
            "BTCUSDT",
            "BUY",
            "LIMIT",
            "NEW",
            Decimal("1"),
            Decimal("1"),
            Decimal("2"),
        )
    with pytest.raises(ValueError, match="orderId must be text-compatible"):
        normalize_open_order(
            {**valid_open_order_payload(), "orderId": True},
            market="SPOT",
        )
    with pytest.raises(ValueError, match="clientOrderId cannot be empty"):
        normalize_open_order(
            {**valid_open_order_payload(), "clientOrderId": " "},
            market="SPOT",
        )
    with pytest.raises(ValueError, match="price must be decimal-compatible"):
        normalize_open_order(
            {**valid_open_order_payload(), "price": object()},
            market="SPOT",
        )
    with pytest.raises(ValueError, match="price must be finite"):
        normalize_open_order(
            {**valid_open_order_payload(), "price": "NaN"},
            market="SPOT",
        )


def test_funding_plan_engine_all_sources_and_validation() -> None:
    engine = FundingPlanEngine(
        AssetPolicy(protected_assets=("BTC",), automatic_conversion_enabled=True)
    )
    plan = engine.build_plan(
        required_capital_usdt=Decimal("100"),
        free_quote_capital_usdt=Decimal("20"),
        locked_order_capital_usdt=Decimal("30"),
        convertible_assets_usdt={
            "ETH": Decimal("40"),
            "BTC": Decimal("50"),
            "ZERO": Decimal("0"),
        },
        transferable_capital_usdt=Decimal("60"),
    )
    actions = [proposal.action for proposal in plan.proposals]
    assert actions == [
        FundingAction.USE_FREE_STABLECOIN,
        FundingAction.REVIEW_LOCKED_ORDER,
        FundingAction.REQUEST_ASSET_CONVERSION,
        FundingAction.REQUEST_ASSET_CONVERSION,
        FundingAction.REQUEST_WALLET_TRANSFER,
    ]
    assert plan.proposals[0].approval_required is False
    assert plan.proposals[3].decision is FundingActionDecision.REJECTED
    assert plan.blockers == ("PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE",)
    assert plan.execution_allowed is False

    unavailable = FundingPlanEngine().build_plan(required_capital_usdt=Decimal("25"))
    assert unavailable.proposals[0].decision is FundingActionDecision.UNAVAILABLE
    with pytest.raises(ValueError, match="positive"):
        FundingPlanEngine().build_plan(required_capital_usdt=Decimal("0"))


def test_research_validation_success_and_sync_are_serialized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class Batch:
        symbol = "BTCUSDT"
        execution_allowed = False
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
        results: tuple[Any, ...] = ()

    class ValidationServiceStub:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run(self, symbol: str, timeframes: tuple[str, ...]) -> Batch:
            assert symbol == "ETHUSDT"
            assert timeframes == ("1h",)
            return Batch()

    monkeypatch.setattr(
        cli_research, "ResearchValidationService", ValidationServiceStub
    )
    settings = Settings(
        dataset_directory=tmp_path / "dataset",
        market_history_local_candles=False,
        validation_artifact_directory=tmp_path / "validation",
        timeframes=("1h",),
    )
    assert cli_research.run_validate_research(settings, "ethusdt") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "BTCUSDT"
    assert payload["results"] == []
    assert payload["execution_allowed"] is False

    class IngestorStub:
        @classmethod
        def with_network(cls, archive: object) -> IngestorStub:
            del archive
            return cls()

        def sync(
            self, symbol: str, timeframes: tuple[str, ...], *, as_of: object
        ) -> tuple[dict[str, object], ...]:
            assert symbol == "BTCUSDT"
            assert timeframes == ("1h",)
            return ({"timeframe": "1h", "rows": 2, "as_of": str(as_of)},)

    class RevisionBuilderStub:
        def __init__(self, root: Path) -> None:
            self.root = root

        def build(self, **kwargs: object) -> dict[str, object]:
            return {"revision_id": "rev-1", **kwargs}

        def write(self, revision: object) -> Path:
            del revision
            return self.root / "revision.json"

    monkeypatch.setattr(cli_research, "BinanceVisionIngestor", IngestorStub)
    monkeypatch.setattr(cli_research, "DatasetRevisionBuilder", RevisionBuilderStub)
    assert cli_research.run_sync_validation_data(settings, None, "2026-07-19") == 0
    sync_payload = json.loads(capsys.readouterr().out)
    assert sync_payload["symbol"] == "BTCUSDT"
    assert sync_payload["as_of_exclusive"] == "2026-07-19"
    assert sync_payload["execution_allowed"] is False

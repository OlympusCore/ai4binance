"""Read-only runtime command handlers."""

from __future__ import annotations

import json
from typing import cast

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import ReadOnlyRuntimeCycle, ResearchApplicationService
from ai4binance.config import Settings
from ai4binance.exchange import (
    BinancePrivateAccountReader,
    BinancePublicClient,
    BinanceUsdMPrivateAccountReader,
    PrivateCredentials,
    SignedReadOnlyRequestFactory,
    SignedUsdMReadOnlyRequestFactory,
    UrllibJsonTransport,
    UrllibPrivateJsonTransport,
)
from ai4binance.ops import (
    PrivateRuntimeStatusStore,
    RuntimeManagementLedger,
    RuntimeStatusStore,
    RuntimeSupervisor,
    SingleInstanceLease,
)
from ai4binance.outlook import MarketOutlookArtifactStore
from ai4binance.portfolio import (
    CostBasisService,
    FuturesAccountSnapshotService,
    PortfolioAnalyticsService,
    WalletSnapshotService,
)
from ai4binance.portfolio.risk_budget import PortfolioRiskPolicy
from ai4binance.reporting import to_primitive
from ai4binance.storage import JsonlAuditStore
from ai4binance.whale_fusion.derivatives import (
    BinanceUsdMClient,
    UsdMFuturesPublicTransport,
)

from .status import build_public_acquisition


def build_read_only_runtime(settings: Settings) -> ReadOnlyRuntimeCycle:
    """Build the resident wallet-first runtime without any write endpoint."""
    spot_wallet_service: WalletSnapshotService | None = None
    futures_account_service: FuturesAccountSnapshotService | None = None
    cost_basis_service: CostBasisService | None = None
    try:
        credentials = PrivateCredentials.from_environment_or_file(
            settings.private_credentials_file
        )
    except ValueError:
        credentials = None
    if credentials is not None:
        private_transport = UrllibPrivateJsonTransport(
            timeout_seconds=settings.request_timeout_seconds,
            max_attempts=settings.request_max_attempts,
            backoff_seconds=settings.request_backoff_seconds,
        )
        spot_reader = BinancePrivateAccountReader(
            SignedReadOnlyRequestFactory(credentials), private_transport
        )
        spot_wallet_service = WalletSnapshotService(spot_reader)
        cost_basis_service = CostBasisService(spot_reader)
        futures_account_service = FuturesAccountSnapshotService(
            BinanceUsdMPrivateAccountReader(
                SignedUsdMReadOnlyRequestFactory(credentials), private_transport
            )
        )
    analytics_transport = UrllibJsonTransport(
        base_url=settings.public_api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
        max_attempts=settings.request_max_attempts,
        backoff_seconds=settings.request_backoff_seconds,
    )
    return ReadOnlyRuntimeCycle(
        symbol=settings.symbol,
        timeframes=settings.timeframes,
        spot_acquirer=build_public_acquisition(settings),
        spot_wallet_service=spot_wallet_service,
        futures_account_service=futures_account_service,
        derivatives_collector=BinanceUsdMClient(
            UsdMFuturesPublicTransport(
                timeout_seconds=settings.request_timeout_seconds,
                max_attempts=settings.request_max_attempts,
                backoff_seconds=settings.request_backoff_seconds,
            )
        ),
        analytics_service=PortfolioAnalyticsService(
            BinancePublicClient(analytics_transport),
            concentration_limit=settings.portfolio_concentration_limit,
            risk_policy=PortfolioRiskPolicy(
                maximum_gross_usdt=settings.portfolio_maximum_gross_usdt,
                maximum_symbol_usdt=settings.portfolio_maximum_symbol_usdt,
                maximum_correlation_group_usdt=(
                    settings.portfolio_maximum_correlation_group_usdt
                ),
                maximum_strategy_usdt=settings.portfolio_maximum_strategy_usdt,
            ),
        ),
        cost_basis_service=cost_basis_service,
        research_service=ResearchApplicationService(
            orchestrator=EnterpriseOrchestrator(
                minimum_candles=settings.minimum_closed_candles
            ),
            audit_store=JsonlAuditStore(
                settings.audit_directory / "runtime_research_events.jsonl"
            ),
            outlook_store=MarketOutlookArtifactStore(
                settings.evidence_artifact_directory
                / "market-outlook"
                / "runtime-state.json"
            ),
        ),
        account_wide_monitoring=True,
    )


def run_runtime_command(
    command: str,
    settings: Settings,
    *,
    max_cycles: int | None,
) -> int:
    runtime = build_read_only_runtime(settings)
    if command == "runtime-once":
        report = runtime.run()
        RuntimeStatusStore(settings.runtime_state_path).save(report)
        PrivateRuntimeStatusStore(
            settings.private_runtime_state_path,
            settings.private_runtime_ledger_path,
            settings.binance_accounting_directory,
        ).save(report)
        RuntimeManagementLedger(settings.management_ledger_path).append(report)
        print(json.dumps(runtime_payload(report), ensure_ascii=False, sort_keys=True))
        return 0 if report.state.value == "READY" else 2
    lease = SingleInstanceLease(settings.runtime_state_path.with_suffix(".lock"))
    try:
        with lease:
            RuntimeSupervisor(
                cycle=runtime.run,
                store=RuntimeStatusStore(settings.runtime_state_path),
                interval_seconds=settings.runtime_cycle_interval_seconds,
                private_store=PrivateRuntimeStatusStore(
                    settings.private_runtime_state_path,
                    settings.private_runtime_ledger_path,
                    settings.binance_accounting_directory,
                ),
                management_ledger=RuntimeManagementLedger(
                    settings.management_ledger_path
                ),
            ).run(max_cycles=max_cycles)
        return 0
    except (KeyboardInterrupt, RuntimeError):
        return 2


def runtime_payload(report: object) -> dict[str, object]:
    """Return a secret-safe summary without wallet balances."""
    primitive = cast(dict[str, object], to_primitive(report))
    for sensitive in ("spot_wallet", "futures_account", "spot_research"):
        primitive.pop(sensitive, None)
    return primitive

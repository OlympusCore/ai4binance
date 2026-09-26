"""Wallet-first dual-market advisory cycle with no execution authority."""
# ruff: noqa: ANN401

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from ai4binance.domain import Action

_PORTFOLIO_COST_BASIS_ASSET_LIMIT = 50
_PAR_USDT_ASSETS = frozenset({"USDT", "FDUSD", "USDC"})


class RuntimeState(StrEnum):
    STARTING = "STARTING"
    WALLET_PREFLIGHT = "WALLET_PREFLIGHT"
    MARKET_PREFLIGHT = "MARKET_PREFLIGHT"
    READY = "READY"
    DEGRADED = "DEGRADED"


class SnapshotAcquirer(Protocol):
    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> Any: ...


class MarketSnapshotLike(Protocol):
    symbol: str


class BalanceLike(Protocol):
    free: Decimal
    locked: Decimal


class WalletSnapshotLike(Protocol):
    can_trade: bool

    def balance(self, asset: str) -> BalanceLike | None: ...


class FuturesAccountSnapshotLike(Protocol):
    can_trade: bool


class PortfolioAnalyticsLike(Protocol):
    blockers: tuple[str, ...]


class CostBasisReportLike(Protocol):
    base_asset: str
    average_cost_quote: Decimal | None
    quote_asset: str
    blockers: tuple[str, ...]


class WalletSnapshotServiceLike(Protocol):
    def capture(
        self,
        symbol: str,
        captured_at: datetime,
        *,
        account_wide: bool = False,
    ) -> Any: ...


class FuturesAccountSnapshotServiceLike(Protocol):
    def capture(
        self,
        symbol: str,
        captured_at: datetime,
        *,
        account_wide: bool = False,
    ) -> Any: ...


class PortfolioAnalyticsServiceLike(Protocol):
    def evaluate(
        self,
        wallet: WalletSnapshotLike,
        *,
        average_costs_usdt: Mapping[str, Decimal] | None = None,
    ) -> Any: ...


class CostBasisServiceLike(Protocol):
    def evaluate(self, symbol: str, wallet_quantity: Decimal) -> Any: ...


class InvestmentManagementReportLike(Protocol):
    recommendations: tuple[object, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool


class InvestmentManager(Protocol):
    def review(
        self,
        *,
        symbol: str,
        spot_wallet: WalletSnapshotLike | None,
        futures_account: FuturesAccountSnapshotLike | None,
        spot: MarketAdvisory,
        futures: MarketAdvisory,
        portfolio_analytics: PortfolioAnalyticsLike | None = None,
    ) -> Any: ...


class FuturesAdvisor(Protocol):
    def build(self, snapshot: Any) -> MarketAdvisory: ...


@dataclass(frozen=True, slots=True)
class RuntimeOpportunityReviewItem:
    setup_name: str
    timeframe: str
    direction: str
    status: str
    promotion_status: str
    setup_tier: str
    score: float
    confidence: float
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketAdvisory:
    market: str
    action: str
    bias: str
    setup_radar: tuple[str, ...]
    blockers: tuple[str, ...]
    wallet_status: str
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    opportunity_radar: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if self.market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError("unsupported advisory market")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("market advisory cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class DualMarketAdvisoryReport:
    cycle_id: str
    symbol: str
    created_at: datetime
    state: RuntimeState
    spot: MarketAdvisory
    futures: MarketAdvisory
    blockers: tuple[str, ...]
    spot_wallet: Any | None = field(default=None, repr=False)
    futures_account: Any | None = field(default=None, repr=False)
    spot_research: Any | None = field(default=None, repr=False)
    investment_management: Any | None = None
    portfolio_analytics: Any | None = None
    cost_basis: Any | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("runtime report timestamp must be timezone-aware")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("runtime report cannot grant execution authority")
        if self.state is RuntimeState.READY and self.blockers:
            raise ValueError("ready runtime report cannot contain blockers")


@dataclass(frozen=True, slots=True)
class ReadOnlyRuntimeCycle:
    """Run wallet preflight before any market advisory calculation."""

    symbol: str
    timeframes: tuple[str, ...]
    spot_acquirer: SnapshotAcquirer
    spot_wallet_service: WalletSnapshotServiceLike | None
    futures_account_service: FuturesAccountSnapshotServiceLike | None
    futures_advisor: FuturesAdvisor
    research_service: Any
    investment_manager: Any | None = None
    analytics_service: Any | None = None
    cost_basis_service: Any | None = None
    account_wide_monitoring: bool = False

    def run(self, now: datetime | None = None) -> DualMarketAdvisoryReport:
        created_at = now or datetime.now(UTC)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("runtime cycle timestamp must be timezone-aware")
        symbol = self.symbol.strip().upper()
        cycle_id = f"runtime-{symbol}-{int(created_at.timestamp() * 1000)}"
        spot_preflight: list[str] = []
        futures_preflight: list[str] = []
        spot_wallet = self._spot_wallet(symbol, created_at, spot_preflight)
        futures_account = self._futures_account(symbol, created_at, futures_preflight)
        blockers = [*spot_preflight, *futures_preflight]
        cost_basis = self._cost_basis(symbol, spot_wallet, blockers)
        portfolio_average_costs = self._portfolio_average_costs(
            spot_wallet,
            cost_basis,
            blockers,
        )
        portfolio_analytics = self._portfolio_analytics(
            spot_wallet,
            blockers,
            portfolio_average_costs,
        )
        spot_ready = spot_wallet is not None and not spot_preflight
        futures_ready = futures_account is not None and not futures_preflight
        if not spot_ready and not futures_ready:
            return self._blocked_report(
                cycle_id,
                symbol,
                created_at,
                blockers,
                spot_wallet,
                futures_account,
                portfolio_analytics,
                cost_basis,
            )

        try:
            snapshot = self.spot_acquirer.acquire(symbol, self.timeframes)
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("SPOT_MARKET_PREFLIGHT_FAILED")
            return self._blocked_report(
                cycle_id,
                symbol,
                created_at,
                blockers,
                spot_wallet,
                futures_account,
                portfolio_analytics,
                cost_basis,
            )

        spot_research: Any | None = None
        if spot_ready:
            try:
                spot_research = self.research_service.run(snapshot, wallet=spot_wallet)
            except (OSError, RuntimeError, TypeError, ValueError):
                spot_preflight.append("SPOT_MARKET_PREFLIGHT_FAILED")
                blockers.append("SPOT_MARKET_PREFLIGHT_FAILED")
                spot = self._unavailable_advisory("SPOT", spot_preflight)
            else:
                spot_signal = spot_research.analysis.final_decision
                spot_action = (
                    spot_signal.action.value
                    if spot_signal is not None
                    else Action.NO_TRADE.value
                )
                spot_blockers = tuple(
                    dict.fromkeys(
                        (
                            *(spot_signal.blockers if spot_signal is not None else ()),
                            *spot_research.analysis.blockers,
                        )
                    )
                )
                opportunity_radar = self._spot_opportunity_radar(spot_research)
                setup_radar = tuple(
                    dict.fromkeys(
                        (
                            *(item.setup_name for item in opportunity_radar),
                            *(
                                item.setup_name
                                for item in spot_research.analysis.candidate_setups
                            ),
                        )
                    )
                )
                spot = MarketAdvisory(
                    market="SPOT",
                    action=spot_action,
                    bias=spot_research.market_outlook.pro_trend_direction.value,
                    setup_radar=setup_radar,
                    blockers=spot_blockers,
                    wallet_status="READY",
                    opportunity_radar=opportunity_radar,
                )
        else:
            spot = self._unavailable_advisory("SPOT", spot_preflight)

        if futures_ready:
            futures = self._futures_advisory(snapshot)
            blockers.extend(futures.blockers)
        else:
            futures = self._unavailable_advisory("USD_M_FUTURES", futures_preflight)
        investment_management = self._investment_management(
            symbol,
            spot_wallet,
            futures_account,
            spot,
            futures,
            portfolio_analytics,
        )
        state = RuntimeState.READY if not blockers else RuntimeState.DEGRADED
        return DualMarketAdvisoryReport(
            cycle_id=cycle_id,
            symbol=symbol,
            created_at=created_at,
            state=state,
            spot=spot,
            futures=futures,
            blockers=tuple(dict.fromkeys(blockers)),
            spot_wallet=spot_wallet,
            futures_account=futures_account,
            spot_research=spot_research,
            investment_management=investment_management,
            portfolio_analytics=portfolio_analytics,
            cost_basis=cost_basis,
        )

    def _portfolio_analytics(
        self,
        wallet: Any | None,
        blockers: list[str],
        average_costs_usdt: Mapping[str, Decimal] | None,
    ) -> Any | None:
        if wallet is None or self.analytics_service is None:
            return None
        try:
            analytics = self.analytics_service.evaluate(
                wallet,
                average_costs_usdt=average_costs_usdt,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("PORTFOLIO_ANALYTICS_FAILED")
            return None
        blockers.extend(analytics.blockers)
        return analytics

    def _cost_basis(
        self,
        symbol: str,
        wallet: Any | None,
        blockers: list[str],
    ) -> Any | None:
        if wallet is None or self.cost_basis_service is None:
            return None
        base_asset = symbol.removesuffix("USDT") or symbol
        balance = wallet.balance(base_asset)
        if balance is None:
            return None
        wallet_quantity = balance.free + balance.locked
        if wallet_quantity <= Decimal("0"):
            return None
        try:
            report = self.cost_basis_service.evaluate(symbol, wallet_quantity)
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("COST_BASIS_RECONCILIATION_FAILED")
            return None
        blockers.extend(report.blockers)
        return report

    def _portfolio_average_costs(
        self,
        wallet: Any | None,
        selected_cost_basis: Any | None,
        blockers: list[str],
    ) -> Mapping[str, Decimal] | None:
        if wallet is None or self.cost_basis_service is None:
            return None
        costs: dict[str, Decimal] = {}
        evaluated_assets: set[str] = set()
        if selected_cost_basis is not None:
            evaluated_assets.add(selected_cost_basis.base_asset)
            if (
                selected_cost_basis.average_cost_quote is not None
                and not selected_cost_basis.blockers
                and selected_cost_basis.quote_asset == "USDT"
            ):
                costs[selected_cost_basis.base_asset] = (
                    selected_cost_basis.average_cost_quote
                )
        balances = tuple(
            sorted(
                (
                    balance
                    for balance in wallet.balances
                    if balance.asset not in _PAR_USDT_ASSETS
                    and balance.free + balance.locked > Decimal("0")
                ),
                key=lambda balance: balance.asset,
            )
        )
        if len(balances) > _PORTFOLIO_COST_BASIS_ASSET_LIMIT:
            blockers.append("PORTFOLIO_COST_BASIS_SCOPE_EXCEEDED")
        for balance in balances[:_PORTFOLIO_COST_BASIS_ASSET_LIMIT]:
            if balance.asset in evaluated_assets:
                continue
            evaluated_assets.add(balance.asset)
            try:
                report = self.cost_basis_service.evaluate(
                    f"{balance.asset}USDT",
                    balance.free + balance.locked,
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                blockers.append("COST_BASIS_RECONCILIATION_FAILED")
                continue
            blockers.extend(report.blockers)
            if (
                report.average_cost_quote is not None
                and not report.blockers
                and report.quote_asset == "USDT"
            ):
                costs[report.base_asset] = report.average_cost_quote
        return costs or None

    @staticmethod
    def _unavailable_advisory(market: str, blockers: list[str]) -> MarketAdvisory:
        return MarketAdvisory(
            market=market,
            action=Action.NO_TRADE.value,
            bias="UNKNOWN",
            setup_radar=(),
            blockers=tuple(dict.fromkeys(blockers)),
            wallet_status="BLOCKED",
        )

    def _investment_management(
        self,
        symbol: str,
        spot_wallet: Any | None,
        futures_account: Any | None,
        spot: MarketAdvisory,
        futures: MarketAdvisory,
        portfolio_analytics: Any | None = None,
    ) -> Any | None:
        if self.investment_manager is None:
            return None
        return self.investment_manager.review(
            symbol=symbol,
            spot_wallet=spot_wallet,
            futures_account=futures_account,
            spot=spot,
            futures=futures,
            portfolio_analytics=portfolio_analytics,
        )

    @staticmethod
    def _spot_opportunity_radar(
        workflow: Any,
    ) -> tuple[RuntimeOpportunityReviewItem, ...]:
        return tuple(
            RuntimeOpportunityReviewItem(
                setup_name=item.setup_name,
                timeframe=item.timeframe,
                direction=item.direction.value,
                status=item.status,
                promotion_status=item.promotion_status,
                setup_tier=item.setup_tier.value,
                score=item.score,
                confidence=item.confidence,
                blockers=item.blockers,
            )
            for item in workflow.market_outlook.setups_on_radar
        )

    def _spot_wallet(
        self, symbol: str, created_at: datetime, blockers: list[str]
    ) -> Any | None:
        if self.spot_wallet_service is None:
            blockers.append("SPOT_WALLET_SERVICE_UNAVAILABLE")
            return None
        try:
            wallet = self.spot_wallet_service.capture(
                symbol,
                created_at,
                account_wide=self.account_wide_monitoring,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("SPOT_WALLET_PREFLIGHT_FAILED")
            return None
        if not wallet.can_trade:
            blockers.append("SPOT_ACCOUNT_TRADING_DISABLED")
        return wallet

    def _futures_account(
        self, symbol: str, created_at: datetime, blockers: list[str]
    ) -> Any | None:
        if self.futures_account_service is None:
            blockers.append("FUTURES_ACCOUNT_SERVICE_UNAVAILABLE")
            return None
        try:
            account = self.futures_account_service.capture(
                symbol,
                created_at,
                account_wide=self.account_wide_monitoring,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("FUTURES_ACCOUNT_PREFLIGHT_FAILED")
            return None
        if not account.can_trade:
            blockers.append("FUTURES_ACCOUNT_TRADING_DISABLED")
        return account

    def _futures_advisory(self, snapshot: Any) -> MarketAdvisory:
        try:
            return self.futures_advisor.build(snapshot)
        except (OSError, RuntimeError, TypeError, ValueError):
            return MarketAdvisory(
                market="USD_M_FUTURES",
                action=Action.NO_TRADE.value,
                bias="UNKNOWN",
                setup_radar=(),
                blockers=("FUTURES_PUBLIC_DATA_FAILED",),
                wallet_status="READY",
            )

    def _blocked_report(
        self,
        cycle_id: str,
        symbol: str,
        created_at: datetime,
        blockers: list[str],
        spot_wallet: Any | None,
        futures_account: Any | None,
        portfolio_analytics: Any | None = None,
        cost_basis: Any | None = None,
    ) -> DualMarketAdvisoryReport:
        unique = tuple(dict.fromkeys(blockers))
        spot = MarketAdvisory("SPOT", "NO_TRADE", "UNKNOWN", (), unique, "BLOCKED")
        futures = MarketAdvisory(
            "USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), unique, "BLOCKED"
        )
        return DualMarketAdvisoryReport(
            cycle_id=cycle_id,
            symbol=symbol,
            created_at=created_at,
            state=RuntimeState.DEGRADED,
            spot=spot,
            futures=futures,
            blockers=unique,
            spot_wallet=spot_wallet,
            futures_account=futures_account,
            investment_management=self._investment_management(
                symbol,
                spot_wallet,
                futures_account,
                spot,
                futures,
                portfolio_analytics,
            ),
            portfolio_analytics=portfolio_analytics,
            cost_basis=cost_basis,
        )

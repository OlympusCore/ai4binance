"""Wallet-first dual-market advisory cycle with no execution authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from ai4binance.application.research import (
    ResearchApplicationService,
    ResearchWorkflowResult,
)
from ai4binance.domain import Action
from ai4binance.portfolio import (
    CostBasisReport,
    CostBasisService,
    FuturesAccountSnapshot,
    FuturesAccountSnapshotService,
    InvestmentManagementAssistant,
    InvestmentManagementReport,
    MarketManagementContext,
    OpportunityReviewItem,
    PortfolioAnalytics,
    PortfolioAnalyticsService,
    WalletSnapshot,
    WalletSnapshotService,
)
from ai4binance.schemas import MarketSnapshot
from ai4binance.whale_fusion.features import DerivativesFeatureEngine
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    PriceOiRegime,
)


class RuntimeState(StrEnum):
    STARTING = "STARTING"
    WALLET_PREFLIGHT = "WALLET_PREFLIGHT"
    MARKET_PREFLIGHT = "MARKET_PREFLIGHT"
    READY = "READY"
    DEGRADED = "DEGRADED"


class SnapshotAcquirer(Protocol):
    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot: ...


class DerivativesCollector(Protocol):
    def collect(
        self, symbol: str, period: str = "1h", limit: int = 100
    ) -> DerivativesDataset: ...


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
    opportunity_radar: tuple[OpportunityReviewItem, ...] = ()

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
    spot_wallet: WalletSnapshot | None = field(default=None, repr=False)
    futures_account: FuturesAccountSnapshot | None = field(default=None, repr=False)
    spot_research: ResearchWorkflowResult | None = field(default=None, repr=False)
    investment_management: InvestmentManagementReport | None = None
    portfolio_analytics: PortfolioAnalytics | None = None
    cost_basis: CostBasisReport | None = None
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
    spot_wallet_service: WalletSnapshotService | None
    futures_account_service: FuturesAccountSnapshotService | None
    derivatives_collector: DerivativesCollector
    research_service: ResearchApplicationService = field(
        default_factory=ResearchApplicationService
    )
    feature_engine: DerivativesFeatureEngine = field(
        default_factory=DerivativesFeatureEngine
    )
    investment_assistant: InvestmentManagementAssistant = field(
        default_factory=InvestmentManagementAssistant
    )
    analytics_service: PortfolioAnalyticsService | None = None
    cost_basis_service: CostBasisService | None = None
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
        portfolio_analytics = self._portfolio_analytics(
            spot_wallet, blockers, cost_basis
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

        spot_research: ResearchWorkflowResult | None = None
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
        wallet: WalletSnapshot | None,
        blockers: list[str],
        cost_basis: CostBasisReport | None,
    ) -> PortfolioAnalytics | None:
        if wallet is None or self.analytics_service is None:
            return None
        try:
            costs = (
                {cost_basis.base_asset: cost_basis.average_cost_quote}
                if cost_basis is not None
                and cost_basis.average_cost_quote is not None
                and cost_basis.quote_asset == "USDT"
                else None
            )
            analytics = self.analytics_service.evaluate(
                wallet,
                average_costs_usdt=costs,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("PORTFOLIO_ANALYTICS_FAILED")
            return None
        blockers.extend(analytics.blockers)
        return analytics

    def _cost_basis(
        self,
        symbol: str,
        wallet: WalletSnapshot | None,
        blockers: list[str],
    ) -> CostBasisReport | None:
        if wallet is None or self.cost_basis_service is None:
            return None
        base_asset = symbol.removesuffix("USDT") or symbol
        balance = wallet.balance(base_asset)
        wallet_quantity = (
            balance.free + balance.locked if balance is not None else Decimal("0")
        )
        try:
            report = self.cost_basis_service.evaluate(symbol, wallet_quantity)
        except (OSError, RuntimeError, TypeError, ValueError):
            blockers.append("COST_BASIS_RECONCILIATION_FAILED")
            return None
        blockers.extend(report.blockers)
        return report

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
        spot_wallet: WalletSnapshot | None,
        futures_account: FuturesAccountSnapshot | None,
        spot: MarketAdvisory,
        futures: MarketAdvisory,
        portfolio_analytics: PortfolioAnalytics | None = None,
    ) -> InvestmentManagementReport:
        return self.investment_assistant.review(
            symbol=symbol,
            spot_wallet=spot_wallet,
            futures_account=futures_account,
            spot=MarketManagementContext(
                spot.market,
                spot.action,
                spot.bias,
                spot.setup_radar,
                spot.blockers,
                spot.opportunity_radar,
            ),
            futures=MarketManagementContext(
                futures.market,
                futures.action,
                futures.bias,
                futures.setup_radar,
                futures.blockers,
                futures.opportunity_radar,
            ),
            portfolio_analytics=portfolio_analytics,
        )

    @staticmethod
    def _spot_opportunity_radar(
        workflow: ResearchWorkflowResult,
    ) -> tuple[OpportunityReviewItem, ...]:
        return tuple(
            OpportunityReviewItem(
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
    ) -> WalletSnapshot | None:
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
    ) -> FuturesAccountSnapshot | None:
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

    def _futures_advisory(self, snapshot: MarketSnapshot) -> MarketAdvisory:
        try:
            dataset = self.derivatives_collector.collect(snapshot.symbol, "1h", 100)
            oi_count = len(dataset.values(DerivativesMetric.OPEN_INTEREST))
            candles = snapshot.ohlcv_by_timeframe.get("1h", ())
            prices = tuple(Decimal(str(candle.close)) for candle in candles[-oi_count:])
            features = self.feature_engine.compute(dataset, prices)
        except (OSError, RuntimeError, TypeError, ValueError):
            return MarketAdvisory(
                market="USD_M_FUTURES",
                action=Action.NO_TRADE.value,
                bias="UNKNOWN",
                setup_radar=(),
                blockers=("FUTURES_PUBLIC_DATA_FAILED",),
                wallet_status="READY",
            )
        bias = {
            PriceOiRegime.NEW_LONG_PARTICIPATION: "BULLISH",
            PriceOiRegime.SHORT_COVERING: "BULLISH_CAUTION",
            PriceOiRegime.NEW_SHORT_PRESSURE: "BEARISH",
            PriceOiRegime.DELEVERAGING: "BEARISH_CAUTION",
            PriceOiRegime.FLAT_OR_MIXED: "NEUTRAL",
        }[features.price_oi_regime]
        blockers = tuple(
            dict.fromkeys((*features.blockers, "FUTURES_OOS_NOT_APPROVED"))
        )
        return MarketAdvisory(
            market="USD_M_FUTURES",
            action=Action.NO_TRADE.value,
            bias=bias,
            setup_radar=(features.price_oi_regime.value,),
            blockers=blockers,
            wallet_status="READY",
            opportunity_radar=(
                OpportunityReviewItem(
                    setup_name=features.price_oi_regime.value,
                    timeframe="1h",
                    direction=bias,
                    status="FUTURES_RESEARCH_RADAR",
                    promotion_status="RESEARCH_ONLY",
                    setup_tier="C",
                    score=50.0,
                    confidence=0.35,
                    blockers=blockers,
                ),
            ),
        )

    def _blocked_report(
        self,
        cycle_id: str,
        symbol: str,
        created_at: datetime,
        blockers: list[str],
        spot_wallet: WalletSnapshot | None,
        futures_account: FuturesAccountSnapshot | None,
        portfolio_analytics: PortfolioAnalytics | None = None,
        cost_basis: CostBasisReport | None = None,
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

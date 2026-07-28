"""Proposal-only Spot/Futures investment management recommendations."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from ai4binance.portfolio.analytics import PortfolioAnalytics
from ai4binance.portfolio.futures import FuturesAccountSnapshot
from ai4binance.portfolio.holding_opportunity import (
    HoldingOpportunityAction,
    HoldingOpportunityReport,
)
from ai4binance.portfolio.inventory_rotation import (
    InventoryRotationAction,
    InventoryRotationProposal,
)
from ai4binance.portfolio.rebalancing import RebalanceAction, RebalanceProposal
from ai4binance.portfolio.wallet import WalletSnapshot

ZERO = Decimal("0")
ONE = Decimal("1")
QUOTE_RESERVE_ASSETS = frozenset({"USDT", "USDC", "FDUSD"})


class ManagementAction(StrEnum):
    NO_ACTION = "NO_ACTION"
    HOLD_REVIEW = "HOLD_REVIEW"
    REDUCE_RISK_REVIEW = "REDUCE_RISK_REVIEW"
    OPEN_ORDER_REVIEW = "OPEN_ORDER_REVIEW"
    PREPARE_LIQUIDITY_REVIEW = "PREPARE_LIQUIDITY_REVIEW"
    WATCHLIST = "WATCHLIST"


@dataclass(frozen=True, slots=True)
class OpportunityReviewItem:
    """Visible growth radar item that never grants execution authority."""

    setup_name: str
    timeframe: str = "UNKNOWN"
    direction: str = "UNKNOWN"
    status: str = "WATCHLIST"
    promotion_status: str = "RESEARCH_ONLY"
    setup_tier: str = "NO_TRADE"
    score: float = 0.0
    confidence: float = 0.0
    target_risk_reward: Decimal = Decimal("2")
    stretch_risk_reward: Decimal = Decimal("3")
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "setup_name",
            "timeframe",
            "direction",
            "status",
            "promotion_status",
            "setup_tier",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if not isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise ValueError("opportunity score must be between zero and 100")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("opportunity confidence must be between zero and one")
        if self.target_risk_reward <= ZERO:
            raise ValueError("target_risk_reward must be positive")
        if self.stretch_risk_reward < self.target_risk_reward:
            raise ValueError("stretch_risk_reward cannot be below target")
        if self.execution_allowed:
            raise ValueError("opportunity review item cannot authorize execution")


@dataclass(frozen=True, slots=True)
class MarketManagementContext:
    market: str
    action: str
    bias: str
    setup_radar: tuple[str, ...]
    blockers: tuple[str, ...]
    opportunity_radar: tuple[OpportunityReviewItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ManagementRecommendation:
    category: str
    market: str
    subject: str
    action: ManagementAction
    rationale: str
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if any(
            not value.strip() for value in (self.category, self.market, self.subject)
        ):
            raise ValueError("management recommendation identity is required")
        if not self.rationale.strip():
            raise ValueError("management recommendation rationale is required")
        if self.execution_allowed:
            raise ValueError("management recommendation cannot authorize execution")


@dataclass(frozen=True, slots=True)
class InvestmentManagementReport:
    symbol: str
    recommendations: tuple[ManagementRecommendation, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("investment management symbol is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("investment management cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class GrowthOpportunityPolicy:
    """Growth-first advisory thresholds without execution authority."""

    minimum_quote_reserve_ratio: Decimal = Decimal("0.10")
    maximum_liquidity_release_ratio: Decimal = Decimal("0.15")

    def __post_init__(self) -> None:
        if not ZERO <= self.minimum_quote_reserve_ratio <= ONE:
            raise ValueError("minimum_quote_reserve_ratio must be between zero and one")
        if not ZERO < self.maximum_liquidity_release_ratio <= ONE:
            raise ValueError(
                "maximum_liquidity_release_ratio must be between zero and one"
            )


@dataclass(frozen=True, slots=True)
class InvestmentManagementAssistant:
    """Review inventory, positions, orders and opportunities without mutation."""

    growth_policy: GrowthOpportunityPolicy = field(
        default_factory=GrowthOpportunityPolicy
    )

    def review(
        self,
        *,
        symbol: str,
        spot_wallet: WalletSnapshot | None,
        futures_account: FuturesAccountSnapshot | None,
        spot: MarketManagementContext,
        futures: MarketManagementContext,
        portfolio_analytics: PortfolioAnalytics | None = None,
        rebalance_proposal: RebalanceProposal | None = None,
        inventory_rotation_proposal: InventoryRotationProposal | None = None,
        holding_opportunity_report: HoldingOpportunityReport | None = None,
    ) -> InvestmentManagementReport:
        normalized = symbol.strip().upper()
        blockers: list[str] = []
        recommendations: list[ManagementRecommendation] = []
        if spot_wallet is None:
            blockers.append("SPOT_WALLET_UNAVAILABLE_FOR_MANAGEMENT")
        if futures_account is None:
            blockers.append("FUTURES_ACCOUNT_UNAVAILABLE_FOR_MANAGEMENT")
        if spot_wallet is not None:
            self._spot_inventory(normalized, spot_wallet, spot, recommendations)
            self._open_orders(normalized, spot_wallet, spot, recommendations)
            self._opportunities(spot, recommendations)
            self._opportunity_liquidity(
                spot_wallet, spot, portfolio_analytics, recommendations
            )
        if futures_account is not None:
            self._futures_positions(
                normalized, futures_account, futures, recommendations
            )
            self._open_orders(normalized, futures_account, futures, recommendations)
            self._opportunities(futures, recommendations)
        if portfolio_analytics is not None:
            self._portfolio_risk(portfolio_analytics, recommendations)
        if rebalance_proposal is not None:
            self._rebalance(rebalance_proposal, recommendations)
        if inventory_rotation_proposal is not None:
            self._inventory_rotation(inventory_rotation_proposal, recommendations)
        if holding_opportunity_report is not None:
            self._holding_opportunity(holding_opportunity_report, recommendations)
        combined_blockers = tuple(
            dict.fromkeys(
                (
                    *blockers,
                    *spot.blockers,
                    *futures.blockers,
                    *(
                        portfolio_analytics.blockers
                        if portfolio_analytics is not None
                        else ()
                    ),
                    *(
                        inventory_rotation_proposal.blockers
                        if inventory_rotation_proposal is not None
                        else ()
                    ),
                    *(
                        rebalance_proposal.blockers
                        if rebalance_proposal is not None
                        else ()
                    ),
                    *(
                        holding_opportunity_report.blockers
                        if holding_opportunity_report is not None
                        else ()
                    ),
                )
            )
        )
        return InvestmentManagementReport(
            normalized,
            tuple(recommendations),
            combined_blockers,
        )

    @staticmethod
    def _holding_opportunity(
        report: HoldingOpportunityReport,
        output: list[ManagementRecommendation],
    ) -> None:
        action_map = {
            HoldingOpportunityAction.HOLD_REVIEW: ManagementAction.HOLD_REVIEW,
            HoldingOpportunityAction.USE_LIQUID_CAPITAL_REVIEW: (
                ManagementAction.WATCHLIST
            ),
            HoldingOpportunityAction.REDUCE_TO_LIQUIDITY_REVIEW: (
                ManagementAction.REDUCE_RISK_REVIEW
            ),
            HoldingOpportunityAction.ROTATE_TO_SPOT_REVIEW: (
                ManagementAction.REDUCE_RISK_REVIEW
            ),
            HoldingOpportunityAction.ROTATE_TO_FUTURES_REVIEW: (
                ManagementAction.REDUCE_RISK_REVIEW
            ),
            HoldingOpportunityAction.WATCHLIST: ManagementAction.WATCHLIST,
            HoldingOpportunityAction.BLOCKED: ManagementAction.HOLD_REVIEW,
        }
        for item in report.advice:
            subject = (
                f"{item.subject}->{item.target_symbol}"
                if item.target_symbol is not None
                else item.subject
            )
            output.append(
                ManagementRecommendation(
                    "HOLDING_OPPORTUNITY_REVIEW",
                    item.market.value if item.market is not None else "PORTFOLIO",
                    subject,
                    action_map[item.action],
                    item.rationale,
                    item.blockers,
                )
            )

    @staticmethod
    def _inventory_rotation(
        proposal: InventoryRotationProposal,
        output: list[ManagementRecommendation],
    ) -> None:
        action = (
            ManagementAction.REDUCE_RISK_REVIEW
            if proposal.action is InventoryRotationAction.SELL
            else ManagementAction.WATCHLIST
            if proposal.action is InventoryRotationAction.REBUY
            else ManagementAction.HOLD_REVIEW
        )
        output.append(
            ManagementRecommendation(
                "INVENTORY_ROTATION",
                "SPOT",
                proposal.next_state.cycle_id,
                action,
                "Inventory rotation is proposal-only and requires a manually "
                "confirmed fill before its state can advance.",
                proposal.blockers,
            )
        )

    @staticmethod
    def _rebalance(
        proposal: RebalanceProposal,
        output: list[ManagementRecommendation],
    ) -> None:
        action = (
            ManagementAction.REDUCE_RISK_REVIEW
            if proposal.action is RebalanceAction.SELL
            else ManagementAction.WATCHLIST
            if proposal.action is RebalanceAction.BUY
            else ManagementAction.HOLD_REVIEW
        )
        output.append(
            ManagementRecommendation(
                "PORTFOLIO_REBALANCE",
                "SPOT",
                f"STAGE_{proposal.stage}",
                action,
                "Fee-aware immutable rebalance proposal requires manual review; "
                "wallet state was not changed.",
                proposal.blockers,
            )
        )

    @staticmethod
    def _portfolio_risk(
        analytics: PortfolioAnalytics,
        output: list[ManagementRecommendation],
    ) -> None:
        if analytics.largest_asset is None or not analytics.blockers:
            return
        concentrated = "PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED" in analytics.blockers
        output.append(
            ManagementRecommendation(
                "PORTFOLIO_RISK",
                "SPOT",
                f"{analytics.largest_asset}_CONCENTRATION",
                (
                    ManagementAction.REDUCE_RISK_REVIEW
                    if concentrated
                    else ManagementAction.HOLD_REVIEW
                ),
                (
                    "Largest portfolio weight exceeds the configured concentration "
                    "limit; calculate a manual, fee-aware reduction plan."
                    if concentrated
                    else "Portfolio analytics has unresolved risk evidence."
                ),
                analytics.blockers,
            )
        )

    @staticmethod
    def _spot_inventory(
        symbol: str,
        wallet: WalletSnapshot,
        context: MarketManagementContext,
        output: list[ManagementRecommendation],
    ) -> None:
        analyzed_asset = symbol.removesuffix("USDT") or symbol
        for balance in wallet.balances:
            quantity = balance.free + balance.locked
            if quantity <= 0:
                continue
            analyzed = balance.asset == analyzed_asset
            bearish = analyzed and (
                context.bias.startswith("BEARISH") or context.action == "SELL"
            )
            blockers = (
                context.blockers
                if analyzed
                else tuple(
                    dict.fromkeys((*context.blockers, "SYMBOL_ANALYSIS_UNAVAILABLE"))
                )
            )
            output.append(
                ManagementRecommendation(
                    "EXISTING_POSITION",
                    "SPOT",
                    f"{balance.asset}_INVENTORY",
                    ManagementAction.REDUCE_RISK_REVIEW
                    if bearish
                    else ManagementAction.HOLD_REVIEW,
                    "Existing Spot inventory conflicts with the current "
                    "bearish context."
                    if bearish
                    else "Inventory is read-only monitored; no validated exit trigger.",
                    blockers,
                )
            )

    @staticmethod
    def _futures_positions(
        symbol: str,
        account: FuturesAccountSnapshot,
        context: MarketManagementContext,
        output: list[ManagementRecommendation],
    ) -> None:
        for position in account.positions:
            if position.quantity == 0:
                continue
            analyzed = position.symbol == symbol
            long_position = position.quantity > 0
            conflict = analyzed and (
                (long_position and context.bias.startswith("BEARISH"))
                or (not long_position and context.bias.startswith("BULLISH"))
            )
            blockers = list(context.blockers)
            if not analyzed:
                blockers.append("SYMBOL_ANALYSIS_UNAVAILABLE")
            if position.mark_price is None:
                blockers.append("MARK_PRICE_UNAVAILABLE")
            if position.liquidation_price is None or position.liquidation_price <= 0:
                blockers.append("LIQUIDATION_PRICE_UNAVAILABLE")
            if position.leverage is None:
                blockers.append("LEVERAGE_UNAVAILABLE")
            if position.margin_type is None:
                blockers.append("MARGIN_TYPE_UNAVAILABLE")
            if position.notional is None:
                blockers.append("NOTIONAL_UNAVAILABLE")
            if position.margin_type == "ISOLATED" and position.isolated_margin is None:
                blockers.append("ISOLATED_MARGIN_UNAVAILABLE")
            blockers.append("FUNDING_DATA_UNAVAILABLE")
            output.append(
                ManagementRecommendation(
                    "EXISTING_POSITION",
                    "USD_M_FUTURES",
                    f"{position.symbol}_{'LONG' if long_position else 'SHORT'}",
                    ManagementAction.REDUCE_RISK_REVIEW
                    if conflict
                    else ManagementAction.HOLD_REVIEW,
                    "Position direction conflicts with market context."
                    if conflict
                    else (
                        "No symbol-specific advisory context; position is monitored "
                        "without a directional classification."
                        if not analyzed
                        else "Position has no validated management trigger."
                    ),
                    tuple(dict.fromkeys(blockers)),
                )
            )

    @staticmethod
    def _open_orders(
        symbol: str,
        account: WalletSnapshot | FuturesAccountSnapshot,
        context: MarketManagementContext,
        output: list[ManagementRecommendation],
    ) -> None:
        for order in account.open_orders:
            analyzed = order.symbol == symbol
            blockers = (
                context.blockers
                if analyzed
                else tuple(
                    dict.fromkeys((*context.blockers, "SYMBOL_ANALYSIS_UNAVAILABLE"))
                )
            )
            blocked = (
                not analyzed or bool(context.blockers) or context.action == "NO_TRADE"
            )
            output.append(
                ManagementRecommendation(
                    "OPEN_ORDER",
                    order.market,
                    order.client_order_id,
                    ManagementAction.OPEN_ORDER_REVIEW
                    if blocked
                    else ManagementAction.HOLD_REVIEW,
                    "Open order has no symbol-specific advisory context."
                    if not analyzed
                    else "Open order requires manual review while advisory is blocked."
                    if blocked
                    else "Open order remains aligned with current advisory context.",
                    blockers,
                )
            )

    def _opportunities(
        self,
        context: MarketManagementContext,
        output: list[ManagementRecommendation],
    ) -> None:
        radar = context.opportunity_radar or tuple(
            OpportunityReviewItem(
                setup_name=setup,
                blockers=context.blockers,
            )
            for setup in context.setup_radar
        )
        for item in radar:
            blockers = tuple(
                dict.fromkeys(
                    (
                        *context.blockers,
                        *item.blockers,
                        "PROFIT_GROWTH_REVIEW",
                        f"TARGET_RR_REVIEW={item.target_risk_reward}_TO_{item.stretch_risk_reward}",
                        "RESEARCH_ONLY_OPPORTUNITY",
                        "VALIDATION_GATE_REQUIRED",
                    )
                )
            )
            subject = (
                f"{item.setup_name}@{item.timeframe}"
                if item.timeframe != "UNKNOWN"
                else item.setup_name
            )
            output.append(
                ManagementRecommendation(
                    "NEW_OPPORTUNITY",
                    context.market,
                    subject,
                    ManagementAction.WATCHLIST,
                    (
                        "Growth opportunity is visible on the radar but remains "
                        "manual-review only; review entry trigger, invalidation, "
                        f"liquidity and target R/R {item.target_risk_reward}-"
                        f"{item.stretch_risk_reward}. status={item.status}; "
                        f"tier={item.setup_tier}; direction={item.direction}; "
                        f"score={item.score:.2f}; confidence={item.confidence:.2f}; "
                        f"promotion={item.promotion_status}."
                    ),
                    blockers,
                )
            )

    def _opportunity_liquidity(
        self,
        wallet: WalletSnapshot,
        context: MarketManagementContext,
        analytics: PortfolioAnalytics | None,
        output: list[ManagementRecommendation],
    ) -> None:
        if context.market != "SPOT" or not (
            context.setup_radar or context.opportunity_radar
        ):
            return
        reserve_ratio = self._quote_reserve_ratio(wallet, analytics)
        if reserve_ratio is not None and (
            reserve_ratio >= self.growth_policy.minimum_quote_reserve_ratio
        ):
            return
        source_asset = self._largest_non_quote_asset(wallet, analytics)
        subject = (
            f"{source_asset}->USDT_RESERVE"
            if source_asset is not None
            else "SPOT_LIQUIDITY_RESERVE"
        )
        evidence_blocker = (
            "QUOTE_RESERVE_BELOW_TARGET"
            if reserve_ratio is not None
            else "QUOTE_RESERVE_EVIDENCE_INCOMPLETE"
        )
        output.append(
            ManagementRecommendation(
                "OPPORTUNITY_LIQUIDITY",
                "SPOT",
                subject,
                ManagementAction.PREPARE_LIQUIDITY_REVIEW,
                "Portfolio is opportunity-constrained by liquid quote reserve; "
                "review a capped, fee-aware liquidity release before acting on "
                "growth setups.",
                tuple(
                    dict.fromkeys(
                        (
                            *context.blockers,
                            "PROFIT_GROWTH_REVIEW",
                            "RESEARCH_ONLY_OPPORTUNITY",
                            evidence_blocker,
                            "MANUAL_LIQUIDITY_REVIEW_REQUIRED",
                        )
                    )
                ),
            )
        )

    @staticmethod
    def _quote_reserve_ratio(
        wallet: WalletSnapshot,
        analytics: PortfolioAnalytics | None,
    ) -> Decimal | None:
        if analytics is not None and analytics.total_value_usdt > ZERO:
            reserve_value = sum(
                (
                    item.value_usdt
                    for item in analytics.valued_assets
                    if item.asset in QUOTE_RESERVE_ASSETS
                ),
                ZERO,
            )
            return reserve_value / analytics.total_value_usdt
        quote_quantity = sum(
            (
                balance.free + balance.locked
                for balance in wallet.balances
                if balance.asset in QUOTE_RESERVE_ASSETS
            ),
            ZERO,
        )
        non_quote_quantity = sum(
            (
                balance.free + balance.locked
                for balance in wallet.balances
                if balance.asset not in QUOTE_RESERVE_ASSETS
            ),
            ZERO,
        )
        if quote_quantity <= ZERO and non_quote_quantity > ZERO:
            return ZERO
        return None

    @staticmethod
    def _largest_non_quote_asset(
        wallet: WalletSnapshot,
        analytics: PortfolioAnalytics | None,
    ) -> str | None:
        if analytics is not None:
            largest = max(
                (
                    item
                    for item in analytics.valued_assets
                    if item.asset not in QUOTE_RESERVE_ASSETS
                ),
                key=lambda item: item.value_usdt,
                default=None,
            )
            if largest is not None:
                return largest.asset
        largest_balance = max(
            (
                balance
                for balance in wallet.balances
                if balance.asset not in QUOTE_RESERVE_ASSETS
                and balance.free + balance.locked > ZERO
            ),
            key=lambda item: item.free + item.locked,
            default=None,
        )
        return largest_balance.asset if largest_balance is not None else None

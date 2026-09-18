"""Deterministic capital allocation proposals separate from execution."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.domain.market.markets import CapitalMarket
from ai4binance.portfolio.asset_policy import AssetPolicy

ZERO = Decimal("0")


class AllocationDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INSUFFICIENT_CAPITAL = "INSUFFICIENT_CAPITAL"
    RISK_LIMIT_REACHED = "RISK_LIMIT_REACHED"
    MIN_NOTIONAL_FAILED = "MIN_NOTIONAL_FAILED"
    FUNDING_ACTION_REQUIRED = "FUNDING_ACTION_REQUIRED"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True, slots=True)
class CapitalPool:
    market: CapitalMarket
    available_amount: Decimal
    locked_amount: Decimal = ZERO
    reserve_amount: Decimal = ZERO
    source: str = "SPOT_FREE_QUOTE"
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if min(self.available_amount, self.locked_amount, self.reserve_amount) < ZERO:
            raise ValueError("capital pool amounts cannot be negative")
        if not self.source.strip():
            raise ValueError("capital pool source is required")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("capital pool blockers cannot be empty")


@dataclass(frozen=True, slots=True)
class OpportunityCapitalRequest:
    market: CapitalMarket
    symbol: str
    requested_notional: Decimal
    minimum_notional: Decimal
    risk_budget_available: bool = True
    requires_asset_sale: bool = False
    required_funding_asset: str | None = None
    requires_transfer: bool = False

    def __post_init__(self) -> None:
        normalized = self.symbol.strip().upper()
        if not normalized:
            raise ValueError("opportunity symbol is required")
        if min(self.requested_notional, self.minimum_notional) <= ZERO:
            raise ValueError("opportunity notional values must be positive")
        if self.required_funding_asset is not None:
            asset = self.required_funding_asset.strip().upper()
            if not asset or not asset.isalnum():
                raise ValueError("required_funding_asset must be alphanumeric")
            object.__setattr__(self, "required_funding_asset", asset)
        object.__setattr__(self, "symbol", normalized)


@dataclass(frozen=True, slots=True)
class AllocationProposal:
    market: CapitalMarket
    symbol: str
    available_capital: Decimal
    proposed_capital: Decimal
    funding_source: str
    requires_asset_sale: bool
    requires_transfer: bool
    decision: AllocationDecision
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.funding_source.strip():
            raise ValueError("allocation proposal identity is required")
        if min(self.available_capital, self.proposed_capital) < ZERO:
            raise ValueError("allocation proposal amounts cannot be negative")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("allocation proposal cannot grant execution authority")
        if self.decision is not AllocationDecision.ELIGIBLE and not self.blockers:
            raise ValueError("rejected allocation proposal must include blockers")


@dataclass(frozen=True, slots=True)
class CapitalAllocator:
    policy: AssetPolicy = field(default_factory=AssetPolicy)

    def allocate(
        self,
        request: OpportunityCapitalRequest,
        pool: CapitalPool,
    ) -> AllocationProposal:
        blockers = list(pool.blockers)
        decision = AllocationDecision.ELIGIBLE
        proposed_capital = request.requested_notional
        if request.market is not pool.market:
            blockers.append("CAPITAL_POOL_MARKET_MISMATCH")
            decision = AllocationDecision.NO_TRADE
        elif request.requires_asset_sale and self._requires_protected_asset(request):
            blockers.append("PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE")
            decision = AllocationDecision.FUNDING_ACTION_REQUIRED
            proposed_capital = ZERO
        elif not request.risk_budget_available:
            blockers.append("RISK_BUDGET_UNAVAILABLE")
            decision = AllocationDecision.RISK_LIMIT_REACHED
            proposed_capital = ZERO
        elif request.requested_notional < request.minimum_notional:
            blockers.append("MIN_NOTIONAL_FAILED")
            decision = AllocationDecision.MIN_NOTIONAL_FAILED
            proposed_capital = ZERO
        elif pool.available_amount < request.requested_notional:
            blockers.append("INSUFFICIENT_AVAILABLE_CAPITAL")
            decision = (
                AllocationDecision.FUNDING_ACTION_REQUIRED
                if request.requires_transfer or request.requires_asset_sale
                else AllocationDecision.INSUFFICIENT_CAPITAL
            )
            proposed_capital = ZERO
        return AllocationProposal(
            request.market,
            request.symbol,
            pool.available_amount,
            proposed_capital,
            pool.source,
            request.requires_asset_sale,
            request.requires_transfer,
            decision,
            tuple(dict.fromkeys(blockers)),
        )

    def _requires_protected_asset(self, request: OpportunityCapitalRequest) -> bool:
        if request.required_funding_asset is None:
            return False
        return self.policy.is_protected(request.required_funding_asset)

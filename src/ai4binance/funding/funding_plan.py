"""Funding option proposals that never mutate wallet state."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.portfolio.asset_policy import AssetPolicy

ZERO = Decimal("0")


class FundingAction(StrEnum):
    USE_FREE_STABLECOIN = "USE_FREE_STABLECOIN"
    REVIEW_LOCKED_ORDER = "REVIEW_LOCKED_ORDER"
    REQUEST_ASSET_CONVERSION = "REQUEST_ASSET_CONVERSION"
    REQUEST_WALLET_TRANSFER = "REQUEST_WALLET_TRANSFER"
    NO_AVAILABLE_FUNDING = "NO_AVAILABLE_FUNDING"


class FundingActionDecision(StrEnum):
    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class FundingActionProposal:
    action: FundingAction
    decision: FundingActionDecision
    asset: str
    estimated_free_capital_usdt: Decimal
    rationale: str
    approval_required: bool = True
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.asset.strip() or not self.rationale.strip():
            raise ValueError("funding action identity is required")
        if self.estimated_free_capital_usdt < ZERO:
            raise ValueError("funding action amount cannot be negative")
        if self.execution_allowed:
            raise ValueError("funding action cannot authorize execution")
        if self.decision is not FundingActionDecision.PROPOSED and not self.blockers:
            raise ValueError("blocked funding action must include blockers")

    @classmethod
    def rejected(
        cls,
        *,
        action: FundingAction,
        asset: str,
        reason: str,
    ) -> "FundingActionProposal":
        return cls(
            action,
            FundingActionDecision.REJECTED,
            asset.strip().upper(),
            ZERO,
            reason,
            True,
            (reason,),
        )


@dataclass(frozen=True, slots=True)
class FundingPlan:
    required_capital_usdt: Decimal
    proposals: tuple[FundingActionProposal, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.required_capital_usdt <= ZERO:
            raise ValueError("required_capital_usdt must be positive")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("funding plan cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class FundingPlanEngine:
    policy: AssetPolicy = field(default_factory=AssetPolicy)

    def build_plan(
        self,
        *,
        required_capital_usdt: Decimal,
        free_quote_capital_usdt: Decimal = ZERO,
        locked_order_capital_usdt: Decimal = ZERO,
        convertible_assets_usdt: Mapping[str, Decimal] | None = None,
        transferable_capital_usdt: Decimal = ZERO,
    ) -> FundingPlan:
        self._validate_amount(
            "required_capital_usdt", required_capital_usdt, positive=True
        )
        self._validate_amount("free_quote_capital_usdt", free_quote_capital_usdt)
        self._validate_amount("locked_order_capital_usdt", locked_order_capital_usdt)
        self._validate_amount("transferable_capital_usdt", transferable_capital_usdt)
        proposals: list[FundingActionProposal] = []
        if free_quote_capital_usdt > ZERO:
            proposals.append(
                FundingActionProposal(
                    FundingAction.USE_FREE_STABLECOIN,
                    FundingActionDecision.PROPOSED,
                    "QUOTE",
                    min(required_capital_usdt, free_quote_capital_usdt),
                    "Use free preferred quote balance before any asset conversion.",
                    approval_required=False,
                )
            )
        if locked_order_capital_usdt > ZERO:
            proposals.append(
                FundingActionProposal(
                    FundingAction.REVIEW_LOCKED_ORDER,
                    FundingActionDecision.PROPOSED,
                    "OPEN_ORDERS",
                    min(required_capital_usdt, locked_order_capital_usdt),
                    "Review stale or invalid open orders; do not cancel automatically.",
                )
            )
        for asset, value in (convertible_assets_usdt or {}).items():
            normalized_asset = asset.strip().upper()
            self._validate_amount(f"convertible_assets_usdt[{normalized_asset}]", value)
            if value <= ZERO:
                continue
            if self.policy.is_protected(normalized_asset):
                proposals.append(
                    FundingActionProposal.rejected(
                        action=FundingAction.REQUEST_ASSET_CONVERSION,
                        asset=normalized_asset,
                        reason="PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE",
                    )
                )
                continue
            proposals.append(
                FundingActionProposal(
                    FundingAction.REQUEST_ASSET_CONVERSION,
                    FundingActionDecision.PROPOSED,
                    normalized_asset,
                    min(required_capital_usdt, value),
                    "Manual asset conversion can be reviewed as a funding option.",
                )
            )
        if transferable_capital_usdt > ZERO:
            proposals.append(
                FundingActionProposal(
                    FundingAction.REQUEST_WALLET_TRANSFER,
                    FundingActionDecision.PROPOSED,
                    "USDT",
                    min(required_capital_usdt, transferable_capital_usdt),
                    "Wallet transfer requires separate manual approval.",
                )
            )
        if not proposals:
            proposals.append(
                FundingActionProposal(
                    FundingAction.NO_AVAILABLE_FUNDING,
                    FundingActionDecision.UNAVAILABLE,
                    "NONE",
                    ZERO,
                    "No non-protected funding source is available.",
                    True,
                    ("NO_AVAILABLE_FUNDING",),
                )
            )
        blockers = tuple(
            dict.fromkeys(
                blocker for proposal in proposals for blocker in proposal.blockers
            )
        )
        return FundingPlan(required_capital_usdt, tuple(proposals), blockers)

    @staticmethod
    def _validate_amount(name: str, value: Decimal, *, positive: bool = False) -> None:
        if not value.is_finite() or value < ZERO or (positive and value <= ZERO):
            expected = "positive" if positive else "non-negative"
            raise ValueError(f"{name} must be finite and {expected}")

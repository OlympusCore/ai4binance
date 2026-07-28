"""Dynamic portfolio policy, funding and allocation tests."""

from decimal import Decimal

import pytest

from ai4binance.allocation import (
    AllocationDecision,
    CapitalAllocator,
    CapitalMarket,
    CapitalPool,
    OpportunityCapitalRequest,
)
from ai4binance.config import Settings
from ai4binance.funding import FundingAction, FundingActionDecision, FundingPlanEngine
from ai4binance.portfolio import (
    AssetClassification,
    AssetClassifier,
    AssetPolicy,
    SpotBalance,
)


def test_default_asset_policy_keeps_hot_reviewable_and_usdt_available() -> None:
    records = AssetClassifier().classify_spot_balances(
        (
            SpotBalance("HOT", Decimal("10000"), Decimal("25")),
            SpotBalance("USDT", Decimal("50"), Decimal("10")),
            SpotBalance("BNB", Decimal("1"), Decimal("0")),
            SpotBalance("ABC", Decimal("10"), Decimal("0")),
        ),
        prices_usdt={
            "HOT": Decimal("0.002"),
            "BNB": Decimal("600"),
            "ABC": Decimal("0.1"),
        },
    )

    by_asset = {item.asset: item for item in records}
    assert by_asset["HOT"].classification is AssetClassification.CONVERTIBLE
    assert by_asset["HOT"].classification_reason == "MANUAL_CONVERSION_REQUIRED"
    assert by_asset["HOT"].funding_eligible is False
    assert by_asset["USDT"].classification is AssetClassification.CASH_EQUIVALENT
    assert by_asset["USDT"].available_for_new_spot_notional == Decimal("50")
    assert by_asset["BNB"].classification is AssetClassification.FEE_RESERVE
    assert by_asset["ABC"].classification is AssetClassification.DUST


def test_funding_plan_proposes_hot_conversion_when_not_protected() -> None:
    plan = FundingPlanEngine().build_plan(
        required_capital_usdt=Decimal("100"),
        convertible_assets_usdt={
            "HOT": Decimal("250"),
            "XRP": Decimal("125"),
        },
    )

    hot = next(item for item in plan.proposals if item.asset == "HOT")
    xrp = next(item for item in plan.proposals if item.asset == "XRP")
    assert hot.action is FundingAction.REQUEST_ASSET_CONVERSION
    assert hot.decision is FundingActionDecision.PROPOSED
    assert hot.approval_required is True
    assert hot.execution_allowed is False
    assert xrp.decision is FundingActionDecision.PROPOSED
    assert plan.execution_allowed is False
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_funding_plan_can_still_reject_explicitly_protected_assets() -> None:
    plan = FundingPlanEngine(AssetPolicy(protected_assets=("HOT",))).build_plan(
        required_capital_usdt=Decimal("100"),
        convertible_assets_usdt={"HOT": Decimal("250")},
    )

    hot = next(item for item in plan.proposals if item.asset == "HOT")
    assert hot.decision is FundingActionDecision.REJECTED
    assert hot.blockers == ("PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE",)


def test_allocator_separates_opportunity_from_capital_fit() -> None:
    proposal = CapitalAllocator().allocate(
        OpportunityCapitalRequest(
            CapitalMarket.SPOT,
            "ETHUSDT",
            Decimal("150"),
            Decimal("10"),
        ),
        CapitalPool(CapitalMarket.SPOT, Decimal("50"), source="SPOT_FREE_USDT"),
    )

    assert proposal.decision is AllocationDecision.INSUFFICIENT_CAPITAL
    assert proposal.proposed_capital == Decimal("0")
    assert proposal.blockers == ("INSUFFICIENT_AVAILABLE_CAPITAL",)
    assert proposal.execution_allowed is False
    assert proposal.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_allocator_blocks_protected_asset_as_funding_source() -> None:
    proposal = CapitalAllocator(AssetPolicy(protected_assets=("HOT",))).allocate(
        OpportunityCapitalRequest(
            CapitalMarket.SPOT,
            "ETHUSDT",
            Decimal("100"),
            Decimal("10"),
            requires_asset_sale=True,
            required_funding_asset="HOT",
        ),
        CapitalPool(CapitalMarket.SPOT, Decimal("0"), source="SPOT_ASSET_SALE"),
    )

    assert proposal.decision is AllocationDecision.FUNDING_ACTION_REQUIRED
    assert proposal.blockers == ("PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE",)
    assert proposal.proposed_capital == Decimal("0")


def test_allocator_can_emit_eligible_proposal_without_execution_authority() -> None:
    proposal = CapitalAllocator().allocate(
        OpportunityCapitalRequest(
            CapitalMarket.SPOT,
            "ETHUSDT",
            Decimal("100"),
            Decimal("10"),
        ),
        CapitalPool(CapitalMarket.SPOT, Decimal("150"), source="SPOT_FREE_USDT"),
    )

    assert proposal.decision is AllocationDecision.ELIGIBLE
    assert proposal.proposed_capital == Decimal("100")
    assert proposal.execution_allowed is False


def test_settings_expose_dynamic_portfolio_defaults() -> None:
    settings = Settings(
        default_watch_symbol=" hotusdt ",
        priority_watchlist=(" hotusdt ", "ethusdt", "ETHUSDT"),
    )

    assert settings.default_watch_symbol == "HOTUSDT"
    assert settings.priority_watchlist == ("HOTUSDT", "ETHUSDT")
    assert settings.protected_assets == ()
    assert settings.allow_auto_asset_conversion is False
    assert settings.allow_auto_wallet_transfer is False
    assert settings.allow_auto_position_close is False


def test_settings_require_separate_approval_for_auto_asset_actions() -> None:
    with pytest.raises(ValueError, match="separate live approval"):
        Settings(allow_auto_live_orders=True, allow_auto_asset_conversion=True)

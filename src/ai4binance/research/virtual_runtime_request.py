"""Validated requests for wallet-independent virtual decision cycles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType

from ai4binance.core.contracts.virtual_governance import (
    DGE_APPROVED_PAPER_ONLY,
    DGE_SIMULATION_NOT_APPROVED,
)
from ai4binance.domain import Action
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.portfolio.risk_budget import PositionExposure
from ai4binance.research.backtesting.liquidity import LiquidityStressConfig
from ai4binance.research.virtual_runtime_portfolio_state import (
    VirtualPortfolioState,
    VirtualPositionSide,
)
from ai4binance.research.virtual_runtime_risk import VirtualPortfolioRiskGovernor

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class VirtualRuntimeRequest:
    """Application-level request for one wallet-independent virtual decision cycle."""

    snapshot_id: str
    decision_id: str
    candidate_id: str
    symbol: str
    market: str
    action: Action
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_levels: tuple[Decimal, ...]
    portfolio: VirtualPortfolioState
    opportunity_id: str = ""
    fee_ratio: Decimal = ZERO
    slippage_ratio: Decimal = ZERO
    half_spread_ratio: Decimal = ZERO
    tick_size: Decimal = Decimal("0.00000001")
    step_size: Decimal = Decimal("0.00000001")
    minimum_notional: Decimal = Decimal("5")
    candle_volume: Decimal | None = None
    liquidity_stress: LiquidityStressConfig = field(
        default_factory=LiquidityStressConfig
    )
    strategy_id: str = "UNSPECIFIED_STRATEGY"
    strategy_version: str = "1"
    strategy_config_version: str = "1"
    strategy_config_hash: str = "default"
    regime: str = "UNKNOWN"
    timeframe: str = "UNKNOWN"
    correlation_group: str = "UNSPECIFIED_GROUP"
    current_exposures: tuple[PositionExposure, ...] = ()
    portfolio_governor: VirtualPortfolioRiskGovernor = field(
        default_factory=VirtualPortfolioRiskGovernor
    )
    position_side: VirtualPositionSide | None = None
    mark_price: Decimal | None = None
    funding_rate: Decimal | None = None
    funding_payment_due: bool = True
    leverage: int | None = None
    isolated_margin_usdt: Decimal | None = None
    maintenance_margin_ratio: Decimal | None = None
    liquidation_fee_ratio: Decimal = Decimal("0.005")
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET
    analysis_blockers: tuple[str, ...] = ()
    candidate_blockers: tuple[str, ...] = ()
    risk_blockers: tuple[str, ...] = ()
    validation_blockers: tuple[str, ...] = ()
    dge_blockers: tuple[str, ...] = ()
    dge_decision: str = "UNKNOWN"
    dge_simulation_allowed: bool = False
    risk_policy_version: str = "unknown"
    validation_version: str = "unknown"
    entry_reason: tuple[str, ...] = ("VIRTUAL_MARKET_ENTRY",)
    require_structural_margin_proof: bool = False
    structural_margin_context: Mapping[str, object] | None = None
    structural_risk_budget_usdt: Decimal | None = None

    def __post_init__(self) -> None:
        self._validate_numeric_inputs()
        if not isinstance(self.require_structural_margin_proof, bool):
            raise ValueError("structural margin requirement must be boolean")
        if self.structural_risk_budget_usdt is not None and (
            not self.structural_risk_budget_usdt.is_finite()
            or self.structural_risk_budget_usdt < ZERO
        ):
            raise ValueError("structural risk budget must be finite and nonnegative")
        if self.structural_margin_context is not None:
            if not isinstance(self.structural_margin_context, Mapping):
                raise ValueError("structural margin context must be a mapping")
            object.__setattr__(
                self,
                "structural_margin_context",
                MappingProxyType(dict(self.structural_margin_context)),
            )
        if not self.opportunity_id.strip():
            object.__setattr__(
                self,
                "opportunity_id",
                f"opportunity:{self.candidate_id}",
            )
        for value in (
            self.snapshot_id,
            self.decision_id,
            self.candidate_id,
            self.symbol,
            self.market,
            self.strategy_id,
            self.strategy_version,
            self.strategy_config_version,
            self.strategy_config_hash,
            self.regime,
            self.timeframe,
            self.correlation_group,
            self.dge_decision,
            self.risk_policy_version,
            self.validation_version,
            self.opportunity_id,
        ):
            if not value.strip():
                raise ValueError("virtual runtime request identity is required")
        _require_unique_nonblank(
            "virtual runtime request entry reason", self.entry_reason
        )
        _require_unique_nonblank(
            "virtual runtime request DGE blockers", self.dge_blockers
        )
        if not isinstance(self.dge_simulation_allowed, bool):
            raise ValueError(
                "virtual runtime request DGE simulation allowance must be boolean"
            )
        if self.quantity <= ZERO or self.entry_price <= ZERO or self.stop_loss <= ZERO:
            raise ValueError("virtual runtime request geometry must be positive")
        if not self.take_profit_levels:
            raise ValueError("virtual runtime request requires take-profit evidence")
        if not ZERO <= self.fee_ratio <= Decimal("0.01"):
            raise ValueError(
                "virtual runtime request fee ratio must stay between zero and 0.01"
            )
        if not ZERO <= self.slippage_ratio <= Decimal("0.02"):
            raise ValueError(
                "virtual runtime request slippage ratio must stay between zero and 0.02"
            )
        if not ZERO <= self.half_spread_ratio <= Decimal("0.02"):
            raise ValueError(
                "virtual runtime request half spread ratio must stay between "
                "zero and 0.02"
            )
        if self.tick_size <= ZERO:
            raise ValueError("virtual runtime request tick size must be positive")
        if self.step_size <= ZERO:
            raise ValueError("virtual runtime request step size must be positive")
        if self.minimum_notional <= ZERO:
            raise ValueError(
                "virtual runtime request minimum notional must be positive"
            )
        if self.candle_volume is not None and (
            not self.candle_volume.is_finite() or self.candle_volume < ZERO
        ):
            raise ValueError(
                "virtual runtime request candle volume must be finite and non-negative"
            )
        if self.mark_price is not None and self.mark_price <= ZERO:
            raise ValueError("virtual runtime request mark price must be positive")
        if self.funding_rate is not None and not self.funding_rate.is_finite():
            raise ValueError("virtual runtime request funding rate must be finite")
        if not isinstance(self.funding_payment_due, bool):
            raise ValueError(
                "virtual runtime request funding payment due must be boolean"
            )
        if self.leverage is not None and self.leverage < 1:
            raise ValueError("virtual runtime request leverage must be positive")
        if self.isolated_margin_usdt is not None and self.isolated_margin_usdt <= ZERO:
            raise ValueError("virtual runtime request isolated margin must be positive")
        if self.maintenance_margin_ratio is not None and not (
            ZERO < self.maintenance_margin_ratio < ONE
        ):
            raise ValueError(
                "virtual runtime request maintenance margin ratio must stay "
                "within zero and one"
            )
        if (
            not self.liquidation_fee_ratio.is_finite()
            or not ZERO <= self.liquidation_fee_ratio <= Decimal("0.02")
        ):
            raise ValueError("virtual runtime request liquidation fee ratio is invalid")
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError(
                "virtual runtime request market must be SPOT or USD_M_FUTURES"
            )
        if normalized_market != self.portfolio.market:
            raise ValueError(
                "virtual runtime request market must match portfolio market"
            )
        object.__setattr__(self, "market", normalized_market)
        dge_approved = (
            self.execution_surface is ExecutionSurface.VIRTUAL_MARKET
            and self.dge_decision == DGE_APPROVED_PAPER_ONLY
            and self.dge_simulation_allowed
            and not self.dge_blockers
        )
        if not dge_approved:
            object.__setattr__(
                self,
                "dge_blockers",
                tuple(dict.fromkeys((*self.dge_blockers, DGE_SIMULATION_NOT_APPROVED))),
            )

    def _validate_numeric_inputs(self) -> None:
        """Reject nonfinite values before arithmetic or comparisons."""
        numeric_values = (
            self.quantity,
            self.entry_price,
            self.stop_loss,
            *self.take_profit_levels,
            self.fee_ratio,
            self.slippage_ratio,
            self.half_spread_ratio,
            self.tick_size,
            self.step_size,
            self.minimum_notional,
            self.mark_price,
            self.isolated_margin_usdt,
            self.maintenance_margin_ratio,
        )
        if any(value is not None and not value.is_finite() for value in numeric_values):
            raise ValueError("virtual runtime request numeric values must be finite")
        if self.leverage is not None and (
            not isinstance(self.leverage, int) or isinstance(self.leverage, bool)
        ):
            raise ValueError("virtual runtime leverage must be an integer")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blank values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

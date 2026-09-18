"""Deterministic virtual-market exit selection for backtest closures."""

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from ai4binance.research.backtesting.models import BacktestExitReason, BacktestIntent
from ai4binance.schemas import OHLCVCandle

if TYPE_CHECKING:
    from ai4binance.execution.paper import ExitReason, PaperPosition


@dataclass(frozen=True, slots=True)
class VirtualExitDecision:
    """Canonical exit decision for one virtual-market closure."""

    reason: BacktestExitReason
    price: Decimal


@dataclass(frozen=True, slots=True)
class VirtualExitEngine:
    """Bridge conservative paper execution exits into canonical virtual reasons."""

    @staticmethod
    def evaluate_long_exit(
        *,
        intent: BacktestIntent,
        position: "PaperPosition",
        candle: OHLCVCandle,
        bars_held: int,
    ) -> VirtualExitDecision | None:
        protective_or_target = VirtualExitEngine._protective_or_target_exit(
            position=position,
            candle=candle,
        )
        if protective_or_target is not None:
            return protective_or_target
        if (
            intent.maximum_holding_bars is not None
            and bars_held > intent.maximum_holding_bars
        ):
            return VirtualExitDecision(
                reason=BacktestExitReason.TIME_EXIT,
                price=candle.close,
            )
        return None

    @staticmethod
    def end_of_data_exit(candle: OHLCVCandle) -> VirtualExitDecision:
        return VirtualExitDecision(
            reason=BacktestExitReason.END_OF_DATA,
            price=candle.close,
        )

    @staticmethod
    def _protective_or_target_exit(
        *,
        position: "PaperPosition",
        candle: OHLCVCandle,
    ) -> VirtualExitDecision | None:
        from ai4binance.execution.paper import PaperBroker

        paper_exit = PaperBroker.evaluate_long_exit(position, candle)
        if paper_exit is None:
            return None
        return VirtualExitDecision(
            reason=_canonical_exit_reason(paper_exit.reason),
            price=paper_exit.price,
        )


def _canonical_exit_reason(reason: "ExitReason") -> BacktestExitReason:
    if reason.value == "STOP_LOSS_EXIT":
        return BacktestExitReason.HARD_STOP
    if reason.value == "TRAILING_STOP_EXIT":
        return BacktestExitReason.TRAILING_STOP
    if reason.value == "TAKE_PROFIT_EXIT":
        return BacktestExitReason.TARGET
    raise ValueError(f"unsupported paper exit reason: {reason.value}")

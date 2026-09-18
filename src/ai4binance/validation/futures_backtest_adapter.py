"""Replay-only adapter from runtime Price/OI regimes to Futures intents."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_DOWN, Decimal
from hashlib import sha256

from ai4binance.research.backtesting.futures_engine import (
    FuturesBacktestConfig,
    FuturesBacktestEngine,
    FuturesBacktestIntent,
)
from ai4binance.research.backtesting.models import TradeDirection
from ai4binance.validation.futures_oos import (
    FUTURES_OOS_STRATEGY_ID,
    FUTURES_OOS_STRATEGY_VERSION,
    RUNTIME_FUTURES_MAXIMUM_HOLDING_BARS,
    RUNTIME_FUTURES_MINIMUM_RISK_REWARD,
    RUNTIME_FUTURES_STOP_LOSS_RATIO,
    RUNTIME_FUTURES_TAKE_PROFIT_RATIO,
    runtime_futures_strategy_sha256,
)
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.whale_fusion.features import DerivativesFeatureEngine
from ai4binance.whale_fusion.models import DerivativesMetric, PriceOiRegime

ZERO = Decimal("0")
ONE = Decimal("1")
RUNTIME_FUTURES_BACKTEST_NOTIONAL_TO_EQUITY_RATIO = ONE
_DIRECTIONAL_SETUPS = frozenset(
    {
        PriceOiRegime.NEW_LONG_PARTICIPATION,
        PriceOiRegime.SHORT_COVERING,
        PriceOiRegime.NEW_SHORT_PRESSURE,
        PriceOiRegime.DELEVERAGING,
    }
)


def runtime_futures_backtest_engine(
    dataset: RuntimeFuturesReplayDataset,
    *,
    base_config: FuturesBacktestConfig | None = None,
) -> FuturesBacktestEngine:
    """Build a price-normalized research engine for one exact replay."""

    if not isinstance(dataset, RuntimeFuturesReplayDataset):
        raise TypeError("runtime Futures sizing requires a replay dataset")
    config = base_config or FuturesBacktestConfig()
    maximum_entry_price = max(candle.open for candle in dataset.candles)
    target_notional = (
        config.initial_cash_usdt * RUNTIME_FUTURES_BACKTEST_NOTIONAL_TO_EQUITY_RATIO
    )
    quantity = (target_notional / maximum_entry_price).quantize(
        config.step_size,
        rounding=ROUND_DOWN,
    )
    if quantity <= ZERO:
        raise ValueError("runtime Futures price-normalized quantity is zero")
    return FuturesBacktestEngine(replace(config, quantity=quantity))


@dataclass(frozen=True, slots=True)
class RuntimeFuturesBacktestConfig:
    """Exact research geometry for one runtime Futures Price/OI setup."""

    setup: PriceOiRegime
    stop_loss_ratio: Decimal = RUNTIME_FUTURES_STOP_LOSS_RATIO
    take_profit_ratio: Decimal = RUNTIME_FUTURES_TAKE_PROFIT_RATIO
    minimum_risk_reward: Decimal = RUNTIME_FUTURES_MINIMUM_RISK_REWARD
    maximum_holding_bars: int = RUNTIME_FUTURES_MAXIMUM_HOLDING_BARS
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)

    def __post_init__(self) -> None:
        if self.setup not in _DIRECTIONAL_SETUPS:
            raise ValueError("runtime Futures backtest setup must be directional")
        ratios = (
            self.stop_loss_ratio,
            self.take_profit_ratio,
            self.minimum_risk_reward,
        )
        if any(not value.is_finite() or value <= ZERO for value in ratios):
            raise ValueError(
                "runtime Futures backtest ratios must be finite and positive"
            )
        if self.take_profit_ratio >= ONE:
            raise ValueError("runtime Futures take-profit ratio must remain below one")
        if self.take_profit_ratio / self.stop_loss_ratio < self.minimum_risk_reward:
            raise ValueError("runtime Futures backtest risk-reward is insufficient")
        if (
            isinstance(self.maximum_holding_bars, bool)
            or not isinstance(self.maximum_holding_bars, int)
            or self.maximum_holding_bars < 1
        ):
            raise ValueError("runtime Futures maximum holding bars must be positive")


@dataclass(slots=True)
class RuntimeFuturesBacktestAdapter:
    """Produce deterministic research intents from one replay-visible setup."""

    config: RuntimeFuturesBacktestConfig
    feature_engine: DerivativesFeatureEngine = field(
        default_factory=DerivativesFeatureEngine
    )
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)
    _blocker_counts: dict[str, int] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    @property
    def strategy_sha256(self) -> str:
        """Return the exact strategy identity carried into OOS lineage."""

        return runtime_futures_strategy_sha256(
            short_lookback=self.feature_engine.short_lookback,
            medium_lookback=self.feature_engine.medium_lookback,
            stop_loss_ratio=self.config.stop_loss_ratio,
            take_profit_ratio=self.config.take_profit_ratio,
            minimum_risk_reward=self.config.minimum_risk_reward,
            maximum_holding_bars=self.config.maximum_holding_bars,
        )

    @property
    def blocker_counts(self) -> tuple[tuple[str, int], ...]:
        """Return deterministic counts for fail-closed no-signal outcomes."""

        return tuple(sorted(self._blocker_counts.items()))

    def __call__(
        self,
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        """Map the latest replay-visible Price/OI regime to one directional intent."""

        self._validate_replay(replay)
        prices = tuple(candle.close for candle in replay.candles)
        features = self.feature_engine.compute(replay.derivatives, prices)
        if features.blockers:
            self._record_blockers(features.blockers)
            return None
        regime = features.price_oi_regime
        if regime is PriceOiRegime.FLAT_OR_MIXED:
            self._record_blockers(("PRICE_OI_DIRECTION_UNAVAILABLE",))
            return None
        if regime is not self.config.setup:
            self._record_blockers(("PRICE_OI_SETUP_MISMATCH",))
            return None
        return self._intent(
            replay,
            len(replay.candles) - 1,
            regime,
            replay.dataset_sha256,
        )

    def intent_at(
        self,
        replay: RuntimeFuturesReplayDataset,
        index: int,
    ) -> FuturesBacktestIntent | None:
        """Produce an intent at one index without rebuilding the replay prefix."""

        self._validate_replay(replay)
        if isinstance(index, bool) or not 0 <= index < len(replay.candles):
            raise IndexError("runtime Futures replay index is out of range")
        medium = self.feature_engine.medium_lookback
        if index < medium:
            self._record_blockers(("OI_OR_PRICE_HISTORY_INSUFFICIENT",))
            return None
        prices = replay.candles
        open_interest = replay.derivatives.series[DerivativesMetric.OPEN_INTEREST]
        price_change = (prices[index].close / prices[index - medium].close) - ONE
        oi_change = (
            open_interest[index].value / open_interest[index - medium].value
        ) - ONE
        regime = self.feature_engine.regime(price_change, oi_change)
        if regime is PriceOiRegime.FLAT_OR_MIXED:
            self._record_blockers(("PRICE_OI_DIRECTION_UNAVAILABLE",))
            return None
        if regime is not self.config.setup:
            self._record_blockers(("PRICE_OI_SETUP_MISMATCH",))
            return None
        snapshot_id = self._indexed_snapshot_id(replay, index)
        return self._intent(replay, index, regime, snapshot_id)

    def _intent(
        self,
        replay: RuntimeFuturesReplayDataset,
        index: int,
        regime: PriceOiRegime,
        snapshot_id: str,
    ) -> FuturesBacktestIntent:
        direction = self._direction(regime)
        candle = replay.candles[index]
        stop_loss, take_profit = self._geometry(direction, candle.close)
        digest = sha256(
            (
                f"{snapshot_id}|{regime.value}|"
                f"{self.strategy_sha256}|{candle.timestamp.isoformat()}"
            ).encode()
        ).hexdigest()[:20]
        return FuturesBacktestIntent(
            signal_id=f"runtime-futures:{digest}",
            timestamp=candle.timestamp,
            direction=direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason_codes=(
                "CLOSED_CANDLE_SIGNAL",
                "PRICE_OI_REGIME_MATCH",
                f"SETUP:{regime.value}",
            ),
            maximum_holding_bars=self.config.maximum_holding_bars,
            strategy_id=FUTURES_OOS_STRATEGY_ID,
            strategy_version=FUTURES_OOS_STRATEGY_VERSION,
            strategy_config_version="runtime-futures-signal-v1",
            strategy_config_hash=self.strategy_sha256,
            symbol=replay.symbol,
            regime=regime.value,
            timeframe=replay.timeframe,
            snapshot_id=snapshot_id,
            decision_id=f"decision:{digest}",
            dge_status="RESEARCH_ONLY",
        )

    def _indexed_snapshot_id(
        self,
        replay: RuntimeFuturesReplayDataset,
        index: int,
    ) -> str:
        medium = self.feature_engine.medium_lookback
        candle = replay.candles[index]
        earlier = replay.candles[index - medium]
        open_interest = replay.derivatives.series[DerivativesMetric.OPEN_INTEREST]
        canonical = "|".join(
            (
                replay.symbol,
                replay.timeframe,
                str(index),
                candle.timestamp.isoformat(),
                str(candle.close),
                str(earlier.close),
                str(open_interest[index].value),
                str(open_interest[index - medium].value),
                self.strategy_sha256,
            )
        )
        return f"runtime-prefix:{sha256(canonical.encode()).hexdigest()}"

    @staticmethod
    def _validate_replay(replay: RuntimeFuturesReplayDataset) -> None:
        if not isinstance(replay, RuntimeFuturesReplayDataset):
            raise TypeError("runtime Futures adapter requires a replay dataset")
        if replay.market != "USD_M_FUTURES":
            raise ValueError("runtime Futures adapter replay identity is unsupported")

    @staticmethod
    def _direction(regime: PriceOiRegime) -> TradeDirection:
        if regime in {
            PriceOiRegime.NEW_LONG_PARTICIPATION,
            PriceOiRegime.SHORT_COVERING,
        }:
            return TradeDirection.LONG
        return TradeDirection.SHORT

    def _geometry(
        self,
        direction: TradeDirection,
        close: Decimal,
    ) -> tuple[Decimal, Decimal]:
        if direction is TradeDirection.LONG:
            return (
                close * (ONE - self.config.stop_loss_ratio),
                close * (ONE + self.config.take_profit_ratio),
            )
        return (
            close * (ONE + self.config.stop_loss_ratio),
            close * (ONE - self.config.take_profit_ratio),
        )

    def _record_blockers(self, blockers: tuple[str, ...]) -> None:
        for blocker in blockers:
            self._blocker_counts[blocker] = self._blocker_counts.get(blocker, 0) + 1

"""Canonical structural-level map projected from existing level evidence."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ai4binance.indicators import atr
from ai4binance.intelligence.contracts import (
    StructuralLevelEvidence,
    TimeframeStructureEvidence,
)
from ai4binance.schemas import (
    AgentResult,
    MarketSnapshot,
    OHLCVCandle,
    is_usable_agent_result,
)

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class StructuralLevelMapEngine:
    """Enrich the existing support/resistance owner into shared zones."""

    atr_zone_ratio: Decimal = Decimal("0.15")
    touch_lookback: int = 50

    def __post_init__(self) -> None:
        if self.atr_zone_ratio <= ZERO:
            raise ValueError("level-map ATR zone ratio must be positive")
        if self.touch_lookback < 14:
            raise ValueError("level-map touch lookback must be at least 14")

    def build(
        self,
        snapshot: MarketSnapshot,
        structures: tuple[TimeframeStructureEvidence, ...],
        result: AgentResult | None,
    ) -> tuple[StructuralLevelEvidence, ...]:
        """Build one reusable level map without owning primary direction."""
        if result is None or not is_usable_agent_result(result):
            return ()
        raw_timeframes = self._mapping(result.calculation_metadata.get("timeframes"))
        structure_by_timeframe = {item.timeframe: item for item in structures}
        levels: list[StructuralLevelEvidence] = []
        for timeframe in snapshot.timeframes:
            candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
            raw = self._mapping(raw_timeframes.get(timeframe))
            if len(candles) < 14 or not raw:
                continue
            volatility = atr(candles, 14)
            half_width = volatility * self.atr_zone_ratio
            structure = structure_by_timeframe.get(timeframe)
            for level_type in ("support", "resistance"):
                center = self._decimal(raw.get(level_type))
                if center is None or center <= ZERO:
                    continue
                levels.append(
                    self._level(
                        snapshot,
                        timeframe,
                        level_type,
                        center,
                        half_width,
                        candles,
                        result.confidence,
                        structure,
                    )
                )
        return tuple(levels)

    def _level(
        self,
        snapshot: MarketSnapshot,
        timeframe: str,
        level_type: str,
        center: Decimal,
        half_width: Decimal,
        candles: tuple[OHLCVCandle, ...],
        source_confidence: float,
        structure: TimeframeStructureEvidence | None,
    ) -> StructuralLevelEvidence:
        typed_candles = candles[-self.touch_lookback :]
        price_low = max(Decimal("0.00000001"), center - half_width)
        price_high = center + half_width
        touches = tuple(
            index
            for index, candle in enumerate(typed_candles)
            if candle.low <= price_high and candle.high >= price_low
        )
        breaks = sum(
            1
            for candle in typed_candles
            if (
                candle.close < price_low
                if level_type == "support"
                else candle.close > price_high
            )
        )
        age_bars = (
            len(typed_candles) - 1 - touches[-1] if touches else len(typed_candles)
        )
        freshness = "FRESH" if age_bars <= 5 else "AGING" if age_bars <= 20 else "STALE"
        rejection_strength = min(1.0, len(touches) / 4.0)
        structure_confidence = structure.confidence if structure is not None else 1.0
        confidence = min(source_confidence, structure_confidence)
        latest_close = typed_candles[-1].close
        role_flip = breaks > 0 and (
            (level_type == "support" and latest_close > price_high)
            or (level_type == "resistance" and latest_close < price_low)
        )
        return StructuralLevelEvidence(
            level_id=f"{snapshot.snapshot_id}:{timeframe}:{level_type}",
            level_type=level_type.upper(),
            price_low=price_low,
            price_high=price_high,
            source_timeframe=timeframe,
            touch_count=len(touches),
            break_count=breaks,
            freshness=freshness,
            role_flip=role_flip,
            confidence=confidence,
            evidence_ref=f"support_resistance:{timeframe}:{level_type}",
            rejection_strength=rejection_strength,
            volume_context="NOT_MEASURED",
            age_bars=age_bars,
        )

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            return {}
        return {str(key): item for key, item in value.items()}

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None

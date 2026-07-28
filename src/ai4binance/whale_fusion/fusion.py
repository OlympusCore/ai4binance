"""Deterministic three-channel WHALE-FUSION research score."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from ai4binance.whale_fusion.models import (
    DerivativesFeatures,
    PriceOiRegime,
    WhaleEventType,
)
from ai4binance.whale_fusion.onchain.models import WhaleEvent
from ai4binance.whale_fusion.social.models import (
    SocialContradiction,
    SocialEvent,
    SocialStance,
)

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


class FusionChannel(StrEnum):
    ONCHAIN = "ONCHAIN"
    SOCIAL = "SOCIAL"
    DERIVATIVES = "DERIVATIVES"


@dataclass(frozen=True, slots=True)
class FusionConfig:
    onchain_weight: Decimal = Decimal("0.40")
    social_weight: Decimal = Decimal("0.25")
    derivatives_weight: Decimal = Decimal("0.35")
    evidence_window: timedelta = timedelta(hours=48)
    minimum_independent_channels: int = 2
    contradiction_penalty: Decimal = Decimal("0.15")

    def __post_init__(self) -> None:
        weights = (
            self.onchain_weight,
            self.social_weight,
            self.derivatives_weight,
        )
        if any(weight < ZERO for weight in weights) or sum(weights, ZERO) != ONE:
            raise ValueError(
                "fusion channel weights must be non-negative and sum to one"
            )
        if self.derivatives_weight > Decimal("0.35"):
            raise ValueError("derivatives cannot dominate Spot fusion")
        if self.evidence_window <= timedelta(0):
            raise ValueError("fusion evidence_window must be positive")
        if not 2 <= self.minimum_independent_channels <= 3:
            raise ValueError("fusion requires two or three independent channels")
        if not ZERO <= self.contradiction_penalty <= ONE:
            raise ValueError("contradiction_penalty must be within zero and one")

    def weight(self, channel: FusionChannel) -> Decimal:
        return {
            FusionChannel.ONCHAIN: self.onchain_weight,
            FusionChannel.SOCIAL: self.social_weight,
            FusionChannel.DERIVATIVES: self.derivatives_weight,
        }[channel]


@dataclass(frozen=True, slots=True)
class FusionContribution:
    channel: FusionChannel
    evidence_id: str
    timestamp: datetime
    direction: Decimal
    confidence: Decimal
    decay: Decimal

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("fusion contribution requires evidence_id")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("fusion contribution timestamp must be timezone-aware")
        if not -ONE <= self.direction <= ONE:
            raise ValueError("fusion contribution direction must be within -1 and 1")
        if not ZERO <= self.confidence <= ONE or not ZERO <= self.decay <= ONE:
            raise ValueError("fusion confidence and decay must be within zero and one")

    @property
    def effective_confidence(self) -> Decimal:
        return self.confidence * self.decay


@dataclass(frozen=True, slots=True)
class FusionResult:
    symbol: str
    asset: str
    as_of: datetime
    fusion_score: Decimal
    direction_score: Decimal
    confidence: Decimal
    active_channels: tuple[FusionChannel, ...]
    contributions: tuple[FusionContribution, ...]
    contradiction_count: int
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.asset.strip():
            raise ValueError("fusion result requires symbol and asset")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("fusion result as_of must be timezone-aware")
        if not ZERO <= self.fusion_score <= HUNDRED:
            raise ValueError("fusion_score must be within zero and one hundred")
        if not -ONE <= self.direction_score <= ONE:
            raise ValueError("direction_score must be within -1 and 1")
        if not ZERO <= self.confidence <= ONE or self.contradiction_count < 0:
            raise ValueError("fusion confidence or contradiction count is invalid")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("fusion result cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class WhaleFusionEngine:
    config: FusionConfig = FusionConfig()

    def evaluate(
        self,
        *,
        symbol: str,
        asset: str,
        as_of: datetime,
        whale_events: tuple[WhaleEvent, ...] = (),
        social_events: tuple[SocialEvent, ...] = (),
        derivatives: DerivativesFeatures | None = None,
        contradictions: tuple[SocialContradiction, ...] = (),
    ) -> FusionResult:
        normalized_symbol = symbol.strip().upper()
        normalized_asset = asset.strip().upper()
        if not normalized_symbol or not normalized_asset:
            raise ValueError("fusion symbol and asset are required")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("fusion as_of must be timezone-aware")

        blockers: list[str] = []
        contributions: list[FusionContribution] = []
        stale_seen = False
        for whale_event in self._unique_whale_events(whale_events, normalized_asset):
            decay = self._decay(whale_event.timestamp, as_of)
            if decay == ZERO:
                stale_seen = True
                continue
            contributions.append(
                FusionContribution(
                    FusionChannel.ONCHAIN,
                    whale_event.event_id,
                    whale_event.timestamp,
                    self._whale_direction(whale_event.event_type),
                    whale_event.confidence,
                    decay,
                )
            )
        for social_event in self._unique_social_events(social_events, normalized_asset):
            decay = self._decay(social_event.timestamp, as_of)
            if decay == ZERO:
                stale_seen = True
                continue
            contributions.append(
                FusionContribution(
                    FusionChannel.SOCIAL,
                    social_event.event_id,
                    social_event.timestamp,
                    self._social_direction(social_event.stance),
                    social_event.confidence,
                    decay,
                )
            )
        if derivatives is not None:
            if derivatives.symbol != normalized_symbol:
                blockers.append("DERIVATIVES_SYMBOL_MISMATCH")
            elif derivatives.blockers:
                blockers.append("DERIVATIVES_FEATURES_BLOCKED")
            else:
                decay = self._decay(derivatives.as_of, as_of)
                if decay == ZERO:
                    stale_seen = True
                else:
                    contributions.append(
                        FusionContribution(
                            FusionChannel.DERIVATIVES,
                            f"derivatives:{derivatives.symbol}:{derivatives.as_of.isoformat()}",
                            derivatives.as_of,
                            self._derivatives_direction(derivatives),
                            Decimal("0.7"),
                            decay,
                        )
                    )
        if stale_seen:
            blockers.append("STALE_FUSION_EVIDENCE_IGNORED")

        channel_scores: dict[FusionChannel, Decimal] = {}
        channel_confidences: dict[FusionChannel, Decimal] = {}
        for channel in FusionChannel:
            channel_items = tuple(
                item for item in contributions if item.channel is channel
            )
            if not channel_items:
                continue
            total_confidence = sum(
                (item.effective_confidence for item in channel_items), ZERO
            )
            if total_confidence == ZERO:
                continue
            channel_scores[channel] = (
                sum(
                    (
                        item.direction * item.effective_confidence
                        for item in channel_items
                    ),
                    ZERO,
                )
                / total_confidence
            )
            channel_confidences[channel] = min(
                ONE, total_confidence / Decimal(len(channel_items))
            )

        active_channels = tuple(
            channel for channel in FusionChannel if channel in channel_scores
        )
        if len(active_channels) < self.config.minimum_independent_channels:
            blockers.append("INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT")
        active_weight = sum(
            (self.config.weight(channel) for channel in active_channels), ZERO
        )
        direction = ZERO
        confidence = ZERO
        if active_weight > ZERO:
            direction = (
                sum(
                    (
                        channel_scores[channel] * self.config.weight(channel)
                        for channel in active_channels
                    ),
                    ZERO,
                )
                / active_weight
            )
            confidence = (
                sum(
                    (
                        channel_confidences[channel] * self.config.weight(channel)
                        for channel in active_channels
                    ),
                    ZERO,
                )
                / active_weight
            )

        relevant_contradictions = tuple(
            item
            for item in contradictions
            if item.asset.strip().upper() == normalized_asset
        )
        if relevant_contradictions:
            blockers.append("SOCIAL_CONTRADICTION_PRESENT")
            penalty = min(
                ONE,
                self.config.contradiction_penalty
                * Decimal(len(relevant_contradictions)),
            )
            confidence *= ONE - penalty
        direction = max(-ONE, min(ONE, direction))
        score = ((direction + ONE) / Decimal("2")) * HUNDRED
        return FusionResult(
            symbol=normalized_symbol,
            asset=normalized_asset,
            as_of=as_of,
            fusion_score=score,
            direction_score=direction,
            confidence=confidence,
            active_channels=active_channels,
            contributions=tuple(contributions),
            contradiction_count=len(relevant_contradictions),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def _decay(self, timestamp: datetime, as_of: datetime) -> Decimal:
        if timestamp > as_of:
            return ZERO
        age = as_of - timestamp
        if age >= self.config.evidence_window:
            return ZERO
        return ONE - (
            Decimal(str(age.total_seconds()))
            / Decimal(str(self.config.evidence_window.total_seconds()))
        )

    @staticmethod
    def _unique_whale_events(
        events: tuple[WhaleEvent, ...], asset: str
    ) -> tuple[WhaleEvent, ...]:
        unique = {
            event.event_id: event
            for event in events
            if event.asset.strip().upper() == asset
        }
        return tuple(unique[key] for key in sorted(unique))

    @staticmethod
    def _unique_social_events(
        events: tuple[SocialEvent, ...], asset: str
    ) -> tuple[SocialEvent, ...]:
        unique = {
            event.event_id: event
            for event in events
            if asset in (item.strip().upper() for item in event.assets)
        }
        return tuple(unique[key] for key in sorted(unique))

    @staticmethod
    def _whale_direction(event_type: WhaleEventType) -> Decimal:
        return {
            WhaleEventType.WHALE_TO_BINANCE: Decimal("-0.8"),
            WhaleEventType.BINANCE_TO_WHALE: Decimal("0.8"),
            WhaleEventType.WHALE_TO_DEX: ZERO,
            WhaleEventType.STABLECOIN_ACCUMULATION: Decimal("0.4"),
            WhaleEventType.STABLECOIN_EXCHANGE_DEPOSIT: Decimal("0.3"),
            WhaleEventType.TOKEN_ACCUMULATION: Decimal("0.9"),
            WhaleEventType.TOKEN_DISTRIBUTION: Decimal("-0.9"),
            WhaleEventType.NEW_WALLET: ZERO,
            WhaleEventType.SPLIT_TRANSFER: ZERO,
            WhaleEventType.BRIDGE_TRANSFER: ZERO,
            WhaleEventType.STAKING_EXIT: Decimal("-0.5"),
            WhaleEventType.TOKEN_UNLOCK_MOVEMENT: Decimal("-0.7"),
            WhaleEventType.MARKET_MAKER_MOVEMENT: ZERO,
        }[event_type]

    @staticmethod
    def _social_direction(stance: SocialStance) -> Decimal:
        return {
            SocialStance.SUPPORTIVE: Decimal("0.7"),
            SocialStance.NEGATIVE: Decimal("-0.7"),
            SocialStance.DENIAL: Decimal("-0.5"),
            SocialStance.NEUTRAL: ZERO,
            SocialStance.UNVERIFIED: ZERO,
        }[stance]

    @staticmethod
    def _derivatives_direction(features: DerivativesFeatures) -> Decimal:
        regime = {
            PriceOiRegime.NEW_LONG_PARTICIPATION: Decimal("0.5"),
            PriceOiRegime.SHORT_COVERING: Decimal("0.2"),
            PriceOiRegime.NEW_SHORT_PRESSURE: Decimal("-0.5"),
            PriceOiRegime.DELEVERAGING: Decimal("-0.2"),
            PriceOiRegime.FLAT_OR_MIXED: ZERO,
        }[features.price_oi_regime]
        taker = features.taker_imbalance or ZERO
        funding = (features.funding_percentile or Decimal("0.5")) - Decimal("0.5")
        direction = regime + (taker * Decimal("0.25")) - (funding * Decimal("0.10"))
        return max(-ONE, min(ONE, direction))

"""Logical intelligence-family consolidation for technical methods."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ai4binance.enterprise.departments import AgentClassification


class IntelligenceFamilyId(StrEnum):
    TREND_DIRECTION = "TREND_DIRECTION"
    STRUCTURE_PRICE_ACTION = "STRUCTURE_PRICE_ACTION"
    MOMENTUM_EXHAUSTION = "MOMENTUM_EXHAUSTION"
    VOLATILITY_RISK_STATE = "VOLATILITY_RISK_STATE"
    VOLUME_LIQUIDITY = "VOLUME_LIQUIDITY"
    STRUCTURAL_LEVELS_FIBONACCI = "STRUCTURAL_LEVELS_FIBONACCI"
    PATTERN_CYCLE = "PATTERN_CYCLE"
    DERIVATIVES_POSITIONING = "DERIVATIVES_POSITIONING"
    WHALE_ONCHAIN = "WHALE_ONCHAIN"
    NEWS_SENTIMENT = "NEWS_SENTIMENT"


_DETERMINISTIC_CALCULATIONS = frozenset(
    {
        "ATR",
        "EMA",
        "EXCHANGE_FILTERS",
        "MACD",
        "MINIMUM_NOTIONAL",
        "POSITION_SIZING",
        "RISK_REWARD",
        "RSI",
        "SLIPPAGE",
        "SMA",
        "SPREAD",
        "STEP_SIZE",
        "SUPERTREND",
        "TICK_SIZE",
        "VWAP",
    }
)


@dataclass(frozen=True, slots=True)
class SkillDeclaration:
    skill_name: str
    classification: AgentClassification
    hard_gate_eligible: bool = False
    advisory_only: bool = False

    def __post_init__(self) -> None:
        if not self.skill_name.strip():
            raise ValueError("skill declaration identity is required")
        normalized = self.skill_name.upper()
        if (
            normalized in _DETERMINISTIC_CALCULATIONS
            and self.classification is not AgentClassification.DETERMINISTIC_SKILL
        ):
            raise ValueError("financial calculations must be deterministic skills")
        if self.hard_gate_eligible and self.advisory_only:
            raise ValueError("advisory-only skills cannot be hard gates")


@dataclass(frozen=True, slots=True)
class IntelligenceFamily:
    family_id: IntelligenceFamilyId
    coordinator_agent: str
    skills: tuple[SkillDeclaration, ...]
    llm_advisory_allowed: bool
    oos_requirements: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.coordinator_agent.strip():
            raise ValueError("intelligence family coordinator is required")
        if not self.skills:
            raise ValueError("intelligence family requires skills")
        names = tuple(item.skill_name for item in self.skills)
        if len(set(names)) != len(names):
            raise ValueError("intelligence family skills must be unique")
        if any(not item.strip() for item in self.oos_requirements):
            raise ValueError("intelligence family OOS requirements cannot be blank")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("intelligence family cannot promote production state")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("intelligence family cannot authorize execution")


@dataclass(frozen=True, slots=True)
class IntelligenceFamilyRegistry:
    families: tuple[IntelligenceFamily, ...]
    _by_id: Mapping[IntelligenceFamilyId, IntelligenceFamily] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        if len(self.families) != len(IntelligenceFamilyId):
            raise ValueError("registry must cover every intelligence family")
        by_id = {item.family_id: item for item in self.families}
        if len(by_id) != len(self.families):
            raise ValueError("intelligence family IDs must be unique")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def get(self, family_id: IntelligenceFamilyId) -> IntelligenceFamily:
        return self._by_id[family_id]


def build_default_intelligence_family_registry() -> IntelligenceFamilyRegistry:
    return IntelligenceFamilyRegistry(
        (
            _family(
                "TrendDirectionIntelligenceAgent",
                IntelligenceFamilyId.TREND_DIRECTION,
                ("EMA", "SMA", "SUPERTREND", "HH_HL_LH_LL"),
            ),
            _family(
                "MarketStructurePriceActionAgent",
                IntelligenceFamilyId.STRUCTURE_PRICE_ACTION,
                ("BOS", "CHOCH", "SUPPORT_RECLAIM", "BREAKOUT_RETEST"),
            ),
            _family(
                "MomentumExhaustionAgent",
                IntelligenceFamilyId.MOMENTUM_EXHAUSTION,
                ("RSI", "MACD", "DIVERGENCE", "EXHAUSTION"),
            ),
            _family(
                "VolatilityRiskStateAgent",
                IntelligenceFamilyId.VOLATILITY_RISK_STATE,
                ("ATR", "VOLATILITY_EXPANSION", "SLIPPAGE"),
            ),
            _family(
                "VolumeLiquidityParticipationAgent",
                IntelligenceFamilyId.VOLUME_LIQUIDITY,
                ("VWAP", "SPREAD", "ORDER_BOOK_DEPTH"),
            ),
            _family(
                "StructuralLevelsFibonacciAgent",
                IntelligenceFamilyId.STRUCTURAL_LEVELS_FIBONACCI,
                ("SUPPORT_RESISTANCE", "FIB_RETRACEMENT", "FIB_EXTENSION"),
                advisory=("FIB_RETRACEMENT", "FIB_EXTENSION"),
            ),
            _family(
                "PatternCycleIntelligenceAgent",
                IntelligenceFamilyId.PATTERN_CYCLE,
                ("DOUBLE_TOP_BOTTOM", "WYCKOFF_PHASE", "MACRO_CYCLE"),
                advisory=("DOUBLE_TOP_BOTTOM", "WYCKOFF_PHASE", "MACRO_CYCLE"),
            ),
            _family(
                "DerivativesPositioningAgent",
                IntelligenceFamilyId.DERIVATIVES_POSITIONING,
                ("OPEN_INTEREST", "FUNDING", "LONG_SHORT_RATIO"),
                advisory=("OPEN_INTEREST", "FUNDING", "LONG_SHORT_RATIO"),
            ),
            _family(
                "WhaleSmartMoneyIntelligenceAgent",
                IntelligenceFamilyId.WHALE_ONCHAIN,
                ("EXCHANGE_FLOW", "STABLECOIN_FLOW", "SMART_MONEY_ACTIVITY"),
                advisory=("EXCHANGE_FLOW", "STABLECOIN_FLOW", "SMART_MONEY_ACTIVITY"),
            ),
            _family(
                "NewsSentimentEventRiskAgent",
                IntelligenceFamilyId.NEWS_SENTIMENT,
                ("NEWS_CLASSIFICATION", "SOURCE_AUTHORITY", "EVENT_WINDOW_CONTROL"),
                advisory=("NEWS_CLASSIFICATION", "SOURCE_AUTHORITY"),
            ),
        ),
    )


def _family(
    coordinator: str,
    family_id: IntelligenceFamilyId,
    skill_names: tuple[str, ...],
    *,
    advisory: tuple[str, ...] = (),
) -> IntelligenceFamily:
    skills = tuple(
        SkillDeclaration(
            skill_name=name,
            classification=(
                AgentClassification.DETERMINISTIC_SKILL
                if name in _DETERMINISTIC_CALCULATIONS
                else AgentClassification.STATELESS_SPECIALIST_WORKER
            ),
            advisory_only=name in advisory,
        )
        for name in skill_names
    )
    return IntelligenceFamily(
        family_id=family_id,
        coordinator_agent=coordinator,
        skills=skills,
        llm_advisory_allowed=bool(advisory),
        oos_requirements=("walk_forward", "multi_regime_oos"),
    )

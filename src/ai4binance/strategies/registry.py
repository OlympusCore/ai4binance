"""Immutable registry for the 20 required strategy playbooks."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from ai4binance.domain import ValidationStatus


@dataclass(frozen=True, slots=True)
class StrategyPlaybook:
    name: str
    compatible_regimes: tuple[str, ...]
    required_agents: tuple[str, ...]
    minimum_evidence: int
    entry_trigger: str
    invalidation_rule: str
    stop_rule: str
    target_rule: str
    trailing_rule: str
    rejection_rules: tuple[str, ...]
    required_oos_evidence: tuple[str, ...]
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    implemented: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip() or self.minimum_evidence < 1:
            raise ValueError("playbook name and minimum_evidence are required")
        if not self.required_agents:
            raise ValueError("playbook must declare required_agents")
        if self.promotion_status is ValidationStatus.LIVE_ELIGIBLE:
            raise ValueError("playbooks cannot be registered directly as live eligible")


@dataclass(frozen=True, slots=True)
class PlaybookRegistry:
    playbooks: tuple[StrategyPlaybook, ...]
    _by_name: Mapping[str, StrategyPlaybook] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        by_name = {item.name: item for item in self.playbooks}
        if len(by_name) != len(self.playbooks):
            raise ValueError("playbook names must be unique")
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def get(self, name: str) -> StrategyPlaybook:
        return self._by_name[name]

    def with_promotion(
        self,
        name: str,
        status: ValidationStatus,
    ) -> "PlaybookRegistry":
        """Return a new registry with one human-approved paper promotion."""
        current = self.get(name)
        if not current.implemented:
            raise ValueError("only implemented playbooks may be promoted")
        if status is not ValidationStatus.PAPER_APPROVED:
            raise ValueError("strategy registry promotion is paper-only")
        return PlaybookRegistry(
            tuple(
                replace(item, promotion_status=status) if item.name == name else item
                for item in self.playbooks
            )
        )


_PLAYBOOK_NAMES = (
    "trend_continuation",
    "pullback_continuation",
    "breakout_retest",
    "support_reclaim",
    "resistance_rejection",
    "failed_breakout_reversal",
    "range_rotation",
    "volatility_expansion",
    "compression_breakout",
    "mean_reversion",
    "smc_liquidity_sweep_reversal",
    "wyckoff_spring_upthrust",
    "harmonic_reversal",
    "fibonacci_continuation",
    "chart_pattern_breakout",
    "candlestick_confirmation",
    "divergence_reversal",
    "strategic_spot_accumulation",
    "strategic_spot_distribution",
    "spot_inventory_sell_rebuy",
)


def build_playbook_registry() -> PlaybookRegistry:
    implemented = {
        "trend_continuation",
        "pullback_continuation",
        "breakout_retest",
        "support_reclaim",
        "resistance_rejection",
        "failed_breakout_reversal",
        "compression_breakout",
        "range_rotation",
        "volatility_expansion",
        "smc_liquidity_sweep_reversal",
    }
    playbooks = tuple(
        StrategyPlaybook(
            name=name,
            compatible_regimes=("ALL_VALIDATED_REGIMES",),
            required_agents=(
                (
                    "trend",
                    "market_structure",
                    "multi_timeframe",
                    "price_action",
                    "confluence",
                    "risk",
                    "validation",
                )
                if name in implemented
                else ("market_regime", "risk", "validation")
            ),
            minimum_evidence=4,
            entry_trigger="DETERMINISTIC_PRICE_ACTION_CONFIRMATION",
            invalidation_rule="STRUCTURAL_INVALIDATION",
            stop_rule="ATR_AND_STRUCTURE_STOP",
            target_rule="MINIMUM_RISK_REWARD_TARGETS",
            trailing_rule="MONOTONIC_1_5_ATR",
            rejection_rules=(
                "DATA_INVALID",
                "REGIME_INCOMPATIBLE",
                "RISK_REJECTED",
                "OOS_UNAPPROVED",
            ),
            required_oos_evidence=("walk_forward", "multi_regime_oos"),
            implemented=name in implemented,
        )
        for name in _PLAYBOOK_NAMES
    )
    return PlaybookRegistry(playbooks)

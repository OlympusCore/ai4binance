"""Immutable registry for strategy playbooks and virtual-market risk profiles."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

from ai4binance.domain import ValidationStatus
from ai4binance.validation.summary import ValidationSummaryReader


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
class StrategyRiskProfile:
    """Versioned deterministic exit-profile baseline for virtual-market research."""

    strategy_id: str
    version: str
    stop_atr_multiple: Decimal
    target_atr_multiple: Decimal
    minimum_rr: Decimal
    regime: str | None = None
    breakeven_trigger_r: Decimal | None = None
    trailing_atr_multiple: Decimal | None = None
    maximum_holding_bars: int | None = None
    config_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.strategy_id.strip() or not self.version.strip():
            raise ValueError("strategy risk profile identity is required")
        if min(
            self.stop_atr_multiple,
            self.target_atr_multiple,
            self.minimum_rr,
        ) <= Decimal("0"):
            raise ValueError("strategy risk profile core multiples must be positive")
        if self.breakeven_trigger_r is not None and self.breakeven_trigger_r <= Decimal(
            "0"
        ):
            raise ValueError("breakeven_trigger_r must be positive when configured")
        if (
            self.trailing_atr_multiple is not None
            and self.trailing_atr_multiple <= Decimal("0")
        ):
            raise ValueError("trailing_atr_multiple must be positive when configured")
        if self.maximum_holding_bars is not None and self.maximum_holding_bars < 1:
            raise ValueError("maximum_holding_bars must be positive when configured")
        object.__setattr__(self, "config_hash", self._config_hash())

    def _config_hash(self) -> str:
        payload = {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "regime": self.regime,
            "stop_atr_multiple": str(self.stop_atr_multiple),
            "target_atr_multiple": str(self.target_atr_multiple),
            "minimum_rr": str(self.minimum_rr),
            "breakeven_trigger_r": (
                None
                if self.breakeven_trigger_r is None
                else str(self.breakeven_trigger_r)
            ),
            "trailing_atr_multiple": (
                None
                if self.trailing_atr_multiple is None
                else str(self.trailing_atr_multiple)
            ),
            "maximum_holding_bars": self.maximum_holding_bars,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()

    def with_parameter_overrides(
        self,
        values: Mapping[str, object],
    ) -> "StrategyRiskProfile":
        """Return a derived profile with deterministic bounded parameter overrides."""

        def optional_decimal(name: str) -> Decimal | None:
            value = values.get(name)
            if value is None:
                return None
            return Decimal(str(value))

        def optional_int(name: str) -> int | None:
            value = values.get(name)
            if value is None:
                return None
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                return int(value)
            raise TypeError(f"{name} must be configured as an integer")

        return StrategyRiskProfile(
            strategy_id=self.strategy_id,
            version=self.version,
            regime=self.regime,
            stop_atr_multiple=optional_decimal("stop_atr_multiple")
            or optional_decimal("atr_stop_multiplier")
            or self.stop_atr_multiple,
            target_atr_multiple=optional_decimal("target_atr_multiple")
            or optional_decimal("take_profit_multiplier")
            or self.target_atr_multiple,
            minimum_rr=optional_decimal("minimum_rr") or self.minimum_rr,
            breakeven_trigger_r=optional_decimal("breakeven_trigger_r")
            if "breakeven_trigger_r" in values
            else self.breakeven_trigger_r,
            trailing_atr_multiple=optional_decimal("trailing_atr_multiple")
            or optional_decimal("trailing_multiplier")
            or self.trailing_atr_multiple,
            maximum_holding_bars=optional_int("maximum_holding_bars")
            if "maximum_holding_bars" in values
            else self.maximum_holding_bars,
        )


@dataclass(frozen=True, slots=True)
class StrategyRiskProfileRegistry:
    """Resolve exact or baseline virtual-market strategy risk profiles."""

    profiles: tuple[StrategyRiskProfile, ...]
    _by_key: Mapping[tuple[str, str | None], StrategyRiskProfile] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        by_key = {
            (
                item.strategy_id.strip(),
                None if item.regime is None else item.regime.strip().upper(),
            ): item
            for item in self.profiles
        }
        if len(by_key) != len(self.profiles):
            raise ValueError("strategy risk profile keys must be unique")
        object.__setattr__(self, "_by_key", MappingProxyType(by_key))

    def resolve(
        self,
        strategy_id: str,
        *,
        regime: str | None = None,
    ) -> StrategyRiskProfile:
        normalized_strategy = strategy_id.strip()
        normalized_regime = None if regime is None else regime.strip().upper()
        exact = self._by_key.get((normalized_strategy, normalized_regime))
        if exact is not None:
            return exact
        baseline = self._by_key.get((normalized_strategy, None))
        if baseline is not None:
            return baseline
        raise ValueError(f"strategy risk profile is not configured: {strategy_id}")


@dataclass(frozen=True, slots=True)
class VirtualStrategyDefinition:
    """Canonical virtual-market strategy family definition without authority."""

    strategy_id: str
    strategy_version: str
    supported_markets: tuple[str, ...]
    supported_regimes: tuple[str, ...]
    entry_rule: str
    invalidation_rule: str
    exit_rule: str
    risk_profile: str
    playbooks: tuple[str, ...]
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    bounded_simulation_only: bool = True

    def __post_init__(self) -> None:
        text_fields = (
            self.strategy_id,
            self.strategy_version,
            self.entry_rule,
            self.invalidation_rule,
            self.exit_rule,
            self.risk_profile,
            self.live_eligibility_status,
        )
        if any(not value.strip() for value in text_fields):
            raise ValueError("virtual strategy definition fields must be non-blank")
        if (
            not self.supported_markets
            or not self.supported_regimes
            or not self.playbooks
        ):
            raise ValueError(
                "virtual strategy definition requires markets, regimes, and playbooks"
            )
        if self.promotion_status is ValidationStatus.LIVE_ELIGIBLE:
            raise ValueError("virtual strategy definition cannot be live eligible")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("virtual strategy definition must remain live blocked")
        if not self.bounded_simulation_only:
            raise ValueError(
                "virtual strategy definition must remain bounded simulation only"
            )


@dataclass(frozen=True, slots=True)
class VirtualStrategyPortfolioRegistry:
    """Canonical bounded portfolio of virtual strategy families."""

    strategies: tuple[VirtualStrategyDefinition, ...]
    _by_id: Mapping[str, VirtualStrategyDefinition] = field(init=False, repr=False)
    _by_playbook: Mapping[str, VirtualStrategyDefinition] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        by_id = {item.strategy_id: item for item in self.strategies}
        if len(by_id) != len(self.strategies):
            raise ValueError("virtual strategy ids must be unique")
        playbook_pairs = {
            playbook: strategy
            for strategy in self.strategies
            for playbook in strategy.playbooks
        }
        if sum(len(item.playbooks) for item in self.strategies) != len(playbook_pairs):
            raise ValueError("virtual strategy playbooks must map to one family")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_by_playbook", MappingProxyType(playbook_pairs))

    def get(self, strategy_id: str) -> VirtualStrategyDefinition:
        return self._by_id[strategy_id]

    def resolve_playbook(self, playbook: str) -> VirtualStrategyDefinition:
        return self._by_playbook[playbook]

    def supports_playbook(self, playbook: str) -> bool:
        return playbook in self._by_playbook


_MISSING_PARAMETER_SET_REF = "PARAMETER_SET_NOT_BOUND"
_MISSING_DATASET_REVISION = "DATASET_REVISION_NOT_BOUND"
_MISSING_BACKTEST_REF = "BACKTEST_REF_NOT_BOUND"
_MISSING_WALK_FORWARD_REF = "WALK_FORWARD_REF_NOT_BOUND"
_MISSING_OOS_REF = "OOS_REF_NOT_BOUND"
_MISSING_ROBUSTNESS_REF = "ROBUSTNESS_REF_NOT_BOUND"
_MISSING_PAPER_REF = "PAPER_REF_NOT_BOUND"
_MISSING_EVIDENCE_FIELDS: Mapping[str, str] = MappingProxyType(
    {
        "parameter_set_ref": _MISSING_PARAMETER_SET_REF,
        "dataset_revision": _MISSING_DATASET_REVISION,
        "backtest_ref": _MISSING_BACKTEST_REF,
        "walk_forward_ref": _MISSING_WALK_FORWARD_REF,
        "oos_ref": _MISSING_OOS_REF,
        "robustness_ref": _MISSING_ROBUSTNESS_REF,
        "paper_ref": _MISSING_PAPER_REF,
    }
)


@dataclass(frozen=True, slots=True)
class GovernedStrategyRegistryEntry:
    """Canonical strategy-family promotion evidence contract."""

    strategy_id: str
    version: str
    implementation_ref: str
    parameter_set_ref: str
    market_scope: tuple[str, ...]
    regime_scope: tuple[str, ...]
    dataset_revision: str
    backtest_ref: str
    walk_forward_ref: str
    oos_ref: str
    robustness_ref: str
    paper_ref: str
    owner: str
    playbooks: tuple[str, ...]
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY

    def __post_init__(self) -> None:
        text_fields = (
            self.strategy_id,
            self.version,
            self.implementation_ref,
            self.parameter_set_ref,
            self.dataset_revision,
            self.backtest_ref,
            self.walk_forward_ref,
            self.oos_ref,
            self.robustness_ref,
            self.paper_ref,
            self.owner,
        )
        if any(not value.strip() for value in text_fields):
            raise ValueError("governed strategy registry fields must be non-blank")
        if not self.market_scope or not self.regime_scope or not self.playbooks:
            raise ValueError(
                "governed strategy registry requires markets, regimes, and playbooks"
            )
        if self.promotion_status is ValidationStatus.LIVE_ELIGIBLE:
            raise ValueError("governed strategy registry cannot grant live eligibility")
        if (
            self.promotion_status is ValidationStatus.PAPER_APPROVED
            and not self.paper_ready
        ):
            raise ValueError(
                "paper approval requires complete backtest, walk-forward, OOS, "
                "robustness, and paper evidence"
            )

    @property
    def evidence_complete(self) -> bool:
        return not self.missing_evidence_refs

    @property
    def missing_evidence_refs(self) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name, sentinel in _MISSING_EVIDENCE_FIELDS.items()
            if getattr(self, field_name) == sentinel
        )

    @property
    def paper_ready(self) -> bool:
        if not self.evidence_complete:
            return False
        validation_root = _resolve_evidence_root(self.paper_ref)
        if validation_root is None:
            return False
        representative = _resolve_evidence_path(self.backtest_ref)
        if representative is None:
            return False
        symbol = _infer_validation_symbol(representative)
        if symbol is None:
            return False
        summary = ValidationSummaryReader(validation_root).summarize(symbol)
        statuses = {run.playbook: run.promotion_status for run in summary.runs}
        return all(
            statuses.get(playbook) == ValidationStatus.PAPER_APPROVED.value
            for playbook in self.playbooks
        )


@dataclass(frozen=True, slots=True)
class GovernedStrategyRegistry:
    """Resolve canonical strategy-family evidence completeness by id or playbook."""

    strategies: tuple[GovernedStrategyRegistryEntry, ...]
    _by_id: Mapping[str, GovernedStrategyRegistryEntry] = field(
        init=False,
        repr=False,
    )
    _by_playbook: Mapping[str, GovernedStrategyRegistryEntry] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        by_id = {item.strategy_id: item for item in self.strategies}
        if len(by_id) != len(self.strategies):
            raise ValueError("governed strategy ids must be unique")
        playbook_pairs = {
            playbook: strategy
            for strategy in self.strategies
            for playbook in strategy.playbooks
        }
        if sum(len(item.playbooks) for item in self.strategies) != len(playbook_pairs):
            raise ValueError("governed strategy playbooks must map to one family")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_by_playbook", MappingProxyType(playbook_pairs))

    def get(self, strategy_id: str) -> GovernedStrategyRegistryEntry:
        return self._by_id[strategy_id]

    def resolve_playbook(self, playbook: str) -> GovernedStrategyRegistryEntry:
        return self._by_playbook[playbook]

    def with_promotion(
        self,
        strategy_id: str,
        status: ValidationStatus,
    ) -> "GovernedStrategyRegistry":
        if status is not ValidationStatus.PAPER_APPROVED:
            raise ValueError("governed strategy registry promotion is paper-only")
        current = self.get(strategy_id)
        if not current.paper_ready:
            raise ValueError(
                "paper approval requires complete backtest, walk-forward, OOS, "
                "robustness, and paper evidence"
            )
        return GovernedStrategyRegistry(
            tuple(
                replace(item, promotion_status=status)
                if item.strategy_id == strategy_id
                else item
                for item in self.strategies
            )
        )


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

_COMPATIBLE_REGIMES_BY_PLAYBOOK: Mapping[str, tuple[str, ...]] = {
    "trend_continuation": ("TREND",),
    "pullback_continuation": ("TREND",),
    "breakout_retest": ("TREND", "HIGH_VOLATILITY"),
    "support_reclaim": ("TREND", "RANGE"),
    "resistance_rejection": ("TREND", "RANGE"),
    "failed_breakout_reversal": ("RANGE", "HIGH_VOLATILITY"),
    "range_rotation": ("RANGE",),
    "volatility_expansion": ("HIGH_VOLATILITY",),
    "compression_breakout": ("RANGE", "HIGH_VOLATILITY"),
    "smc_liquidity_sweep_reversal": ("RANGE", "HIGH_VOLATILITY"),
}

_DEFAULT_STRATEGY_RISK_PROFILE_VERSION = "1"
_DEFAULT_STOP_ATR_MULTIPLE = Decimal("1.5")
_DEFAULT_TARGET_ATR_MULTIPLE = Decimal("3.0")
_DEFAULT_MINIMUM_RR = Decimal("2.0")
_DEFAULT_TRAILING_ATR_MULTIPLE = Decimal("1.5")
_DEFAULT_VIRTUAL_STRATEGY_VERSION = "1"
_DEFAULT_GOVERNED_STRATEGY_OWNER = "Enterprise Strategy Governance"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_VALIDATION_ARTIFACT_ROOT_REF = "runtime/artifacts/research/backtest/validation"
_IMPLEMENTATION_REF_BY_STRATEGY_ID: Mapping[str, str] = MappingProxyType(
    {
        "TREND_PULLBACK": (
            "ai4binance.strategies.registry:"
            "build_virtual_strategy_portfolio_registry#TREND_PULLBACK"
        ),
        "BREAKOUT_RETEST": (
            "ai4binance.strategies.registry:"
            "build_virtual_strategy_portfolio_registry#BREAKOUT_RETEST"
        ),
        "MOMENTUM_CONTINUATION": (
            "ai4binance.strategies.registry:"
            "build_virtual_strategy_portfolio_registry#MOMENTUM_CONTINUATION"
        ),
        "MEAN_REVERSION": (
            "ai4binance.strategies.registry:"
            "build_virtual_strategy_portfolio_registry#MEAN_REVERSION"
        ),
    }
)
_GOVERNED_STRATEGY_EVIDENCE_BUNDLES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "TREND_PULLBACK": {
            "symbol": "HOTUSDT",
            "timeframe": "1h",
            "playbook": "support_reclaim",
        },
        "BREAKOUT_RETEST": {
            "symbol": "HOTUSDT",
            "timeframe": "1h",
            "playbook": "breakout_retest",
        },
        "MOMENTUM_CONTINUATION": {
            "symbol": "HOTUSDT",
            "timeframe": "1h",
            "playbook": "trend_continuation",
        },
        "MEAN_REVERSION": {
            "symbol": "HOTUSDT",
            "timeframe": "1h",
            "playbook": "failed_breakout_reversal",
        },
    }
)


def _resolve_evidence_path(ref: str) -> Path | None:
    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate
    resolved = _REPOSITORY_ROOT / candidate
    return resolved if resolved.exists() else None


def _resolve_evidence_root(ref: str) -> Path | None:
    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    resolved = _REPOSITORY_ROOT / candidate
    return resolved if resolved.exists() else None


def _infer_validation_symbol(path: Path) -> str | None:
    parts = path.parts
    try:
        index = parts.index("validation")
    except ValueError:
        return None
    if index + 2 >= len(parts):
        return None
    symbol = parts[index + 1].strip().upper()
    if not symbol or not parts[index + 2].strip():
        return None
    return symbol


def _strategy_evidence_refs(strategy_id: str) -> Mapping[str, str]:
    bundle = _GOVERNED_STRATEGY_EVIDENCE_BUNDLES[strategy_id]
    run_card_ref = (
        f"{_VALIDATION_ARTIFACT_ROOT_REF}/"
        f"{bundle['symbol']}/{bundle['timeframe']}/{bundle['playbook']}.run-card.json"
    )
    return MappingProxyType(
        {
            "parameter_set_ref": run_card_ref,
            "dataset_revision": _VALIDATION_ARTIFACT_ROOT_REF,
            "backtest_ref": run_card_ref,
            "walk_forward_ref": _VALIDATION_ARTIFACT_ROOT_REF,
            "oos_ref": _VALIDATION_ARTIFACT_ROOT_REF,
            "robustness_ref": _VALIDATION_ARTIFACT_ROOT_REF,
            "paper_ref": _VALIDATION_ARTIFACT_ROOT_REF,
        }
    )


def _governed_strategy_entry(
    strategy: VirtualStrategyDefinition,
) -> GovernedStrategyRegistryEntry:
    evidence_refs = _strategy_evidence_refs(strategy.strategy_id)
    return GovernedStrategyRegistryEntry(
        strategy_id=strategy.strategy_id,
        version=strategy.strategy_version,
        implementation_ref=_IMPLEMENTATION_REF_BY_STRATEGY_ID[strategy.strategy_id],
        parameter_set_ref=evidence_refs["parameter_set_ref"],
        market_scope=strategy.supported_markets,
        regime_scope=strategy.supported_regimes,
        dataset_revision=evidence_refs["dataset_revision"],
        backtest_ref=evidence_refs["backtest_ref"],
        walk_forward_ref=evidence_refs["walk_forward_ref"],
        oos_ref=evidence_refs["oos_ref"],
        robustness_ref=evidence_refs["robustness_ref"],
        paper_ref=evidence_refs["paper_ref"],
        owner=_DEFAULT_GOVERNED_STRATEGY_OWNER,
        playbooks=strategy.playbooks,
        promotion_status=ValidationStatus.RESEARCH_ONLY,
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
            compatible_regimes=_COMPATIBLE_REGIMES_BY_PLAYBOOK.get(
                name,
                ("ALL_VALIDATED_REGIMES",),
            ),
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


def build_strategy_risk_profile_registry() -> StrategyRiskProfileRegistry:
    """Return canonical baseline exit profiles for virtual-market research."""

    return StrategyRiskProfileRegistry(
        tuple(
            StrategyRiskProfile(
                strategy_id=name,
                version=_DEFAULT_STRATEGY_RISK_PROFILE_VERSION,
                stop_atr_multiple=_DEFAULT_STOP_ATR_MULTIPLE,
                target_atr_multiple=_DEFAULT_TARGET_ATR_MULTIPLE,
                minimum_rr=_DEFAULT_MINIMUM_RR,
                trailing_atr_multiple=_DEFAULT_TRAILING_ATR_MULTIPLE,
            )
            for name in _PLAYBOOK_NAMES
        )
    )


def build_virtual_strategy_portfolio_registry() -> VirtualStrategyPortfolioRegistry:
    """Return the bounded canonical virtual-market strategy family portfolio."""

    return VirtualStrategyPortfolioRegistry(
        (
            VirtualStrategyDefinition(
                strategy_id="TREND_PULLBACK",
                strategy_version=_DEFAULT_VIRTUAL_STRATEGY_VERSION,
                supported_markets=("SPOT", "USD_M_FUTURES"),
                supported_regimes=("TREND_UP",),
                entry_rule="PULLBACK_CONTINUATION_CONFIRMATION",
                invalidation_rule="TREND_STRUCTURE_BREAK",
                exit_rule="ATR_TARGETS_AND_TRAILING_EXIT",
                risk_profile="TREND_PULLBACK_V1",
                playbooks=("pullback_continuation", "support_reclaim"),
            ),
            VirtualStrategyDefinition(
                strategy_id="BREAKOUT_RETEST",
                strategy_version=_DEFAULT_VIRTUAL_STRATEGY_VERSION,
                supported_markets=("SPOT", "USD_M_FUTURES"),
                supported_regimes=("TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY"),
                entry_rule="BREAKOUT_RETEST_CONFIRMATION",
                invalidation_rule="FAILED_RECLAIM_OR_RETEST_LOSS",
                exit_rule="R_MULTIPLE_TARGETS_AND_TRAILING_EXIT",
                risk_profile="BREAKOUT_RETEST_V1",
                playbooks=("breakout_retest", "compression_breakout"),
            ),
            VirtualStrategyDefinition(
                strategy_id="MOMENTUM_CONTINUATION",
                strategy_version=_DEFAULT_VIRTUAL_STRATEGY_VERSION,
                supported_markets=("SPOT", "USD_M_FUTURES"),
                supported_regimes=("TREND_UP", "TREND_DOWN"),
                entry_rule="MOMENTUM_EXPANSION_WITH_CONFLUENCE",
                invalidation_rule="MOMENTUM_FAILURE_OR_STRUCTURE_BREAK",
                exit_rule="TREND_EXTENSION_TARGETS_AND_TRAILING_EXIT",
                risk_profile="MOMENTUM_CONTINUATION_V1",
                playbooks=("trend_continuation", "volatility_expansion"),
            ),
            VirtualStrategyDefinition(
                strategy_id="MEAN_REVERSION",
                strategy_version=_DEFAULT_VIRTUAL_STRATEGY_VERSION,
                supported_markets=("SPOT", "USD_M_FUTURES"),
                supported_regimes=("RANGE",),
                entry_rule="EXTREME_DISLOCATION_REVERSION_CONFIRMATION",
                invalidation_rule="RANGE_LOSS_OR_FAILED_REVERSAL",
                exit_rule="MID_RANGE_OR_2R_MEAN_REVERSION_EXIT",
                risk_profile="MEAN_REVERSION_V1",
                playbooks=(
                    "range_rotation",
                    "resistance_rejection",
                    "failed_breakout_reversal",
                    "smc_liquidity_sweep_reversal",
                    "mean_reversion",
                ),
            ),
        )
    )


def build_governed_strategy_registry() -> GovernedStrategyRegistry:
    """Return canonical strategy-family evidence contracts for paper promotion."""

    portfolio = build_virtual_strategy_portfolio_registry()
    return GovernedStrategyRegistry(
        tuple(_governed_strategy_entry(strategy) for strategy in portfolio.strategies)
    )

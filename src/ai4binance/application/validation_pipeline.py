"""Archived-data backtest, walk-forward and tuning validation pipeline."""
# ruff: noqa: ANN401

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Protocol, cast

from ai4binance.domain import ValidationStatus

VALIDATED_PLAYBOOKS = (
    "trend_continuation",
    "pullback_continuation",
    "breakout_retest",
    "support_reclaim",
    "resistance_rejection",
    "failed_breakout_reversal",
)
MINIMUM_VALIDATION_CANDLES = 60


class StrategyRiskProfileLike(Protocol):
    version: str
    config_hash: str
    stop_atr_multiple: Decimal
    target_atr_multiple: Decimal
    minimum_rr: Decimal
    breakeven_trigger_r: Decimal | None
    trailing_atr_multiple: Decimal | None
    maximum_holding_bars: int | None

    def with_parameter_overrides(
        self,
        values: dict[str, object],
    ) -> Any: ...


class StrategyRiskProfileRegistryLike(Protocol):
    def resolve(
        self,
        strategy_id: str,
        *,
        regime: str | None = None,
    ) -> Any: ...


def _build_strategy_risk_profile_registry() -> StrategyRiskProfileRegistryLike:
    registry_module = import_module("ai4binance.strategies.registry")
    return cast(
        StrategyRiskProfileRegistryLike,
        registry_module.build_strategy_risk_profile_registry(),
    )


class CandleLike(Protocol):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class ParameterSetLike(Protocol):
    name: str
    values: tuple[tuple[str, object], ...]


class HistoricalDecisionLike(Protocol):
    triggered: bool
    blockers: tuple[str, ...]


class ValidationArchiveLike(Protocol):
    def read(self, symbol: str, timeframe: str) -> tuple[Any, ...]: ...


class ValidationRuntimeLike(Protocol):
    def start_validation_run(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        *,
        artifact_directory: Path,
    ) -> str: ...

    def record_timeframe_ready(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        candle_count: int,
        *,
        artifact_directory: Path,
        dataset_sha256: str,
        config_sha256: str,
        implementation_sha256: str,
        stage_timings_ms: tuple[tuple[str, float], ...],
    ) -> None: ...

    def ensure_playbook_implemented(self, playbook: str) -> None: ...

    def dataset_sha256(self, candles: tuple[Any, ...]) -> str: ...

    def config_sha256(self, candle_count: int) -> str: ...

    def implementation_sha256(self) -> str: ...

    def load_checkpoint(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[Any, ...],
        *,
        artifact_directory: Path,
        dataset_sha256: str,
        config_sha256: str,
        implementation_sha256: str,
    ) -> PlaybookValidationResult | None: ...

    def validate_one(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[Any, ...],
        *,
        artifact_directory: Path,
    ) -> PlaybookValidationResult: ...

    def write_checkpoint(
        self,
        symbol: str,
        result: PlaybookValidationResult,
        *,
        dataset_sha256: str,
        config_sha256: str,
        implementation_sha256: str,
    ) -> None: ...

    def record_playbook_terminal(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        playbook: str,
        result: PlaybookValidationResult | None,
        *,
        artifact_directory: Path,
        checkpoint_status: str,
        terminal_status: str,
        stage_timings_ms: tuple[tuple[str, float], ...],
        failure_code: str | None = None,
    ) -> None: ...

    def finish_validation_run(
        self,
        run_id: str,
        symbol: str,
        *,
        artifact_directory: Path,
        terminal_status: str,
    ) -> None: ...

    def persist_blocker_dashboard(
        self,
        batch: ValidationBatchResult,
        *,
        artifact_directory: Path,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PlaybookValidationResult:
    """One playbook/timeframe evidence result with no execution authority."""

    playbook: str
    timeframe: str
    candle_count: int
    promotion_status: ValidationStatus
    blockers: tuple[str, ...]
    backtest: object | None = None
    tuning: object | None = None
    robustness: object | None = None
    run_card: object | None = None
    signal_blockers: tuple[tuple[str, int], ...] = ()
    artifact_path: str | None = None
    checkpoint_path: str | None = None
    resumed_from_checkpoint: bool = False
    stage_timings_ms: tuple[tuple[str, float], ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("validation evidence cannot grant execution authority")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError("validation may only produce research or staged status")
        stage_names = tuple(name for name, _ in self.stage_timings_ms)
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("validation stage timing names must be unique")
        if any(
            not name.strip() or duration < 0 for name, duration in self.stage_timings_ms
        ):
            raise ValueError("validation stage timings must be named and non-negative")


@dataclass(frozen=True, slots=True)
class ValidationBatchResult:
    """Deterministic cross-timeframe validation batch."""

    symbol: str
    results: tuple[PlaybookValidationResult, ...]
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        invalid_authority = (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        )
        if invalid_authority:
            raise ValueError("validation batch must remain execution blocked")


@dataclass(slots=True)
class HistoricalPlaybookAdapter:
    """Long-only deterministic adapter for implemented research playbooks."""

    playbook: str
    parameters: Any
    decision_resolver: Callable[..., Any]
    atr_calculator: Callable[..., Decimal]
    intent_builder: Callable[..., Any]
    symbol: str = "UNKNOWN_SYMBOL"
    timeframe: str = "UNKNOWN"
    strategy_version: str = "1"
    market: str = "SPOT"
    regime_classifier: Callable[[Any], Any] | None = None
    risk_profile_registry: StrategyRiskProfileRegistryLike = field(
        default_factory=_build_strategy_risk_profile_registry
    )
    _history_length: int = field(init=False, default=0, repr=False)
    _last_timestamp: datetime | None = field(init=False, default=None, repr=False)
    _current_atr: Decimal | None = field(init=False, default=None, repr=False)
    _blocker_counts: dict[str, int] = field(
        init=False,
        default_factory=dict,
        repr=False,
    )

    def __call__(
        self,
        history: tuple[Any, ...],
    ) -> Any | None:
        current_atr = self._update_atr(history)
        decision = self.decision_resolver(self.playbook, history)
        if not decision.triggered:
            self._blocker_counts[decision.regime_strategy_reason_code] = (
                self._blocker_counts.get(decision.regime_strategy_reason_code, 0) + 1
            )
            for blocker in decision.blockers:
                self._blocker_counts[blocker] = self._blocker_counts.get(blocker, 0) + 1
            return None
        values = dict(self.parameters.values)
        if current_atr is None:
            return None
        regime = "UNKNOWN"
        if self.regime_classifier is not None:
            classified_regime = self.regime_classifier(history[-1])
            regime = getattr(classified_regime, "value", str(classified_regime))
        try:
            profile = self.risk_profile_registry.resolve(
                self.playbook,
                regime=regime,
            ).with_parameter_overrides(values)
        except ValueError:
            blocker = "STRATEGY_RISK_PROFILE_UNCONFIGURED"
            self._blocker_counts[blocker] = self._blocker_counts.get(blocker, 0) + 1
            return None
        close = history[-1].close
        stop_multiplier = profile.stop_atr_multiple
        target_multiplier = profile.target_atr_multiple
        realized_rr = target_multiplier / stop_multiplier
        if realized_rr < profile.minimum_rr:
            blocker = "MINIMUM_RISK_REWARD_NOT_SATISFIED"
            self._blocker_counts[blocker] = self._blocker_counts.get(blocker, 0) + 1
            return None
        if current_atr <= 0 or close <= current_atr * stop_multiplier:
            return None
        expected_move_ratio = current_atr * target_multiplier / close
        minimum_edge_ratio = Decimal("0.009")
        if expected_move_ratio < minimum_edge_ratio:
            blocker = "EXPECTED_EDGE_BELOW_COST_BUFFER"
            self._blocker_counts[blocker] = self._blocker_counts.get(blocker, 0) + 1
            return None
        timestamp = history[-1].timestamp
        digest = sha256(
            f"{self.playbook}|{self.parameters.name}|{timestamp.isoformat()}".encode()
        ).hexdigest()[:16]
        lineage_suffix = f"{profile.version}:{profile.config_hash[:12]}"
        return self.intent_builder(
            signal_id=f"historical:{digest}",
            timestamp=timestamp,
            stop_loss=close - current_atr * stop_multiplier,
            take_profit=close + current_atr * target_multiplier,
            atr=current_atr,
            reason_codes=(
                f"PLAYBOOK:{self.playbook}",
                "CLOSED_CANDLE_SIGNAL",
                decision.regime_strategy_reason_code,
            ),
            strategy_id=self.playbook,
            strategy_version=self.strategy_version,
            strategy_config_version=profile.version,
            strategy_config_hash=profile.config_hash,
            market=self.market,
            symbol=self.symbol,
            regime=regime,
            timeframe=self.timeframe,
            snapshot_id=f"snapshot:{digest}:{lineage_suffix}",
            decision_id=f"decision:{digest}:{lineage_suffix}",
            breakeven_trigger_r=profile.breakeven_trigger_r,
            trailing_atr_multiple=profile.trailing_atr_multiple,
            maximum_holding_bars=profile.maximum_holding_bars,
            funnel_stages=("DISCOVERED", "READY_FOR_RISK"),
        )

    @property
    def blocker_counts(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._blocker_counts.items()))

    def _update_atr(
        self,
        history: tuple[Any, ...],
    ) -> Decimal | None:
        period = 14
        if len(history) < period + 1:
            return None
        sequential = (
            self._current_atr is not None
            and len(history) == self._history_length + 1
            and history[-2].timestamp == self._last_timestamp
        )
        if sequential:
            previous_atr = self._current_atr
            if previous_atr is None:
                raise RuntimeError("sequential ATR state is unavailable")
            previous, current = history[-2], history[-1]
            true_range = max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
            self._current_atr = (
                previous_atr * Decimal(period - 1) + true_range
            ) / Decimal(period)
        else:
            self._current_atr = self.atr_calculator(history, period)
        self._history_length = len(history)
        self._last_timestamp = history[-1].timestamp
        return self._current_atr


@dataclass(frozen=True, slots=True)
class ResearchValidationService:
    """Run governed historical validation against checksum-verified archives."""

    archive: Any
    artifact_directory: Path
    runtime: Any

    def run(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
    ) -> ValidationBatchResult:
        """Validate implemented playbooks across every requested timeframe."""
        results: list[PlaybookValidationResult] = []
        normalized_symbol = symbol.strip().upper()
        run_id = self.runtime.start_validation_run(
            normalized_symbol,
            timeframes,
            artifact_directory=self.artifact_directory,
        )
        try:
            for timeframe in timeframes:
                stage_started = perf_counter_ns()
                candles = self.archive.read(normalized_symbol, timeframe)
                archive_read_ms = _elapsed_ms(stage_started)
                stage_started = perf_counter_ns()
                dataset_sha256 = self.runtime.dataset_sha256(candles)
                dataset_hash_ms = _elapsed_ms(stage_started)
                stage_started = perf_counter_ns()
                config_sha256 = self.runtime.config_sha256(len(candles))
                config_hash_ms = _elapsed_ms(stage_started)
                stage_started = perf_counter_ns()
                implementation_sha256 = self.runtime.implementation_sha256()
                implementation_hash_ms = _elapsed_ms(stage_started)
                self.runtime.record_timeframe_ready(
                    run_id,
                    normalized_symbol,
                    timeframe,
                    len(candles),
                    artifact_directory=self.artifact_directory,
                    dataset_sha256=dataset_sha256,
                    config_sha256=config_sha256,
                    implementation_sha256=implementation_sha256,
                    stage_timings_ms=(
                        ("archive_read", archive_read_ms),
                        ("dataset_hash", dataset_hash_ms),
                        ("config_hash", config_hash_ms),
                        ("implementation_hash", implementation_hash_ms),
                    ),
                )
                for playbook in VALIDATED_PLAYBOOKS:
                    self.runtime.ensure_playbook_implemented(playbook)
                    checkpoint_started = perf_counter_ns()
                    checkpoint = self.runtime.load_checkpoint(
                        normalized_symbol,
                        timeframe,
                        playbook,
                        candles,
                        artifact_directory=self.artifact_directory,
                        dataset_sha256=dataset_sha256,
                        config_sha256=config_sha256,
                        implementation_sha256=implementation_sha256,
                    )
                    checkpoint_ms = _elapsed_ms(checkpoint_started)
                    if checkpoint is not None:
                        resumed = replace(
                            checkpoint,
                            stage_timings_ms=(("checkpoint_lookup", checkpoint_ms),),
                        )
                        results.append(resumed)
                        self.runtime.record_playbook_terminal(
                            run_id,
                            normalized_symbol,
                            timeframe,
                            playbook,
                            resumed,
                            artifact_directory=self.artifact_directory,
                            checkpoint_status="HIT",
                            terminal_status="COMPLETED_FROM_CHECKPOINT",
                            stage_timings_ms=resumed.stage_timings_ms,
                        )
                        continue
                    try:
                        result = self.runtime.validate_one(
                            normalized_symbol,
                            timeframe,
                            playbook,
                            candles,
                            artifact_directory=self.artifact_directory,
                        )
                        result = replace(
                            result,
                            stage_timings_ms=(
                                ("checkpoint_lookup", checkpoint_ms),
                                *result.stage_timings_ms,
                            ),
                        )
                        results.append(result)
                        if result.artifact_path is not None:
                            checkpoint_write_started = perf_counter_ns()
                            self.runtime.write_checkpoint(
                                normalized_symbol,
                                result,
                                dataset_sha256=dataset_sha256,
                                config_sha256=config_sha256,
                                implementation_sha256=implementation_sha256,
                            )
                            result = replace(
                                result,
                                stage_timings_ms=(
                                    *result.stage_timings_ms,
                                    (
                                        "checkpoint_write",
                                        _elapsed_ms(checkpoint_write_started),
                                    ),
                                ),
                            )
                            results[-1] = result
                    except (Exception, KeyboardInterrupt) as exc:
                        self.runtime.record_playbook_terminal(
                            run_id,
                            normalized_symbol,
                            timeframe,
                            playbook,
                            None,
                            artifact_directory=self.artifact_directory,
                            checkpoint_status="MISS",
                            terminal_status="FAILED",
                            stage_timings_ms=(("checkpoint_lookup", checkpoint_ms),),
                            failure_code=type(exc).__name__,
                        )
                        raise
                    self.runtime.record_playbook_terminal(
                        run_id,
                        normalized_symbol,
                        timeframe,
                        playbook,
                        result,
                        artifact_directory=self.artifact_directory,
                        checkpoint_status="MISS",
                        terminal_status="COMPLETED",
                        stage_timings_ms=result.stage_timings_ms,
                    )
        except (Exception, KeyboardInterrupt):
            self.runtime.finish_validation_run(
                run_id,
                normalized_symbol,
                artifact_directory=self.artifact_directory,
                terminal_status="FAILED",
            )
            raise
        batch = ValidationBatchResult(symbol.strip().upper(), tuple(results))
        self.runtime.persist_blocker_dashboard(
            batch,
            artifact_directory=self.artifact_directory,
        )
        self.runtime.finish_validation_run(
            run_id,
            normalized_symbol,
            artifact_directory=self.artifact_directory,
            terminal_status="COMPLETED",
        )
        return batch


def _elapsed_ms(started_ns: int) -> float:
    return round((perf_counter_ns() - started_ns) / 1_000_000, 3)

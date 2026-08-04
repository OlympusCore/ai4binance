"""Archived-data backtest, walk-forward and tuning validation pipeline."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from ai4binance.backtest import (
    BacktestEngine,
    BacktestIntent,
    BacktestRobustnessAnalyzer,
    BacktestRobustnessReport,
)
from ai4binance.backtest.models import BacktestResult
from ai4binance.backtest.storage import BacktestAuditWriter, BacktestRobustnessWriter
from ai4binance.data import ParquetOHLCVArchive
from ai4binance.domain import ValidationStatus
from ai4binance.indicators import atr
from ai4binance.reporting import to_primitive
from ai4binance.research_governance import (
    ResearchBlockerDashboardWriter,
    ResearchBlockerObservation,
    ResearchRunCard,
    ResearchRunCardWriter,
    build_research_blocker_dashboard,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage import JsonlAuditStore
from ai4binance.storage.destination_verification import (
    DestinationVerificationError,
    read_json_object,
    write_json_object_verified,
)
from ai4binance.strategies.registry import build_playbook_registry
from ai4binance.strategies.rules import historical_playbook_decision
from ai4binance.tuning import (
    ParameterDomain,
    SearchSpace,
    TuningConfig,
    TuningEngine,
    TuningReport,
)
from ai4binance.tuning.storage import TuningAuditWriter
from ai4binance.validation import MarketRegime, ParameterSet, WalkForwardConfig
from ai4binance.validation.storage import WalkForwardAuditWriter

VALIDATED_PLAYBOOKS = (
    "trend_continuation",
    "pullback_continuation",
    "breakout_retest",
    "support_reclaim",
    "resistance_rejection",
    "failed_breakout_reversal",
)
MINIMUM_VALIDATION_CANDLES = 60


@dataclass(frozen=True, slots=True)
class PlaybookValidationResult:
    """One playbook/timeframe evidence result with no execution authority."""

    playbook: str
    timeframe: str
    candle_count: int
    promotion_status: ValidationStatus
    blockers: tuple[str, ...]
    backtest: BacktestResult | None = None
    tuning: TuningReport | None = None
    robustness: BacktestRobustnessReport | None = None
    run_card: ResearchRunCard | None = None
    signal_blockers: tuple[tuple[str, int], ...] = ()
    artifact_path: str | None = None
    checkpoint_path: str | None = None
    resumed_from_checkpoint: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("validation evidence cannot grant execution authority")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError("validation may only produce research or staged status")


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
    parameters: ParameterSet
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
        history: tuple[OHLCVCandle, ...],
    ) -> BacktestIntent | None:
        current_atr = self._update_atr(history)
        decision = historical_playbook_decision(self.playbook, history)
        if not decision.triggered:
            for blocker in decision.blockers:
                self._blocker_counts[blocker] = self._blocker_counts.get(blocker, 0) + 1
            return None
        values = dict(self.parameters.values)
        if current_atr is None:
            return None
        close = history[-1].close
        stop_multiplier = Decimal(str(values["atr_stop_multiplier"]))
        target_multiplier = Decimal(str(values["take_profit_multiplier"]))
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
        return BacktestIntent(
            signal_id=f"historical:{digest}",
            timestamp=timestamp,
            stop_loss=close - current_atr * stop_multiplier,
            take_profit=close + current_atr * target_multiplier,
            atr=current_atr,
            reason_codes=(f"PLAYBOOK:{self.playbook}", "CLOSED_CANDLE_SIGNAL"),
        )

    @property
    def blocker_counts(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._blocker_counts.items()))

    def _update_atr(
        self,
        history: tuple[OHLCVCandle, ...],
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
            self._current_atr = atr(history, period)
        self._history_length = len(history)
        self._last_timestamp = history[-1].timestamp
        return self._current_atr


@dataclass(frozen=True, slots=True)
class ResearchValidationService:
    """Run governed historical validation against checksum-verified archives."""

    archive: ParquetOHLCVArchive
    artifact_directory: Path
    backtest_engine: BacktestEngine = field(default_factory=BacktestEngine)
    tuning_engine: TuningEngine = field(default_factory=TuningEngine)

    def run(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
    ) -> ValidationBatchResult:
        """Validate implemented playbooks across every requested timeframe."""
        registry = build_playbook_registry()
        results: list[PlaybookValidationResult] = []
        for timeframe in timeframes:
            candles = self.archive.read(symbol, timeframe)
            dataset_sha256 = self._hash_candles(candles)
            config_sha256 = self._config_sha256(len(candles))
            implementation_sha256 = self._implementation_sha256()
            for playbook in VALIDATED_PLAYBOOKS:
                if not registry.get(playbook).implemented:
                    raise ValueError(f"playbook is not implemented: {playbook}")
                checkpoint = self._load_checkpoint(
                    symbol,
                    timeframe,
                    playbook,
                    candles,
                    dataset_sha256=dataset_sha256,
                    config_sha256=config_sha256,
                    implementation_sha256=implementation_sha256,
                )
                if checkpoint is not None:
                    results.append(checkpoint)
                    continue
                result = self._validate_one(symbol, timeframe, playbook, candles)
                results.append(result)
                if result.artifact_path is not None:
                    self._write_checkpoint(
                        symbol,
                        result,
                        dataset_sha256=dataset_sha256,
                        config_sha256=config_sha256,
                        implementation_sha256=implementation_sha256,
                    )
        batch = ValidationBatchResult(symbol.strip().upper(), tuple(results))
        self._persist_blocker_dashboard(batch)
        return batch

    def _validate_one(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[OHLCVCandle, ...],
    ) -> PlaybookValidationResult:
        preflight = self._preflight(playbook, candles)
        if preflight:
            return PlaybookValidationResult(
                playbook,
                timeframe,
                len(candles),
                ValidationStatus.RESEARCH_ONLY,
                preflight,
            )
        baseline_parameters = ParameterSet(
            "baseline",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        )
        baseline_provider = HistoricalPlaybookAdapter(playbook, baseline_parameters)
        backtest = self.backtest_engine.run(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            signal_provider=baseline_provider,
        )
        tuning = self.tuning_engine.tune(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            search_space=self._search_space(),
            strategy_factory=lambda parameters: HistoricalPlaybookAdapter(
                playbook, parameters
            ),
            regime_classifier=self._regime,
            config=self._tuning_config(len(candles)),
        )
        robustness = BacktestRobustnessAnalyzer().analyze(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            provider_factory=lambda: HistoricalPlaybookAdapter(
                playbook,
                tuning.selected_parameters,
            ),
        )
        blockers = tuple(dict.fromkeys((*tuning.blockers, *robustness.blockers)))
        promotion_status = (
            ValidationStatus.STAGED_CANDIDATE
            if not blockers
            else ValidationStatus.RESEARCH_ONLY
        )
        run_card = self._persist(
            symbol,
            timeframe,
            playbook,
            candles,
            backtest,
            tuning,
            robustness,
            blockers,
            promotion_status,
        )
        artifact_path = self._artifact_path(symbol, timeframe, playbook)
        return PlaybookValidationResult(
            playbook=playbook,
            timeframe=timeframe,
            candle_count=len(candles),
            promotion_status=promotion_status,
            blockers=blockers,
            backtest=backtest,
            tuning=tuning,
            robustness=robustness,
            run_card=run_card,
            signal_blockers=baseline_provider.blocker_counts,
            artifact_path=str(artifact_path),
            checkpoint_path=str(self._checkpoint_path(artifact_path)),
        )

    @staticmethod
    def _preflight(
        playbook: str,
        candles: tuple[OHLCVCandle, ...],
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if len(candles) < MINIMUM_VALIDATION_CANDLES:
            blockers.append("INSUFFICIENT_VALIDATION_CANDLES")
        if playbook == "resistance_rejection":
            blockers.append("HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED")
        return tuple(blockers)

    @staticmethod
    def _search_space() -> SearchSpace:
        return SearchSpace(
            (
                ParameterDomain("atr_stop_multiplier", (1.25, 1.5, 1.75)),
                ParameterDomain("take_profit_multiplier", (2.5, 3.0, 3.5)),
            )
        )

    @staticmethod
    def _tuning_config(candle_count: int) -> TuningConfig:
        test_size = max(10, candle_count // 8)
        train_size = candle_count - (test_size * 5)
        return TuningConfig(
            WalkForwardConfig(
                train_size=train_size,
                test_size=test_size,
                step_size=test_size,
                min_folds=5,
                min_oos_trades=5,
                min_regime_count=2,
            ),
            min_neighbor_count=2,
            min_neighbor_pass_ratio=0.5,
            min_neighbor_return_ratio=0.5,
        )

    @staticmethod
    def _regime(candle: OHLCVCandle) -> MarketRegime:
        if candle.open > 0 and (candle.high - candle.low) / candle.open >= Decimal(
            "0.03"
        ):
            return MarketRegime.HIGH_VOLATILITY
        if candle.close > candle.open:
            return MarketRegime.TREND
        return MarketRegime.RANGE

    def _persist(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[OHLCVCandle, ...],
        backtest: BacktestResult,
        tuning: TuningReport,
        robustness: BacktestRobustnessReport,
        blockers: tuple[str, ...],
        promotion_status: ValidationStatus,
    ) -> ResearchRunCard:
        path = self._artifact_path(symbol, timeframe, playbook)
        store = JsonlAuditStore(path)
        BacktestAuditWriter(store).append(backtest)
        WalkForwardAuditWriter(store).append(
            next(
                evaluation.walk_forward_report
                for evaluation in tuning.evaluations
                if evaluation.parameters == tuning.selected_parameters
            )
        )
        TuningAuditWriter(store).append(tuning)
        BacktestRobustnessWriter(store).append(robustness, tuning.created_at)
        card = self._build_run_card(
            symbol,
            timeframe,
            playbook,
            candles,
            backtest,
            tuning,
            robustness,
            path,
            blockers,
            promotion_status,
        )
        ResearchRunCardWriter(
            path.with_name(f"{playbook}.run-card.json"),
            JsonlAuditStore(self.artifact_directory / "research_run_cards.jsonl"),
        ).write(card)
        return card

    def _build_run_card(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[OHLCVCandle, ...],
        backtest: BacktestResult,
        tuning: TuningReport,
        robustness: BacktestRobustnessReport,
        artifact_path: Path,
        blockers: tuple[str, ...],
        promotion_status: ValidationStatus,
    ) -> ResearchRunCard:
        metrics = backtest.metrics
        artifact_digest = sha256(artifact_path.read_bytes()).hexdigest()
        run_digest = sha256(
            f"{symbol.upper()}|{timeframe}|{playbook}|{tuning.report_id}".encode()
        ).hexdigest()[:16]
        return ResearchRunCard(
            run_id=f"run:{run_digest}",
            created_at=tuning.created_at,
            symbol=symbol.upper(),
            timeframe=timeframe,
            hypothesis_id=f"hyp:{playbook}:{timeframe}",
            dataset_sha256=self._hash_candles(candles),
            config_sha256=ResearchRunCard.hash_json(
                {
                    "search_space": to_primitive(self._search_space()),
                    "tuning_config": to_primitive(self._tuning_config(len(candles))),
                }
            ),
            strategy_sha256=ResearchRunCard.hash_json(
                {
                    "playbook": playbook,
                    "selected_parameters": to_primitive(tuning.selected_parameters),
                }
            ),
            code_revision="WORKTREE_UNVERIFIED",
            random_seed=robustness.bootstrap.seed,
            fee_rate=float(backtest.assumptions.fee_ratio),
            slippage_rate=float(backtest.assumptions.slippage_ratio),
            metrics=(
                ("net_return", metrics.net_return),
                ("max_drawdown", metrics.max_drawdown),
                ("expectancy_usdt", metrics.expectancy_usdt),
                ("trade_count", float(metrics.trade_count)),
                (
                    "bootstrap_probability_of_loss",
                    robustness.bootstrap.probability_of_loss,
                ),
            ),
            artifact_sha256=((artifact_path.as_posix(), artifact_digest),),
            blockers=blockers,
            promotion_status=promotion_status.value,
        )

    def _persist_blocker_dashboard(self, batch: ValidationBatchResult) -> None:
        if not self.artifact_directory.exists():
            return
        observations = self._blocker_observations(batch)
        dashboard = build_research_blocker_dashboard(
            dashboard_id=f"dashboard:{batch.symbol}:validation",
            created_at=datetime.now().astimezone(),
            symbol=batch.symbol,
            observations=observations,
        )
        ResearchBlockerDashboardWriter(
            self.artifact_directory / batch.symbol / "blocker-dashboard.json",
            JsonlAuditStore(self.artifact_directory / "blocker_dashboards.jsonl"),
        ).write(dashboard)

    @staticmethod
    def _blocker_observations(
        batch: ValidationBatchResult,
    ) -> tuple[ResearchBlockerObservation, ...]:
        observations: list[ResearchBlockerObservation] = []
        for result in batch.results:
            for blocker in result.blockers:
                observations.append(
                    ResearchBlockerObservation(
                        symbol=batch.symbol,
                        timeframe=result.timeframe,
                        playbook=result.playbook,
                        blocker=blocker,
                    )
                )
            for blocker, count in result.signal_blockers:
                observations.append(
                    ResearchBlockerObservation(
                        symbol=batch.symbol,
                        timeframe=result.timeframe,
                        playbook=result.playbook,
                        blocker=blocker,
                        count=count,
                    )
                )
        return tuple(observations)

    @staticmethod
    def _hash_candles(candles: tuple[OHLCVCandle, ...]) -> str:
        digest = sha256()
        for candle in candles:
            payload = json.dumps(
                to_primitive(candle),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
            digest.update(payload.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _artifact_path(self, symbol: str, timeframe: str, playbook: str) -> Path:
        return (
            self.artifact_directory / symbol.upper() / timeframe / f"{playbook}.jsonl"
        )

    @staticmethod
    def _checkpoint_path(artifact_path: Path) -> Path:
        return artifact_path.with_suffix(".checkpoint.json")

    def _config_sha256(self, candle_count: int) -> str:
        if candle_count < MINIMUM_VALIDATION_CANDLES:
            return ResearchRunCard.hash_json(
                {
                    "validated_playbooks": VALIDATED_PLAYBOOKS,
                    "minimum_validation_candles": MINIMUM_VALIDATION_CANDLES,
                    "candle_count": candle_count,
                }
            )
        return ResearchRunCard.hash_json(
            {
                "validated_playbooks": VALIDATED_PLAYBOOKS,
                "search_space": to_primitive(self._search_space()),
                "tuning_config": to_primitive(self._tuning_config(candle_count)),
            }
        )

    @staticmethod
    def _implementation_sha256() -> str:
        return sha256(Path(__file__).read_bytes()).hexdigest()

    def _write_checkpoint(
        self,
        symbol: str,
        result: PlaybookValidationResult,
        *,
        dataset_sha256: str,
        config_sha256: str,
        implementation_sha256: str,
    ) -> None:
        if result.artifact_path is None:
            return
        artifact_path = Path(result.artifact_path)
        checkpoint_path = self._checkpoint_path(artifact_path)
        write_json_object_verified(
            checkpoint_path,
            {
                "schema_version": "1.0",
                "symbol": symbol.strip().upper(),
                "timeframe": result.timeframe,
                "playbook": result.playbook,
                "candle_count": result.candle_count,
                "dataset_sha256": dataset_sha256,
                "config_sha256": config_sha256,
                "implementation_sha256": implementation_sha256,
                "artifact_sha256": sha256(artifact_path.read_bytes()).hexdigest(),
                "promotion_status": result.promotion_status.value,
                "blockers": list(result.blockers),
                "signal_blockers": [list(item) for item in result.signal_blockers],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            blocker="VALIDATION_CHECKPOINT_DESTINATION_VERIFY_FAILED",
            subject_id=f"{symbol.strip().upper()}:{result.timeframe}:{result.playbook}",
            indent=2,
        )

    def _load_checkpoint(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[OHLCVCandle, ...],
        *,
        dataset_sha256: str,
        config_sha256: str,
        implementation_sha256: str,
    ) -> PlaybookValidationResult | None:
        artifact_path = self._artifact_path(symbol, timeframe, playbook)
        checkpoint_path = self._checkpoint_path(artifact_path)
        if not checkpoint_path.is_file() or not artifact_path.is_file():
            return None
        try:
            payload = read_json_object(
                checkpoint_path,
                blocker="VALIDATION_CHECKPOINT_READ_FAILED",
            )
            expected = {
                "symbol": symbol.strip().upper(),
                "timeframe": timeframe,
                "playbook": playbook,
                "candle_count": len(candles),
                "dataset_sha256": dataset_sha256,
                "config_sha256": config_sha256,
                "implementation_sha256": implementation_sha256,
                "artifact_sha256": sha256(artifact_path.read_bytes()).hexdigest(),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                return None
            blockers = self._checkpoint_blockers(payload.get("blockers"))
            signal_blockers = self._checkpoint_signal_blockers(
                payload.get("signal_blockers")
            )
            promotion_status = ValidationStatus(str(payload["promotion_status"]))
        except (
            DestinationVerificationError,
            KeyError,
            OSError,
            TypeError,
            ValueError,
        ):
            return None
        return PlaybookValidationResult(
            playbook=playbook,
            timeframe=timeframe,
            candle_count=len(candles),
            promotion_status=promotion_status,
            blockers=blockers,
            signal_blockers=signal_blockers,
            artifact_path=str(artifact_path),
            checkpoint_path=str(checkpoint_path),
            resumed_from_checkpoint=True,
        )

    @staticmethod
    def _checkpoint_blockers(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise TypeError("validation checkpoint blockers are invalid")
        return tuple(str(item) for item in value)

    @staticmethod
    def _checkpoint_signal_blockers(value: object) -> tuple[tuple[str, int], ...]:
        if not isinstance(value, list):
            raise TypeError("validation checkpoint signal blockers are invalid")
        parsed: list[tuple[str, int]] = []
        for item in value:
            if not isinstance(item, list) or len(item) != 2:
                raise TypeError("validation checkpoint signal blocker is invalid")
            parsed.append((str(item[0]), int(item[1])))
        return tuple(parsed)

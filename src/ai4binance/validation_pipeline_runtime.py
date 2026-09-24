"""Concrete runtime wiring for historical validation workflows."""
# ruff: noqa: ANN401

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from functools import partial
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from ai4binance.application.validation_pipeline import (
    MINIMUM_VALIDATION_CANDLES,
    VALIDATED_PLAYBOOKS,
    HistoricalPlaybookAdapter,
    PlaybookValidationResult,
    ValidationBatchResult,
)
from ai4binance.domain import ValidationStatus
from ai4binance.indicators import atr
from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting import (
    BacktestEngine,
    BacktestIntent,
    BacktestRobustnessAnalyzer,
    BacktestRobustnessReport,
)
from ai4binance.research.backtesting.layout import (
    BacktestLayoutManifest,
    load_backtest_layout_manifest,
)
from ai4binance.research.backtesting.models import BacktestResult
from ai4binance.research.backtesting.storage import (
    BacktestAuditWriter,
    BacktestRobustnessWriter,
)
from ai4binance.research_governance import (
    ResearchBlockerDashboardWriter,
    ResearchBlockerObservation,
    ResearchRunCard,
    ResearchRunCardWriter,
    build_research_blocker_dashboard,
)
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.storage.destination_verification import (
    DestinationVerificationError,
    read_json_object,
    write_json_object_verified,
)
from ai4binance.strategies.registry import (
    StrategyRiskProfile,
    StrategyRiskProfileRegistry,
    build_playbook_registry,
    build_strategy_risk_profile_registry,
)
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
from ai4binance.validation.oos_maturity import (
    OOSMaturityEvidenceBundle,
    OOSMaturityGate,
)
from ai4binance.validation.regimes import classify_validation_regime
from ai4binance.validation.storage import WalkForwardAuditWriter

SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO = Decimal("0.25")


def runtime_spot_backtest_engine(
    candles: tuple[Any, ...],
    *,
    base_engine: BacktestEngine,
    notional_to_equity_ratio: Decimal,
) -> BacktestEngine:
    """Build a price-normalized Spot engine for one immutable validation set."""

    if not candles:
        raise ValueError("runtime Spot sizing requires validation candles")
    if (
        not notional_to_equity_ratio.is_finite()
        or notional_to_equity_ratio <= 0
        or notional_to_equity_ratio > 1
    ):
        raise ValueError("runtime Spot notional ratio must be within (0, 1]")
    config = base_engine.config
    maximum_entry_price = max(candle.open for candle in candles)
    if maximum_entry_price <= 0:
        raise ValueError("runtime Spot maximum entry price must be positive")
    target_notional = config.initial_cash_usdt * notional_to_equity_ratio
    quantity = (target_notional / maximum_entry_price).quantize(
        config.step_size,
        rounding=ROUND_DOWN,
    )
    if quantity <= 0 or quantity * maximum_entry_price < config.minimum_notional:
        raise ValueError("runtime Spot price-normalized quantity is not tradable")
    return BacktestEngine(replace(config, quantity=quantity))


def _build_historical_decision_resolver(
    candles: tuple[Any, ...] | None = None,
) -> Callable[..., Any]:
    """Bind registry and reuse decisions for one immutable validation dataset."""

    registry = build_playbook_registry()
    if candles is None:
        return partial(historical_playbook_decision, registry=registry)
    index_by_identity = {id(candle): index for index, candle in enumerate(candles)}
    decisions_by_playbook: dict[str, list[Any | None]] = {}

    def resolve(playbook: str, history: tuple[Any, ...]) -> Any:
        recent = history[-50:]
        if len(recent) == 50:
            end_index = index_by_identity.get(id(recent[-1]))
            start_index = -1 if end_index is None else end_index - len(recent) + 1
            if (
                end_index is not None
                and start_index >= 0
                and candles[start_index] is recent[0]
            ):
                cached = decisions_by_playbook.get(playbook)
                if cached is None:
                    cached = [None] * len(candles)
                    decisions_by_playbook[playbook] = cached
                decision = cached[end_index]
                if decision is None:
                    decision = historical_playbook_decision(
                        playbook,
                        history,
                        registry=registry,
                    )
                    cached[end_index] = decision
                return decision
        return historical_playbook_decision(playbook, history, registry=registry)

    return resolve


@dataclass(frozen=True, slots=True)
class HistoricalValidationRuntime:
    """Concrete validation runtime bound at the composition boundary."""

    backtest_engine: BacktestEngine = field(default_factory=BacktestEngine)
    tuning_engine: TuningEngine = field(default_factory=TuningEngine)
    robustness_analyzer: BacktestRobustnessAnalyzer = field(
        default_factory=BacktestRobustnessAnalyzer
    )
    risk_profile_registry: StrategyRiskProfileRegistry = field(
        default_factory=build_strategy_risk_profile_registry
    )
    layout: BacktestLayoutManifest = field(
        default_factory=load_backtest_layout_manifest
    )
    report_directory: Path | None = None
    position_notional_to_equity_ratio: Decimal | None = None

    def __post_init__(self) -> None:
        ratio = self.position_notional_to_equity_ratio
        if ratio is not None and (not ratio.is_finite() or ratio <= 0 or ratio > 1):
            raise ValueError("validation position notional ratio must be within (0, 1]")

    def start_validation_run(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        *,
        artifact_directory: Path,
    ) -> str:
        normalized_symbol = symbol.strip().upper()
        started_at = datetime.now().astimezone()
        identity_payload = (
            f"{normalized_symbol}|{'|'.join(timeframes)}|{started_at.isoformat()}"
        )
        run_id = (
            f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}_"
            f"{sha256(identity_payload.encode()).hexdigest()[:16]}"
        )
        payload = {
            "schema_version": "1.0",
            "run_id": run_id,
            "symbol": normalized_symbol,
            "requested_timeframes": list(timeframes),
            "validated_playbooks": list(VALIDATED_PLAYBOOKS),
            "started_at": started_at.isoformat(),
            "updated_at": started_at.isoformat(),
            "status": "RUNNING",
            "timeframe_evidence": [],
            "playbook_terminals": [],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_json_object_verified(
            self._validation_run_manifest_path(
                artifact_directory,
                normalized_symbol,
                run_id,
            ),
            payload,
            blocker="VALIDATION_RUN_MANIFEST_DESTINATION_VERIFY_FAILED",
            subject_id=run_id,
            indent=2,
        )
        self._append_validation_run_event(
            artifact_directory,
            normalized_symbol,
            run_id,
            "VALIDATION_RUN_STARTED",
            {
                "requested_timeframes": list(timeframes),
                "validated_playbooks": list(VALIDATED_PLAYBOOKS),
            },
        )
        return run_id

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
    ) -> None:
        evidence = {
            "timeframe": timeframe,
            "candle_count": candle_count,
            "dataset_sha256": dataset_sha256,
            "config_sha256": config_sha256,
            "implementation_sha256": implementation_sha256,
            "stage_timings_ms": self._stage_timings_payload(stage_timings_ms),
        }
        self._update_validation_run_manifest(
            artifact_directory,
            symbol,
            run_id,
            collection="timeframe_evidence",
            item=evidence,
        )
        self._append_validation_run_event(
            artifact_directory,
            symbol,
            run_id,
            "VALIDATION_TIMEFRAME_READY",
            evidence,
        )

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
    ) -> None:
        if checkpoint_status not in {"HIT", "MISS"}:
            raise ValueError("validation checkpoint status is invalid")
        if terminal_status not in {"COMPLETED", "COMPLETED_FROM_CHECKPOINT", "FAILED"}:
            raise ValueError("validation playbook terminal status is invalid")
        terminal = {
            "timeframe": timeframe,
            "playbook": playbook,
            "status": terminal_status,
            "checkpoint_status": checkpoint_status,
            "stage_timings_ms": self._stage_timings_payload(stage_timings_ms),
            "promotion_status": (
                "RESEARCH_ONLY" if result is None else result.promotion_status.value
            ),
            "blockers": [] if result is None else list(result.blockers),
            "failure_code": failure_code,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        self._update_validation_run_manifest(
            artifact_directory,
            symbol,
            run_id,
            collection="playbook_terminals",
            item=terminal,
        )
        self._append_validation_run_event(
            artifact_directory,
            symbol,
            run_id,
            "VALIDATION_PLAYBOOK_TERMINAL",
            terminal,
        )

    def finish_validation_run(
        self,
        run_id: str,
        symbol: str,
        *,
        artifact_directory: Path,
        terminal_status: str,
    ) -> None:
        if terminal_status not in {"COMPLETED", "FAILED"}:
            raise ValueError("validation run terminal status is invalid")
        self._update_validation_run_manifest(
            artifact_directory,
            symbol,
            run_id,
            status=terminal_status,
        )
        self._append_validation_run_event(
            artifact_directory,
            symbol,
            run_id,
            "VALIDATION_RUN_TERMINAL",
            {"status": terminal_status},
        )

    def ensure_playbook_implemented(self, playbook: str) -> None:
        if not build_playbook_registry().get(playbook).implemented:
            raise ValueError(f"playbook is not implemented: {playbook}")

    def validate_one(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[Any, ...],
        *,
        artifact_directory: Path,
    ) -> PlaybookValidationResult:
        stage_timings: list[tuple[str, float]] = []
        stage_started = perf_counter_ns()
        preflight = self._preflight(playbook, candles)
        stage_timings.append(("preflight", self._elapsed_ms(stage_started)))
        if preflight:
            return PlaybookValidationResult(
                playbook,
                timeframe,
                len(candles),
                ValidationStatus.RESEARCH_ONLY,
                preflight,
                stage_timings_ms=tuple(stage_timings),
            )
        baseline_parameters = ParameterSet(
            "baseline",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        )
        decision_resolver = _build_historical_decision_resolver(candles)
        baseline_provider = HistoricalPlaybookAdapter(
            playbook=playbook,
            parameters=baseline_parameters,
            decision_resolver=decision_resolver,
            atr_calculator=atr,
            intent_builder=BacktestIntent,
            symbol=symbol,
            timeframe=timeframe,
            strategy_version="1",
            regime_classifier=self._regime,
            risk_profile_registry=self.risk_profile_registry,
        )
        backtest_engine = (
            self.backtest_engine
            if self.position_notional_to_equity_ratio is None
            else runtime_spot_backtest_engine(
                candles,
                base_engine=self.backtest_engine,
                notional_to_equity_ratio=self.position_notional_to_equity_ratio,
            )
        )
        stage_started = perf_counter_ns()
        backtest = backtest_engine.run(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            signal_provider=baseline_provider,
        )
        stage_timings.append(("backtest", self._elapsed_ms(stage_started)))
        stage_started = perf_counter_ns()
        tuning_engine = replace(
            self.tuning_engine,
            validator=replace(
                self.tuning_engine.validator,
                backtest_engine=backtest_engine,
            ),
        )
        tuning = tuning_engine.tune(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            search_space=self._search_space(),
            strategy_factory=lambda parameters: HistoricalPlaybookAdapter(
                playbook=playbook,
                parameters=parameters,
                decision_resolver=decision_resolver,
                atr_calculator=atr,
                intent_builder=BacktestIntent,
                symbol=symbol,
                timeframe=timeframe,
                strategy_version="1",
                regime_classifier=self._regime,
                risk_profile_registry=self.risk_profile_registry,
            ),
            regime_classifier=self._regime,
            config=self._tuning_config(len(candles)),
        )
        stage_timings.append(("walk_forward_tuning", self._elapsed_ms(stage_started)))
        stage_started = perf_counter_ns()
        robustness = self.robustness_analyzer.analyze(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            backtest_config=backtest_engine.config,
            provider_factory=lambda: HistoricalPlaybookAdapter(
                playbook=playbook,
                parameters=tuning.selected_parameters,
                decision_resolver=decision_resolver,
                atr_calculator=atr,
                intent_builder=BacktestIntent,
                symbol=symbol,
                timeframe=timeframe,
                strategy_version="1",
                regime_classifier=self._regime,
                risk_profile_registry=self.risk_profile_registry,
            ),
        )
        stage_timings.append(("robustness", self._elapsed_ms(stage_started)))
        blockers = tuple(dict.fromkeys((*tuning.blockers, *robustness.blockers)))
        promotion_status = (
            ValidationStatus.STAGED_CANDIDATE
            if not blockers
            else ValidationStatus.RESEARCH_ONLY
        )
        stage_started = perf_counter_ns()
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
            artifact_directory=artifact_directory,
        )
        stage_timings.append(("evidence_persistence", self._elapsed_ms(stage_started)))
        artifact_path = self._artifact_path(
            artifact_directory,
            symbol,
            timeframe,
            playbook,
        )
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
            stage_timings_ms=tuple(stage_timings),
        )

    def persist_blocker_dashboard(
        self,
        batch: ValidationBatchResult,
        *,
        artifact_directory: Path,
    ) -> None:
        if not artifact_directory.exists():
            return
        observations = self._blocker_observations(batch)
        dashboard = build_research_blocker_dashboard(
            dashboard_id=f"dashboard:{batch.symbol}:validation",
            created_at=datetime.now().astimezone(),
            symbol=batch.symbol,
            observations=observations,
        )
        ResearchBlockerDashboardWriter(
            self.layout.blocker_dashboard_path(artifact_directory, batch.symbol),
            JsonlAuditStore(
                self.layout.blocker_dashboard_ledger_path(artifact_directory)
            ),
        ).write(dashboard)

    def dataset_sha256(self, candles: tuple[object, ...]) -> str:
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

    def config_sha256(self, candle_count: int) -> str:
        if candle_count < MINIMUM_VALIDATION_CANDLES:
            return ResearchRunCard.hash_json(
                {
                    "validated_playbooks": VALIDATED_PLAYBOOKS,
                    "minimum_validation_candles": MINIMUM_VALIDATION_CANDLES,
                    "candle_count": candle_count,
                    "backtest_config": to_primitive(self.backtest_engine.config),
                    "position_notional_to_equity_ratio": (
                        str(self.position_notional_to_equity_ratio)
                        if self.position_notional_to_equity_ratio is not None
                        else None
                    ),
                    "stress_scenarios": to_primitive(
                        self.robustness_analyzer.scenarios
                    ),
                    "strategy_risk_profiles": self._risk_profiles_payload(),
                }
            )
        return ResearchRunCard.hash_json(
            {
                "validated_playbooks": VALIDATED_PLAYBOOKS,
                "search_space": to_primitive(self._search_space()),
                "backtest_config": to_primitive(self.backtest_engine.config),
                "position_notional_to_equity_ratio": (
                    str(self.position_notional_to_equity_ratio)
                    if self.position_notional_to_equity_ratio is not None
                    else None
                ),
                "stress_scenarios": to_primitive(self.robustness_analyzer.scenarios),
                "tuning_config": to_primitive(self._tuning_config(candle_count)),
                "strategy_risk_profiles": self._risk_profiles_payload(),
            }
        )

    @staticmethod
    def implementation_sha256() -> str:
        package_root = Path(__file__).resolve().parent
        digest = sha256()
        for source_path in sorted(package_root.rglob("*.py")):
            digest.update(source_path.relative_to(package_root).as_posix().encode())
            digest.update(b"\0")
            digest.update(source_path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def write_checkpoint(
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
    ) -> PlaybookValidationResult | None:
        artifact_path = self._artifact_path(
            artifact_directory,
            symbol,
            timeframe,
            playbook,
        )
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
    def _preflight(
        playbook: str,
        candles: tuple[Any, ...],
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
        purge_size = 1
        embargo_size = 1
        train_size = candle_count - (test_size * 5) - purge_size - (embargo_size * 4)
        return TuningConfig(
            WalkForwardConfig(
                train_size=train_size,
                test_size=test_size,
                step_size=test_size,
                min_folds=5,
                min_oos_trades=5,
                min_regime_count=2,
                purge_size=purge_size,
                embargo_size=embargo_size,
            ),
            min_neighbor_count=2,
            min_neighbor_pass_ratio=0.5,
            min_neighbor_return_ratio=0.5,
        )

    @staticmethod
    def _regime(candle: Any) -> MarketRegime:
        return classify_validation_regime(candle)

    def _persist(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[Any, ...],
        backtest: BacktestResult,
        tuning: TuningReport,
        robustness: BacktestRobustnessReport,
        blockers: tuple[str, ...],
        promotion_status: ValidationStatus,
        *,
        artifact_directory: Path,
    ) -> ResearchRunCard:
        path = self._artifact_path(artifact_directory, symbol, timeframe, playbook)
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
            self.layout.validation_run_card_path(
                artifact_directory,
                symbol,
                timeframe,
                playbook,
            ),
            JsonlAuditStore(
                self.layout.research_run_cards_ledger_path(artifact_directory)
            ),
        ).write(card)
        self._write_human_summary(
            artifact_directory=artifact_directory,
            symbol=symbol,
            timeframe=timeframe,
            playbook=playbook,
            backtest=backtest,
            robustness=robustness,
            blockers=blockers,
            promotion_status=promotion_status,
            artifact_path=path,
        )
        # Existing WF/tuning artifacts are exploratory and have no independent
        # final holdout or forward-paper chain. Publish that gap explicitly.
        maturity = OOSMaturityGate(artifact_directory).evaluate(
            OOSMaturityEvidenceBundle(subject=None, blockers=blockers)
        )
        payload = {
            "maturity": to_primitive(maturity),
            "available_exploratory_artifacts": to_primitive(card.artifact_sha256),
            "dataset_sha256": card.dataset_sha256,
            "strategy_sha256": card.strategy_sha256,
            "config_sha256": card.config_sha256,
            "code_revision": card.code_revision,
            "qualification": "UNBOUND_EXPLORATORY_EVIDENCE",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        digest = ResearchRunCard.hash_json(payload)
        maturity_path = path.with_name(f"{playbook}.{digest}.oos-maturity.json")
        if maturity_path.exists():
            previous = read_json_object(
                maturity_path, blocker="OOS_MATURITY_OBSERVATION_UNREADABLE"
            )
            if previous != payload:
                raise ValueError("OOS_MATURITY_OBSERVATION_CONFLICT")
            return card
        write_json_object_verified(
            maturity_path,
            payload,
            subject_id=f"oos-observation:{digest}",
            blocker="OOS_MATURITY_OBSERVATION_WRITE_FAILED",
            durable=True,
        )
        return card

    def _build_run_card(
        self,
        symbol: str,
        timeframe: str,
        playbook: str,
        candles: tuple[Any, ...],
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
            dataset_sha256=self.dataset_sha256(candles),
            config_sha256=ResearchRunCard.hash_json(
                {
                    "search_space": to_primitive(self._search_space()),
                    "backtest_config": to_primitive(backtest.assumptions),
                    "stress_scenarios": to_primitive(
                        self.robustness_analyzer.scenarios
                    ),
                    "tuning_config": to_primitive(self._tuning_config(len(candles))),
                }
            ),
            strategy_sha256=ResearchRunCard.hash_json(
                {
                    "playbook": playbook,
                    "selected_parameters": to_primitive(tuning.selected_parameters),
                    "strategy_risk_profiles": self._risk_profiles_payload(playbook),
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
            artifact_sha256=(
                (self._canonical_artifact_uri(artifact_path), artifact_digest),
            ),
            blockers=blockers,
            promotion_status=promotion_status.value,
        )

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

    def _artifact_path(
        self,
        artifact_directory: Path,
        symbol: str,
        timeframe: str,
        playbook: str,
    ) -> Path:
        return self.layout.validation_artifact_path(
            artifact_directory,
            symbol,
            timeframe,
            playbook,
        )

    @staticmethod
    def _validation_run_manifest_path(
        artifact_directory: Path,
        symbol: str,
        run_id: str,
    ) -> Path:
        return (
            artifact_directory
            / symbol.strip().upper()
            / "runs"
            / f"{run_id}.manifest.json"
        )

    @staticmethod
    def _validation_run_event_path(
        artifact_directory: Path,
        symbol: str,
    ) -> Path:
        return (
            artifact_directory / symbol.strip().upper() / "validation-run-events.jsonl"
        )

    def _update_validation_run_manifest(
        self,
        artifact_directory: Path,
        symbol: str,
        run_id: str,
        *,
        collection: str | None = None,
        item: dict[str, object] | None = None,
        status: str | None = None,
    ) -> None:
        path = self._validation_run_manifest_path(artifact_directory, symbol, run_id)
        payload = dict(
            read_json_object(
                path,
                blocker="VALIDATION_RUN_MANIFEST_READ_FAILED",
            )
        )
        if (
            payload.get("run_id") != run_id
            or payload.get("symbol") != symbol.strip().upper()
            or payload.get("execution_allowed") is not False
            or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("VALIDATION_RUN_MANIFEST_IDENTITY_DRIFT")
        if collection is not None:
            existing = payload.get(collection)
            if not isinstance(existing, list) or item is None:
                raise ValueError("VALIDATION_RUN_MANIFEST_COLLECTION_INVALID")
            existing.append(item)
        if status is not None:
            payload["status"] = status
        payload["updated_at"] = datetime.now().astimezone().isoformat()
        write_json_object_verified(
            path,
            payload,
            blocker="VALIDATION_RUN_MANIFEST_DESTINATION_VERIFY_FAILED",
            subject_id=run_id,
            indent=2,
        )

    def _append_validation_run_event(
        self,
        artifact_directory: Path,
        symbol: str,
        run_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        JsonlAuditStore(
            self._validation_run_event_path(artifact_directory, symbol)
        ).append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=datetime.now().astimezone(),
                snapshot_id=run_id,
                payload={
                    "run_id": run_id,
                    "symbol": symbol.strip().upper(),
                    **payload,
                    "execution_allowed": False,
                    "promotion_status": "RESEARCH_ONLY",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            )
        )

    @staticmethod
    def _stage_timings_payload(
        stage_timings_ms: tuple[tuple[str, float], ...],
    ) -> dict[str, float]:
        names = tuple(name for name, _ in stage_timings_ms)
        if len(names) != len(set(names)):
            raise ValueError("validation stage timing names must be unique")
        if any(not name.strip() or duration < 0 for name, duration in stage_timings_ms):
            raise ValueError("validation stage timings must be named and non-negative")
        return dict(stage_timings_ms)

    @staticmethod
    def _elapsed_ms(started_ns: int) -> float:
        return round((perf_counter_ns() - started_ns) / 1_000_000, 3)

    @staticmethod
    def _checkpoint_path(artifact_path: Path) -> Path:
        return artifact_path.with_suffix(".checkpoint.json")

    def _canonical_artifact_uri(self, artifact_path: Path) -> str:
        relative = artifact_path.as_posix()
        marker = "/".join(Path(self.layout.validation_root).parts)
        if marker and marker in relative:
            return relative[relative.index(marker) :]
        return self.layout.canonicalize_uri(relative)

    def _report_directory(self, artifact_directory: Path) -> Path | None:
        if self.report_directory is not None:
            return self.report_directory
        layout_parts = tuple(
            part.casefold() for part in Path(self.layout.validation_root).parts
        )
        artifact_parts = tuple(part.casefold() for part in artifact_directory.parts)
        if (
            len(artifact_parts) >= len(layout_parts)
            and artifact_parts[-len(layout_parts) :] == layout_parts
        ):
            prefix = artifact_directory.parents[len(layout_parts) - 1]
            return prefix / Path(self.layout.report_root)
        return None

    def _write_human_summary(
        self,
        *,
        artifact_directory: Path,
        symbol: str,
        timeframe: str,
        playbook: str,
        backtest: BacktestResult,
        robustness: BacktestRobustnessReport,
        blockers: tuple[str, ...],
        promotion_status: ValidationStatus,
        artifact_path: Path,
    ) -> None:
        report_root = self._report_directory(artifact_directory)
        if report_root is None:
            return
        json_path, markdown_path = self.layout.report_paths(
            report_root,
            symbol,
            timeframe,
            playbook,
        )
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        metrics = backtest.metrics
        payload = {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "playbook": playbook,
            "artifact_path": self._canonical_artifact_uri(artifact_path),
            "promotion_status": promotion_status.value,
            "blockers": list(blockers),
            "created_at": backtest.ended_at.isoformat(),
            "net_return": metrics.net_return,
            "max_drawdown": metrics.max_drawdown,
            "trade_count": metrics.trade_count,
            "profit_factor": metrics.profit_factor,
            "bootstrap_probability_of_loss": (robustness.bootstrap.probability_of_loss),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_json_object_verified(
            json_path,
            payload,
            blocker="BACKTEST_HUMAN_REPORT_DESTINATION_VERIFY_FAILED",
            subject_id=f"{symbol.upper()}:{timeframe}:{playbook}",
            indent=2,
        )
        profit_factor_text = (
            "UNAVAILABLE"
            if metrics.profit_factor is None
            else f"{metrics.profit_factor:.6f}"
        )
        markdown_path.write_text(
            "\n".join(
                (
                    f"# {symbol.upper()} {timeframe} {playbook} Backtest Summary",
                    "",
                    f"- promotion_status: `{promotion_status.value}`",
                    f"- artifact_path: `{payload['artifact_path']}`",
                    f"- net_return: `{metrics.net_return:.6f}`",
                    f"- max_drawdown: `{metrics.max_drawdown:.6f}`",
                    f"- trade_count: `{metrics.trade_count}`",
                    f"- profit_factor: `{profit_factor_text}`",
                    (
                        "- bootstrap_probability_of_loss: "
                        f"`{robustness.bootstrap.probability_of_loss:.6f}`"
                    ),
                    f"- blockers: `{', '.join(blockers) if blockers else 'NONE'}`",
                    "- execution_allowed: `False`",
                    "- live_eligibility_status: `LIVE_ORDER_BLOCKED`",
                )
            ),
            encoding="utf-8",
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

    def _risk_profiles_payload(
        self,
        strategy_id: str | None = None,
    ) -> tuple[dict[str, object], ...]:
        profiles = self.risk_profile_registry.profiles
        if strategy_id is not None:
            profiles = tuple(
                profile for profile in profiles if profile.strategy_id == strategy_id
            )
        return tuple(self._risk_profile_payload(profile) for profile in profiles)

    @staticmethod
    def _risk_profile_payload(profile: StrategyRiskProfile) -> dict[str, object]:
        return {
            "strategy_id": profile.strategy_id,
            "version": profile.version,
            "regime": profile.regime,
            "stop_atr_multiple": str(profile.stop_atr_multiple),
            "target_atr_multiple": str(profile.target_atr_multiple),
            "minimum_rr": str(profile.minimum_rr),
            "breakeven_trigger_r": (
                None
                if profile.breakeven_trigger_r is None
                else str(profile.breakeven_trigger_r)
            ),
            "trailing_atr_multiple": (
                None
                if profile.trailing_atr_multiple is None
                else str(profile.trailing_atr_multiple)
            ),
            "maximum_holding_bars": profile.maximum_holding_bars,
            "config_hash": profile.config_hash,
        }

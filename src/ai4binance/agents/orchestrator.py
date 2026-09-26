"""Dependency-aware deterministic enterprise orchestrator."""

from collections.abc import Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter_ns
from types import MappingProxyType

from ai4binance.agents.advanced import build_advanced_agent
from ai4binance.agents.base import BaseAgent
from ai4binance.agents.bundles import CapabilityBundleExecutor
from ai4binance.agents.catalog import (
    ORCHESTRATED_SPECIALIST_NAMES,
    build_default_capability_bundle_registry,
    build_default_capability_registry,
    build_default_registry,
)
from ai4binance.agents.data_quality_gate import DataQualityGate
from ai4binance.agents.evidence_fusion import EvidenceFusionEngine
from ai4binance.agents.preflight import (
    CapabilityPreflightDecision,
    CapabilityPreflightMode,
    build_capability_bundle_preflight_plan,
    build_capability_preflight_plan,
)
from ai4binance.agents.registry import (
    AgentRegistry,
    CapabilityBundleRegistry,
    CapabilityRegistry,
)
from ai4binance.agents.risk_gate import RiskGate
from ai4binance.agents.specialists import (
    ResearchOnlyAgent,
)
from ai4binance.agents.technical import build_core_technical_agent
from ai4binance.agents.telemetry import (
    AgentExecutionMetric,
    AgentTelemetrySink,
    CycleTelemetrySink,
    OrchestrationCycleMetric,
)
from ai4binance.agents.trend_events import build_trend_events_agent
from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate
from ai4binance.agents.validation_gate import ValidationGate
from ai4binance.core.contracts.memory import CompiledCycleContext
from ai4binance.domain import TradeCandidate
from ai4binance.intelligence.contracts import TradingIntelligenceState
from ai4binance.intelligence.trading import TradingIntelligenceEngine
from ai4binance.schemas import AgentResult, AgentStatus, AnalysisState, MarketSnapshot
from ai4binance.strategies import StrategyEngine
from ai4binance.strategies.arbitration import CandidateArbitrator
from ai4binance.whale_fusion.agent import build_whale_fusion_agent


@dataclass(frozen=True, slots=True)
class EnterpriseOrchestrator:
    """Coordinate immutable snapshot analysis without calculating indicators."""

    registry: AgentRegistry = field(default_factory=build_default_registry)
    capability_registry: CapabilityRegistry = field(
        default_factory=build_default_capability_registry
    )
    capability_bundle_registry: CapabilityBundleRegistry = field(
        default_factory=build_default_capability_bundle_registry
    )
    max_workers: int = 8
    minimum_candles: int = 2
    preflight_mode: CapabilityPreflightMode = CapabilityPreflightMode.STANDARD
    validation_agent: ValidationGate = field(default_factory=ValidationGate)
    strategy_engine: StrategyEngine = field(default_factory=StrategyEngine)
    candidate_arbitrator: CandidateArbitrator = field(
        default_factory=CandidateArbitrator
    )
    trading_intelligence_engine: TradingIntelligenceEngine = field(
        default_factory=TradingIntelligenceEngine
    )
    telemetry_sink: AgentTelemetrySink | None = None
    agent_latency_budget_ms: float = 1_000.0

    def __post_init__(self) -> None:
        """Bound concurrency and minimum-history configuration."""
        if not 1 <= self.max_workers <= 32:
            raise ValueError("max_workers must be between 1 and 32")
        if self.minimum_candles < 2:
            raise ValueError("minimum_candles must be at least 2")
        if tuple(self.capability_registry.by_id) != ORCHESTRATED_SPECIALIST_NAMES:
            raise ValueError("capability registry must match the analytical catalog")
        if tuple(self.capability_bundle_registry.capability_registry.by_id) != tuple(
            self.capability_registry.by_id
        ):
            raise ValueError(
                "capability bundle registry must match capability registry"
            )
        if not 1.0 <= self.agent_latency_budget_ms <= 60_000.0:
            raise ValueError("agent latency budget must be between 1 and 60000 ms")

    def analyze(
        self,
        snapshot: MarketSnapshot,
        compiled_cycle_context: CompiledCycleContext | None = None,
    ) -> AnalysisState:
        """Run eligibility, specialists, synthesis, risk and final validation."""
        cycle_started_ns = perf_counter_ns()
        specialist_wall_ms = 0.0
        scheduler_overhead_ms = 0.0
        scheduled_capability_count = 0
        executed_capability_count = 0
        scheduled_bundle_count = 0
        skipped_bundle_count = 0
        bundle_task_count = 0
        self._validate_compiled_context(snapshot, compiled_cycle_context)
        results: dict[str, AgentResult] = {}
        data_quality_gate = DataQualityGate(
            self.registry.get("data_quality"),
            minimum_candles=self.minimum_candles,
        )
        results[data_quality_gate.definition.name] = self._run_data_quality_gate(
            data_quality_gate,
            snapshot,
        )
        if results["data_quality"].status is AgentStatus.BLOCKED:
            return self._finalize_cycle(
                snapshot,
                results,
                ("EARLY_EXIT_NO_TRADE",),
                compiled_cycle_context=compiled_cycle_context,
                cycle_started_ns=cycle_started_ns,
                specialist_wall_ms=specialist_wall_ms,
                scheduler_overhead_ms=scheduler_overhead_ms,
                scheduled_capability_count=scheduled_capability_count,
                executed_capability_count=executed_capability_count,
                scheduled_bundle_count=scheduled_bundle_count,
                skipped_bundle_count=skipped_bundle_count,
                bundle_task_count=bundle_task_count,
            )

        universe_liquidity_gate = UniverseLiquidityGate(
            self.registry.get("universe_liquidity")
        )
        results[universe_liquidity_gate.definition.name] = (
            self._run_universe_liquidity_gate(
                universe_liquidity_gate,
                snapshot,
                results,
            )
        )
        if results["universe_liquidity"].status is AgentStatus.BLOCKED:
            return self._finalize_cycle(
                snapshot,
                results,
                ("EARLY_EXIT_NO_TRADE",),
                compiled_cycle_context=compiled_cycle_context,
                cycle_started_ns=cycle_started_ns,
                specialist_wall_ms=specialist_wall_ms,
                scheduler_overhead_ms=scheduler_overhead_ms,
                scheduled_capability_count=scheduled_capability_count,
                executed_capability_count=executed_capability_count,
                scheduled_bundle_count=scheduled_bundle_count,
                skipped_bundle_count=skipped_bundle_count,
                bundle_task_count=bundle_task_count,
            )

        preflight_plan = build_capability_preflight_plan(
            self.capability_registry,
            snapshot,
            mode=self.preflight_mode,
        )
        bundle_preflight_plan = build_capability_bundle_preflight_plan(
            preflight_plan,
            self.capability_bundle_registry,
        )
        scheduled_bundle_count = len(bundle_preflight_plan.scheduled_bundle_ids)
        skipped_bundle_count = len(bundle_preflight_plan.skipped_bundle_ids)
        for decision in preflight_plan.skipped:
            results[decision.capability_id] = self._preflight_result(snapshot, decision)
        specialist_agents_list: list[BaseAgent] = []
        for name in preflight_plan.scheduled_ids:
            definition = self.registry.get(name)
            implemented_agent = build_core_technical_agent(definition)
            implemented_agent = implemented_agent or build_whale_fusion_agent(
                definition
            )
            implemented_agent = implemented_agent or build_advanced_agent(definition)
            implemented_agent = implemented_agent or build_trend_events_agent(
                definition
            )
            specialist_agents_list.append(
                implemented_agent or ResearchOnlyAgent(definition)
            )
        specialist_agents = tuple(specialist_agents_list)
        scheduled_capability_count = len(preflight_plan.decisions)
        specialists_started_ns = perf_counter_ns()
        with ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="ai4binance-agent",
        ) as executor:
            scheduler_overhead_ms, bundle_task_count = self._run_dependency_layers(
                snapshot,
                specialist_agents,
                results,
                executor,
            )
        specialist_wall_ms = (perf_counter_ns() - specialists_started_ns) / 1_000_000.0
        executed_capability_count = len(specialist_agents)
        if compiled_cycle_context is not None and (
            compiled_cycle_context.memory_advisory_evidence
        ):
            results["memory_advisory"] = self._memory_advisory_result(
                snapshot,
                compiled_cycle_context,
            )

        evidence_fusion_engine = EvidenceFusionEngine(
            self.registry.get("confluence"),
            self.registry,
        )
        results[evidence_fusion_engine.definition.name] = self._run_evidence_fusion(
            evidence_fusion_engine,
            snapshot,
            MappingProxyType(results),
        )
        trading_intelligence = self.trading_intelligence_engine.build(
            snapshot,
            MappingProxyType(results),
        )
        candidates = self.strategy_engine.generate(
            snapshot,
            MappingProxyType(results),
        )
        candidates = self.trading_intelligence_engine.bind_candidates(
            candidates,
            trading_intelligence,
            snapshot,
        )
        selection = self.candidate_arbitrator.select(candidates)
        risk_candidates = selection.ranked[:5] if selection.selected is not None else ()
        risk_gate = RiskGate(self.registry.get("risk"), candidates=risk_candidates)
        results[risk_gate.definition.name] = self._run_risk_gate(
            risk_gate, snapshot, MappingProxyType(results)
        )
        return self._finalize_cycle(
            snapshot,
            results,
            extra_blockers=tuple(
                dict.fromkeys((*selection.blockers, *trading_intelligence.blockers))
            ),
            candidates=candidates,
            compiled_cycle_context=compiled_cycle_context,
            trading_intelligence=trading_intelligence,
            cycle_started_ns=cycle_started_ns,
            specialist_wall_ms=specialist_wall_ms,
            scheduler_overhead_ms=scheduler_overhead_ms,
            scheduled_capability_count=scheduled_capability_count,
            executed_capability_count=executed_capability_count,
            scheduled_bundle_count=scheduled_bundle_count,
            skipped_bundle_count=skipped_bundle_count,
            bundle_task_count=bundle_task_count,
        )

    @staticmethod
    def _validate_compiled_context(
        snapshot: MarketSnapshot,
        compiled_cycle_context: CompiledCycleContext | None,
    ) -> None:
        if compiled_cycle_context is None:
            return
        if compiled_cycle_context.market_snapshot_id != snapshot.snapshot_id:
            raise ValueError("compiled cycle context snapshot must match")
        if compiled_cycle_context.symbol != snapshot.symbol:
            raise ValueError("compiled cycle context symbol must match")
        if compiled_cycle_context.market_type != snapshot.market_type:
            raise ValueError("compiled cycle context market type must match")

    def _run_dependency_layers(
        self,
        snapshot: MarketSnapshot,
        agents: tuple[BaseAgent, ...],
        results: dict[str, AgentResult],
        executor: Executor,
    ) -> tuple[float, int]:
        """Run ready layers through bounded bundle-level executor tasks."""
        scheduler_overhead_ns = 0
        pending = {agent.definition.name: agent for agent in agents}
        bundle_executors = self._build_bundle_executors(pending)
        bundle_task_count = 0
        while pending:
            scheduling_started_ns = perf_counter_ns()
            ready_names = tuple(
                sorted(
                    name
                    for name, agent in pending.items()
                    if all(
                        dependency in results
                        for dependency in agent.definition.dependencies
                    )
                )
            )
            if not ready_names:
                raise RuntimeError("orchestrated agent graph cannot make progress")
            prior_results: Mapping[str, AgentResult] = MappingProxyType(results.copy())
            ready_by_bundle = self._ready_capabilities_by_bundle(ready_names)
            futures = {
                bundle_id: executor.submit(
                    bundle_executors[bundle_id].run_ready,
                    snapshot,
                    prior_results,
                    capability_ids,
                )
                for bundle_id, capability_ids in ready_by_bundle.items()
            }
            bundle_task_count += len(futures)
            scheduler_overhead_ns += perf_counter_ns() - scheduling_started_ns
            completed_by_name = {
                capability_id: (result, elapsed_ms)
                for bundle_id in ready_by_bundle
                for capability_id, result, elapsed_ms in futures[bundle_id].result()
            }
            for name in ready_names:
                result, elapsed_ms = completed_by_name[name]
                result_record_started_ns = perf_counter_ns()
                results[name] = result
                self._record_metric(snapshot, result, elapsed_ms)
                del pending[name]
                scheduler_overhead_ns += perf_counter_ns() - result_record_started_ns
        return scheduler_overhead_ns / 1_000_000.0, bundle_task_count

    def _build_bundle_executors(
        self,
        pending: Mapping[str, BaseAgent],
    ) -> Mapping[str, CapabilityBundleExecutor]:
        """Bind this cycle's admitted capabilities to their canonical bundles."""
        return MappingProxyType(
            {
                definition.bundle_id: CapabilityBundleExecutor(
                    definition,
                    {
                        capability_id: pending[capability_id]
                        for capability_id in definition.capability_ids
                        if capability_id in pending
                    },
                )
                for definition in self.capability_bundle_registry.definitions
                if any(
                    capability_id in pending
                    for capability_id in definition.capability_ids
                )
            }
        )

    def _ready_capabilities_by_bundle(
        self,
        ready_names: tuple[str, ...],
    ) -> Mapping[str, tuple[str, ...]]:
        """Group one ready layer without changing canonical result merge order."""
        ready_ids = frozenset(ready_names)
        return MappingProxyType(
            {
                definition.bundle_id: tuple(
                    capability_id
                    for capability_id in definition.capability_ids
                    if capability_id in ready_ids
                )
                for definition in self.capability_bundle_registry.definitions
                if any(
                    capability_id in ready_ids
                    for capability_id in definition.capability_ids
                )
            }
        )

    def _run_agent(
        self,
        agent: BaseAgent,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        result, elapsed_ms = self._timed_agent_call(agent, snapshot, prior_results)
        self._record_metric(snapshot, result, elapsed_ms)
        return result

    def _run_evidence_fusion(
        self,
        engine: EvidenceFusionEngine,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Run the canonical deterministic fusion service with telemetry."""
        started = perf_counter_ns()
        result = engine.fuse(snapshot, prior_results)
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000.0
        self._record_metric(snapshot, result, elapsed_ms)
        return result

    def _run_data_quality_gate(
        self,
        gate: DataQualityGate,
        snapshot: MarketSnapshot,
    ) -> AgentResult:
        """Run the canonical deterministic data-quality control with telemetry."""
        started = perf_counter_ns()
        result = gate.evaluate(snapshot)
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000.0
        self._record_metric(snapshot, result, elapsed_ms)
        return result

    def _run_risk_gate(
        self,
        gate: RiskGate,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Run the canonical deterministic risk control with telemetry."""
        started = perf_counter_ns()
        result = gate.evaluate(snapshot, prior_results)
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000.0
        self._record_metric(snapshot, result, elapsed_ms)
        return result

    def _run_universe_liquidity_gate(
        self,
        gate: UniverseLiquidityGate,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Run the canonical deterministic universe/liquidity control."""
        started = perf_counter_ns()
        result = gate.evaluate(snapshot, prior_results)
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000.0
        self._record_metric(snapshot, result, elapsed_ms)
        return result

    @staticmethod
    def _timed_agent_call(
        agent: BaseAgent,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> tuple[AgentResult, float]:
        started = perf_counter_ns()
        result = agent.run(snapshot, prior_results)
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000.0
        return result, elapsed_ms

    def _record_metric(
        self,
        snapshot: MarketSnapshot,
        result: AgentResult,
        elapsed_ms: float,
    ) -> None:
        if self.telemetry_sink is None:
            return
        self.telemetry_sink.record(
            AgentExecutionMetric(
                cycle_id=snapshot.snapshot_id,
                snapshot_id=snapshot.snapshot_id,
                agent_name=result.agent_name,
                elapsed_ms=elapsed_ms,
                status=result.status,
                blocker_count=len(result.blockers),
                latency_budget_exceeded=elapsed_ms > self.agent_latency_budget_ms,
            )
        )

    def _memory_advisory_result(
        self,
        snapshot: MarketSnapshot,
        compiled_cycle_context: CompiledCycleContext,
    ) -> AgentResult:
        evidence = compiled_cycle_context.memory_advisory_evidence
        confidence = max((item.confidence for item in evidence), default=0.0)
        return AgentResult(
            agent_name="memory_advisory",
            agent_version=self.registry.get("memory_advisory").version,
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframes=snapshot.timeframes,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=0.0,
            score=0.0,
            confidence=round(min(confidence, 0.75), 6),
            evidence=tuple(f"memory:{item.memory_id}" for item in evidence),
            counter_evidence=tuple(
                f"{item.advisory_effect.value}:{item.memory_id}" for item in evidence
            ),
            warnings=("MEMORY_ADVISORY_EVIDENCE_APPLIED",),
            regime_compatibility="ADVISORY_ONLY",
            false_positive_risk=("historical_bias", "stale_memory"),
            reason_codes=("MEMORY_ADVISORY_EVIDENCE_BOUND",),
            calculation_metadata={
                "advisory_effects": tuple(
                    item.advisory_effect.value for item in evidence
                ),
                "memory_ids": tuple(item.memory_id for item in evidence),
                "signal_authority": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _preflight_result(
        self,
        snapshot: MarketSnapshot,
        decision: CapabilityPreflightDecision,
    ) -> AgentResult:
        """Expose an unexecuted capability as a fail-closed analysis outcome."""
        definition = self.registry.get(decision.capability_id)
        return AgentResult(
            agent_name=definition.name,
            agent_version=definition.version,
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframes=snapshot.timeframes,
            status=AgentStatus.NOT_APPLICABLE,
            data_quality=snapshot.data_quality,
            applicable=False,
            directional_vote=0.0,
            score=0.0,
            confidence=0.0,
            warnings=("CAPABILITY_PREFLIGHT_SKIPPED",),
            regime_compatibility="NOT_APPLICABLE",
            false_positive_risk=definition.false_positive_risk,
            promotion_status=definition.promotion_status,
            reason_codes=decision.reason_codes,
            calculation_metadata={
                "preflight": True,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _finalize_cycle(
        self,
        snapshot: MarketSnapshot,
        results: Mapping[str, AgentResult],
        extra_blockers: tuple[str, ...] = (),
        candidates: tuple[TradeCandidate, ...] = (),
        compiled_cycle_context: CompiledCycleContext | None = None,
        trading_intelligence: TradingIntelligenceState | None = None,
        *,
        cycle_started_ns: int,
        specialist_wall_ms: float,
        scheduler_overhead_ms: float,
        scheduled_capability_count: int,
        executed_capability_count: int,
        scheduled_bundle_count: int,
        skipped_bundle_count: int,
        bundle_task_count: int,
    ) -> AnalysisState:
        """Finalize a cycle and emit non-authoritative baseline telemetry."""
        state = self._finalize(
            snapshot,
            results,
            extra_blockers=extra_blockers,
            candidates=candidates,
            compiled_cycle_context=compiled_cycle_context,
            trading_intelligence=trading_intelligence,
        )
        self._record_cycle_metric(
            snapshot,
            cycle_started_ns=cycle_started_ns,
            specialist_wall_ms=specialist_wall_ms,
            scheduler_overhead_ms=scheduler_overhead_ms,
            scheduled_capability_count=scheduled_capability_count,
            executed_capability_count=executed_capability_count,
            scheduled_bundle_count=scheduled_bundle_count,
            skipped_bundle_count=skipped_bundle_count,
            bundle_task_count=bundle_task_count,
        )
        return state

    def _record_cycle_metric(
        self,
        snapshot: MarketSnapshot,
        *,
        cycle_started_ns: int,
        specialist_wall_ms: float,
        scheduler_overhead_ms: float,
        scheduled_capability_count: int,
        executed_capability_count: int,
        scheduled_bundle_count: int,
        skipped_bundle_count: int,
        bundle_task_count: int,
    ) -> None:
        """Record baseline data only when the optional sink supports it."""
        if not isinstance(self.telemetry_sink, CycleTelemetrySink):
            return
        self.telemetry_sink.record_cycle(
            OrchestrationCycleMetric(
                cycle_id=snapshot.snapshot_id,
                snapshot_id=snapshot.snapshot_id,
                cycle_wall_ms=(perf_counter_ns() - cycle_started_ns) / 1_000_000.0,
                specialist_wall_ms=specialist_wall_ms,
                scheduler_overhead_ms=scheduler_overhead_ms,
                scheduled_capability_count=scheduled_capability_count,
                executed_capability_count=executed_capability_count,
                skipped_capability_count=(
                    scheduled_capability_count - executed_capability_count
                ),
                scheduled_bundle_count=scheduled_bundle_count,
                skipped_bundle_count=skipped_bundle_count,
                bundle_task_count=bundle_task_count,
            )
        )

    def _finalize(
        self,
        snapshot: MarketSnapshot,
        results: Mapping[str, AgentResult],
        extra_blockers: tuple[str, ...] = (),
        candidates: tuple[TradeCandidate, ...] = (),
        compiled_cycle_context: CompiledCycleContext | None = None,
        trading_intelligence: TradingIntelligenceState | None = None,
    ) -> AnalysisState:
        """Build the immutable state and final fail-closed decision."""
        if trading_intelligence is None:
            trading_intelligence = self.trading_intelligence_engine.blocked(
                snapshot,
                tuple(
                    dict.fromkeys(
                        (
                            "TRADING_INTELLIGENCE_NOT_EVALUATED",
                            *extra_blockers,
                        )
                    )
                ),
            )
        validation_blockers = tuple(
            dict.fromkeys(
                (
                    *extra_blockers,
                    *_compiled_cycle_context_blockers(compiled_cycle_context),
                )
            )
        )
        decision = self.validation_agent.validate(
            snapshot,
            results,
            extra_blockers=validation_blockers,
            candidates=candidates,
        )
        blockers = tuple(dict.fromkeys(decision.blockers))
        warnings = tuple(dict.fromkeys(decision.warnings))
        return AnalysisState(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            timestamp=snapshot.created_at,
            market_snapshot=snapshot,
            agent_results=results,
            blockers=blockers,
            warnings=warnings,
            candidate_setups=candidates,
            final_decision=decision,
            compiled_cycle_context=compiled_cycle_context,
            trading_intelligence=trading_intelligence,
        )


def _compiled_cycle_context_blockers(
    compiled_cycle_context: CompiledCycleContext | None,
) -> tuple[str, ...]:
    if compiled_cycle_context is None or not compiled_cycle_context.blockers:
        return ()
    return tuple(
        dict.fromkeys(("MEMORY_GUARDIAN_VETO", *compiled_cycle_context.blockers))
    )

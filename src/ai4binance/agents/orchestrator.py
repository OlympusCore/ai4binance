"""Dependency-aware deterministic enterprise orchestrator."""

from collections.abc import Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter_ns
from types import MappingProxyType

from ai4binance.agents.advanced import build_advanced_agent
from ai4binance.agents.base import BaseAgent
from ai4binance.agents.catalog import (
    ORCHESTRATED_SPECIALIST_NAMES,
    build_default_registry,
)
from ai4binance.agents.registry import AgentRegistry
from ai4binance.agents.specialists import (
    ConfluenceAgent,
    DataQualityAgent,
    ResearchOnlyAgent,
    RiskAgent,
    UniverseLiquidityAgent,
)
from ai4binance.agents.technical import build_core_technical_agent
from ai4binance.agents.telemetry import AgentExecutionMetric, AgentTelemetrySink
from ai4binance.agents.trend_events import build_trend_events_agent
from ai4binance.agents.validation import ValidationAgent
from ai4binance.domain import TradeCandidate
from ai4binance.schemas import AgentResult, AgentStatus, AnalysisState, MarketSnapshot
from ai4binance.strategies import StrategyEngine
from ai4binance.strategies.arbitration import CandidateArbitrator
from ai4binance.whale_fusion.agent import build_whale_fusion_agent


@dataclass(frozen=True, slots=True)
class EnterpriseOrchestrator:
    """Coordinate immutable snapshot analysis without calculating indicators."""

    registry: AgentRegistry = field(default_factory=build_default_registry)
    max_workers: int = 8
    minimum_candles: int = 2
    validation_agent: ValidationAgent = field(default_factory=ValidationAgent)
    strategy_engine: StrategyEngine = field(default_factory=StrategyEngine)
    candidate_arbitrator: CandidateArbitrator = field(
        default_factory=CandidateArbitrator
    )
    telemetry_sink: AgentTelemetrySink | None = None
    agent_latency_budget_ms: float = 1_000.0

    def __post_init__(self) -> None:
        """Bound concurrency and minimum-history configuration."""
        if not 1 <= self.max_workers <= 32:
            raise ValueError("max_workers must be between 1 and 32")
        if self.minimum_candles < 2:
            raise ValueError("minimum_candles must be at least 2")
        if not 1.0 <= self.agent_latency_budget_ms <= 60_000.0:
            raise ValueError("agent latency budget must be between 1 and 60000 ms")

    def analyze(self, snapshot: MarketSnapshot) -> AnalysisState:
        """Run eligibility, specialists, synthesis, risk and final validation."""
        results: dict[str, AgentResult] = {}
        data_agent = DataQualityAgent(
            self.registry.get("data_quality"),
            minimum_candles=self.minimum_candles,
        )
        results[data_agent.definition.name] = self._run_agent(
            data_agent, snapshot, results
        )
        if results["data_quality"].status is AgentStatus.BLOCKED:
            return self._finalize(snapshot, results, ("EARLY_EXIT_NO_TRADE",))

        universe_agent = UniverseLiquidityAgent(self.registry.get("universe_liquidity"))
        results[universe_agent.definition.name] = self._run_agent(
            universe_agent, snapshot, results
        )
        if results["universe_liquidity"].status is AgentStatus.BLOCKED:
            return self._finalize(snapshot, results, ("EARLY_EXIT_NO_TRADE",))

        specialist_agents_list: list[BaseAgent] = []
        for name in ORCHESTRATED_SPECIALIST_NAMES:
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
        with ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="ai4binance-agent",
        ) as executor:
            self._run_dependency_layers(
                snapshot,
                specialist_agents,
                results,
                executor,
            )

        confluence_agent = ConfluenceAgent(
            self.registry.get("confluence"),
            registry=self.registry,
        )
        results[confluence_agent.definition.name] = self._run_agent(
            confluence_agent, snapshot, MappingProxyType(results)
        )
        candidates = self.strategy_engine.generate(
            snapshot,
            MappingProxyType(results),
        )
        selection = self.candidate_arbitrator.select(candidates)
        risk_candidates = selection.ranked[:5] if selection.selected is not None else ()
        risk_agent = RiskAgent(self.registry.get("risk"), candidates=risk_candidates)
        results[risk_agent.definition.name] = self._run_agent(
            risk_agent, snapshot, MappingProxyType(results)
        )
        return self._finalize(
            snapshot,
            results,
            extra_blockers=selection.blockers,
            candidates=candidates,
        )

    def _run_dependency_layers(
        self,
        snapshot: MarketSnapshot,
        agents: tuple[BaseAgent, ...],
        results: dict[str, AgentResult],
        executor: Executor,
    ) -> None:
        """Run each ready dependency layer in bounded parallel workers."""
        pending = {agent.definition.name: agent for agent in agents}
        while pending:
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
            futures = {
                name: executor.submit(
                    self._timed_agent_call,
                    pending[name],
                    snapshot,
                    prior_results,
                )
                for name in ready_names
            }
            for name in ready_names:
                result, elapsed_ms = futures[name].result()
                results[name] = result
                self._record_metric(snapshot, result, elapsed_ms)
                del pending[name]

    def _run_agent(
        self,
        agent: BaseAgent,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        result, elapsed_ms = self._timed_agent_call(agent, snapshot, prior_results)
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

    def _finalize(
        self,
        snapshot: MarketSnapshot,
        results: Mapping[str, AgentResult],
        extra_blockers: tuple[str, ...] = (),
        candidates: tuple[TradeCandidate, ...] = (),
    ) -> AnalysisState:
        """Build the immutable state and final fail-closed decision."""
        decision = self.validation_agent.validate(
            snapshot,
            results,
            extra_blockers=extra_blockers,
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
        )

"""Bounded runtime execution for one declarative capability bundle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter_ns
from types import MappingProxyType

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.registry import CapabilityBundleDefinition
from ai4binance.schemas import AgentResult, MarketSnapshot


@dataclass(frozen=True, slots=True)
class CapabilityBundleExecutor:
    """Run ready members of one bundle against one immutable result view."""

    definition: CapabilityBundleDefinition
    agents_by_capability_id: Mapping[str, BaseAgent]
    _agents_by_capability_id: Mapping[str, BaseAgent] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        agents_by_capability_id = dict(self.agents_by_capability_id)
        if not agents_by_capability_id:
            raise ValueError("capability bundle executor requires scheduled agents")
        unknown_ids = set(agents_by_capability_id).difference(
            self.definition.capability_ids
        )
        if unknown_ids:
            raise ValueError("bundle executor contains capabilities outside its bundle")
        incorrect_identities = tuple(
            capability_id
            for capability_id, agent in agents_by_capability_id.items()
            if agent.definition.name != capability_id
        )
        if incorrect_identities:
            raise ValueError(
                "bundle executor agent identities must match capability ids"
            )
        object.__setattr__(
            self,
            "_agents_by_capability_id",
            MappingProxyType(agents_by_capability_id),
        )

    def run_ready(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
        ready_capability_ids: tuple[str, ...],
    ) -> tuple[tuple[str, AgentResult, float], ...]:
        """Run one ready dependency layer in bundle membership order."""
        if not ready_capability_ids or len(set(ready_capability_ids)) != len(
            ready_capability_ids
        ):
            raise ValueError("ready capability ids must be unique and non-empty")
        ready_ids = frozenset(ready_capability_ids)
        unavailable_ids = ready_ids.difference(self._agents_by_capability_id)
        if unavailable_ids:
            raise ValueError("bundle executor received unavailable capabilities")
        immutable_prior_results = MappingProxyType(dict(prior_results))
        executions: list[tuple[str, AgentResult, float]] = []
        for capability_id in self.definition.capability_ids:
            if capability_id not in ready_ids:
                continue
            started_ns = perf_counter_ns()
            result = self._agents_by_capability_id[capability_id].run(
                snapshot,
                immutable_prior_results,
            )
            elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000.0
            executions.append((capability_id, result, elapsed_ms))
        return tuple(executions)

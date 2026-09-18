"""Compatibility facade for final deterministic validation."""

from collections.abc import Mapping
from dataclasses import dataclass

from ai4binance.agents.validation_gate import ValidationGate
from ai4binance.domain import Signal, TradeCandidate
from ai4binance.schemas import AgentResult, MarketSnapshot


@dataclass(frozen=True, slots=True)
class ValidationAgent:
    """Compatibility facade for the canonical `ValidationGate`."""

    version: str = "0.2.0"

    def validate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        *,
        extra_blockers: tuple[str, ...] = (),
        candidates: tuple[TradeCandidate, ...] = (),
    ) -> Signal:
        """Delegate final deterministic validation without execution authority."""
        return ValidationGate(version=self.version).validate(
            snapshot,
            agent_results,
            extra_blockers=extra_blockers,
            candidates=candidates,
        )

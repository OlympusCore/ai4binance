"""Immutable agent definitions and dependency registry."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ai4binance.schemas import PromotionStatus


class AgentStage(StrEnum):
    """Dependency-aware platform stages."""

    ACQUISITION = "ACQUISITION"
    ELIGIBILITY = "ELIGIBILITY"
    ANALYSIS = "ANALYSIS"
    SYNTHESIS = "SYNTHESIS"
    RISK = "RISK"
    VALIDATION = "VALIDATION"
    EXECUTION = "EXECUTION"
    RESEARCH = "RESEARCH"
    LEARNING = "LEARNING"


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Governed technical-method and platform-agent declaration."""

    name: str
    family: str
    version: str
    stage: AgentStage
    required_data: tuple[str, ...]
    supported_timeframes: tuple[str, ...]
    compatible_regimes: tuple[str, ...]
    output_schema: str = "AgentResult/v1"
    score_range: tuple[float, float] = (0.0, 100.0)
    hard_gate_eligible: bool = False
    false_positive_risk: tuple[str, ...] = field(default_factory=tuple)
    oos_requirements: tuple[str, ...] = field(default_factory=tuple)
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH_ONLY
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    evidence_cluster: str = "diagnostic"
    expensive: bool = False

    def __post_init__(self) -> None:
        """Reject incomplete or prematurely promoted declarations."""
        for field_name in ("name", "family", "version", "output_schema"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        lower, upper = self.score_range
        if lower < 0.0 or upper > 100.0 or lower > upper:
            raise ValueError("score_range must be ordered within 0 and 100")
        if self.name in self.dependencies:
            raise ValueError("an agent cannot depend on itself")
        if self.hard_gate_eligible and self.promotion_status not in {
            PromotionStatus.PAPER_APPROVED,
            PromotionStatus.LIVE_ELIGIBLE,
        }:
            raise ValueError("hard-gate agents require governed promotion")
        if self.hard_gate_eligible and not self.oos_requirements:
            raise ValueError("hard-gate agents require explicit OOS requirements")


@dataclass(frozen=True, slots=True)
class AgentRegistry:
    """Immutable registry with unique names and validated dependencies."""

    definitions: tuple[AgentDefinition, ...]
    _by_name: Mapping[str, AgentDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build an immutable lookup and reject unknown dependencies."""
        by_name = {definition.name: definition for definition in self.definitions}
        if len(by_name) != len(self.definitions):
            raise ValueError("agent names must be unique")
        for definition in self.definitions:
            unknown = tuple(
                dependency
                for dependency in definition.dependencies
                if dependency not in by_name
            )
            if unknown:
                joined = ", ".join(unknown)
                raise ValueError(
                    f"unknown dependencies for {definition.name}: {joined}"
                )
        unresolved = {
            definition.name: set(definition.dependencies)
            for definition in self.definitions
        }
        resolved: set[str] = set()
        while unresolved:
            ready = tuple(
                name
                for name, dependencies in unresolved.items()
                if dependencies <= resolved
            )
            if not ready:
                raise ValueError("agent dependency graph contains a cycle")
            resolved.update(ready)
            for name in ready:
                del unresolved[name]
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def get(self, name: str) -> AgentDefinition:
        """Return one registered definition."""
        return self._by_name[name]

    def by_stage(self, stage: AgentStage) -> tuple[AgentDefinition, ...]:
        """Return stage definitions in stable registration order."""
        return tuple(item for item in self.definitions if item.stage is stage)

    @property
    def by_name(self) -> Mapping[str, AgentDefinition]:
        """Expose the immutable name lookup."""
        return self._by_name

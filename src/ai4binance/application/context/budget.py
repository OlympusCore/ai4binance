"""Canonical bounded advisory context assembly."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import ceil

from ai4binance.core.contracts.memory import memory_canonical_sha256


class ContextBudgetExceededError(ValueError):
    """Raised before advisory inference when context cannot fit safely."""


@dataclass(frozen=True, slots=True)
class TokenBudget:
    context_window: int = 4096
    max_system: int = 512
    max_current_input: int = 512
    max_history: int = 512
    max_context: int = 2048
    max_fragment: int = 384
    max_tool_schemas: int = 256
    output_reserve: int = 512

    def __post_init__(self) -> None:
        values = (
            self.context_window,
            self.max_system,
            self.max_current_input,
            self.max_history,
            self.max_context,
            self.max_fragment,
            self.max_tool_schemas,
            self.output_reserve,
        )
        if any(value < 0 for value in values) or self.context_window <= 0:
            raise ValueError("token budget values must be non-negative")
        if self.output_reserve > self.context_window:
            raise ValueError("token budget output reserve exceeds context window")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    system: int
    current_input: int
    history: int
    context: int
    tool_schemas: int
    output_reserve: int

    @property
    def total(self) -> int:
        return (
            self.system
            + self.current_input
            + self.history
            + self.context
            + self.tool_schemas
            + self.output_reserve
        )

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.system,
                self.current_input,
                self.history,
                self.context,
                self.tool_schemas,
                self.output_reserve,
            )
        ):
            raise ValueError("token usage cannot be negative")


class ConservativeTokenEstimator:
    """UTF-8 estimator biased toward over-counting structured multilingual text."""

    _BYTES_PER_TOKEN = 3

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, ceil(len(text.encode("utf-8")) / self._BYTES_PER_TOKEN))

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        if self.count(text) <= max_tokens:
            return text
        low = 0
        high = len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self.count(text[:middle]) <= max_tokens:
                low = middle
            else:
                high = middle - 1
        return text[:low]


@dataclass(frozen=True, slots=True)
class TokenBudgetGuard:
    budget: TokenBudget = field(default_factory=TokenBudget)
    estimator: ConservativeTokenEstimator = field(
        default_factory=ConservativeTokenEstimator
    )

    def measure(
        self,
        *,
        system: str,
        current_input: str,
        history: str,
        context: str,
        tool_schemas: str,
    ) -> TokenUsage:
        return TokenUsage(
            system=self.estimator.count(system),
            current_input=self.estimator.count(current_input),
            history=self.estimator.count(history),
            context=self.estimator.count(context),
            tool_schemas=self.estimator.count(tool_schemas),
            output_reserve=self.budget.output_reserve,
        )

    def validate(self, usage: TokenUsage) -> None:
        blockers: list[str] = []
        if usage.system > self.budget.max_system:
            blockers.append("SYSTEM_TOKEN_BUDGET_EXCEEDED")
        if usage.current_input > self.budget.max_current_input:
            blockers.append("INPUT_TOKEN_BUDGET_EXCEEDED")
        if usage.history > self.budget.max_history:
            blockers.append("HISTORY_TOKEN_BUDGET_EXCEEDED")
        if usage.context > self.budget.max_context:
            blockers.append("CONTEXT_TOKEN_BUDGET_EXCEEDED")
        if usage.tool_schemas > self.budget.max_tool_schemas:
            blockers.append("TOOL_SCHEMA_TOKEN_BUDGET_EXCEEDED")
        if usage.total > self.budget.context_window:
            blockers.append("CONTEXT_WINDOW_EXCEEDED")
        if blockers:
            raise ContextBudgetExceededError(",".join(blockers))


@dataclass(frozen=True, slots=True)
class ContextFragment:
    source: str
    content: str
    priority: int = 0
    classification: str = "PUBLIC_RESEARCH"
    evidence_status: str = "VALIDATED"
    authority: str = "READ_ONLY"
    expires_at: datetime | None = None

    @property
    def content_sha256(self) -> str:
        return memory_canonical_sha256(self.content)

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.content.strip():
            raise ValueError("context fragment source and content are required")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("context fragment expiry must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ContextAssembly:
    rendered_context: str
    usage: TokenUsage
    kept_sources: tuple[str, ...]
    truncated_sources: tuple[str, ...]
    dropped_sources: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("context assembly cannot authorize trading")


class BoundedContextAssembler:
    def __init__(self, guard: TokenBudgetGuard | None = None) -> None:
        self._guard = guard or TokenBudgetGuard()

    def assemble(
        self,
        *,
        system: str,
        current_input: str,
        fragments: Iterable[ContextFragment],
        history: str = "",
        tool_schemas: str = "",
    ) -> ContextAssembly:
        now = datetime.now(UTC)
        active: list[ContextFragment] = []
        dropped: list[str] = []
        for fragment in fragments:
            if fragment.expires_at is not None and fragment.expires_at < now:
                dropped.append(fragment.source)
                continue
            if fragment.classification.upper() == "RESTRICTED":
                dropped.append(fragment.source)
                continue
            active.append(fragment)
        active.sort(key=lambda item: (-item.priority, item.source))

        rendered: list[tuple[ContextFragment, str]] = []
        truncated: list[str] = []
        for fragment in active:
            content = fragment.content
            if self._guard.estimator.count(content) > self._guard.budget.max_fragment:
                marker = "\n[CONTEXT_TRUNCATED]"
                marker_tokens = self._guard.estimator.count(marker)
                content = self._guard.estimator.truncate(
                    content,
                    max(0, self._guard.budget.max_fragment - marker_tokens),
                )
                content += marker
                truncated.append(fragment.source)
            rendered.append((fragment, content))

        def render() -> str:
            return "\n\n".join(
                "\n".join(
                    (
                        f"[SOURCE {fragment.source}]",
                        f"EVIDENCE_STATUS={fragment.evidence_status}",
                        f"EVIDENCE_AUTHORITY={fragment.authority}",
                        f"EVIDENCE_CLASSIFICATION={fragment.classification}",
                        f"EVIDENCE_SHA256={fragment.content_sha256}",
                        content,
                    )
                )
                for fragment, content in rendered
            )

        context = render()
        usage = self._guard.measure(
            system=system,
            current_input=current_input,
            history=history,
            context=context,
            tool_schemas=tool_schemas,
        )
        while (
            usage.context > self._guard.budget.max_context
            or usage.total > self._guard.budget.context_window
        ):
            if not rendered:
                break
            removed, _ = rendered.pop()
            dropped.append(removed.source)
            context = render()
            usage = self._guard.measure(
                system=system,
                current_input=current_input,
                history=history,
                context=context,
                tool_schemas=tool_schemas,
            )
        self._guard.validate(usage)
        if active and not rendered:
            raise ContextBudgetExceededError("ALL_CONTEXT_EVIDENCE_DROPPED")
        return ContextAssembly(
            rendered_context=context,
            usage=usage,
            kept_sources=tuple(fragment.source for fragment, _ in rendered),
            truncated_sources=tuple(dict.fromkeys(truncated)),
            dropped_sources=tuple(sorted(set(dropped))),
        )

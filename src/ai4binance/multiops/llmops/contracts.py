"""Typed, observation-only contracts for Codex model-usage governance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_SUMMARY_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|api[_-]?token|"
    r"authorization|bearer\s+|password|private[_-]?key|secret|"
    r"sk-[a-z0-9_-]{8,})"
)


class TaskClass(StrEnum):
    TRIVIAL = "TRIVIAL"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskCriticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ModelTier(StrEnum):
    ECONOMY = "ECONOMY"
    BALANCED = "BALANCED"
    ADVANCED = "ADVANCED"
    EXCEPTIONAL = "EXCEPTIONAL"


class ReasoningEffort(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class TokenAccountingSource(StrEnum):
    EXACT_PROVIDER = "EXACT_PROVIDER"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"


class BudgetStatus(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    WITHIN_BUDGET = "WITHIN_BUDGET"
    TOKEN_BUDGET_WARNING = "TOKEN_BUDGET_WARNING"  # nosec B105  # noqa: S105
    TOKEN_BUDGET_EXCEEDED = "TOKEN_BUDGET_EXCEEDED"  # nosec B105  # noqa: S105


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_nonnegative(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} cannot be negative")


def _require_nonnegative_decimal(name: str, value: Decimal | None) -> None:
    if value is not None and (not value.is_finite() or value < 0):
        raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ModelUsageRecord:
    """One secret-safe usage observation; it grants no model or trade authority."""

    task_id: str
    timestamp: datetime
    task_type: str
    task_class: TaskClass
    criticality: TaskCriticality
    token_accounting_source: TokenAccountingSource
    sanitized_summary: str
    model_id: str | None = None
    model_tier: ModelTier | None = None
    reasoning_effort: ReasoningEffort | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None
    actual_cost_usd: Decimal | None = None
    context_files: int = 0
    context_bytes: int = 0
    tool_calls: int = 0
    subagent_calls: int = 0
    retry_count: int = 0
    escalation_count: int = 0
    quality_result: str = "UNVALIDATED"
    tests_passed: bool | None = None
    budget_status: BudgetStatus = BudgetStatus.UNCONFIGURED
    human_approval: str = "HUMAN_APPROVAL_REQUIRED"
    files_modified: tuple[str, ...] = ()
    escalation_reason: str | None = None
    prompt_hash: str | None = None
    routing_policy_version: str = "UNAVAILABLE"
    pricing_version: str = "UNAVAILABLE"
    model_registry_version: str = "UNAVAILABLE"
    task_classifier_version: str = "UNAVAILABLE"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for text_name, text_value in (
            ("task id", self.task_id),
            ("task type", self.task_type),
            ("sanitized summary", self.sanitized_summary),
            ("quality result", self.quality_result),
            ("human approval", self.human_approval),
        ):
            _require_text(text_name, text_value)
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("model usage timestamp must be timezone-aware")
        if len(self.sanitized_summary) > 512 or "\n" in self.sanitized_summary:
            raise ValueError("sanitized summary must be one bounded line")
        if _SECRET_SUMMARY_RE.search(self.sanitized_summary):
            raise ValueError("sanitized summary contains secret-like content")
        for count_name, count_value in (
            ("input tokens", self.input_tokens),
            ("cached input tokens", self.cached_input_tokens),
            ("output tokens", self.output_tokens),
            ("reasoning tokens", self.reasoning_tokens),
            ("total tokens", self.total_tokens),
            ("context files", self.context_files),
            ("context bytes", self.context_bytes),
            ("tool calls", self.tool_calls),
            ("subagent calls", self.subagent_calls),
            ("retry count", self.retry_count),
            ("escalation count", self.escalation_count),
        ):
            _require_nonnegative(count_name, count_value)
        for cost_name, cost_value in (
            ("estimated cost", self.estimated_cost_usd),
            ("actual cost", self.actual_cost_usd),
        ):
            _require_nonnegative_decimal(cost_name, cost_value)
        if (
            self.cached_input_tokens is not None
            and self.input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("cached input tokens cannot exceed input tokens")
        counters = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.total_tokens,
        )
        if self.token_accounting_source is TokenAccountingSource.UNAVAILABLE and any(
            value is not None for value in counters
        ):
            raise ValueError("unavailable token accounting cannot carry counters")
        if self.token_accounting_source is TokenAccountingSource.EXACT_PROVIDER and any(
            value is None
            for value in (self.input_tokens, self.output_tokens, self.total_tokens)
        ):
            raise ValueError("exact provider accounting requires core token counters")
        if (
            self.token_accounting_source is TokenAccountingSource.ESTIMATED
            and self.total_tokens is None
        ):
            raise ValueError("estimated token accounting requires total tokens")
        if self.actual_cost_usd is not None and (
            self.token_accounting_source is not TokenAccountingSource.EXACT_PROVIDER
        ):
            raise ValueError("actual cost requires exact provider accounting")
        if self.prompt_hash is not None and not _SHA256_RE.fullmatch(self.prompt_hash):
            raise ValueError("prompt hash must be lowercase sha256")
        if len(set(self.files_modified)) != len(self.files_modified) or any(
            not item.strip() for item in self.files_modified
        ):
            raise ValueError("modified file list must be unique and nonblank")
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("model id cannot be blank")
        if self.escalation_reason is not None and not self.escalation_reason.strip():
            raise ValueError("escalation reason cannot be blank")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model usage observation cannot authorize execution")

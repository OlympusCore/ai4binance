"""Executive-only prompt intake and redaction contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise.contracts import (
    BoardDirective,
    DepartmentId,
    WorkflowIdentity,
)
from ai4binance.enterprise.departments import DepartmentRegistry


class PromptVisibility(StrEnum):
    GENERAL_MANAGER_ONLY = "GENERAL_MANAGER_ONLY"
    DEPARTMENT_SUMMARY = "DEPARTMENT_SUMMARY"
    AGENT_TASK_CONTEXT = "AGENT_TASK_CONTEXT"


class PromptAccessStatus(StrEnum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


_RESTRICTED_MARKERS = (
    "RAW_PROMPT:",
    "USER_PROMPT:",
    "CODEX_PROMPT:",
    "RAW PROMPT:",
    "USER PROMPT:",
    "CODEX PROMPT:",
    "BEGIN_RAW_PROMPT",
    "END_RAW_PROMPT",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "PRIVATE_KEY",
    "SECRET=",
    "API_KEY=",
    "WALLET_BALANCE",
    "HOT_BALANCE",
    "USDT_BALANCE",
    "HOT BALANCE",
    "USDT BALANCE",
)

_SECRET_PATTERNS = (
    re.compile(
        r"\b(?:BINANCE_)?(?:API[_ -]?KEY|API[_ -]?SECRET|SECRET|PRIVATE[_ -]?KEY)"
        r"\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:HOT|USDT|WALLET)[_ -]?BALANCE\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:RAW|USER|CODEX)[_ -]?PROMPT\b\s*[:=]\s*", re.IGNORECASE),
)


def contains_restricted_prompt_content(value: str) -> bool:
    """Return True when text appears to carry raw prompt or sensitive context."""
    normalized = value.upper()
    return any(marker in normalized for marker in _RESTRICTED_MARKERS)


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _require_no_restricted_content(name: str, values: tuple[str, ...]) -> None:
    for value in values:
        if contains_restricted_prompt_content(value):
            raise ValueError(f"{name} cannot contain raw prompt or sensitive context")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_prompt(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SENSITIVE_CONTEXT] ", redacted)
    return " ".join(redacted.split())


def _summary(value: str, *, limit: int = 240) -> str:
    redacted = _redact_prompt(value)
    if len(redacted) <= limit:
        return redacted
    return f"{redacted[: limit - 3].rstrip()}..."


@dataclass(frozen=True, slots=True)
class PromptAccessDecision:
    status: PromptAccessStatus
    actor_department_id: DepartmentId
    actor_role: str
    prompt_id: str
    visibility: PromptVisibility
    reason_codes: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("prompt access actor role", self.actor_role)
        _require_text("prompt access prompt_id", self.prompt_id)
        _require_unique_text("prompt access reasons", self.reason_codes)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("prompt access cannot authorize execution")
        if self.status is PromptAccessStatus.ALLOWED and self.reason_codes != (
            "GENERAL_MANAGER_RAW_PROMPT_ACCESS",
        ):
            raise ValueError("raw prompt access is restricted to the general manager")


@dataclass(frozen=True, slots=True)
class ExecutivePromptIntake:
    """Prompt-derived directive record that never stores the raw prompt text."""

    identity: WorkflowIdentity
    prompt_id: str
    submitted_by: str
    raw_prompt_sha256: str
    raw_prompt_ref: str
    sanitized_summary: str
    objective: str
    constraints: tuple[str, ...]
    authority_scope: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = (
        "GENERAL_MANAGER_ONLY_RAW_PROMPT",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    raw_prompt_visibility: PromptVisibility = PromptVisibility.GENERAL_MANAGER_ONLY
    department_visibility: PromptVisibility = PromptVisibility.DEPARTMENT_SUMMARY
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("prompt_id", self.prompt_id)
        _require_text("submitted_by", self.submitted_by)
        _require_text("raw_prompt_ref", self.raw_prompt_ref)
        _require_text("sanitized_summary", self.sanitized_summary)
        _require_text("objective", self.objective)
        if len(self.raw_prompt_sha256) != 64:
            raise ValueError("raw prompt hash must be sha256")
        int(self.raw_prompt_sha256, 16)
        _require_unique_text("prompt constraints", self.constraints)
        _require_unique_text("prompt authority scope", self.authority_scope)
        _require_unique_text("prompt evidence refs", self.evidence_refs)
        _require_unique_text("prompt blockers", self.blockers)
        _require_no_restricted_content(
            "sanitized prompt fields",
            (
                self.sanitized_summary,
                self.objective,
                *self.constraints,
                *self.authority_scope,
            ),
        )
        if self.raw_prompt_visibility is not PromptVisibility.GENERAL_MANAGER_ONLY:
            raise ValueError("raw prompt must remain general-manager-only")
        if self.department_visibility is not PromptVisibility.DEPARTMENT_SUMMARY:
            raise ValueError("department prompt context must be summary-only")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("prompt intake cannot promote production state")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("prompt intake cannot authorize execution")

    @classmethod
    def from_raw_prompt(
        cls,
        *,
        identity: WorkflowIdentity,
        prompt_id: str,
        submitted_by: str,
        raw_prompt: str,
        objective: str | None = None,
        constraints: tuple[str, ...] = (),
        authority_scope: tuple[str, ...] = (),
    ) -> ExecutivePromptIntake:
        _require_text("raw prompt", raw_prompt)
        prompt_hash = _sha256_text(raw_prompt)
        safe_summary = _summary(raw_prompt)
        safe_objective = _summary(objective or safe_summary, limit=180)
        return cls(
            identity=identity,
            prompt_id=prompt_id,
            submitted_by=submitted_by,
            raw_prompt_sha256=prompt_hash,
            raw_prompt_ref=f"prompt:{prompt_id}:{prompt_hash[:12]}",
            sanitized_summary=safe_summary,
            objective=safe_objective,
            constraints=(
                _stable_unique(
                    (
                        "GENERAL_MANAGER_ONLY_RAW_PROMPT",
                        "DEPARTMENT_SUMMARY_ONLY",
                        "NO_LIVE_AUTHORITY",
                        *constraints,
                    )
                )
            ),
            authority_scope=(
                _stable_unique(
                    (
                        "WORK_ORDER_PREVIEW",
                        "RESEARCH_ONLY",
                        "LIVE_ORDER_BLOCKED",
                        *authority_scope,
                    )
                )
            ),
            evidence_refs=(f"prompt-sha256:{prompt_hash}",),
        )

    def to_board_directive(
        self,
        *,
        directive_id: str,
        resource_budget: str,
        time_budget_seconds: int,
    ) -> BoardDirective:
        return BoardDirective(
            identity=self.identity,
            directive_id=directive_id,
            requested_by=self.submitted_by,
            objective=self.objective,
            constraints=self.constraints,
            authority_scope=self.authority_scope,
            resource_budget=resource_budget,
            time_budget_seconds=time_budget_seconds,
        )


@dataclass(frozen=True, slots=True)
class PromptAccessPolicy:
    """Authorize raw prompt visibility for the executive office only."""

    registry: DepartmentRegistry

    def authorize_raw_prompt(
        self,
        *,
        actor_department_id: DepartmentId,
        actor_role: str,
        intake: ExecutivePromptIntake,
    ) -> PromptAccessDecision:
        expected_manager = self.registry.get(DepartmentId.EXECUTIVE_OFFICE).manager_role
        if (
            actor_department_id is DepartmentId.EXECUTIVE_OFFICE
            and actor_role == expected_manager
        ):
            return PromptAccessDecision(
                PromptAccessStatus.ALLOWED,
                actor_department_id,
                actor_role,
                intake.prompt_id,
                intake.raw_prompt_visibility,
                ("GENERAL_MANAGER_RAW_PROMPT_ACCESS",),
            )
        return PromptAccessDecision(
            PromptAccessStatus.BLOCKED,
            actor_department_id,
            actor_role,
            intake.prompt_id,
            intake.raw_prompt_visibility,
            ("PROMPT_ACCESS_BLOCKED", "LIVE_ORDER_BLOCKED"),
        )

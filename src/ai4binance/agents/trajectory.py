"""Deterministic, privacy-bounded trajectory review for advisory agent runs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_MARKERS = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer\s+|password|secret|token|"
    r"sk-[a-z0-9_-]{8,}|lv_[a-z0-9_-]{8,})"
)
_FAILURE_MARKERS = (
    "traceback (most recent call last)",
    "error:",
    "error ",
    "exception",
    "failed",
    "failing",
    "no such file",
    "command not found",
    "permission denied",
    "timed out",
    "exit code 1",
    "exit code 2",
    "assertionerror",
    "syntaxerror",
    "cannot find module",
)
_ERROR_CLASSES = (
    ("modulenotfounderror", "ModuleNotFoundError"),
    ("importerror", "ImportError"),
    ("syntaxerror", "SyntaxError"),
    ("indentationerror", "IndentationError"),
    ("nameerror", "NameError"),
    ("typeerror", "TypeError"),
    ("valueerror", "ValueError"),
    ("attributeerror", "AttributeError"),
    ("keyerror", "KeyError"),
    ("indexerror", "IndexError"),
    ("zerodivisionerror", "ZeroDivisionError"),
    ("assertionerror", "AssertionError"),
    ("segmentation fault", "SegFault"),
    ("no such file", "FileNotFound"),
    ("cannot find module", "ModuleNotFoundError"),
    ("command not found", "CommandNotFound"),
    ("permission denied", "PermissionDenied"),
    ("timed out", "Timeout"),
    ("exit code 1", "ProcessExit1"),
    ("exit code 2", "ProcessExit2"),
)
_WRITE_TOOLS = (
    "apply_patch",
    "edit",
    "format",
    "move",
    "patch",
    "replace",
    "write",
)
_VERIFICATION_TOOLS = (
    "bandit",
    "compile",
    "mypy",
    "pip check",
    "pytest",
    "quality",
    "ruff",
    "test",
    "typecheck",
)
_BASELINE_BLOCKERS = ("LIVE_ORDER_BLOCKED",)


class AgentTrajectorySignal(StrEnum):
    ACTION_OBSERVATION_REPEAT = "ACTION_OBSERVATION_REPEAT"
    REPEATED_ERROR_CLASS = "REPEATED_ERROR_CLASS"
    PING_PONG_ACTIONS = "PING_PONG_ACTIONS"
    REWRITE_RETEST_CYCLE = "REWRITE_RETEST_CYCLE"
    STEPS_WITHOUT_PROGRESS = "STEPS_WITHOUT_PROGRESS"
    BUDGET_GUARDRAIL = "BUDGET_GUARDRAIL"
    TRAJECTORY_EMPTY = "TRAJECTORY_EMPTY"


class AgentTrajectoryVerdict(StrEnum):
    CONTINUE_RESEARCH = "CONTINUE_RESEARCH"
    WATCHLIST = "WATCHLIST"
    RESTART_RECOMMENDED = "RESTART_RECOMMENDED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class AgentTrajectoryStep:
    """One bounded observation of what an advisory agent actually did."""

    index: int
    tool_name: str
    args_digest: str
    output_digest: str
    ok: bool
    error_class: str = ""
    args_preview: str = ""
    output_preview: str = ""
    verification_passed: bool = False

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("trajectory step index must be positive")
        _require_text(self.tool_name, "trajectory step tool name", max_len=200)
        _require_digest(self.args_digest, "trajectory args digest")
        _require_digest(self.output_digest, "trajectory output digest")
        _require_preview(self.args_preview, "trajectory args preview")
        _require_preview(self.output_preview, "trajectory output preview")
        if self.ok and self.error_class:
            raise ValueError("successful trajectory step cannot carry an error class")
        if self.error_class:
            _require_text(self.error_class, "trajectory error class", max_len=120)

    @classmethod
    def from_observation(
        cls,
        *,
        index: int,
        tool_name: str,
        arguments: object,
        output: object,
        ok: bool | None = None,
        verification_passed: bool = False,
        max_preview_chars: int = 220,
    ) -> AgentTrajectoryStep:
        output_text = _canonical_text(output)
        observed_ok = (not _looks_like_failure(output_text)) if ok is None else ok
        error_class = "" if observed_ok else classify_error(output_text)
        return cls(
            index=index,
            tool_name=tool_name,
            args_digest=_sha256(_canonical_text(arguments)),
            output_digest=_sha256(output_text),
            ok=observed_ok,
            error_class=error_class,
            args_preview=_safe_preview(arguments, max_chars=max_preview_chars),
            output_preview=_safe_preview(output, max_chars=max_preview_chars),
            verification_passed=verification_passed,
        )


@dataclass(frozen=True, slots=True)
class AgentTrajectoryReview:
    """Research-only route review produced from deterministic trajectory signals."""

    session_id: str
    task_name: str
    selected_pattern: str
    steps: tuple[AgentTrajectoryStep, ...]
    signals: tuple[AgentTrajectorySignal, ...]
    verdict: AgentTrajectoryVerdict
    blockers: tuple[str, ...]
    review_rule: str = "HUMAN_REVIEW_REQUIRED_FOR_RESTART_OR_TRADING_SCOPE"
    before_after_measurement: str = (
        "before=prompt_or_self_report_estimate; "
        "after=digest_backed_tool_test_loop_progress_signals"
    )
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY_TRAJECTORY_REVIEW"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(self.session_id, "trajectory session id", max_len=240)
        _require_text(self.task_name, "trajectory task name", max_len=500)
        _require_text(self.selected_pattern, "trajectory pattern", max_len=240)
        _require_text(self.review_rule, "trajectory review rule", max_len=240)
        _require_text(
            self.before_after_measurement,
            "trajectory before/after measurement",
            max_len=500,
        )
        if tuple(step.index for step in self.steps) != tuple(
            range(1, len(self.steps) + 1)
        ):
            raise ValueError("trajectory step indexes must be contiguous")
        if len(set(self.signals)) != len(self.signals):
            raise ValueError("trajectory signals must be unique")
        _require_unique_text(self.blockers, "trajectory blockers")
        if self.verdict is AgentTrajectoryVerdict.CONTINUE_RESEARCH:
            unexpected = tuple(
                blocker
                for blocker in self.blockers
                if blocker not in _BASELINE_BLOCKERS
            )
            if self.signals or unexpected:
                raise ValueError("continue trajectory review cannot carry blockers")
        elif not any(blocker not in _BASELINE_BLOCKERS for blocker in self.blockers):
            raise ValueError("non-continue trajectory review requires a blocker")
        if self.execution_allowed:
            raise ValueError("trajectory review cannot grant execution authority")
        if self.promotion_status != "RESEARCH_ONLY_TRAJECTORY_REVIEW":
            raise ValueError("trajectory review cannot promote beyond research")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("trajectory review must remain live blocked")


@dataclass(frozen=True, slots=True)
class AgentTrajectoryReviewConfig:
    action_repeat_threshold: int = 3
    repeated_error_threshold: int = 3
    ping_pong_window: int = 4
    rewrite_retest_failures_threshold: int = 2
    max_steps_without_progress: int = 5

    def __post_init__(self) -> None:
        if (
            self.action_repeat_threshold < 2
            or self.repeated_error_threshold < 2
            or self.ping_pong_window < 4
            or self.ping_pong_window % 2 != 0
            or self.rewrite_retest_failures_threshold < 1
            or self.max_steps_without_progress < 1
        ):
            raise ValueError("trajectory review thresholds are invalid")


def review_agent_trajectory(
    *,
    session_id: str,
    task_name: str,
    steps: Sequence[AgentTrajectoryStep],
    config: AgentTrajectoryReviewConfig | None = None,
    budget_usd_spent: float = 0.0,
    budget_usd_limit: float | None = None,
) -> AgentTrajectoryReview:
    effective_config = config or AgentTrajectoryReviewConfig()
    step_tuple = tuple(steps)
    signals = _detect_signals(
        step_tuple,
        config=effective_config,
        budget_usd_spent=budget_usd_spent,
        budget_usd_limit=budget_usd_limit,
    )
    verdict = _verdict_for_signals(signals)
    blockers = _blockers_for(verdict, signals)
    return AgentTrajectoryReview(
        session_id=session_id,
        task_name=task_name,
        selected_pattern="evaluator-optimizer+human-in-the-loop",
        steps=step_tuple,
        signals=signals,
        verdict=verdict,
        blockers=blockers,
    )


def classify_error(text: str) -> str:
    lowered = text.casefold()
    for marker, error_class in _ERROR_CLASSES:
        if marker in lowered:
            return error_class
    return "UnknownError"


def _detect_signals(
    steps: tuple[AgentTrajectoryStep, ...],
    *,
    config: AgentTrajectoryReviewConfig,
    budget_usd_spent: float,
    budget_usd_limit: float | None,
) -> tuple[AgentTrajectorySignal, ...]:
    signals: list[AgentTrajectorySignal] = []
    if not steps:
        signals.append(AgentTrajectorySignal.TRAJECTORY_EMPTY)
    if budget_usd_spent < 0.0 or (
        budget_usd_limit is not None and budget_usd_limit < 0.0
    ):
        raise ValueError("trajectory budget values cannot be negative")
    if budget_usd_limit is not None and budget_usd_spent >= budget_usd_limit:
        signals.append(AgentTrajectorySignal.BUDGET_GUARDRAIL)
    if _has_action_observation_repeat(steps, config.action_repeat_threshold):
        signals.append(AgentTrajectorySignal.ACTION_OBSERVATION_REPEAT)
    if _has_repeated_error_class(steps, config.repeated_error_threshold):
        signals.append(AgentTrajectorySignal.REPEATED_ERROR_CLASS)
    if _has_ping_pong(steps, config.ping_pong_window):
        signals.append(AgentTrajectorySignal.PING_PONG_ACTIONS)
    if _has_rewrite_retest_cycle(steps, config.rewrite_retest_failures_threshold):
        signals.append(AgentTrajectorySignal.REWRITE_RETEST_CYCLE)
    if _steps_since_progress(steps) >= config.max_steps_without_progress:
        signals.append(AgentTrajectorySignal.STEPS_WITHOUT_PROGRESS)
    return tuple(dict.fromkeys(signals))


def _verdict_for_signals(
    signals: tuple[AgentTrajectorySignal, ...],
) -> AgentTrajectoryVerdict:
    if AgentTrajectorySignal.BUDGET_GUARDRAIL in signals:
        return AgentTrajectoryVerdict.HUMAN_REVIEW_REQUIRED
    restart_signals = {
        AgentTrajectorySignal.ACTION_OBSERVATION_REPEAT,
        AgentTrajectorySignal.PING_PONG_ACTIONS,
        AgentTrajectorySignal.REWRITE_RETEST_CYCLE,
        AgentTrajectorySignal.STEPS_WITHOUT_PROGRESS,
    }
    if any(signal in restart_signals for signal in signals):
        return AgentTrajectoryVerdict.RESTART_RECOMMENDED
    if signals:
        return AgentTrajectoryVerdict.WATCHLIST
    return AgentTrajectoryVerdict.CONTINUE_RESEARCH


def _blockers_for(
    verdict: AgentTrajectoryVerdict,
    signals: tuple[AgentTrajectorySignal, ...],
) -> tuple[str, ...]:
    blockers = list(_BASELINE_BLOCKERS)
    if verdict is AgentTrajectoryVerdict.HUMAN_REVIEW_REQUIRED:
        blockers.append("HUMAN_REVIEW_REQUIRED")
    if verdict is AgentTrajectoryVerdict.RESTART_RECOMMENDED:
        blockers.append("RESTART_RECOMMENDED")
    blockers.extend(signal.value for signal in signals)
    return tuple(dict.fromkeys(blockers))


def _has_action_observation_repeat(
    steps: tuple[AgentTrajectoryStep, ...],
    threshold: int,
) -> bool:
    previous: tuple[str, str, str, bool] | None = None
    count = 0
    for step in steps:
        signature = (step.tool_name, step.args_digest, step.output_digest, step.ok)
        count = count + 1 if signature == previous else 1
        previous = signature
        if count >= threshold:
            return True
    return False


def _has_repeated_error_class(
    steps: tuple[AgentTrajectoryStep, ...],
    threshold: int,
) -> bool:
    previous = ""
    count = 0
    for step in steps:
        error_class = step.error_class if not step.ok else ""
        count = count + 1 if error_class and error_class == previous else 1
        previous = error_class
        if error_class and count >= threshold:
            return True
    return False


def _has_ping_pong(steps: tuple[AgentTrajectoryStep, ...], window: int) -> bool:
    if len(steps) < window:
        return False
    for offset in range(0, len(steps) - window + 1):
        tools = tuple(step.tool_name for step in steps[offset : offset + window])
        if len(set(tools)) != 2:
            continue
        if all(tools[index] == tools[index % 2] for index in range(window)):
            return True
    return False


def _has_rewrite_retest_cycle(
    steps: tuple[AgentTrajectoryStep, ...],
    threshold: int,
) -> bool:
    cycles = 0
    waiting_for_failed_test = False
    for step in steps:
        if _is_write_tool(step.tool_name):
            waiting_for_failed_test = True
            continue
        if waiting_for_failed_test and _is_verification_tool(step.tool_name):
            if not step.ok:
                cycles += 1
            waiting_for_failed_test = False
        if cycles >= threshold:
            return True
    return False


def _steps_since_progress(steps: tuple[AgentTrajectoryStep, ...]) -> int:
    last_progress_index = 0
    for step in steps:
        if _is_progress_step(step):
            last_progress_index = step.index
    return len(steps) - last_progress_index


def _is_progress_step(step: AgentTrajectoryStep) -> bool:
    return step.verification_passed or (
        step.ok and _is_verification_tool(step.tool_name)
    )


def _is_write_tool(tool_name: str) -> bool:
    lowered = tool_name.casefold()
    return any(marker in lowered for marker in _WRITE_TOOLS)


def _is_verification_tool(tool_name: str) -> bool:
    lowered = tool_name.casefold()
    return any(marker in lowered for marker in _VERIFICATION_TOOLS)


def _looks_like_failure(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _FAILURE_MARKERS)


def _safe_preview(value: object, *, max_chars: int) -> str:
    if max_chars < 1:
        raise ValueError("preview length must be positive")
    text = " ".join(_canonical_text(value).split())
    if _SECRET_MARKERS.search(text):
        return "[REDACTED_CREDENTIAL]"
    return text[:max_chars]


def _canonical_text(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except TypeError:
        return repr(value)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _require_text(value: str, label: str, *, max_len: int) -> None:
    if not value.strip() or len(value) > max_len:
        raise ValueError(f"{label} is invalid")


def _require_preview(value: str, label: str) -> None:
    if len(value) > 220:
        raise ValueError(f"{label} is too large")
    if _SECRET_MARKERS.search(value):
        raise ValueError(f"{label} contains secret-like content")


def _require_digest(value: str, label: str) -> None:
    if not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{label} must be a sha256 hex digest")


def _require_unique_text(values: tuple[str, ...], label: str) -> None:
    if len(set(values)) != len(values) or any(not value.strip() for value in values):
        raise ValueError(f"{label} must contain unique non-empty values")

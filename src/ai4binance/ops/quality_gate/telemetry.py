"""Compact quality gate telemetry and console evidence helpers."""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

_SENSITIVE_OUTPUT = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|authorization)(\s*[:=]\s*)(\S+)"
)


@dataclass(frozen=True, slots=True)
class QualityStepTelemetry:
    """Bounded telemetry for one quality gate step."""

    step_id: str
    name: str
    started_at_utc: datetime
    ended_at_utc: datetime
    wall_time_ms: int
    exit_code: int | None
    status: str
    artifact_path: str = ""
    output_sha256: str = ""
    first_actionable_error: str = ""
    output_tail: str = ""
    output_truncated: bool = False


def first_actionable_error(output: str, *, max_characters: int = 500) -> str:
    """Return the first useful failure line without leaking sensitive values."""
    sanitized = sanitize_quality_output(output)
    for line in sanitized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if (
            "error" in lowered
            or "failed" in lowered
            or "traceback" in lowered
            or "assertionerror" in lowered
        ):
            return stripped[:max_characters]
    return sanitized.strip()[:max_characters]


def sanitize_quality_output(output: str) -> str:
    """Redact common secret-like tokens from quality tool output."""
    return _SENSITIVE_OUTPUT.sub(r"\1\2[REDACTED]", output)


def output_sha256(output: str) -> str:
    """Return a SHA-256 digest for sanitized output."""
    return hashlib.sha256(sanitize_quality_output(output).encode("utf-8")).hexdigest()


def build_compact_quality_console_summary(
    *,
    status: str,
    profile: str,
    run_id: str,
    duration_ms: int,
    selected_test_count: int,
    evidence_path: str,
    steps: Iterable[Mapping[str, object]],
    error: str | None = None,
) -> dict[str, object]:
    """Build the governed, token-bounded terminal summary for a gate run."""
    if selected_test_count < 0:
        raise ValueError("selected_test_count must be non-negative")

    material_steps = tuple(steps)
    normalized_status = status.strip().upper()
    run_passed = normalized_status in {"PASS", "PASSED"} or normalized_status.endswith(
        "_PASS"
    )
    if not run_passed:
        failed_step = next(
            (
                step
                for step in material_steps
                if str(step.get("status", "")).upper() not in {"PASS", "PASSED"}
            ),
            {},
        )
        actionable_error = str(failed_step.get("first_actionable_error", "")).strip()
        if actionable_error:
            actionable_error = first_actionable_error(actionable_error)
        if not actionable_error:
            actionable_error = first_actionable_error(error or "")
        if not actionable_error:
            actionable_error = "Quality gate failed; inspect evidence."
        return {
            "failed_step": failed_step.get("step_id", ""),
            "exit_code": failed_step.get("exit_code"),
            "first_actionable_error": actionable_error,
            "evidence_path": evidence_path,
        }

    tools = tuple(
        dict.fromkeys(
            step_id
            for step in material_steps
            if (step_id := str(step.get("step_id", "")).strip())
        )
    )
    return {
        "profile": profile,
        "run_id": run_id,
        "status": status,
        "duration": duration_ms,
        "tools": tools,
        "selected_test_count": selected_test_count,
        "evidence_path": evidence_path,
    }

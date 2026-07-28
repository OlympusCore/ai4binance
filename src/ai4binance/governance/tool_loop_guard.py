"""Fail-closed loop guardrails for governed tool calls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ai4binance.governance.tool_policy import ToolSideEffect


class ToolLoopAction(StrEnum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ValueError("tool call signature requires a tool name")
        if len(self.args_hash) != 64:
            raise ValueError("tool call signature args hash is invalid")

    @classmethod
    def from_call(
        cls,
        tool_name: str,
        arguments: Mapping[str, object] | None,
    ) -> ToolCallSignature:
        return cls(tool_name, _sha256(_canonical_json(arguments or {})))


@dataclass(frozen=True, slots=True)
class ToolLoopDecision:
    action: ToolLoopAction = ToolLoopAction.ALLOW
    code: str = "LOOP_GUARD_ALLOWED"
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None
    result_hash: str | None = None

    @property
    def blocked(self) -> bool:
        return self.action is ToolLoopAction.BLOCK

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("tool loop decision count cannot be negative")
        if self.result_hash is not None and len(self.result_hash) != 64:
            raise ValueError("tool loop decision result hash is invalid")


@dataclass(frozen=True, slots=True)
class ToolLoopGuardConfig:
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 4
    max_result_fingerprint_bytes: int = 16_384
    idempotent_side_effects: frozenset[ToolSideEffect] = field(
        default_factory=lambda: frozenset(
            {
                ToolSideEffect.READ_LOCAL,
                ToolSideEffect.NETWORK_READ,
            }
        )
    )

    def __post_init__(self) -> None:
        if (
            self.exact_failure_warn_after < 1
            or self.exact_failure_block_after < self.exact_failure_warn_after
            or self.no_progress_warn_after < 1
            or self.no_progress_block_after < self.no_progress_warn_after
            or self.max_result_fingerprint_bytes < 1
        ):
            raise ValueError("tool loop guard thresholds are invalid")


class ToolLoopGuard:
    """Detect repeated failures and idempotent no-progress loops."""

    def __init__(self, config: ToolLoopGuardConfig | None = None) -> None:
        self._config = config or ToolLoopGuardConfig()
        self._exact_failures: dict[ToolCallSignature, int] = {}
        self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}

    def before_call(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | None,
        side_effect: ToolSideEffect,
    ) -> ToolLoopDecision:
        signature = ToolCallSignature.from_call(tool_name, arguments)
        failure_count = self._exact_failures.get(signature, 0)
        if failure_count >= self._config.exact_failure_block_after:
            return ToolLoopDecision(
                ToolLoopAction.BLOCK,
                "REPEATED_EXACT_FAILURE_BLOCKED",
                tool_name,
                failure_count,
                signature,
            )
        progress = self._no_progress.get(signature)
        if (
            side_effect in self._config.idempotent_side_effects
            and progress is not None
            and progress[1] >= self._config.no_progress_block_after
        ):
            return ToolLoopDecision(
                ToolLoopAction.BLOCK,
                "IDEMPOTENT_NO_PROGRESS_BLOCKED",
                tool_name,
                progress[1],
                signature,
                progress[0],
            )
        return ToolLoopDecision(tool_name=tool_name, signature=signature)

    def after_call(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | None,
        side_effect: ToolSideEffect,
        result: object,
        failed: bool,
    ) -> ToolLoopDecision:
        signature = ToolCallSignature.from_call(tool_name, arguments)
        if failed:
            count = self._exact_failures.get(signature, 0) + 1
            self._exact_failures[signature] = count
            self._no_progress.pop(signature, None)
            if count >= self._config.exact_failure_warn_after:
                return ToolLoopDecision(
                    ToolLoopAction.WARN,
                    "REPEATED_EXACT_FAILURE_WARNING",
                    tool_name,
                    count,
                    signature,
                )
            return ToolLoopDecision(
                tool_name=tool_name,
                count=count,
                signature=signature,
            )

        self._exact_failures.pop(signature, None)
        if side_effect not in self._config.idempotent_side_effects:
            self._no_progress.pop(signature, None)
            return ToolLoopDecision(tool_name=tool_name, signature=signature)

        result_hash = _fingerprint_result(
            result,
            self._config.max_result_fingerprint_bytes,
        )
        previous = self._no_progress.get(signature)
        count = 1 if previous is None or previous[0] != result_hash else previous[1] + 1
        self._no_progress[signature] = (result_hash, count)
        if count >= self._config.no_progress_warn_after:
            return ToolLoopDecision(
                ToolLoopAction.WARN,
                "IDEMPOTENT_NO_PROGRESS_WARNING",
                tool_name,
                count,
                signature,
                result_hash,
            )
        return ToolLoopDecision(
            tool_name=tool_name,
            count=count,
            signature=signature,
            result_hash=result_hash,
        )


def default_tool_arguments(
    *,
    project: str,
    permission: object,
    target: str | None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "permission": str(permission),
        "project": project,
        "target": target,
    }
    if extra:
        payload.update(extra)
    return payload


def _fingerprint_result(result: object, max_bytes: int) -> str:
    encoded = _canonical_json(result).encode("utf-8", errors="replace")[:max_bytes]
    return _sha256(encoded.decode("utf-8", errors="replace"))


def _canonical_json(value: object) -> str:
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
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

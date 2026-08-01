"""Fail-closed experiment sandbox policy and backend contract."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Protocol


class SandboxRunStatus(StrEnum):
    """Experiment completion state with no production authority."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class SandboxCapabilities:
    """Security properties a real backend must prove before execution."""

    network_disabled: bool
    read_only_source: bool
    resource_limits: bool
    secret_free_environment: bool

    @property
    def ready(self) -> bool:
        return all(
            (
                self.network_disabled,
                self.read_only_source,
                self.resource_limits,
                self.secret_free_environment,
            )
        )


@dataclass(frozen=True, slots=True)
class ExperimentSandboxPolicy:
    """Bounded research policy independent of a Docker implementation."""

    allowed_imports: tuple[str, ...] = ("decimal", "math", "statistics")
    max_source_bytes: int = 65_536
    max_output_bytes: int = 16_384
    timeout_seconds: float = 10.0
    memory_limit_mb: int = 256
    cpu_limit: float = 1.0

    def __post_init__(self) -> None:
        if not self.allowed_imports or any(
            not item.strip() for item in self.allowed_imports
        ):
            raise ValueError("sandbox import allowlist cannot be empty")
        if len(set(self.allowed_imports)) != len(self.allowed_imports):
            raise ValueError("sandbox import allowlist must be unique")
        if not 1_024 <= self.max_source_bytes <= 1_048_576:
            raise ValueError("sandbox source limit is invalid")
        if not 1_024 <= self.max_output_bytes <= 1_048_576:
            raise ValueError("sandbox output limit is invalid")
        if not isfinite(self.timeout_seconds) or not 0.1 <= self.timeout_seconds <= 60:
            raise ValueError("sandbox timeout must be between 0.1 and 60 seconds")
        if not 64 <= self.memory_limit_mb <= 4_096:
            raise ValueError("sandbox memory limit is invalid")
        if not isfinite(self.cpu_limit) or not 0.1 <= self.cpu_limit <= 4.0:
            raise ValueError("sandbox CPU limit is invalid")


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    """Immutable run manifest suitable for an isolated backend."""

    experiment_id: str
    created_at: datetime
    source_sha256: str
    timeout_seconds: float
    memory_limit_mb: int
    cpu_limit: float
    network_allowed: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or len(self.source_sha256) != 64:
            raise ValueError("experiment manifest identity or hash is invalid")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("experiment manifest timestamp must be timezone-aware")
        if self.network_allowed or self.execution_authority:
            raise ValueError(
                "research experiment cannot use network or execution authority"
            )


@dataclass(frozen=True, slots=True)
class SandboxBackendOutput:
    """Capped raw output returned by a separately isolated backend."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class ExperimentSandboxBackend(Protocol):
    """Pluggable backend; no backend is selected implicitly."""

    @property
    def name(self) -> str:
        """Return a stable backend identifier."""

    @property
    def capabilities(self) -> SandboxCapabilities:
        """Return proven isolation capabilities."""

    def execute(
        self,
        manifest: ExperimentManifest,
        source: str,
    ) -> SandboxBackendOutput:
        """Execute only inside the backend's isolated environment."""


@dataclass(frozen=True, slots=True)
class SandboxRunResult:
    """Research-only result; completion never promotes code or parameters."""

    experiment_id: str
    status: SandboxRunStatus
    backend_name: str | None
    source_sha256: str
    blockers: tuple[str, ...]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or len(self.source_sha256) != 64:
            raise ValueError("sandbox result identity is invalid")
        if self.status is SandboxRunStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked sandbox run requires blockers")
        if self.status is SandboxRunStatus.COMPLETED and self.blockers:
            raise ValueError("completed sandbox run cannot contain blockers")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("sandbox output must remain research only")


_FORBIDDEN_CALLS = frozenset(
    {"__import__", "compile", "eval", "exec", "getattr", "input", "open"}
)
_FORBIDDEN_NODES = (ast.Global, ast.Nonlocal)
_SANDBOX_BACKEND_FAILURES = (RuntimeError, OSError, TimeoutError, ValueError)


def validate_experiment_source(
    source: str,
    policy: ExperimentSandboxPolicy,
) -> tuple[str, ...]:
    """Reject unsafe syntax before any backend sees the source."""
    if len(source.encode("utf-8")) > policy.max_source_bytes:
        return ("SANDBOX_SOURCE_TOO_LARGE",)
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError:
        return ("SANDBOX_SOURCE_SYNTAX_ERROR",)
    blockers: list[str] = []
    allowed = frozenset(policy.allowed_imports)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                tuple(alias.name.split(".", 1)[0] for alias in node.names)
                if isinstance(node, ast.Import)
                else ((node.module or "").split(".", 1)[0],)
            )
            if any(module not in allowed for module in modules):
                blockers.append("SANDBOX_IMPORT_NOT_ALLOWED")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALLS:
                blockers.append("SANDBOX_CALL_NOT_ALLOWED")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            blockers.append("SANDBOX_DUNDER_ACCESS_NOT_ALLOWED")
        elif isinstance(node, _FORBIDDEN_NODES):
            blockers.append("SANDBOX_SCOPE_MUTATION_NOT_ALLOWED")
    return tuple(dict.fromkeys(blockers))


@dataclass(frozen=True, slots=True)
class ExperimentSandbox:
    """Validate and delegate only to an explicitly supplied secure backend."""

    policy: ExperimentSandboxPolicy = ExperimentSandboxPolicy()
    backend: ExperimentSandboxBackend | None = None

    def run(
        self,
        *,
        experiment_id: str,
        source: str,
        created_at: datetime,
    ) -> SandboxRunResult:
        if not experiment_id.strip():
            raise ValueError("experiment ID cannot be empty")
        source_hash = sha256(source.encode("utf-8")).hexdigest()
        blockers = validate_experiment_source(source, self.policy)
        if blockers:
            return self._blocked(experiment_id, source_hash, blockers)
        if self.backend is None:
            return self._blocked(
                experiment_id, source_hash, ("SANDBOX_BACKEND_NOT_CONFIGURED",)
            )
        if not self.backend.capabilities.ready:
            return self._blocked(
                experiment_id,
                source_hash,
                ("SANDBOX_BACKEND_ISOLATION_INSUFFICIENT",),
                backend_name=self.backend.name,
            )
        manifest = ExperimentManifest(
            experiment_id=experiment_id,
            created_at=created_at,
            source_sha256=source_hash,
            timeout_seconds=self.policy.timeout_seconds,
            memory_limit_mb=self.policy.memory_limit_mb,
            cpu_limit=self.policy.cpu_limit,
        )
        try:
            output = self.backend.execute(manifest, source)
        except _SANDBOX_BACKEND_FAILURES:
            return self._blocked(
                experiment_id,
                source_hash,
                ("SANDBOX_BACKEND_FAILED",),
                backend_name=self.backend.name,
            )
        stdout = self._cap(output.stdout)
        stderr = self._cap(output.stderr)
        return SandboxRunResult(
            experiment_id=experiment_id,
            status=SandboxRunStatus.COMPLETED,
            backend_name=self.backend.name,
            source_sha256=source_hash,
            blockers=(),
            stdout=stdout,
            stderr=stderr,
            exit_code=output.exit_code,
        )

    def _cap(self, value: str) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= self.policy.max_output_bytes:
            return value
        return encoded[: self.policy.max_output_bytes].decode("utf-8", errors="ignore")

    @staticmethod
    def _blocked(
        experiment_id: str,
        source_hash: str,
        blockers: tuple[str, ...],
        *,
        backend_name: str | None = None,
    ) -> SandboxRunResult:
        return SandboxRunResult(
            experiment_id=experiment_id,
            status=SandboxRunStatus.BLOCKED,
            backend_name=backend_name,
            source_sha256=source_hash,
            blockers=blockers,
        )

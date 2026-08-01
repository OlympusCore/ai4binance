"""Fail-closed local privacy boundary for the Computer.md profile."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path


class PrivacyBoundaryStatus(StrEnum):
    """Machine-readable privacy boundary state."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class PrivacyBoundaryBlocker(StrEnum):
    """Fail-closed privacy blocker codes."""

    COMPUTER_MD_NOT_FOUND = "COMPUTER_MD_NOT_FOUND"
    COMPUTER_MD_UNREADABLE = "COMPUTER_MD_UNREADABLE"
    PERSONAL_INFO_OUTSIDE_COMPUTER_MD = "PERSONAL_INFO_OUTSIDE_COMPUTER_MD"


@dataclass(frozen=True, slots=True)
class PrivacyBoundaryFinding:
    """A redacted location where Computer.md-derived information was found."""

    file_path: str
    line_number: int
    token_sha256: str
    evidence_ref: str = "Computer.md"

    def __post_init__(self) -> None:
        if Path(self.file_path).is_absolute():
            raise ValueError("finding file_path must be repository-relative")
        if self.line_number < 1:
            raise ValueError("line_number must be 1 or greater")
        if not _SHA256_HEX_RE.fullmatch(self.token_sha256):
            raise ValueError("token_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class PrivacyBoundaryReport:
    """Typed privacy boundary report with no raw personal values."""

    status: PrivacyBoundaryStatus
    computer_profile_ref: str
    scanned_file_count: int
    finding_count: int
    findings: tuple[PrivacyBoundaryFinding, ...]
    blockers: tuple[PrivacyBoundaryBlocker, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("privacy boundary reports cannot allow execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("privacy boundary reports must keep live trading blocked")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("privacy boundary reports must stay research-only")
        if self.finding_count != len(self.findings):
            raise ValueError("finding_count must match findings")
        if self.scanned_file_count < 0:
            raise ValueError("scanned_file_count cannot be negative")
        if self.status is PrivacyBoundaryStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked reports require blockers")


DEFAULT_TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".cfg",
        ".css",
        ".csv",
        ".env",
        ".gitignore",
        ".html",
        ".ini",
        ".json",
        ".jsonl",
        ".lock",
        ".md",
        ".ps1",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
DEFAULT_EXCLUDED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".hardware",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "Artifacts",
        "Backtest",
        "Data",
        "Logs",
        "Models",
        "Secrets",
        "State",
        "Tools",
        "htmlcov",
    }
)
DEFAULT_EXCLUDED_FILES: frozenset[str] = frozenset({"Computer.md", "Computer.local.md"})

_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/\\-]{3,}")
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s`\"'<>|]+")
_SENSITIVE_FIELD_KEYS = frozenset(
    {
        "build",
        "computer",
        "device",
        "graphics",
        "gpu",
        "host",
        "machine",
        "model",
        "os",
        "path",
        "processor",
        "product",
        "python",
        "ram",
        "serial",
        "storage",
        "user",
        "vscode",
        "windows",
    }
)
_COMMON_TOKENS = frozenset(
    {
        "about",
        "agent",
        "ai4binance",
        "backup",
        "binance",
        "codex",
        "code",
        "computer",
        "core",
        "device",
        "edition",
        "experience",
        "graphics",
        "hardware",
        "installed",
        "local",
        "local-only",
        "markdown",
        "memory",
        "microsoft",
        "profile",
        "processor",
        "project",
        "python",
        "pyproject.toml",
        "ram",
        "repository",
        "repo-local",
        "storage",
        "studio",
        "system",
        "user-provided",
        "venv/scripts/python.exe",
        "visual",
        "windows",
        "windows_nt",
        "workspace",
        "x64-based",
    }
)
_COMMON_VERSION_TOKENS = frozenset(
    {
        "3.12.10",
        "64-bit",
    }
)


def scan_privacy_boundary(
    repo_root: Path,
    *,
    computer_md: Path | None = None,
    max_file_bytes: int = 1_000_000,
) -> PrivacyBoundaryReport:
    """Scan repo text files for sensitive tokens derived from Computer.md.

    The report intentionally contains only token hashes and repository-relative
    file paths. Raw Computer.md content never leaves the scanner.
    """

    root = repo_root.resolve()
    profile_path = (computer_md or root / "Computer.md").resolve()
    profile_ref = _safe_profile_ref(root, profile_path)
    if not profile_path.is_file():
        return PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.NOT_CONFIGURED,
            computer_profile_ref=profile_ref,
            scanned_file_count=0,
            finding_count=0,
            findings=(),
            blockers=(PrivacyBoundaryBlocker.COMPUTER_MD_NOT_FOUND,),
        )
    try:
        profile_text = profile_path.read_text(encoding="utf-8")
    except OSError:
        return PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.BLOCKED,
            computer_profile_ref=profile_ref,
            scanned_file_count=0,
            finding_count=0,
            findings=(),
            blockers=(PrivacyBoundaryBlocker.COMPUTER_MD_UNREADABLE,),
        )

    candidates = _extract_candidate_tokens(profile_text)
    findings: list[PrivacyBoundaryFinding] = []
    scanned_count = 0
    for path in _iter_scannable_files(root, max_file_bytes=max_file_bytes):
        scanned_count += 1
        relative = path.relative_to(root).as_posix()
        findings.extend(_scan_file(path, relative, candidates))

    blockers = (
        (PrivacyBoundaryBlocker.PERSONAL_INFO_OUTSIDE_COMPUTER_MD,) if findings else ()
    )
    status = PrivacyBoundaryStatus.BLOCKED if findings else PrivacyBoundaryStatus.PASSED
    return PrivacyBoundaryReport(
        status=status,
        computer_profile_ref=profile_ref,
        scanned_file_count=scanned_count,
        finding_count=len(findings),
        findings=tuple(findings),
        blockers=blockers,
    )


def _safe_profile_ref(root: Path, profile_path: Path) -> str:
    try:
        return profile_path.relative_to(root).as_posix()
    except ValueError:
        return profile_path.name


def _extract_candidate_tokens(text: str) -> frozenset[str]:
    candidates: set[str] = set()
    for path_value in _WINDOWS_PATH_RE.findall(text):
        path_candidate = path_value.rstrip(".,);]")
        candidates.add(path_candidate)
        candidates.update(_specific_tokens(path_candidate))
    for line in text.splitlines():
        line_lower = line.casefold()
        if not any(key in line_lower for key in _SENSITIVE_FIELD_KEYS):
            continue
        for raw in _TOKEN_RE.findall(line):
            token = raw.strip("`'\"()[]{}.,;:")
            if _is_specific_candidate(token):
                candidates.add(token)
    return frozenset(candidates)


def _specific_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in (raw.strip("`'\"()[]{}.,;:") for raw in _TOKEN_RE.findall(value))
        if _is_specific_candidate(token)
    )


def _is_specific_candidate(token: str) -> bool:
    normalized = token.casefold()
    if len(token) < 5:
        return False
    if normalized in _COMMON_TOKENS:
        return False
    if normalized in _COMMON_VERSION_TOKENS:
        return False
    if token.isdigit():
        return False
    return any(character.isdigit() for character in token) or any(
        marker in token for marker in (":", "\\", "/", "-", "_", ".")
    )


def _iter_scannable_files(
    root: Path,
    *,
    max_file_bytes: int,
) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in DEFAULT_EXCLUDED_DIRECTORIES for part in relative_parts[:-1]):
            continue
        if path.name in DEFAULT_EXCLUDED_FILES:
            continue
        if path.suffix and path.suffix not in DEFAULT_TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue
        files.append(path)
    return tuple(files)


def _scan_file(
    path: Path,
    relative: str,
    candidates: frozenset[str],
) -> tuple[PrivacyBoundaryFinding, ...]:
    findings: list[PrivacyBoundaryFinding] = []
    if not candidates:
        return ()
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ()
    matched_hashes: set[tuple[str, int]] = set()
    for line_number, line in enumerate(lines, start=1):
        for candidate in candidates:
            if candidate not in line:
                continue
            digest = sha256(candidate.encode("utf-8")).hexdigest()
            key = (digest, line_number)
            if key in matched_hashes:
                continue
            matched_hashes.add(key)
            findings.append(
                PrivacyBoundaryFinding(
                    file_path=relative,
                    line_number=line_number,
                    token_sha256=digest,
                )
            )
    return tuple(findings)

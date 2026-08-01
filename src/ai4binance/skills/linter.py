"""Deterministic linter for local Agent Skills."""

from __future__ import annotations

import re
from pathlib import Path

from ai4binance.skills.models import (
    SkillAuditReport,
    SkillManifest,
    SkillSeverity,
    SkillValidationIssue,
)
from ai4binance.skills.parser import SkillParseError, discover_skill_paths, read_skill

_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_HIGH_RISK_TOOL_HINTS = (
    "bash",
    "shell",
    "powershell",
    "python",
    "node",
    "web",
    "http",
    "fetch",
)
_AUTHORITY_DRIFT_TERMS = (
    "allow_auto_live_orders=true",
    "auto live",
    "authorize live",
    "bypass gate",
    "bypass risk",
    "execute order",
    "place order",
    "submit order",
    "live eligible",
)
_SECRET_TERMS = ("api key", "apikey", "secret", "private key", ".env")
_TRUST_LEVELS = {"trusted", "review-required", "quarantined", "local"}


def audit_skill_root(root: Path) -> SkillAuditReport:
    issues: list[SkillValidationIssue] = []
    skills: list[SkillManifest] = []
    try:
        skill_paths = discover_skill_paths(root)
    except SkillParseError as exc:
        issues.append(
            _issue("SKILL_ROOT_INVALID", SkillSeverity.BLOCKER, str(exc), root)
        )
        return _report(root, skills, issues)
    for skill_path in skill_paths:
        try:
            manifest = read_skill(skill_path)
        except SkillParseError as exc:
            issues.append(
                _issue(
                    "SKILL_PARSE_FAILED",
                    SkillSeverity.BLOCKER,
                    str(exc),
                    skill_path,
                )
            )
            continue
        skills.append(manifest)
        issues.extend(lint_skill_manifest(manifest))
    if not skill_paths:
        issues.append(
            _issue(
                "NO_SKILLS_FOUND",
                SkillSeverity.WARNING,
                "skill root contains no child directories with SKILL.md",
                root,
            )
        )
    return _report(root, skills, issues)


def lint_skill_manifest(manifest: SkillManifest) -> tuple[SkillValidationIssue, ...]:
    issues: list[SkillValidationIssue] = []
    path = Path(manifest.skill_file)
    if not manifest.name:
        issues.append(
            _issue("SKILL_NAME_MISSING", SkillSeverity.ERROR, "name is required", path)
        )
    elif not _NAME.fullmatch(manifest.name) or "--" in manifest.name:
        issues.append(
            _issue(
                "SKILL_NAME_INVALID",
                SkillSeverity.ERROR,
                "name must be lowercase alphanumeric or hyphen, max 64 chars",
                path,
            )
        )
    if manifest.name and manifest.name != Path(manifest.skill_dir).name:
        issues.append(
            _issue(
                "SKILL_NAME_DIRECTORY_MISMATCH",
                SkillSeverity.ERROR,
                "name must match parent directory",
                path,
            )
        )
    if not manifest.description.strip():
        issues.append(
            _issue(
                "SKILL_DESCRIPTION_MISSING",
                SkillSeverity.ERROR,
                "description is required",
                path,
            )
        )
    elif len(manifest.description) > 1024:
        issues.append(
            _issue(
                "SKILL_DESCRIPTION_TOO_LONG",
                SkillSeverity.ERROR,
                "description must be at most 1024 characters",
                path,
            )
        )
    if manifest.compatibility is not None and len(manifest.compatibility) > 500:
        issues.append(
            _issue(
                "SKILL_COMPATIBILITY_TOO_LONG",
                SkillSeverity.ERROR,
                "compatibility must be at most 500 characters",
                path,
            )
        )
    if len(manifest.body.splitlines()) > 500:
        issues.append(
            _issue(
                "SKILL_BODY_TOO_LONG",
                SkillSeverity.WARNING,
                "SKILL.md should stay under 500 lines; move details to references/",
                path,
            )
        )
    if (
        len(manifest.body.splitlines()) > 120
        and "references" not in manifest.optional_directories
    ):
        issues.append(
            _issue(
                "SKILL_PROGRESSIVE_DISCLOSURE_RECOMMENDED",
                SkillSeverity.WARNING,
                "long skills should move details to references/",
                path,
            )
        )
    _append_metadata_guidance(issues, manifest)
    if manifest.allowed_tools:
        issues.append(
            _issue(
                "SKILL_ALLOWED_TOOLS_EXPERIMENTAL",
                SkillSeverity.WARNING,
                "allowed-tools is advisory only and cannot enforce AI4BINANCE security",
                path,
            )
        )
        if _contains_any(manifest.allowed_tools, _HIGH_RISK_TOOL_HINTS):
            issues.append(
                _issue(
                    "SKILL_HIGH_RISK_TOOL_DECLARED",
                    SkillSeverity.BLOCKER,
                    "tool declaration includes shell, network or code execution hints",
                    path,
                )
            )
    if "scripts" in manifest.optional_directories:
        issues.append(
            _issue(
                "SKILL_SCRIPT_REVIEW_REQUIRED",
                SkillSeverity.BLOCKER,
                "bundled scripts require human supply-chain review before use",
                path,
            )
        )
    if manifest.root_files:
        issues.append(
            _issue(
                "SKILL_ROOT_EXTRA_FILES",
                SkillSeverity.WARNING,
                "root files outside SKILL.md may be loaded unintentionally",
                path,
            )
        )
    for reference in manifest.referenced_files:
        if reference.count("/") > 1:
            issues.append(
                _issue(
                    "SKILL_DEEP_REFERENCE",
                    SkillSeverity.WARNING,
                    "file references should remain one level deep from SKILL.md",
                    path,
                )
            )
    combined = f"{manifest.description}\n{manifest.body}".casefold()
    if _has_unnegated_authority_drift(combined):
        issues.append(
            _issue(
                "SKILL_AUTHORITY_DRIFT_REVIEW_REQUIRED",
                SkillSeverity.BLOCKER,
                "skill text appears to request trading or live authority",
                path,
            )
        )
    if _contains_any(combined, _SECRET_TERMS):
        issues.append(
            _issue(
                "SKILL_SECRET_HANDLING_REVIEW_REQUIRED",
                SkillSeverity.WARNING,
                "skill mentions credentials or secrets; verify redaction boundaries",
                path,
            )
        )
    return tuple(issues)


def _append_metadata_guidance(
    issues: list[SkillValidationIssue], manifest: SkillManifest
) -> None:
    path = Path(manifest.skill_file)
    if not manifest.metadata.get("ai4binance.authority", "").strip():
        issues.append(
            _issue(
                "SKILL_AUTHORITY_METADATA_MISSING",
                SkillSeverity.INFO,
                "metadata.ai4binance.authority is recommended",
                path,
            )
        )
    if not manifest.version:
        issues.append(
            _issue(
                "SKILL_VERSION_MISSING",
                SkillSeverity.ERROR,
                "metadata.ai4binance.version is required for reviewed local skills",
                path,
            )
        )
    if not manifest.owner:
        issues.append(
            _issue(
                "SKILL_OWNER_MISSING",
                SkillSeverity.WARNING,
                "metadata.ai4binance.owner should name the accountable owner",
                path,
            )
        )
    if not manifest.trust_level:
        issues.append(
            _issue(
                "SKILL_TRUST_LEVEL_MISSING",
                SkillSeverity.WARNING,
                "metadata.ai4binance.trust_level should define trust classification",
                path,
            )
        )
    elif manifest.trust_level.casefold() not in _TRUST_LEVELS:
        issues.append(
            _issue(
                "SKILL_TRUST_LEVEL_INVALID",
                SkillSeverity.ERROR,
                "trust_level must be trusted, local, review-required, or quarantined",
                path,
            )
        )
    if not manifest.last_reviewed:
        issues.append(
            _issue(
                "SKILL_LAST_REVIEWED_MISSING",
                SkillSeverity.WARNING,
                "metadata.ai4binance.last_reviewed should record the review date",
                path,
            )
        )
    if not manifest.trigger_examples:
        issues.append(
            _issue(
                "SKILL_TRIGGER_EXAMPLES_MISSING",
                SkillSeverity.WARNING,
                "metadata.ai4binance.trigger_examples should list trigger phrases",
                path,
            )
        )
    if "use when" not in manifest.description.casefold():
        issues.append(
            _issue(
                "SKILL_TRIGGER_DESCRIPTION_WEAK",
                SkillSeverity.WARNING,
                "description should start with a clear trigger such as 'Use when...'",
                path,
            )
        )


def _report(
    root: Path,
    skills: list[SkillManifest],
    issues: list[SkillValidationIssue],
) -> SkillAuditReport:
    blockers = tuple(
        dict.fromkeys(
            issue.code for issue in issues if issue.severity is SkillSeverity.BLOCKER
        )
    )
    return SkillAuditReport(
        root=str(root),
        skill_count=len(skills),
        issue_count=len(issues),
        blocker_count=len(blockers),
        high_risk_capability_count=sum(
            1 for issue in issues if issue.code == "SKILL_HIGH_RISK_TOOL_DECLARED"
        ),
        skills=tuple(skills),
        issues=tuple(issues),
        blockers=blockers,
    )


def _issue(
    code: str,
    severity: SkillSeverity,
    message: str,
    path: Path,
) -> SkillValidationIssue:
    return SkillValidationIssue(code, severity, message, str(path))


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    lowered = value.casefold()
    return any(needle in lowered for needle in needles)


def _has_unnegated_authority_drift(value: str) -> bool:
    for line in value.splitlines():
        if not _contains_any(line, _AUTHORITY_DRIFT_TERMS):
            continue
        if _contains_any(
            line,
            (
                "do not",
                "never",
                "cannot",
                "must not",
                "no ",
                "blocked",
                "without authority",
            ),
        ):
            continue
        return True
    return False

"""Config-driven quality gate profile and pytest-scope selection."""

import subprocess  # nosec B404
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


class AffectedScopeResolutionError(RuntimeError):
    """Raised when affected-test scope cannot be resolved without false confidence."""

    def __init__(
        self,
        message: str,
        *,
        unknown_paths: Sequence[str],
        escalate_to: str,
    ) -> None:
        super().__init__(message)
        self.unknown_paths = tuple(unknown_paths)
        self.escalate_to = escalate_to


@dataclass(frozen=True, slots=True)
class QualityGateProfile:
    """One governed quality gate profile."""

    name: str
    verification_status: str
    canonical_quality_authority: bool
    format_check: str
    lint: str
    type_check: str
    pytest_scope: str
    fail_fast: bool
    full_suite: bool
    execution_trigger: str


@dataclass(frozen=True, slots=True)
class AffectedTestMapping:
    """Mapping from changed path prefixes to required pytest files."""

    name: str
    path_prefixes: tuple[str, ...]
    tests: tuple[str, ...]
    tests_from_changed_paths: bool = False


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    """Machine-readable quality gate policy loaded from config/quality/gates.yaml."""

    version: int
    profiles: Mapping[str, QualityGateProfile]
    default_when_clean: tuple[str, ...]
    affected_mappings: tuple[AffectedTestMapping, ...]
    standard_impact_mappings: tuple[AffectedTestMapping, ...]
    required_tests: tuple[str, ...]
    unknown_impact_escalates_to: str


def load_quality_gate_policy(path: Path) -> QualityGatePolicy:
    """Load and validate the quality gate profile policy."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("quality gate policy must be a mapping")
    profiles_payload = _mapping(payload, "profiles")
    profiles = {
        name: _profile(name, _mapping(profiles_payload, name))
        for name in ("fast", "standard", "full")
    }
    affected_tests = _mapping(payload, "affected_tests")
    mappings = tuple(
        _affected_mapping(item) for item in _sequence(affected_tests, "mappings")
    )
    standard_impact_tests = _optional_mapping(payload, "standard_impact_tests")
    standard_impact_mappings = tuple(
        _affected_mapping(item)
        for item in _optional_sequence(standard_impact_tests, "mappings")
    )
    required_tests = tuple(_string_sequence(payload.get("required_tests", ())))
    return QualityGatePolicy(
        version=int(payload.get("version", 0)),
        profiles=profiles,
        default_when_clean=tuple(
            _string_sequence(affected_tests.get("default_when_clean", ()))
        ),
        affected_mappings=mappings,
        standard_impact_mappings=standard_impact_mappings,
        required_tests=required_tests,
        unknown_impact_escalates_to=str(
            affected_tests.get("unknown_impact_escalates_to", "standard")
        ),
    )


def changed_repository_paths(repository_root: Path) -> tuple[str, ...]:
    """Return git changed and untracked paths as repository-relative POSIX strings."""
    root = repository_root.resolve()
    changed: list[str] = []
    for arguments in (
        ("git", "-C", str(root), "diff", "--name-only", "HEAD", "--"),
        ("git", "-C", str(root), "ls-files", "--others", "--exclude-standard"),
    ):
        completed = subprocess.run(  # noqa: S603  # nosec B603
            arguments,
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise AffectedScopeResolutionError(
                f"changed path discovery failed with exit code {completed.returncode}",
                unknown_paths=("GIT_CHANGED_PATH_DISCOVERY_FAILED",),
                escalate_to="standard",
            )
        changed.extend(completed.stdout.splitlines())
    return tuple(sorted({_normalize_path(path) for path in changed if path.strip()}))


def resolve_profile_pytest_arguments(
    policy: QualityGatePolicy,
    profile: str,
    repository_root: Path,
    changed_paths: Sequence[str] = (),
) -> tuple[str, ...]:
    """Resolve pytest arguments for a profile from the canonical policy."""
    normalized_profile = profile.strip().lower()
    if normalized_profile not in policy.profiles:
        raise ValueError(f"unknown quality gate profile: {profile}")
    gate_profile = policy.profiles[normalized_profile]
    if gate_profile.pytest_scope == "affected":
        actual_changed_paths = tuple(changed_paths) or changed_repository_paths(
            repository_root
        )
        return resolve_affected_pytest_arguments(
            policy,
            repository_root,
            actual_changed_paths,
        )
    if gate_profile.pytest_scope == "required":
        if not policy.required_tests:
            raise ValueError("standard profile requires configured required_tests")
        actual_changed_paths = tuple(changed_paths) or changed_repository_paths(
            repository_root
        )
        return resolve_standard_pytest_arguments(
            policy,
            repository_root,
            actual_changed_paths,
        )
    if gate_profile.pytest_scope == "full":
        return ()
    raise ValueError(f"unsupported pytest scope: {gate_profile.pytest_scope}")


def resolve_standard_pytest_arguments(
    policy: QualityGatePolicy,
    repository_root: Path,
    changed_paths: Sequence[str],
) -> tuple[str, ...]:
    """Resolve STANDARD pytest arguments from required and impacted critical scopes."""
    if not policy.required_tests:
        raise ValueError("standard profile requires configured required_tests")
    normalized_changed_paths = tuple(
        _normalize_path(path) for path in changed_paths if path.strip()
    )
    selected_tests: list[str] = list(policy.required_tests)
    for changed_path in normalized_changed_paths:
        for mapping in _most_specific_matching_mappings(
            changed_path,
            policy.standard_impact_mappings,
        ):
            selected_tests.extend(mapping.tests)
            if mapping.tests_from_changed_paths and changed_path.endswith(".py"):
                selected_tests.append(changed_path)
    return _existing_tests_with_no_cov(repository_root, selected_tests)


def resolve_affected_pytest_arguments(
    policy: QualityGatePolicy,
    repository_root: Path,
    changed_paths: Sequence[str],
) -> tuple[str, ...]:
    """Resolve fail-closed affected pytest arguments for FAST profile."""
    normalized_changed_paths = tuple(
        _normalize_path(path) for path in changed_paths if path.strip()
    )
    if not normalized_changed_paths:
        return _existing_tests_with_no_cov(repository_root, policy.default_when_clean)

    selected_tests: list[str] = []
    unknown_paths: list[str] = []
    for changed_path in normalized_changed_paths:
        matching_mappings = _most_specific_matching_mappings(
            changed_path,
            policy.affected_mappings,
        )
        if matching_mappings:
            for mapping in matching_mappings:
                selected_tests.extend(mapping.tests)
                if mapping.tests_from_changed_paths and changed_path.endswith(".py"):
                    selected_tests.append(changed_path)
        else:
            unknown_paths.append(changed_path)

    if unknown_paths:
        unique_unknown_paths = tuple(sorted(set(unknown_paths)))
        raise AffectedScopeResolutionError(
            "FAST affected pytest scope cannot be resolved safely for: "
            + ", ".join(unique_unknown_paths)
            + ". Run scripts\\quality.ps1 -Profile standard or -Profile full.",
            unknown_paths=unique_unknown_paths,
            escalate_to=policy.unknown_impact_escalates_to,
        )
    return _existing_tests_with_no_cov(repository_root, selected_tests)


def _existing_tests_with_no_cov(
    repository_root: Path,
    tests: Iterable[str],
) -> tuple[str, ...]:
    root = repository_root.resolve()
    existing_tests: list[str] = []
    seen_tests: set[str] = set()
    for test in tests:
        normalized = _normalize_path(test)
        if normalized in seen_tests:
            continue
        if not _pytest_selection_exists(root, normalized):
            continue
        existing_tests.append(normalized)
        seen_tests.add(normalized)
    if not existing_tests:
        raise AffectedScopeResolutionError(
            "pytest scope resolved no existing tests. "
            "Run scripts\\quality.ps1 -Profile standard or -Profile full.",
            unknown_paths=("NO_EXISTING_TESTS",),
            escalate_to="standard",
        )
    return (*existing_tests, "--no-cov")


def _profile(name: str, payload: Mapping[str, Any]) -> QualityGateProfile:
    return QualityGateProfile(
        name=name,
        verification_status=str(payload.get("verification_status", "")),
        canonical_quality_authority=bool(
            payload.get("canonical_quality_authority", False)
        ),
        format_check=str(payload.get("format_check", "")),
        lint=str(payload.get("lint", "")),
        type_check=str(payload.get("type_check", "")),
        pytest_scope=str(payload.get("pytest_scope", "")),
        fail_fast=bool(payload.get("fail_fast", False)),
        full_suite=bool(payload.get("full_suite", False)),
        execution_trigger=str(payload.get("execution_trigger", "")),
    )


def _affected_mapping(payload: object) -> AffectedTestMapping:
    if not isinstance(payload, dict):
        raise ValueError("affected test mapping must be a mapping")
    mapping = cast(dict[str, object], payload)
    return AffectedTestMapping(
        name=str(mapping.get("name", "")),
        path_prefixes=tuple(_string_sequence(mapping.get("path_prefixes", ()))),
        tests=tuple(_string_sequence(mapping.get("tests", ()))),
        tests_from_changed_paths=bool(mapping.get("tests_from_changed_paths", False)),
    )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"quality gate policy field must be a mapping: {key}")
    return cast(Mapping[str, Any], value)


def _optional_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"quality gate policy field must be a mapping: {key}")
    return cast(Mapping[str, Any], value)


def _sequence(payload: Mapping[str, Any], key: str) -> Sequence[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"quality gate policy field must be a list: {key}")
    return value


def _optional_sequence(payload: Mapping[str, Any], key: str) -> Sequence[object]:
    value = payload.get(key, ())
    if not isinstance(value, list | tuple):
        raise ValueError(f"quality gate policy field must be a list: {key}")
    return value


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _matches_any_prefix(path: str, prefixes: Sequence[str]) -> bool:
    return any(path.startswith(_normalize_path(prefix)) for prefix in prefixes)


def _most_specific_matching_mappings(
    path: str,
    mappings: Sequence[AffectedTestMapping],
) -> tuple[AffectedTestMapping, ...]:
    matches: list[tuple[int, AffectedTestMapping]] = []
    for mapping in mappings:
        prefix_length = _matching_prefix_length(path, mapping.path_prefixes)
        if prefix_length >= 0:
            matches.append((prefix_length, mapping))
    if not matches:
        return ()
    max_prefix_length = max(prefix_length for prefix_length, _ in matches)
    return tuple(
        mapping
        for prefix_length, mapping in matches
        if prefix_length == max_prefix_length
    )


def _matching_prefix_length(path: str, prefixes: Sequence[str]) -> int:
    normalized_path = _normalize_path(path)
    matching_lengths = tuple(
        len(normalized_prefix)
        for prefix in prefixes
        if normalized_path.startswith(normalized_prefix := _normalize_path(prefix))
    )
    if not matching_lengths:
        return -1
    return max(matching_lengths)


def _pytest_selection_exists(root: Path, selection: str) -> bool:
    test_path = selection.split("::", maxsplit=1)[0]
    return (root / test_path).is_file()


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")

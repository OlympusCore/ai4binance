"""Canonical runtime artifact layout manifest for machine-generated evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


def default_runtime_artifact_layout_manifest_path() -> Path:
    """Return the default runtime artifact manifest path."""
    return _repository_root().joinpath(
        "config",
        "governance",
        "runtime_artifact_layout_manifest.json",
    )


@dataclass(frozen=True, slots=True)
class RuntimeRetentionPolicy:
    """Validated owner-scoped retention rule for one runtime family."""

    path: str
    cleanup_mode: str
    minimum_age_days: int
    keep_latest: int
    automatic_cleanup: bool
    entry_kind: str = "directory"

    def __post_init__(self) -> None:
        if not self.path.startswith("runtime/"):
            raise ValueError("runtime retention policy path must be under runtime")
        if not self.cleanup_mode.strip():
            raise ValueError("runtime retention cleanup mode must be non-empty")
        if self.minimum_age_days < 0 or self.keep_latest < 0:
            raise ValueError("runtime retention bounds cannot be negative")
        if self.entry_kind not in {"directory", "log_file"}:
            raise ValueError("runtime retention entry kind is invalid")


@dataclass(frozen=True, slots=True)
class RuntimeArtifactLayoutManifest:
    """Validated canonical and legacy runtime artifact path mappings."""

    canonical_root: str
    legacy_root: str
    roots: dict[str, str]
    legacy_roots: dict[str, str]
    retention: dict[str, RuntimeRetentionPolicy] = field(default_factory=dict)
    capacity_budgets: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = (
            self.canonical_root,
            self.legacy_root,
            *self.roots.values(),
            *self.legacy_roots.keys(),
            *self.legacy_roots.values(),
        )
        if any(not value.strip() for value in values):
            raise ValueError("runtime artifact layout paths must be non-empty")
        if any(
            not path.startswith("runtime/") or maximum_bytes < 1
            for path, maximum_bytes in self.capacity_budgets.items()
        ):
            raise ValueError("runtime capacity budgets must be positive runtime paths")

    def root_for(self, key: str) -> str:
        """Return a named canonical runtime artifact root."""
        try:
            return self.roots[key]
        except KeyError as error:
            raise ValueError(f"unknown runtime artifact root: {key}") from error

    def retention_for(self, key: str) -> RuntimeRetentionPolicy:
        """Return one named runtime retention policy."""
        try:
            return self.retention[key]
        except KeyError as error:
            raise ValueError(f"unknown runtime retention policy: {key}") from error

    @property
    def aliases(self) -> tuple[tuple[str, str], ...]:
        """Return legacy-to-canonical prefix mappings sorted by specificity."""
        return tuple(
            sorted(
                self.legacy_roots.items(),
                key=lambda item: len(item[0]),
                reverse=True,
            )
        )

    def canonicalize_uri(self, uri: str) -> str:
        """Normalize a runtime artifact URI to its canonical root."""
        normalized = uri.replace("\\", "/").strip()
        for legacy, canonical in self.aliases:
            if normalized == legacy or normalized.startswith(f"{legacy}/"):
                suffix = normalized[len(legacy) :].lstrip("/")
                return canonical if not suffix else f"{canonical}/{suffix}"
        return normalized


def load_runtime_artifact_layout_manifest(
    path: Path | None = None,
) -> RuntimeArtifactLayoutManifest:
    """Load and validate the runtime artifact layout manifest."""
    manifest_path = path or default_runtime_artifact_layout_manifest_path()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("runtime artifact layout manifest must be an object")
    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version not in {"1.0", "1.1"}:
        raise ValueError("runtime artifact layout manifest schema version is invalid")
    retention = _retention_mapping(payload.get("retention"))
    capacity_budgets = _capacity_budget_mapping(payload.get("capacity_budgets"))
    if schema_version == "1.1" and not retention:
        raise ValueError("runtime artifact layout retention must be non-empty")
    return RuntimeArtifactLayoutManifest(
        canonical_root=_text(payload, "canonical_root"),
        legacy_root=_text(payload, "legacy_root"),
        roots=_text_mapping(payload.get("roots"), "roots"),
        legacy_roots=_text_mapping(payload.get("legacy_roots"), "legacy_roots"),
        retention=retention,
        capacity_budgets=capacity_budgets,
    )


def _text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip().replace("\\", "/")
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _text_mapping(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{name} must be a non-empty object")
    normalized = {
        str(key).strip().replace("\\", "/"): str(item).strip().replace("\\", "/")
        for key, item in value.items()
    }
    if any(not key or not item for key, item in normalized.items()):
        raise ValueError(f"{name} must contain non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} keys must be unique")
    return normalized


def _retention_mapping(value: object) -> dict[str, RuntimeRetentionPolicy]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("retention must be an object")
    policies: dict[str, RuntimeRetentionPolicy] = {}
    for raw_key, raw_policy in value.items():
        key = str(raw_key).strip()
        if not key or not isinstance(raw_policy, Mapping):
            raise ValueError("retention entries must be named objects")
        automatic_cleanup = raw_policy.get("automatic_cleanup")
        minimum_age_days = raw_policy.get("minimum_age_days")
        keep_latest = raw_policy.get("keep_latest")
        if not isinstance(automatic_cleanup, bool):
            raise ValueError("runtime retention automatic_cleanup must be boolean")
        if not isinstance(minimum_age_days, int) or isinstance(minimum_age_days, bool):
            raise ValueError("runtime retention minimum_age_days must be an integer")
        if not isinstance(keep_latest, int) or isinstance(keep_latest, bool):
            raise ValueError("runtime retention keep_latest must be an integer")
        policies[key] = RuntimeRetentionPolicy(
            path=_text(raw_policy, "path"),
            cleanup_mode=_text(raw_policy, "cleanup_mode"),
            minimum_age_days=minimum_age_days,
            keep_latest=keep_latest,
            automatic_cleanup=automatic_cleanup,
            entry_kind=_retention_entry_kind(raw_policy.get("entry_kind", "directory")),
        )
    return policies


def _retention_entry_kind(value: object) -> str:
    entry_kind = str(value).strip()
    if entry_kind not in {"directory", "log_file"}:
        raise ValueError("runtime retention entry kind is invalid")
    return entry_kind


def _capacity_budget_mapping(value: object) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("capacity_budgets must be an object")
    budgets: dict[str, int] = {}
    for raw_path, raw_maximum_bytes in value.items():
        path = str(raw_path).strip().replace("\\", "/")
        if not path.startswith("runtime/"):
            raise ValueError("runtime capacity budgets must use runtime paths")
        if not isinstance(raw_maximum_bytes, int) or isinstance(
            raw_maximum_bytes, bool
        ):
            raise ValueError("runtime capacity budget must be an integer")
        if raw_maximum_bytes < 1:
            raise ValueError("runtime capacity budget must be positive")
        budgets[path] = raw_maximum_bytes
    return budgets


def _repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "config").is_dir() and (candidate / "src").is_dir():
            return candidate
    raise ValueError("repository root could not be determined from module path")
